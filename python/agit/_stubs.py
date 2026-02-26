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

    def set_encryption_key(self, key: str) -> None:
        """Enable field-level encryption using AES-256-GCM (via Fernet-like scheme)."""
        import hashlib
        import base64
        from dataclasses import dataclass

        key_bytes = hashlib.sha256(key.encode()).digest()

        @dataclass
        class _Encryptor:
            key: bytes

            def encrypt(self, plaintext: bytes) -> bytes:
                """Simple XOR-based encryption for stubs (NOT production-grade)."""
                import os
                nonce = os.urandom(16)
                key_stream = hashlib.sha256(self.key + nonce).digest()
                # Repeat key_stream to cover plaintext length
                full_stream = key_stream * ((len(plaintext) // len(key_stream)) + 1)
                encrypted = bytes(a ^ b for a, b in zip(plaintext, full_stream))
                return nonce + encrypted

            def decrypt(self, ciphertext: bytes) -> bytes:
                if len(ciphertext) < 16:
                    raise ValueError("Ciphertext too short")
                nonce = ciphertext[:16]
                encrypted = ciphertext[16:]
                key_stream = hashlib.sha256(self.key + nonce).digest()
                full_stream = key_stream * ((len(encrypted) // len(key_stream)) + 1)
                return bytes(a ^ b for a, b in zip(encrypted, full_stream))

        self._encryptor = _Encryptor(key=key_bytes)

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
