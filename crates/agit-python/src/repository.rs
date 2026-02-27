use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::sync::OnceLock;

use agit_core::types::MergeStrategy;
use agit_core::{Repository, SqliteStorage};

use crate::convert::{agent_state_to_py, commit_to_py, diff_to_py, py_to_agent_state};
use crate::types::{PyAgentState, PyCommit, PyStateDiff};

/// Shared Tokio runtime across all PyRepository instances.
/// Avoids the overhead of creating a new runtime per repository.
static SHARED_RUNTIME: OnceLock<tokio::runtime::Runtime> = OnceLock::new();

fn get_runtime() -> &'static tokio::runtime::Runtime {
    SHARED_RUNTIME.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .expect("failed to create shared Tokio runtime")
    })
}

/// Convert an agit_core::AgitError to a Python RuntimeError.
fn agit_err_to_py(e: agit_core::AgitError) -> PyErr {
    PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())
}

/// Parse a merge strategy string, defaulting to ThreeWay.
fn parse_strategy(s: Option<&str>) -> MergeStrategy {
    match s {
        Some("ours") => MergeStrategy::Ours,
        Some("theirs") => MergeStrategy::Theirs,
        _ => MergeStrategy::ThreeWay,
    }
}

/// Parse an action type string, defaulting to Checkpoint.
fn parse_action_type(s: Option<&str>) -> agit_core::types::ActionType {
    use agit_core::types::ActionType;
    match s {
        Some("tool_call") => ActionType::ToolCall,
        Some("llm_response") => ActionType::LlmResponse,
        Some("user_input") => ActionType::UserInput,
        Some("system_event") => ActionType::SystemEvent,
        Some("retry") => ActionType::Retry,
        Some("rollback") => ActionType::Rollback,
        Some("merge") => ActionType::Merge,
        Some("checkpoint") | None => ActionType::Checkpoint,
        Some(other) => ActionType::Custom(other.to_string()),
    }
}

/// Python wrapper for the agit Repository.
#[pyclass(name = "Repository")]
pub struct PyRepository {
    inner: Option<Repository>,
}

#[pymethods]
impl PyRepository {
    /// Open or initialize a repository at the given filesystem path.
    /// The path is used as the SQLite database file location.
    #[new]
    #[pyo3(signature = (path, agent_id=None))]
    fn new(path: &str, agent_id: Option<&str>) -> PyResult<Self> {
        let runtime = get_runtime();

        let repo = runtime.block_on(async {
            let db_path = if path.ends_with(".db") || path == ":memory:" {
                path.to_string()
            } else {
                format!("{}/agit.db", path.trim_end_matches('/'))
            };
            let storage = SqliteStorage::new(&db_path)
                .await
                .map_err(agit_err_to_py)?;
            Repository::init(Box::new(storage))
                .await
                .map_err(agit_err_to_py)
        })?;

        Ok(PyRepository {
            inner: Some(repo),
        })
    }

    /// Commit an AgentState, returning the commit hash string.
    #[pyo3(signature = (state, message, action_type=None))]
    fn commit(
        &mut self,
        state: &PyAgentState,
        message: &str,
        action_type: Option<&str>,
    ) -> PyResult<String> {
        let core_state = py_to_agent_state(state);
        let action = parse_action_type(action_type);
        let repo = self
            .inner
            .as_mut()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        get_runtime()
            .block_on(repo.commit(&core_state, message, action))
            .map(|h| h.0)
            .map_err(agit_err_to_py)
    }

    /// Create a new branch. Optionally specify a source ref; defaults to HEAD.
    #[pyo3(signature = (name, from_ref=None))]
    fn branch(&mut self, name: &str, from_ref: Option<&str>) -> PyResult<()> {
        let repo = self
            .inner
            .as_mut()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        get_runtime()
            .block_on(repo.branch(name, from_ref))
            .map_err(agit_err_to_py)
    }

    /// Checkout a branch or commit hash, returning the AgentState at that point.
    fn checkout(&mut self, target: &str) -> PyResult<PyAgentState> {
        let repo = self
            .inner
            .as_mut()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        let state = get_runtime()
            .block_on(repo.checkout(target))
            .map_err(agit_err_to_py)?;
        Ok(agent_state_to_py(&state))
    }

