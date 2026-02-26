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
/// objects/<hash>                              – raw (or zstd-compressed) object bytes
/// refs/<name>                                 – small JSON file: {"target": "<hash>"}
/// logs/<agent_id>/<timestamp>_<uuid>.json     – one object per log entry (atomic append)
/// ```
///
/// Enable with the `s3` Cargo feature flag.
#[cfg(feature = "s3")]
pub struct S3Storage {
    client: S3Client,
    bucket: String,
    prefix: String,
    sqs_queue_url: Option<String>,
    compress: bool,
}

#[cfg(feature = "s3")]
impl S3Storage {
    /// Create a new S3Storage.
    ///
    /// `bucket` – the S3 bucket name.
    /// `prefix` – optional key prefix (e.g. `"agit/"`) – use `""` for none.
    /// `sqs_queue_url` – optional SQS queue URL for real-time log streaming.
    ///
    /// AWS credentials / region are resolved via the standard SDK chain
    /// (env vars, `~/.aws/credentials`, instance profile, etc.).
    pub async fn new(
        bucket: impl Into<String>,
        prefix: impl Into<String>,
        sqs_queue_url: Option<String>,
    ) -> Result<Self> {
        let config = aws_config::load_from_env().await;
        let client = S3Client::new(&config);
        let storage = S3Storage {
            client,
            bucket: bucket.into(),
            prefix: prefix.into(),
            sqs_queue_url,
            compress: true,
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

    /// Build the S3 key prefix for log entries belonging to a given agent.
    fn log_prefix(&self, agent_id: &str) -> String {
        format!("{}logs/{}/", self.prefix, agent_id)
    }

    /// Build the S3 key prefix for all log entries.
    fn all_logs_prefix(&self) -> String {
        format!("{}logs/", self.prefix)
    }

    /// Download a key and return its raw bytes, or `None` if not found.
    /// Unlike `get_bytes`, this returns `Ok(None)` for any SDK error (for
    /// resilient log scanning).
    async fn get_raw_object(&self, key: &str) -> Result<Option<Vec<u8>>> {
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
                    .map_err(|e| AgitError::Storage(e.to_string()))?;
                Ok(Some(bytes.into_bytes().to_vec()))
            }
            Err(_) => Ok(None),
        }
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
    /// Enforces AES-256 server-side encryption on all objects.
    async fn put_bytes(&self, key: &str, data: Vec<u8>, content_type: &str) -> Result<()> {
        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .body(aws_sdk_s3::primitives::ByteStream::from(data))
            .content_type(content_type)
            .server_side_encryption(aws_sdk_s3::types::ServerSideEncryption::Aes256)
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

    /// Append a log entry as an individual S3 object.
    ///
    /// Key pattern: `{prefix}/logs/{agent_id}/{timestamp}_{id}.json`
    ///
    /// Each entry is its own object, making concurrent writes fully atomic –
    /// no read-modify-write race.  Optional zstd compression is applied when
    /// `self.compress` is true.
    async fn append_log(&self, entry: &LogEntry) -> Result<()> {
        let key = format!(
            "{}logs/{}/{}_{}.json",
            self.prefix,
            entry.agent_id,
            entry.timestamp.replace(':', "-"),
            entry.id,
        );

        let data = serde_json::to_vec(entry)
            .map_err(|e| AgitError::Storage(e.to_string()))?;

        let body = if self.compress {
            zstd::stream::encode_all(data.as_slice(), 3)
                .map_err(|e| AgitError::Storage(format!("compression error: {e}")))?
        } else {
            data
        };

        let content_type = if self.compress {
            "application/zstd"
        } else {
            "application/json"
        };

        self.put_bytes(&key, body, content_type).await?;

        // Optional SQS notification (placeholder – requires aws-sdk-sqs dep).
        if let Some(_queue_url) = &self.sqs_queue_url {
            // SQS integration placeholder: publish key + entry metadata to queue
            // for real-time log streaming consumers.
        }

        Ok(())
    }

    /// Query log entries by listing per-entry S3 objects and fetching each.
    ///
    /// When `filter.agent_id` is set the list is scoped to that agent's
    /// prefix; otherwise all agents are scanned.  Remaining filters (action,
    /// level, since) are applied in-memory after deserialization.
    async fn query_logs(&self, filter: &LogFilter) -> Result<Vec<LogEntry>> {
        let prefix = match &filter.agent_id {
            Some(agent_id) => self.log_prefix(agent_id),
            None => self.all_logs_prefix(),
        };

        let mut entries = Vec::new();
        let mut continuation_token: Option<String> = None;

        loop {
            let mut req = self
                .client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(&prefix);

            if let Some(ref token) = continuation_token {
                req = req.continuation_token(token);
            }

            let resp = req
                .send()
                .await
                .map_err(|e| AgitError::Storage(e.into_service_error().to_string()))?;

            for obj in resp.contents() {
                let key = obj.key().unwrap_or("");
                if let Ok(Some(raw)) = self.get_raw_object(key).await {
                    let bytes = if self.compress {
                        zstd::stream::decode_all(raw.as_slice()).unwrap_or(raw)
                    } else {
                        raw
                    };
                    if let Ok(entry) = serde_json::from_slice::<LogEntry>(&bytes) {
                        // Apply filters
                        if let Some(ref action) = filter.action {
                            if &entry.action != action {
                                continue;
                            }
                        }
                        if let Some(ref level) = filter.level {
                            if &entry.level != level {
                                continue;
                            }
                        }
                        if let Some(ref since) = filter.since {
                            if entry.timestamp < *since {
                                continue;
                            }
                        }
                        entries.push(entry);
                    }
                }
            }

            if resp.is_truncated().unwrap_or(false) {
                continuation_token = resp.next_continuation_token().map(|s| s.to_string());
            } else {
                break;
            }
        }

        // Sort by timestamp (ascending).
        entries.sort_by(|a, b| a.timestamp.cmp(&b.timestamp));

        // Apply limit.
        if let Some(limit) = filter.limit {
            entries.truncate(limit);
        }

        Ok(entries)
    }

    async fn delete_object(&self, hash: &str) -> Result<bool> {
        let key = self.object_key(hash);
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(&key)
            .send()
            .await
            .map_err(|e| AgitError::Storage(e.into_service_error().to_string()))?;
        Ok(true)
    }

    async fn list_objects(&self) -> Result<Vec<String>> {
        let prefix = format!("{}objects/", self.prefix);
        let mut hashes = Vec::new();
        let mut continuation_token: Option<String> = None;

        loop {
            let mut req = self
                .client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(&prefix);

            if let Some(ref token) = continuation_token {
                req = req.continuation_token(token);
            }

            let resp = req
                .send()
                .await
                .map_err(|e| AgitError::Storage(e.into_service_error().to_string()))?;

            for obj in resp.contents() {
                if let Some(key) = obj.key() {
                    // Extract hash from key: prefix/objects/<hash>
                    if let Some(hash) = key.strip_prefix(&prefix) {
                        hashes.push(hash.to_string());
                    }
                }
            }

            if resp.is_truncated().unwrap_or(false) {
                continuation_token = resp.next_continuation_token().map(|s| s.to_string());
            } else {
                break;
            }
        }

        Ok(hashes)
    }
}
