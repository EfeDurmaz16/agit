use std::collections::{HashMap, HashSet, VecDeque};

use chrono::Utc;
use serde_json::Value;
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::error::{AgitError, Result};
use crate::hash::compute_state_hash;
use crate::objects::{Blob, Commit};
use crate::refs::{Head, RefStore};
use crate::state::{merkle_diff, three_way_merge, AgentState, StateDiff};
use crate::storage::{LogEntry, LogFilter, StorageBackend};
use crate::gc;
use crate::types::{ActionType, Hash, MergeStrategy, ObjectType};

#[cfg(feature = "encryption")]
use crate::encryption::StateEncryptor;

/// The main VCS repository, orchestrating storage, refs, and object model.
pub struct Repository {
    storage: Box<dyn StorageBackend>,
    refs: RefStore,
    agent_id: String,
    #[cfg(feature = "encryption")]
    encryptor: Option<StateEncryptor>,
}

impl Repository {
    /// Initialize a new repository with the given storage backend.
    pub async fn init(storage: Box<dyn StorageBackend>) -> Result<Self> {
        storage.initialize().await?;

        let mut refs = RefStore::new();

        // Load existing refs from storage
        let stored_refs = storage.list_refs().await?;
        if !stored_refs.is_empty() {
            refs.load_from_map(stored_refs);
        }

        Ok(Repository {
            storage,
            refs,
            agent_id: "default".to_string(),
            #[cfg(feature = "encryption")]
            encryptor: None,
        })
    }

    /// Set the agent ID for audit logging.
    pub fn set_agent_id(&mut self, id: &str) {
        self.agent_id = id.to_string();
    }

    /// Set an encryption key to encrypt/decrypt agent state fields at rest.
    #[cfg(feature = "encryption")]
    pub fn set_encryption_key(&mut self, key: &str) {
        self.encryptor = Some(StateEncryptor::with_context(key, &self.agent_id));
    }

    /// Commit agent state, returning the commit hash.
    pub async fn commit(
        &mut self,
        state: &AgentState,
        message: &str,
        action_type: ActionType,
    ) -> Result<Hash> {
        self.commit_with_metadata(state, message, action_type, serde_json::Map::new())
            .await
    }

    /// Commit with additional metadata.
    #[cfg_attr(feature = "observability", tracing::instrument(skip(self, state, metadata)))]
    pub async fn commit_with_metadata(
        &mut self,
        state: &AgentState,
        message: &str,
        action_type: ActionType,
        metadata: serde_json::Map<String, Value>,
    ) -> Result<Hash> {
        // Optional encryption
        let final_state = match self.get_encryptor() {
            #[cfg(feature = "encryption")]
            Some(enc) => enc.encrypt_state(state)?,
            _ => state.clone(),
        };

        // Store the state as a blob
        let state_value = final_state.to_value();
        let blob = Blob::new(state_value);
        let tree_hash = blob.hash();
        self.storage
            .put_object(tree_hash.as_str(), ObjectType::Blob, &blob.serialize())
            .await?;

        // Determine parent(s)
        let parent_hashes = match self.refs.resolve_ref("HEAD") {
            Ok(hash) => vec![hash],
            Err(AgitError::NoCommits) => vec![],
            Err(e) => return Err(e),
        };

        // Create the commit
        let commit = Commit {
            tree_hash: tree_hash.clone(),
            parent_hashes,
            message: message.to_string(),
            author: self.agent_id.clone(),
            timestamp: Utc::now(),
            action_type: action_type.clone(),
            metadata,
        };
        let commit_hash = commit.hash();
        let commit_data = serde_json::to_vec(&commit)?;
        self.storage
            .put_object(commit_hash.as_str(), ObjectType::Commit, &commit_data)
            .await?;

        // Update branch ref
        match self.refs.get_head() {
            Head::Attached(branch) => {
                let branch = branch.clone();
                if self.refs.list_branches().contains_key(&branch) {
                    self.refs.update_branch(&branch, commit_hash.clone())?;
                } else {
                    self.refs.create_branch(&branch, commit_hash.clone())?;
                }
                self.storage
                    .set_ref(&branch, commit_hash.as_str())
                    .await?;
            }
            Head::Detached(_) => {
                self.refs.set_head(commit_hash.as_str(), true);
            }
        }

        // Persist HEAD
        let refs_map = self.refs.to_map();
        if let Some(head_val) = refs_map.get("HEAD") {
            self.storage.set_ref("HEAD", head_val).await?;
        }

        // Audit log
        self.log_action(
            &action_type.to_string(),
            message,
            Some(commit_hash.as_str()),
        )
        .await?;

        Ok(commit_hash)
    }

