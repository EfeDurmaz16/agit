pub mod sqlite;

#[cfg(feature = "postgres")]
pub mod postgres;

#[cfg(feature = "s3")]
pub mod s3;

#[cfg(feature = "postgres")]
pub use postgres::PostgresStorage;

#[cfg(feature = "s3")]
pub use s3::S3Storage;

use async_trait::async_trait;
use std::collections::HashMap;

use crate::error::Result;
use crate::types::ObjectType;

/// An entry in the audit log.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct LogEntry {
    pub id: String,
    pub timestamp: String,
    pub agent_id: String,
    pub action: String,
    pub message: String,
    pub commit_hash: Option<String>,
    pub details: Option<serde_json::Value>,
    pub level: String,
}

/// Filter for querying log entries.
#[derive(Debug, Clone, Default)]
pub struct LogFilter {
    pub agent_id: Option<String>,
    pub action: Option<String>,
    pub level: Option<String>,
    pub limit: Option<usize>,
    pub since: Option<String>,
}

/// Trait for pluggable storage backends.
#[async_trait]
pub trait StorageBackend: Send + Sync {
    /// Initialize storage (create tables, etc.).
    async fn initialize(&self) -> Result<()>;

    /// Store a content-addressed object.
    async fn put_object(&self, hash: &str, obj_type: ObjectType, data: &[u8]) -> Result<()>;

    /// Retrieve an object by hash.
    async fn get_object(&self, hash: &str) -> Result<Option<Vec<u8>>>;

    /// Check if an object exists.
    async fn has_object(&self, hash: &str) -> Result<bool>;

    /// Set a named reference to point to a hash.
    async fn set_ref(&self, name: &str, hash: &str) -> Result<()>;

    /// Get the hash a reference points to.
    async fn get_ref(&self, name: &str) -> Result<Option<String>>;

    /// List all references.
    async fn list_refs(&self) -> Result<HashMap<String, String>>;

    /// Delete a reference.
    async fn delete_ref(&self, name: &str) -> Result<bool>;

    /// Append an entry to the audit log.
    async fn append_log(&self, entry: &LogEntry) -> Result<()>;

    /// Query audit log entries.
    async fn query_logs(&self, filter: &LogFilter) -> Result<Vec<LogEntry>>;
}
