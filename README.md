# Kairos

> *Kairos* (Greek: καιρός) — the opportune moment.

**The right knowledge, at the right moment, for the right task.**

Kairos is a structured context system for AI agents working in multi-repo ecosystems. It transforms scattered codebase knowledge into queryable contracts that agents can discover semantically and consume via [MCP](https://modelcontextprotocol.io/).

## The Problem

Modern platforms span dozens of repositories. AI coding agents start every session cold — no understanding of how repos relate, what interfaces they share, or what gotchas will bite them. Current solutions (onboarding docs, README files, agent memory) either go stale silently or require expensive re-exploration every session.

## The Approach

Kairos implements the **D2W chain** (Data to Wisdom) for AI agent context:

| Layer | What | How |
|-------|------|-----|
| **Data** | Raw code scattered across repos | (your codebase) |
| **Information** | Structured YAML contracts | Schema-driven, versioned, per-repo |
| **Knowledge** | Semantic embeddings | Fine-grained vectors in sqlite-vec |
| **Wisdom** | Right knowledge → right agent → right moment | MCP tools for semantic discovery |

## How It Works

**1. Write contracts** — structured YAML files describing what each repo provides, consumes, and what will bite you (see the [Contract Authoring Guide](docs/contracts-guide.md) for how to write effective contracts):

```yaml
identity:
  name: compute
  purpose: "EC2 + Docker Swarm infrastructure with Traefik and Keycloak"

provides:
  cloudformation_exports:
    - name: "blueshift-compute-{env}-InstanceId"
      description: "EC2 instance ID for the Swarm manager"
  docker_networks:
    - name: blueshift_public
      scope: swarm

consumes:
  cloudformation_imports:
    - export: "blueshift-vpc-{env}-VpcId"
      from: vpc

gotchas:
  - severity: critical
    summary: "CDK user-data changes trigger EC2 replacement"
```

**2. Embed** — contracts are chunked into fine-grained semantic units and stored as vectors:

```bash
kairos embed          # YAML → chunks → vectors → sqlite-vec
```

**3. Query via MCP** — AI agents discover relevant contracts for their current task:

```
Agent: find_relevant_contracts("fix LDAP timeout in compute stack")
Kairos: → compute contract (direct match)
        → coppermind contract (secrets/auth dependency)
```

## Architecture

```
Contract YAML  →  Chunker  →  Embedder  →  sqlite-vec  →  MCP Server  →  AI Agent
(source of truth)  (semantic    (sentence-     (zero-daemon    (tools for      (Claude, Cursor,
                    units)      transformers)   vector store)   discovery)      any MCP client)
```

| Component | Technology | Why |
|-----------|-----------|-----|
| Contracts | YAML | Universal, human-readable, machine-parseable |
| Vectors | sqlite-vec | Zero-daemon, file-based, portable |
| Embeddings | sentence-transformers | Local, offline, no API costs |
| Interface | MCP | Standard protocol, works with any AI client |

## Installation

Requires Python 3.11+.

```bash
git clone git@github.com:Wave-Engineering/kairos.git
cd kairos
pip install -e .
```

Verify:

```bash
kairos --help
```

## Quickstart

```bash
# 1. Embed contracts into the vector database
kairos embed --contracts-dir contracts/repos --db contracts/contracts.db

# 2. Start the MCP server
kairos serve --contracts-dir contracts/repos --db contracts/contracts.db

# 3. Configure Claude Code (add to .claude/settings.local.json)
```

```json
{
  "mcpServers": {
    "kairos": {
      "command": "kairos",
      "args": [
        "serve",
        "--contracts-dir", "/absolute/path/to/contracts/repos",
        "--db", "/absolute/path/to/contracts/contracts.db"
      ]
    }
  }
}
```

See the full [Quickstart Guide](docs/quickstart.md) for a step-by-step walkthrough.

## Configuration

Kairos provides four CLI subcommands:

| Command | Description |
|---------|-------------|
| `kairos embed` | Embed contract chunks into a sqlite-vec database |
| `kairos serve` | Run the Kairos MCP server (stdio transport) |
| `kairos check-staleness` | Check contract staleness against git history |
| `kairos aggregate` | Generate a static Markdown digest from contracts |

See the full [Configuration Reference](docs/configuration.md) for all CLI flags, MCP tools, and directory layout.

## Status

**Alpha.** Core functionality is implemented: contract schema, chunker, embedder, MCP server with semantic search, staleness detection, and aggregation. See [docs/architecture.md](docs/architecture.md) for the technical internals reference and [docs/PRD.md](docs/PRD.md) for the historical product requirements document.

## License

Copyright (c) 2026 Oak and Wave, Inc. All rights reserved. See [LICENSE](LICENSE).
