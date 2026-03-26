# Configuration

This document covers how to configure Kairos for use with Claude Code and other MCP-compatible AI clients.

## Claude Code MCP Configuration

The easiest way to configure Claude Code is with `kairos install`:

```bash
kairos install --contracts-dir contracts/repos --db contracts/contracts.db
```

This writes the correct JSON to `.mcp.json` (or `~/.claude.json` with `--scope user`), resolving all paths to absolute. See the [`kairos install`](#kairos-install) CLI reference below.

Alternatively, manually add the following to `.mcp.json` (per-project) or `~/.claude.json` (global):

```json
{
  "mcpServers": {
    "kairos": {
      "command": "kairos",
      "args": [
        "serve",
        "--contracts-dir", "/absolute/path/to/contracts/repos",
        "--db", "/absolute/path/to/contracts/contracts.db",
        "--workspace", "/absolute/path/to/workspace"
      ]
    }
  }
}
```

**Parameter reference:**

| Argument | Required | Description |
|----------|----------|-------------|
| `--contracts-dir` | Yes | Directory containing contract YAML files |
| `--db` | Yes | Path to the sqlite-vec database (created by `kairos embed`) |
| `--workspace` | No | Root directory containing git repositories (enables staleness checks) |

The `--workspace` flag is optional. If omitted, the `check_staleness` MCP tool will return an error message when invoked. All other tools (semantic search, get contract, list contracts) work without it.

**Transport:** Kairos uses stdio transport. The MCP client spawns the `kairos serve` process and communicates over stdin/stdout.

## CLI Reference

Kairos provides five subcommands. Run any with `--help` for full usage.

### `kairos embed`

Reads contract YAML files, chunks them into semantic units, generates embeddings with sentence-transformers, and stores them in a sqlite-vec database.

```
kairos embed --contracts-dir <path> --db <path>
```

| Flag | Required | Description |
|------|----------|-------------|
| `--contracts-dir` | Yes | Directory containing contract YAML files |
| `--db` | Yes | Path to the sqlite-vec database file (created if it does not exist) |

**Example:**

```bash
kairos embed --contracts-dir contracts/repos --db contracts/contracts.db
```

### `kairos check-staleness`

Compares each contract's `verified_at_commit` against the current git history to detect contracts that may be out of date.

```
kairos check-staleness --contracts-dir <path> --workspace <path>
```

| Flag | Required | Description |
|------|----------|-------------|
| `--contracts-dir` | Yes | Directory containing contract YAML files |
| `--workspace` | Yes | Root directory containing git repositories (each repo in a subdirectory matching the contract's `full_name`) |

**Example:**

```bash
kairos check-staleness --contracts-dir contracts/repos --workspace ~/projects
```

Output is a table showing each contract's staleness status: `CURRENT`, `STALE`, or `UNKNOWN`.

### `kairos aggregate`

Generates a static Markdown digest from all contract files. Useful for human review or inclusion in documentation.

```
kairos aggregate --contracts-dir <path> --output <path>
```

| Flag | Required | Description |
|------|----------|-------------|
| `--contracts-dir` | Yes | Directory containing contract YAML files |
| `--output` | Yes | Path to write the output Markdown file |

**Example:**

```bash
kairos aggregate --contracts-dir contracts/repos --output docs/contracts-digest.md
```

### `kairos serve`

Starts the Kairos MCP server using stdio transport. This is the command used in MCP client configuration.

```
kairos serve --contracts-dir <path> --db <path> [--workspace <path>]
```

| Flag | Required | Description |
|------|----------|-------------|
| `--contracts-dir` | Yes | Directory containing contract YAML files |
| `--db` | Yes | Path to the sqlite-vec database file |
| `--workspace` | No | Root directory containing git repositories (enables staleness checks) |

**MCP tools exposed:**

| Tool | Description |
|------|-------------|
| `find_relevant_contracts` | Semantic search — finds contracts relevant to a natural-language query |
| `get_contract` | Returns the full YAML for a specific contract by repo name |
| `list_contracts` | Lists all loaded contracts with identity summaries |
| `check_staleness` | Checks whether contracts are stale relative to git history |

### `kairos install`

Adds the Kairos MCP server configuration to a Claude Code MCP config file. Resolves all paths to absolute and preserves any existing MCP servers in the file.

```
kairos install --contracts-dir <path> --db <path> [--scope project|user]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--contracts-dir` | Yes | — | Directory containing contract YAML files |
| `--db` | Yes | — | Path to the sqlite-vec database file |
| `--scope` | No | `project` | `project` writes `.mcp.json` in the current directory; `user` writes `~/.claude.json` |

**Examples:**

```bash
# Add to project config (most common)
kairos install --contracts-dir contracts/repos --db contracts/contracts.db

# Add to user-level config (available in all projects)
kairos install --scope user --contracts-dir contracts/repos --db contracts/contracts.db
```

**Behavior:**
- Creates the config file (and parent directory for user scope) if it doesn't exist.
- Merges `mcpServers.kairos` into the config without touching other configured MCP servers.
- If a `kairos` entry already exists, it is updated with the new paths.
- Errors cleanly if the existing settings file contains malformed JSON.

## Directory Layout

A typical Kairos-enabled workspace looks like this:

```
workspace/
  contracts/
    repos/              # Contract YAML files (one per repository)
      compute.yaml
      vpc.yaml
      manifests.yaml
    schema.yaml         # JSON Schema for contract validation
    templates/
      contract-template.yaml   # Starter template for new contracts
    contracts.db        # sqlite-vec database (generated by kairos embed)
  blueshift-compute/    # Git repositories (used by staleness checks)
  blueshift-vpc/
  blueshift-manifests/
```

**Key points:**

- Contract YAML files live in `contracts/repos/` (or any directory you point `--contracts-dir` at).
- The sqlite-vec database is generated by `kairos embed` and should be listed in `.gitignore`.
- The `--workspace` path should be the parent directory that contains the git repositories referenced by contracts. Each repo directory name must match the contract's `identity.full_name` field.
- The contract template at `contracts/templates/contract-template.yaml` provides a starting point for writing new contracts.

## See Also

- [Quickstart Guide](quickstart.md) -- step-by-step first-use walkthrough
- [Contract Authoring Guide](contracts-guide.md) -- how to write effective contracts
- [Architecture Reference](architecture.md) -- technical internals and design decisions
