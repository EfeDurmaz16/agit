//! Garbage collection and history squashing for agit repositories.
//!
//! Provides two strategies:
//! - `gc`: Mark-and-sweep to remove unreachable objects
//! - `squash`: Collapse a range of commits into a single commit

use std::collections::{HashSet, VecDeque};

use chrono::Utc;

use crate::error::{AgitError, Result};
use crate::objects::Commit;
use crate::refs::RefStore;
use crate::storage::StorageBackend;
use crate::types::{ActionType, Hash, ObjectType};

/// Result of a garbage collection run.
#[derive(Debug, Clone)]
pub struct GcResult {
    /// Number of objects before GC.
    pub objects_before: usize,
    /// Number of objects removed.
    pub objects_removed: usize,
    /// Number of objects remaining.
    pub objects_after: usize,
}

/// Result of a squash operation.
#[derive(Debug, Clone)]
pub struct SquashResult {
    /// The new squashed commit hash.
    pub new_hash: Hash,
    /// Number of commits squashed.
    pub commits_squashed: usize,
    /// The message of the squashed commit.
    pub message: String,
}

/// Collect all reachable object hashes starting from a set of root hashes.
/// This traverses commits and their tree (blob) hashes.
pub async fn collect_reachable(
    storage: &dyn StorageBackend,
    roots: &[Hash],
) -> Result<HashSet<String>> {
    let mut reachable = HashSet::new();
    let mut queue: VecDeque<String> = roots.iter().map(|h| h.0.clone()).collect();

    while let Some(hash) = queue.pop_front() {
        if reachable.contains(&hash) {
            continue;
        }
        reachable.insert(hash.clone());

        // Try to load as commit
        if let Some(data) = storage.get_object(&hash).await? {
            if let Ok(commit) = serde_json::from_slice::<Commit>(&data) {
                // Add tree hash (blob)
                if !reachable.contains(&commit.tree_hash.0) {
                    queue.push_back(commit.tree_hash.0.clone());
                }
                // Add parent commits
                for parent in &commit.parent_hashes {
                    if !reachable.contains(&parent.0) {
                        queue.push_back(parent.0.clone());
                    }
                }
            }
            // If it's a blob, it's already marked reachable
        }
    }

    Ok(reachable)
}

/// Run garbage collection: remove objects not reachable from any branch tip.
///
/// # Arguments
/// * `storage` - The storage backend
/// * `refs` - The ref store with all branch tips
/// * `keep_last_n` - Always keep at least this many commits on each branch (0 = only keep reachable)
pub async fn gc(
    storage: &dyn StorageBackend,
    refs: &RefStore,
    keep_last_n: usize,
) -> Result<GcResult> {
    // Collect all branch tips as roots
    let branches = refs.list_branches();
    let roots: Vec<Hash> = branches.values().cloned().collect();

    if roots.is_empty() {
        return Ok(GcResult {
            objects_before: 0,
            objects_removed: 0,
            objects_after: 0,
        });
    }

    // Find all reachable objects
    let reachable = collect_reachable(storage, &roots).await?;

    // Additionally mark the last N commits per branch as reachable
    let mut reachable = reachable;
    if keep_last_n > 0 {
        for root in &roots {
            let mut queue: VecDeque<String> = VecDeque::new();
            queue.push_back(root.0.clone());
            let mut count = 0;

            while let Some(hash) = queue.pop_front() {
                if count >= keep_last_n {
                    break;
                }
                reachable.insert(hash.clone());
                count += 1;

                if let Some(data) = storage.get_object(&hash).await? {
                    if let Ok(commit) = serde_json::from_slice::<Commit>(&data) {
                        // Mark the tree blob as reachable too
                        reachable.insert(commit.tree_hash.0.clone());
                        for parent in &commit.parent_hashes {
                            if !reachable.contains(&parent.0) {
                                queue.push_back(parent.0.clone());
                            }
                        }
                    }
                }
            }
        }
    }

    // List all objects and delete unreachable ones
    let all_objects = storage.list_objects().await?;
    let objects_before = all_objects.len();
    let mut objects_removed = 0;

    for hash in &all_objects {
        if !reachable.contains(hash) {
            if storage.delete_object(hash).await? {
                objects_removed += 1;
            }
        }
    }

    Ok(GcResult {
        objects_before,
        objects_removed,
        objects_after: objects_before - objects_removed,
    })
}

