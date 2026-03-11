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

    #[error("invalid operation: {0}")]
    InvalidOperation(String),

    #[error("no commits yet on this branch")]
    NoCommits,

    #[error("encryption error: {0}")]
    EncryptionError(String),

    #[error("depth limit exceeded: {0}")]
    DepthLimitExceeded(String),

    #[error("guard blocked: [{guard}] {reason}")]
    GuardBlocked { guard: String, reason: String },

    #[error("approval required [{approval_id}]: {reason}")]
    ApprovalRequired { approval_id: String, reason: String },
}

pub type Result<T> = std::result::Result<T, AgitError>;

impl From<serde_json::Error> for AgitError {
    fn from(e: serde_json::Error) -> Self {
        AgitError::Serialization(e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn guard_blocked_display() {
        let err = AgitError::GuardBlocked {
            guard: "no-secrets".to_string(),
            reason: "found API key in source".to_string(),
        };
        assert_eq!(
            err.to_string(),
            "guard blocked: [no-secrets] found API key in source"
        );
    }

    #[test]
    fn approval_required_display() {
        let err = AgitError::ApprovalRequired {
            approval_id: "apr-12345".to_string(),
            reason: "changes to production config require approval".to_string(),
        };
        assert_eq!(
            err.to_string(),
            "approval required [apr-12345]: changes to production config require approval"
        );
    }
}

