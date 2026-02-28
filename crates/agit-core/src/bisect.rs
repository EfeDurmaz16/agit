//! Binary search through commit history to find where agent behavior diverged.
//! Analogous to `git bisect` but operates on JSON state predicates.

use std::collections::{HashSet, VecDeque};

use serde::{Deserialize, Serialize};

use crate::error::{AgitError, Result};
use crate::objects::Commit;
use crate::storage::StorageBackend;
use crate::types::Hash;

/// The result of a completed bisect session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BisectResult {
    /// The first commit identified as "bad".
    pub first_bad: Hash,
    /// Total number of mark_good/mark_bad steps taken.
    pub total_steps: usize,
    /// Total number of candidate commits that were searched.
    pub commits_searched: usize,
}

/// Current state of a bisect session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum BisectState {
    /// Session has not been started.
    NotStarted,
    /// Session is in progress, narrowing down the bad commit.
    InProgress {
        /// Known-good commit hash.
        good: Hash,
        /// Known-bad commit hash.
        bad: Hash,
        /// Candidate commits between good and bad, sorted oldest-first.
        candidates: Vec<Hash>,
        /// Index into `candidates` pointing at the current commit under test.
        current_idx: usize,
    },
    /// Session is complete with a definitive result.
    Completed {
        result: BisectResult,
    },
}

/// A bisect session that performs binary search over a commit DAG.
///
/// Usage:
/// 1. `BisectSession::start(storage, good_hash, bad_hash).await`
/// 2. Inspect `session.current_commit()` and test that state.
/// 3. Call `session.mark_good()` or `session.mark_bad()` based on the test.
/// 4. Repeat until `session.is_complete()`.
/// 5. Retrieve the culprit via `session.result()`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BisectSession {
    state: BisectState,
    steps_taken: usize,
    commits_searched: usize,
}

impl BisectSession {
    /// Start a new bisect session between a known-good and known-bad commit.
    ///
    /// Collects all commits reachable from `bad_hash` back to `good_hash` via
    /// BFS and sorts them by timestamp (oldest first). The session immediately
    /// positions itself at the midpoint.
    pub async fn start(
        storage: &dyn StorageBackend,
        good_hash: Hash,
        bad_hash: Hash,
    ) -> Result<BisectSession> {
        if good_hash == bad_hash {
            return Err(AgitError::InvalidArgument(
                "good and bad commits must be different".to_string(),
            ));
        }

        let candidates =
            collect_commits_between(storage, &good_hash, &bad_hash).await?;

        if candidates.is_empty() {
            // No intermediate commits — bad_hash itself is the first bad commit.
            return Ok(BisectSession {
                state: BisectState::Completed {
                    result: BisectResult {
                        first_bad: bad_hash,
                        total_steps: 0,
                        commits_searched: 0,
                    },
                },
                steps_taken: 0,
                commits_searched: 0,
            });
        }

        let current_idx = candidates.len() / 2;
        let commits_searched = candidates.len();

        Ok(BisectSession {
            state: BisectState::InProgress {
                good: good_hash,
                bad: bad_hash,
                candidates,
                current_idx,
            },
            steps_taken: 0,
            commits_searched,
        })
    }

    /// Returns the hash of the commit currently under test, if the session is in progress.
    pub fn current_commit(&self) -> Option<&Hash> {
        match &self.state {
            BisectState::InProgress {
                candidates,
                current_idx,
                ..
            } => candidates.get(*current_idx),
            _ => None,
        }
    }

    /// Mark the current commit as good (the regression has not yet appeared).
    /// Narrows the search to the upper (newer) half of the candidate list.
    pub fn mark_good(&mut self) {
        self.steps_taken += 1;

        let new_state = match &self.state {
            BisectState::InProgress {
                good: _,
                bad,
                candidates,
                current_idx,
            } => {
                let idx = *current_idx;
                let bad = bad.clone();

                // Everything at or before idx is now known-good.
                // Narrow candidates to those strictly after idx.
                let remaining: Vec<Hash> = candidates[idx + 1..].to_vec();

                if remaining.is_empty() {
                    // The commit just after idx (i.e. bad itself) is the first bad.
                    BisectState::Completed {
                        result: BisectResult {
                            first_bad: bad,
                            total_steps: self.steps_taken,
                            commits_searched: self.commits_searched,
                        },
                    }
                } else {
                    let new_idx = remaining.len() / 2;
                    let new_good = candidates[idx].clone();
                    BisectState::InProgress {
                        good: new_good,
                        bad,
                        candidates: remaining,
                        current_idx: new_idx,
                    }
                }
            }
            // No-op if not in progress.
            other => other.clone(),
        };

        self.state = new_state;
    }

