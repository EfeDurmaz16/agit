#[cfg(feature = "postgres")]
use async_trait::async_trait;
#[cfg(feature = "postgres")]
use std::collections::HashMap;
#[cfg(feature = "postgres")]
use deadpool_postgres::{Config, Pool, Runtime};
#[cfg(feature = "postgres")]
use tokio_postgres::NoTls;

#[cfg(feature = "postgres")]
use super::{LogEntry, LogFilter, StorageBackend};
#[cfg(feature = "postgres")]
use crate::error::{AgitError, Result};
#[cfg(feature = "postgres")]
use crate::types::ObjectType;

/// PostgreSQL-backed storage with multi-tenant support and connection pooling.
///
/// Uses `deadpool_postgres::Pool` for connection pooling, allowing efficient
/// concurrent access without serializing behind a single connection.
///
/// Enable with the `postgres` Cargo feature flag.
#[cfg(feature = "postgres")]
pub struct PostgresStorage {
    pool: Pool,
    namespace: String,
}

#[cfg(feature = "postgres")]
impl PostgresStorage {
    /// Connect to a PostgreSQL database using a connection string, e.g.
    /// `"host=localhost user=postgres dbname=agit"`.
    pub async fn new(connection_str: &str) -> Result<Self> {
        Self::new_scoped(connection_str, "").await
    }

    /// Connect to PostgreSQL with a storage namespace.
    ///
    /// The namespace is used to isolate refs and objects across tenants.
    pub async fn new_scoped(connection_str: &str, namespace: &str) -> Result<Self> {
        let mut cfg = Config::new();
        cfg.url = Some(connection_str.to_string());
        cfg.pool = Some(deadpool_postgres::PoolConfig {
            max_size: 16,
            ..Default::default()
        });

        let pool = cfg
            .create_pool(Some(Runtime::Tokio1), NoTls)
            .map_err(|e| AgitError::Storage(format!("pool creation error: {e}")))?;

        let storage = PostgresStorage {
            pool,
            namespace: namespace.to_string(),
        };
        storage.initialize().await?;
        Ok(storage)
    }

    fn scope_hash(&self, hash: &str) -> String {
        if self.namespace.is_empty() {
            hash.to_string()
        } else {
            format!("{}:{}", self.namespace, hash)
        }
    }

    fn unscope_hash(&self, scoped: &str) -> String {
        if self.namespace.is_empty() {
            scoped.to_string()
        } else {
            scoped
                .strip_prefix(&format!("{}:", self.namespace))
                .unwrap_or(scoped)
                .to_string()
        }
    }

    fn scope_ref(&self, name: &str) -> String {
        if self.namespace.is_empty() {
            name.to_string()
        } else {
            format!("{}:{}", self.namespace, name)
        }
    }

    fn unscope_ref(&self, scoped: &str) -> String {
        if self.namespace.is_empty() {
            scoped.to_string()
        } else {
            scoped
                .strip_prefix(&format!("{}:", self.namespace))
                .unwrap_or(scoped)
                .to_string()
        }
    }
}

