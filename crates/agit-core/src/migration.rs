//! Storage backend migration and schema versioning utilities.
//!
//! Provides:
//! - Schema version tracking for storage backends
//! - Numbered migration registry with up/down support
//! - Cross-backend data migration (e.g., SQLite -> PostgreSQL)
//! - Auto-migration on repository initialization

use crate::error::{AgitError, Result};
use crate::storage::StorageBackend;
use crate::types::ObjectType;

use serde::{Deserialize, Serialize};

/// Current schema version of the agit storage format.
pub const CURRENT_SCHEMA_VERSION: u32 = 2;

/// A single schema migration step.
pub struct Migration {
    /// Version this migration upgrades TO.
    pub version: u32,
    /// Human-readable description.
    pub description: &'static str,
    /// SQL to apply (up migration). For SQLite backend.
    pub up_sql: &'static str,
    /// SQL to roll back (down migration). For SQLite backend.
    pub down_sql: &'static str,
}

/// Registry of all known migrations, ordered by version.
pub fn migrations() -> Vec<Migration> {
    vec![
        Migration {
            version: 1,
            description: "Initial schema: objects, refs, logs tables",
            up_sql: "",  // Version 1 is the baseline (created by initialize())
            down_sql: "",
        },
        Migration {
            version: 2,
            description: "Add schema_version table and retention metadata",
            up_sql: "
                CREATE TABLE IF NOT EXISTS schema_version (
                    key TEXT PRIMARY KEY DEFAULT 'version',
                    version INTEGER NOT NULL,
                    migrated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    description TEXT
                );
                ALTER TABLE objects ADD COLUMN size_bytes INTEGER DEFAULT 0;
                CREATE INDEX IF NOT EXISTS idx_objects_type ON objects(type);
                CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
            ",
            down_sql: "
                DROP TABLE IF EXISTS schema_version;
            ",
        },
    ]
}

/// Result of a migration operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MigrationResult {
    pub from_version: u32,
    pub to_version: u32,
    pub migrations_applied: usize,
    pub total_objects: usize,
    pub migrated_objects: usize,
    pub skipped_objects: usize,
    pub total_refs: usize,
    pub migrated_refs: usize,
}

/// Progress callback data.
pub struct MigrationProgress<'a> {
    pub phase: &'a str,
    pub current: usize,
    pub total: usize,
}

/// Migrate all data from one storage backend to another.
///
/// This is idempotent: objects that already exist in the target are skipped.
/// Progress is reported via the optional callback.
pub async fn migrate_data<F>(
    source: &dyn StorageBackend,
    target: &dyn StorageBackend,
    mut on_progress: Option<F>,
) -> Result<MigrationResult>
where
    F: FnMut(MigrationProgress),
{
    target.initialize().await?;

    // Migrate objects
    let objects = source.list_objects().await?;
    let total_objects = objects.len();
    let mut migrated_objects = 0;
    let mut skipped_objects = 0;

    for (i, hash) in objects.iter().enumerate() {
        if target.has_object(hash).await? {
            skipped_objects += 1;
        } else if let Some(data) = source.get_object(hash).await? {
            // Try to determine type by attempting to parse as commit
            let obj_type = if serde_json::from_slice::<crate::objects::Commit>(&data).is_ok() {
                ObjectType::Commit
            } else {
                ObjectType::Blob
            };
            target.put_object(hash, obj_type, &data).await?;
            migrated_objects += 1;
        }

        if let Some(ref mut cb) = on_progress {
            cb(MigrationProgress {
                phase: "objects",
                current: i + 1,
                total: total_objects,
            });
        }
    }

    // Migrate refs
    let refs = source.list_refs().await?;
    let total_refs = refs.len();
    let mut migrated_refs = 0;

    for (i, (name, hash)) in refs.iter().enumerate() {
        target.set_ref(name, hash).await?;
        migrated_refs += 1;

        if let Some(ref mut cb) = on_progress {
            cb(MigrationProgress {
                phase: "refs",
                current: i + 1,
                total: total_refs,
            });
        }
    }

    Ok(MigrationResult {
        from_version: 0,
        to_version: CURRENT_SCHEMA_VERSION,
        migrations_applied: 0,
        total_objects,
        migrated_objects,
        skipped_objects,
        total_refs,
        migrated_refs,
    })
}

