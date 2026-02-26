use pyo3::prelude::*;

#[pymodule]
fn agit_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", "0.1.0")?;
    m.add_class::<PyRepository>()?;
    m.add_class::<PyAgentState>()?;
    m.add_class::<PyCommit>()?;
    m.add_class::<PyStateDiff>()?;
    m.add_class::<PyDiffEntry>()?;
    Ok(())
}

mod convert;
mod repository;
mod types;

pub use repository::PyRepository;
pub use types::{PyAgentState, PyCommit, PyDiffEntry, PyStateDiff};
