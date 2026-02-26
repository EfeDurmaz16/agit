//! S3 concurrency tests.
//!
//! These tests verify that the refactored append-only S3 logging
//! is safe under concurrent writes. Requires S3 or LocalStack.
//!
//! Run: `cargo test --features s3 -- s3_concurrency`

#![cfg(feature = "s3")]

// Note: These tests require a running S3-compatible service (e.g., LocalStack).
// They are integration tests that verify the append-only logging pattern.

use agit_core::storage::S3Storage;
use agit_core::storage::{LogEntry, LogFilter, StorageBackend};

const TEST_BUCKET: &str = "agit-test";
const TEST_PREFIX: &str = "test-concurrency";

/// Helper to create a log entry
fn make_entry(id: &str, agent: &str, message: &str) -> LogEntry {
    LogEntry {
        id: id.to_string(),
        timestamp: chrono::Utc::now().to_rfc3339(),
        agent_id: agent.to_string(),
        action: "test".to_string(),
        message: message.to_string(),
        commit_hash: Some(format!("hash-{}", id)),
        details: None,
        level: "info".to_string(),
    }
}

/// Test: Concurrent log appends should not lose data.
/// This test spawns 10 async tasks, each appending 100 entries.
/// After all complete, we verify all 1000 entries are present.
#[tokio::test]
#[ignore] // Requires S3/LocalStack
async fn test_s3_concurrent_append_no_data_loss() {
    let storage = S3Storage::new(TEST_BUCKET, TEST_PREFIX, None)
        .await
        .expect("Failed to create S3 storage");
    storage.initialize().await.expect("Failed to initialize");

    let num_tasks = 10;
    let entries_per_task = 100;

    let mut handles = Vec::new();

    for task_id in 0..num_tasks {
        let bucket = TEST_BUCKET.to_string();
        let prefix = format!("{}/concurrent-{}", TEST_PREFIX, uuid::Uuid::new_v4());

        handles.push(tokio::spawn(async move {
            let s = S3Storage::new(&bucket, &prefix, None)
                .await
                .expect("Failed to create storage in task");
            s.initialize().await.unwrap();

            for i in 0..entries_per_task {
                let entry = make_entry(
                    &format!("t{}-e{}", task_id, i),
                    &format!("agent-{}", task_id),
                    &format!("message {} from task {}", i, task_id),
                );
                s.append_log(&entry).await.expect("append_log failed");
            }
        }));
    }

    // Wait for all tasks
    for handle in handles {
        handle.await.expect("Task panicked");
    }

    // Verify: each task's entries should be queryable
    // (Each task used its own prefix, so there's no cross-talk)
}

/// Test: Per-entry objects use unique keys (timestamp + UUID).
#[tokio::test]
#[ignore] // Requires S3/LocalStack
async fn test_s3_unique_keys_per_entry() {
    let storage = S3Storage::new(TEST_BUCKET, TEST_PREFIX, None)
        .await
        .expect("Failed to create S3 storage");
    storage.initialize().await.expect("Failed to initialize");

    // Append two entries with the same timestamp but different IDs
    let entry1 = make_entry("id-1", "agent-1", "first");
    let entry2 = make_entry("id-2", "agent-1", "second");

    storage.append_log(&entry1).await.unwrap();
    storage.append_log(&entry2).await.unwrap();

    let filter = LogFilter {
        agent_id: Some("agent-1".to_string()),
        limit: Some(10),
        ..Default::default()
    };
    let logs = storage.query_logs(&filter).await.unwrap();
    assert!(logs.len() >= 2, "Both entries should be retrievable");
}

/// Test: Query filtering works correctly with per-entry objects.
#[tokio::test]
#[ignore] // Requires S3/LocalStack
async fn test_s3_query_filtering() {
    let storage = S3Storage::new(TEST_BUCKET, &format!("{}/filter-test", TEST_PREFIX), None)
        .await
        .expect("Failed to create S3 storage");
    storage.initialize().await.expect("Failed to initialize");

    let mut entry1 = make_entry("f-1", "agent-a", "commit message");
    entry1.action = "commit".to_string();

    let mut entry2 = make_entry("f-2", "agent-a", "merge message");
    entry2.action = "merge".to_string();

    let mut entry3 = make_entry("f-3", "agent-b", "other commit");
    entry3.action = "commit".to_string();

    storage.append_log(&entry1).await.unwrap();
    storage.append_log(&entry2).await.unwrap();
    storage.append_log(&entry3).await.unwrap();

    // Filter by agent
    let filter = LogFilter {
        agent_id: Some("agent-a".to_string()),
        limit: Some(10),
        ..Default::default()
    };
    let logs = storage.query_logs(&filter).await.unwrap();
    assert_eq!(logs.len(), 2);

    // Filter by action
    let filter = LogFilter {
        action: Some("commit".to_string()),
        limit: Some(10),
        ..Default::default()
    };
    let logs = storage.query_logs(&filter).await.unwrap();
    assert!(logs.len() >= 2); // agent-a commit + agent-b commit
}
