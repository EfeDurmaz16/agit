use napi_derive::napi;

use agit_core::{AgentState, Commit, DiffEntry, StateDiff};

/// JS-facing wrapper for AgentState. JSON fields are serialized strings.
#[napi(object)]
pub struct JsAgentState {
    /// JSON string of the memory object
    pub memory: String,
    /// JSON string of the world_state object
    pub world_state: String,
    pub timestamp: String,
    pub cost: f64,
    /// JSON string of the metadata object (or null)
    pub metadata: Option<String>,
}

/// JS-facing wrapper for Commit.
#[napi(object)]
pub struct JsCommit {
    pub hash: String,
    pub tree_hash: String,
    pub parent_hashes: Vec<String>,
    pub message: String,
    pub author: String,
    pub timestamp: String,
    pub action_type: String,
}

/// A single entry in a state diff exposed to JS.
#[napi(object)]
pub struct JsDiffEntry {
    pub path: Vec<String>,
    pub change_type: String,
    pub old_value: Option<String>,
    pub new_value: Option<String>,
}

/// The diff between two commits exposed to JS.
#[napi(object)]
pub struct JsStateDiff {
    pub base_hash: String,
    pub target_hash: String,
    pub entries: Vec<JsDiffEntry>,
}

// ---- Conversion helpers ----

impl From<AgentState> for JsAgentState {
    fn from(s: AgentState) -> Self {
        let metadata_str = serde_json::to_string(&s.metadata).unwrap_or_else(|_| "{}".into());
        JsAgentState {
            memory: serde_json::to_string(&s.memory).unwrap_or_else(|_| "{}".into()),
            world_state: serde_json::to_string(&s.world_state).unwrap_or_else(|_| "{}".into()),
            timestamp: s.timestamp.to_rfc3339(),
            cost: s.cost,
            metadata: if metadata_str == "{}" {
                None
            } else {
                Some(metadata_str)
            },
        }
    }
}

impl From<(String, Commit)> for JsCommit {
    fn from((hash, c): (String, Commit)) -> Self {
        JsCommit {
            hash,
            tree_hash: c.tree_hash.0,
            parent_hashes: c.parent_hashes.into_iter().map(|h| h.0).collect(),
            message: c.message,
            author: c.author,
            timestamp: c.timestamp.to_rfc3339(),
            action_type: c.action_type.to_string(),
        }
    }
}

impl From<DiffEntry> for JsDiffEntry {
    fn from(e: DiffEntry) -> Self {
        JsDiffEntry {
            path: e.path,
            change_type: format!("{:?}", e.change_type).to_lowercase(),
            old_value: e.old_value.map(|v| v.to_string()),
            new_value: e.new_value.map(|v| v.to_string()),
        }
    }
}

impl From<StateDiff> for JsStateDiff {
    fn from(d: StateDiff) -> Self {
        JsStateDiff {
            base_hash: d.base_hash,
            target_hash: d.target_hash,
            entries: d.entries.into_iter().map(JsDiffEntry::from).collect(),
        }
    }
}
