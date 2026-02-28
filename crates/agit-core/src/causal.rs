//! Causal dependency graph across commits.
//! Tracks which state changes caused which subsequent agent actions,
//! enabling root-cause analysis for agent behavior.

use std::collections::HashMap;

use petgraph::algo::astar;
use petgraph::graph::{DiGraph, NodeIndex};
use serde::{Deserialize, Serialize};

use crate::error::{AgitError, Result};
use crate::objects::Commit;
use crate::state::merkle_diff;
use crate::storage::StorageBackend;
use crate::types::{ActionType, Hash};

// ---------------------------------------------------------------------------
// Core types
// ---------------------------------------------------------------------------

/// The causal relationship between two commits.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CausalRelation {
    /// The effect commit lists the cause commit as a direct parent.
    DirectParent,
    /// The effect commit's action was triggered by a state change introduced
    /// by the cause commit (detected via state diff).
    StateDependent,
    /// The effect commit is a merge of two branches; the cause is one of the
    /// merged parents.
    BranchMerge,
    /// The effect commit explicitly rolls back the cause commit.
    Rollback,
}

/// A directed edge in the causal graph: cause → effect.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CausalEdge {
    pub cause_commit: Hash,
    pub effect_commit: Hash,
    /// State paths that changed between the two commits and contributed to
    /// the causal link.
    pub changed_paths: Vec<String>,
    pub relationship: CausalRelation,
}

/// A node in the causal graph representing a single commit.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CausalNode {
    pub commit_hash: Hash,
    pub action_type: ActionType,
    pub message: String,
    pub author: String,
    /// RFC 3339 timestamp string.
    pub timestamp: String,
    /// Distance from the head commit (0 = head).
    pub depth: usize,
}

// ---------------------------------------------------------------------------
// CausalGraph
// ---------------------------------------------------------------------------

/// A directed acyclic graph of causal dependencies between commits.
///
/// Nodes are [`CausalNode`]s; edges are [`CausalEdge`]s stored as petgraph
/// edge weights so that the underlying `DiGraph` drives pathfinding while we
/// still expose typed edge data.
pub struct CausalGraph {
    /// Underlying directed graph.  Node weights are `CausalNode`, edge
    /// weights are `CausalEdge`.
    graph: DiGraph<CausalNode, CausalEdge>,
    /// Map from commit hash string to the corresponding `NodeIndex`.
    index: HashMap<String, NodeIndex>,
}

impl CausalGraph {
    /// Create an empty causal graph.
    pub fn new() -> Self {
        CausalGraph {
            graph: DiGraph::new(),
            index: HashMap::new(),
        }
    }

    // -----------------------------------------------------------------------
    // Builder
    // -----------------------------------------------------------------------

