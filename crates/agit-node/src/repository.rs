use napi::bindgen_prelude::*;
use napi_derive::napi;
use std::sync::Arc;
use tokio::sync::Mutex;

use agit_core::{ActionType, AgentState, MergeStrategy, Repository, SqliteStorage};

use crate::types::{JsAgentState, JsCommit, JsStateDiff};

/// Napi-rs wrapper around agit_core::Repository.
#[napi]
pub struct JsRepository {
    inner: Arc<Mutex<Repository>>,
}

#[napi]
impl JsRepository {
    /// Open (or create) a repository at the given filesystem path.
    #[napi(factory)]
    pub async fn open(path: String) -> Result<JsRepository> {
        let db_path = if path.ends_with(".db") {
            path
        } else {
            format!("{}/agit.db", path.trim_end_matches('/'))
        };
        let storage = SqliteStorage::new(&db_path)
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;
        let repo = Repository::init(Box::new(storage))
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;
        Ok(JsRepository {
            inner: Arc::new(Mutex::new(repo)),
        })
    }

    /// Commit the given agent state, returning the commit hash.
    /// `memory_json` and `world_state_json` are JSON strings.
    #[napi]
    pub async fn commit(
        &self,
        memory_json: String,
        world_state_json: String,
        message: String,
        action_type: String,
        cost: Option<f64>,
    ) -> Result<String> {
        let memory: serde_json::Value = serde_json::from_str(&memory_json)
            .map_err(|e| Error::new(Status::InvalidArg, format!("invalid memory JSON: {}", e)))?;
        let world_state: serde_json::Value = serde_json::from_str(&world_state_json)
            .map_err(|e| {
                Error::new(
                    Status::InvalidArg,
                    format!("invalid world_state JSON: {}", e),
                )
            })?;

        let action = parse_action_type(&action_type);
        let mut state = AgentState::new(memory, world_state);
        if let Some(c) = cost {
            state.cost = c;
        }

        let mut repo = self.inner.lock().await;
        let hash = repo
            .commit(&state, &message, action)
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;
        Ok(hash.0)
    }

    /// Create a new branch at the given source commit or HEAD.
    #[napi]
    pub async fn branch(&self, name: String, from: Option<String>) -> Result<()> {
        let mut repo = self.inner.lock().await;
        repo.branch(&name, from.as_deref())
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))
    }

    /// Checkout a branch or commit hash, returning the restored state.
    #[napi]
    pub async fn checkout(&self, target: String) -> Result<JsAgentState> {
        let mut repo = self.inner.lock().await;
        let state = repo
            .checkout(&target)
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;
        Ok(JsAgentState::from(state))
    }

    /// Compute the diff between two commits identified by hash.
    #[napi]
    pub async fn diff(&self, hash1: String, hash2: String) -> Result<JsStateDiff> {
        let repo = self.inner.lock().await;
        let diff = repo
            .diff(&hash1, &hash2)
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;
        Ok(JsStateDiff::from(diff))
    }

    /// Merge a branch into the current branch.
    /// `strategy`: `"ours"`, `"theirs"`, or `"three_way"`.
    #[napi]
    pub async fn merge(&self, branch: String, strategy: String) -> Result<String> {
        let s = parse_merge_strategy(&strategy)?;
        let mut repo = self.inner.lock().await;
        let hash = repo
            .merge(&branch, s)
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;
        Ok(hash.0)
    }

    /// Return commit history for the given branch (or HEAD), newest first.
    #[napi]
    pub async fn log(&self, branch: Option<String>, limit: Option<u32>) -> Result<Vec<JsCommit>> {
        let lim = limit.unwrap_or(50) as usize;
        let repo = self.inner.lock().await;
        let commits = repo
            .log(branch.as_deref(), lim)
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;

        let js_commits = commits
            .into_iter()
            .map(|c| {
                let hash = c.hash().0.clone();
                JsCommit::from((hash, c))
            })
            .collect();
        Ok(js_commits)
    }

    /// Create a revert commit that restores the state from the given hash.
    #[napi]
    pub async fn revert(&self, to_hash: String) -> Result<JsAgentState> {
        let mut repo = self.inner.lock().await;
        let state = repo
            .revert(&to_hash)
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;
        Ok(JsAgentState::from(state))
    }

    /// Retrieve the agent state stored at the given commit hash.
    #[napi]
    pub async fn get_state(&self, hash: String) -> Result<JsAgentState> {
        let repo = self.inner.lock().await;
        let state = repo
            .get_state(&hash)
            .await
            .map_err(|e| Error::new(Status::GenericFailure, e.to_string()))?;
        Ok(JsAgentState::from(state))
    }

    /// Return the current HEAD hash, or null if the repo has no commits.
    #[napi]
    pub fn head(&self) -> Option<String> {
        let repo = self.inner.try_lock().ok()?;
        repo.head().ok().map(|h| h.0)
    }

    /// Return the currently checked-out branch name, or null if detached HEAD.
    #[napi]
    pub fn current_branch(&self) -> Option<String> {
        let repo = self.inner.try_lock().ok()?;
        repo.current_branch().map(|s| s.to_string())
    }

    /// List all branch names.
    #[napi]
    pub fn list_branches(&self) -> Vec<String> {
        let Ok(repo) = self.inner.try_lock() else {
            return vec![];
        };
        repo.list_branches().keys().cloned().collect()
    }
}

fn parse_action_type(s: &str) -> ActionType {
    match s {
        "tool_call" => ActionType::ToolCall,
        "llm_response" => ActionType::LlmResponse,
        "user_input" => ActionType::UserInput,
        "system_event" => ActionType::SystemEvent,
        "retry" => ActionType::Retry,
        "rollback" => ActionType::Rollback,
        "merge" => ActionType::Merge,
        "checkpoint" => ActionType::Checkpoint,
        other => ActionType::Custom(other.to_string()),
    }
}

fn parse_merge_strategy(s: &str) -> Result<MergeStrategy> {
    match s {
        "ours" => Ok(MergeStrategy::Ours),
        "theirs" => Ok(MergeStrategy::Theirs),
        "three_way" | "3way" => Ok(MergeStrategy::ThreeWay),
        other => Err(Error::new(
            Status::InvalidArg,
            format!("unknown merge strategy '{}'; use ours|theirs|three_way", other),
        )),
    }
}