/// Squash a range of commits on a branch into a single commit.
///
/// The squashed commit preserves the final state and has the parent
/// of the first commit in the range as its parent.
///
/// # Arguments
/// * `storage` - The storage backend
/// * `refs` - The ref store
/// * `agent_id` - Agent ID for the new commit
/// * `branch` - Branch name to squash on
/// * `from_hash` - Start of range (oldest commit, inclusive)
/// * `to_hash` - End of range (newest commit, inclusive -- its state is preserved)
pub async fn squash(
    storage: &dyn StorageBackend,
    refs: &mut RefStore,
    agent_id: &str,
    branch: &str,
    from_hash: &str,
    to_hash: &str,
) -> Result<SquashResult> {
    // Load the range of commits to count them
    let mut commits_in_range = Vec::new();
    let mut current = to_hash.to_string();

    loop {
        let data = storage
            .get_object(&current)
            .await?
            .ok_or_else(|| AgitError::ObjectNotFound {
                hash: current.clone(),
            })?;
        let commit: Commit = serde_json::from_slice(&data)?;
        commits_in_range.push(commit.clone());

        if current == from_hash {
            break;
        }

        match commit.parent_hashes.first() {
            Some(parent) => current = parent.0.clone(),
            None => break,
        }
    }

    if commits_in_range.is_empty() {
        return Err(AgitError::InvalidOperation(
            "No commits found in squash range".to_string(),
        ));
    }

    // Get the final state (from to_hash)
    let final_commit_data = storage
        .get_object(to_hash)
        .await?
        .ok_or_else(|| AgitError::ObjectNotFound {
            hash: to_hash.to_string(),
        })?;
    let final_commit: Commit = serde_json::from_slice(&final_commit_data)?;

    // Get the state blob
    let state_data = storage
        .get_object(final_commit.tree_hash.as_str())
        .await?
        .ok_or_else(|| AgitError::ObjectNotFound {
            hash: final_commit.tree_hash.to_string(),
        })?;

    // Determine parent: the parent of from_hash (the commit before the range)
    let from_data = storage
        .get_object(from_hash)
        .await?
        .ok_or_else(|| AgitError::ObjectNotFound {
            hash: from_hash.to_string(),
        })?;
    let from_commit: Commit = serde_json::from_slice(&from_data)?;
    let parent_hashes = from_commit.parent_hashes.clone();

    // Collect messages
    let messages: Vec<String> = commits_in_range
        .iter()
        .rev()
        .map(|c| c.message.clone())
        .collect();
    let squash_message = format!(
        "squash {} commits: {}",
        commits_in_range.len(),
        messages.join("; ")
    );

    // Create new squashed commit
    let new_commit = Commit {
        tree_hash: final_commit.tree_hash.clone(),
        parent_hashes,
        message: squash_message.clone(),
        author: agent_id.to_string(),
        timestamp: Utc::now(),
        action_type: ActionType::Checkpoint,
        metadata: serde_json::Map::new(),
    };

    let new_hash = new_commit.hash();
    let commit_data = serde_json::to_vec(&new_commit)?;

    // Store the squashed commit
    storage
        .put_object(new_hash.as_str(), ObjectType::Commit, &commit_data)
        .await?;

    // Ensure the state blob exists (it should already)
    storage
        .put_object(
            final_commit.tree_hash.as_str(),
            ObjectType::Blob,
            &state_data,
        )
        .await?;

    // Update branch ref to point to new squashed commit
    refs.update_branch(branch, new_hash.clone())?;
    storage.set_ref(branch, new_hash.as_str()).await?;

    Ok(SquashResult {
        new_hash,
        commits_squashed: commits_in_range.len(),
        message: squash_message,
    })
}
