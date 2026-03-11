use async_trait::async_trait;
use serde_json::Value;

use crate::blast_radius::{analyze_blast_radius_opt, RiskLevel};
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

// ---------------------------------------------------------------------------
// Built-in guards
// ---------------------------------------------------------------------------

/// Blocks commits where the deletion ratio exceeds a configurable threshold.
///
/// For example, with a threshold of 0.5 a commit that removes more than 50%
/// of the existing keys will be blocked.
pub struct DestructiveActionGuard {
    /// Maximum allowed ratio of removed keys to total keys (0.0–1.0).
    deletion_threshold: f64,
}

impl DestructiveActionGuard {
    /// Create a new guard with the given deletion threshold.
    ///
    /// `deletion_threshold` is in the range `0.0..=1.0`; e.g. `0.5` means
    /// block when more than 50% of keys are deleted.
    pub fn new(deletion_threshold: f64) -> Self {
        Self { deletion_threshold }
    }
}

impl Default for DestructiveActionGuard {
    fn default() -> Self {
        Self::new(0.5)
    }
}

#[async_trait]
impl CommitGuard for DestructiveActionGuard {
    fn name(&self) -> &str {
        "destructive-action"
    }

    async fn check(&self, context: &GuardContext) -> GuardDecision {
        let report =
            analyze_blast_radius_opt(context.previous_state.as_ref(), &context.new_state);

        if report.total_keys == 0 {
            return GuardDecision::Allow;
        }

        let deletion_ratio = report.keys_removed as f64 / report.total_keys as f64;

        if deletion_ratio > self.deletion_threshold {
            GuardDecision::Block(format!(
                "Deletion ratio {:.0}% exceeds threshold {:.0}% ({} of {} keys removed)",
                deletion_ratio * 100.0,
                self.deletion_threshold * 100.0,
                report.keys_removed,
                report.total_keys,
            ))
        } else {
            GuardDecision::Allow
        }
    }
}

/// Blocks commits whose blast-radius risk level meets or exceeds a
/// configurable threshold.
///
/// For example, with a threshold of `RiskLevel::Critical` only critical-risk
/// commits are blocked; with `RiskLevel::High` both high and critical commits
/// are blocked.
pub struct BlastRadiusGuard {
    /// The minimum risk level that will cause the guard to block.
    block_threshold: RiskLevel,
}

impl BlastRadiusGuard {
    /// Create a new guard that blocks commits at or above `block_threshold`.
    pub fn new(block_threshold: RiskLevel) -> Self {
        Self { block_threshold }
    }
}

impl Default for BlastRadiusGuard {
    fn default() -> Self {
        Self::new(RiskLevel::Critical)
    }
}

#[async_trait]
impl CommitGuard for BlastRadiusGuard {
    fn name(&self) -> &str {
        "blast-radius"
    }

