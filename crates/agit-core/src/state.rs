use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::types::ChangeType;

/// Full agent state at a point in time.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentState {
    pub memory: Value,
    pub world_state: Value,
    pub timestamp: DateTime<Utc>,
    #[serde(default)]
    pub cost: f64,
    #[serde(default)]
    pub metadata: serde_json::Map<String, Value>,
}

impl AgentState {
    pub fn new(memory: Value, world_state: Value) -> Self {
        AgentState {
            memory,
            world_state,
            timestamp: Utc::now(),
            cost: 0.0,
            metadata: serde_json::Map::new(),
        }
    }

    /// Convert to a flat JSON value for hashing and storage.
    pub fn to_value(&self) -> Value {
        serde_json::to_value(self).unwrap_or(Value::Null)
    }
}

/// A single entry in a state diff.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffEntry {
    pub path: Vec<String>,
    pub change_type: ChangeType,
    pub old_value: Option<Value>,
    pub new_value: Option<Value>,
}

/// The diff between two agent states.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StateDiff {
    pub base_hash: String,
    pub target_hash: String,
    pub entries: Vec<DiffEntry>,
}

/// A conflict encountered during three-way merge.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MergeConflict {
    pub path: Vec<String>,
    pub base_value: Option<Value>,
    pub ours_value: Option<Value>,
    pub theirs_value: Option<Value>,
}

/// Compute a recursive diff between two JSON values.
pub fn diff_states(base: &AgentState, target: &AgentState) -> StateDiff {
    let mut entries = Vec::new();
    let base_val = base.to_value();
    let target_val = target.to_value();
    diff_values(&base_val, &target_val, &mut vec![], &mut entries);
    StateDiff {
        base_hash: String::new(),
        target_hash: String::new(),
        entries,
    }
}

fn diff_values(
    base: &Value,
    target: &Value,
    path: &mut Vec<String>,
    entries: &mut Vec<DiffEntry>,
) {
    if base == target {
        return;
    }

    match (base, target) {
        (Value::Object(base_map), Value::Object(target_map)) => {
            // Check for removed and changed keys
            for (key, base_val) in base_map {
                path.push(key.clone());
                if let Some(target_val) = target_map.get(key) {
                    diff_values(base_val, target_val, path, entries);
                } else {
                    entries.push(DiffEntry {
                        path: path.clone(),
                        change_type: ChangeType::Removed,
                        old_value: Some(base_val.clone()),
                        new_value: None,
                    });
                }
                path.pop();
            }
            // Check for added keys
            for (key, target_val) in target_map {
                if !base_map.contains_key(key) {
                    path.push(key.clone());
                    entries.push(DiffEntry {
                        path: path.clone(),
                        change_type: ChangeType::Added,
                        old_value: None,
                        new_value: Some(target_val.clone()),
                    });
                    path.pop();
                }
            }
        }
        _ => {
            // Leaf value changed
            entries.push(DiffEntry {
                path: path.clone(),
                change_type: ChangeType::Changed,
                old_value: Some(base.clone()),
                new_value: Some(target.clone()),
            });
        }
    }
}

/// Three-way merge of JSON values. Returns merged result and any conflicts.
pub fn three_way_merge(
    base: &Value,
    ours: &Value,
    theirs: &Value,
) -> (Value, Vec<MergeConflict>) {
    let mut conflicts = Vec::new();
    let merged = merge_values(base, ours, theirs, &mut vec![], &mut conflicts);
    (merged, conflicts)
}

