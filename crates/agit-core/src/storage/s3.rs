#[cfg(feature = "s3")]
use async_trait::async_trait;
#[cfg(feature = "s3")]
use aws_sdk_s3::Client as S3Client;
#[cfg(feature = "s3")]
use std::collections::HashMap;

#[cfg(feature = "s3")]
use super::{LogEntry, LogFilter, StorageBackend};
#[cfg(feature = "s3")]
use crate::error::{AgitError, Result};
#[cfg(feature = "s3")]
use crate::types::ObjectType;

/// Minimum byte size above which objects are zstd-compressed before upload.
#[cfg(feature = "s3")]
const COMPRESS_THRESHOLD: usize = 1024;

/// S3-backed storage backend.
///
/// Layout inside the bucket:
/// ```text
/// objects/<hash>          – raw (or zstd-compressed) object bytes
/// refs/<name>             – small JSON file: {"target": "<hash>"}
/// logs/<agent_id>.jsonl   – append-only JSONL audit log per agent
/// ```
///
/// Enable with the `s3` Cargo feature flag.
#[cfg(feature = "s3")]
pub struct S3Storage {
    client: S3Client,
    bucket: String,
    prefix: String,
}

#[cfg(feature = "s3")]
impl S3Storage {
    /// Create a new S3Storage.
    ///
    /// `bucket` – the S3 bucket name.
    /// `prefix` – optional key prefix (e.g. `"agit/"`) – use `""` for none.
    ///
    /// AWS credentials / region are resolved via the standard SDK chain
    /// (env vars, `~/.aws/credentials`, instance profile, etc.).
    pub async fn new(bucket: impl Into<String>, prefix: impl Into<String>) -> Result<Self> {
        let config = aws_config::load_from_env().await;
        let client = S3Client::new(&config);
        let storage = S3Storage {
            client,
            bucket: bucket.into(),
            prefix: prefix.into(),
        };
        storage.initialize().await?;
        Ok(storage)
    }

    fn object_key(&self, hash: &str) -> String {
        format!("{}objects/{}", self.prefix, hash)
    }

    fn ref_key(&self, name: &str) -> String {
        // Sanitise ref names: replace `/` → `|` to stay bucket-friendly while
        // staying reversible.
        let safe = name.replace('/', "|");
        format!("{}refs/{}", self.prefix, safe)
    }

    fn log_key(&self, agent_id: &str) -> String {
        format!("{}logs/{}.jsonl", self.prefix, agent_id)
    }

    /// Download a key and return its bytes, or `None` if not found.
    async fn get_bytes(&self, key: &str) -> Result<Option<Vec<u8>>> {
        match self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(resp) => {
                let bytes = resp
                    .body
                    .collect()
                    .await
                    .map_err(|e| AgitError::Storage(e.to_string()))?
                    .into_bytes()
                    .to_vec();
                Ok(Some(bytes))
            }
            Err(e) => {
                // The SDK wraps NoSuchKey inside SdkError; check the service error.
                let service_err = e.into_service_error();
                if service_err.is_no_such_key() {
                    Ok(None)
                } else {
                    Err(AgitError::Storage(service_err.to_string()))
                }
            }
        }
    }

    /// Upload bytes to a key, replacing any existing content.
    async fn put_bytes(&self, key: &str, data: Vec<u8>, content_type: &str) -> Result<()> {
        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .body(aws_sdk_s3::primitives::ByteStream::from(data))
            .content_type(content_type)
            .send()
            .await
            .map_err(|e| AgitError::Storage(e.into_service_error().to_string()))?;
        Ok(())
    }

    /// Check whether a key exists using a cheap HEAD request.
    async fn key_exists(&self, key: &str) -> Result<bool> {
        match self
            .client
            .head_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(_) => Ok(true),
            Err(e) => {
                let service_err = e.into_service_error();
                if service_err.is_not_found() {
                    Ok(false)
                } else {
                    Err(AgitError::Storage(service_err.to_string()))
                }
            }
        }
    }

    /// Compress `data` with zstd (level 3) if it exceeds the threshold.
    /// Returns `(possibly_compressed_bytes, was_compressed)`.
    fn maybe_compress(data: &[u8]) -> Result<(Vec<u8>, bool)> {
        if data.len() >= COMPRESS_THRESHOLD {
            let compressed = zstd::stream::encode_all(data, 3)
                .map_err(|e| AgitError::Storage(format!("zstd compress: {e}")))?;
            Ok((compressed, true))
        } else {
            Ok((data.to_vec(), false))
        }
    }

    /// Decompress `data` with zstd if `compressed` is true.
    fn maybe_decompress(data: Vec<u8>, compressed: bool) -> Result<Vec<u8>> {
        if compressed {
            zstd::stream::decode_all(data.as_slice())
                .map_err(|e| AgitError::Storage(format!("zstd decompress: {e}")))
        } else {
            Ok(data)
        }
    }
}

#[cfg(feature = "s3")]
#[async_trait]
impl StorageBackend for S3Storage {
    /// S3 is schema-less; `initialize` is a no-op but verifies bucket access
    /// by issuing a cheap `head_bucket` call.
    async fn initialize(&self) -> Result<()> {
        self.client
            .head_bucket()
            .bucket(&self.bucket)
            .send()
            .await
            .map_err(|e| {
                AgitError::Storage(format!(
                    "S3 bucket '{}' not accessible: {}",
                    self.bucket,
                    e.into_service_error()
                ))
            })?;
        Ok(())
    }

