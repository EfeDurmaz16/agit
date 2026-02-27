//! Retention policy support for automatic cleanup of old commits and logs.

use std::collections::{HashSet, VecDeque};
use std::time::Duration;

use chrono::Utc;

use crate::error::Result;
use crate::objects::Commit;
use crate::refs::RefStore;
use crate::storage::StorageBackend;

/// Configurable retention policy for repository data.
#[derive(Debug, Clone)]
pub struct RetentionPolicy {
    /// Maximum age for commits (None = no age limit).
    pub max_age: Option<Duration>,
    /// Maximum number of commits to keep per branch (None = no limit).
    pub max_commits: Option<usize>,
    /// Branches to always preserve fully (e.g., "main").
    pub keep_branches: Vec<String>,
    /// Maximum age for log entries (None = no limit).
    pub max_log_age: Option<Duration>,
    /// Maximum number of log entries (None = no limit).
    pub max_log_entries: Option<usize>,
}

impl Default for RetentionPolicy {
    fn default() -> Self {
        Self {
            max_age: None,
            max_commits: None,
            keep_branches: vec!["main".to_string()],
            max_log_age: None,
            max_log_entries: None,
        }
    }
}

/// Result of applying a retention policy.
#[derive(Debug, Clone)]
pub struct RetentionResult {
    /// Number of commits marked for removal.
    pub commits_expired: usize,
    /// Number of commits retained.
    pub commits_retained: usize,
}

/// Apply a retention policy, returning hashes that should be considered
/// unreachable (and thus eligible for GC).
pub async fn apply_retention(
    storage: &dyn StorageBackend,
    refs: &RefStore,
    policy: &RetentionPolicy,
) -> Result<RetentionResult> {
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
                    if let Some(max_age) = policy.max_age {
                        let age = now.signed_duration_since(commit.timestamp);
                        if age.num_seconds() > max_age.as_secs() as i64 && !is_protected {
                            keep = false;
                        }
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

    Ok(RetentionResult {
        commits_expired: total_seen.saturating_sub(retained.len()),
        commits_retained: retained.len(),
    })
}
