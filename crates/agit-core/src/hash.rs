use sha2::{Digest, Sha256};

use crate::types::{Hash, ObjectType};

/// Serialize a JSON value with sorted keys for deterministic hashing.
pub fn canonical_serialize(value: &serde_json::Value) -> Vec<u8> {
    fn write_sorted(value: &serde_json::Value, buf: &mut Vec<u8>) {
        match value {
            serde_json::Value::Object(map) => {
                let mut keys: Vec<&String> = map.keys().collect();
                keys.sort();
                buf.push(b'{');
                for (i, key) in keys.iter().enumerate() {
                    if i > 0 {
                        buf.push(b',');
                    }
                    // Write key
                    buf.push(b'"');
                    buf.extend_from_slice(key.as_bytes());
                    buf.push(b'"');
                    buf.push(b':');
                    // Write value recursively
                    write_sorted(&map[*key], buf);
                }
                buf.push(b'}');
            }
            serde_json::Value::Array(arr) => {
                buf.push(b'[');
                for (i, item) in arr.iter().enumerate() {
                    if i > 0 {
                        buf.push(b',');
                    }
                    write_sorted(item, buf);
                }
                buf.push(b']');
            }
            _ => {
                // Primitives: use serde_json's serialization
                let s = serde_json::to_string(value).unwrap_or_default();
                buf.extend_from_slice(s.as_bytes());
            }
        }
    }

    let mut buf = Vec::new();
    write_sorted(value, &mut buf);
    buf
}

/// Compute a SHA-256 hash using Git-style format: `<type> <len>\0<content>`.
pub fn compute_hash(obj_type: ObjectType, content: &[u8]) -> Hash {
    let mut hasher = Sha256::new();
    let header = format!("{} {}\0", obj_type, content.len());
    hasher.update(header.as_bytes());
    hasher.update(content);
    let result = hasher.finalize();
    Hash(hex::encode(result))
}

/// Compute a hash of agent state by canonical-serializing the JSON value.
pub fn compute_state_hash(state: &serde_json::Value) -> Hash {
    let content = canonical_serialize(state);
    compute_hash(ObjectType::Blob, &content)
}

// Inline hex encoding to avoid adding the `hex` crate dependency.
mod hex {
    pub fn encode(bytes: impl AsRef<[u8]>) -> String {
        bytes
            .as_ref()
            .iter()
            .map(|b| format!("{:02x}", b))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_canonical_serialize_sorts_keys() {
        let value = json!({"z": 1, "a": 2, "m": 3});
        let serialized = String::from_utf8(canonical_serialize(&value)).unwrap();
        assert_eq!(serialized, r#"{"a":2,"m":3,"z":1}"#);
    }

    #[test]
    fn test_canonical_serialize_nested() {
        let value = json!({"b": {"z": 1, "a": 2}, "a": [3, 2, 1]});
        let serialized = String::from_utf8(canonical_serialize(&value)).unwrap();
        assert_eq!(serialized, r#"{"a":[3,2,1],"b":{"a":2,"z":1}}"#);
    }

    #[test]
    fn test_compute_hash_deterministic() {
        let content = b"hello world";
        let h1 = compute_hash(ObjectType::Blob, content);
        let h2 = compute_hash(ObjectType::Blob, content);
        assert_eq!(h1, h2);
        assert_eq!(h1.0.len(), 64); // SHA-256 = 64 hex chars
    }

    #[test]
    fn test_compute_hash_different_types() {
        let content = b"same content";
        let blob_hash = compute_hash(ObjectType::Blob, content);
        let commit_hash = compute_hash(ObjectType::Commit, content);
        assert_ne!(blob_hash, commit_hash);
    }

    #[test]
    fn test_compute_state_hash() {
        let state = json!({"memory": {"counter": 1}, "world_state": {}});
        let h1 = compute_state_hash(&state);
        let h2 = compute_state_hash(&state);
        assert_eq!(h1, h2);
    }
}
