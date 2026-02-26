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

## License

MIT
