//! Tests for garbage collection and squash operations.

use agit_core::storage::sqlite::SqliteStorage;
use agit_core::types::ActionType;
use agit_core::{AgentState, Repository};
use serde_json::json;

async fn test_repo() -> Repository {
    let storage = SqliteStorage::new(":memory:").await.unwrap();
    Repository::init(Box::new(storage)).await.unwrap()
}

#[tokio::test]
async fn test_gc_empty_repo() {
    let repo = test_repo().await;
    let result = repo.gc(100).await.unwrap();
    assert_eq!(result.objects_before, 0);
    assert_eq!(result.objects_removed, 0);
}

#[tokio::test]
async fn test_gc_with_commits() {
    let mut repo = test_repo().await;

    let s1 = AgentState::new(json!({"v": 1}), json!({}));
    repo.commit(&s1, "first", ActionType::ToolCall).await.unwrap();

    let s2 = AgentState::new(json!({"v": 2}), json!({}));
    repo.commit(&s2, "second", ActionType::ToolCall).await.unwrap();

    let result = repo.gc(100).await.unwrap();
    // Should find reachable objects (commits + blobs)
    assert!(result.objects_before > 0);
    assert_eq!(result.objects_after, result.objects_before);
}

#[tokio::test]
async fn test_gc_preserves_branch_tips() {
    let mut repo = test_repo().await;

    let s1 = AgentState::new(json!({"v": 1}), json!({}));
    repo.commit(&s1, "initial", ActionType::ToolCall).await.unwrap();

    repo.branch("feature", None).await.unwrap();
    repo.checkout("feature").await.unwrap();

    let s2 = AgentState::new(json!({"v": 2}), json!({}));
    repo.commit(&s2, "feature work", ActionType::ToolCall).await.unwrap();

    let result = repo.gc(100).await.unwrap();
    // Both branch tips should be reachable
    assert!(result.objects_before >= 4); // at least 2 commits + 2 blobs
}

#[tokio::test]
async fn test_squash_commits() {
    let mut repo = test_repo().await;

    let s1 = AgentState::new(json!({"v": 1}), json!({}));
    let h1 = repo.commit(&s1, "first", ActionType::ToolCall).await.unwrap();

    let s2 = AgentState::new(json!({"v": 2}), json!({}));
    let _h2 = repo.commit(&s2, "second", ActionType::ToolCall).await.unwrap();

    let s3 = AgentState::new(json!({"v": 3}), json!({}));
    let h3 = repo.commit(&s3, "third", ActionType::ToolCall).await.unwrap();

    // Squash h1..h3 (all 3 commits)
    let result = repo.squash("main", h1.as_str(), h3.as_str()).await.unwrap();

    assert_eq!(result.commits_squashed, 3);
    assert!(result.message.contains("squash 3 commits"));

    // The squashed commit should have the final state
    let state = repo.get_state(result.new_hash.as_str()).await.unwrap();
    assert_eq!(state.memory, json!({"v": 3}));
}

#[tokio::test]
async fn test_squash_preserves_final_state() {
    let mut repo = test_repo().await;

    let s1 = AgentState::new(json!({"data": "initial"}), json!({"count": 0}));
    let h1 = repo.commit(&s1, "start", ActionType::Checkpoint).await.unwrap();

    let s2 = AgentState::new(json!({"data": "middle"}), json!({"count": 1}));
    let _h2 = repo.commit(&s2, "progress", ActionType::ToolCall).await.unwrap();

    let s3 = AgentState::new(json!({"data": "final", "extra": true}), json!({"count": 2}));
    let h3 = repo.commit(&s3, "done", ActionType::ToolCall).await.unwrap();

    let result = repo.squash("main", h1.as_str(), h3.as_str()).await.unwrap();

    let state = repo.get_state(result.new_hash.as_str()).await.unwrap();
    assert_eq!(state.memory, json!({"data": "final", "extra": true}));
    assert_eq!(state.world_state, json!({"count": 2}));
}
