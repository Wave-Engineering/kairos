# Quickstart

This guide walks through installing Kairos, writing your first contract, embedding it, starting the MCP server, and querying from Claude Code.

## Prerequisites

- Python 3.11 or later
- Git (for staleness checks)
- An MCP-compatible AI client (e.g., Claude Code)

## 1. Install Kairos

Clone the repository and install in editable mode:

```bash
git clone git@github.com:Wave-Engineering/kairos.git
cd kairos
pip install -e .
```

Verify the installation:

```bash
kairos --help
```

You should see the top-level help with the available subcommands: `embed`, `check-staleness`, `aggregate`, and `serve`.

## 2. Write Your First Contract

Copy the contract template to the contracts directory:

```bash
cp contracts/templates/contract-template.yaml contracts/repos/my-service.yaml
```

Open `contracts/repos/my-service.yaml` and fill in the fields. Here is a minimal working example:

```yaml
contract_version: "0.1.0"

identity:
  name: my-service
  full_name: org-my-service
  category: application
  purpose: >
    A web API that processes customer orders and publishes events
    to the shared message bus.
  archetype: swarm-service

provides:
  docker_images:
    - name: my-service
      registry: harbor.example.com
      description: "Order processing API container image"
  docker_networks: []
  cloudformation_exports: []
  packages: []
  secrets: []
  ci_templates: []

consumes:
  docker_images:
    - name: postgres
      source: "postgres:16"
  cloudformation_imports: []
  secrets: []
  repos:
    - name: shared-infra
      relationship: "Deploys onto infrastructure provisioned by this repo"

interfaces:
  api_endpoints:
    - url: "orders.{DOMAIN}/api/v1"
      service: my-service
      description: "REST API for order management"
  compose_variables:
    - name: DOMAIN
      description: "Base domain for the environment"

operational:
  tech_stack:
    language: python
    framework: fastapi
  validation_command: "make lint"
  test_command: "make test"
  deploy_trigger:
    dev: "push to release/* branch"
    test: "rc tag"
    prod: "v tag"
  environments:
    - dev
    - test
    - prod

gotchas:
  - severity: high
    summary: "Database migrations must run before deploy"
    detail: >
      The service expects the database schema to match the current code.
      Run alembic upgrade head before deploying a new version, or the
      service will fail to start with a schema mismatch error.

staleness_paths:
  - "src/**"
  - "Dockerfile"
  - "docker-compose*.yml"

last_verified: "2026-01-01"
verified_at_commit: "abc1234"
```

See `contracts/templates/contract-template.yaml` for the full template with all fields documented.

## 3. Embed Contracts

Generate the vector database from your contract files:

```bash
kairos embed --contracts-dir contracts/repos --db contracts/contracts.db
```

Output:

```
Embedded 42 chunks across 1 contracts into /path/to/contracts/contracts.db
```

The first run downloads the `all-MiniLM-L6-v2` sentence-transformers model (~80 MB). Subsequent runs use the cached model.

Re-run this command whenever you add or update contracts.

## 4. Start the MCP Server

Test the server manually to verify everything works:

```bash
kairos serve --contracts-dir contracts/repos --db contracts/contracts.db
```

The server starts on stdio transport and waits for MCP messages. Press `Ctrl+C` to stop.

To enable staleness checks, add the `--workspace` flag pointing to the directory that contains your git repositories:

```bash
kairos serve \
  --contracts-dir contracts/repos \
  --db contracts/contracts.db \
  --workspace ~/projects
```

## 5. Configure Claude Code

Add the Kairos MCP server to your Claude Code project configuration. Create or edit `.claude/settings.local.json`:

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

Replace the paths with absolute paths to your contracts directory, database, and workspace.

## 6. Query from Claude Code

Once configured, Claude Code can use the Kairos MCP tools during a session. The available tools are:

- **`find_relevant_contracts`** -- Semantic search. Ask a natural-language question and get the most relevant contracts.
- **`get_contract`** -- Retrieve the full contract for a specific repository by name.
- **`list_contracts`** -- List all loaded contracts with their identity summaries.
- **`check_staleness`** -- Check whether contracts are stale relative to their git repositories.

Example interaction in a Claude Code session:

```
You: Fix the LDAP timeout in the compute stack.

Claude: [calls find_relevant_contracts("LDAP timeout compute stack")]
  -> Returns compute contract (direct match) and coppermind contract (auth dependency)

Claude: [calls get_contract("compute")]
  -> Returns full compute contract YAML with gotchas, interfaces, and dependencies
```

## Next Steps

- Read the full [Configuration Reference](configuration.md) for all CLI flags and MCP tools.
- Use `kairos check-staleness` in CI to detect contracts that need review.
- Use `kairos aggregate` to generate a Markdown digest for human review.