fn merge_values(
    base: &Value,
    ours: &Value,
    theirs: &Value,
    path: &mut Vec<String>,
    conflicts: &mut Vec<MergeConflict>,
) -> Value {
    // If both sides are the same, no conflict
    if ours == theirs {
        return ours.clone();
    }

    // If only one side changed from base, take that side
    if ours == base {
        return theirs.clone();
    }
    if theirs == base {
        return ours.clone();
    }

    // Both sides changed differently from base
    match (base, ours, theirs) {
        (Value::Object(base_map), Value::Object(ours_map), Value::Object(theirs_map)) => {
            let mut result = serde_json::Map::new();
            let mut all_keys: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
            all_keys.extend(base_map.keys().cloned());
            all_keys.extend(ours_map.keys().cloned());
            all_keys.extend(theirs_map.keys().cloned());

            for key in all_keys {
                path.push(key.clone());
                let base_val = base_map.get(&key).unwrap_or(&Value::Null);
                let ours_val = ours_map.get(&key).unwrap_or(&Value::Null);
                let theirs_val = theirs_map.get(&key).unwrap_or(&Value::Null);
                let merged = merge_values(base_val, ours_val, theirs_val, path, conflicts);
                if merged != Value::Null || ours_map.contains_key(&key) || theirs_map.contains_key(&key) {
                    result.insert(key, merged);
                }
                path.pop();
            }
            Value::Object(result)
        }
        _ => {
            // Leaf conflict: both changed differently
            conflicts.push(MergeConflict {
                path: path.clone(),
                base_value: Some(base.clone()),
                ours_value: Some(ours.clone()),
                theirs_value: Some(theirs.clone()),
            });
            // Default: take ours
            ours.clone()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_diff_added() {
        let base = AgentState::new(json!({}), json!({}));
        let target = AgentState::new(json!({"key": "value"}), json!({}));
        let diff = diff_states(&base, &target);
        let memory_entries: Vec<_> = diff.entries.iter()
            .filter(|e| e.path.first().map(|s| s.as_str()) == Some("memory"))
            .collect();
        assert!(!memory_entries.is_empty());
    }

    #[test]
    fn test_diff_removed() {
        let base = AgentState::new(json!({"key": "value"}), json!({}));
        let target = AgentState::new(json!({}), json!({}));
        let diff = diff_states(&base, &target);
        let removed: Vec<_> = diff.entries.iter()
            .filter(|e| e.change_type == ChangeType::Removed)
            .collect();
        assert!(!removed.is_empty());
    }

    #[test]
    fn test_diff_changed() {
        let base = AgentState::new(json!({"counter": 1}), json!({}));
        let target = AgentState::new(json!({"counter": 2}), json!({}));
        let diff = diff_states(&base, &target);
        let changed: Vec<_> = diff.entries.iter()
            .filter(|e| e.change_type == ChangeType::Changed)
            .collect();
        assert!(!changed.is_empty());
    }

    #[test]
    fn test_diff_no_changes() {
        let state = AgentState::new(json!({"x": 1}), json!({"y": 2}));
        let diff = diff_states(&state, &state);
        assert!(diff.entries.is_empty());
    }

    #[test]
    fn test_three_way_merge_no_conflict() {
        let base = json!({"a": 1, "b": 2});
        let ours = json!({"a": 10, "b": 2});    // changed a
        let theirs = json!({"a": 1, "b": 20});   // changed b
        let (merged, conflicts) = three_way_merge(&base, &ours, &theirs);
        assert!(conflicts.is_empty());
        assert_eq!(merged, json!({"a": 10, "b": 20}));
    }

    #[test]
    fn test_three_way_merge_conflict() {
        let base = json!({"a": 1});
        let ours = json!({"a": 2});
        let theirs = json!({"a": 3});
        let (merged, conflicts) = three_way_merge(&base, &ours, &theirs);
        assert_eq!(conflicts.len(), 1);
        assert_eq!(merged, json!({"a": 2})); // defaults to ours
    }

    #[test]
    fn test_three_way_merge_both_same() {
        let base = json!({"a": 1});
        let ours = json!({"a": 2});
        let theirs = json!({"a": 2});
        let (merged, conflicts) = three_way_merge(&base, &ours, &theirs);
        assert!(conflicts.is_empty());
        assert_eq!(merged, json!({"a": 2}));
    }
}