    /// Create a new branch at the given source (or HEAD).
    pub async fn branch(&mut self, name: &str, from: Option<&str>) -> Result<()> {
        let source_hash = match from {
            Some(src) => self.resolve(src)?,
            None => self.refs.resolve_ref("HEAD")?,
        };
        self.refs.create_branch(name, source_hash.clone())?;
        self.storage.set_ref(name, source_hash.as_str()).await?;
        Ok(())
    }

    /// Checkout a branch or commit, returning the state at that point.
    pub async fn checkout(&mut self, target: &str) -> Result<AgentState> {
        // Try as branch first
        if self.refs.list_branches().contains_key(target) {
            self.refs.set_head(target, false);
            let hash = self.refs.resolve_ref(target)?;
            let refs_map = self.refs.to_map();
            if let Some(head_val) = refs_map.get("HEAD") {
                self.storage.set_ref("HEAD", head_val).await?;
            }
            return self.get_state(hash.as_str()).await;
        }

        // Try as commit hash
        if self.storage.has_object(target).await? {
            self.refs.set_head(target, true);
            let refs_map = self.refs.to_map();
            if let Some(head_val) = refs_map.get("HEAD") {
                self.storage.set_ref("HEAD", head_val).await?;
            }
            return self.get_state(target).await;
        }

        Err(AgitError::RefNotFound {
            name: target.to_string(),
        })
    }

    /// Compute the diff between two commits.
    /// Uses Merkle trees for O(log N) performance on large states.
    #[cfg_attr(feature = "observability", tracing::instrument(skip(self)))]
    pub async fn diff(&self, hash1: &str, hash2: &str) -> Result<StateDiff> {
        let state1 = self.get_state(hash1).await?;
        let state2 = self.get_state(hash2).await?;
        
        let entries = merkle_diff(&state1.to_value(), &state2.to_value());
        
        Ok(StateDiff {
            base_hash: hash1.to_string(),
            target_hash: hash2.to_string(),
            entries,
        })
    }

