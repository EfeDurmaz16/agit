//! Storage backend migration utilities.
//!
//! Provides tools to migrate data between storage backends (e.g., SQLite → PostgreSQL).

use crate::error::Result;
use crate::storage::StorageBackend;
use crate::types::ObjectType;

/// Migrate all data from one storage backend to another.
///
/// This is idempotent: objects that already exist in the target are skipped.
/// Progress is reported via the optional callback.
pub async fn migrate<F>(
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
        total_objects,
        migrated_objects,
        skipped_objects,
        total_refs,
        migrated_refs,
    })
}

/// Progress callback data.
pub struct MigrationProgress<'a> {
    pub phase: &'a str,
    pub current: usize,
    pub total: usize,
}

/// Result of a migration operation.
#[derive(Debug, Clone)]
pub struct MigrationResult {
    pub total_objects: usize,
    pub migrated_objects: usize,
    pub skipped_objects: usize,
    pub total_refs: usize,
    pub migrated_refs: usize,
}
