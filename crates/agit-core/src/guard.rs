use async_trait::async_trait;
use serde_json::Value;

use crate::error::AgitError;
use crate::state::AgentState;
use crate::types::ActionType;

/// The decision returned by a guard after inspecting a commit context.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GuardDecision {
    /// The commit is allowed to proceed.
    Allow,
    /// The commit may proceed, but a warning is attached.
    Warn(String),
    /// The commit is blocked with the given reason.
    Block(String),
}

/// Context passed to each guard for evaluation.
#[derive(Debug, Clone)]
pub struct GuardContext {
    /// The new state being committed.
    pub new_state: AgentState,
    /// The previous state (if any).
    pub previous_state: Option<AgentState>,
    /// The commit message.
    pub message: String,
    /// The type of action that produced this commit.
    pub action_type: ActionType,
    /// The agent identifier.
    pub agent_id: String,
    /// The branch being committed to (if any).
    pub branch: Option<String>,
    /// Arbitrary metadata attached to the commit.
    pub metadata: serde_json::Map<String, Value>,
}

/// A guard that inspects a commit context and returns a decision.
///
/// Implement this trait to create custom pre-commit checks such as
/// secret detection, cost-limit enforcement, or schema validation.
#[async_trait]
pub trait CommitGuard: Send + Sync {
    /// A human-readable name for this guard (used in error messages).
    fn name(&self) -> &str;

    /// Evaluate the commit context and return a decision.
    async fn check(&self, context: &GuardContext) -> GuardDecision;
}

/// A chain of guards that are evaluated in order.
///
/// Evaluation stops at the first `Block` decision. Warnings are
/// accumulated and returned alongside the `Ok` result.
pub struct GuardChain {
    guards: Vec<Box<dyn CommitGuard>>,
}

impl GuardChain {
    /// Create an empty guard chain.
    pub fn new() -> Self {
        Self {
            guards: Vec::new(),
        }
    }

    /// Add a guard to the chain.
    pub fn add(&mut self, guard: Box<dyn CommitGuard>) {
        self.guards.push(guard);
    }

    /// Returns `true` if the chain has no guards.
    pub fn is_empty(&self) -> bool {
        self.guards.is_empty()
    }

    /// Evaluate all guards in order.
    ///
    /// Returns `Ok(warnings)` if all guards allow or warn, where `warnings`
    /// is the list of warning messages from `Warn` decisions.
    ///
    /// Returns `Err(AgitError::GuardBlocked)` at the first `Block` decision.
    pub async fn evaluate(&self, context: &GuardContext) -> crate::Result<Vec<String>> {
        let mut warnings = Vec::new();

        for guard in &self.guards {
            match guard.check(context).await {
                GuardDecision::Allow => {}
                GuardDecision::Warn(msg) => {
                    warnings.push(msg);
                }
                GuardDecision::Block(reason) => {
                    return Err(AgitError::GuardBlocked {
                        guard: guard.name().to_string(),
                        reason,
                    });
                }
            }
        }

        Ok(warnings)
    }
}

impl Default for GuardChain {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // ---- test helper guards ----

    struct AlwaysAllowGuard;

    #[async_trait]
    impl CommitGuard for AlwaysAllowGuard {
        fn name(&self) -> &str {
            "always-allow"
        }

        async fn check(&self, _context: &GuardContext) -> GuardDecision {
            GuardDecision::Allow
        }
    }

    struct AlwaysBlockGuard;

    #[async_trait]
    impl CommitGuard for AlwaysBlockGuard {
        fn name(&self) -> &str {
            "always-block"
        }

        async fn check(&self, _context: &GuardContext) -> GuardDecision {
            GuardDecision::Block("blocked by policy".to_string())
        }
    }

    fn make_context() -> GuardContext {
        GuardContext {
            new_state: AgentState::new(json!({}), json!({})),
            previous_state: None,
            message: "test commit".to_string(),
            action_type: ActionType::ToolCall,
            agent_id: "agent-1".to_string(),
            branch: Some("main".to_string()),
            metadata: serde_json::Map::new(),
        }
    }

    #[tokio::test]
    async fn test_empty_chain_allows() {
        let chain = GuardChain::new();
        assert!(chain.is_empty());
        let result = chain.evaluate(&make_context()).await;
        assert!(result.is_ok());
        assert!(result.unwrap().is_empty());
    }

    #[tokio::test]
    async fn test_allow_guard_passes() {
        let mut chain = GuardChain::new();
        chain.add(Box::new(AlwaysAllowGuard));
        let result = chain.evaluate(&make_context()).await;
        assert!(result.is_ok());
        assert!(result.unwrap().is_empty());
    }

    #[tokio::test]
    async fn test_block_guard_returns_error() {
        let mut chain = GuardChain::new();
        chain.add(Box::new(AlwaysBlockGuard));
        let result = chain.evaluate(&make_context()).await;
        assert!(result.is_err());
        match result.unwrap_err() {
            AgitError::GuardBlocked { guard, reason } => {
                assert_eq!(guard, "always-block");
                assert_eq!(reason, "blocked by policy");
            }
            other => panic!("expected GuardBlocked, got: {:?}", other),
        }
    }

    #[tokio::test]
    async fn test_chain_stops_at_first_block() {
        let mut chain = GuardChain::new();
        chain.add(Box::new(AlwaysAllowGuard));
        chain.add(Box::new(AlwaysBlockGuard));
        chain.add(Box::new(AlwaysAllowGuard));
        let result = chain.evaluate(&make_context()).await;
        assert!(result.is_err());
        match result.unwrap_err() {
            AgitError::GuardBlocked { guard, .. } => {
                assert_eq!(guard, "always-block");
            }
            other => panic!("expected GuardBlocked, got: {:?}", other),
        }
    }
}