    /// Merge a branch into the current branch.
    #[cfg_attr(feature = "observability", tracing::instrument(skip(self)))]
    pub async fn merge(&mut self, branch: &str, strategy: MergeStrategy) -> Result<Hash> {
        let current_branch = match self.refs.get_head() {
            Head::Attached(name) => name.clone(),
            Head::Detached(_) => return Err(AgitError::DetachedHead),
        };

        let ours_hash = self.refs.resolve_ref(&current_branch)?;
        let theirs_hash = self.refs.resolve_ref(branch)?;

        // Fast-forward check
        if ours_hash == theirs_hash {
            return Ok(ours_hash);
        }

        // Find merge base
        let base_hash = self.find_merge_base(ours_hash.as_str(), theirs_hash.as_str()).await?;

        let base_state = self.get_state(base_hash.as_str()).await?;
        let ours_state = self.get_state(ours_hash.as_str()).await?;
        let theirs_state = self.get_state(theirs_hash.as_str()).await?;

        let merged_state = match strategy {
            MergeStrategy::Ours => ours_state.clone(),
            MergeStrategy::Theirs => theirs_state.clone(),
            MergeStrategy::ThreeWay => {
                let base_val = base_state.to_value();
                let ours_val = ours_state.to_value();
                let theirs_val = theirs_state.to_value();

                let (merged_val, conflicts) = three_way_merge(&base_val, &ours_val, &theirs_val);

                if !conflicts.is_empty() {
                    let conflict_paths: Vec<String> = conflicts
                        .iter()
                        .map(|c| c.path.join("."))
                        .collect();
                    return Err(AgitError::MergeConflict {
                        details: format!("conflicts at: {}", conflict_paths.join(", ")),
                    });
                }

                serde_json::from_value::<AgentState>(merged_val)
                    .map_err(|e| AgitError::Serialization(e.to_string()))?
            }
        };

        // Create merge commit with two parents
        let blob = Blob::new(merged_state.to_value());
        let tree_hash = blob.hash();
        self.storage
            .put_object(tree_hash.as_str(), ObjectType::Blob, &blob.serialize())
            .await?;

        let commit = Commit {
            tree_hash,
            parent_hashes: vec![ours_hash, theirs_hash],
            message: format!("merge branch '{}' into '{}'", branch, current_branch),
            author: self.agent_id.clone(),
            timestamp: Utc::now(),
            action_type: ActionType::Merge,
            metadata: serde_json::Map::new(),
        };

        let commit_hash = commit.hash();
        let commit_data = serde_json::to_vec(&commit)?;
        self.storage
            .put_object(commit_hash.as_str(), ObjectType::Commit, &commit_data)
            .await?;

        // Update current branch
        self.refs.update_branch(&current_branch, commit_hash.clone())?;
        self.storage
            .set_ref(&current_branch, commit_hash.as_str())
            .await?;

        let refs_map = self.refs.to_map();
        if let Some(head_val) = refs_map.get("HEAD") {
            self.storage.set_ref("HEAD", head_val).await?;
        }

        self.log_action(
            "merge",
            &format!("merged '{}' into '{}'", branch, current_branch),
            Some(commit_hash.as_str()),
        )
        .await?;

        Ok(commit_hash)
    }

    /// Get commit history for a branch (or HEAD).
    pub async fn log(&self, branch: Option<&str>, limit: usize) -> Result<Vec<Commit>> {
        let start_hash = match branch {
            Some(b) => self.refs.resolve_ref(b)?,
            None => self.refs.resolve_ref("HEAD")?,
        };

        let mut commits = Vec::new();
        let mut queue = VecDeque::new();
        let mut visited = HashSet::new();

        queue.push_back(start_hash);

        while let Some(hash) = queue.pop_front() {
            if commits.len() >= limit || visited.contains(&hash) {
                continue;
            }
            visited.insert(hash.clone());

            if let Some(commit) = self.get_commit(hash.as_str()).await? {
                for parent in &commit.parent_hashes {
                    if !visited.contains(parent) {
                        queue.push_back(parent.clone());
                    }
                }
                commits.push(commit);
            }
        }

        // Sort by timestamp descending
        commits.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
        commits.truncate(limit);
        Ok(commits)
    }

    /// Revert to a previous state, creating a new revert commit.
    #[cfg_attr(feature = "observability", tracing::instrument(skip(self)))]
    pub async fn revert(&mut self, to_hash: &str) -> Result<AgentState> {
        let state = self.get_state(to_hash).await?;
        let message = format!("revert to {}", &to_hash[..8.min(to_hash.len())]);
        self.commit(&state, &message, ActionType::Rollback).await?;
        Ok(state)
    }

