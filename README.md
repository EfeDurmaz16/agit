[![CI](https://github.com/anthropics/agit/actions/workflows/ci.yml/badge.svg)](https://github.com/anthropics/agit/actions/workflows/ci.yml)

# AgentGit (agit)

Git-like version control for AI agents. Every agent action is a commit -- diffable, revertable, auditable.

## Architecture

- **Rust core** (`crates/agit-core`): High-performance VCS engine (SHA-256, DAG, storage)
- **Python SDK** (`python/agit`): CLI, execution engine, integrations
- **TypeScript SDK** (`ts-sdk`): Node.js bindings via napi-rs

## Quick Start

```bash
# Install from source
make dev

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

## SDK Integrations

- Google ADK
- OpenAI Agents SDK
- Claude Agent SDK
- Vercel AI SDK
- LangGraph
- CrewAI
- MCP Server

## Development

```bash
# Build everything
make build

# Run tests
make test

# Lint
make lint
```

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

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — System design and data flow
- [DEPLOYMENT.md](./DEPLOYMENT.md) — Production deployment guide
- [SECURITY.md](./SECURITY.md) — Security policy and threat model
- [CONTRIBUTING.md](./CONTRIBUTING.md) — Development setup and guidelines
- [CHANGELOG.md](./CHANGELOG.md) — Version history

## License

MIT