    /// Mark the current commit as bad (the regression is present here or earlier).
    /// Narrows the search to the lower (older) half of the candidate list.
    pub fn mark_bad(&mut self) {
        self.steps_taken += 1;

        let new_state = match &self.state {
            BisectState::InProgress {
                good,
                bad: _,
                candidates,
                current_idx,
            } => {
                let idx = *current_idx;
                let good = good.clone();

                // Everything from idx onward is now bad.
                // Narrow candidates to those strictly before idx.
                let remaining: Vec<Hash> = candidates[..idx].to_vec();

                if remaining.is_empty() {
                    // Current commit is the first bad.
                    BisectState::Completed {
                        result: BisectResult {
                            first_bad: candidates[idx].clone(),
                            total_steps: self.steps_taken,
                            commits_searched: self.commits_searched,
                        },
                    }
                } else {
                    let new_idx = remaining.len() / 2;
                    let new_bad = candidates[idx].clone();
                    BisectState::InProgress {
                        good,
                        bad: new_bad,
                        candidates: remaining,
                        current_idx: new_idx,
                    }
                }
            }
            other => other.clone(),
        };

        self.state = new_state;
    }

    /// Returns true when bisect has found the first bad commit.
    pub fn is_complete(&self) -> bool {
        matches!(self.state, BisectState::Completed { .. })
    }

    /// Returns the bisect result if the session is complete.
    pub fn result(&self) -> Option<&BisectResult> {
        match &self.state {
            BisectState::Completed { result } => Some(result),
            _ => None,
        }
    }

    /// Returns the number of candidate commits still to be tested.
    pub fn remaining(&self) -> usize {
        match &self.state {
            BisectState::InProgress { candidates, .. } => candidates.len(),
            _ => 0,
        }
    }

    /// Returns the number of mark_good / mark_bad steps taken so far.
    pub fn steps_taken(&self) -> usize {
        self.steps_taken
    }

    /// Expose the inner state for inspection / serialization.
    pub fn state(&self) -> &BisectState {
        &self.state
    }
}

