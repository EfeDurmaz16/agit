use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::state::{merkle_diff, AgentState};
use crate::types::ChangeType;

const WEIGHT_REMOVED: f64 = 0.5;
const WEIGHT_MODIFIED: f64 = 0.3;
const WEIGHT_ADDED: f64 = 0.2;

/// Risk level classification for a state change.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RiskLevel {
    Low,
    Medium,
    High,
    Critical,
}

/// Report summarizing the blast radius of a state change.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BlastRadiusReport {
    pub risk_level: RiskLevel,
    pub score: f64,
    pub changed_paths: Vec<String>,
    pub keys_added: usize,
    pub keys_removed: usize,
    pub keys_modified: usize,
    pub total_keys: usize,
    pub change_ratio: f64,
}

/// Recursively count leaf keys in a JSON value.
/// A leaf key is any key whose value is not an object (or an empty object counts as 0 leaves,
/// with the key itself counted). For non-object values at the root, returns 1.
pub fn count_leaf_keys(val: &Value) -> usize {
    match val {
        Value::Object(map) => {
            if map.is_empty() {
                return 0;
            }
            let mut count = 0;
            for (_key, v) in map {
                match v {
                    Value::Object(inner) if !inner.is_empty() => {
                        count += count_leaf_keys(v);
                    }
                    _ => {
                        count += 1;
                    }
                }
            }
            count
        }
        _ => 1,
    }
}

/// Analyze the blast radius between two agent states using merkle_diff.
pub fn analyze_blast_radius(old: &AgentState, new: &AgentState) -> BlastRadiusReport {
    let old_val = old.to_value();
    let new_val = new.to_value();

    let diff_entries = merkle_diff(&old_val, &new_val);

    let mut keys_added: usize = 0;
    let mut keys_removed: usize = 0;
    let mut keys_modified: usize = 0;
    let mut changed_paths: Vec<String> = Vec::new();

    for entry in &diff_entries {
        let path_str = entry.path.join(".");
        changed_paths.push(path_str);

        match entry.change_type {
            ChangeType::Added => keys_added += 1,
            ChangeType::Removed => keys_removed += 1,
            ChangeType::Changed => keys_modified += 1,
        }
    }

    // Count total leaf keys from the content-bearing fields (memory + world_state)
    // rather than the full serialized value, which includes structural overhead
    // (timestamp, cost, metadata) that would dilute the risk score.
    let old_content_keys = count_leaf_keys(&old.memory) + count_leaf_keys(&old.world_state);
    let new_content_keys = count_leaf_keys(&new.memory) + count_leaf_keys(&new.world_state);
    let total_keys = old_content_keys.max(new_content_keys);

    if total_keys == 0 {
        return BlastRadiusReport {
            risk_level: RiskLevel::Low,
            score: 0.0,
            changed_paths,
            keys_added,
            keys_removed,
            keys_modified,
            total_keys,
            change_ratio: 0.0,
        };
    }

    let total = total_keys as f64;
    // Compute weighted score: removals are most impactful, then modifications, then additions.
    // The raw formula maxes at 0.5 for pure removals, so we normalize by the max single-category
    // weight to ensure the full risk spectrum is reachable.
    let score_raw = (keys_removed as f64 / total) * WEIGHT_REMOVED
        + (keys_modified as f64 / total) * WEIGHT_MODIFIED
        + (keys_added as f64 / total) * WEIGHT_ADDED;
    let score = (score_raw / WEIGHT_REMOVED).min(1.0);

    let change_ratio = (keys_added + keys_removed + keys_modified) as f64 / total;

    let risk_level = if score > 0.7 {
        RiskLevel::Critical
    } else if score > 0.4 {
        RiskLevel::High
    } else if score > 0.2 {
        RiskLevel::Medium
    } else {
        RiskLevel::Low
    };

    BlastRadiusReport {
        risk_level,
        score,
        changed_paths,
        keys_added,
        keys_removed,
        keys_modified,
        total_keys,
        change_ratio,
    }
}

