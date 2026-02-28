//! Retention policy support for automatic cleanup of old commits and logs.
//!
//! Provides configurable policies for:
//! - Commit age and count limits per branch
//! - Protected branches that are never pruned
//! - Audit log age and count limits
//! - Full enforcement with actual object deletion

use std::collections::{HashSet, VecDeque};
use std::time::Duration;

use chrono::Utc;
use serde::{Deserialize, Serialize};

use crate::error::Result;
use crate::objects::Commit;
use crate::refs::RefStore;
use crate::storage::StorageBackend;
use crate::types::Hash;

/// Configurable retention policy for repository data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetentionPolicy {
    /// Maximum age for commits in seconds (None = no age limit).
    pub max_age_secs: Option<u64>,
    /// Maximum number of commits to keep per branch (None = no limit).
    pub max_commits: Option<usize>,
    /// Branches to always preserve fully (e.g., "main").
    pub keep_branches: Vec<String>,
    /// Maximum age for log entries in seconds (None = no limit).
    pub max_log_age_secs: Option<u64>,
    /// Maximum number of log entries (None = no limit).
    pub max_log_entries: Option<usize>,
    /// Whether to auto-squash old commits instead of deleting them.
    pub auto_squash: bool,
    /// Number of commits to keep before squashing the rest.
    pub squash_threshold: Option<usize>,
}

impl RetentionPolicy {
    /// Helper to get max_age as Duration.
    pub fn max_age(&self) -> Option<Duration> {
        self.max_age_secs.map(Duration::from_secs)
    }

    /// Helper to get max_log_age as Duration.
    pub fn max_log_age(&self) -> Option<Duration> {
        self.max_log_age_secs.map(Duration::from_secs)
    }
}

impl Default for RetentionPolicy {
    fn default() -> Self {
        Self {
            max_age_secs: None,
            max_commits: None,
            keep_branches: vec!["main".to_string()],
            max_log_age_secs: None,
            max_log_entries: None,
            auto_squash: false,
            squash_threshold: None,
        }
    }
}

/// Result of applying a retention policy.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetentionResult {
    /// Number of commits marked for removal.
    pub commits_expired: usize,
    /// Number of commits retained.
    pub commits_retained: usize,
    /// Number of objects actually deleted.
    pub objects_deleted: usize,
    /// Number of log entries pruned.
    pub logs_pruned: usize,
    /// Total objects before enforcement.
    pub objects_before: usize,
    /// Total objects after enforcement.
    pub objects_after: usize,
}

/// Analyze which commits should be retained under the given policy.
/// Returns the set of object hashes that should be kept.
pub async fn analyze_retention(
    storage: &dyn StorageBackend,
    refs: &RefStore,
    policy: &RetentionPolicy,
) -> Result<(HashSet<String>, usize)> {
    let branches = refs.list_branches();
    let now = Utc::now();
    let mut retained = HashSet::new();
    let mut total_seen = 0usize;

    for (branch_name, tip) in branches {
        let is_protected = policy.keep_branches.contains(branch_name);

        let mut queue = VecDeque::new();
        let mut visited = HashSet::new();
        let mut branch_count = 0usize;
        queue.push_back(tip.clone());

        while let Some(hash) = queue.pop_front() {
            if visited.contains(&hash) {
                continue;
            }
            visited.insert(hash.clone());
            total_seen += 1;

            if let Some(data) = storage.get_object(hash.as_str()).await? {
                if let Ok(commit) = serde_json::from_slice::<Commit>(&data) {
                    let mut keep = is_protected;

                    // Check max_commits
                    if let Some(max) = policy.max_commits {
                        if branch_count < max {
                            keep = true;
                        }
                    } else {
                        keep = true;
                    }

                    // Check max_age
                    if let Some(max_age_secs) = policy.max_age_secs {
                        let age = now.signed_duration_since(commit.timestamp);
                        if age.num_seconds() > max_age_secs as i64 && !is_protected {
                            keep = false;
                        }
                    }

                    // Always keep branch tips
                    if branches.values().any(|v| v == &hash) {
                        keep = true;
                    }

                    if keep {
                        retained.insert(hash.0.clone());
                        // Also retain the tree blob
                        retained.insert(commit.tree_hash.0.clone());
                    }

                    branch_count += 1;
                    for parent in &commit.parent_hashes {
                        queue.push_back(parent.clone());
                    }
                }
            }
        }
    }

    Ok((retained, total_seen))
}

