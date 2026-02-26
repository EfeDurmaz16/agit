use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::hash::{canonical_serialize, compute_hash};
use crate::types::{ActionType, Hash, ObjectType};

/// Content-addressed blob storing agent state as JSON.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Blob {
    pub data: Value,
}

impl Blob {
    pub fn new(data: Value) -> Self {
        Blob { data }
    }

    pub fn serialize(&self) -> Vec<u8> {
        canonical_serialize(&self.data)
    }

    pub fn hash(&self) -> Hash {
        compute_hash(ObjectType::Blob, &self.serialize())
    }
}

/// A commit pointing to a state blob, with parent links forming a DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Commit {
    pub tree_hash: Hash,
    pub parent_hashes: Vec<Hash>,
    pub message: String,
    pub author: String,
    pub timestamp: DateTime<Utc>,
    pub action_type: ActionType,
    #[serde(default)]
    pub metadata: serde_json::Map<String, Value>,
}

impl Commit {
    pub fn serialize(&self) -> Vec<u8> {
        // Build a canonical JSON representation with sorted keys
        let value = serde_json::json!({
            "action_type": self.action_type,
            "author": self.author,
            "message": self.message,
            "metadata": self.metadata,
            "parent_hashes": self.parent_hashes,
            "timestamp": self.timestamp.to_rfc3339(),
            "tree_hash": self.tree_hash,
        });
        canonical_serialize(&value)
    }

    pub fn hash(&self) -> Hash {
        compute_hash(ObjectType::Commit, &self.serialize())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_blob_hash_deterministic() {
        let blob1 = Blob::new(json!({"counter": 42}));
        let blob2 = Blob::new(json!({"counter": 42}));
        assert_eq!(blob1.hash(), blob2.hash());
    }

    #[test]
    fn test_blob_different_data_different_hash() {
        let blob1 = Blob::new(json!({"counter": 1}));
        let blob2 = Blob::new(json!({"counter": 2}));
        assert_ne!(blob1.hash(), blob2.hash());
    }

    #[test]
    fn test_commit_hash_deterministic() {
        let ts = Utc::now();
        let c1 = Commit {
            tree_hash: Hash::from("abc123"),
            parent_hashes: vec![],
            message: "test".to_string(),
            author: "agent".to_string(),
            timestamp: ts,
            action_type: ActionType::ToolCall,
            metadata: serde_json::Map::new(),
        };
        let c2 = Commit {
            tree_hash: Hash::from("abc123"),
            parent_hashes: vec![],
            message: "test".to_string(),
            author: "agent".to_string(),
            timestamp: ts,
            action_type: ActionType::ToolCall,
            metadata: serde_json::Map::new(),
        };
        assert_eq!(c1.hash(), c2.hash());
    }

    #[test]
    fn test_blob_serialization_roundtrip() {
        let data = json!({"memory": {"facts": [1, 2, 3]}, "world": "state"});
        let blob = Blob::new(data.clone());
        let serialized = blob.serialize();
        // Verify it's valid JSON
        let parsed: Value = serde_json::from_slice(&serialized).unwrap();
        // Keys should be sorted
        assert_eq!(parsed, json!({"memory": {"facts": [1, 2, 3]}, "world": "state"}));
    }
}
