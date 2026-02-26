//! Postgres integration tests.
//!
//! These tests require a running Postgres instance.
//! Run: `docker compose -f docker/docker-compose.test.yml up -d`
//! Then: `cargo test --features postgres -- postgres`

#![cfg(feature = "postgres")]

use agit_core::storage::PostgresStorage;
use agit_core::types::{ActionType, ObjectType};
use agit_core::{AgentState, Repository};
use agit_core::storage::{LogEntry, LogFilter, StorageBackend};
use serde_json::json;

const TEST_DB_URL: &str = "postgresql://agit_test:agit_test_password@localhost:5433/agit_test";

async fn setup_storage(schema: &str) -> PostgresStorage {
    let storage = PostgresStorage::new(TEST_DB_URL, schema)
        .await
        .expect("Failed to connect to test Postgres");
    storage.initialize().await.expect("Failed to initialize");
    storage
}

async fn setup_repo(schema: &str) -> Repository {
    let storage = setup_storage(schema).await;
    Repository::init(Box::new(storage)).await.expect("Failed to init repo")
}

#[tokio::test]
async fn test_postgres_put_and_get_object() {
    let storage = setup_storage("test_objects").await;

    let data = b"hello world";
    let hash = "abc123";
    storage
        .put_object(hash, ObjectType::Blob, data)
        .await
        .unwrap();

    let retrieved = storage.get_object(hash).await.unwrap();
    assert_eq!(retrieved, Some(data.to_vec()));
}

#[tokio::test]
async fn test_postgres_has_object() {
    let storage = setup_storage("test_has_obj").await;

    assert!(!storage.has_object("nonexistent").await.unwrap());

    storage
        .put_object("exists", ObjectType::Blob, b"data")
        .await
        .unwrap();
    assert!(storage.has_object("exists").await.unwrap());
}

#[tokio::test]
async fn test_postgres_refs() {
    let storage = setup_storage("test_refs").await;

    storage.set_ref("main", "hash1").await.unwrap();
    storage.set_ref("feature", "hash2").await.unwrap();

    assert_eq!(storage.get_ref("main").await.unwrap(), Some("hash1".to_string()));
    assert_eq!(storage.get_ref("feature").await.unwrap(), Some("hash2".to_string()));

    let refs = storage.list_refs().await.unwrap();
    assert_eq!(refs.len(), 2);

    storage.delete_ref("feature").await.unwrap();
    assert_eq!(storage.get_ref("feature").await.unwrap(), None);
}

#[tokio::test]
async fn test_postgres_audit_log() {
    let storage = setup_storage("test_audit").await;

    let entry = LogEntry {
        id: "log-1".to_string(),
        timestamp: "2025-01-01T00:00:00Z".to_string(),
        agent_id: "agent-1".to_string(),
        action: "commit".to_string(),
        message: "test commit".to_string(),
        commit_hash: Some("abc123".to_string()),
        details: None,
        level: "info".to_string(),
    };
    storage.append_log(&entry).await.unwrap();

    let filter = LogFilter {
        agent_id: Some("agent-1".to_string()),
        limit: Some(10),
        ..Default::default()
    };
    let logs = storage.query_logs(&filter).await.unwrap();
    assert!(!logs.is_empty());
    assert_eq!(logs[0].message, "test commit");
}

#[tokio::test]
async fn test_postgres_full_repository_workflow() {
    let mut repo = setup_repo("test_full_workflow").await;

    // Commit
    let s1 = AgentState::new(json!({"step": 1}), json!({}));
    let h1 = repo.commit(&s1, "first", ActionType::ToolCall).await.unwrap();
    assert_eq!(h1.0.len(), 64);

    // Second commit
    let s2 = AgentState::new(json!({"step": 2}), json!({}));
    let h2 = repo.commit(&s2, "second", ActionType::ToolCall).await.unwrap();

    // Log
    let commits = repo.log(None, 10).await.unwrap();
    assert_eq!(commits.len(), 2);

    // Diff
    let diff = repo.diff(h1.as_str(), h2.as_str()).await.unwrap();
    assert!(!diff.entries.is_empty());

    // Branch
    repo.branch("feature", None).await.unwrap();
    let branches = repo.list_branches();
    assert!(branches.contains_key("feature"));

    // Checkout
    let state = repo.checkout("feature").await.unwrap();
    assert_eq!(state.memory, json!({"step": 2}));

    // Revert
    let reverted = repo.revert(h1.as_str()).await.unwrap();
    assert_eq!(reverted.memory, json!({"step": 1}));
}

#[tokio::test]
async fn test_postgres_multi_tenant_isolation() {
    let mut repo1 = setup_repo("tenant_a").await;
    let mut repo2 = setup_repo("tenant_b").await;

    let s1 = AgentState::new(json!({"tenant": "a"}), json!({}));
    repo1.commit(&s1, "tenant a commit", ActionType::ToolCall).await.unwrap();

    let s2 = AgentState::new(json!({"tenant": "b"}), json!({}));
    repo2.commit(&s2, "tenant b commit", ActionType::ToolCall).await.unwrap();

    let commits1 = repo1.log(None, 10).await.unwrap();
    let commits2 = repo2.log(None, 10).await.unwrap();

    assert_eq!(commits1.len(), 1);
    assert_eq!(commits2.len(), 1);
    assert_eq!(commits1[0].message, "tenant a commit");
    assert_eq!(commits2[0].message, "tenant b commit");
}