/// Apply a retention policy: analyze, delete expired objects, prune logs.
/// This is the main entry point for retention enforcement.
pub async fn enforce_retention(
    storage: &dyn StorageBackend,
    refs: &RefStore,
    policy: &RetentionPolicy,
) -> Result<RetentionResult> {
    // Phase 1: Analyze which objects to keep
    let (retained, total_seen) = analyze_retention(storage, refs, policy).await?;

    // Phase 2: Delete expired objects
    let all_objects = storage.list_objects().await?;
    let objects_before = all_objects.len();
    let mut objects_deleted = 0;

    for hash in &all_objects {
        if !retained.contains(hash) {
            if storage.delete_object(hash).await? {
                objects_deleted += 1;
            }
        }
    }

    // Phase 3: Prune old log entries
    let mut logs_pruned = 0;

    if let Some(max_age_secs) = policy.max_log_age_secs {
        let cutoff = Utc::now() - chrono::Duration::seconds(max_age_secs as i64);
        let cutoff_str = cutoff.to_rfc3339();
        logs_pruned += storage.delete_logs_before(&cutoff_str).await?;
    }

    if let Some(max_entries) = policy.max_log_entries {
        logs_pruned += storage.prune_logs_excess(max_entries).await?;
    }

    let objects_after = objects_before - objects_deleted;

    Ok(RetentionResult {
        commits_expired: total_seen.saturating_sub(retained.len()),
        commits_retained: retained.len(),
        objects_deleted,
        logs_pruned,
        objects_before,
        objects_after,
    })
}

/// Dry-run: analyze retention without deleting anything.
/// Returns what would be deleted.
pub async fn preview_retention(
    storage: &dyn StorageBackend,
    refs: &RefStore,
    policy: &RetentionPolicy,
) -> Result<RetentionResult> {
    let (retained, total_seen) = analyze_retention(storage, refs, policy).await?;
    let all_objects = storage.list_objects().await?;
    let objects_before = all_objects.len();
    let would_delete = all_objects.iter().filter(|h| !retained.contains(*h)).count();

    Ok(RetentionResult {
        commits_expired: total_seen.saturating_sub(retained.len()),
        commits_retained: retained.len(),
        objects_deleted: would_delete,
        logs_pruned: 0, // Can't preview log pruning without querying
        objects_before,
        objects_after: objects_before - would_delete,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::repo::Repository;
    use crate::state::AgentState;
    use crate::storage::sqlite::SqliteStorage;
    use crate::types::ActionType;
    use serde_json::json;

    #[tokio::test]
    async fn test_default_policy_retains_all() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let mut repo = Repository::init(Box::new(storage)).await.unwrap();
        let s = AgentState::new(json!({"v": 1}), json!({}));
        repo.commit(&s, "c1", ActionType::ToolCall).await.unwrap();

        let policy = RetentionPolicy::default();
        let result = repo.preview_retention(&policy).await.unwrap();
        // Default policy with no limits should retain everything
        assert_eq!(result.objects_deleted, 0);
    }

    #[tokio::test]
    async fn test_enforce_retention_deletes_nothing_on_default() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let mut repo = Repository::init(Box::new(storage)).await.unwrap();
        for i in 0..5 {
            let s = AgentState::new(json!({"v": i}), json!({}));
            repo.commit(&s, &format!("c{}", i), ActionType::ToolCall).await.unwrap();
        }

        let policy = RetentionPolicy::default();
        let result = repo.enforce_retention(&policy).await.unwrap();
        assert_eq!(result.objects_deleted, 0);
        assert!(result.objects_after > 0);
    }

    #[tokio::test]
    async fn test_policy_serialization() {
        let policy = RetentionPolicy {
            max_age_secs: Some(86400),
            max_commits: Some(100),
            keep_branches: vec!["main".to_string(), "production".to_string()],
            max_log_age_secs: Some(604800),
            max_log_entries: Some(10000),
            auto_squash: true,
            squash_threshold: Some(50),
        };
        let json_str = serde_json::to_string(&policy).unwrap();
        let deserialized: RetentionPolicy = serde_json::from_str(&json_str).unwrap();
        assert_eq!(deserialized.max_age_secs, Some(86400));
        assert_eq!(deserialized.max_commits, Some(100));
        assert!(deserialized.auto_squash);
    }

    #[tokio::test]
    async fn test_enforce_retention_prunes_excess_logs() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let mut repo = Repository::init(Box::new(storage)).await.unwrap();

        // Create several commits (each generates an audit log entry)
        for i in 0..10 {
            let s = AgentState::new(json!({"v": i}), json!({}));
            repo.commit(&s, &format!("c{}", i), ActionType::ToolCall).await.unwrap();
        }

        let policy = RetentionPolicy {
            max_log_entries: Some(3),
            ..Default::default()
        };
        let result = repo.enforce_retention(&policy).await.unwrap();
        assert!(result.logs_pruned > 0);
    }
}
