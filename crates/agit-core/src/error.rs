use thiserror::Error;

#[derive(Debug, Error)]
pub enum AgitError {
    #[error("object not found: {hash}")]
    ObjectNotFound { hash: String },

    #[error("ref not found: {name}")]
    RefNotFound { name: String },

    #[error("branch already exists: {name}")]
    BranchExists { name: String },

    #[error("branch not found: {name}")]
    BranchNotFound { name: String },

    #[error("merge conflict: {details}")]
    MergeConflict { details: String },

    #[error("detached HEAD: cannot perform operation requiring a branch")]
    DetachedHead,

    #[error("storage error: {0}")]
    Storage(String),

    #[error("serialization error: {0}")]
    Serialization(String),

    #[error("invalid argument: {0}")]
    InvalidArgument(String),

    #[error("no commits yet on this branch")]
    NoCommits,
}

pub type Result<T> = std::result::Result<T, AgitError>;

impl From<serde_json::Error> for AgitError {
    fn from(e: serde_json::Error) -> Self {
        AgitError::Serialization(e.to_string())
    }
}

