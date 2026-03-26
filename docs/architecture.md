# Kairos Architecture and Internals Reference

> **Audience:** Developers (human or AI) who need to understand how kairos works internally.
> This is a technical reference, not a tutorial. For usage, see [quickstart.md](quickstart.md).
> For contract authoring guidance, see [contracts-guide.md](contracts-guide.md).
> For CLI flags and MCP tool configuration, see [configuration.md](configuration.md).

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Contract Schema Design](#2-contract-schema-design)
3. [Chunking Strategy](#3-chunking-strategy)
4. [Embedding Pipeline](#4-embedding-pipeline)
5. [MCP Server Architecture](#5-mcp-server-architecture)
6. [Staleness Detection](#6-staleness-detection)
7. [CLI Architecture](#7-cli-architecture)
8. [Key Design Decisions Log](#8-key-design-decisions-log)

---

## 1. System Overview

### The D2W Chain

Kairos exists because of a specific problem: AI agents working in multi-repo ecosystems start every session cold. The conceptual framework behind kairos is the **D2W chain** (Data to Wisdom) -- the progressive refinement of raw material into actionable understanding:

```
Data           Information        Knowledge          Wisdom
(raw code)  -> (YAML contracts) -> (vector embeddings) -> (MCP tool responses)

Disorganized    Structured per-repo   Semantic vectors     Right knowledge
intentional     descriptions of       that capture what    delivered to the
markings        roles & interfaces    things *mean*        right agent at
                                                           the right moment
```

Wisdom -- the application layer -- is the only thing that makes the preceding layers valuable. Without it, organized knowledge just sits in files that agents may or may not read.

### Component Diagram

```
contracts/repos/*.yaml         kairos/chunker.py        kairos/embed.py
 (source of truth)               (decomposition)          (vectorization)
        |                             |                        |
        v                             v                        v
  Contract.from_yaml()  --->  chunk_contract()  --->  embed_contracts()
        |                             |                        |
        |                    list[Chunk]                       |
        |                                                      v
        |                                            contracts.db (sqlite-vec)
        |                                                      |
        v                                                      v
  kairos/server.py  <--  create_server()  -->  search() + _load_contracts()
        |
        v
  FastMCP("kairos")
    |-- find_relevant_contracts(query, top_k)
    |-- get_contract(repo_name)
    |-- list_contracts()
    '-- check_staleness(repo_name)
        |
        v
  AI Agent (Claude Code, Cursor, any MCP client)
```

### Data Flow

```
YAML file  -->  Contract dataclass  -->  list[Chunk]  -->  float[384] vectors
                                                                |
                                                                v
                                                      chunks_vec (vec0 virtual table)
                                                      chunks_meta (id, repo_name, section, field_path, text)
                                                                |
                                                                v
                                              search(query) --> list[(Chunk, distance)]
                                                                |
                                                                v
                                              MCP tool response (formatted text + YAML)
```

### File Layout

```
kairos/
  kairos/
    __init__.py
    models.py          # Contract, ContractIdentity, Chunk, StalenessReport dataclasses
    schema.py          # JSON Schema validation via jsonschema library
    chunker.py         # Contract -> list[Chunk] decomposition
    embed.py           # Chunk -> vector embedding + sqlite-vec storage + search
    aggregate.py       # Static markdown digest generation
    staleness.py       # Git-based contract freshness detection
    server.py          # FastMCP server with 4 tools
    cli.py             # argparse CLI with 4 subcommands
  contracts/
    schema.yaml        # JSON Schema for contract YAML files
    templates/
      contract-template.yaml
    repos/             # Production contracts (one per repo)
      compute.yaml
      vpc.yaml
      littleguy.yaml
      manifests.yaml
  tests/
    fixtures/
      sample-contracts/    # Test YAML files
      aggregate-contracts/ # Test fixtures for aggregation
    test_schema.py
    test_chunker.py
    test_embed.py
    test_aggregate.py
    test_staleness.py
    test_server.py
    test_server_staleness.py
    test_server_lifespan.py
    test_cli_e2e.py
    test_smoke.py
  docs/
    PRD.md             # Historical product requirements (Waves 1-6)
    architecture.md    # This document
    contracts-guide.md # How to write effective contracts
    quickstart.md      # Getting started guide
    configuration.md   # CLI flags, MCP tools, directory layout
```

---

## 2. Contract Schema Design

**Schema file:** `contracts/schema.yaml`
**Validation module:** `kairos/schema.py`

### Why YAML over JSON

Contracts are authored and reviewed by humans. YAML supports:
- Inline comments explaining field values
- Multi-line strings (`>` and `|`) for purpose and detail fields
- Cleaner diffs in pull requests (no trailing commas, fewer brackets)

### Schema Evolution Strategy

The `contract_version` field (required, string) enables future schema migration. Currently all contracts use `"0.1.0"`. The schema is defined as JSON Schema Draft 2020-12 and validated using the `jsonschema` Python library via `jsonschema.Draft202012Validator`.

### Identity Model

Every contract has a required `identity` section with five required fields:

| Field | Purpose | Example |
|-------|---------|---------|
| `name` | Short lookup key, used as the primary identifier throughout kairos | `"compute"` |
| `full_name` | Full repository name (matches git repo name) | `"blueshift-compute"` |
| `category` | Logical grouping for sorting and filtering | `"infrastructure"` |
| `purpose` | One-paragraph description of what the repo does and why | (multi-line) |
| `archetype` | Architectural pattern -- constrains to a fixed enum | `"cdk-infra"` |

The `archetype` enum currently includes: `cdk-infra`, `swarm-service`, `compose-standalone`, `config-only`, `docs-only`, `meta-tooling`, `library`.

### Section-by-Section Rationale

| Section | Required | Description |
|---------|----------|-------------|
| `contract_version` | Yes | Schema version for future migration |
| `identity` | Yes | Core identity -- the only mandatory content section |
| `provides` | No | What this repo exports: CF exports, images, networks, secrets, packages, CI templates |
| `consumes` | No | What this repo imports: CF imports (with `from` field linking to provider), images, secrets, repo relationships |
| `interfaces` | No | How other systems interact: API endpoints, compose variables |
| `operational` | No | How to work in the repo: tech stack, validation/test commands, deploy triggers, environments |
| `gotchas` | No | Non-obvious traps with severity (critical/high/medium/low), summary, and detail |
| `staleness_paths` | No | File globs to monitor for freshness detection |
| `last_verified` | No | ISO 8601 date of last human verification |
| `verified_at_commit` | No | Git SHA at time of verification |

### Forward Compatibility

The root-level schema sets `additionalProperties: true`. This means contracts can include fields not defined in the schema without breaking validation. This is deliberate -- it allows incremental schema evolution without requiring all contracts to update simultaneously.

Note: individual sections (e.g., `identity`, `provides`) set `additionalProperties: false` to catch typos in known fields. The forward-compatibility affordance is at the root level only.

### Validation

`kairos/schema.py` provides `validate_contract(yaml_path, schema_path)` which returns a `list[ValidationError]`. Each `ValidationError` is a dataclass with `field_path` (dot-separated), `message`, and `severity`. An empty list means the contract is valid.

The schema path defaults to `contracts/schema.yaml` relative to the project root (resolved via `Path(__file__).resolve().parent.parent / "contracts"` in `schema.py`).

---

## 3. Chunking Strategy

**Module:** `kairos/chunker.py`
**Entry point:** `chunk_contract(contract: Contract) -> list[Chunk]`

### Why Fine-Grained

Kairos embeds one vector per semantic unit, not one per contract. This means "LDAP timeout" matches the *specific gotcha* about connection handling, not the entire contract because it mentions LDAP somewhere. The trade-off: more vectors means better recall at the cost of more storage and slightly slower search. At prototype scale (~200-1000 vectors), this trade-off is negligible.

### The 12 Chunk Types

Each chunk type corresponds to a semantic unit extracted from a contract section:

| # | Source | Text Template | Section | Field Path |
|---|--------|---------------|---------|------------|
| 1 | `identity.purpose` | `"{name}: {purpose}"` | `identity` | `identity.purpose` |
| 2 | `provides.cloudformation_exports[i]` | `"{name} provides CloudFormation export {export_name}: {description}"` | `provides` | `provides.cloudformation_exports[i]` |
| 3 | `provides.docker_images[i]` | `"{name} builds Docker image {image_name}: {description}"` | `provides` | `provides.docker_images[i]` |
| 4 | `provides.docker_networks[i]` | `"{name} creates Docker network {network_name} ({scope}): {description}"` | `provides` | `provides.docker_networks[i]` |
| 5 | `provides.secrets[i]` | `"{name} manages secret at {path}: {description}"` | `provides` | `provides.secrets[i]` |
| 6 | `consumes.cloudformation_imports[i]` | `"{name} consumes CloudFormation export {export} from {from}: {description}"` | `consumes` | `consumes.cloudformation_imports[i]` |
| 7 | `consumes.docker_images[i]` | `"{name} uses Docker image {image_name} from {source}"` | `consumes` | `consumes.docker_images[i]` |
| 8 | `consumes.secrets[i]` | `"{name} reads secret at {path} from {from}: {description}"` | `consumes` | `consumes.secrets[i]` |
| 9 | `consumes.repos[i]` | `"{name} depends on {repo}: {relationship}"` | `consumes` | `consumes.repos[i]` |
| 10 | `interfaces.api_endpoints[i]` | `"{name} exposes {service} at {url}: {description}"` | `interfaces` | `interfaces.api_endpoints[i]` |
| 11 | `gotchas[i]` | `"{name} gotcha ({severity}): {summary}. {detail}"` | `gotchas` | `gotchas[i]` |
| 12 | `operational` | `"{name} uses {language}/{framework}, validate: {validation_command}, test: {test_command}"` | `operational` | `operational` |

### Metadata Preservation

Each `Chunk` dataclass carries four fields:

- `text` -- the natural-language sentence generated from the template above
- `repo_name` -- the contract's `identity.name` (for deduplication and traceability)
- `section` -- which contract section the chunk came from (e.g., `"provides"`, `"gotchas"`)
- `field_path` -- dot/bracket notation path to the source field (e.g., `"provides.cloudformation_exports[0]"`)

This metadata survives embedding and is stored alongside vectors in `chunks_meta`. It allows MCP tools to report *why* a contract matched and where in the contract the match originated.

### Rules

- Empty arrays produce zero chunks (no noise vectors).
- Missing optional sections produce zero chunks.
- The `operational` section produces a single combined chunk (not one per sub-field).
- Each chunk text includes the repo name as a prefix for context during embedding.

---

## 4. Embedding Pipeline

**Module:** `kairos/embed.py`
**Entry points:** `embed_contracts()` and `search()`

### Model Choice: all-MiniLM-L6-v2

| Property | Value |
|----------|-------|
| Dimensions | 384 |
| Size | ~80MB |
| Library | sentence-transformers |
| Inference | Local CPU, no API calls |

**Why local inference:** Zero-daemon architecture, no API costs, no network dependency, air-gap compatible. The contract corpus is small enough (~100-1000 vectors) that local inference performs well.

**Why this model:** Best quality-to-speed ratio at small size, well-benchmarked for semantic similarity tasks. The 384-dimension output is compact enough for sqlite-vec while maintaining good discrimination.

**When to consider upgrading:** If the contract corpus exceeds ~10K chunks and search quality degrades, consider a larger model (e.g., all-mpnet-base-v2 at 768-dim). This would require regenerating all embeddings and updating the virtual table schema.

### sqlite-vec Integration

**Why sqlite over alternatives:**

| Alternative | Rejection Reason |
|-------------|-----------------|
| FAISS | No metadata storage -- would need a separate DB for chunk metadata |
| ChromaDB | Requires a daemon process, violates zero-daemon constraint |
| Pinecone / Voyage AI | External API, introduces cost and network dependency |

sqlite-vec is a SQLite extension that adds vector search via virtual tables. It is a library, not a server -- the database is a single file.

**Database schema:**

```sql
-- Vector index (vec0 virtual table)
CREATE VIRTUAL TABLE chunks_vec USING vec0(embedding float[384]);

-- Metadata table (standard SQLite)
CREATE TABLE chunks_meta(
    id INTEGER PRIMARY KEY,
    repo_name TEXT,
    section TEXT,
    field_path TEXT,
    text TEXT
);
```

Vectors and metadata are linked by matching rowid/id. The `embed_contracts()` function inserts them with matching integer keys (starting at 1).

**Full re-embed on each run:** `embed_contracts()` drops and recreates both tables on every invocation. This is idempotent and simple -- there is no incremental update logic. At prototype scale, a full re-embed takes seconds.

### embed_contracts()

```python
def embed_contracts(
    contracts_dir: Path,
    db_path: Path,
    model_name: str = "all-MiniLM-L6-v2",
) -> tuple[int, int]:
```

1. Loads the sentence-transformers model (lazy import inside function body).
2. Iterates `*.yaml` files in `contracts_dir`, parsing each with `Contract.from_yaml()`.
3. Skips invalid contracts with a warning to stderr (does not abort the run).
4. Calls `chunk_contract()` on each valid contract, collecting all chunks.
5. Batch-encodes all chunk texts with `model.encode()`.
6. Opens sqlite-vec connection, drops/recreates tables via `_init_db()`.
7. Inserts metadata and serialized vectors with matching rowids.
8. Returns `(total_chunks, total_contracts)`.

### search()

```python
def search(
    query: str,
    model: object,
    db_path: Path,
    top_k: int = 10,
    conn: sqlite3.Connection | None = None,
) -> list[tuple[Chunk, float]]:
```

1. Encodes the query with the same model used for embedding.
2. If no `conn` is provided, opens a new sqlite-vec connection (and closes it after).
3. Queries `chunks_vec` with `WHERE embedding MATCH ? ORDER BY distance LIMIT ?`.
4. Joins with `chunks_meta` by rowid to reconstruct `Chunk` objects.
5. Returns `(Chunk, distance)` tuples ordered by ascending distance (lower = more similar).

The optional `conn` parameter enables connection reuse -- the MCP server holds a single connection for its entire session lifetime, passing it to each `search()` call to avoid per-query connection overhead.

### Vector Serialization

`_serialize_f32(vector)` packs a list of floats into a compact binary format using `struct.pack(f"{len(vector)}f", *vector)`. This is the format sqlite-vec expects for vector insertion and query matching.

---

## 5. MCP Server Architecture

**Module:** `kairos/server.py`
**Entry point:** `create_server(contracts_dir, db_path, workspace_path) -> FastMCP`

### FastMCP SDK

The server uses the `mcp` Python SDK's `FastMCP` class. Tools are registered via the `@mcp.tool()` decorator. The server runs on stdio transport (`server.run(transport="stdio")`), which is the standard MCP transport for local tools.

### The `_kairos_state` Pattern

State management follows a specific pattern driven by a testing constraint:

```python
state: dict[str, Any] = {}

@asynccontextmanager
async def lifespan(server: FastMCP):
    state["contracts"] = _load_contracts(contracts_dir)
    state["model"] = SentenceTransformer("all-MiniLM-L6-v2")
    state["conn"] = _open_vec_connection(db_path)
    state["workspace_path"] = workspace_path
    yield state
    state["conn"].close()

mcp = FastMCP("kairos", lifespan=lifespan)
mcp._kairos_state = state  # testing workaround
```

**Why this pattern:** FastMCP 1.26.0 has no public session or test API. The lifespan context manager populates the `state` dict, and tools read from it via closure. To enable test code to pre-populate state without running the full lifespan (which requires an MCP client connection), the `state` dict is also attached to the `FastMCP` instance as `_kairos_state`. Test files can set `mcp._kairos_state["contracts"] = {...}` directly.

### Connection Reuse

The sqlite-vec connection is opened once in the lifespan and held for the entire server session. All `search()` calls receive this connection via the `conn` parameter, avoiding per-query connection overhead. The connection is closed when the lifespan context exits.

### The 4 Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `find_relevant_contracts` | `query: str, top_k: int = 3` | Formatted text with matched chunk context + full contract YAML for top-K repos |
| `get_contract` | `repo_name: str` | Full contract YAML as string, or error with available repo names |
| `list_contracts` | (none) | YAML list of identity objects for all loaded contracts |
| `check_staleness` | `repo_name: str \| None = None` | Formatted staleness report (single repo or all repos) |

**`find_relevant_contracts` query pattern:**

1. Calls `search()` with `top_k * 5` to get extra results for deduplication headroom.
2. Deduplicates by `repo_name` -- keeps only the best-matching (lowest distance) chunk per repo.
3. Sorts deduplicated results by distance ascending.
4. Takes the top `top_k` repos.
5. For each repo, includes the matched chunk text (explaining *why* it matched) and the full contract YAML.

**`check_staleness` behavior:**

- With `repo_name`: checks a single contract using `staleness.check_staleness()`.
- Without `repo_name`: checks all contracts using `staleness.check_all_staleness()`.
- Returns an error if `workspace_path` was not configured at server start.

### Helper Functions

- `_load_contracts(contracts_dir)` -- loads all `*.yaml` files into a `dict[str, Contract]` keyed by `identity.name`. Skips unparseable files silently.
- `_open_vec_connection(db_path)` -- opens a sqlite connection and loads the sqlite-vec extension. Lazy-imports `sqlite_vec`.
- `_format_staleness_report(report)` -- formats a `StalenessReport` as human-readable markdown text with status, message, changed files, and commit count.

---

## 6. Staleness Detection

**Module:** `kairos/staleness.py`
**Entry points:** `check_staleness()` and `check_all_staleness()`

### Approach: Real Git Subprocess

Staleness detection uses `subprocess.run()` to call git directly. Not libgit2, not dulwich. Rationale: git is always available in development environments, there is no extra dependency, and the API surface needed (rev-parse, cat-file, rev-list, diff) is small and stable.

All git commands use `git -C <repo_path>` to operate on the target repo without changing the working directory.

### check_staleness()

```python
def check_staleness(contract: Contract, repo_path: Path) -> StalenessReport
```

The function follows a guard-clause pattern:

1. **Repo exists?** If `repo_path` is not a directory or not a git repo -> `UNKNOWN("Repo not found")`.
2. **Has verified_at_commit?** If the contract has no `verified_at_commit` -> `UNKNOWN("No verified_at_commit in contract")`.
3. **Can resolve HEAD?** If `git rev-parse HEAD` fails -> `UNKNOWN("Could not determine HEAD")`.
4. **HEAD matches verified?** If HEAD SHA matches `verified_at_commit` (prefix match in either direction) -> `CURRENT("HEAD matches verified_at_commit")`.
5. **Verified commit exists in repo?** If `git cat-file -t` fails -> `UNKNOWN("verified_at_commit not found in repo")`.
6. **Count commits since:** `git rev-list --count {verified}..HEAD`.
7. **Has staleness_paths?** If no `staleness_paths` defined -> `CURRENT("No staleness_paths defined")`.
8. **Check each path:** For each glob in `staleness_paths`, run `git diff --name-only {verified}..HEAD -- {glob}`.
9. **Changed files found?** If any files changed -> `STALE` with file list and commit count. Otherwise -> `CURRENT`.

### Three States

| Status | Meaning |
|--------|---------|
| `CURRENT` | No changes in staleness paths since verified commit, or HEAD matches verified commit |
| `STALE` | Files matching staleness paths have changed since verified commit |
| `UNKNOWN` | Cannot determine staleness (repo not found, no verified commit, commit not in history) |

### check_all_staleness()

```python
def check_all_staleness(contracts_dir: Path, workspace_path: Path) -> dict[str, StalenessReport]
```

Iterates all `*.yaml` files in `contracts_dir`, parses each as a `Contract`, derives the repo path as `workspace_path / contract.identity.full_name`, and calls `check_staleness()` on each. Returns a dict mapping `identity.name` to its report.

### Why workspace_path is Optional

The MCP server accepts `workspace_path` as an optional parameter. If not provided, the `check_staleness` tool returns an error message explaining how to set it. This allows the server to run without filesystem access to the actual repos (e.g., in a CI environment where only the contracts and database are available). The `find_relevant_contracts`, `get_contract`, and `list_contracts` tools work without `workspace_path`.

---

## 7. CLI Architecture

**Module:** `kairos/cli.py`
**Entry point:** `main(argv: list[str] | None = None) -> int`

### Subcommands

The CLI uses `argparse` with subcommands:

| Subcommand | Handler | Description |
|------------|---------|-------------|
| `kairos embed` | `_cmd_embed(args)` | Embed contract chunks into sqlite-vec |
| `kairos serve` | `_cmd_serve(args)` | Start the MCP server (stdio transport) |
| `kairos check-staleness` | `_cmd_check_staleness(args)` | Check contract staleness against git |
| `kairos aggregate` | `_cmd_aggregate(args)` | Generate static markdown digest |

### Return Codes

- `0` -- success
- `1` -- error (missing directory, database not found, stale contracts detected by check-staleness)

### Lazy Imports

Heavy dependencies are imported inside function bodies, not at module level:

- `sentence_transformers.SentenceTransformer` -- imported inside `embed_contracts()` and the server lifespan
- `sqlite_vec` -- imported inside `embed_contracts()`, `search()`, and `_open_vec_connection()`

This keeps the CLI responsive for subcommands that do not need these dependencies (e.g., `kairos aggregate` does not load the embedding model).

The `serve` subcommand handler (`_cmd_serve`) also uses a lazy import: `from kairos.server import main as serve_main` is inside the function body, deferring the FastMCP import until the serve subcommand is actually invoked.

### Color Output

The `check-staleness` subcommand uses ANSI color codes for terminal output:
- Green for `CURRENT`
- Yellow for `STALE`
- Red for `UNKNOWN`

Colors are automatically disabled when stdout is not a terminal (`sys.stdout.isatty()` check).

---

## 8. Key Design Decisions Log

Numbered list of non-obvious choices made during kairos development. These decisions were made during the prototype phase (Waves 1-6) and capture rationale that would otherwise be lost between sessions.

### D1. D2W Chain as Conceptual Framework

**Decision:** Structure kairos around the Data-to-Wisdom chain (Data -> Information -> Knowledge -> Wisdom).

**Alternatives:** Generic "context management" framing; RAG-first approach.

**Rationale:** The D2W chain provides a clear mental model for why each component exists. Contracts are the Information layer (structured from raw Data). Embeddings are the Knowledge layer (semantic meaning extracted from Information). MCP tools are the Wisdom layer (delivering the right Knowledge to the right agent at the right moment). This framing guides feature prioritization -- if a feature does not advance the chain, it is out of scope.

### D2. YAML Contracts Centralized in Devkit

**Decision:** Store all contracts in `contracts/repos/` inside the kairos repository, not in each individual repo.

**Alternatives:** Per-repo contracts (each repo stores its own `CONTRACT.yaml`); hybrid (template in kairos, instances in repos).

**Rationale:** Chosen for prototype simplicity. Centralized contracts avoid cross-repo MRs when updating the schema or doing bulk edits. A single `kairos embed` run processes all contracts from one directory. The trade-off is that contract updates require a kairos repo commit, not a commit in the described repo. For a production system with many contributors, per-repo contracts with a collection pipeline would scale better, but that complexity is not justified at prototype scale.

### D3. Fine-Grained Embedding (One Vector per Semantic Unit)

**Decision:** Embed one vector per semantic unit (each CF export, each gotcha, each API endpoint), not one per contract.

**Alternatives:** One vector per contract (coarse); one per section (medium).

**Rationale:** Coarse embedding degrades to fuzzy keyword matching -- a query about "LDAP timeout" would match an entire contract because it mentions LDAP somewhere, with no way to distinguish which part matched. Fine-grained embedding means the specific gotcha about LDAP connection handling gets its own vector and matches precisely. The cost is more vectors (~5-15 per contract vs 1), but at the expected scale (~20-100 repos), this is trivial for sqlite-vec.

### D4. sqlite-vec + Local sentence-transformers

**Decision:** Use sqlite-vec for vector storage and all-MiniLM-L6-v2 via sentence-transformers for local embedding.

**Alternatives considered:**

| Option | Rejection Reason |
|--------|-----------------|
| FAISS | No metadata storage -- would need a separate database for chunk metadata, adding complexity |
| ChromaDB | Requires a daemon process, violating the zero-daemon architecture constraint |
| Voyage AI / OpenAI embeddings | External API introduces cost, network dependency, and data exfiltration concerns |
| Pinecone | Cloud-hosted, violates zero-daemon and offline constraints |

**Rationale:** sqlite-vec is a library (not a server), stores vectors and metadata in a single file, requires no background process, and handles the expected scale trivially. sentence-transformers with all-MiniLM-L6-v2 provides 384-dimension vectors with good semantic quality, runs on CPU, and requires no API calls.

### D5. MCP Server (Not Skills)

**Decision:** Expose kairos as an MCP server with tools, not as a Claude Code Skills directory.

**Alternatives:** Skills (file-based, Claude Code-specific); direct CLI integration; REST API.

**Rationale:** MCP is the standard protocol for AI agent tool integration. An MCP server works with any MCP-compatible client (Claude Code, Cursor, future clients) without per-client implementation. The session lifecycle of an MCP server (start with agent session, hold state, stop when session ends) matches the connection model naturally. Skills would be Claude Code-specific and lack the ability to hold state (model + database connection) across tool calls.

### D6. Lazy Imports for Heavy Dependencies

**Decision:** Import `sentence_transformers` and `sqlite_vec` inside function bodies, not at module level.

**Alternatives:** Top-level imports (standard Python practice); optional dependency groups.

**Rationale:** `sentence_transformers` takes several seconds to import (loads PyTorch). Top-level import would make every CLI invocation slow, even for subcommands that do not need embeddings (e.g., `kairos aggregate`). Lazy imports keep the CLI responsive. The trade-off is slightly non-standard Python style, but the user experience improvement is significant.

### D7. `_kairos_state` Pattern for Test Access

**Decision:** Attach a `state` dict to the FastMCP instance as `_kairos_state` so test code can pre-populate it without running the lifespan.

**Alternatives:** Mock the lifespan; use dependency injection; test only through MCP client protocol.

**Rationale:** FastMCP 1.26.0 has no public session or test API. The lifespan context manager is the only way to populate server state, but it requires a running MCP client connection. Attaching state to the instance allows tests to set `mcp._kairos_state["contracts"] = {...}` directly, then call tool functions. This is a testing workaround, not an architectural pattern -- it should be revisited if FastMCP adds a public test API.

### D8. Connection Reuse via Optional `conn` Parameter

**Decision:** `search()` accepts an optional `conn` parameter for pre-opened sqlite connections.

**Alternatives:** Global connection; connection pool; always open/close per call.

**Rationale:** The MCP server holds a single sqlite-vec connection for its entire session lifetime (opened in lifespan, closed on exit). Passing this connection to `search()` via the `conn` parameter avoids per-query connection overhead and extension loading. When `conn` is None (e.g., CLI usage or tests), `search()` opens and closes its own connection. This keeps the function usable in both contexts without coupling it to server lifecycle.

### D9. `additionalProperties: true` at Schema Root

**Decision:** The contract JSON Schema sets `additionalProperties: true` at the root level.

**Alternatives:** Strict schema (`additionalProperties: false` everywhere); no schema validation.

**Rationale:** Forward compatibility. Contracts can include extra fields (e.g., experimental sections, team-specific metadata) without breaking validation. This allows incremental schema evolution -- new fields can be added to contracts before the schema formally defines them. Individual sections (identity, provides, etc.) use `additionalProperties: false` to catch typos in known fields, so the trade-off is narrowly scoped.

### D10. Full Re-Embed on Each Run

**Decision:** `embed_contracts()` drops and recreates all tables on every invocation.

**Alternatives:** Incremental update (hash-based change detection); append-only with versioning.

**Rationale:** Idempotent and simple. At prototype scale, a full re-embed takes seconds. Incremental update would require tracking which contracts changed, which chunks were added/removed, and handling schema changes -- significant complexity for negligible performance gain. If the corpus grows to thousands of contracts, incremental update can be added without changing the external interface.

### D11. Deduplication at Tool Level

**Decision:** `search()` returns raw results; deduplication by contract name happens in the `find_relevant_contracts` tool in `server.py`.

**Alternatives:** Deduplicate in `search()` itself; deduplicate in chunker (one chunk per repo).

**Rationale:** Separation of concerns. `search()` is a general-purpose vector search function -- it should return what the database returns. The MCP tool `find_relevant_contracts` has domain-specific knowledge that users want one result per repo (not five chunks from the same contract). Keeping dedup at the tool level means other consumers of `search()` (future tools, CLI commands) can choose their own dedup strategy.

### D12. Real Git Subprocess for Staleness

**Decision:** Use `subprocess.run(["git", ...])` for staleness detection, not libgit2 or dulwich.

**Alternatives:** GitPython (wraps git subprocess); dulwich (pure Python git); libgit2/pygit2 (C library bindings).

**Rationale:** Simple, no extra dependency. Git is always available in development environments. The staleness checker needs only four git commands (rev-parse, cat-file, rev-list, diff), and subprocess handles them cleanly. dulwich and pygit2 would add dependencies and complexity for no practical benefit at this scale. GitPython wraps subprocess anyway and adds its own quirks.