    /// Build a causal graph by walking the commit DAG backwards from
    /// `head_hash` up to `depth_limit` commits.
    ///
    /// For each commit that is loaded the function:
    /// 1. Adds a `CausalNode` to the graph.
    /// 2. Loads each parent commit and adds edges with the appropriate
    ///    [`CausalRelation`].
    /// 3. Computes a merkle diff between the parent state blob and the
    ///    current commit's state blob to populate `changed_paths`.
    pub async fn build_from_history(
        storage: &dyn StorageBackend,
        head_hash: &str,
        depth_limit: usize,
    ) -> Result<Self> {
        let mut graph = CausalGraph::new();

        // BFS queue: (commit_hash, depth)
        let mut queue: std::collections::VecDeque<(String, usize)> = std::collections::VecDeque::new();
        queue.push_back((head_hash.to_string(), 0));

        // Track which commits we have already visited so we don't process
        // them twice in a DAG with shared ancestors.
        let mut visited: std::collections::HashSet<String> = std::collections::HashSet::new();

        while let Some((hash, depth)) = queue.pop_front() {
            if visited.contains(&hash) {
                continue;
            }
            if depth > depth_limit {
                continue;
            }
            visited.insert(hash.clone());

            // Load and deserialise the commit object.
            let commit = Self::load_commit(storage, &hash).await?;

            // Add a node for this commit (or retrieve the existing index if
            // it was already inserted as a parent of a previously processed
            // commit).
            let node = CausalNode {
                commit_hash: Hash::from(hash.as_str()),
                action_type: commit.action_type.clone(),
                message: commit.message.clone(),
                author: commit.author.clone(),
                timestamp: commit.timestamp.to_rfc3339(),
                depth,
            };
            let node_idx = graph.ensure_node(hash.clone(), node);

            // Load the blob (state) for this commit so we can diff it
            // against each parent's blob.
            let current_blob = Self::load_blob_value(storage, commit.tree_hash.as_str()).await;

            let is_merge = commit.parent_hashes.len() > 1;

            for parent_hash in &commit.parent_hashes {
                let parent_hash_str = parent_hash.as_str().to_string();

                // Ensure parent node exists (with a placeholder depth that
                // will be updated when we actually visit it).
                let parent_commit = Self::load_commit(storage, &parent_hash_str).await;

                if let Ok(pc) = parent_commit {
                    let parent_node = CausalNode {
                        commit_hash: parent_hash.clone(),
                        action_type: pc.action_type.clone(),
                        message: pc.message.clone(),
                        author: pc.author.clone(),
                        timestamp: pc.timestamp.to_rfc3339(),
                        depth: depth + 1,
                    };
                    let parent_idx = graph.ensure_node(parent_hash_str.clone(), parent_node);

                    // Compute changed paths via merkle diff.
                    let changed_paths = if let Ok(parent_blob) =
                        Self::load_blob_value(storage, pc.tree_hash.as_str()).await
                    {
                        if let Some(cb) = &current_blob.as_ref().ok().and_then(|v| v.clone()) {
                            merkle_diff(&parent_blob, cb)
                                .into_iter()
                                .map(|e| e.path.join("."))
                                .collect()
                        } else {
                            vec![]
                        }
                    } else {
                        vec![]
                    };

                    // Determine relationship.
                    let relationship = if is_merge {
                        CausalRelation::BranchMerge
                    } else if commit.action_type == ActionType::Rollback {
                        CausalRelation::Rollback
                    } else if !changed_paths.is_empty() {
                        CausalRelation::StateDependent
                    } else {
                        CausalRelation::DirectParent
                    };

                    let edge = CausalEdge {
                        cause_commit: parent_hash.clone(),
                        effect_commit: Hash::from(hash.as_str()),
                        changed_paths,
                        relationship,
                    };

                    // Edge direction: parent (cause) → child (effect).
                    graph.graph.add_edge(parent_idx, node_idx, edge);

                    // Enqueue the parent for processing.
                    if !visited.contains(&parent_hash_str) {
                        queue.push_back((parent_hash_str, depth + 1));
                    }
                }
                // If loading the parent fails we simply skip that edge – the
                // graph will still contain whatever was reachable.
            }
        }

        Ok(graph)
    }

    // -----------------------------------------------------------------------
    // Query API
    // -----------------------------------------------------------------------

    /// Return all edges whose *effect* is `commit_hash` (i.e. edges pointing
    /// INTO this commit, representing its causes).
    pub fn get_causes(&self, commit_hash: &str) -> Vec<&CausalEdge> {
        let Some(&node_idx) = self.index.get(commit_hash) else {
            return vec![];
        };
        self.graph
            .edges_directed(node_idx, petgraph::Direction::Incoming)
            .map(|e| e.weight())
            .collect()
    }

    /// Return all edges whose *cause* is `commit_hash` (i.e. edges going OUT
    /// from this commit, representing its effects).
    pub fn get_effects(&self, commit_hash: &str) -> Vec<&CausalEdge> {
        let Some(&node_idx) = self.index.get(commit_hash) else {
            return vec![];
        };
        self.graph
            .edges_directed(node_idx, petgraph::Direction::Outgoing)
            .map(|e| e.weight())
            .collect()
    }