/// Apply schema migrations to a SQLite storage backend.
/// This runs inside the sqlite connection and applies any pending migrations.
pub async fn apply_schema_migrations(storage: &crate::storage::sqlite::SqliteStorage) -> Result<MigrationApplyResult> {
    use tokio_rusqlite::Connection;

    let all_migrations = migrations();

    storage.run_migration(|conn| {
        // Check current version
        let has_version_table: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='schema_version'",
                [],
                |row| row.get::<_, i64>(0),
            )
            .map(|c| c > 0)
            .unwrap_or(false);

        let current_version = if has_version_table {
            conn.query_row(
                "SELECT COALESCE(MAX(version), 0) FROM schema_version",
                [],
                |row| row.get::<_, u32>(0),
            )
            .unwrap_or(1)
        } else {
            1 // Baseline: tables exist but no version tracking
        };

        let mut applied = 0;
        for migration in &all_migrations {
            if migration.version > current_version && !migration.up_sql.is_empty() {
                conn.execute_batch(migration.up_sql)
                    .map_err(|e| rusqlite::Error::ToSqlConversionFailure(
                        Box::new(std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))
                    ))?;

                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (key, version, description) VALUES ('version', ?1, ?2)",
                    rusqlite::params![migration.version, migration.description],
                )?;
                applied += 1;
            }
        }

        // If no version table existed, create it and set to current
        if !has_version_table && applied == 0 {
            conn.execute_batch(
                "CREATE TABLE IF NOT EXISTS schema_version (
                    key TEXT PRIMARY KEY DEFAULT 'version',
                    version INTEGER NOT NULL,
                    migrated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    description TEXT
                );"
            )?;
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (key, version, description) VALUES ('version', ?1, ?2)",
                rusqlite::params![CURRENT_SCHEMA_VERSION, "auto-set to current"],
            )?;
        }

        Ok(MigrationApplyResult {
            from_version: current_version,
            to_version: CURRENT_SCHEMA_VERSION,
            migrations_applied: applied,
        })
    }).await
}

/// Result of applying schema migrations.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MigrationApplyResult {
    pub from_version: u32,
    pub to_version: u32,
    pub migrations_applied: usize,
}

/// Get the current schema version from storage.
pub async fn get_schema_version(storage: &crate::storage::sqlite::SqliteStorage) -> Result<u32> {
    storage.run_migration(|conn| {
        let has_table: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='schema_version'",
                [],
                |row| row.get::<_, i64>(0),
            )
            .map(|c| c > 0)
            .unwrap_or(false);

        if !has_table {
            return Ok(1); // Baseline version
        }

        conn.query_row(
            "SELECT COALESCE(MAX(version), 1) FROM schema_version",
            [],
            |row| row.get::<_, u32>(0),
        ).map_err(|e| e)
    }).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::sqlite::SqliteStorage;

    #[tokio::test]
    async fn test_migration_registry_ordered() {
        let migs = migrations();
        for i in 1..migs.len() {
            assert!(migs[i].version > migs[i - 1].version);
        }
    }

    #[tokio::test]
    async fn test_apply_schema_migrations() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let result = apply_schema_migrations(&storage).await.unwrap();
        assert_eq!(result.to_version, CURRENT_SCHEMA_VERSION);
    }

    #[tokio::test]
    async fn test_idempotent_migrations() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let r1 = apply_schema_migrations(&storage).await.unwrap();
        let r2 = apply_schema_migrations(&storage).await.unwrap();
        // Second run should be a no-op
        assert_eq!(r2.migrations_applied, 0);
    }

    #[tokio::test]
    async fn test_get_schema_version() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let v1 = get_schema_version(&storage).await.unwrap();
        assert_eq!(v1, 1); // Before migration

        apply_schema_migrations(&storage).await.unwrap();
        let v2 = get_schema_version(&storage).await.unwrap();
        assert_eq!(v2, CURRENT_SCHEMA_VERSION);
    }

    #[tokio::test]
    async fn test_migrate_data_between_backends() {
        let source = SqliteStorage::new(":memory:").await.unwrap();
        let target = SqliteStorage::new(":memory:").await.unwrap();

        // Put some data in source
        use crate::types::ObjectType;
        source.initialize().await.unwrap();
        source.put_object("abc123", ObjectType::Blob, b"hello").await.unwrap();
        source.set_ref("main", "abc123").await.unwrap();

        let result = migrate_data(&source, &target, None::<fn(MigrationProgress)>).await.unwrap();
        assert_eq!(result.migrated_objects, 1);
        assert_eq!(result.migrated_refs, 1);

        // Verify target has the data
        let obj = target.get_object("abc123").await.unwrap();
        assert_eq!(obj, Some(b"hello".to_vec()));
    }
}
