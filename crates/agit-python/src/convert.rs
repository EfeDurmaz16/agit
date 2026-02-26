use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString};
use serde_json::Value;

use agit_core::{AgentState, Commit, DiffEntry, StateDiff};

use crate::types::{PyAgentState, PyCommit, PyDiffEntry, PyStateDiff};

/// Recursively convert a Python dict/list/primitive to a serde_json::Value.
pub fn py_dict_to_json(dict: &Bound<'_, PyDict>) -> Value {
    let mut map = serde_json::Map::new();
    for (k, v) in dict.iter() {
        let key = k.str().map(|s| s.to_string()).unwrap_or_default();
        map.insert(key, py_any_to_json(&v));
    }
    Value::Object(map)
}

/// Convert any Python object to a serde_json::Value.
pub fn py_any_to_json(obj: &Bound<'_, PyAny>) -> Value {
    // None
    if obj.is_none() {
        return Value::Null;
    }
    // bool (must check before int, because bool is a subtype of int in Python)
    if let Ok(b) = obj.downcast::<PyBool>() {
        return Value::Bool(b.is_true());
    }
    // int
    if let Ok(i) = obj.downcast::<PyInt>() {
        if let Ok(n) = i.extract::<i64>() {
            return Value::Number(n.into());
        }
    }
    // float
    if let Ok(f) = obj.downcast::<PyFloat>() {
        if let Some(n) = serde_json::Number::from_f64(f.value()) {
            return Value::Number(n);
        }
        return Value::Null;
    }
    // str
    if let Ok(s) = obj.downcast::<PyString>() {
        return Value::String(s.to_string());
    }
    // dict
    if let Ok(d) = obj.downcast::<PyDict>() {
        return py_dict_to_json(d);
    }
    // list / tuple / any sequence
    if let Ok(lst) = obj.downcast::<PyList>() {
        let arr: Vec<Value> = lst.iter().map(|item| py_any_to_json(&item)).collect();
        return Value::Array(arr);
    }
    // fallback: try to extract as str repr
    Value::String(obj.str().map(|s| s.to_string()).unwrap_or_default())
}

/// Recursively convert a serde_json::Value to a Python object.
pub fn json_to_py_object(py: Python<'_>, value: &Value) -> PyObject {
    match value {
        Value::Null => py.None(),
        Value::Bool(b) => b.into_pyobject(py).unwrap().to_owned().into_any().unbind(),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.into_pyobject(py).unwrap().into_any().unbind()
            } else if let Some(f) = n.as_f64() {
                f.into_pyobject(py).unwrap().into_any().unbind()
            } else {
                py.None()
            }
        }
        Value::String(s) => s.into_pyobject(py).unwrap().into_any().unbind(),
        Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(json_to_py_object(py, item)).ok();
            }
            list.into()
        }
        Value::Object(map) => {
            let d = PyDict::new(py);
            for (k, v) in map {
                d.set_item(k, json_to_py_object(py, v)).ok();
            }
            d.into()
        }
    }
}

/// Convert an agit-core AgentState to its Python wrapper.
pub fn agent_state_to_py(state: &AgentState) -> PyAgentState {
    PyAgentState {
        memory_json: serde_json::to_string(&state.memory).unwrap_or_else(|_| "{}".to_string()),
        world_state_json: serde_json::to_string(&state.world_state)
            .unwrap_or_else(|_| "{}".to_string()),
        timestamp: state.timestamp.to_rfc3339(),
        cost: state.cost,
        metadata_json: serde_json::to_string(&state.metadata)
            .unwrap_or_else(|_| "{}".to_string()),
    }
}

/// Convert a Python AgentState wrapper back to an agit-core AgentState.
pub fn py_to_agent_state(py_state: &PyAgentState) -> agit_core::AgentState {
    let memory: Value =
        serde_json::from_str(&py_state.memory_json).unwrap_or(Value::Object(Default::default()));
    let world_state: Value = serde_json::from_str(&py_state.world_state_json)
        .unwrap_or(Value::Object(Default::default()));
    let metadata: serde_json::Map<String, Value> =
        serde_json::from_str(&py_state.metadata_json).unwrap_or_default();
    let timestamp = chrono::DateTime::parse_from_rfc3339(&py_state.timestamp)
        .map(|dt| dt.with_timezone(&chrono::Utc))
        .unwrap_or_else(|_| chrono::Utc::now());

    AgentState {
        memory,
        world_state,
        timestamp,
        cost: py_state.cost,
        metadata,
    }
}

/// Convert an agit-core Commit to its Python wrapper.
/// The commit hash must be pre-computed and passed separately.
pub fn commit_to_py(commit: &Commit) -> PyCommit {
    PyCommit {
        hash: commit.hash().0.clone(),
        tree_hash: commit.tree_hash.0.clone(),
        parent_hashes: commit.parent_hashes.iter().map(|h| h.0.clone()).collect(),
        message: commit.message.clone(),
        author: commit.author.clone(),
        timestamp: commit.timestamp.to_rfc3339(),
        action_type: commit.action_type.to_string(),
        metadata_json: serde_json::to_string(&commit.metadata)
            .unwrap_or_else(|_| "{}".to_string()),
    }
}

/// Convert a single agit-core DiffEntry to its Python wrapper.
fn diff_entry_to_py(entry: &DiffEntry) -> PyDiffEntry {
    PyDiffEntry {
        path: entry.path.clone(),
        change_type: match &entry.change_type {
            agit_core::types::ChangeType::Added => "added".to_string(),
            agit_core::types::ChangeType::Removed => "removed".to_string(),
            agit_core::types::ChangeType::Changed => "changed".to_string(),
        },
        old_value_json: entry
            .old_value
            .as_ref()
            .map(|v| serde_json::to_string(v).unwrap_or_default()),
        new_value_json: entry
            .new_value
            .as_ref()
            .map(|v| serde_json::to_string(v).unwrap_or_default()),
    }
}

/// Convert an agit-core StateDiff to its Python wrapper.
pub fn diff_to_py(diff: &StateDiff) -> PyStateDiff {
    PyStateDiff {
        base_hash: diff.base_hash.clone(),
        target_hash: diff.target_hash.clone(),
        entries: diff.entries.iter().map(diff_entry_to_py).collect(),
    }
}
