use serde::{Deserialize, Serialize};
use std::fmt;

/// A SHA-256 hash represented as a 64-character hex string.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Hash(pub String);

impl Hash {
    pub fn as_str(&self) -> &str {
        &self.0
    }

    /// Return a short prefix (first 8 chars) for display.
    pub fn short(&self) -> &str {
        &self.0[..8.min(self.0.len())]
    }
}

impl fmt::Display for Hash {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl From<String> for Hash {
    fn from(s: String) -> Self {
        Hash(s)
    }
}

impl From<&str> for Hash {
    fn from(s: &str) -> Self {
        Hash(s.to_string())
    }
}

/// Type of content-addressed object stored in the repository.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ObjectType {
    Blob,
    Commit,
}

impl fmt::Display for ObjectType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ObjectType::Blob => write!(f, "blob"),
            ObjectType::Commit => write!(f, "commit"),
        }
    }
}

/// The type of agent action that produced a commit.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionType {
    ToolCall,
    LlmResponse,
    UserInput,
    SystemEvent,
    Retry,
    Rollback,
    Merge,
    Checkpoint,
    Custom(String),
}

impl fmt::Display for ActionType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ActionType::ToolCall => write!(f, "tool_call"),
            ActionType::LlmResponse => write!(f, "llm_response"),
            ActionType::UserInput => write!(f, "user_input"),
            ActionType::SystemEvent => write!(f, "system_event"),
            ActionType::Retry => write!(f, "retry"),
            ActionType::Rollback => write!(f, "rollback"),
            ActionType::Merge => write!(f, "merge"),
            ActionType::Checkpoint => write!(f, "checkpoint"),
            ActionType::Custom(s) => write!(f, "custom:{}", s),
        }
    }
}

/// Strategy for merging two branches.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MergeStrategy {
    /// Use the target branch state for any conflicts.
    Ours,
    /// Use the source branch state for any conflicts.
    Theirs,
    /// Attempt automatic three-way merge, fail on conflicts.
    ThreeWay,
}

/// Type of change in a diff entry.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeType {
    Added,
    Removed,
    Changed,
}