/// Analyze blast radius with an optional previous state.
/// If `old` is None (e.g. first commit), returns a Low-risk report.
pub fn analyze_blast_radius_opt(old: Option<&AgentState>, new: &AgentState) -> BlastRadiusReport {
    match old {
        Some(old_state) => analyze_blast_radius(old_state, new),
        None => {
            let new_val = new.to_value();
            let total_keys = count_leaf_keys(&new_val);
            BlastRadiusReport {
                risk_level: RiskLevel::Low,
                score: 0.0,
                changed_paths: Vec::new(),
                keys_added: 0,
                keys_removed: 0,
                keys_modified: 0,
                total_keys,
                change_ratio: 0.0,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_no_change_is_low_risk() {
        let state = AgentState::new(json!({"a": 1, "b": 2}), json!({"c": 3}));
        let report = analyze_blast_radius(&state, &state);
        assert_eq!(report.risk_level, RiskLevel::Low);
        assert_eq!(report.score, 0.0);
    }

    #[test]
    fn test_small_change_is_low_risk() {
        let old = AgentState::new(
            json!({"a": 1, "b": 2, "c": 3}),
            json!({"d": 4, "e": 5}),
        );
        // Clone to keep timestamp/cost identical so only content changes matter.
        let mut new = old.clone();
        new.memory = json!({"a": 1, "b": 2, "c": 99});
        let report = analyze_blast_radius(&old, &new);
        // 1 modified out of 5 content keys -> Low
        assert_eq!(report.risk_level, RiskLevel::Low);
        assert!(report.score <= 0.2);
    }

    #[test]
    fn test_massive_deletion_is_critical() {
        // Clone the old state and clear memory/world_state so that timestamp
        // and cost remain unchanged and don't dilute the removal score.
        let old = AgentState::new(
            json!({
                "a": 1, "b": 2, "c": 3, "d": 4, "e": 5,
                "f": 6, "g": 7, "h": 8, "i": 9, "j": 10,
                "k": 11, "l": 12, "m": 13, "n": 14, "o": 15
            }),
            json!({
                "p": 16, "q": 17, "r": 18, "s": 19, "t": 20
            }),
        );
        let mut new = old.clone();
        new.memory = json!({});
        new.world_state = json!({});
        let report = analyze_blast_radius(&old, &new);
        assert_eq!(report.risk_level, RiskLevel::Critical);
        assert!(report.score > 0.7);
    }

    #[test]
    fn test_partial_deletion_is_high() {
        // Remove 2 of 4 keys (50% deletion). With normalized scoring, this should
        // yield High or Critical risk.
        let old = AgentState::new(
            json!({"a": 1, "b": 2, "c": 3, "d": 4}),
            json!({}),
        );
        let mut new = old.clone();
        new.memory = json!({"a": 1, "b": 2});
        let report = analyze_blast_radius(&old, &new);
        // 2 removed out of 4 content keys -> normalized score = (2/4 * 0.5) / 0.5 = 0.5 -> High
        assert!(
            report.risk_level == RiskLevel::High || report.risk_level == RiskLevel::Critical,
            "Expected High or Critical, got {:?} with score {}",
            report.risk_level,
            report.score
        );
    }

    #[test]
    fn test_first_commit_no_previous_is_low() {
        let new = AgentState::new(json!({"a": 1}), json!({"b": 2}));
        let report = analyze_blast_radius_opt(None, &new);
        assert_eq!(report.risk_level, RiskLevel::Low);
        assert_eq!(report.score, 0.0);
    }

    #[test]
    fn test_report_has_changed_paths() {
        let old = AgentState::new(
            json!({"a": 1, "b": 2}),
            json!({"c": 3}),
        );
        let new = AgentState::new(
            json!({"a": 99, "d": 4}),
            json!({"c": 3}),
        );
        let report = analyze_blast_radius(&old, &new);

        // "b" was removed from memory, "a" was changed, "d" was added
        assert!(report.keys_removed >= 1, "expected at least 1 removed key");
        assert!(report.keys_modified >= 1, "expected at least 1 modified key");
        assert!(report.keys_added >= 1, "expected at least 1 added key");
        assert!(!report.changed_paths.is_empty(), "changed_paths should not be empty");

        // Verify the paths contain expected substrings
        let paths_joined = report.changed_paths.join(", ");
        assert!(
            report.changed_paths.iter().any(|p| p.contains("memory")),
            "expected a memory path in changed_paths, got: {}",
            paths_joined
        );
    }
}