/// Collect all commit hashes that lie on paths from `bad_hash` back to
/// `good_hash` (exclusive of both endpoints), sorted by timestamp oldest-first.
///
/// Uses BFS starting at `bad_hash`, following parent links, stopping when
/// `good_hash` is reached or there are no more ancestors.
pub async fn collect_commits_between(
    storage: &dyn StorageBackend,
    good_hash: &Hash,
    bad_hash: &Hash,
) -> Result<Vec<Hash>> {
    // BFS from bad toward good.
    let mut visited: HashSet<String> = HashSet::new();
    let mut queue: VecDeque<String> = VecDeque::new();
    // Store (hash, commit) pairs so we can sort by timestamp.
    let mut collected: Vec<(Hash, chrono::DateTime<chrono::Utc>)> = Vec::new();

    queue.push_back(bad_hash.0.clone());

    while let Some(current_hash) = queue.pop_front() {
        if visited.contains(&current_hash) {
            continue;
        }
        visited.insert(current_hash.clone());

        // Stop following this path once we reach the good commit.
        if current_hash == good_hash.0 {
            continue;
        }

        // Load the commit object.
        let data = storage
            .get_object(&current_hash)
            .await?
            .ok_or_else(|| AgitError::ObjectNotFound {
                hash: current_hash.clone(),
            })?;

        let commit: Commit = serde_json::from_slice(&data)
            .map_err(|e| AgitError::Serialization(e.to_string()))?;

        // Collect this commit if it is not the bad_hash endpoint itself
        // and not the good_hash endpoint.
        if current_hash != bad_hash.0 && current_hash != good_hash.0 {
            collected.push((Hash(current_hash.clone()), commit.timestamp));
        }

        // Enqueue parents.
        for parent in &commit.parent_hashes {
            if !visited.contains(&parent.0) {
                queue.push_back(parent.0.clone());
            }
        }
    }

    // Sort by timestamp ascending (oldest first).
    collected.sort_by_key(|(_, ts)| *ts);

    Ok(collected.into_iter().map(|(h, _)| h).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::collections::HashMap;
    use std::sync::Arc;

    use async_trait::async_trait;
    use chrono::{TimeZone, Utc};
    use serde_json::json;
    use tokio::sync::Mutex;

    use crate::objects::Commit;
    use crate::storage::{LogEntry, LogFilter, StorageBackend};
    use crate::types::{ActionType, Hash, ObjectType};

    // -----------------------------------------------------------------------
    // Minimal in-memory storage backend for tests
    // -----------------------------------------------------------------------

    #[derive(Default, Clone)]
    struct MemStorage {
        objects: Arc<Mutex<HashMap<String, Vec<u8>>>>,
        refs: Arc<Mutex<HashMap<String, String>>>,
    }

    #[async_trait]
    impl StorageBackend for MemStorage {
        async fn initialize(&self) -> Result<()> {
            Ok(())
        }

        async fn put_object(
            &self,
            hash: &str,
            _obj_type: ObjectType,
            data: &[u8],
        ) -> Result<()> {
            self.objects
                .lock()
                .await
                .insert(hash.to_string(), data.to_vec());
            Ok(())
        }

        async fn get_object(&self, hash: &str) -> Result<Option<Vec<u8>>> {
            Ok(self.objects.lock().await.get(hash).cloned())
        }

        async fn has_object(&self, hash: &str) -> Result<bool> {
            Ok(self.objects.lock().await.contains_key(hash))
        }

        async fn set_ref(&self, name: &str, hash: &str) -> Result<()> {
            self.refs
                .lock()
                .await
                .insert(name.to_string(), hash.to_string());
            Ok(())
        }

        async fn get_ref(&self, name: &str) -> Result<Option<String>> {
            Ok(self.refs.lock().await.get(name).cloned())
        }

        async fn list_refs(&self) -> Result<HashMap<String, String>> {
            Ok(self.refs.lock().await.clone())
        }

        async fn delete_ref(&self, name: &str) -> Result<bool> {
            Ok(self.refs.lock().await.remove(name).is_some())
        }

        async fn append_log(&self, _entry: &LogEntry) -> Result<()> {
            Ok(())
        }

        async fn query_logs(&self, _filter: &LogFilter) -> Result<Vec<LogEntry>> {
            Ok(vec![])
        }

        async fn delete_object(&self, hash: &str) -> Result<bool> {
            Ok(self.objects.lock().await.remove(hash).is_some())
        }

        async fn list_objects(&self) -> Result<Vec<String>> {
            Ok(self.objects.lock().await.keys().cloned().collect())
        }

        async fn delete_logs_before(&self, _before_timestamp: &str) -> Result<usize> {
            Ok(0)
        }

        async fn prune_logs_excess(&self, _keep: usize) -> Result<usize> {
            Ok(0)
        }
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------

    /// Store a commit in the MemStorage and return its hash.
    async fn store_commit(storage: &MemStorage, commit: &Commit) -> Hash {
        let hash = commit.hash();
        let data = serde_json::to_vec(commit).unwrap();
        storage
            .put_object(hash.as_str(), ObjectType::Commit, &data)
            .await
            .unwrap();
        hash
    }

    /// Build a linear chain of N+2 commits (root → c0 → c1 → … → c_{N-1} → tip)
    /// and return (root_hash, tip_hash, intermediate_hashes).
    async fn build_chain(
        storage: &MemStorage,
        n: usize,
    ) -> (Hash, Hash, Vec<Hash>) {
        // Root commit (good)
        let root = Commit {
            tree_hash: Hash::from("blob-root"),
            parent_hashes: vec![],
            message: "root".to_string(),
            author: "agent".to_string(),
            timestamp: Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
            action_type: ActionType::Checkpoint,
            metadata: serde_json::Map::new(),
        };
        let root_hash = store_commit(storage, &root).await;

        let mut intermediates = Vec::new();
        let mut parent = root_hash.clone();

        for i in 0..n {
            let c = Commit {
                tree_hash: Hash(format!("blob-{}", i)),
                parent_hashes: vec![parent.clone()],
                message: format!("step {}", i),
                author: "agent".to_string(),
                timestamp: Utc
                    .with_ymd_and_hms(2024, 1, 1, 0, 0, (i + 1) as u32)
                    .unwrap(),
                action_type: ActionType::ToolCall,
                metadata: serde_json::Map::new(),
            };
            let h = store_commit(storage, &c).await;
            intermediates.push(h.clone());
            parent = h;
        }

        // Tip commit (bad)
        let tip = Commit {
            tree_hash: Hash::from("blob-tip"),
            parent_hashes: vec![parent.clone()],
            message: "tip (bad)".to_string(),
            author: "agent".to_string(),
            timestamp: Utc
                .with_ymd_and_hms(2024, 1, 1, 0, 0, (n + 1) as u32)
                .unwrap(),
            action_type: ActionType::ToolCall,
            metadata: serde_json::Map::new(),
        };
        let tip_hash = store_commit(storage, &tip).await;

        (root_hash, tip_hash, intermediates)
    }

    // -----------------------------------------------------------------------
    // Tests
    // -----------------------------------------------------------------------

    /// With 5 intermediate commits the binary search should converge and find
    /// one of the middle commits as the first bad when we always answer "bad".
    #[tokio::test]
    async fn test_bisect_finds_middle() {
        let storage = MemStorage::default();
        let (good, bad, intermediates) = build_chain(&storage, 5).await;

        let mut session = BisectSession::start(&storage, good, bad)
            .await
            .unwrap();

        assert!(!session.is_complete());
        assert!(session.current_commit().is_some());

        // Drive the session: always mark current as bad (regression everywhere).
        let mut iterations = 0;
        while !session.is_complete() {
            session.mark_bad();
            iterations += 1;
            assert!(iterations < 20, "bisect did not converge");
        }

        let result = session.result().unwrap();
        // The first bad must be one of our intermediate commits (or the tip
        // boundary) — crucially it must be a known hash.
        let all_hashes: Vec<&Hash> = intermediates.iter().collect();
        let found = all_hashes
            .iter()
            .any(|h| h.0 == result.first_bad.0);
        assert!(
            found,
            "first_bad {:?} was not among the intermediate commits",
            result.first_bad
        );
        assert!(result.total_steps > 0);
    }

    /// When there are no intermediate commits (adjacent good/bad) the session
    /// should complete immediately with bad_hash as the first bad commit.
    #[tokio::test]
    async fn test_bisect_single_commit() {
        let storage = MemStorage::default();

        let good = Commit {
            tree_hash: Hash::from("blob-g"),
            parent_hashes: vec![],
            message: "good".to_string(),
            author: "agent".to_string(),
            timestamp: Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
            action_type: ActionType::Checkpoint,
            metadata: serde_json::Map::new(),
        };
        let good_hash = store_commit(&storage, &good).await;

        let bad = Commit {
            tree_hash: Hash::from("blob-b"),
            parent_hashes: vec![good_hash.clone()],
            message: "bad".to_string(),
            author: "agent".to_string(),
            timestamp: Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 1).unwrap(),
            action_type: ActionType::ToolCall,
            metadata: serde_json::Map::new(),
        };
        let bad_hash = store_commit(&storage, &bad).await;

        let session = BisectSession::start(&storage, good_hash, bad_hash.clone())
            .await
            .unwrap();

        // Should complete immediately — no intermediates.
        assert!(session.is_complete());
        let result = session.result().unwrap();
        assert_eq!(result.first_bad.0, bad_hash.0);
        assert_eq!(result.total_steps, 0);
    }

    /// Full session: build a chain, simulate mixed good/bad answers and verify
    /// the session eventually reaches Completed state with a valid result.
    #[tokio::test]
    async fn test_bisect_session_complete() {
        let storage = MemStorage::default();
        // 7 intermediate commits gives a good binary search depth.
        let (good, bad, intermediates) = build_chain(&storage, 7).await;

        let mut session = BisectSession::start(&storage, good, bad.clone())
            .await
            .unwrap();

        assert_eq!(session.remaining(), intermediates.len());
        assert_eq!(session.steps_taken(), 0);

        // Simulate: commits before index 4 are good, from index 4 onward are bad.
        // This means intermediates[4] should be the first bad commit.
        let bad_from = &intermediates[4];

        let mut iters = 0;
        while !session.is_complete() {
            let current = session.current_commit().unwrap().clone();
            // Determine whether this commit is in the "bad" region.
            let pos = intermediates.iter().position(|h| h.0 == current.0);
            match pos {
                Some(p) if p >= 4 => session.mark_bad(),
                _ => session.mark_good(),
            }
            iters += 1;
            assert!(iters < 20, "bisect did not converge");
        }

        let result = session.result().unwrap();
        assert_eq!(
            result.first_bad.0, bad_from.0,
            "expected first_bad to be intermediates[4]"
        );
        assert!(session.is_complete());
        assert!(result.total_steps > 0);
        assert!(result.commits_searched > 0);
        // Remaining should be 0 once complete.
        assert_eq!(session.remaining(), 0);
        // steps_taken on the session should match result.
        assert_eq!(session.steps_taken(), result.total_steps);

        // Unused import lint suppression: confirm json! compiles.
        let _ = json!({"check": true});
    }
}
