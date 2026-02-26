use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::error::{AgitError, Result};
use crate::types::Hash;

/// HEAD can point to a branch (attached) or directly to a commit (detached).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Head {
    Attached(String),
    Detached(Hash),
}

/// In-memory reference store for HEAD and branches.
#[derive(Debug, Clone)]
pub struct RefStore {
    head: Head,
    branches: HashMap<String, Hash>,
}

impl RefStore {
    pub fn new() -> Self {
        RefStore {
            head: Head::Attached("main".to_string()),
            branches: HashMap::new(),
        }
    }

    pub fn get_head(&self) -> &Head {
        &self.head
    }

    /// Set HEAD to point to a branch or detach to a commit hash.
    pub fn set_head(&mut self, target: &str, detach: bool) {
        if detach {
            self.head = Head::Detached(Hash::from(target));
        } else {
            self.head = Head::Attached(target.to_string());
        }
    }

    /// Get the name of the current branch, if HEAD is attached.
    pub fn current_branch(&self) -> Option<&str> {
        match &self.head {
            Head::Attached(name) => Some(name),
            Head::Detached(_) => None,
        }
    }

    /// Create a new branch pointing to the given hash.
    pub fn create_branch(&mut self, name: &str, at: Hash) -> Result<()> {
        if self.branches.contains_key(name) {
            return Err(AgitError::BranchExists {
                name: name.to_string(),
            });
        }
        self.branches.insert(name.to_string(), at);
        Ok(())
    }

    /// Delete a branch by name.
    pub fn delete_branch(&mut self, name: &str) -> Result<()> {
        if name == "main" {
            return Err(AgitError::InvalidArgument(
                "cannot delete main branch".to_string(),
            ));
        }
        if self.branches.remove(name).is_none() {
            return Err(AgitError::BranchNotFound {
                name: name.to_string(),
            });
        }
        Ok(())
    }

    /// Update an existing branch to point to a new hash.
    pub fn update_branch(&mut self, name: &str, hash: Hash) -> Result<()> {
        if !self.branches.contains_key(name) {
            return Err(AgitError::BranchNotFound {
                name: name.to_string(),
            });
        }
        self.branches.insert(name.to_string(), hash);
        Ok(())
    }

    pub fn list_branches(&self) -> &HashMap<String, Hash> {
        &self.branches
    }

    /// Resolve a ref name (branch or HEAD) to a commit hash.
    pub fn resolve_ref(&self, name: &str) -> Result<Hash> {
        if name == "HEAD" {
            return match &self.head {
                Head::Attached(branch) => self
                    .branches
                    .get(branch)
                    .cloned()
                    .ok_or(AgitError::NoCommits),
                Head::Detached(hash) => Ok(hash.clone()),
            };
        }
        self.branches
            .get(name)
            .cloned()
            .ok_or(AgitError::BranchNotFound {
                name: name.to_string(),
            })
    }

    /// Load refs from a persisted map (e.g., from storage).
    pub fn load_from_map(&mut self, refs: HashMap<String, String>) {
        for (name, hash) in refs {
            if name == "HEAD" {
                // Check if it's a branch ref or direct hash
                if let Some(branch) = hash.strip_prefix("ref:") {
                    self.head = Head::Attached(branch.to_string());
                } else {
                    self.head = Head::Detached(Hash::from(hash));
                }
            } else {
                self.branches.insert(name, Hash::from(hash));
            }
        }
    }

    /// Serialize refs to a map for persistence.
    pub fn to_map(&self) -> HashMap<String, String> {
        let mut map = HashMap::new();
        match &self.head {
            Head::Attached(branch) => {
                map.insert("HEAD".to_string(), format!("ref:{}", branch));
            }
            Head::Detached(hash) => {
                map.insert("HEAD".to_string(), hash.0.clone());
            }
        }
        for (name, hash) in &self.branches {
            map.insert(name.clone(), hash.0.clone());
        }
        map
    }
}

impl Default for RefStore {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_refstore() {
        let store = RefStore::new();
        assert!(matches!(store.get_head(), Head::Attached(name) if name == "main"));
        assert!(store.list_branches().is_empty());
    }

    #[test]
    fn test_create_branch() {
        let mut store = RefStore::new();
        store.create_branch("main", Hash::from("abc")).unwrap();
        store.create_branch("feature", Hash::from("def")).unwrap();
        assert_eq!(store.list_branches().len(), 2);
    }

    #[test]
    fn test_create_duplicate_branch() {
        let mut store = RefStore::new();
        store.create_branch("main", Hash::from("abc")).unwrap();
        let result = store.create_branch("main", Hash::from("def"));
        assert!(result.is_err());
    }

    #[test]
    fn test_delete_branch() {
        let mut store = RefStore::new();
        store.create_branch("feature", Hash::from("abc")).unwrap();
        store.delete_branch("feature").unwrap();
        assert!(store.list_branches().is_empty());
    }

    #[test]
    fn test_cannot_delete_main() {
        let mut store = RefStore::new();
        store.create_branch("main", Hash::from("abc")).unwrap();
        let result = store.delete_branch("main");
        assert!(result.is_err());
    }

    #[test]
    fn test_resolve_head_attached() {
        let mut store = RefStore::new();
        store.create_branch("main", Hash::from("abc123")).unwrap();
        let hash = store.resolve_ref("HEAD").unwrap();
        assert_eq!(hash.0, "abc123");
    }

    #[test]
    fn test_resolve_head_detached() {
        let mut store = RefStore::new();
        store.set_head("abc123", true);
        let hash = store.resolve_ref("HEAD").unwrap();
        assert_eq!(hash.0, "abc123");
    }

    #[test]
    fn test_set_head_branch() {
        let mut store = RefStore::new();
        store.create_branch("feature", Hash::from("abc")).unwrap();
        store.set_head("feature", false);
        assert_eq!(store.current_branch(), Some("feature"));
    }

    #[test]
    fn test_roundtrip_to_map() {
        let mut store = RefStore::new();
        store.create_branch("main", Hash::from("abc")).unwrap();
        store.create_branch("dev", Hash::from("def")).unwrap();
        let map = store.to_map();

        let mut store2 = RefStore::new();
        store2.load_from_map(map);
        assert_eq!(
            store2.resolve_ref("main").unwrap().0,
            "abc"
        );
        assert_eq!(
            store2.resolve_ref("dev").unwrap().0,
            "def"
        );
    }
}
