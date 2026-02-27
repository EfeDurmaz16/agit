# Architecture

## System Overview

```
+------------------+     +------------------+     +------------------+
|   Python SDK     |     |  TypeScript SDK  |     |   REST API       |
|   (PyO3 + stubs) |     |  (NAPI + stubs)  |     |   (FastAPI)      |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         +------------------------+------------------------+
                                  |
                    +-------------+-------------+
                    |       agit-core (Rust)     |
                    |                           |
                    |  repo.rs    - orchestrator |
                    |  objects.rs - blob/commit  |
                    |  refs.rs   - branch mgmt  |
                    |  state.rs  - diff/merge   |
                    |  gc.rs     - garbage coll. |
                    |  hash.rs   - SHA-256       |
                    |  encryption.rs - AES-GCM   |
                    +-------------+-------------+
                                  |
              +-------------------+-------------------+
              |                   |                   |
     +--------+-------+  +-------+--------+  +-------+--------+
     | SQLite Backend |  | Postgres Pool  |  | S3 + SQS       |
     | (bundled, WAL) |  | (deadpool-pg)  |  | (zstd compress) |
     +----------------+  +----------------+  +----------------+
```

## Rust Core Crate Structure

```
crates/agit-core/src/
  lib.rs          - Module exports and feature gates
  repo.rs         - Repository orchestrator (commit, merge, diff, revert, log)
  objects.rs      - Content-addressed Blob and Commit structs
  refs.rs         - Branch/HEAD reference management
  state.rs        - AgentState, Merkle diffing, three-way merge
  gc.rs           - Mark-and-sweep GC, squash operations
  hash.rs         - Deterministic SHA-256 content hashing
  error.rs        - AgitError enum with thiserror
  types.rs        - Hash, ActionType, MergeStrategy, ObjectType
  encryption.rs   - Optional AES-256-GCM + Argon2id encryption
  migration.rs    - Storage backend migration utilities
  retention.rs    - Retention policy for automatic cleanup
  storage/
    mod.rs        - StorageBackend trait definition
    sqlite.rs     - SQLite backend (WAL mode, bundled)
    postgres.rs   - PostgreSQL backend (deadpool connection pool)
    s3.rs         - AWS S3 backend (zstd compression, SQS notifications)
```

## Storage Backend Architecture

All backends implement the `StorageBackend` trait:

- **Objects**: Content-addressed by SHA-256 hash. Immutable once stored.
- **Refs**: Mutable pointers (branch names -> commit hashes).
- **Logs**: Append-only audit entries with hash-chain integrity.

### SQLite (Default)
- Zero external dependencies (bundled via rusqlite)
- WAL mode for concurrent read access
- Pragmas: `synchronous=NORMAL`, `cache_size=64MB`, `busy_timeout=5s`

### PostgreSQL
- Connection pooling via `deadpool-postgres` (max 16 connections)
- Multi-tenant namespace scoping
- JSONB for log entry details

### S3
- Object layout: `objects/<hash>`, `refs/<name>`, `logs/<agent>/<ts>.json`
- zstd compression for objects > 1KB
- Optional SQS notifications on log append
- Server-side AES-256 encryption

## Data Flow: Commit

```
AgentState → serialize(JSON) → Blob → SHA-256(blob) → tree_hash
                                                          |
Commit { tree_hash, parents, message, author, ts } → SHA-256(commit) → commit_hash
                                                                           |
                                                                    update branch ref
                                                                    append audit log
```

## Merge Algorithm

1. Find merge base (LCA) via BFS with depth limit (10,000)
2. Load base, ours, theirs states
3. Three-way merge: recursive JSON comparison
   - If only one side changed: take the change
   - If both changed identically: take either
   - If both changed differently: conflict (ours wins by default)
4. Create merge commit with two parents

## SDK Binding Architecture

- **Python (PyO3)**: Shared Tokio runtime via `OnceLock<Runtime>`, blocking bridge
- **Node.js (napi-rs)**: Async bindings with native Promise support
- **Pure fallback**: Both SDKs include in-memory stubs for testing (gated by `AGIT_ALLOW_STUBS=1`)