    /// Trace back through causal edges to find the earliest commit in the
    /// cause chain for `commit_hash`.  Returns `None` if the commit is not
    /// in the graph or has no causes (i.e. it is already a root).
    pub fn find_root_cause(&self, commit_hash: &str) -> Option<Hash> {
        let Some(&start_idx) = self.index.get(commit_hash) else {
            return None;
        };

        // Walk backwards (Incoming edges) using an iterative DFS / BFS.
        let mut current = start_idx;
        let mut found_root = false;

        loop {
            let parents: Vec<NodeIndex> = self
                .graph
                .edges_directed(current, petgraph::Direction::Incoming)
                .map(|e| e.source())
                .collect();

            if parents.is_empty() {
                // No more incoming edges – this is the root.
                found_root = true;
                break;
            }

            // Follow the first parent (primary causal chain).
            current = parents[0];
        }

        if found_root {
            Some(self.graph[current].commit_hash.clone())
        } else {
            None
        }
    }

    /// Find the shortest path (in hop count) of causal edges between two
    /// commits.  Returns the ordered sequence of commit hashes from `from`
    /// to `to`, inclusive.  Returns an empty `Vec` if no path exists.
    pub fn get_critical_path(&self, from: &str, to: &str) -> Vec<Hash> {
        let Some(&from_idx) = self.index.get(from) else {
            return vec![];
        };
        let Some(&to_idx) = self.index.get(to) else {
            return vec![];
        };

        // Use petgraph's A* with uniform edge cost and no heuristic.
        let result = astar(
            &self.graph,
            from_idx,
            |n| n == to_idx,
            |_| 1usize,
            |_| 0usize,
        );

        match result {
            Some((_cost, path)) => path
                .into_iter()
                .map(|idx| self.graph[idx].commit_hash.clone())
                .collect(),
            None => vec![],
        }
    }

    /// Serialize the graph as an adjacency list suitable for API or dashboard
    /// consumption.  Each element contains a node and the list of outgoing
    /// causal edges.
    pub fn to_adjacency_list(&self) -> Vec<(CausalNode, Vec<CausalEdge>)> {
        use petgraph::graph::NodeIndex;

        let mut result = Vec::new();

        for node_idx in self.graph.node_indices() {
            let node = self.graph[node_idx].clone();
            let edges: Vec<CausalEdge> = self
                .graph
                .edges_directed(node_idx, petgraph::Direction::Outgoing)
                .map(|e| e.weight().clone())
                .collect();
            result.push((node, edges));
        }

        result
    }

    // -----------------------------------------------------------------------
    // Internal helpers
    // -----------------------------------------------------------------------

    /// Add a node for `hash` if it does not already exist.  If it does exist
    /// the node weight is left unchanged (the first writer wins).
    /// Returns the `NodeIndex` in either case.
    fn ensure_node(&mut self, hash: String, node: CausalNode) -> NodeIndex {
        if let Some(&idx) = self.index.get(&hash) {
            return idx;
        }
        let idx = self.graph.add_node(node);
        self.index.insert(hash, idx);
        idx
    }

    /// Load a [`Commit`] object from storage and deserialise it.
    async fn load_commit(storage: &dyn StorageBackend, hash: &str) -> Result<Commit> {
        let bytes = storage
            .get_object(hash)
            .await?
            .ok_or_else(|| AgitError::ObjectNotFound { hash: hash.to_string() })?;

        serde_json::from_slice::<Commit>(&bytes)
            .map_err(|e| AgitError::Serialization(e.to_string()))
    }

    /// Load a blob's raw JSON value from storage.  Returns `Ok(None)` when
    /// the blob does not exist (e.g. for the initial empty-state commit).
    async fn load_blob_value(
        storage: &dyn StorageBackend,
        tree_hash: &str,
    ) -> Result<Option<serde_json::Value>> {
        let bytes = match storage.get_object(tree_hash).await? {
            Some(b) => b,
            None => return Ok(None),
        };
        let value: serde_json::Value =
            serde_json::from_slice(&bytes).map_err(|e| AgitError::Serialization(e.to_string()))?;
        Ok(Some(value))
    }
}

