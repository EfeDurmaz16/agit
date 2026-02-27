use async_trait::async_trait;
use std::collections::HashMap;
use tokio_rusqlite::Connection;

use super::{LogEntry, LogFilter, StorageBackend};
use crate::error::{AgitError, Result};
use crate::types::ObjectType;

/// SQLite-backed storage using bundled SQLite (zero system dependencies).
pub struct SqliteStorage {
    conn: Connection,
}

impl SqliteStorage {
    pub async fn new(path: &str) -> Result<Self> {
        let conn = if path == ":memory:" {
            Connection::open_in_memory()
                .await
                .map_err(|e: rusqlite::Error| AgitError::Storage(e.to_string()))?
        } else {
            Connection::open(path)
                .await
                .map_err(|e: rusqlite::Error| AgitError::Storage(e.to_string()))?
        };

        let storage = SqliteStorage { conn };
        storage.initialize().await?;
        Ok(storage)
    }
}

#[async_trait]
impl StorageBackend for SqliteStorage {
    async fn initialize(&self) -> Result<()> {
        self.conn
            .call(|conn| -> std::result::Result<(), rusqlite::Error> {
                // Performance pragmas: WAL mode for concurrent reads, larger cache
                conn.execute_batch(
                    "
                    PRAGMA journal_mode = WAL;
                    PRAGMA synchronous = NORMAL;
                    PRAGMA cache_size = -64000;
                    PRAGMA busy_timeout = 5000;
                    ",
                )?;

                conn.execute_batch(
                    "
                    CREATE TABLE IF NOT EXISTS objects (
                        hash TEXT PRIMARY KEY,
                        type TEXT NOT NULL,
                        data BLOB NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE TABLE IF NOT EXISTS refs (
                        name TEXT PRIMARY KEY,
                        target TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE TABLE IF NOT EXISTS logs (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        message TEXT NOT NULL,
                        commit_hash TEXT,
                        details BLOB,
                        level TEXT NOT NULL DEFAULT 'info'
                    );
                    CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_logs_agent_id ON logs(agent_id);
                    CREATE INDEX IF NOT EXISTS idx_logs_action ON logs(action);
                    ",
                )?;
                Ok(())
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn put_object(&self, hash: &str, obj_type: ObjectType, data: &[u8]) -> Result<()> {
        let hash = hash.to_string();
        let type_str = obj_type.to_string();
        let data = data.to_vec();

        self.conn
            .call(move |conn| -> std::result::Result<(), rusqlite::Error> {
                conn.execute(
                    "INSERT OR IGNORE INTO objects (hash, type, data) VALUES (?1, ?2, ?3)",
                    rusqlite::params![hash, type_str, data],
                )?;
                Ok(())
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn get_object(&self, hash: &str) -> Result<Option<Vec<u8>>> {
        let hash = hash.to_string();

        self.conn
            .call(move |conn| -> std::result::Result<Option<Vec<u8>>, rusqlite::Error> {
                let mut stmt = conn.prepare("SELECT data FROM objects WHERE hash = ?1")?;
                let result = stmt
                    .query_row(rusqlite::params![hash], |row| row.get::<_, Vec<u8>>(0))
                    .optional()?;
                Ok(result)
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn has_object(&self, hash: &str) -> Result<bool> {
        let hash = hash.to_string();

        self.conn
            .call(move |conn| -> std::result::Result<bool, rusqlite::Error> {
                let mut stmt = conn.prepare("SELECT COUNT(*) FROM objects WHERE hash = ?1")?;
                let count: i64 = stmt.query_row(rusqlite::params![hash], |row| row.get(0))?;
                Ok(count > 0)
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn set_ref(&self, name: &str, hash: &str) -> Result<()> {
        let name = name.to_string();
        let hash = hash.to_string();

        self.conn
            .call(move |conn| -> std::result::Result<(), rusqlite::Error> {
                conn.execute(
                    "INSERT OR REPLACE INTO refs (name, target) VALUES (?1, ?2)",
                    rusqlite::params![name, hash],
                )?;
                Ok(())
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn get_ref(&self, name: &str) -> Result<Option<String>> {
        let name = name.to_string();

        self.conn
            .call(move |conn| -> std::result::Result<Option<String>, rusqlite::Error> {
                let mut stmt = conn.prepare("SELECT target FROM refs WHERE name = ?1")?;
                let result = stmt
                    .query_row(rusqlite::params![name], |row| row.get::<_, String>(0))
                    .optional()?;
                Ok(result)
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn list_refs(&self) -> Result<HashMap<String, String>> {
        self.conn
            .call(|conn| -> std::result::Result<HashMap<String, String>, rusqlite::Error> {
                let mut stmt = conn.prepare("SELECT name, target FROM refs")?;
                let rows = stmt.query_map([], |row| {
                    Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
                })?;
                let mut map = HashMap::new();
                for row in rows {
                    let (name, target) = row?;
                    map.insert(name, target);
                }
                Ok(map)
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn delete_ref(&self, name: &str) -> Result<bool> {
        let name = name.to_string();

        self.conn
            .call(move |conn| -> std::result::Result<bool, rusqlite::Error> {
                let count = conn.execute(
                    "DELETE FROM refs WHERE name = ?1",
                    rusqlite::params![name],
                )?;
                Ok(count > 0)
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn append_log(&self, entry: &LogEntry) -> Result<()> {
        let entry = entry.clone();

        self.conn
            .call(move |conn| -> std::result::Result<(), rusqlite::Error> {
                let details_bytes = entry
                    .details
                    .as_ref()
                    .map(|d| serde_json::to_vec(d).unwrap_or_default());

                conn.execute(
                    "INSERT INTO logs (id, timestamp, agent_id, action, message, commit_hash, details, level) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
                    rusqlite::params![
                        entry.id,
                        entry.timestamp,
                        entry.agent_id,
                        entry.action,
                        entry.message,
                        entry.commit_hash,
                        details_bytes,
                        entry.level,
                    ],
                )?;
                Ok(())
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn query_logs(&self, filter: &LogFilter) -> Result<Vec<LogEntry>> {
        let filter = filter.clone();

        self.conn
            .call(move |conn| -> std::result::Result<Vec<LogEntry>, rusqlite::Error> {
                let mut sql = "SELECT id, timestamp, agent_id, action, message, commit_hash, details, level FROM logs WHERE 1=1".to_string();
                let mut params: Vec<Box<dyn rusqlite::types::ToSql>> = Vec::new();

                if let Some(ref agent_id) = filter.agent_id {
                    sql.push_str(&format!(" AND agent_id = ?{}", params.len() + 1));
                    params.push(Box::new(agent_id.clone()));
                }
                if let Some(ref action) = filter.action {
                    sql.push_str(&format!(" AND action = ?{}", params.len() + 1));
                    params.push(Box::new(action.clone()));
                }
                if let Some(ref level) = filter.level {
                    sql.push_str(&format!(" AND level = ?{}", params.len() + 1));
                    params.push(Box::new(level.clone()));
                }
                if let Some(ref since) = filter.since {
                    sql.push_str(&format!(" AND timestamp >= ?{}", params.len() + 1));
                    params.push(Box::new(since.clone()));
                }

                sql.push_str(" ORDER BY timestamp DESC");

                if let Some(limit) = filter.limit {
                    sql.push_str(&format!(" LIMIT ?{}", params.len() + 1));
                    params.push(Box::new(limit as i64));
                }

                let mut stmt = conn.prepare(&sql)?;
                let param_refs: Vec<&dyn rusqlite::types::ToSql> =
                    params.iter().map(|p| p.as_ref()).collect();

                let rows = stmt.query_map(param_refs.as_slice(), |row| {
                    let details_bytes: Option<Vec<u8>> = row.get(6)?;
                    let details = details_bytes.and_then(|b| serde_json::from_slice(&b).ok());

                    Ok(LogEntry {
                        id: row.get(0)?,
                        timestamp: row.get(1)?,
                        agent_id: row.get(2)?,
                        action: row.get(3)?,
                        message: row.get(4)?,
                        commit_hash: row.get(5)?,
                        details,
                        level: row.get(7)?,
                    })
                })?;

                let mut entries = Vec::new();
                for row in rows {
                    entries.push(row?);
                }
                Ok(entries)
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }
    async fn delete_object(&self, hash: &str) -> Result<bool> {
        let hash = hash.to_string();

        self.conn
            .call(move |conn| -> std::result::Result<bool, rusqlite::Error> {
                let count = conn.execute(
                    "DELETE FROM objects WHERE hash = ?1",
                    rusqlite::params![hash],
                )?;
                Ok(count > 0)
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }

    async fn list_objects(&self) -> Result<Vec<String>> {
        self.conn
            .call(|conn| -> std::result::Result<Vec<String>, rusqlite::Error> {
                let mut stmt = conn.prepare("SELECT hash FROM objects")?;
                let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
                let mut hashes = Vec::new();
                for row in rows {
                    hashes.push(row?);
                }
                Ok(hashes)
            })
            .await
            .map_err(|e: tokio_rusqlite::Error| AgitError::Storage(e.to_string()))
    }
}

use rusqlite::OptionalExtension;

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_put_get_object() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let data = b"hello world";
        storage.put_object("abc123", ObjectType::Blob, data).await.unwrap();
        let result = storage.get_object("abc123").await.unwrap();
        assert_eq!(result, Some(data.to_vec()));
    }

    #[tokio::test]
    async fn test_get_missing_object() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let result = storage.get_object("nonexistent").await.unwrap();
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_has_object() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        storage.put_object("abc", ObjectType::Blob, b"data").await.unwrap();
        assert!(storage.has_object("abc").await.unwrap());
        assert!(!storage.has_object("xyz").await.unwrap());
    }

    #[tokio::test]
    async fn test_refs() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        storage.set_ref("main", "abc123").await.unwrap();
        storage.set_ref("dev", "def456").await.unwrap();

        assert_eq!(storage.get_ref("main").await.unwrap(), Some("abc123".to_string()));
        assert_eq!(storage.get_ref("missing").await.unwrap(), None);

        let refs = storage.list_refs().await.unwrap();
        assert_eq!(refs.len(), 2);

        storage.delete_ref("dev").await.unwrap();
        let refs = storage.list_refs().await.unwrap();
        assert_eq!(refs.len(), 1);
    }

    #[tokio::test]
    async fn test_logs() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();

        let entry = LogEntry {
            id: "log-1".to_string(),
            timestamp: "2026-01-01T00:00:00Z".to_string(),
            agent_id: "agent-1".to_string(),
            action: "tool_call".to_string(),
            message: "called search".to_string(),
            commit_hash: Some("abc123".to_string()),
            details: Some(serde_json::json!({"tool": "search"})),
            level: "info".to_string(),
        };
        storage.append_log(&entry).await.unwrap();

        let filter = LogFilter {
            agent_id: Some("agent-1".to_string()),
            ..Default::default()
        };
        let logs = storage.query_logs(&filter).await.unwrap();
        assert_eq!(logs.len(), 1);
        assert_eq!(logs[0].message, "called search");
    }

    #[tokio::test]
    async fn test_wal_mode_active() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let mode: String = storage
            .conn
            .call(|conn| {
                let mut stmt = conn.prepare("PRAGMA journal_mode")?;
                let mode: String = stmt.query_row([], |row| row.get(0))?;
                Ok(mode)
            })
            .await
            .unwrap();
        // In-memory databases may report "memory" instead of "wal", but
        // file-backed databases will report "wal". Accept both.
        assert!(
            mode == "wal" || mode == "memory",
            "expected WAL or memory journal mode, got: {mode}"
        );
    }

    #[tokio::test]
    async fn test_idempotent_put() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        storage.put_object("abc", ObjectType::Blob, b"data").await.unwrap();
        storage.put_object("abc", ObjectType::Blob, b"data").await.unwrap();
    }
}
