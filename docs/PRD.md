> **Historical Document.** This PRD guided the implementation of Waves 1-6. For the current architecture as-built, see [architecture.md](architecture.md).

# Kairos — Product Requirements Document

> *Kairos* (Greek: καιρός) — the opportune moment. The right knowledge, applied at the right time.

**Version:** 1.0
**Date:** 2026-03-24
**Status:** Draft
**Authors:** bakerb, Claude (AI Partner)

---

## Table of Contents

1. [Problem Domain](#1-problem-domain)
2. [Constraints](#2-constraints)
3. [Requirements (EARS Format)](#3-requirements-ears-format)
4. [Concept of Operations](#4-concept-of-operations)
5. [Detailed Design](#5-detailed-design)
6. [Definition of Done](#6-definition-of-done)
7. [Phased Implementation Plan](#7-phased-implementation-plan)
8. [Appendices](#8-appendices)

---

## 1. Problem Domain

### 1.1 Background

Modern software platforms are multi-repo ecosystems. A single product might span 10-30+ repositories covering infrastructure, services, deployment, configuration, and documentation. Each repo has its own architecture, interfaces, dependencies, and hard-won operational knowledge (gotchas).

AI coding agents (Claude Code, Cursor, Copilot, etc.) are increasingly used to work across these ecosystems. But every new session starts cold — the agent has no understanding of how repos relate, what interfaces they share, or which pieces of the ecosystem are relevant to the current task.

This problem is an instance of the **D2W chain** (Data to Wisdom) — the progressive refinement of raw material into actionable understanding:

| Layer | Definition | In this domain |
|-------|-----------|----------------|
| **Data** | Disorganized intentional markings | Raw code, configs, YAML scattered across repos |
| **Information** | Data organized to be readable | Structured descriptions of each repo's role and interfaces |
| **Knowledge** | Information from which you can interpret meaning | Semantic representations that capture what things *mean* |
| **Wisdom** | The ability to apply knowledge to a situation | Delivering the *right* knowledge to the *right* agent at the *right* moment |

Wisdom — the application layer — is the only thing that makes the preceding layers valuable. Without it, organized knowledge just sits in files that agents may or may not read.

**Reference:** [Contract Engineering: Beyond Context](https://bakeb7j0.github.io/blog/contract-engineering-beyond-context/)

### 1.2 Problem Statement

AI agents working in multi-repo ecosystems lack a structured, maintainable, queryable system for cross-repository knowledge. Current approaches each fail in distinct ways:

| Approach | Failure Mode |
|----------|-------------|
| **Deep exploration every session** | Expensive (tokens + time). Rediscovers the same architecture repeatedly. |
| **Hand-maintained docs** (README, onboarding guides) | Goes stale silently. Captures what the author remembered, not what the agent needs. |
| **Per-repo agent config** (CLAUDE.md, .cursorrules) | No cross-repo awareness. 90% duplicated boilerplate. |
| **Agent memory** | Session-scoped or project-scoped. Doesn't aggregate across an ecosystem. Decays. |

The result: agents make avoidable mistakes, miss cross-repo dependencies, and require expensive human re-onboarding every session.

### 1.3 Proposed Solution

Kairos is a structured context system that implements the full D2W chain for AI agent ecosystems:

1. **Contracts** (Data → Information): A YAML schema for describing what an AI agent needs to know about a repository — its purpose, what it provides, what it consumes, how it's operated, and what traps to avoid.
2. **Semantic Embeddings** (Information → Knowledge): A pipeline that decomposes contracts into fine-grained semantic chunks and stores them as vectors in a lightweight, zero-daemon database (sqlite-vec).
3. **MCP Server** (Knowledge → Wisdom): Tools exposed via the Model Context Protocol that allow any AI agent to discover the right contracts for the current task via semantic search.

### 1.4 Target Users

| Persona | Description | Primary Use Case |
|---------|-------------|------------------|
| **Platform Engineer** | Maintains 5+ repos forming a cohesive platform. Uses AI agents daily across the ecosystem. | Writes contracts for their repos. Benefits from agents that automatically understand cross-repo dependencies when starting work. |
| **AI Agent Operator** | Configures and orchestrates AI agents (skills, hooks, subagent waves) for development workflows. | Wires Kairos MCP into agent configuration so subagents automatically receive relevant ecosystem context for their assigned tasks. |
| **DevOps / SRE** | Manages cross-service infrastructure and deployment pipelines. | Queries contracts to understand dependency chains, identify blast radius of changes, and detect when interfaces have drifted from documented contracts. |

### 1.5 Non-Goals

- **Not a documentation generator.** Kairos does not auto-generate contracts from code. AI agents can draft contracts through exploration, but code analysis produces descriptions of *what is*, not *what matters*. A human with domain authority approves every contract.
- **Not a runtime dependency.** Applications must never import or depend on Kairos. It exists to improve the development experience, not to become a runtime coupling point.
- **Not a replacement for CLAUDE.md / .cursorrules.** Those files define agent *behavior* (workflow rules, commit protocols, tone). Contracts define *ecosystem knowledge* (architecture, interfaces, dependencies). They are complementary layers.
- **Not tied to any specific AI agent.** MCP is the interface. Any MCP-compatible client can use Kairos. There are no Claude Code-specific APIs or assumptions.
- **Not a monorepo tool.** Kairos is designed for multi-repo ecosystems where cross-repo knowledge is the gap. Monorepos have different tooling for this (IDE navigation, unified build systems). Kairos may still be useful in monorepos, but it is not optimized for them.

---

## 2. Constraints

### 2.1 Technical Constraints

| ID | Constraint | Rationale |
|----|-----------|-----------|
| CT-01 | Zero-daemon architecture — no persistent background services required beyond the MCP session | Contracts and embeddings must be portable across machines. Developers should not need to run infrastructure to use Kairos. sqlite-vec (library, not server) and local sentence-transformers satisfy this. |
| CT-02 | Embeddings computed locally — no external API calls for vector generation | Eliminates API cost, network dependency, and data exfiltration concerns. The corpus is small enough (~100-1000 vectors) that local models perform well. |
| CT-03 | MCP as the sole agent interface — no custom CLI protocol or agent-specific integrations | MCP is the emerging standard for AI agent tool integration. Building on MCP ensures compatibility with Claude Code, Cursor, and future MCP clients without per-client work. |
| CT-04 | YAML contracts are the source of truth — the sqlite-vec database is a derived artifact | The database is regenerated from YAML at any time (`kairos embed`). It is gitignored. Contracts are human-readable, diffable, and reviewable in pull requests. |
| CT-05 | Python as the implementation language | sentence-transformers and the MCP SDK are Python-native. The embedding pipeline and MCP server share a runtime. |

### 2.2 Product Constraints

| ID | Constraint | Rationale |
|----|-----------|-----------|
| CP-01 | Contracts may be identified and authored by AI or human, but must be approved for inclusion by a human with the authority to judge the veracity of the contract | AI agents are capable of identifying candidate contracts and drafting high-quality contract content through code exploration. However, the highest-value sections (gotchas, interface semantics, operational context) require judgment that only someone with domain authority can validate. Human approval is the quality gate, not human authorship. |
| CP-02 | Kairos is a development-time tool — no runtime dependencies | Applications must never import or depend on Kairos. It exists to improve the development experience, not to become a runtime coupling point. |
| CP-03 | Ecosystem-agnostic — not tied to any specific platform, language, or IaC tool | The contract schema must accommodate repos using CDK, Terraform, Docker Compose, Kubernetes, bare scripts, or any other tooling. Platform-specific fields (e.g., `cloudformation_exports`) are optional extensions, not required. |
| CP-04 | Kairos does not replace CLAUDE.md / .cursorrules | Those files define agent *behavior* (workflow rules, commit protocols, tone). Contracts define *ecosystem knowledge* (architecture, interfaces, dependencies). They are complementary layers. |

---

## 3. Requirements (EARS Format)

Requirements follow the **EARS** (Easy Approach to Requirements Syntax) notation:

- **Ubiquitous**: The system shall [function].
- **Event-driven**: When [event], the system shall [function].
- **State-driven**: While [state], the system shall [function].
- **Optional**: Where [feature/condition], the system shall [function].
- **Unwanted**: If [unwanted condition], then the system shall [function].

**Traceability:** Every requirement ID must appear in at least one Acceptance Criteria item in Section 7. After implementation, the VRTM (Appendix V) provides the formal forward and backward trace.

### 3.1 Contract Schema

| ID | Type | Requirement |
|----|------|-------------|
| R-01 | Ubiquitous | The system shall define a YAML-based contract schema with sections for identity, provides, consumes, interfaces, operational, and gotchas. |
| R-02 | Ubiquitous | The system shall provide a JSON Schema definition (`schema.yaml`) that can validate any contract file. |
| R-03 | Ubiquitous | Each contract shall include `staleness_paths` — file globs identifying which codebase files, if changed, suggest the contract may need review. |
| R-04 | Ubiquitous | Each contract shall include `last_verified` (date) and `verified_at_commit` (git SHA) metadata for freshness tracking. |
| R-05 | Ubiquitous | The system shall provide a contract template that can scaffold a new contract for any repository. |

### 3.2 Embedding Pipeline

| ID | Type | Requirement |
|----|------|-------------|
| R-06 | Ubiquitous | The system shall decompose each contract into fine-grained semantic chunks (one vector per meaningful field: each provides entry, each consumes entry, each gotcha, etc.). |
| R-07 | Ubiquitous | Each vector shall carry metadata: `repo_name`, `section`, `field_path`, and the original text. |
| R-08 | Ubiquitous | The system shall use a local embedding model (sentence-transformers) with no external API calls. |
| R-09 | Ubiquitous | The system shall store vectors in a sqlite-vec database file alongside the contract YAML files. |
| R-10 | Event-driven | When `kairos embed` is invoked, the system shall read all contract YAML files, chunk them, embed them, and write the results to the sqlite-vec database, replacing any previous embeddings. |
| R-11 | Unwanted | If a contract YAML file fails schema validation, then the system shall report the validation error and skip that contract without aborting the entire embedding run. |

### 3.3 MCP Server

| ID | Type | Requirement |
|----|------|-------------|
| R-12 | Ubiquitous | The system shall expose an MCP server with tools for contract discovery. |
| R-13 | Event-driven | When an agent calls `find_relevant_contracts(query, top_k)`, the system shall embed the query, search sqlite-vec for the most similar chunks, deduplicate by repo, and return full contract YAML for the top-K matching repos. |
| R-14 | Event-driven | When an agent calls `get_contract(repo_name)`, the system shall return the full contract YAML for the named repo. |
| R-15 | Event-driven | When an agent calls `list_contracts()`, the system shall return the identity section of every contract. |
| R-16 | Event-driven | When an agent calls `check_staleness(repo_name)`, the system shall compare the contract's `verified_at_commit` against the repo's current git HEAD for files matching `staleness_paths` and return a staleness report. |
| R-17 | Event-driven | When an agent calls `check_staleness()` with no repo specified, the system shall check all contracts and return an aggregate staleness report. |
| R-18 | State-driven | While the MCP server is running, the system shall hold the sqlite-vec database connection open for the session duration (no cold start per query). |

### 3.4 Static Digest (Fallback)

| ID | Type | Requirement |
|----|------|-------------|
| R-19 | Ubiquitous | The system shall provide an aggregation script that generates a static markdown digest (`ecosystem-digest.md`) from all contracts. |
| R-20 | Ubiquitous | The ecosystem digest shall include: platform overview, per-repo summaries sorted by category, cross-repo dependency table (provides/consumes joins), and aggregated gotchas sorted by severity. |
| R-21 | Optional | Where the MCP server is not available, agents shall be able to read `ecosystem-digest.md` as a fallback for ecosystem awareness. |

### 3.5 Staleness Detection

| ID | Type | Requirement |
|----|------|-------------|
| R-22 | Event-driven | When staleness is checked for a contract, the system shall run `git diff --stat <verified_at_commit>..HEAD -- <staleness_paths>` in the contract's repo directory. |
| R-23 | Event-driven | When changes are found in staleness paths, the system shall report the contract as STALE with a summary of changed files. |
| R-24 | Event-driven | When no changes are found in staleness paths, the system shall report the contract as CURRENT. |
| R-25 | Unwanted | If the repo directory does not exist or is not a git repository, then the system shall report the contract as UNKNOWN with an explanatory message. |

---

## 4. Concept of Operations

### 4.1 System Context

```
┌─────────────────────────────────────────────────────────┐
│                    Developer Workspace                   │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  repo-A   │  │  repo-B   │  │  repo-C   │  ...       │
│  │           │  │           │  │           │             │
│  └──────────┘  └──────────┘  └──────────┘              │
│        │              │              │                   │
│        ▼              ▼              ▼                   │
│  ┌─────────────────────────────────────┐                │
│  │     Contract YAML Files             │ source of truth│
│  │     (one per repo, versioned)       │                │
│  └──────────────────┬──────────────────┘                │
│                     │                                   │
│            kairos embed                                 │
│                     │                                   │
│  ┌──────────────────▼──────────────────┐                │
│  │        sqlite-vec Database          │ derived        │
│  │    (vectors + metadata, gitignored) │                │
│  └──────────────────┬──────────────────┘                │
│                     │                                   │
│  ┌──────────────────▼──────────────────┐                │
│  │         Kairos MCP Server           │                │
│  │  find | get | list | staleness      │                │
│  └───────┬─────────────┬──────────────┘                │
│          │             │                                │
│    ┌─────▼─────┐ ┌─────▼─────┐                         │
│    │Claude Code│ │  Cursor   │  (any MCP client)       │
│    └───────────┘ └───────────┘                         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Contract Authoring Flow

1. A repository's architecture changes (new exports, new services, new gotchas discovered), or a new repo is added to the ecosystem.
2. An AI agent or human identifies that a contract needs to be created or updated.
3. An AI agent or human authors/updates the contract YAML (AI agents can deep-dive a codebase to draft comprehensive contracts).
4. A human with domain authority reviews and approves the contract for inclusion — this is the quality gate.
5. The approved contract is committed to version control via standard PR/MR workflow.
6. `kairos embed` regenerates the vector database from all contracts.

### 4.3 Agent Consumption Flow

1. An AI agent session starts (Claude Code, Cursor, etc.).
2. The Kairos MCP server starts alongside the session (configured in agent settings).
3. The agent receives a task (prompt, issue, branch name).
4. The agent calls `find_relevant_contracts(task_description)`.
5. Kairos embeds the query, searches sqlite-vec, and returns the top-K matching contracts.
6. The agent now has focused ecosystem context — relevant interfaces, dependencies, and gotchas — without reading irrelevant repos.

### 4.4 Parallel Wave Execution

1. A wave orchestrator prepares N sub-issues for parallel agent execution.
2. For each sub-issue, the orchestrator calls `find_relevant_contracts(sub_issue.description)`.
3. Each subagent is launched with only the contracts relevant to its specific task.
4. Result: precise context per subagent, no wasted tokens on irrelevant ecosystem knowledge.

### 4.5 Staleness Detection Flow

1. Periodically (or on demand), an engineer or agent calls `check_staleness()`.
2. Kairos compares each contract's `verified_at_commit` against the repo's current HEAD.
3. Contracts where `staleness_paths` files have changed are flagged as STALE.
4. The engineer reviews flagged contracts and updates them if the architecture actually changed.
5. Updated contracts are re-committed and re-embedded.

---

## 5. Detailed Design

### 5.1 Contract Schema

The full contract schema is defined in `contracts/schema.yaml` (JSON Schema format). A contract answers five questions:

| Question | Schema Section | Content |
|----------|---------------|---------|
| What is this repo? | `identity` | Name, category, purpose, archetype |
| What does it provide? | `provides` | CF exports, Docker images, networks, packages, secrets, CI templates |
| What does it consume? | `consumes` | CF imports (with source repo), images, secrets, repo dependencies |
| How do you interact with it? | `interfaces` | API endpoints, compose variables |
| How do you work in it? | `operational` | Tech stack, validation/test commands, deploy triggers, environments |
| What will bite you? | `gotchas` | Non-obvious traps with severity (critical/high/medium/low) and detail |

See the [contract example in the appendix](#appendix-a-full-contract-example) for a complete annotated contract.

### 5.2 Embedding Pipeline

**Chunking strategy:** Each contract is decomposed into semantic units. One vector per meaningful chunk, not one per contract.

| Chunk Source | Example Text | Metadata |
|-------------|-------------|----------|
| `identity.purpose` | "EC2 + Docker Swarm infrastructure with Traefik and Keycloak" | `{repo: compute, section: identity, field: purpose}` |
| `provides.cloudformation_exports[0]` | "blueshift-compute-{env}-InstanceId: EC2 instance ID for Swarm manager" | `{repo: compute, section: provides, field: cloudformation_exports}` |
| `consumes.cloudformation_imports[0]` | "blueshift-vpc-{env}-VpcId from vpc: VPC to deploy into" | `{repo: compute, section: consumes, field: cloudformation_imports}` |
| `gotchas[0]` | "CDK user-data changes trigger EC2 replacement. user_data_causes_replacement=True..." | `{repo: compute, section: gotchas, severity: critical}` |

**Why fine-grained:** Coarse embedding (one vector per contract) degrades to fuzzy keyword matching. Fine-grained means "LDAP timeout" matches the *specific gotcha* about connection handling, not the entire contract because it mentions LDAP somewhere.

**Scale:** ~5-15 chunks per contract × N repos. At 20 repos ≈ 200 vectors. At 100 repos ≈ 1000 vectors. sqlite-vec handles both trivially.

**Embedding model:** `all-MiniLM-L6-v2` — 384-dimension vectors, ~80MB model, excellent quality-to-size ratio. Runs locally via sentence-transformers with no API calls.

**Deduplication:** When multiple chunks from the same repo match a query, the MCP tool deduplicates by repo and returns the full contract for each unique matching repo, ranked by best-matching chunk score.

### 5.3 MCP Server Design

```python
# Tool signatures (conceptual)

@tool
def find_relevant_contracts(query: str, top_k: int = 3) -> list[Contract]:
    """Embed query → search sqlite-vec → deduplicate by repo → return full contracts."""

@tool
def get_contract(repo_name: str) -> Contract:
    """Direct lookup by repo shortname."""

@tool
def list_contracts() -> list[ContractSummary]:
    """Return identity section of every contract."""

@tool
def check_staleness(repo_name: str | None = None) -> StalenessReport:
    """Compare verified_at_commit against repo HEAD for staleness_paths."""
```

The server loads the sqlite-vec database and the sentence-transformers model on startup. Both remain in memory for the session duration — no cold start per query.

### 5.4 File Layout

```
kairos/
├── kairos/                       # Python package
│   ├── __init__.py
│   ├── server.py                 # MCP server — tool definitions and handlers
│   ├── embed.py                  # Embedding pipeline — YAML → chunks → vectors → db
│   ├── chunker.py                # Contract decomposition into semantic units
│   ├── schema.py                 # Contract validation against JSON Schema
│   └── models.py                 # Data classes for Contract, Chunk, StalenessReport
├── contracts/                    # Example / reference contracts
│   ├── schema.yaml               # JSON Schema for CONTRACT.yaml
│   └── templates/
│       └── contract-template.yaml
├── tests/
│   ├── test_chunker.py
│   ├── test_embed.py
│   ├── test_server.py
│   └── fixtures/
│       └── sample-contracts/     # Test contract YAML files
├── docs/
│   └── PRD.md                    # This document
├── pyproject.toml
├── README.md
└── LICENSE
```

### 5.5 Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Contract format | YAML | Ubiquitous in DevOps, machine-parseable, human-readable, diffable in PRs |
| Vector store | sqlite-vec | Zero-daemon, file-based, portable. Library not a server. |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Local, offline, no API costs, 384-dim, ~80MB |
| Interface | MCP (Model Context Protocol) | Standard protocol, multi-client, multi-tool surface from one server |
| Language | Python | Best ecosystem for ML libs + MCP SDK available |
| Schema validation | JSON Schema (via `jsonschema` lib) | Standard, tooling-rich, can also power IDE autocomplete for YAML |

### 5.6 Open Questions

1. **Contract inheritance/composition:** Should contracts support `extends` or `includes` for shared sections (e.g., all CDK repos share certain gotchas)? Or keep each contract fully self-contained? Self-contained is simpler but may lead to duplication.
2. **Multi-ecosystem support:** Should one Kairos instance serve contracts for multiple independent ecosystems? Or one instance per ecosystem? Current design assumes one instance per ecosystem.
3. **Contract diffing:** Should the embedding pipeline detect semantic drift between contract versions and flag significant changes? This could power automated "contract changelog" generation.
4. **Embedding model upgrades:** When upgrading the embedding model, all vectors must be regenerated. Should the database store the model identifier and refuse queries if the model has changed since last embed?
5. **Contract authoring UX:** Should Kairos include a `kairos init` command that scaffolds a contract by analyzing a repo's code (reading CI config, CDK exports, compose files)? This would lower the authoring barrier. Listed as future work, but priority TBD based on Phase 1 learnings.

---

## 6. Definition of Done

Phase-level Definitions of Done are in Section 7 under each Phase header. Section 6 defines the **global** DoD that applies to the project as a whole.

### Global Definition of Done

Each item is annotated with the requirement IDs it verifies. See Appendix V for the full VRTM.

- [ ] All Phase 1 and Phase 2 DoD checklists are satisfied
- [ ] All unit tests pass (`pytest` green)
- [ ] README includes installation, quickstart, and configuration instructions [R-12]
- [ ] A new Claude Code session configured with the Kairos MCP server can discover relevant contracts for a task via `find_relevant_contracts()` without any prior ecosystem knowledge [R-12, R-13, R-18]
- [ ] The system has been validated against the Blueshift pilot ecosystem (4 repos) [R-01 through R-25]

---

## 7. Phased Implementation Plan

### Wave Map

Stories are grouped into **waves** — sets of stories that can execute in parallel. Each wave has a **master issue** used to orchestrate execution.

```
Wave 1 ─── [1.1] Schema & Template (foundation)
              │
Wave 2 ─┬─ [1.2] Pilot Contracts: vpc, compute
         ├─ [1.3] Pilot Contracts: littleguy, manifests
         ├─ [1.5] Staleness Checker
         └─ [2.1] Contract Chunker
              │
Wave 3 ─┬─ [1.4] Static Digest Aggregation
         └─ [2.2] Embedding Pipeline
              │
Wave 4 ─── [2.3] MCP Server: Core Tools
              │
Wave 5 ─── [2.4] MCP Server: Staleness Tool
              │
Wave 6 ─── [2.5] Packaging & Configuration
```

| Wave | Stories | Master Issue | Parallel? |
|------|---------|-------------|-----------|
| 1 | 1.1 | Story 1.1 | Single story |
| 2 | 1.2, 1.3, 1.5, 2.1 | Wave 2 Master | Yes — 4 independent stories |
| 3 | 1.4, 2.2 | Wave 3 Master | Yes — 2 independent stories |
| 4 | 2.3 | Story 2.3 | Single story |
| 5 | 2.4 | Story 2.4 | Single story |
| 6 | 2.5 | Story 2.5 | Single story |

---

### Phase 1: Contracts & Static Digest (Epic)

**Goal:** Prove the contract schema captures useful ecosystem knowledge by generating contracts for a pilot set of repos and producing a consumable static digest.

#### Phase 1 Definition of Done

- [ ] Contract JSON Schema (`contracts/schema.yaml`) is defined and can validate YAML contracts [R-01, R-02]
- [ ] Contract template (`contracts/templates/contract-template.yaml`) is usable to scaffold a new contract [R-05]
- [ ] 4 pilot contracts exist and pass schema validation (vpc, compute, littleguy, manifests) [R-01, R-03, R-04]
- [ ] Each pilot contract has been reviewed and approved by a human with domain authority [CP-01]
- [ ] `kairos aggregate` produces an `ecosystem-digest.md` from the 4 pilot contracts [R-19]
- [ ] The ecosystem digest includes: per-repo summaries, dependency cross-reference table, aggregated gotchas [R-20]
- [ ] `kairos check-staleness` reports CURRENT/STALE/UNKNOWN for each pilot contract [R-22, R-23, R-24, R-25]
- [ ] A new agent session reading only the ecosystem digest can correctly answer: "What CF exports does vpc provide?" and "What does compute consume from vpc?" [R-20, R-21]
- [ ] All Phase 1 unit tests pass

---

#### Story 1.1: Define contract schema and template

**Wave:** 1 (foundation)
**Dependencies:** None

Create the JSON Schema that validates contract YAML files, a template for authoring new contracts, and a Python validation module.

**Implementation Steps:**

1. Create `contracts/schema.yaml`:
   - Define the root object with `contract_version` (string, required).
   - Define `identity` object: `name` (string, required), `full_name` (string, required), `category` (string, required), `purpose` (string, required), `archetype` (string, enum: `cdk-infra`, `swarm-service`, `compose-standalone`, `config-only`, `docs-only`, `meta-tooling`, `library`).
   - Define `provides` object with optional array fields: `cloudformation_exports` (items: `{name, description}`), `docker_images` (items: `{name, registry?, source?, description}`), `docker_networks` (items: `{name, scope, description}`), `packages`, `secrets` (items: `{path, description}`), `ci_templates`.
   - Define `consumes` object with optional array fields: `cloudformation_imports` (items: `{export, from, description}`), `docker_images`, `secrets` (items: `{path, from, description}`), `repos` (items: `{name, relationship}`).
   - Define `interfaces` object: `api_endpoints` (items: `{url, service, description}`), `compose_variables` (items: `{name, description}`).
   - Define `operational` object: `tech_stack` (object: `{language, framework?, iac?}`), `validation_command` (string), `test_command` (string), `deploy_trigger` (object with string values), `environments` (array of strings).
   - Define `gotchas` array: items are `{severity (enum: critical, high, medium, low), summary, detail}`.
   - Define `staleness_paths` (array of strings), `last_verified` (string, date format), `verified_at_commit` (string).
   - Set `additionalProperties: true` at root level for forward compatibility.

2. Create `contracts/templates/contract-template.yaml`:
   - A fully populated template with placeholder values and YAML comments explaining each field.
   - Every field present (even optional ones) with example values and `# TODO: fill in` markers.
   - Comments should explain what the field means, not just what type it is.

3. Write `kairos/models.py`:
   - Define `@dataclass` classes: `Contract`, `ContractIdentity`, `Chunk`, `StalenessReport`.
   - `Contract` wraps the parsed YAML with typed access to all sections.
   - Include a `Contract.from_yaml(path: Path) -> Contract` class method.

4. Write `kairos/schema.py`:
   - Function `validate_contract(yaml_path: Path) -> list[ValidationError]`.
   - Loads `contracts/schema.yaml` via `jsonschema`.
   - Parses the target YAML file with `pyyaml`.
   - Returns empty list on success, list of structured errors on failure.
   - Each error includes: field path, message, severity.

5. Write `tests/test_schema.py`:
   - Create `tests/fixtures/sample-contracts/valid-compute.yaml` — a minimal but complete valid contract.
   - Create `tests/fixtures/sample-contracts/invalid-missing-identity.yaml` — missing required `identity` section.
   - Create `tests/fixtures/sample-contracts/invalid-bad-archetype.yaml` — archetype value not in enum.
   - Create `tests/fixtures/sample-contracts/valid-minimal.yaml` — only required fields, all optional fields omitted.
   - Create `tests/fixtures/sample-contracts/valid-extra-fields.yaml` — has additional fields not in schema (forward compatibility).
   - Test cases: valid passes, missing required fails with correct field path, bad enum fails, minimal passes, extra fields pass.

**Acceptance Criteria:**

- [ ] `contracts/schema.yaml` exists and is valid JSON Schema (parseable by `jsonschema` library) [R-02]
- [ ] `contracts/templates/contract-template.yaml` exists and passes schema validation when placeholder values are filled [R-05]
- [ ] `kairos/schema.py` validates a correct contract YAML and returns no errors [R-02]
- [ ] `kairos/schema.py` rejects a contract missing `identity.name` and returns an error referencing that field [R-02]
- [ ] `kairos/schema.py` rejects a contract with `archetype: invalid-value` and returns an error referencing the enum [R-02]
- [ ] `kairos/schema.py` accepts a contract with additional fields not defined in the schema [R-02]
- [ ] All tests in `tests/test_schema.py` pass [R-01, R-02]
- [ ] `kairos/models.py` provides `Contract.from_yaml()` that loads and parses a valid contract [R-01]

---

#### Story 1.2: Author pilot contracts (vpc, compute)

**Wave:** 2
**Dependencies:** Story 1.1

Generate contracts for the first two repos in the dependency chain via agent deep-dive exploration of their codebases. These two demonstrate the CloudFormation export/import interface.

**Implementation Steps:**

1. Explore `blueshift-vpc` codebase:
   - Read CDK stack definitions in `infrastructure/` — identify all `CfnOutput` / CloudFormation exports.
   - Read `.gitlab-ci.yml` — identify CI stages, deploy triggers, tag patterns.
   - Read `CLAUDE.md` and `README.md` — extract purpose, tech stack, existing gotchas.
   - Identify any Docker images built, networks created, secrets seeded.
   - Identify known gotchas from code comments, CLAUDE.md, and operational history.

2. Write `contracts/repos/vpc.yaml`:
   - Populate `identity`: name, full_name, category (infrastructure), purpose, archetype (cdk-infra).
   - Populate `provides.cloudformation_exports` with every export found in CDK code.
   - Populate `provides.docker_networks`, `provides.secrets` if applicable.
   - Leave `consumes` minimal (VPC is typically a root provider).
   - Populate `operational` with tech stack, validation/test commands, deploy triggers.
   - Populate `gotchas` with any non-obvious traps found during exploration.
   - Set `staleness_paths` to CDK stack files, CI config, and deploy scripts.
   - Set `last_verified` and `verified_at_commit` to current date and HEAD SHA.

3. Run `kairos/schema.py` to validate `contracts/repos/vpc.yaml`.

4. Explore `blueshift-compute` codebase:
   - Read CDK stack definitions — identify all `Fn.import_value` calls (consumes) and `CfnOutput` exports (provides).
   - Read Docker Compose files — identify overlay networks created, images used.
   - Read user-data bootstrap scripts — identify SwarmCD wiring, service dependencies.
   - Read `.gitlab-ci.yml` — CI stages, deploy triggers, tag patterns.
   - Read `CLAUDE.md` (especially lines 232-254 which already contain informal contracts).
   - Identify gotchas: user-data replacement, stack deletion order, sites branch detection.

5. Write `contracts/repos/compute.yaml`:
   - Populate all sections from exploration findings.
   - Cross-reference `consumes.cloudformation_imports` against vpc's `provides.cloudformation_exports` to verify the interface matches.

6. Run `kairos/schema.py` to validate `contracts/repos/compute.yaml`.

7. Submit both contracts for human review and approval.

**Acceptance Criteria:**

- [ ] `contracts/repos/vpc.yaml` exists and passes schema validation [R-01, R-02]
- [ ] vpc contract lists all CloudFormation exports found in the CDK code [R-01]
- [ ] `contracts/repos/compute.yaml` exists and passes schema validation [R-01, R-02]
- [ ] compute contract's `consumes.cloudformation_imports` references exports that appear in vpc's `provides` [R-01]
- [ ] compute contract includes the `blueshift_public` Docker overlay network in `provides.docker_networks` [R-01]
- [ ] Both contracts include at least 2 gotchas each with severity ratings [R-01]
- [ ] Both contracts include `staleness_paths` covering infrastructure code and CI config [R-03]
- [ ] Both contracts include `last_verified` and `verified_at_commit` metadata [R-04]
- [ ] Both contracts have been reviewed and approved by a human with domain authority [CP-01]

---

#### Story 1.3: Author pilot contracts (littleguy, manifests)

**Wave:** 2
**Dependencies:** Story 1.1

Generate contracts for the remaining two pilot repos. These demonstrate config-only and meta-tooling archetypes.

**Implementation Steps:**

1. Explore `blueshift-littleguy` codebase:
   - Read Docker Compose configuration — identify services, networks joined, images used.
   - Read SwarmCD polling configuration — what branch/tag it watches, polling interval.
   - Read operator scripts (redeploy, branch-switch) — how deployments are triggered.
   - Read `Docs/` directory for architecture and operational docs.
   - Identify gotchas from code comments and operational history.

2. Write `contracts/repos/littleguy.yaml`:
   - Populate `identity` with archetype `config-only` or `compose-standalone`.
   - Populate `consumes` with images pulled, networks joined, secrets read.
   - Populate `interfaces` with any scripts/APIs other repos call.
   - Populate `gotchas` and `staleness_paths`.

3. Run `kairos/schema.py` to validate.

4. Explore `blueshift-manifests` codebase:
   - Read wave directory structure — how compose fragments are organized per service.
   - Read `scripts/ci/render.sh` — how fragments are assembled into per-site compose files.
   - Read `scripts/ci/push-site-order.sh` — how rendered output reaches site-order repos.
   - Read `.gitlab-ci.yml` — CI pipeline stages, how site-order MRs are created.
   - Read `Docs/site-order-pipeline.md` for the full deployment flow.
   - Identify cross-repo dependencies: which compose variables are required, which images are referenced.

5. Write `contracts/repos/manifests.yaml`:
   - Populate `identity` with archetype `meta-tooling`.
   - Populate `provides` — what manifests produces (rendered compose files, site-order MRs).
   - Populate `consumes` — Docker images referenced in compose fragments, secrets, repos.
   - Populate `interfaces.compose_variables` — all `${VAR}` placeholders that must be set.
   - Populate `gotchas` and `staleness_paths`.

6. Run `kairos/schema.py` to validate.

7. Submit both contracts for human review and approval.

**Acceptance Criteria:**

- [ ] `contracts/repos/littleguy.yaml` exists and passes schema validation [R-01, R-02]
- [ ] littleguy contract accurately reflects SwarmCD configuration and operator scripts [R-01]
- [ ] `contracts/repos/manifests.yaml` exists and passes schema validation [R-01, R-02]
- [ ] manifests contract documents the render/push pipeline and compose variable requirements [R-01]
- [ ] manifests contract's `consumes` references images/networks that appear in other pilot contracts' `provides` [R-01]
- [ ] Both contracts include at least 1 gotcha each with severity ratings [R-01]
- [ ] Both contracts include `staleness_paths` and versioning metadata [R-03, R-04]
- [ ] Both contracts have been reviewed and approved by a human with domain authority [CP-01]

---

#### Story 1.4: Static digest aggregation

**Wave:** 3
**Dependencies:** Stories 1.2, 1.3

Build a module that reads all contract YAML files and produces a markdown ecosystem digest.

**Implementation Steps:**

1. Write `kairos/aggregate.py`:
   - Function `aggregate_contracts(contracts_dir: Path) -> str` that returns markdown.
   - Load all `*.yaml` files from the contracts directory.
   - Parse each with `Contract.from_yaml()`.
   - Sort contracts by `identity.category` (infrastructure first, then deployment, core, apps).

2. Generate markdown sections:
   - **Platform Overview**: Auto-generated header with contract count and categories present.
   - **Repository Summaries**: For each contract, render identity (name, purpose, archetype, category) as a subsection.
   - **Dependency Table**: Build a cross-reference table — for each `provides` entry, list which repos `consume` it. Use the `from` field in `consumes` entries to create the mapping.
   - **Aggregated Gotchas**: Collect all gotchas across all contracts, sort by severity (critical → high → medium → low), render with repo attribution.

3. Add CLI entry point: `kairos aggregate --contracts-dir <path> --output <path>`.

4. Write `tests/test_aggregate.py`:
   - Create 2-3 minimal fixture contracts in `tests/fixtures/sample-contracts/` that have known provides/consumes relationships.
   - Test: output contains all repo names.
   - Test: dependency table correctly shows that repo-B consumes an export from repo-A.
   - Test: gotchas are sorted by severity (critical before medium).
   - Test: repos are sorted by category.

**Acceptance Criteria:**

- [ ] `kairos aggregate --contracts-dir contracts/repos/ --output ecosystem-digest.md` produces a markdown file [R-19]
- [ ] The digest contains a summary for each of the 4 pilot contracts [R-20]
- [ ] The dependency table shows compute consuming vpc's CF exports [R-20]
- [ ] Gotchas section lists critical-severity items before medium-severity items [R-20]
- [ ] Repos are grouped/sorted by category [R-20]
- [ ] All tests in `tests/test_aggregate.py` pass [R-19, R-20]
- [ ] A human or agent reading only the digest can determine what vpc provides and what compute consumes [R-20, R-21]

---

#### Story 1.5: Staleness checker

**Wave:** 2
**Dependencies:** Story 1.1

Build a module that compares contract metadata against git history to detect potential staleness.

**Implementation Steps:**

1. Write `kairos/staleness.py`:
   - Function `check_staleness(contract: Contract, repo_path: Path) -> StalenessReport`.
   - Read `verified_at_commit` and `staleness_paths` from the contract.
   - If `repo_path` does not exist or is not a git repo, return `StalenessReport(status="UNKNOWN", message="Repo not found")`.
   - Run `git -C <repo_path> rev-parse HEAD` to get current HEAD.
   - If HEAD == `verified_at_commit`, return `CURRENT` immediately.
   - Run `git -C <repo_path> diff --stat <verified_at_commit>..HEAD -- <staleness_paths>` for each glob in `staleness_paths`.
   - If any files changed, return `StalenessReport(status="STALE", changed_files=[...], commits_since=N)`.
   - If no files changed in staleness paths, return `CURRENT`.
   - Function `check_all_staleness(contracts_dir: Path, workspace_path: Path) -> dict[str, StalenessReport]` that iterates all contracts.

2. Add CLI entry point: `kairos check-staleness --contracts-dir <path> --workspace <path>`.
   - Output: table with repo name, status (colored: green CURRENT, yellow STALE, red UNKNOWN), and summary.

3. Write `tests/test_staleness.py`:
   - Use `tmp_path` fixture to create a temporary git repo with an initial commit.
   - Create a contract pointing at that repo with `verified_at_commit` set to the initial commit SHA.
   - Test CURRENT: no changes since verified commit → CURRENT.
   - Test STALE: add a commit that modifies a file matching `staleness_paths` → STALE with changed file listed.
   - Test CURRENT despite changes: add a commit that modifies a file NOT in `staleness_paths` → CURRENT.
   - Test UNKNOWN: point contract at a non-existent path → UNKNOWN.

**Acceptance Criteria:**

- [ ] `kairos check-staleness` runs against pilot contracts and reports status for each [R-22]
- [ ] A contract with no changes since `verified_at_commit` reports CURRENT [R-24]
- [ ] A contract where `staleness_paths` files have changed reports STALE with a list of changed files [R-22, R-23]
- [ ] A contract where changes exist but NOT in `staleness_paths` reports CURRENT [R-24]
- [ ] A contract pointing at a non-existent repo reports UNKNOWN [R-25]
- [ ] All tests in `tests/test_staleness.py` pass [R-22, R-23, R-24, R-25]

---

### Phase 2: Semantic Discovery & MCP Server (Epic)

**Goal:** Make contracts queryable via semantic search and expose discovery as MCP tools that any AI agent can call.

#### Phase 2 Definition of Done

- [ ] Embedding pipeline produces a sqlite-vec database from pilot contracts [R-06, R-09, R-10]
- [ ] MCP server starts successfully and exposes all 4 tools (`find`, `get`, `list`, `check_staleness`) [R-12, R-18]
- [ ] `find_relevant_contracts("Docker overlay network CIDR")` returns compute + vpc contracts [R-13]
- [ ] `find_relevant_contracts("LDAP timeout")` returns compute contract (gotcha match) [R-06, R-13]
- [ ] `find_relevant_contracts("compose fragment rendering")` returns manifests contract [R-13]
- [ ] `get_contract("compute")` returns the full compute contract [R-14]
- [ ] `list_contracts()` returns identity summaries for all 4 pilot contracts [R-15]
- [ ] `check_staleness()` correctly reports CURRENT or STALE per contract via MCP [R-16, R-17]
- [ ] Claude Code can be configured to use the Kairos MCP server via documented settings [R-12]
- [ ] Integration test: an agent session uses MCP tools to discover relevant contracts for a task without prior ecosystem knowledge [R-13, R-18]
- [ ] All unit and integration tests pass
- [ ] `README.md` includes installation, quickstart, and MCP configuration instructions [R-12]

---

#### Story 2.1: Contract chunker

**Wave:** 2
**Dependencies:** Story 1.1

Build the module that decomposes a contract YAML into fine-grained semantic chunks with metadata.

**Implementation Steps:**

1. Write `kairos/chunker.py`:
   - Function `chunk_contract(contract: Contract) -> list[Chunk]`.
   - Each `Chunk` has: `text` (str), `repo_name` (str), `section` (str), `field_path` (str).

2. Implement chunking rules:
   - `identity.purpose` → one chunk. Text: `"{name}: {purpose}"`.
   - Each entry in `provides.cloudformation_exports` → one chunk. Text: `"{name} provides CloudFormation export {export_name}: {description}"`.
   - Each entry in `provides.docker_images` → one chunk. Text: `"{name} builds Docker image {image_name}: {description}"`.
   - Each entry in `provides.docker_networks` → one chunk. Text: `"{name} creates Docker network {network_name} ({scope}): {description}"`.
   - Each entry in `provides.secrets` → one chunk. Text: `"{name} manages secret at {path}: {description}"`.
   - Each entry in `consumes.cloudformation_imports` → one chunk. Text: `"{name} consumes CloudFormation export {export} from {from}: {description}"`.
   - Each entry in `consumes.docker_images` → one chunk. Text: `"{name} uses Docker image {image_name} from {source}"`.
   - Each entry in `consumes.secrets` → one chunk. Text: `"{name} reads secret at {path} from {from}: {description}"`.
   - Each entry in `consumes.repos` → one chunk. Text: `"{name} depends on {repo}: {relationship}"`.
   - Each entry in `interfaces.api_endpoints` → one chunk. Text: `"{name} exposes {service} at {url}: {description}"`.
   - Each entry in `gotchas` → one chunk. Text: `"{name} gotcha ({severity}): {summary}. {detail}"`.
   - `operational` → one chunk. Text: `"{name} uses {language}/{framework}, validate: {validation_command}, test: {test_command}"`.
   - Empty arrays produce no chunks. Missing optional sections produce no chunks.

3. Write `tests/test_chunker.py`:
   - Load `tests/fixtures/sample-contracts/valid-compute.yaml`.
   - Test: chunk count matches expected (count manually from the fixture).
   - Test: each chunk has non-empty `text`, `repo_name`, `section`, `field_path`.
   - Test: `identity.purpose` chunk contains the repo name and purpose text.
   - Test: gotcha chunks include severity in text.
   - Test: a contract with all empty arrays produces only `identity.purpose` + `operational` chunks.

**Acceptance Criteria:**

- [ ] `chunk_contract()` produces one chunk per semantic unit (not one per contract) [R-06]
- [ ] Each chunk's `text` is a natural-language sentence with context (not just the raw field value) [R-06]
- [ ] Each chunk carries correct `repo_name`, `section`, and `field_path` metadata [R-07]
- [ ] Empty provides/consumes arrays produce zero chunks (no noise vectors) [R-06]
- [ ] Gotcha chunks include severity level in their text [R-06]
- [ ] All tests in `tests/test_chunker.py` pass [R-06, R-07]

---

#### Story 2.2: Embedding pipeline

**Wave:** 3
**Dependencies:** Story 2.1

Build the pipeline that embeds chunks into vectors and stores them in sqlite-vec.

**Implementation Steps:**

1. Write `kairos/embed.py`:
   - Function `embed_contracts(contracts_dir: Path, db_path: Path, model_name: str = "all-MiniLM-L6-v2")`.
   - Load the sentence-transformers model.
   - Read all contract YAML files from `contracts_dir`.
   - For each contract, call `chunk_contract()` to get chunks.
   - Batch-encode all chunk texts using `model.encode()`.
   - Open (or create) sqlite-vec database at `db_path`.

2. Create sqlite-vec schema:
   - `CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(embedding float[384])` for the vector index.
   - `CREATE TABLE IF NOT EXISTS chunks_meta(id INTEGER PRIMARY KEY, repo_name TEXT, section TEXT, field_path TEXT, text TEXT)` for metadata.
   - On each run: drop and recreate both tables (full re-embed).

3. Insert vectors and metadata:
   - For each chunk: insert metadata into `chunks_meta`, insert vector into `chunks_vec` with matching rowid.

4. Implement query function (used by MCP server):
   - Function `search(query: str, model, db_path: Path, top_k: int = 10) -> list[tuple[Chunk, float]]`.
   - Encode query with the same model.
   - Query sqlite-vec: `SELECT rowid, distance FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?`.
   - Join with `chunks_meta` to get full chunk data.
   - Return chunks with similarity scores.

5. Add CLI entry point: `kairos embed --contracts-dir <path> --db <path>`.
   - Print summary: "Embedded N chunks across M contracts into <db_path>".

6. Write `tests/test_embed.py`:
   - Use fixture contracts (at least 2 with known content).
   - Test: embed runs without error and creates the database file.
   - Test: database has expected number of rows (matches total chunk count).
   - Test: vectors have dimensionality 384.
   - Test: `search("Docker overlay network")` returns chunks from the contract that mentions Docker networks, with higher score than unrelated chunks.
   - Test: `search("CloudFormation export VPC")` returns vpc-related chunks first.

**Acceptance Criteria:**

- [ ] `kairos embed` reads YAML contracts and produces a sqlite-vec database [R-09, R-10]
- [ ] Database contains one row per semantic chunk with correct metadata [R-07, R-09]
- [ ] Vectors are 384-dimensional (matching `all-MiniLM-L6-v2`) [R-08]
- [ ] `search()` function returns semantically relevant results (Docker query → Docker chunks) [R-09]
- [ ] Re-running embed replaces previous data (idempotent) [R-10]
- [ ] Summary output reports chunk and contract counts [R-10]
- [ ] Invalid contract YAML is skipped with error reported, not aborting the run [R-11]
- [ ] All tests in `tests/test_embed.py` pass [R-08, R-09, R-10, R-11]

---

#### Story 2.3: MCP server — core tools

**Wave:** 4
**Dependencies:** Story 2.2

Build the MCP server with `find_relevant_contracts`, `get_contract`, and `list_contracts`.

**Implementation Steps:**

1. Write `kairos/server.py` using the MCP Python SDK:
   - Import and initialize the MCP server with name "kairos".
   - Accept configuration: `contracts_dir` (Path), `db_path` (Path), `workspace_path` (Path, optional).
   - On startup: load all contract YAML files into an in-memory dict keyed by `identity.name`. Load the sentence-transformers model. Open the sqlite-vec database.

2. Implement `find_relevant_contracts(query: str, top_k: int = 3)`:
   - Call `search()` from `embed.py` with a higher internal limit (e.g., `top_k * 5`).
   - Deduplicate by `repo_name`: for each repo, keep only the chunk with the highest similarity score.
   - Sort deduplicated results by score descending.
   - Take the top `top_k` repos.
   - Return the full contract YAML for each matching repo.
   - Include the matching chunk text and score as context (so the agent knows *why* this contract matched).

3. Implement `get_contract(repo_name: str)`:
   - Lookup in the in-memory contract dict.
   - If found, return the full contract YAML as a string.
   - If not found, return an error message listing available repo names.

4. Implement `list_contracts()`:
   - For each contract in the dict, return the `identity` section only.
   - Format as a YAML list of identity objects.

5. Write `tests/test_server.py`:
   - Test tool registration: server exposes exactly 4 tools (3 core + staleness from 2.4 — stub the 4th for now).
   - Test `find_relevant_contracts("Docker overlay network")`: returns compute contract.
   - Test `find_relevant_contracts("VPC subnets")`: returns vpc contract.
   - Test `get_contract("compute")`: returns full compute contract YAML.
   - Test `get_contract("nonexistent")`: returns error with available names.
   - Test `list_contracts()`: returns identity for all contracts.

**Acceptance Criteria:**

- [ ] MCP server starts without error and registers tools [R-12, R-18]
- [ ] `find_relevant_contracts("Docker overlay network CIDR")` includes compute in results [R-13]
- [ ] `find_relevant_contracts` results include the matching chunk text (explains *why* it matched) [R-13]
- [ ] `find_relevant_contracts` deduplicates by repo (one result per repo, not per chunk) [R-13]
- [ ] `get_contract("compute")` returns the full compute contract [R-14]
- [ ] `get_contract("nonexistent")` returns an error listing available repo names [R-14]
- [ ] `list_contracts()` returns identity summaries for all loaded contracts [R-15]
- [ ] All tests in `tests/test_server.py` pass [R-12, R-13, R-14, R-15]

---

#### Story 2.4: MCP server — staleness tool

**Wave:** 5
**Dependencies:** Stories 1.5, 2.3

Add the `check_staleness` tool to the MCP server.

**Implementation Steps:**

1. Add `check_staleness` tool to `server.py`:
   - Parameter: `repo_name` (string, optional). If None, check all contracts.
   - Uses `workspace_path` from server configuration to resolve repo directories.
   - Pattern: `{workspace_path}/blueshift-{identity.name}/` (configurable via a path template).

2. Integrate `staleness.py` from Story 1.5:
   - Call `check_staleness()` or `check_all_staleness()` depending on whether `repo_name` is provided.
   - Format the `StalenessReport` as a readable string for agent consumption.

3. Handle edge cases:
   - `workspace_path` not configured → return helpful error explaining how to set it.
   - Repo directory not found → return UNKNOWN per existing staleness.py behavior.

4. Write `tests/test_server_staleness.py`:
   - Create temporary git repos matching the workspace pattern.
   - Test: `check_staleness("vpc")` returns CURRENT for a fresh contract.
   - Test: `check_staleness()` (all) returns a report for every loaded contract.
   - Test: missing workspace_path returns an informative error.

**Acceptance Criteria:**

- [ ] `check_staleness("vpc")` returns a staleness report via MCP [R-16]
- [ ] `check_staleness()` with no argument returns reports for all contracts [R-17]
- [ ] Missing `workspace_path` configuration returns a clear error message [R-16]
- [ ] Staleness report includes status (CURRENT/STALE/UNKNOWN), changed files (if STALE), and commits since verification [R-16, R-23]
- [ ] All tests in `tests/test_server_staleness.py` pass [R-16, R-17]

---

#### Story 2.5: Packaging and configuration

**Wave:** 6
**Dependencies:** Stories 2.3, 2.4

Package Kairos for installation and configure it for use with Claude Code.

**Implementation Steps:**

1. Write `pyproject.toml`:
   - Project name: `kairos-contracts`.
   - Dependencies: `sentence-transformers`, `sqlite-vec`, `mcp`, `pyyaml`, `jsonschema`.
   - Dev dependencies: `pytest`, `pytest-tmp-files` (or similar).
   - CLI entry points via `[project.scripts]`: `kairos = "kairos.cli:main"`.
   - Subcommands: `kairos embed`, `kairos check-staleness`, `kairos aggregate`, `kairos serve`.

2. Write `kairos/cli.py`:
   - Use `argparse` with subcommands.
   - `embed`: calls `embed_contracts()` with `--contracts-dir` and `--db` arguments.
   - `check-staleness`: calls staleness checker with `--contracts-dir` and `--workspace` arguments.
   - `aggregate`: calls aggregator with `--contracts-dir` and `--output` arguments.
   - `serve`: starts the MCP server with `--contracts-dir`, `--db`, and `--workspace` arguments.

3. Write `docs/configuration.md`:
   - Claude Code MCP configuration: example `.claude/settings.local.json` snippet showing the `mcpServers` entry for Kairos.
   - Document all CLI flags and environment variables.
   - Document the expected directory layout for a new ecosystem adopting Kairos.

4. Write `docs/quickstart.md`:
   - Step-by-step guide: install Kairos, write your first contract, embed it, start the MCP server, query from Claude Code.
   - Include a complete working example with a sample contract.

5. Update `README.md`:
   - Installation section (pip install from source or PyPI).
   - Quickstart section (link to `docs/quickstart.md`).
   - Configuration section (link to `docs/configuration.md`).
   - Badge: tests passing / version / license.

**Acceptance Criteria:**

- [ ] `pip install -e .` succeeds in a clean virtual environment [R-12]
- [ ] `kairos embed --help`, `kairos check-staleness --help`, `kairos aggregate --help`, `kairos serve --help` all display usage info [R-10, R-12]
- [ ] `kairos embed --contracts-dir contracts/repos/ --db contracts/contracts.db` produces a database [R-10]
- [ ] `kairos serve` starts the MCP server (verifiable by MCP client connection) [R-12, R-18]
- [ ] `docs/configuration.md` includes a working Claude Code MCP configuration snippet [R-12]
- [ ] `docs/quickstart.md` walks through a complete first-use flow [R-12]
- [ ] `README.md` includes install, quickstart, and config sections [R-12]

---

### Phase 3: Enforcement (Future — not scoped for initial release)

**Goal:** Use the discovery mechanism to enforce contract integrity — detect when work output may stale or violate existing contracts.

#### Phase 3 Definition of Done

*Will be defined when Phase 3 is scoped after Phase 2 validation.*

#### Story 3.1: Pre-commit staleness alerting

When a commit modifies files in a contract's `staleness_paths`, surface the affected contracts for review.

#### Story 3.2: MR contract impact summary

Automatically list affected contracts in MR/PR descriptions based on the changeset.

#### Story 3.3: Violation detection

Use LLM reasoning (not just embedding similarity) to detect when a change may violate a contract's declared interfaces (e.g., removing a CF export that another contract declares as consumed).

*Phase 3 stories are intentionally under-specified. They will be fully scoped after Phase 2 is validated.*

---

## 8. Appendices

### Appendix A: Full Contract Example

```yaml
contract_version: "0.1.0"

identity:
  name: compute
  full_name: blueshift-compute
  category: infrastructure
  purpose: >
    Shared compute infrastructure: EC2 instances running Docker Swarm
    with Traefik reverse proxy, Keycloak identity provider, and core
    platform services.
  archetype: cdk-infra

provides:
  cloudformation_exports:
    - name: "blueshift-compute-{env}-InstanceId"
      description: "EC2 instance ID for the Swarm manager node"
    - name: "blueshift-compute-{env}-PublicIp"
      description: "Public IP of the Swarm manager"
  docker_images:
    - name: "blueshift-mutator"
      registry: "harbor.blueshift.internal"
      description: "Secret/config injection sidecar"
  docker_networks:
    - name: blueshift_public
      scope: swarm
      description: "Overlay network for public-facing services via Traefik"
  packages: []
  secrets:
    - path: "secret/data/blueshift/{env}/swarm"
      description: "Swarm join tokens and manager credentials"
  ci_templates: []

consumes:
  cloudformation_imports:
    - export: "blueshift-vpc-{env}-VpcId"
      from: vpc
      description: "VPC to deploy into"
    - export: "blueshift-vpc-{env}-PublicSubnetIds"
      from: vpc
      description: "Public subnets for EC2 placement"
  docker_images:
    - name: "swarm-cd"
      source: "ghcr.io/wave-engineering/swarm-cd:1.17.0"
  secrets:
    - path: "secret/data/blueshift/{env}/registry"
      from: registry
      description: "Harbor registry credentials for image pulls"
  repos:
    - name: vpc
      relationship: "Deploys into VPC provisioned by this repo"

interfaces:
  api_endpoints:
    - url: "auth.{DOMAIN}"
      service: keycloak
      description: "OIDC/SAML identity provider for all platform services"
    - url: "{DOMAIN}/portainer"
      service: portainer
      description: "Container management UI (OIDC via Keycloak)"
  compose_variables:
    - name: DOMAIN
      description: "Base domain for the environment (e.g., dev.blueshift.plus)"

operational:
  tech_stack:
    language: python
    framework: aws-cdk
    iac: cdk
  validation_command: "./scripts/ci/validate.sh"
  test_command: "cd infrastructure && uv run cdk synth"
  deploy_trigger:
    dev: "release/* branch push"
    test: "rc tag (rcX.Y.Z-N)"
    prod: "v tag (vX.Y.Z-N)"
  environments: [dev, test, prod]

gotchas:
  - severity: critical
    summary: "CDK user-data changes trigger EC2 replacement"
    detail: >
      user_data_causes_replacement=True in CDK config. Any modification to
      the EC2 user-data script will destroy and recreate the instance,
      causing downtime for all services running on the Swarm.
  - severity: high
    summary: "VPC stack deletion order matters"
    detail: >
      Cannot delete the VPC stack while this stack references its CF exports.
      Teardown order: application stacks first, then compute, then VPC.
  - severity: medium
    summary: "Sites branch auto-detection"
    detail: >
      resolve_sites_branch() auto-detects the blueshift-sites git ref per
      environment. Ensure the sites repo is on the expected branch before
      deploying compute changes.

staleness_paths:
  - "infrastructure/stacks/**"
  - "scripts/ci/deploy*.sh"
  - "docker-compose*.yml"
  - ".gitlab-ci.yml"

last_verified: "2026-03-24"
verified_at_commit: "abc1234"
```

### Appendix V: Verification Requirements Traceability Matrix (VRTM)

This matrix is populated as each Phase is closed. It provides formal proof that every requirement in Section 3 was implemented and verified.

| Req ID | Requirement (short) | Story | AC / DoD Item | Verification Method | Status |
|--------|-------------------|-------|--------------|-------------------|--------|
| R-01 | YAML-based contract schema | 1.1, 1.2, 1.3 | Schema exists; contracts pass validation | Unit test, inspection | Pending |
| R-02 | JSON Schema definition | 1.1 | schema.yaml parseable; validates/rejects correctly | Unit test | Pending |
| R-03 | staleness_paths in contracts | 1.2, 1.3 | Pilot contracts include staleness_paths | Inspection | Pending |
| R-04 | last_verified and verified_at_commit | 1.2, 1.3 | Pilot contracts include versioning metadata | Inspection | Pending |
| R-05 | Contract template | 1.1 | Template exists and passes validation | Unit test | Pending |
| R-06 | Fine-grained semantic chunks | 2.1 | One chunk per semantic unit; empty arrays → zero chunks | Unit test | Pending |
| R-07 | Vector metadata (repo, section, field_path, text) | 2.1, 2.2 | Chunks carry correct metadata; db rows have metadata | Unit test | Pending |
| R-08 | Local embedding model | 2.2 | Vectors are 384-dim; no external API calls | Unit test | Pending |
| R-09 | sqlite-vec storage | 2.2 | Database created; search returns relevant results | Unit test | Pending |
| R-10 | kairos embed command | 2.2, 2.5 | CLI produces database; re-run replaces data | Unit test, integration | Pending |
| R-11 | Skip invalid contracts during embed | 2.2 | Invalid YAML skipped with error, run continues | Unit test | Pending |
| R-12 | MCP server with tools | 2.3, 2.5 | Server starts; tools registered; Claude Code configurable | Unit test, integration | Pending |
| R-13 | find_relevant_contracts | 2.3 | Docker query → compute; deduplicates by repo | Unit test, integration | Pending |
| R-14 | get_contract | 2.3 | Returns full contract; error for nonexistent | Unit test | Pending |
| R-15 | list_contracts | 2.3 | Returns identity summaries for all contracts | Unit test | Pending |
| R-16 | check_staleness(repo_name) | 1.5, 2.4 | Returns report for named repo; handles missing workspace | Unit test, integration | Pending |
| R-17 | check_staleness() all | 1.5, 2.4 | Returns aggregate report for all contracts | Unit test, integration | Pending |
| R-18 | Hold db connection for session | 2.3, 2.5 | Server loads model+db on startup; no cold start per query | Integration | Pending |
| R-19 | Aggregation script | 1.4 | kairos aggregate produces markdown | Unit test | Pending |
| R-20 | Ecosystem digest content | 1.4 | Digest has summaries, dependency table, gotchas sorted | Unit test, inspection | Pending |
| R-21 | Fallback when MCP unavailable | 1.4 | Agent can answer dependency questions from digest alone | Manual | Pending |
| R-22 | git diff for staleness | 1.5 | Staleness checker runs git diff against staleness_paths | Unit test | Pending |
| R-23 | STALE report with changed files | 1.5, 2.4 | Report lists changed files when STALE | Unit test | Pending |
| R-24 | CURRENT report | 1.5 | No changes in staleness_paths → CURRENT | Unit test | Pending |
| R-25 | UNKNOWN for missing repos | 1.5 | Non-existent repo → UNKNOWN with message | Unit test | Pending |