impl Default for CausalGraph {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::objects::Blob;
    use crate::state::AgentState;
    use crate::storage::StorageBackend;
    use crate::types::{ActionType, ObjectType};
    use async_trait::async_trait;
    use chrono::Utc;
    use serde_json::json;
    use std::collections::HashMap;
    use std::sync::Mutex;

    // ------------------------------------------------------------------
    // Minimal in-memory storage backend for tests
    // ------------------------------------------------------------------

    #[derive(Default)]
    struct MemStorage {
        objects: Mutex<HashMap<String, Vec<u8>>>,
        refs: Mutex<HashMap<String, String>>,
    }

    #[async_trait]
    impl StorageBackend for MemStorage {
        async fn initialize(&self) -> Result<()> {
            Ok(())
        }
        async fn put_object(&self, hash: &str, _: ObjectType, data: &[u8]) -> Result<()> {
            self.objects.lock().unwrap().insert(hash.to_string(), data.to_vec());
            Ok(())
        }
        async fn get_object(&self, hash: &str) -> Result<Option<Vec<u8>>> {
            Ok(self.objects.lock().unwrap().get(hash).cloned())
        }
        async fn has_object(&self, hash: &str) -> Result<bool> {
            Ok(self.objects.lock().unwrap().contains_key(hash))
        }
        async fn set_ref(&self, name: &str, hash: &str) -> Result<()> {
            self.refs.lock().unwrap().insert(name.to_string(), hash.to_string());
            Ok(())
        }
        async fn get_ref(&self, name: &str) -> Result<Option<String>> {
            Ok(self.refs.lock().unwrap().get(name).cloned())
        }
        async fn list_refs(&self) -> Result<HashMap<String, String>> {
            Ok(self.refs.lock().unwrap().clone())
        }
        async fn delete_ref(&self, name: &str) -> Result<bool> {
            Ok(self.refs.lock().unwrap().remove(name).is_some())
        }
        async fn append_log(&self, _: &crate::storage::LogEntry) -> Result<()> {
            Ok(())
        }
        async fn query_logs(&self, _: &crate::storage::LogFilter) -> Result<Vec<crate::storage::LogEntry>> {
            Ok(vec![])
        }
        async fn delete_object(&self, hash: &str) -> Result<bool> {
            Ok(self.objects.lock().unwrap().remove(hash).is_some())
        }
        async fn list_objects(&self) -> Result<Vec<String>> {
            Ok(self.objects.lock().unwrap().keys().cloned().collect())
        }
        async fn delete_logs_before(&self, _: &str) -> Result<usize> {
            Ok(0)
        }
        async fn prune_logs_excess(&self, _: usize) -> Result<usize> {
            Ok(0)
        }
    }

    // ------------------------------------------------------------------
    // Helper: store a commit + its blob, return commit hash string
    // ------------------------------------------------------------------
    async fn store_commit(
        storage: &MemStorage,
        parent_hashes: Vec<Hash>,
        state_json: serde_json::Value,
        action_type: ActionType,
        message: &str,
    ) -> String {
        let blob = Blob::new(state_json);
        let blob_hash = blob.hash();
        storage
            .put_object(blob_hash.as_str(), ObjectType::Blob, &blob.serialize())
            .await
            .unwrap();

        let commit = Commit {
            tree_hash: blob_hash,
            parent_hashes,
            message: message.to_string(),
            author: "test-agent".to_string(),
            timestamp: Utc::now(),
            action_type,
            metadata: serde_json::Map::new(),
        };
        let commit_hash = commit.hash();
        let commit_bytes = serde_json::to_vec(&commit).unwrap();
        storage
            .put_object(commit_hash.as_str(), ObjectType::Commit, &commit_bytes)
            .await
            .unwrap();

        commit_hash.0
    }