    async fn put_object(&self, hash: &str, _obj_type: ObjectType, data: &[u8]) -> Result<()> {
        let key = self.object_key(hash);

        // Skip upload if the object already exists (content-addressed → immutable).
        if self.key_exists(&key).await? {
            return Ok(());
        }

        let (body, compressed) = Self::maybe_compress(data)?;
        let content_type = if compressed {
            "application/zstd"
        } else {
            "application/octet-stream"
        };
        self.put_bytes(&key, body, content_type).await
    }

    async fn get_object(&self, hash: &str) -> Result<Option<Vec<u8>>> {
        let key = self.object_key(hash);
        match self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(&key)
            .send()
            .await
        {
            Ok(resp) => {
                let compressed = resp
                    .content_type()
                    .map(|ct| ct == "application/zstd")
                    .unwrap_or(false);
                let bytes = resp
                    .body
                    .collect()
                    .await
                    .map_err(|e| AgitError::Storage(e.to_string()))?
                    .into_bytes()
                    .to_vec();
                let out = Self::maybe_decompress(bytes, compressed)?;
                Ok(Some(out))
            }
            Err(e) => {
                let service_err = e.into_service_error();
                if service_err.is_no_such_key() {
                    Ok(None)
                } else {
                    Err(AgitError::Storage(service_err.to_string()))
                }
            }
        }
    }

    async fn has_object(&self, hash: &str) -> Result<bool> {
        self.key_exists(&self.object_key(hash)).await
    }

    async fn set_ref(&self, name: &str, hash: &str) -> Result<()> {
        let key = self.ref_key(name);
        let body = serde_json::to_vec(&serde_json::json!({ "target": hash }))
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        self.put_bytes(&key, body, "application/json").await
    }

    async fn get_ref(&self, name: &str) -> Result<Option<String>> {
        let key = self.ref_key(name);
        match self.get_bytes(&key).await? {
            None => Ok(None),
            Some(bytes) => {
                let v: serde_json::Value = serde_json::from_slice(&bytes)
                    .map_err(|e| AgitError::Storage(e.to_string()))?;
                Ok(v["target"].as_str().map(|s| s.to_string()))
            }
        }
    }

    async fn list_refs(&self) -> Result<HashMap<String, String>> {
        let prefix = format!("{}refs/", self.prefix);
        let mut map = HashMap::new();

        let mut continuation: Option<String> = None;
        loop {
            let mut req = self
                .client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(&prefix);
            if let Some(ref token) = continuation {
                req = req.continuation_token(token);
            }
            let resp = req
                .send()
                .await
                .map_err(|e| AgitError::Storage(e.into_service_error().to_string()))?;

            for obj in resp.contents() {
                let key = obj.key().unwrap_or("");
                // Strip prefix + "refs/" and restore `/` from `|`.
                let raw_name = key
                    .strip_prefix(&prefix)
                    .unwrap_or(key)
                    .replace('|', "/");

                if let Some(bytes) = self.get_bytes(key).await? {
                    let v: serde_json::Value =
                        serde_json::from_slice(&bytes).unwrap_or(serde_json::Value::Null);
                    if let Some(target) = v["target"].as_str() {
                        map.insert(raw_name, target.to_string());
                    }
                }
            }

            if resp.is_truncated().unwrap_or(false) {
                continuation = resp.next_continuation_token().map(|s| s.to_string());
            } else {
                break;
            }
        }
        Ok(map)
    }

    async fn delete_ref(&self, name: &str) -> Result<bool> {
        let key = self.ref_key(name);
        if !self.key_exists(&key).await? {
            return Ok(false);
        }
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(&key)
            .send()
            .await
            .map_err(|e| AgitError::Storage(e.into_service_error().to_string()))?;
        Ok(true)
    }

    /// Append the log entry to `logs/<agent_id>.jsonl`.
    ///
    /// S3 does not support true append; we read the existing file, append a
    /// line, and re-upload.  For high-volume production use, consider routing
    /// log writes through a queue or using S3's multipart API.
    async fn append_log(&self, entry: &LogEntry) -> Result<()> {
        let key = self.log_key(&entry.agent_id);
        let existing = self.get_bytes(&key).await?.unwrap_or_default();

        let mut line = serde_json::to_vec(entry)
            .map_err(|e| AgitError::Storage(e.to_string()))?;
        line.push(b'\n');

        let mut body = existing;
        body.extend_from_slice(&line);
        self.put_bytes(&key, body, "application/x-ndjson").await
    }

    /// Query the in-memory JSONL for `filter.agent_id` (required for S3;
    /// cross-agent scans are not supported to avoid unbounded list operations).
    async fn query_logs(&self, filter: &LogFilter) -> Result<Vec<LogEntry>> {
        let agent_id = filter.agent_id.as_deref().unwrap_or("_global");
        let key = self.log_key(agent_id);

        let bytes = match self.get_bytes(&key).await? {
            None => return Ok(Vec::new()),
            Some(b) => b,
        };

        let mut entries: Vec<LogEntry> = bytes
            .split(|&b| b == b'\n')
            .filter(|line| !line.is_empty())
            .filter_map(|line| serde_json::from_slice(line).ok())
            .collect();

        // Apply remaining filters in-memory.
        if let Some(ref action) = filter.action {
            entries.retain(|e| &e.action == action);
        }
        if let Some(ref level) = filter.level {
            entries.retain(|e| &e.level == level);
        }
        if let Some(ref since) = filter.since {
            entries.retain(|e| &e.timestamp >= since);
        }

        // JSONL is already insertion order; reverse for newest-first.
        entries.reverse();

        if let Some(limit) = filter.limit {
            entries.truncate(limit);
        }

        Ok(entries)
    }
}