#[cfg(feature = "postgres")]
#[async_trait]
impl StorageBackend for PostgresStorage {
    async fn initialize(&self) -> Result<()> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        client
            .batch_execute(
                "
                CREATE TABLE IF NOT EXISTS objects (
                    hash        TEXT        PRIMARY KEY,
                    type        TEXT        NOT NULL,
                    data        BYTEA       NOT NULL,
                    agent_id    TEXT        NOT NULL DEFAULT '',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS refs (
                    name        TEXT        NOT NULL,
                    target      TEXT        NOT NULL,
                    agent_id    TEXT        NOT NULL DEFAULT '',
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (name, agent_id)
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id          TEXT        NOT NULL,
                    timestamp   TEXT        NOT NULL,
                    agent_id    TEXT        NOT NULL,
                    action      TEXT        NOT NULL,
                    message     TEXT        NOT NULL,
                    commit_hash TEXT,
                    details     JSONB,
                    level       TEXT        NOT NULL DEFAULT 'info',
                    PRIMARY KEY (id, agent_id)
                );

                CREATE INDEX IF NOT EXISTS idx_logs_timestamp  ON logs(timestamp);
                CREATE INDEX IF NOT EXISTS idx_logs_agent_id   ON logs(agent_id);
                CREATE INDEX IF NOT EXISTS idx_logs_action     ON logs(action);
                CREATE INDEX IF NOT EXISTS idx_objects_agent   ON objects(agent_id);
                ",
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))
    }

    async fn put_object(&self, hash: &str, obj_type: ObjectType, data: &[u8]) -> Result<()> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let type_str = obj_type.to_string();
        let scoped_hash = self.scope_hash(hash);
        client
            .execute(
                "INSERT INTO objects (hash, type, data)
                 VALUES ($1, $2, $3)
                 ON CONFLICT (hash) DO NOTHING",
                &[&scoped_hash, &type_str, &data],
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        Ok(())
    }

    async fn get_object(&self, hash: &str) -> Result<Option<Vec<u8>>> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let scoped_hash = self.scope_hash(hash);
        let rows = client
            .query(
                "SELECT data FROM objects WHERE hash = $1",
                &[&scoped_hash],
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        Ok(rows.first().map(|row| row.get::<_, Vec<u8>>(0)))
    }

    async fn has_object(&self, hash: &str) -> Result<bool> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let scoped_hash = self.scope_hash(hash);
        let rows = client
            .query(
                "SELECT 1 FROM objects WHERE hash = $1 LIMIT 1",
                &[&scoped_hash],
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        Ok(!rows.is_empty())
    }

    async fn set_ref(&self, name: &str, hash: &str) -> Result<()> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let scoped_name = self.scope_ref(name);
        let scoped_hash = self.scope_hash(hash);
        client
            .execute(
                "INSERT INTO refs (name, target, agent_id)
                 VALUES ($1, $2, '')
                 ON CONFLICT (name, agent_id)
                 DO UPDATE SET target = EXCLUDED.target, updated_at = NOW()",
                &[&scoped_name, &scoped_hash],
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        Ok(())
    }

    async fn get_ref(&self, name: &str) -> Result<Option<String>> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let scoped_name = self.scope_ref(name);
        let rows = client
            .query(
                "SELECT target FROM refs WHERE name = $1 AND agent_id = ''",
                &[&scoped_name],
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        Ok(rows
            .first()
            .map(|row| self.unscope_hash(&row.get::<_, String>(0))))
    }

    async fn list_refs(&self) -> Result<HashMap<String, String>> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let rows = client
            .query(
                "SELECT name, target FROM refs WHERE agent_id = ''",
                &[],
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        let mut map = HashMap::new();
        for row in rows {
            let scoped_name: String = row.get(0);
            if !self.namespace.is_empty() && !scoped_name.starts_with(&format!("{}:", self.namespace)) {
                continue;
            }
            let scoped_target: String = row.get(1);
            map.insert(
                self.unscope_ref(&scoped_name),
                self.unscope_hash(&scoped_target),
            );
        }
        Ok(map)
    }

    async fn delete_ref(&self, name: &str) -> Result<bool> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let scoped_name = self.scope_ref(name);
        let count = client
            .execute(
                "DELETE FROM refs WHERE name = $1 AND agent_id = ''",
                &[&scoped_name],
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        Ok(count > 0)
    }

    async fn append_log(&self, entry: &LogEntry) -> Result<()> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let details_json: Option<String> = entry
            .details
            .as_ref()
            .map(|v| serde_json::to_string(v))
            .transpose()
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        client
            .execute(
                "INSERT INTO logs (id, timestamp, agent_id, action, message, commit_hash, details, level)
                 VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)",
                &[
                    &entry.id,
                    &entry.timestamp,
                    &entry.agent_id,
                    &entry.action,
                    &entry.message,
                    &entry.commit_hash,
                    &details_json,
                    &entry.level,
                ],
            )
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        Ok(())
    }

    async fn query_logs(&self, filter: &LogFilter) -> Result<Vec<LogEntry>> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;

        // Build a parameterised query dynamically.  We use $1, $2, … style
        // placeholders.  Collect the actual parameter values as trait objects
        // so we can pass them to tokio-postgres.
        let mut conditions: Vec<String> = Vec::new();
        // We'll store owned strings/Options and then borrow them.
        let mut p_agent_id: Option<String> = None;
        let mut p_action: Option<String> = None;
        let mut p_level: Option<String> = None;
        let mut p_since: Option<String> = None;

        let mut param_idx: usize = 1;

        if let Some(ref v) = filter.agent_id {
            p_agent_id = Some(v.clone());
            conditions.push(format!("agent_id = ${}", param_idx));
            param_idx += 1;
        }
        if let Some(ref v) = filter.action {
            p_action = Some(v.clone());
            conditions.push(format!("action = ${}", param_idx));
            param_idx += 1;
        }
        if let Some(ref v) = filter.level {
            p_level = Some(v.clone());
            conditions.push(format!("level = ${}", param_idx));
            param_idx += 1;
        }
        if let Some(ref v) = filter.since {
            p_since = Some(v.clone());
            conditions.push(format!("timestamp >= ${}", param_idx));
            param_idx += 1;
        }

        let where_clause = if conditions.is_empty() {
            String::new()
        } else {
            format!("WHERE {}", conditions.join(" AND "))
        };

        let mut p_limit: Option<i64> = None;
        let limit_clause = if let Some(l) = filter.limit {
            p_limit = Some(l as i64);
            format!(" LIMIT ${}", param_idx)
        } else {
            String::new()
        };

        let sql = format!(
            "SELECT id, timestamp, agent_id, action, message, commit_hash, details, level
             FROM logs
             {} ORDER BY timestamp DESC{}",
            where_clause, limit_clause
        );

        // Build the params slice dynamically.
        let mut params: Vec<&(dyn tokio_postgres::types::ToSql + Sync)> = Vec::new();
        if let Some(ref v) = p_agent_id {
            params.push(v);
        }
        if let Some(ref v) = p_action {
            params.push(v);
        }
        if let Some(ref v) = p_level {
            params.push(v);
        }
        if let Some(ref v) = p_since {
            params.push(v);
        }
        if let Some(ref v) = p_limit {
            params.push(v);
        }

        let rows = client
            .query(sql.as_str(), params.as_slice())
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;

        let entries = rows
            .into_iter()
            .map(|row| -> Result<LogEntry> {
                let details_raw: Option<String> = row.get(6);
                let details = match details_raw {
                    Some(s) => Some(
                        serde_json::from_str(&s)
                            .map_err(|e| AgitError::Storage(e.to_string()))?,
                    ),
                    None => None,
                };
                Ok(LogEntry {
                    id: row.get(0),
                    timestamp: row.get(1),
                    agent_id: row.get(2),
                    action: row.get(3),
                    message: row.get(4),
                    commit_hash: row.get(5),
                    details,
                    level: row.get(7),
                })
            })
            .collect::<Result<Vec<_>>>()?;

        Ok(entries)
    }

    async fn delete_object(&self, hash: &str) -> Result<bool> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let scoped_hash = self.scope_hash(hash);
        let count = client
            .execute("DELETE FROM objects WHERE hash = $1", &[&scoped_hash])
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        Ok(count > 0)
    }

    async fn list_objects(&self) -> Result<Vec<String>> {
        let client = self.pool.get().await
            .map_err(|e| AgitError::Storage(format!("pool error: {e}")))?;
        let rows = client
            .query("SELECT hash FROM objects", &[])
            .await
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        let mut objects = Vec::new();
        for row in rows {
            let scoped_hash: String = row.get(0);
            if self.namespace.is_empty()
                || scoped_hash.starts_with(&format!("{}:", self.namespace))
            {
                objects.push(self.unscope_hash(&scoped_hash));
            }
        }
        Ok(objects)
    }
}