    // ------------------------------------------------------------------
    // test_empty_graph
    // ------------------------------------------------------------------

    #[tokio::test]
    async fn test_empty_graph() {
        let g = CausalGraph::new();
        assert!(g.get_causes("nonexistent").is_empty());
        assert!(g.get_effects("nonexistent").is_empty());
        assert!(g.find_root_cause("nonexistent").is_none());
        assert!(g.get_critical_path("a", "b").is_empty());
        assert!(g.to_adjacency_list().is_empty());
    }

    // ------------------------------------------------------------------
    // test_causal_graph_linear_history
    // ------------------------------------------------------------------
    //
    // Commit chain: c0 ← c1 ← c2   (head = c2)
    //
    // Expected causal edges: c0→c1, c1→c2

    #[tokio::test]
    async fn test_causal_graph_linear_history() {
        let storage = MemStorage::default();

        let c0 = store_commit(
            &storage,
            vec![],
            json!({"counter": 0}),
            ActionType::Checkpoint,
            "init",
        )
        .await;

        let c1 = store_commit(
            &storage,
            vec![Hash::from(c0.as_str())],
            json!({"counter": 1}),
            ActionType::ToolCall,
            "increment",
        )
        .await;

        let c2 = store_commit(
            &storage,
            vec![Hash::from(c1.as_str())],
            json!({"counter": 2}),
            ActionType::LlmResponse,
            "respond",
        )
        .await;

        let graph = CausalGraph::build_from_history(&storage, &c2, 10)
            .await
            .expect("build_from_history should succeed");

        // c2 should have one cause: c1
        let causes_c2 = graph.get_causes(&c2);
        assert_eq!(causes_c2.len(), 1, "c2 should have exactly one cause");
        assert_eq!(causes_c2[0].cause_commit.as_str(), c1.as_str());

        // c1 should have one cause: c0
        let causes_c1 = graph.get_causes(&c1);
        assert_eq!(causes_c1.len(), 1, "c1 should have exactly one cause");
        assert_eq!(causes_c1[0].cause_commit.as_str(), c0.as_str());

        // c0 should have no causes
        assert!(graph.get_causes(&c0).is_empty(), "c0 should have no causes");

        // Effects: c0 should have c1 as an effect
        let effects_c0 = graph.get_effects(&c0);
        assert_eq!(effects_c0.len(), 1);
        assert_eq!(effects_c0[0].effect_commit.as_str(), c1.as_str());

        // Adjacency list should have 3 nodes
        assert_eq!(graph.to_adjacency_list().len(), 3);
    }

    // ------------------------------------------------------------------
    // test_find_root_cause
    // ------------------------------------------------------------------

    #[tokio::test]
    async fn test_find_root_cause() {
        let storage = MemStorage::default();

        let c0 = store_commit(
            &storage,
            vec![],
            json!({"x": 0}),
            ActionType::Checkpoint,
            "root",
        )
        .await;

        let c1 = store_commit(
            &storage,
            vec![Hash::from(c0.as_str())],
            json!({"x": 1}),
            ActionType::ToolCall,
            "step 1",
        )
        .await;

        let c2 = store_commit(
            &storage,
            vec![Hash::from(c1.as_str())],
            json!({"x": 2}),
            ActionType::ToolCall,
            "step 2",
        )
        .await;

        let graph = CausalGraph::build_from_history(&storage, &c2, 10)
            .await
            .expect("build should succeed");

        // Root cause of c2 should trace all the way back to c0
        let root = graph.find_root_cause(&c2).expect("should find root cause");
        assert_eq!(root.as_str(), c0.as_str(), "root cause of c2 should be c0");

        // Root cause of c0 itself should be c0 (it has no parents)
        let root_of_root = graph.find_root_cause(&c0).expect("c0 should be its own root");
        assert_eq!(root_of_root.as_str(), c0.as_str());
    }
}