    async fn check(&self, context: &GuardContext) -> GuardDecision {
        let report =
            analyze_blast_radius_opt(context.previous_state.as_ref(), &context.new_state);

        if report.risk_level >= self.block_threshold {
            GuardDecision::Block(format!(
                "Blast radius risk {:?} meets or exceeds threshold {:?} (score: {:.2})",
                report.risk_level, self.block_threshold, report.score,
            ))
        } else {
            GuardDecision::Allow
        }
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

    // ---- DestructiveActionGuard tests ----

    #[tokio::test]
    async fn test_destructive_action_guard_blocks_mass_deletion() {
        // 4 keys in old state, 3 removed → 75% deletion, threshold 50% → Block
        let old = AgentState::new(json!({"a": 1, "b": 2, "c": 3, "d": 4}), json!({}));
        let new = {
            let mut s = old.clone();
            s.memory = json!({"a": 1});
            s
        };

        let guard = DestructiveActionGuard::new(0.5);
        let ctx = GuardContext {
            new_state: new,
            previous_state: Some(old),
            message: "mass delete".to_string(),
            action_type: ActionType::ToolCall,
            agent_id: "agent-1".to_string(),
            branch: Some("main".to_string()),
            metadata: serde_json::Map::new(),
        };

        let decision = guard.check(&ctx).await;
        assert!(
            matches!(decision, GuardDecision::Block(_)),
            "expected Block, got: {:?}",
            decision
        );
    }

    #[tokio::test]
    async fn test_destructive_action_guard_allows_small_deletion() {
        // 10 keys in old state, 1 removed → 10% deletion, threshold 50% → Allow
        let old = AgentState::new(
            json!({"a":1,"b":2,"c":3,"d":4,"e":5,"f":6,"g":7,"h":8,"i":9,"j":10}),
            json!({}),
        );
        let new = {
            let mut s = old.clone();
            s.memory = json!({"a":1,"b":2,"c":3,"d":4,"e":5,"f":6,"g":7,"h":8,"i":9});
            s
        };

        let guard = DestructiveActionGuard::new(0.5);
        let ctx = GuardContext {
            new_state: new,
            previous_state: Some(old),
            message: "small delete".to_string(),
            action_type: ActionType::ToolCall,
            agent_id: "agent-1".to_string(),
            branch: Some("main".to_string()),
            metadata: serde_json::Map::new(),
        };

        let decision = guard.check(&ctx).await;
        assert_eq!(decision, GuardDecision::Allow);
    }

    #[tokio::test]
    async fn test_destructive_action_guard_allows_first_commit() {
        // No previous state (first commit) → Allow
        let new = AgentState::new(json!({"a": 1}), json!({}));

        let guard = DestructiveActionGuard::default();
        let ctx = GuardContext {
            new_state: new,
            previous_state: None,
            message: "initial commit".to_string(),
            action_type: ActionType::ToolCall,
            agent_id: "agent-1".to_string(),
            branch: Some("main".to_string()),
            metadata: serde_json::Map::new(),
        };

        let decision = guard.check(&ctx).await;
        assert_eq!(decision, GuardDecision::Allow);
    }

    // ---- BlastRadiusGuard tests ----

    #[tokio::test]
    async fn test_blast_radius_guard_blocks_critical() {
        // Delete all keys → Critical risk, threshold High → Block
        let old = AgentState::new(
            json!({"a":1,"b":2,"c":3,"d":4,"e":5,"f":6,"g":7,"h":8,"i":9,"j":10}),
            json!({}),
        );
        let new = {
            let mut s = old.clone();
            s.memory = json!({});
            s
        };

        let guard = BlastRadiusGuard::new(RiskLevel::High);
        let ctx = GuardContext {
            new_state: new,
            previous_state: Some(old),
            message: "nuke everything".to_string(),
            action_type: ActionType::ToolCall,
            agent_id: "agent-1".to_string(),
            branch: Some("main".to_string()),
            metadata: serde_json::Map::new(),
        };

        let decision = guard.check(&ctx).await;
        assert!(
            matches!(decision, GuardDecision::Block(_)),
            "expected Block, got: {:?}",
            decision
        );
    }

    #[tokio::test]
    async fn test_blast_radius_guard_allows_low_risk() {
        // 1 of 2 keys modified → Low or Medium risk, threshold High → Allow
        let old = AgentState::new(json!({"a": 1, "b": 2}), json!({}));
        let new = {
            let mut s = old.clone();
            s.memory = json!({"a": 99, "b": 2});
            s
        };

        let guard = BlastRadiusGuard::new(RiskLevel::High);
        let ctx = GuardContext {
            new_state: new,
            previous_state: Some(old),
            message: "small edit".to_string(),
            action_type: ActionType::ToolCall,
            agent_id: "agent-1".to_string(),
            branch: Some("main".to_string()),
            metadata: serde_json::Map::new(),
        };

        let decision = guard.check(&ctx).await;
        assert_eq!(decision, GuardDecision::Allow);
    }
}
