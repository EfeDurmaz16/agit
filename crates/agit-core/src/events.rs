//! Event system for real-time notifications of repository mutations.
//! Enables SSE/WebSocket streaming and multi-agent coordination.

use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

use crate::types::{ActionType, Hash};

/// All mutations that can occur in an agit repository.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AgitEvent {
    CommitCreated {
        hash: Hash,
        message: String,
        author: String,
        action_type: ActionType,
        branch: Option<String>,
        timestamp: String,
    },
    BranchCreated {
        name: String,
        from_hash: Hash,
        timestamp: String,
    },
    BranchDeleted {
        name: String,
        timestamp: String,
    },
    MergeCompleted {
        merge_hash: Hash,
        source_branch: String,
        target_branch: String,
        timestamp: String,
    },
    RevertPerformed {
        new_hash: Hash,
        reverted_to: Hash,
        timestamp: String,
    },
    CheckoutPerformed {
        target: String,
        is_branch: bool,
        timestamp: String,
    },
    GcCompleted {
        objects_removed: usize,
        objects_remaining: usize,
        timestamp: String,
    },
    RetentionApplied {
        objects_deleted: usize,
        logs_pruned: usize,
        timestamp: String,
    },
}

/// Trait for anything that can broadcast `AgitEvent`s.
pub trait EventEmitter: Send + Sync {
    fn emit(&self, event: AgitEvent);
    fn subscribe(&self) -> EventReceiver;
}

/// A snapshot receiver that returns all events from a given offset.
/// Backed by `InMemoryEventBus` – poll `recv_all` to receive new events.
pub struct EventReceiver {
    bus: InMemoryEventBus,
    offset: usize,
}

impl EventReceiver {
    /// Drain all new events since this receiver was created / last drained.
    pub fn recv_all(&mut self) -> Vec<AgitEvent> {
        let events = self.bus.events_since(self.offset);
        self.offset += events.len();
        events
    }
}

// ── Internal shared state ────────────────────────────────────────────────────

struct InMemoryEventBusInner {
    log: Mutex<Vec<AgitEvent>>,
    callbacks: Mutex<Vec<Box<dyn Fn(&AgitEvent) + Send + Sync>>>,
}

// ── Public bus ───────────────────────────────────────────────────────────────

/// A simple in-process event bus backed by an append-only log.
///
/// Suitable for SSE polling (`events_since`) and synchronous callbacks.
/// Clone is cheap – all clones share the same inner state.
#[derive(Clone)]
pub struct InMemoryEventBus {
    inner: Arc<InMemoryEventBusInner>,
}

impl InMemoryEventBus {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(InMemoryEventBusInner {
                log: Mutex::new(Vec::new()),
                callbacks: Mutex::new(Vec::new()),
            }),
        }
    }

    /// Append an event to the log and synchronously invoke all registered callbacks.
    pub fn emit(&self, event: AgitEvent) {
        {
            let callbacks = self.inner.callbacks.lock().unwrap();
            for cb in callbacks.iter() {
                cb(&event);
            }
        }
        let mut log = self.inner.log.lock().unwrap();
        log.push(event);
    }

    /// Return all events whose index is >= `offset`.
    /// Use offset 0 to receive the full history.
    pub fn events_since(&self, offset: usize) -> Vec<AgitEvent> {
        let log = self.inner.log.lock().unwrap();
        log[offset.min(log.len())..].to_vec()
    }

    /// Total number of events recorded so far.
    pub fn event_count(&self) -> usize {
        self.inner.log.lock().unwrap().len()
    }

    /// Register a callback that will be invoked synchronously on every future `emit`.
    pub fn register_callback(&self, cb: Box<dyn Fn(&AgitEvent) + Send + Sync>) {
        self.inner.callbacks.lock().unwrap().push(cb);
    }

    /// Remove all recorded events (useful in tests).
    pub fn clear(&self) {
        self.inner.log.lock().unwrap().clear();
    }
}

impl Default for InMemoryEventBus {
    fn default() -> Self {
        Self::new()
    }
}

impl EventEmitter for InMemoryEventBus {
    fn emit(&self, event: AgitEvent) {
        InMemoryEventBus::emit(self, event);
    }

    fn subscribe(&self) -> EventReceiver {
        let offset = self.event_count();
        EventReceiver {
            bus: self.clone(),
            offset,
        }
    }
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn make_commit_event(msg: &str) -> AgitEvent {
        AgitEvent::CommitCreated {
            hash: Hash::from("abc123def456abc123def456abc123def456abc123def456abc123def456abc1"),
            message: msg.to_string(),
            author: "agent-0".to_string(),
            action_type: ActionType::Checkpoint,
            branch: Some("main".to_string()),
            timestamp: "2024-01-01T00:00:00Z".to_string(),
        }
    }

    #[test]
    fn test_emit_and_receive() {
        let bus = InMemoryEventBus::new();
        assert_eq!(bus.event_count(), 0);

        bus.emit(make_commit_event("first commit"));
        assert_eq!(bus.event_count(), 1);

        bus.emit(make_commit_event("second commit"));
        assert_eq!(bus.event_count(), 2);

        let all = bus.events_since(0);
        assert_eq!(all.len(), 2);

        if let AgitEvent::CommitCreated { message, .. } = &all[0] {
            assert_eq!(message, "first commit");
        } else {
            panic!("expected CommitCreated");
        }
    }

    #[test]
    fn test_events_since() {
        let bus = InMemoryEventBus::new();

        for i in 0..5 {
            bus.emit(make_commit_event(&format!("commit {i}")));
        }

        let tail = bus.events_since(3);
        assert_eq!(tail.len(), 2);

        if let AgitEvent::CommitCreated { message, .. } = &tail[0] {
            assert_eq!(message, "commit 3");
        } else {
            panic!("expected CommitCreated");
        }

        // offset beyond length → empty
        let none = bus.events_since(100);
        assert!(none.is_empty());
    }

    #[test]
    fn test_callback_invoked() {
        let bus = InMemoryEventBus::new();
        let counter = Arc::new(AtomicUsize::new(0));

        let counter_clone = Arc::clone(&counter);
        bus.register_callback(Box::new(move |_event| {
            counter_clone.fetch_add(1, Ordering::SeqCst);
        }));

        bus.emit(make_commit_event("alpha"));
        bus.emit(AgitEvent::BranchCreated {
            name: "feature".to_string(),
            from_hash: Hash::from("deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
            timestamp: "2024-01-01T00:00:00Z".to_string(),
        });

        assert_eq!(counter.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn test_subscriber_receives_only_new_events() {
        let bus = InMemoryEventBus::new();
        bus.emit(make_commit_event("before subscribe"));

        let mut rx = bus.subscribe();

        bus.emit(make_commit_event("after subscribe 1"));
        bus.emit(make_commit_event("after subscribe 2"));

        let received = rx.recv_all();
        assert_eq!(received.len(), 2);

        // Second drain should be empty
        let again = rx.recv_all();
        assert!(again.is_empty());
    }

    #[test]
    fn test_clear() {
        let bus = InMemoryEventBus::new();
        bus.emit(make_commit_event("to be cleared"));
        assert_eq!(bus.event_count(), 1);
        bus.clear();
        assert_eq!(bus.event_count(), 0);
    }
}