    /// Compute the diff between two commit hashes.
    fn diff(&self, hash1: &str, hash2: &str) -> PyResult<PyStateDiff> {
        let repo = self
            .inner
            .as_ref()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        let diff = get_runtime()
            .block_on(repo.diff(hash1, hash2))
            .map_err(agit_err_to_py)?;
        Ok(diff_to_py(&diff))
    }

    /// Merge a branch into the current branch. Returns the merge commit hash.
    /// strategy: "ours" | "theirs" | "three_way" (default)
    #[pyo3(signature = (branch, strategy=None))]
    fn merge(&mut self, branch: &str, strategy: Option<&str>) -> PyResult<String> {
        let strat = parse_strategy(strategy);
        let repo = self
            .inner
            .as_mut()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        get_runtime()
            .block_on(repo.merge(branch, strat))
            .map(|h| h.0)
            .map_err(agit_err_to_py)
    }

    /// Return commit history as a list of PyCommit objects.
    #[pyo3(signature = (branch=None, limit=None))]
    fn log(&self, branch: Option<&str>, limit: Option<usize>) -> PyResult<Vec<PyCommit>> {
        let n = limit.unwrap_or(100);
        let repo = self
            .inner
            .as_ref()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        let commits = get_runtime()
            .block_on(repo.log(branch, n))
            .map_err(agit_err_to_py)?;
        Ok(commits.iter().map(commit_to_py).collect())
    }

    /// Revert to a previous commit hash, creating a new revert commit.
    fn revert(&mut self, to_hash: &str) -> PyResult<PyAgentState> {
        let repo = self
            .inner
            .as_mut()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        let state = get_runtime()
            .block_on(repo.revert(to_hash))
            .map_err(agit_err_to_py)?;
        Ok(agent_state_to_py(&state))
    }

    /// Retrieve the AgentState stored at a specific commit hash.
    fn get_state(&self, hash: &str) -> PyResult<PyAgentState> {
        let repo = self
            .inner
            .as_ref()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        let state = get_runtime()
            .block_on(repo.get_state(hash))
            .map_err(agit_err_to_py)?;
        Ok(agent_state_to_py(&state))
    }

    /// Return the current branch name, or None if in detached HEAD mode.
    fn current_branch(&self) -> Option<String> {
        self.inner
            .as_ref()
            .and_then(|r| r.current_branch().map(|s| s.to_string()))
    }

    /// Return a Python dict mapping branch names to their tip commit hashes.
    fn list_branches(&self, py: Python<'_>) -> PyResult<PyObject> {
        let repo = self
            .inner
            .as_ref()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        let branches = repo.list_branches();
        let d = PyDict::new(py);
        for (name, hash) in branches {
            d.set_item(name, &hash.0)?;
        }
        Ok(d.into())
    }

    /// Return the current HEAD commit hash.
    fn head(&self) -> PyResult<String> {
        let repo = self
            .inner
            .as_ref()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        repo.head().map(|h| h.0).map_err(agit_err_to_py)
    }

    /// Delete a branch.
    fn delete_branch(&mut self, name: &str) -> PyResult<()> {
        let repo = self
            .inner
            .as_mut()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        get_runtime()
            .block_on(repo.delete_branch(name))
            .map_err(agit_err_to_py)
    }

    /// Set an encryption key to encrypt/decrypt agent state fields at rest.
    fn set_encryption_key(&mut self, key: &str) -> PyResult<()> {
        #[cfg(feature = "encryption")]
        {
            let repo = self.inner.as_mut().ok_or_else(|| {
                PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed")
            })?;
            repo.set_encryption_key(key);
            Ok(())
        }
        #[cfg(not(feature = "encryption"))]
        {
            Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "encryption feature not enabled in agit-core",
            ))
        }
    }

    /// Run garbage collection to remove unreachable objects.
    fn gc(&self, py: Python<'_>, keep_last_n: usize) -> PyResult<PyObject> {
        let repo = self
            .inner
            .as_ref()
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("repository closed"))?;
        let result = get_runtime()
            .block_on(repo.gc(keep_last_n))
            .map_err(agit_err_to_py)?;

        let d = PyDict::new(py);
        d.set_item("objects_before", result.objects_before)?;
        d.set_item("objects_removed", result.objects_removed)?;
        d.set_item("objects_after", result.objects_after)?;
        Ok(d.into())
    }

    fn __repr__(&self) -> String {
        match &self.inner {
            Some(repo) => format!(
                "Repository(branch={:?})",
                repo.current_branch().unwrap_or("<detached>")
            ),
            None => "Repository(<closed>)".to_string(),
        }
    }
}