    /// Find the merge base (lowest common ancestor) of two commits using BFS.
    pub async fn find_merge_base(&self, h1: &str, h2: &str) -> Result<Hash> {
        const MAX_DEPTH: usize = 10_000;

        // BFS from both commits, find first intersection
        let ancestors1 = self.collect_ancestors(h1, MAX_DEPTH).await?;

        let mut queue = VecDeque::new();
        let mut visited = HashSet::new();
        let mut depth = 0usize;
        queue.push_back(Hash::from(h2));

        while let Some(hash) = queue.pop_front() {
            if ancestors1.contains(&hash) {
                return Ok(hash);
            }
            if visited.contains(&hash) {
                continue;
            }
            visited.insert(hash.clone());

            depth += 1;
            if depth > MAX_DEPTH {
                return Err(AgitError::DepthLimitExceeded(
                    "merge base depth limit exceeded".to_string(),
                ));
            }

            if let Some(commit) = self.get_commit(hash.as_str()).await? {
                for parent in commit.parent_hashes {
                    if !visited.contains(&parent) {
                        queue.push_back(parent);
                    }
                }
            }
        }

        // If no common ancestor, return h1 (initial commit scenario)
        Ok(Hash::from(h1))
    }

    /// Get the agent state stored at a commit.
    pub async fn get_state(&self, hash: &str) -> Result<AgentState> {
        let commit = self
            .get_commit(hash)
            .await?
            .ok_or_else(|| AgitError::ObjectNotFound {
                hash: hash.to_string(),
            })?;

        let blob_data = self
            .storage
            .get_object(commit.tree_hash.as_str())
            .await?
            .ok_or_else(|| AgitError::ObjectNotFound {
                hash: commit.tree_hash.to_string(),
            })?;

        let state: AgentState = serde_json::from_slice(&blob_data)?;

        // Optional decryption
        match self.get_encryptor() {
            #[cfg(feature = "encryption")]
            Some(enc) => enc.decrypt_state(&state),
            _ => Ok(state),
        }
    }

    /// Helper to get encryptor if feature is enabled.
    #[cfg(feature = "encryption")]
    fn get_encryptor(&self) -> Option<&StateEncryptor> {
        self.encryptor.as_ref()
    }

    #[cfg(not(feature = "encryption"))]
    fn get_encryptor(&self) -> Option<()> {
        None
    }

    /// Get the current HEAD hash.
    pub fn head(&self) -> Result<Hash> {
        self.refs.resolve_ref("HEAD")
    }

    /// Get current branch name.
    pub fn current_branch(&self) -> Option<&str> {
        self.refs.current_branch()
    }

    /// List all branches.
    pub fn list_branches(&self) -> &HashMap<String, Hash> {
        self.refs.list_branches()
    }

    /// Delete a branch.
    pub async fn delete_branch(&mut self, name: &str) -> Result<()> {
        self.refs.delete_branch(name)?;
        self.storage.delete_ref(name).await?;
        Ok(())
    }

    /// Query audit logs.
    pub async fn audit_log(&self, filter: &LogFilter) -> Result<Vec<LogEntry>> {
        self.storage.query_logs(filter).await
    }

    /// Get the state hash for content addressing.
    pub fn compute_state_hash(state: &AgentState) -> Hash {
        compute_state_hash(&state.to_value())
    }

    /// Run garbage collection to remove unreachable objects.
    pub async fn gc(&self, keep_last_n: usize) -> Result<gc::GcResult> {
        gc::gc(&*self.storage, &self.refs, keep_last_n).await
    }

    /// Squash a range of commits into a single commit.
    pub async fn squash(
        &mut self,
        branch: &str,
        from_hash: &str,
        to_hash: &str,
    ) -> Result<gc::SquashResult> {
        gc::squash(
            &*self.storage,
            &mut self.refs,
            &self.agent_id,
            branch,
            from_hash,
            to_hash,
        )
        .await
    }

    // --- Private helpers ---

    fn resolve(&self, name: &str) -> Result<Hash> {
        // Try as branch, then as raw hash
        self.refs.resolve_ref(name).or_else(|_| {
            // Assume it's a commit hash
            Ok(Hash::from(name))
        })
    }

    async fn get_commit(&self, hash: &str) -> Result<Option<Commit>> {
        let data = self.storage.get_object(hash).await?;
        match data {
            Some(bytes) => {
                let commit: Commit = serde_json::from_slice(&bytes)?;
                Ok(Some(commit))
            }
            None => Ok(None),
        }
    }

