"""Pure-Python fallback stubs when agit_core native module is unavailable."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes mirroring the Rust types
# ---------------------------------------------------------------------------

class PyAgentState:
    """Pure-Python equivalent of agit_core.PyAgentState."""

    def __init__(self, memory: dict[str, Any], world_state: dict[str, Any]) -> None:
        self.memory: dict[str, Any] = memory
        self.world_state: dict[str, Any] = world_state

    def to_dict(self) -> dict[str, Any]:
        return {"memory": self.memory, "world_state": self.world_state}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PyAgentState:
        return cls(d.get("memory", {}), d.get("world_state", {}))

    def __repr__(self) -> str:  # pragma: no cover
        return f"PyAgentState(memory={self.memory!r})"


@dataclass
class PyCommit:
    """Pure-Python equivalent of agit_core.PyCommit."""

    hash: str
    message: str
    author: str
    timestamp: str
    action_type: str
    parent_hashes: list[str] = field(default_factory=list)
    tree_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return f"PyCommit({self.hash[:8]}…, {self.message!r})"


@dataclass
class PyDiffEntry:
    """A single diff entry."""

    path: str
    change_type: str  # "added" | "removed" | "changed"
    old_value: Any = None
    new_value: Any = None


@dataclass
class PyStateDiff:
    """Collection of diff entries between two states."""

    base_hash: str
    target_hash: str
    entries: list[PyDiffEntry] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0


# ---------------------------------------------------------------------------
# Minimal in-process repository implementation
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _diff_dicts(
    base: dict[str, Any],
    target: dict[str, Any],
    prefix: str = "",
) -> list[PyDiffEntry]:
    entries: list[PyDiffEntry] = []
    all_keys = set(base) | set(target)
    for key in sorted(all_keys):
        path = f"{prefix}.{key}" if prefix else key
        if key not in base:
            entries.append(PyDiffEntry(path=path, change_type="added", new_value=target[key]))
        elif key not in target:
            entries.append(PyDiffEntry(path=path, change_type="removed", old_value=base[key]))
        elif base[key] != target[key]:
            if isinstance(base[key], dict) and isinstance(target[key], dict):
                entries.extend(_diff_dicts(base[key], target[key], prefix=path))
            else:
                entries.append(
                    PyDiffEntry(
                        path=path,
                        change_type="changed",
                        old_value=base[key],
                        new_value=target[key],
                    )
                )
    return entries


class PyRepository:
    """Pure-Python in-memory/SQLite repository stub."""

    def __init__(self, path: str, agent_id: str = "default") -> None:
        self._path = path
        self._agent_id = agent_id
        self._lock = threading.Lock()

        # In-memory storage
        self._objects: dict[str, bytes] = {}  # hash -> serialised bytes
        self._refs: dict[str, str] = {"HEAD": "main"}
        self._branches: dict[str, str] = {}  # branch -> commit hash
        self._audit: list[dict[str, Any]] = []

        # If path is a real directory (not ":memory:"), persist via SQLite
        if path != ":memory:":
            self._db_path = str(Path(path) / ".agit" / "repo.db")
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
        else:
            self._db_path = None  # type: ignore[assignment]

    # --- Initialisation ---

    def _init_db(self) -> None:
        if self._db_path is None:
            return
        con = sqlite3.connect(self._db_path)
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS objects (hash TEXT PRIMARY KEY, data BLOB);
            CREATE TABLE IF NOT EXISTS refs   (name TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS audit  (id TEXT, ts TEXT, agent TEXT, action TEXT, msg TEXT, commit_hash TEXT);
            """
        )
        con.commit()
        # Load existing refs and branches from disk into memory
        for row in con.execute("SELECT name, value FROM refs"):
            name, value = row
            self._refs[name] = value
            if name != "HEAD":
                self._branches[name] = value
        # Load existing objects into memory
        for row in con.execute("SELECT hash, data FROM objects"):
            self._objects[row[0]] = bytes(row[1])
        con.close()

    # --- Core operations ---

    def _put(self, h: str, data: bytes) -> None:
        with self._lock:
            self._objects[h] = data
        if self._db_path:
            con = sqlite3.connect(self._db_path)
            con.execute("INSERT OR REPLACE INTO objects VALUES (?,?)", (h, data))
            con.commit()
            con.close()

    def _get(self, h: str) -> bytes | None:
        with self._lock:
            if h in self._objects:
                return self._objects[h]
        if self._db_path:
            con = sqlite3.connect(self._db_path)
            row = con.execute("SELECT data FROM objects WHERE hash=?", (h,)).fetchone()
            con.close()
            if row:
                return bytes(row[0])
        return None

    def _set_ref(self, name: str, value: str) -> None:
        with self._lock:
            self._refs[name] = value
            if name != "HEAD":
                self._branches[name] = value
        if self._db_path:
            con = sqlite3.connect(self._db_path)
            con.execute("INSERT OR REPLACE INTO refs VALUES (?,?)", (name, value))
            con.commit()
            con.close()

    def _resolve(self, name: str) -> str | None:
        with self._lock:
            if name in self._branches:
                return self._branches[name]
            head = self._refs.get("HEAD", "main")
            if name == "HEAD":
                return self._branches.get(head) or self._refs.get(head)
            # Check if it's a raw commit hash that exists in object store
            if name in self._objects:
                return name
        # Also check on-disk storage for commit hashes
        if self._db_path:
            if self._get(name) is not None:
                return name
        return None

    # --- Public API (mirrors PyO3 bindings) ---

    def commit(
        self,
        state: PyAgentState,
        message: str,
        action_type: str = "tool_call",
    ) -> str:
        state_dict = state.to_dict()
        if hasattr(self, "_encryptor") and self._encryptor is not None:
            state_dict = self._encrypt_state(state_dict)
        state_bytes = json.dumps(state_dict, sort_keys=True).encode()
        tree_hash = _sha256(state_bytes)
        self._put(tree_hash, state_bytes)

        parent = self._resolve("HEAD") or ""

        # Optimistic concurrency control: verify expected parent
        if hasattr(self, '_expected_parent') and self._expected_parent is not None:
            if parent != self._expected_parent:
                raise ValueError(
                    f"Concurrency conflict: expected parent {self._expected_parent[:12]} "
                    f"but HEAD is at {parent[:12]}. Another agent may have committed."
                )
            self._expected_parent = None

        commit_obj: dict[str, Any] = {
            "tree_hash": tree_hash,
            "parent_hashes": [parent] if parent else [],
            "message": message,
            "author": self._agent_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action_type": action_type,
            "metadata": {},
        }
        commit_bytes = json.dumps(commit_obj, sort_keys=True).encode()
        commit_hash = _sha256(commit_bytes)
        self._put(commit_hash, commit_bytes)

        # Update current branch ref
        with self._lock:
            head_ref = self._refs.get("HEAD", "main")
        branch = head_ref if head_ref in self._branches or not self._branches else head_ref
        self._set_ref(branch, commit_hash)
        self._set_ref("HEAD", branch)

        self._append_audit("commit", message, commit_hash)
        return commit_hash

    def get_state(self, commit_hash: str) -> PyAgentState:
        data = self._get(commit_hash)
        if data is None:
            raise KeyError(f"commit not found: {commit_hash}")
        commit_obj = json.loads(data)
        blob = self._get(commit_obj["tree_hash"])
        if blob is None:
            raise KeyError(f"blob not found: {commit_obj['tree_hash']}")
        state_dict = json.loads(blob)
        if hasattr(self, "_encryptor") and self._encryptor is not None:
            state_dict = self._decrypt_state(state_dict)
        return PyAgentState.from_dict(state_dict)

    def log(self, limit: int = 10) -> list[PyCommit]:
        start = self._resolve("HEAD")
        if not start:
            return []
        commits: list[PyCommit] = []
        visited: set[str] = set()
        queue = [start]
        while queue and len(commits) < limit:
            h = queue.pop(0)
            if h in visited or not h:
                continue
            visited.add(h)
            data = self._get(h)
            if data is None:
                continue
            obj = json.loads(data)
            commits.append(
                PyCommit(
                    hash=h,
                    message=obj["message"],
                    author=obj["author"],
                    timestamp=obj["timestamp"],
                    action_type=obj["action_type"],
                    parent_hashes=obj.get("parent_hashes", []),
                    tree_hash=obj.get("tree_hash", ""),
                )
            )
            queue.extend(obj.get("parent_hashes", []))
        commits.sort(key=lambda c: c.timestamp, reverse=True)
        return commits[:limit]

    def branch(self, name: str, from_ref: str | None = None) -> None:
        source = self._resolve(from_ref or "HEAD") or ""
        if not source:
            raise ValueError("No commits yet; cannot create branch")
        self._set_ref(name, source)

    def checkout(self, target: str) -> PyAgentState:
        with self._lock:
            if target in self._branches:
                self._refs["HEAD"] = target
                commit_hash = self._branches[target]
            else:
                # Treat as commit hash
                self._refs["HEAD"] = target
                commit_hash = target
        return self.get_state(commit_hash)

    def diff(self, hash1: str, hash2: str) -> PyStateDiff:
        s1 = self.get_state(hash1)
        s2 = self.get_state(hash2)
        entries = _diff_dicts(s1.to_dict(), s2.to_dict())
        return PyStateDiff(base_hash=hash1, target_hash=hash2, entries=entries)

    def merge(self, branch: str, strategy: str = "three_way") -> str:
        with self._lock:
            current_branch = self._refs.get("HEAD", "main")
            ours_hash = self._branches.get(current_branch, "")
            theirs_hash = self._branches.get(branch, "")
        if not ours_hash or not theirs_hash:
            raise ValueError("Cannot merge: missing branch commit")
        ours_state = self.get_state(ours_hash)
        theirs_state = self.get_state(theirs_hash)

        if strategy == "ours":
            merged = ours_state
        elif strategy == "theirs":
            merged = theirs_state
        else:
            merged_dict = {**theirs_state.to_dict(), **ours_state.to_dict()}
            merged = PyAgentState.from_dict(merged_dict)

        state_bytes = json.dumps(merged.to_dict(), sort_keys=True).encode()
        tree_hash = _sha256(state_bytes)
        self._put(tree_hash, state_bytes)
        with self._lock:
            current_branch = self._refs.get("HEAD", "main")
            current_hash = self._branches.get(current_branch, "")
        commit_obj: dict[str, Any] = {
            "tree_hash": tree_hash,
            "parent_hashes": [ours_hash, theirs_hash],
            "message": f"merge branch '{branch}' into '{current_branch}'",
            "author": self._agent_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action_type": "merge",
            "metadata": {},
        }
        commit_bytes = json.dumps(commit_obj, sort_keys=True).encode()
        commit_hash = _sha256(commit_bytes)
        self._put(commit_hash, commit_bytes)
        with self._lock:
            self._branches[current_branch] = commit_hash
        self._append_audit("merge", f"merged '{branch}'", commit_hash)
        return commit_hash

    def revert(self, to_hash: str) -> PyAgentState:
        state = self.get_state(to_hash)
        self.commit(state, f"revert to {to_hash[:8]}", "rollback")
        return state

    def list_branches(self) -> dict[str, str]:
        with self._lock:
            return dict(self._branches)

    def current_branch(self) -> str | None:
        with self._lock:
            head = self._refs.get("HEAD", "main")
            return head if head in self._branches else None

    def audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._audit[-limit:])

    def delete_branch(self, name: str) -> None:
        with self._lock:
            self._branches.pop(name, None)
            self._refs.pop(name, None)

    def set_expected_parent(self, parent_hash: str | None) -> None:
        """Set expected parent for next commit (optimistic concurrency control).
        If the actual HEAD doesn't match when committing, a ValueError is raised."""
        self._expected_parent = parent_hash

    def compare_and_swap_ref(self, name: str, expected: str, new_value: str) -> bool:
        """Atomically update a ref only if it currently points to `expected`.
        Returns True if the swap succeeded, False if the ref was changed by another writer."""
        with self._lock:
            current = self._branches.get(name) or self._refs.get(name)
            if current != expected:
                return False
            self._refs[name] = new_value
            if name != "HEAD":
                self._branches[name] = new_value
        if self._db_path:
            con = sqlite3.connect(self._db_path)
            con.execute("INSERT OR REPLACE INTO refs VALUES (?,?)", (name, new_value))
            con.commit()
            con.close()
        return True

    def set_encryption_key(self, key: str) -> None:
        """Enable field-level encryption using Fernet (AES-128-CBC + HMAC-SHA256)."""
        import base64
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.fernet import Fernet
        from dataclasses import dataclass

        # Derive a Fernet-compatible key using PBKDF2
        salt = b"agit-encryption-salt-v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        derived = kdf.derive(key.encode())
        fernet_key = base64.urlsafe_b64encode(derived)

        @dataclass
        class _Encryptor:
            fernet: Fernet

            def encrypt(self, plaintext: bytes) -> bytes:
                return self.fernet.encrypt(plaintext)

            def decrypt(self, ciphertext: bytes) -> bytes:
                return self.fernet.decrypt(ciphertext)

        self._encryptor = _Encryptor(fernet=Fernet(fernet_key))

    def _encrypt_state(self, state_dict: dict[str, Any]) -> dict[str, Any]:
        """Encrypt memory and world_state fields if encryptor is set."""
        if not hasattr(self, "_encryptor") or self._encryptor is None:
            return state_dict
        import base64 as b64
        enc_memory = b64.b64encode(
            self._encryptor.encrypt(json.dumps(state_dict.get("memory", {}), sort_keys=True).encode())
        ).decode()
        enc_world = b64.b64encode(
            self._encryptor.encrypt(json.dumps(state_dict.get("world_state", {}), sort_keys=True).encode())
        ).decode()
        return {"memory": f"ENC:{enc_memory}", "world_state": f"ENC:{enc_world}"}

    def _decrypt_state(self, state_dict: dict[str, Any]) -> dict[str, Any]:
        """Decrypt memory and world_state fields if they are encrypted."""
        if not hasattr(self, "_encryptor") or self._encryptor is None:
            return state_dict
        import base64 as b64
        result = dict(state_dict)
        for field in ("memory", "world_state"):
            val = result.get(field)
            if isinstance(val, str) and val.startswith("ENC:"):
                raw = b64.b64decode(val[4:])
                result[field] = json.loads(self._encryptor.decrypt(raw))
        return result

    def gc(self, keep_last_n: int = 0) -> Any:
        """Garbage collection: remove unreachable objects."""
        # Find all reachable objects via BFS from branch tips
        reachable: set[str] = set()
        queue: list[str] = []
        with self._lock:
            for branch_hash in self._branches.values():
                queue.append(branch_hash)

        while queue:
            h = queue.pop(0)
            if h in reachable or not h:
                continue
            reachable.add(h)
            data = self._get(h)
            if data is None:
                continue
            try:
                obj = json.loads(data)
                # It's a commit - add tree hash and parents
                if "tree_hash" in obj:
                    reachable.add(obj["tree_hash"])
                    queue.extend(obj.get("parent_hashes", []))
            except (json.JSONDecodeError, KeyError):
                pass  # It's a blob, already marked reachable

        # Remove unreachable objects
        objects_before = len(self._objects)
        unreachable = set(self._objects.keys()) - reachable
        for h in unreachable:
            del self._objects[h]
            if self._db_path:
                con = sqlite3.connect(self._db_path)
                con.execute("DELETE FROM objects WHERE hash=?", (h,))
                con.commit()
                con.close()

        class _GcResult:
            def __init__(self, before: int, removed: int):
                self.objects_before = before
                self.objects_removed = removed
                self.objects_after = before - removed

        return _GcResult(objects_before, len(unreachable))

    def bisect_start(self, good_hash: str, bad_hash: str) -> dict[str, Any]:
        """Start a bisect session. Returns session state."""
        # Collect commits between good and bad
        commits = []
        visited = set()
        queue = [bad_hash]
        while queue:
            h = queue.pop(0)
            if h in visited or not h:
                continue
            visited.add(h)
            data = self._get(h)
            if data is None:
                continue
            obj = json.loads(data)
            commits.append({"hash": h, "timestamp": obj.get("timestamp", "")})
            if h == good_hash:
                break
            queue.extend(obj.get("parent_hashes", []))

        commits.sort(key=lambda c: c["timestamp"])
        hashes = [c["hash"] for c in commits]
        mid = len(hashes) // 2

        self._bisect_session = {
            "good": good_hash,
            "bad": bad_hash,
            "candidates": hashes,
            "current_idx": mid,
            "steps": 0,
            "status": "in_progress",
        }
        return self._bisect_session

    def bisect_step(self, mark: str) -> dict[str, Any]:
        """Mark current commit as 'good' or 'bad', narrow search."""
        if not hasattr(self, '_bisect_session') or self._bisect_session is None:
            raise ValueError("No bisect session active")

        session = self._bisect_session
        candidates = session["candidates"]
        idx = session["current_idx"]
        session["steps"] += 1

        if mark == "good":
            # First bad is after this point
            candidates = candidates[idx + 1:]
        elif mark == "bad":
            # First bad is at or before this point
            candidates = candidates[:idx + 1]
        else:
            raise ValueError(f"Invalid mark: {mark}, expected 'good' or 'bad'")

        session["candidates"] = candidates

        if len(candidates) <= 1:
            session["status"] = "completed"
            session["result"] = {
                "first_bad": candidates[0] if candidates else session["bad"],
                "total_steps": session["steps"],
                "commits_searched": len(candidates),
            }
        else:
            session["current_idx"] = len(candidates) // 2

        return session

    def bisect_reset(self) -> None:
        """Reset bisect session."""
        self._bisect_session = None

    def get_causal_graph(self, head_hash: str | None = None, depth: int = 50) -> dict[str, Any]:
        """Build a causal dependency graph from commit history."""
        start = head_hash or (self._resolve("HEAD") or "")
        if not start:
            return {"nodes": [], "edges": []}

        nodes = []
        edges = []
        visited = set()
        queue = [start]
        count = 0

        while queue and count < depth:
            h = queue.pop(0)
            if h in visited or not h:
                continue
            visited.add(h)
            count += 1

            data = self._get(h)
            if data is None:
                continue
            obj = json.loads(data)

            nodes.append({
                "hash": h,
                "message": obj.get("message", ""),
                "author": obj.get("author", ""),
                "action_type": obj.get("action_type", ""),
                "timestamp": obj.get("timestamp", ""),
                "depth": count - 1,
            })

            for parent in obj.get("parent_hashes", []):
                relationship = "direct_parent"
                if obj.get("action_type") == "merge":
                    relationship = "branch_merge"
                elif obj.get("action_type") == "rollback":
                    relationship = "rollback"

                edges.append({
                    "cause": parent,
                    "effect": h,
                    "relationship": relationship,
                    "changed_paths": [],  # Would need diff computation
                })
                queue.append(parent)

        return {"nodes": nodes, "edges": edges}

    def get_retention_preview(self, policy_dict: dict[str, Any]) -> dict[str, Any]:
        """Analyze objects/commits and return what would be deleted under policy."""
        max_age_secs = policy_dict.get("max_age_secs")
        max_commits = policy_dict.get("max_commits")
        keep_branches = policy_dict.get("keep_branches", ["main"])
        max_log_age_secs = policy_dict.get("max_log_age_secs")
        max_log_entries = policy_dict.get("max_log_entries")

        now = time.time()
        all_commits = self.log(limit=10000)

        # Determine which commits would be expired
        commits_expired = 0
        commits_retained = 0
        for i, c in enumerate(all_commits):
            expired = False
            if max_age_secs is not None:
                try:
                    ts = time.mktime(time.strptime(c.timestamp, "%Y-%m-%dT%H:%M:%SZ"))
                    if (now - ts) > max_age_secs:
                        expired = True
                except (ValueError, OverflowError):
                    pass
            if max_commits is not None and i >= max_commits:
                expired = True
            if expired:
                commits_expired += 1
            else:
                commits_retained += 1

        objects_before = len(self._objects)

        # Estimate objects that would be deleted (2 per expired commit: tree + commit)
        objects_deleted = commits_expired * 2

        # Estimate log entries that would be pruned
        logs_pruned = 0
        with self._lock:
            total_logs = len(self._audit)
        if max_log_entries is not None and total_logs > max_log_entries:
            logs_pruned = total_logs - max_log_entries
        if max_log_age_secs is not None:
            for entry in list(self._audit):
                try:
                    ts = time.mktime(time.strptime(entry["timestamp"], "%Y-%m-%dT%H:%M:%SZ"))
                    if (now - ts) > max_log_age_secs:
                        logs_pruned += 1
                except (ValueError, OverflowError):
                    pass

        return {
            "commits_expired": commits_expired,
            "commits_retained": commits_retained,
            "objects_deleted": objects_deleted,
            "logs_pruned": logs_pruned,
            "objects_before": objects_before,
            "objects_after": max(0, objects_before - objects_deleted),
        }

    def enforce_retention(self, policy_dict: dict[str, Any]) -> dict[str, Any]:
        """Actually delete expired objects and prune logs based on policy."""
        max_age_secs = policy_dict.get("max_age_secs")
        max_commits = policy_dict.get("max_commits")
        keep_branches = policy_dict.get("keep_branches", ["main"])
        max_log_age_secs = policy_dict.get("max_log_age_secs")
        max_log_entries = policy_dict.get("max_log_entries")

        now = time.time()
        objects_before = len(self._objects)
        all_commits = self.log(limit=10000)

        # Find protected commit hashes (branch tips for kept branches)
        protected_hashes: set[str] = set()
        with self._lock:
            for br in keep_branches:
                if br in self._branches:
                    protected_hashes.add(self._branches[br])

        commits_expired = 0
        commits_retained = 0
        hashes_to_remove: set[str] = set()

        for i, c in enumerate(all_commits):
            if c.hash in protected_hashes:
                commits_retained += 1
                continue
            expired = False
            if max_age_secs is not None:
                try:
                    ts = time.mktime(time.strptime(c.timestamp, "%Y-%m-%dT%H:%M:%SZ"))
                    if (now - ts) > max_age_secs:
                        expired = True
                except (ValueError, OverflowError):
                    pass
            if max_commits is not None and i >= max_commits:
                expired = True
            if expired:
                commits_expired += 1
                hashes_to_remove.add(c.hash)
                if c.tree_hash:
                    hashes_to_remove.add(c.tree_hash)
            else:
                commits_retained += 1

        # Delete expired objects
        objects_deleted = 0
        for h in hashes_to_remove:
            if h in self._objects:
                with self._lock:
                    self._objects.pop(h, None)
                if self._db_path:
                    con = sqlite3.connect(self._db_path)
                    con.execute("DELETE FROM objects WHERE hash=?", (h,))
                    con.commit()
                    con.close()
                objects_deleted += 1

        # Prune logs
        logs_pruned = 0
        with self._lock:
            original_logs = list(self._audit)

        kept_logs = list(original_logs)
        if max_log_age_secs is not None:
            kept_logs_new = []
            for entry in kept_logs:
                try:
                    ts = time.mktime(time.strptime(entry["timestamp"], "%Y-%m-%dT%H:%M:%SZ"))
                    if (now - ts) <= max_log_age_secs:
                        kept_logs_new.append(entry)
                    else:
                        logs_pruned += 1
                except (ValueError, OverflowError):
                    kept_logs_new.append(entry)
            kept_logs = kept_logs_new

        if max_log_entries is not None and len(kept_logs) > max_log_entries:
            excess = len(kept_logs) - max_log_entries
            logs_pruned += excess
            kept_logs = kept_logs[-max_log_entries:]

        with self._lock:
            self._audit = kept_logs

        objects_after = len(self._objects)
        return {
            "commits_expired": commits_expired,
            "commits_retained": commits_retained,
            "objects_deleted": objects_deleted,
            "logs_pruned": logs_pruned,
            "objects_before": objects_before,
            "objects_after": objects_after,
        }

    def get_schema_version(self) -> int:
        """Return current schema version from schema_version table."""
        if self._db_path is None:
            return 1
        con = sqlite3.connect(self._db_path)
        try:
            row = con.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
            if row:
                return int(row[0])
            return 1
        except sqlite3.OperationalError:
            # Table does not exist yet; version 1 is baseline
            return 1
        finally:
            con.close()

    def apply_migrations(self) -> dict[str, Any]:
        """Apply pending schema migrations. Returns migration result."""
        current_version = self.get_schema_version()

        if self._db_path is None:
            return {"from_version": current_version, "to_version": current_version, "migrations_applied": 0}

        con = sqlite3.connect(self._db_path)
        try:
            # Ensure schema_version table exists
            con.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)"
            )
            con.commit()

            # Define available migrations (version -> DDL)
            migrations: list[tuple[int, str]] = [
                (2, "CREATE TABLE IF NOT EXISTS branches (name TEXT PRIMARY KEY, commit_hash TEXT, created_at TEXT)"),
                (3, "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit (ts)"),
            ]

            applied = 0
            target_version = current_version
            for version, ddl in migrations:
                if version > current_version:
                    con.execute(ddl)
                    con.execute(
                        "INSERT OR REPLACE INTO schema_version VALUES (?, ?)",
                        (version, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                    )
                    con.commit()
                    target_version = version
                    applied += 1

            return {
                "from_version": current_version,
                "to_version": target_version,
                "migrations_applied": applied,
            }
        finally:
            con.close()

    # --- Internal ---

    def _append_audit(self, action: str, message: str, commit_hash: str | None) -> None:
        entry: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent_id": self._agent_id,
            "action": action,
            "message": message,
            "commit_hash": commit_hash,
        }
        with self._lock:
            self._audit.append(entry)
        if self._db_path:
            con = sqlite3.connect(self._db_path)
            con.execute(
                "INSERT INTO audit VALUES (?,?,?,?,?,?)",
                (
                    entry["id"],
                    entry["timestamp"],
                    entry["agent_id"],
                    entry["action"],
                    entry["message"],
                    entry["commit_hash"],
                ),
            )
            con.commit()
            con.close()
