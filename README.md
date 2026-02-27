[![CI](https://github.com/anthropics/agit/actions/workflows/ci.yml/badge.svg)](https://github.com/anthropics/agit/actions/workflows/ci.yml)

# AgentGit (agit)

**Git-like version control for AI agents.** Every agent action is a commit — diffable, revertable, auditable.

agit is a purpose-built VCS engine for the AI agent lifecycle. It combines a high-performance Rust core with Python and TypeScript SDKs to provide structured state versioning, three-way merge for JSON state, encrypted audit trails, and 9+ framework integrations — including the only native support for both Google A2A and FIDES trust protocols.

## Why agit?

AI agents make thousands of decisions, call tools, modify state, and collaborate in swarms. When something goes wrong, you need to know *exactly* what happened and *roll it back* — just like git for code.

- **Every action is a commit** — SHA-256 content-addressable, hash-chained audit log
- **Branch & merge for agents** — Retry strategies, A/B testing, parallel exploration
- **Three-way merge** — Merkle-optimized JSON diffing (O(log N × M) vs O(N) for text VCS)
- **Multi-agent swarms** — DID-signed commits via FIDES, trust-gated merge, reputation scoring
- **9+ framework integrations** — Drop-in support for every major agent framework
- **Enterprise security** — AES-256-GCM encryption, RBAC, CSRF, PII masking, cosign-signed releases

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Applications                                │
│  Claude SDK · OpenAI · LangGraph · CrewAI · ADK · Vercel AI · MCP  │
│  Google A2A (Agent-to-Agent) · FIDES (Trusted Agent Protocol)       │
├─────────────────────────────────────────────────────────────────────┤
│  Python SDK          │  TypeScript SDK       │  Web Dashboard        │
│  PyO3 + fallback     │  napi-rs + fallback   │  Next.js 15 + React 19│
├─────────────────────────────────────────────────────────────────────┤
│                     Rust Core Engine                                │
│  SHA-256 DAG · Merkle diff · 3-way merge · Encryption · GC         │
├─────────────────────────────────────────────────────────────────────┤
│  SQLite (WAL)        │  PostgreSQL (Pool)    │  S3 + SQS             │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install from source
make dev

# Python
pip install agit

# Initialize a repository
agit init my-agent

# Commit agent state
agit commit -m "initial diagnosis"

# Branch for retry
agit branch retry-1

# View history
agit log

# Diff states
agit diff HEAD~1 HEAD

# Rollback
agit revert <hash>
```

## SDK Usage

### Python — ExecutionEngine

```python
from agit.engine.executor import ExecutionEngine

engine = ExecutionEngine("./my-repo", agent_id="my-agent")

# Commit state
engine.commit_state(
    {"memory": {"task": "research"}, "world_state": {"progress": 0.5}},
    message="research step 1",
    action_type="checkpoint",
)

# Branch, merge, revert
engine.branch("experiment-1")
engine.merge("experiment-1", strategy="three_way")
engine.revert(commit_hash)
```

### TypeScript — AgitClient

```typescript
import { AgitClient } from "@agit/sdk";

const client = new AgitClient({ path: "./my-repo", agentId: "my-agent" });

await client.commit({
  memory: { task: "research" },
  world_state: { progress: 0.5 },
  message: "research step 1",
});

await client.branch({ name: "experiment-1" });
await client.merge({ branch: "experiment-1", strategy: "three-way" });
```

## Framework Integrations

| Framework | Python | TypeScript | Description |
|-----------|--------|------------|-------------|
| **Claude SDK** | `AgitClaudeHooks` | `createAgitClaudeHooks()` | Pre/post tool call versioning |
| **OpenAI Agents** | `AgitAgentHooks` | `AgitAgentHooks` | Tool start/end + agent response tracking |
| **LangGraph** | `AgitCheckpointSaver` | `AgitCheckpointSaver` | Thread-aware checkpoint persistence |
| **CrewAI** | `agit_step_callback()` | — | Step and task callback wrappers |
| **Google ADK** | `AgitPlugin` | — | Before/after tool hooks |
| **Vercel AI** | `AgitVercelMiddleware` | `createAgitMiddleware()` | Generate/stream wrapping |
| **MCP** | `agit_mcp_server()` | `createAgitMcpServer()` | 8 MCP tools (commit, log, diff, branch...) |
| **Google A2A** | `AgitA2AExecutor` | `AgitA2AHooks` | A2A message versioning, branch-per-context |
| **FIDES** | `AgitFidesEngine` | `AgitFidesClient` | DID-signed commits, trust-gated merge |

### Multi-Agent Swarm with FIDES Trust

```python
from agit.integrations.fides import AgitFidesEngine

# Each agent gets a DID identity (Ed25519 keypair)
engine = AgitFidesEngine("./shared-repo", agent_id="research-agent")
await engine.init_identity(name="research-agent")

# Commits are signed with the agent's DID
engine.signed_commit(state, "research findings")

# Other agents verify identity before merging
result = await engine.trusted_merge("research-branch", min_trust_level=50)
# → {"merged": True, "trust_level": 75}
```

### A2A Protocol Integration

```python
from agit.integrations.a2a import AgitA2AExecutor

# Wrap any A2A executor with agit versioning
executor = AgitA2AExecutor(engine, inner_executor=my_executor)
# Every A2A message exchange is automatically committed
```

## Security

- **Rust core**: AES-256-GCM encryption + Argon2id KDF
- **Python fallback**: Fernet (PBKDF2HMAC + AES-128-CBC)
- **API**: RBAC (admin/write/read) + CSRF middleware + correlation IDs
- **Web**: CSP + HSTS + X-Frame-Options + Permissions-Policy
- **CI/CD**: TruffleHog secrets scanning + Trivy container scanning + cosign release signing + SBOM
- **Trust**: FIDES DID-signed commits + Ed25519 verification + trust-gated operations

## Known Limitations

| Area | Limitation | Workaround |
|------|-----------|------------|
| SQLite | ~1,000 RPS ceiling (single writer) | Use PostgreSQL for higher throughput |
| PostgreSQL | ~5,000 QPS with connection pool (16 conns) | Increase pool size, add read replicas |
| Consensus | No distributed consensus protocol | Use single-writer architecture |
| Sharding | No built-in data sharding | Partition by tenant/agent_id at app level |
| Large states | Memory-bound for states > 100MB | Use incremental checkpointing |
| Encryption | Python stubs use Fernet (not AES-256-GCM) | Use native Rust bindings for production |

For scaling guidance, see [DEPLOYMENT.md](./DEPLOYMENT.md#scaling-guidelines).

## Development

```bash
# Build everything
make build

# Run tests
make test

# Lint
make lint

# Run examples
python examples/fides_demo.py
python examples/a2a_demo.py
python examples/langgraph_demo.py
```

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — System design and data flow
- [DEPLOYMENT.md](./DEPLOYMENT.md) — Production deployment guide
- [SECURITY.md](./SECURITY.md) — Security policy and threat model
- [CONTRIBUTING.md](./CONTRIBUTING.md) — Development setup and guidelines
- [CHANGELOG.md](./CHANGELOG.md) — Version history

## License

MIT