    async fn collect_ancestors(&self, hash: &str, max_depth: usize) -> Result<HashSet<Hash>> {
        let mut ancestors = HashSet::new();
        let mut queue = VecDeque::new();
        queue.push_back(Hash::from(hash));

        while let Some(h) = queue.pop_front() {
            if ancestors.contains(&h) {
                continue;
            }
            ancestors.insert(h.clone());

            if ancestors.len() > max_depth {
                return Err(AgitError::DepthLimitExceeded(
                    "ancestor traversal depth limit exceeded".to_string(),
                ));
            }

            if let Some(commit) = self.get_commit(h.as_str()).await? {
                for parent in commit.parent_hashes {
                    queue.push_back(parent);
                }
            }
        }

        Ok(ancestors)
    }

    async fn log_action(
        &self,
        action: &str,
        message: &str,
        commit_hash: Option<&str>,
    ) -> Result<()> {
        let mut filter = LogFilter::default();
        filter.agent_id = Some(self.agent_id.clone());
        filter.limit = Some(1);
        let prev_hash = self
            .storage
            .query_logs(&filter)
            .await?
            .first()
            .and_then(|e| e.details.as_ref())
            .and_then(|d| d.get("integrity_hash"))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        let timestamp = Utc::now().to_rfc3339();
        let id = Uuid::new_v4().to_string();
        let chain_hash = compute_audit_hash(
            &id,
            &timestamp,
            &self.agent_id,
            action,
            message,
            commit_hash.unwrap_or(""),
            prev_hash.as_deref(),
        );

        let entry = LogEntry {
            id,
            timestamp,
            agent_id: self.agent_id.clone(),
            action: action.to_string(),
            message: message.to_string(),
            commit_hash: commit_hash.map(|s| s.to_string()),
            details: Some(serde_json::json!({
                "integrity_hash": chain_hash,
                "prev_integrity_hash": prev_hash,
            })),
            level: "info".to_string(),
        };
        self.storage.append_log(&entry).await
    }
}

