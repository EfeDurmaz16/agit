use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;

use crate::blast_radius::BlastRadiusReport;
use crate::error::{AgitError, Result};
use crate::state::AgentState;
use crate::storage::StorageBackend;
use crate::types::ActionType;

/// Status of a pending approval request.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum ApprovalStatus {
    Pending {
        requested_at: DateTime<Utc>,
        expires_at: DateTime<Utc>,
    },
    Approved {
        by: String,
        at: DateTime<Utc>,
    },
    Rejected {
        by: String,
        reason: String,
        at: DateTime<Utc>,
    },
}

/// A pending approval entry for a high-risk commit.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingApproval {
    pub id: String,
    pub agent_id: String,
    pub state: AgentState,
    pub message: String,
    pub action_type: ActionType,
    pub blast_radius: BlastRadiusReport,
    pub status: ApprovalStatus,
}

/// In-memory store for approval requests.
pub struct ApprovalStore {
    _storage: Box<dyn StorageBackend>,
    pending: Mutex<Vec<PendingApproval>>,
}

impl ApprovalStore {
    /// Create a new approval store backed by the given storage.
    pub async fn new(_storage: Box<dyn StorageBackend>) -> Result<Self> {
        Ok(Self {
            _storage,
            pending: Mutex::new(Vec::new()),
        })
    }

    /// Request approval for a high-risk action. Returns the approval ID (format: "apr-{uuid}").
    pub async fn request(
        &self,
        agent_id: String,
        state: AgentState,
        message: String,
        action_type: ActionType,
        blast_radius: BlastRadiusReport,
        ttl_seconds: u64,
    ) -> Result<String> {
        let id = format!("apr-{}", uuid::Uuid::new_v4());
        let now = Utc::now();
        let expires_at = now + Duration::seconds(ttl_seconds as i64);

        let approval = PendingApproval {
            id: id.clone(),
            agent_id,
            state,
            message,
            action_type,
            blast_radius,
            status: ApprovalStatus::Pending {
                requested_at: now,
                expires_at,
            },
        };

        let mut pending = self.pending.lock().await;
        pending.push(approval);
        Ok(id)
    }

    /// Approve a pending request. Removes it from the pending list and returns it with Approved status.
    pub async fn approve(&self, approval_id: &str, by: String) -> Result<PendingApproval> {
        let mut pending = self.pending.lock().await;
        let pos = pending
            .iter()
            .position(|a| a.id == approval_id)
            .ok_or_else(|| {
                AgitError::InvalidArgument(format!("approval not found: {}", approval_id))
            })?;

        let mut approval = pending.remove(pos);
        approval.status = ApprovalStatus::Approved {
            by,
            at: Utc::now(),
        };
        Ok(approval)
    }

    /// Reject a pending request. Removes it from the pending list and returns it with Rejected status.
    pub async fn reject(
        &self,
        approval_id: &str,
        by: String,
        reason: String,
    ) -> Result<PendingApproval> {
        let mut pending = self.pending.lock().await;
        let pos = pending
            .iter()
            .position(|a| a.id == approval_id)
            .ok_or_else(|| {
                AgitError::InvalidArgument(format!("approval not found: {}", approval_id))
            })?;

        let mut approval = pending.remove(pos);
        approval.status = ApprovalStatus::Rejected {
            by,
            reason,
            at: Utc::now(),
        };
        Ok(approval)
    }

    /// List all pending approval requests.
    pub async fn list_pending(&self) -> Result<Vec<PendingApproval>> {
        let pending = self.pending.lock().await;
        let result = pending
            .iter()
            .filter(|a| matches!(a.status, ApprovalStatus::Pending { .. }))
            .cloned()
            .collect();
        Ok(result)
    }

    /// Get a specific approval by ID.
    pub async fn get(&self, approval_id: &str) -> Result<PendingApproval> {
        let pending = self.pending.lock().await;
        pending
            .iter()
            .find(|a| a.id == approval_id)
            .cloned()
            .ok_or_else(|| {
                AgitError::InvalidArgument(format!("approval not found: {}", approval_id))
            })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::blast_radius::{BlastRadiusReport, RiskLevel};
    use crate::storage::sqlite::SqliteStorage;
    use crate::types::ActionType;
    use serde_json::json;

    fn test_blast_radius() -> BlastRadiusReport {
        BlastRadiusReport {
            risk_level: RiskLevel::High,
            score: 0.6,
            changed_paths: vec!["memory.config".to_string()],
            keys_added: 0,
            keys_removed: 2,
            keys_modified: 1,
            total_keys: 10,
            change_ratio: 0.3,
        }
    }

    #[tokio::test]
    async fn test_request_and_list_pending() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let store = ApprovalStore::new(Box::new(storage)).await.unwrap();

        let state = AgentState::new(json!({"key": "value"}), json!({}));
        let id = store
            .request(
                "agent-1".to_string(),
                state,
                "deploy to prod".to_string(),
                ActionType::ToolCall,
                test_blast_radius(),
                300,
            )
            .await
            .unwrap();

        assert!(id.starts_with("apr-"));

        let pending = store.list_pending().await.unwrap();
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].agent_id, "agent-1");
    }

    #[tokio::test]
    async fn test_approve_removes_from_pending() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let store = ApprovalStore::new(Box::new(storage)).await.unwrap();

        let state = AgentState::new(json!({"key": "value"}), json!({}));
        let id = store
            .request(
                "agent-1".to_string(),
                state,
                "deploy to prod".to_string(),
                ActionType::ToolCall,
                test_blast_radius(),
                300,
            )
            .await
            .unwrap();

        let approved = store.approve(&id, "admin".to_string()).await.unwrap();
        assert_eq!(approved.agent_id, "agent-1");
        assert!(matches!(approved.status, ApprovalStatus::Approved { .. }));

        let pending = store.list_pending().await.unwrap();
        assert!(pending.is_empty());
    }

    #[tokio::test]
    async fn test_reject_removes_from_pending() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let store = ApprovalStore::new(Box::new(storage)).await.unwrap();

        let state = AgentState::new(json!({"key": "value"}), json!({}));
        let id = store
            .request(
                "agent-1".to_string(),
                state,
                "deploy to prod".to_string(),
                ActionType::ToolCall,
                test_blast_radius(),
                300,
            )
            .await
            .unwrap();

        let rejected = store
            .reject(&id, "admin".to_string(), "too risky".to_string())
            .await
            .unwrap();
        assert!(matches!(rejected.status, ApprovalStatus::Rejected { .. }));

        let pending = store.list_pending().await.unwrap();
        assert!(pending.is_empty());
    }

    #[tokio::test]
    async fn test_approve_nonexistent_returns_error() {
        let storage = SqliteStorage::new(":memory:").await.unwrap();
        let store = ApprovalStore::new(Box::new(storage)).await.unwrap();

        let result = store.approve("nonexistent", "admin".to_string()).await;
        assert!(result.is_err());
    }
}
