pub mod error;
pub mod hash;
pub mod objects;
pub mod refs;
pub mod repo;
pub mod state;
pub mod storage;
pub mod types;

// Re-export primary types for convenience
pub use error::{AgitError, Result};
pub use objects::{Blob, Commit};
pub use refs::{Head, RefStore};
pub use repo::Repository;
pub use state::{AgentState, DiffEntry, MergeConflict, StateDiff};
pub use storage::sqlite::SqliteStorage;
pub use storage::{LogEntry, LogFilter, StorageBackend};
pub use types::{ActionType, ChangeType, Hash, MergeStrategy, ObjectType};
