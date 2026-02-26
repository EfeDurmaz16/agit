use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::convert::json_to_py_object;

/// Python wrapper for AgentState.
/// Stores JSON-serialized fields internally for easy FFI crossing.
#[pyclass(name = "AgentState")]
#[derive(Clone)]
pub struct PyAgentState {
    pub memory_json: String,
    pub world_state_json: String,
    pub timestamp: String,
    pub cost: f64,
    pub metadata_json: String,
}

#[pymethods]
impl PyAgentState {
    #[new]
    #[pyo3(signature = (memory=None, world_state=None, cost=0.0))]
    fn new(memory: Option<&str>, world_state: Option<&str>, cost: f64) -> Self {
        PyAgentState {
            memory_json: memory.unwrap_or("{}").to_string(),
            world_state_json: world_state.unwrap_or("{}").to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            cost,
            metadata_json: "{}".to_string(),
        }
    }

    /// Return the memory field as a Python dict.
    #[getter]
    fn memory(&self, py: Python<'_>) -> PyResult<PyObject> {
        let value: serde_json::Value = serde_json::from_str(&self.memory_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(json_to_py_object(py, &value))
    }

    /// Return the world_state field as a Python dict.
    #[getter]
    fn world_state(&self, py: Python<'_>) -> PyResult<PyObject> {
        let value: serde_json::Value = serde_json::from_str(&self.world_state_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(json_to_py_object(py, &value))
    }

    #[getter]
    fn timestamp(&self) -> &str {
        &self.timestamp
    }

    #[getter]
    fn cost(&self) -> f64 {
        self.cost
    }

    /// Return a Python dict representation of the full state.
    fn to_dict(&self, py: Python<'_>) -> PyResult<PyObject> {
        let d = PyDict::new(py);
        let mem: serde_json::Value = serde_json::from_str(&self.memory_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        let ws: serde_json::Value = serde_json::from_str(&self.world_state_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        let meta: serde_json::Value = serde_json::from_str(&self.metadata_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        d.set_item("memory", json_to_py_object(py, &mem))?;
        d.set_item("world_state", json_to_py_object(py, &ws))?;
        d.set_item("timestamp", self.timestamp.clone())?;
        d.set_item("cost", self.cost)?;
        d.set_item("metadata", json_to_py_object(py, &meta))?;
        Ok(d.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "AgentState(timestamp={}, cost={:.4})",
            self.timestamp, self.cost
        )
    }
}

/// Python wrapper for a Commit object.
#[pyclass(name = "Commit")]
#[derive(Clone)]
pub struct PyCommit {
    pub hash: String,
    pub tree_hash: String,
    pub parent_hashes: Vec<String>,
    pub message: String,
    pub author: String,
    pub timestamp: String,
    pub action_type: String,
    pub metadata_json: String,
}

#[pymethods]
impl PyCommit {
    #[getter]
    fn hash(&self) -> &str {
        &self.hash
    }

    #[getter]
    fn tree_hash(&self) -> &str {
        &self.tree_hash
    }

    #[getter]
    fn parent_hashes(&self) -> Vec<String> {
        self.parent_hashes.clone()
    }

    #[getter]
    fn message(&self) -> &str {
        &self.message
    }

    #[getter]
    fn author(&self) -> &str {
        &self.author
    }

    #[getter]
    fn timestamp(&self) -> &str {
        &self.timestamp
    }

    #[getter]
    fn action_type(&self) -> &str {
        &self.action_type
    }

    #[getter]
    fn metadata(&self, py: Python<'_>) -> PyResult<PyObject> {
        let value: serde_json::Value = serde_json::from_str(&self.metadata_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(json_to_py_object(py, &value))
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<PyObject> {
        let d = PyDict::new(py);
        let meta: serde_json::Value = serde_json::from_str(&self.metadata_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        d.set_item("hash", self.hash.clone())?;
        d.set_item("tree_hash", self.tree_hash.clone())?;
        d.set_item("parent_hashes", self.parent_hashes.clone())?;
        d.set_item("message", self.message.clone())?;
        d.set_item("author", self.author.clone())?;
        d.set_item("timestamp", self.timestamp.clone())?;
        d.set_item("action_type", self.action_type.clone())?;
        d.set_item("metadata", json_to_py_object(py, &meta))?;
        Ok(d.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "Commit(hash={}, message={:?}, author={})",
            &self.hash[..8.min(self.hash.len())],
            self.message,
            self.author,
        )
    }
}

/// Python wrapper for a single diff entry.
#[pyclass(name = "DiffEntry")]
#[derive(Clone)]
pub struct PyDiffEntry {
    pub path: Vec<String>,
    pub change_type: String,
    pub old_value_json: Option<String>,
    pub new_value_json: Option<String>,
}

#[pymethods]
impl PyDiffEntry {
    #[getter]
    fn path(&self) -> Vec<String> {
        self.path.clone()
    }

    #[getter]
    fn change_type(&self) -> &str {
        &self.change_type
    }

    #[getter]
    fn old_value(&self, py: Python<'_>) -> PyResult<PyObject> {
        match &self.old_value_json {
            Some(s) => {
                let v: serde_json::Value = serde_json::from_str(s)
                    .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
                Ok(json_to_py_object(py, &v))
            }
            None => Ok(py.None()),
        }
    }

    #[getter]
    fn new_value(&self, py: Python<'_>) -> PyResult<PyObject> {
        match &self.new_value_json {
            Some(s) => {
                let v: serde_json::Value = serde_json::from_str(s)
                    .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
                Ok(json_to_py_object(py, &v))
            }
            None => Ok(py.None()),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "DiffEntry(path={}, change_type={})",
            self.path.join("."),
            self.change_type
        )
    }
}

/// Python wrapper for a StateDiff between two commits.
#[pyclass(name = "StateDiff")]
#[derive(Clone)]
pub struct PyStateDiff {
    pub base_hash: String,
    pub target_hash: String,
    pub entries: Vec<PyDiffEntry>,
}

#[pymethods]
impl PyStateDiff {
    #[getter]
    fn base_hash(&self) -> &str {
        &self.base_hash
    }

    #[getter]
    fn target_hash(&self) -> &str {
        &self.target_hash
    }

    #[getter]
    fn entries(&self, py: Python<'_>) -> PyResult<PyObject> {
        let list = PyList::empty(py);
        for entry in &self.entries {
            list.append(Py::new(py, entry.clone())?)?;
        }
        Ok(list.into())
    }

    fn __len__(&self) -> usize {
        self.entries.len()
    }

    fn __repr__(&self) -> String {
        format!(
            "StateDiff(base={}, target={}, entries={})",
            &self.base_hash[..8.min(self.base_hash.len())],
            &self.target_hash[..8.min(self.target_hash.len())],
            self.entries.len()
        )
    }
}