fn compute_audit_hash(
    id: &str,
    timestamp: &str,
    agent_id: &str,
    action: &str,
    message: &str,
    commit_hash: &str,
    prev_hash: Option<&str>,
) -> String {
    let mut hasher = Sha256::new();
    hasher.update(id.as_bytes());
    hasher.update(b"|");
    hasher.update(timestamp.as_bytes());
    hasher.update(b"|");
    hasher.update(agent_id.as_bytes());
    hasher.update(b"|");
    hasher.update(action.as_bytes());
    hasher.update(b"|");
    hasher.update(message.as_bytes());
    hasher.update(b"|");
    hasher.update(commit_hash.as_bytes());
    hasher.update(b"|");
    hasher.update(prev_hash.unwrap_or("").as_bytes());
    format!("{:x}", hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::sqlite::SqliteStorage;
    use serde_json::json;

    async fn test_repo() -> Repository {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        Repository::init(Box::new(storage)).await.unwrap()
    }

    #[tokio::test]
    async fn test_init() {
        let repo = test_repo().await;
        assert_eq!(repo.current_branch(), Some("main"));
    }

    #[tokio::test]
    async fn test_commit_and_log() {
        let mut repo = test_repo().await;
        let state = AgentState::new(json!({"counter": 1}), json!({}));
        let hash = repo
            .commit(&state, "first commit", ActionType::ToolCall)
            .await
            .unwrap();
        assert_eq!(hash.0.len(), 64);

        let commits = repo.log(None, 10).await.unwrap();
        assert_eq!(commits.len(), 1);
        assert_eq!(commits[0].message, "first commit");
    }

    #[tokio::test]
    async fn test_multiple_commits() {
        let mut repo = test_repo().await;

        let s1 = AgentState::new(json!({"step": 1}), json!({}));
        repo.commit(&s1, "step 1", ActionType::ToolCall).await.unwrap();

        let s2 = AgentState::new(json!({"step": 2}), json!({}));
        repo.commit(&s2, "step 2", ActionType::ToolCall).await.unwrap();

        let s3 = AgentState::new(json!({"step": 3}), json!({}));
        repo.commit(&s3, "step 3", ActionType::ToolCall).await.unwrap();

        let commits = repo.log(None, 10).await.unwrap();
        assert_eq!(commits.len(), 3);
    }

    #[tokio::test]
    async fn test_branch_and_checkout() {
        let mut repo = test_repo().await;

        let s1 = AgentState::new(json!({"v": 1}), json!({}));
        repo.commit(&s1, "initial", ActionType::ToolCall).await.unwrap();

        repo.branch("feature", None).await.unwrap();
        let state = repo.checkout("feature").await.unwrap();
        assert_eq!(state.memory, json!({"v": 1}));
        assert_eq!(repo.current_branch(), Some("feature"));
    }

    #[tokio::test]
    async fn test_diff() {
        let mut repo = test_repo().await;

        let s1 = AgentState::new(json!({"a": 1, "b": 2}), json!({}));
        let h1 = repo.commit(&s1, "first", ActionType::ToolCall).await.unwrap();

        let s2 = AgentState::new(json!({"a": 1, "b": 3, "c": 4}), json!({}));
        let h2 = repo.commit(&s2, "second", ActionType::ToolCall).await.unwrap();

        let diff = repo.diff(h1.as_str(), h2.as_str()).await.unwrap();
        assert!(!diff.entries.is_empty());
    }

    #[tokio::test]
    async fn test_revert() {
        let mut repo = test_repo().await;

        let s1 = AgentState::new(json!({"v": 1}), json!({}));
        let h1 = repo.commit(&s1, "first", ActionType::ToolCall).await.unwrap();

        let s2 = AgentState::new(json!({"v": 2}), json!({}));
        repo.commit(&s2, "second", ActionType::ToolCall).await.unwrap();

        let reverted = repo.revert(h1.as_str()).await.unwrap();
        assert_eq!(reverted.memory, json!({"v": 1}));

        // Should now have 3 commits
        let commits = repo.log(None, 10).await.unwrap();
        assert_eq!(commits.len(), 3);
    }

    #[tokio::test]
    async fn test_merge_ours() {
        let mut repo = test_repo().await;

        let s1 = AgentState::new(json!({"v": 1}), json!({}));
        repo.commit(&s1, "initial", ActionType::ToolCall).await.unwrap();

        repo.branch("feature", None).await.unwrap();
        repo.checkout("feature").await.unwrap();

        let s2 = AgentState::new(json!({"v": 2}), json!({}));
        repo.commit(&s2, "feature work", ActionType::ToolCall).await.unwrap();

        repo.checkout("main").await.unwrap();

        let s3 = AgentState::new(json!({"v": 3}), json!({}));
        repo.commit(&s3, "main work", ActionType::ToolCall).await.unwrap();

        let merge_hash = repo.merge("feature", MergeStrategy::Ours).await.unwrap();
        let merged_state = repo.get_state(merge_hash.as_str()).await.unwrap();
        assert_eq!(merged_state.memory, json!({"v": 3}));
    }

    #[tokio::test]
    async fn test_get_state() {
        let mut repo = test_repo().await;
        let state = AgentState::new(json!({"data": "hello"}), json!({"world": true}));
        let hash = repo
            .commit(&state, "test", ActionType::Checkpoint)
            .await
            .unwrap();

        let retrieved = repo.get_state(hash.as_str()).await.unwrap();
        assert_eq!(retrieved.memory, json!({"data": "hello"}));
        assert_eq!(retrieved.world_state, json!({"world": true}));
    }

    #[tokio::test]
    async fn test_audit_log() {
        let mut repo = test_repo().await;
        let state = AgentState::new(json!({}), json!({}));
        repo.commit(&state, "test action", ActionType::ToolCall)
            .await
            .unwrap();

        let filter = LogFilter {
            limit: Some(10),
            ..Default::default()
        };
        let logs = repo.audit_log(&filter).await.unwrap();
        assert!(!logs.is_empty());
    }
}
