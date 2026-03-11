pub mod bisect;
pub mod blast_radius;
pub mod causal;
pub mod encryption;
pub mod error;
pub mod events;
pub mod gc;
pub mod guard;
pub mod hash;
pub mod migration;
pub mod objects;
pub mod refs;
pub mod repo;
pub mod retention;
pub mod state;
pub mod storage;
pub mod types;

#[cfg(feature = "encryption")]
pub use encryption::StateEncryptor;

// Re-export primary types for convenience
pub use error::{AgitError, Result};
pub use objects::{Blob, Commit};
pub use refs::{Head, RefStore};
pub use repo::Repository;
pub use state::{AgentState, DiffEntry, MergeConflict, MerkleNode, StateDiff, merkle_diff};
pub use storage::sqlite::SqliteStorage;
pub use storage::{LogEntry, LogFilter, StorageBackend};
pub use gc::{GcResult, SquashResult};
pub use retention::{RetentionPolicy, RetentionResult, enforce_retention, preview_retention};
pub use types::{ActionType, ChangeType, Hash, MergeStrategy, ObjectType};
pub use events::{AgitEvent, InMemoryEventBus};
pub use bisect::{BisectSession, BisectResult, BisectState};
pub use causal::{CausalGraph, CausalNode, CausalEdge, CausalRelation};
pub use guard::{CommitGuard, GuardChain, GuardContext, GuardDecision, DestructiveActionGuard, BlastRadiusGuard};
pub use blast_radius::{BlastRadiusReport, RiskLevel, analyze_blast_radius, analyze_blast_radius_opt};
pub use migration::{MigrationResult, MigrationApplyResult, CURRENT_SCHEMA_VERSION, apply_schema_migrations, migrate_data};
