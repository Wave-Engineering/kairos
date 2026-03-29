# Lessons from Automated Estimator

Reference document capturing architecture, patterns, and design insights from
the [`automated-estimator`](https://gitlab.com/analogicdev/internal/tools/automated-estimator)
project. This prior work demonstrated how AI agents and humans can collaborate
through a structured, multi-pass pipeline to categorize, classify, decompose,
and understand complex requirements. The patterns documented here directly
inform the design of Kairos contract initialization and future topic-based
contract workflows.

Source: https://gitlab.com/analogicdev/internal/tools/automated-estimator

---

## 1. Project Overview

Automated Estimator is a Streamlit-based application that transforms a
multi-hour manual cybersecurity requirement estimation process into a guided
5-minute workflow. It ingests Excel spreadsheets containing hundreds or
thousands of raw requirements and guides a human operator through four
progressive passes, each producing a refined artifact that feeds the next.

The core philosophy: **AI does what it does well (semantic processing, pattern
recognition, distillation), and the human does what they do best (judgment,
decision-making, domain knowledge).** The system is an "assist," not an
"appliance."

### Tech Stack

- **UI:** Streamlit (Python)
- **Database:** SQLite — per-project databases + a global topics database
- **AI:** AWS Bedrock — Claude (Haiku/Opus) for reasoning, Titan Embeddings v2
  for semantic search
- **Export:** openpyxl for Excel generation with formatting, hyperlinks, and
  color-coded compliance status

---

## 2. The Four-Pass Pipeline

The application implements a **Pipes-and-Filters architecture**. Each pass is a
self-contained filter that reads from and writes to a shared SQLite database
(the pipe). Passes are loosely coupled — they share data through the database,
not through in-memory state.

```
Pass 1: Binning        →  Pass 2: Classification  →  Pass 3: Epics  →  Pass 4: Estimation
upload + categorize       compliance labeling         group into epics   assign hours + export
      ↕                         ↕                          ↕                    ↕
                    Project Database (SQLite)
```

### Pass 1: Upload & Bin (Categorize)

**Purpose:** Ingest requirements from Excel and assign each to a semantic
category (bin) within a user-selected topic.

**What the AI does:**
- Semantic column detection — finds the "requirements" column even if named
  "User Stories" or has typos, using Titan Embeddings with cosine similarity
  (threshold 0.3) and fallback to string-matching heuristics
- Semantic binning — embeds each requirement and computes cosine similarity
  against pre-embedded search terms for each bin. Uses a dual-strategy
  approach: max-score as primary (threshold 0.40), ensemble average of top-3
  as fallback (threshold 0.35). Requirements that match neither strategy go
  to an "Other" bin
- Topic creation wizard — generates bin structures from a human-provided topic
  name + description via Claude, with iterative refinement

**What the human does:**
- Selects topics (domain categories) to bin against
- Reviews quality tiers: requirements are scored 0-100 by confidence
  (length + keyword presence + structural prefix) and bucketed into
  HIGH (75-100), MEDIUM (30-74), LOW (0-29). LOW are shown first for
  discard/keep decisions, then MEDIUM. HIGH are auto-accepted
- Confirms or overrides auto-detected column mapping
- Creates and refines topics via call-and-response with the AI

**Key artifacts:**
- `requirements` table populated with `bin_id` assignments
- `bins` table populated from selected topics
- Embedding cache in `topics.db` (search term embeddings persisted as BLOBs)

**Data structures:**

```sql
-- Global topics database (topics.db)
topics:       id TEXT PK, name, description, created_by, created_at
bins:         id INT PK, topic_id FK, name, description
search_terms: id INT PK, bin_id FK, term TEXT, embedding BLOB

-- Per-project database
requirements: id INT PK, text, bin_id FK, excel_index, compliance_status,
              classified_by, created_at
bins:         id INT PK, name, description, session_id
```

### Pass 2: Classify (Assess Compliance)

**Purpose:** Assign a compliance status to each requirement:
`complies | partially_complies | non_compliant | not_applicable | unclassified`.

**What the AI does:**
- Guided interview mode — analyzes requirements in batches via Claude to
  discover thematic patterns, generates targeted yes/no questions for the human
  (e.g., "Do you currently have MFA?"), and bulk-classifies matching
  requirements based on answers
- User-directed command parsing — human types natural language commands like
  "mark all encryption requirements except SSH as non-compliant." AI parses
  intent via Claude Haiku, expands keywords with synonym generation, runs
  semantic search, and applies with confidence gating
- Informational Q&A — answers questions about the requirement set using
  semantic search + optional knowledge base RAG, without modifying data

**What the human does:**
- Answers interview questions (guided mode)
- Issues classification commands (user-directed mode)
- Reviews uncertainty UI when confidence is low (see Section 3)
- Manually classifies individual requirements via dropdowns
- Adjusts similarity threshold via slider (0.3-0.9, default 0.55)

**Key design decisions:**
- Config-driven prompts — the two core LLM prompts (`keyword_expansion` and
  `classification_intent`) are stored in `ae-config.yaml`, not in Python code
- Dual-model invocation — pattern analysis uses Claude with temperature 0.3
  (slightly creative), command parsing uses temperature 0.1 (deterministic)
- Audit trail — every classification records `classified_by` as `ai_semantic`,
  `ai_semantic_reviewed`, `manual`, or `agent`
- Soft gate — the pass allows proceeding even with partial classification
  (`can_proceed=True` always)

### Pass 3: Create Epics (Group into Work Packages)

**Purpose:** Group non-compliant/partially-compliant requirements into named
epics, each labeled as Customer NRE (billable) or Internal NRE (company
investment).

**What the AI does:**
- Natural language requirement selection — human types "select all firewall
  requirements" in a chat interface, AI parses intent and runs semantic search,
  returns a delta (added/removed) with undo support
- Bulk assignment via hybrid matching algorithm (v2):
  1. Embeds all epic descriptions via Titan
  2. Extracts keywords per epic via Claude Haiku
  3. For each requirement, computes: `score = cosine_similarity + keyword_boost + learning_boost`
  4. Buckets into HIGH (≥0.70), MEDIUM (0.50-0.70), LOW (<0.50)
  5. In high-accuracy mode: LOW items get a second LLM reasoning pass
  6. In deep mode: every item gets LLM reasoning (most accurate, most expensive)
- Glance generation — writes a 2-3 sentence executive summary per epic via
  Claude Haiku, stored in `epics.glance`

**What the human does:**
- Names epics and writes descriptions
- Sets NRE type (customer vs. internal) per epic
- Reviews three-tier assignment results: HIGH auto-assigned, MEDIUM need
  radio-button confirmation, LOW need manual multiselect
- Clicks "Commit All Assignments" — nothing writes to DB until this point
- Can use chat-based AI selection and manual checkboxes simultaneously (shared
  state via `st.session_state.selected_requirements`)

**Key design decisions:**
- Session-scoped learning — when the human corrects an AI assignment, the
  system extracts patterns and applies a learning boost to future assignments
  in the same session. Not persisted across sessions (deliberate simplicity)
- Nothing writes to DB until commit — all intermediate state lives in session
  state. The human reviews the full picture before any database mutation
- Three assignment modes (fast/high_accuracy/deep) give users a
  cost-vs-accuracy dial

### Pass 4: Estimate & Export

**Purpose:** Human enters hour estimates per epic, system generates a
professional Excel report with NRE breakdown.

**What the AI does:**
- Nothing in this pass directly. The AI's contribution was fully materialized
  in Pass 3's glance generation. The human reads the AI-generated glance and
  uses that context to estimate effort.

**What the human does:**
- Reviews each epic's AI glance, description, and requirement count
- Enters hour estimates via number inputs (step size: 8 hours = 1 day)
- Exports to Excel (3 sheets: NRE Breakdown, Epic Summary, Requirements Detail)
- Optionally backfills the original source Excel with compliance status and
  epic assignments, matched by `excel_index` (not database ID)

---

## 3. The Call-and-Response Inference Pattern

This is the core collaboration model. It appears in multiple forms throughout
the pipeline.

### The Basic Loop

```
Human provides direction (natural language)
    ↓
AI processes: parses intent, searches, reasons
    ↓
AI distills results into a reviewable artifact
    ↓
┌─────────────────────────────┐
│ Confidence assessment       │
│ (similarity, length, keywords, volume) │
└─────────────────────────────┘
    ↓ HIGH              ↓ LOW
Auto-execute        Show review UI
                        ↓
                    Human sees:
                    • Why uncertain (specific reasons)
                    • Preview of matched items
                    • Match quality statistics
                    • Multiple choices:
                      1. Proceed Anyway
                      2. Tighten Threshold
                      3. Show All Matches
                      4. Cancel
```

### The Topic Creation Wizard (Purest Expression)

1. Human provides topic name + description (the "call")
2. AI generates a structured bin set with names, descriptions, and 15 diverse
   search terms each (the "response")
3. Human reviews: modified/added bins highlighted with 🔸 markers, auto-expanded
4. Human issues refinement instruction in natural language: "Add more bins for
   user permissions" (another "call")
5. AI regenerates the modified bin set + a `changes_summary` explaining what
   changed (another "response")
6. Loop continues until human clicks "Accept & Save Topic"

This is exactly the pattern we want for contract section authoring.

### Confidence Assessment Heuristics (Pass 2)

The `_assess_match_confidence()` function combines four independent quality
signals into a composite score:

| Heuristic | What it checks | Threshold |
|-----------|---------------|-----------|
| Average similarity | Mean cosine similarity of matched items | < 0.80 reduces confidence |
| Short text ratio | % of matches with < 30 characters | > 30% is suspicious |
| Keyword presence | % of matches containing the searched keywords | < 20% is suspicious |
| Result set size | Total number of matches at low confidence | > 100 triggers caution |

If the composite drops below 0.75, the system flags `needs_human_review = True`
and returns the full match set with preview samples. The human never makes a
decision based on a black-box confidence score — they see the specific reasons
and the actual data.

### Design Principle

> "When automation is not nearly certain, ask the human for guidance rather
> than silently filtering."

The system never silently drops data, never auto-approves uncertain operations,
and never presents binary approve/reject — it always offers a spectrum of
choices that let the human calibrate the AI's behavior.

---

## 4. Architecture Patterns

### 4.1 Pass Contract (Abstract Base Class)

All passes implement a common interface defined in `passes/base.py`:

```python
class Pass(ABC):
    @abstractmethod
    def render(self, project_name: str) -> PassResult: ...

    @abstractmethod
    def validate_preconditions(self, project_name: str) -> tuple[bool, str]: ...

    @abstractmethod
    def is_complete(self, project_name: str) -> bool: ...

    def get_state(self, key, default=None):
        """Namespaced session state: pass_<classname>_<key>"""

    def set_state(self, key, value):
        """Namespaced session state: pass_<classname>_<key>"""

@dataclass
class PassResult:
    success: bool       # Did execution proceed without system errors?
    message: str        # Human-readable status
    can_proceed: bool   # Is the next-pass button enabled?
```

**Key properties:**
- Each pass self-validates preconditions (no external orchestration needed)
- `PassResult` carries gate state — whether the user can advance
- Session state is namespaced by class name to prevent cross-pass coupling
- Data persistence is exclusively via SQLite — session state is ephemeral

### 4.2 Pipes-and-Filters with Soft Gates

The pipeline is sequential but non-blocking. Each pass's `can_proceed` flag
controls navigation but doesn't enforce it rigidly. Pass 2 allows proceeding
with partial classification. Pass 4 allows export with incomplete estimates.
This respects the reality that human workflows are iterative — people go back
and forth.

### 4.3 Dual-Mode Operation

Almost every pass offers both AI-assisted and manual paths:

| Pass | AI Path | Manual Path |
|------|---------|-------------|
| 1 | Semantic column detection, auto-categorization | Column dropdowns, manual topic management |
| 2 | Guided interview, user-directed commands | Per-requirement dropdowns, bulk-action buttons |
| 3 | Chat-based selection, AI bulk assignment | Checkbox selector, manual epic creation |
| 4 | AI glance display (read-only) | Hour input, export buttons |

Both paths share the same underlying data and can be used simultaneously. The
AI chat and manual checkboxes in Pass 3 share `selected_requirements` in
session state — either modifies the same set.

### 4.4 Embedding Persistence and Reuse

Embeddings are expensive (AWS Bedrock API calls). The system uses a layered
caching strategy:

| Layer | Scope | Storage | Lifetime |
|-------|-------|---------|----------|
| Search term embeddings | Global (all projects) | `topics.db` BLOB column | Permanent until term replaced |
| Requirement embeddings | Per session | `st.session_state` dict | Session duration |
| Cross-pass reuse | Pass 2 → Pass 3 | Shared session state key | Session duration |

Pass 1 generates and persists search term embeddings to `topics.db` as packed
binary BLOBs (4 bytes per float32). These are generated once and reused across
all projects that use that topic.

Pass 2 generates requirement embeddings and caches them in session state. Pass 3
reads Pass 2's cache to avoid re-calling Bedrock.

**Known gap:** Requirement embeddings are not persisted to disk. Opening a
project with 1,247 requirements means ~1,247 Bedrock API calls on every session
start. This is a documented performance bottleneck.

### 4.5 Progressive Disclosure / Tiered Review

The system consistently presents uncertain items in tiers to reduce cognitive
load:

- **Pass 1 quality review:** LOW tier first (discard/keep?), then MEDIUM.
  HIGH auto-accepted — never shown.
- **Pass 3 bulk assignment:** HIGH auto-assigned, MEDIUM shown as radio buttons
  (confirm/change), LOW shown as multiselects (assign from scratch).

The human only ever reviews what's uncertain. The AI handles the obvious cases
silently.

### 4.6 Graceful Degradation

Every AI-dependent path has a fallback:

| Feature | Primary | Fallback |
|---------|---------|----------|
| Column detection | Titan embeddings + cosine similarity | Heuristic scoring (name patterns, text length, keyword presence) |
| Requirement binning | Embedding-based semantic matching | String/keyword matching |
| Classification commands | Semantic search + LLM intent parsing | Regex keyword extraction |
| Epic keywords | LLM-generated keyword lists | Regex word extraction |
| Glance generation | Claude Haiku summary | First sentence of description |

If Bedrock is unavailable, the system continues with reduced accuracy rather
than failing. Fallbacks are logged as warnings, not errors.

### 4.7 Config-Driven Prompts

LLM prompts are stored in `ae-config.yaml` under namespaced keys:

```yaml
classification:
  prompts:
    keyword_expansion: |
      Given these search keywords: {keywords}
      Generate a list of related terms, synonyms, and acronyms...
    classification_intent: |
      Parse the following command into a structured intent...
  embedding:
    model_id: "amazon.titan-embed-text-v2:0"
    dimensions: 1024
    normalize: true
  llm:
    model_id: "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    max_tokens: 500
    temperature: 0.1
```

This allows non-code tuning of LLM behavior. Different operations use different
temperature settings — creative tasks (pattern discovery) at 0.3, deterministic
tasks (command parsing) at 0.1.

### 4.8 Session State Namespacing

Each pass uses `pass_<classname>_` prefixed keys for Streamlit session state.
This prevents accidental coupling between passes. Shared state (like
`selected_topic_ids` or `requirement_embeddings`) uses unprefixed global keys
by deliberate choice — these are the explicit contracts between passes.

---

## 5. Data Architecture

### Dual Database Design

| Database | Scope | Contents | Access Pattern |
|----------|-------|----------|---------------|
| `data/topics.db` | Global | Topics, bins, search terms + embeddings | Read by all projects, written during topic management |
| `data/projects/<name>.db` | Per-project | Requirements, bins, epics, epic_requirements, classification_history, project_context, project_glossary | Read/written by all passes for one project |

The separation ensures topics are reusable across projects while project data
is isolated.

### Schema Evolution

Database migrations are stored as numbered SQL files
(`database/migrations/001_*.sql`, `002_*.sql`). Each migration is applied
idempotently on project open. This allows schema changes without breaking
existing project databases.

Backward compatibility is also maintained via `PRAGMA table_info()` guards —
functions check whether a column exists before querying it.

### Data Flow Through the Pipeline

```
Excel Upload
     ↓
[Pass 1] requirements table: id, text, bin_id, excel_index
         compliance_status = 'unclassified'
     ↓
[Pass 2] requirements table: compliance_status updated
         classified_by = 'ai_semantic' | 'manual' | etc.
         classification_history table: audit log
     ↓
[Pass 3] epics table: id, name, description, glance, nre_type
         epic_requirements: epic_id, requirement_id (many-to-many)
         Filter: compliance_status NOT IN ('complies', 'not_applicable')
     ↓
[Pass 4] epics table: estimated_hours updated
         Export: 3-sheet Excel with NRE breakdown
```

---

## 6. Lessons for Kairos

### What to Adopt

**1. The call-and-response loop for contract authoring.** When initializing a
contract, the agent should explore the repo, generate a draft, and present it
section by section for human review. The human should be able to issue
natural-language refinement instructions ("add the Redis dependency," "that
export name is wrong") and the agent should regenerate the affected section
with a changes summary.

**2. Confidence-gated discovery.** When the agent explores a repo, it will find
some things with high confidence (CloudFormation exports in a CDK stack) and
some with low confidence (a possible API endpoint mentioned in a comment).
Present these in tiers — auto-accept the obvious, surface the uncertain.

**3. Tiered review for cross-reference validation.** When checking a new
contract against existing contracts, bucket findings into
HIGH (confirmed dependency match), MEDIUM (probable relationship), and
LOW (possible but uncertain). Only surface MEDIUM and LOW for review.

**4. Embedding persistence for semantic matching.** If Kairos ever does
semantic similarity between contracts (e.g., finding related services,
detecting duplicate exports), cache embeddings to avoid re-computation.

**5. The Pass base class contract.** A `PassResult` with `success`, `message`,
and `can_proceed` is a clean way to represent gate state in a multi-step
workflow. The namespaced state pattern prevents cross-step coupling.

**6. Dual-mode operation.** Always offer both AI-assisted and manual paths.
The agent should be able to auto-discover contract contents, but the human
should also be able to directly add/edit any field.

**7. Config-driven prompts.** If Kairos uses LLM inference for contract
discovery, store prompts in config (YAML or similar), not in Python code.

### What to Adapt

**1. Database vs. YAML files.** Automated Estimator uses SQLite as the shared
pipe between passes. Kairos contracts are YAML files. The "database" in
Kairos is the `contracts/` directory tree. The MCP server already provides
CRUD operations. The question is whether initialization should use the MCP
tools or write YAML directly.

**2. Streamlit UI vs. CLI/MCP.** Automated Estimator's human interaction is
via a Streamlit web UI. Kairos initialization will likely be a CLI command or
Claude Code skill. The call-and-response pattern works in both modalities —
the "UI" is the Claude Code conversation itself.

**3. Single-project vs. cross-project.** Automated Estimator processes one
project at a time. Kairos contracts describe relationships between multiple
repos. The cross-reference validation step has no direct analog in
Automated Estimator — it's a new capability.

**4. Topics as contract collections.** Automated Estimator's topics (collections
of bins with search terms) map to Kairos's future "topics" or "collections."
A topic in Kairos would be a named collection of contracts that a subject
(repo, document tree, compliance framework) can subscribe to. The
`selected_topic_ids` pattern — human selects which collections apply before
the AI starts processing — is directly applicable.

### What to Skip

**1. Excel import/export.** Kairos contracts are YAML, not spreadsheets.

**2. NRE cost tracking.** Not relevant to contract initialization.

**3. Compliance taxonomy (complies/non_compliant/etc.).** The five-value
classification is domain-specific to cybersecurity estimation.

**4. Streamlit session state patterns.** Claude Code skills don't use Streamlit.
The namespacing concept is useful, but the implementation is different.

---

## 7. The Hybrid Matching Algorithm (Pass 3, v2)

This is the most sophisticated algorithm in the system and worth documenting
in detail, as it may inform future semantic matching in Kairos.

### Problem

Pure cosine similarity between requirement embeddings and epic embeddings
produced 0% high-confidence matches. Requirements are terse mandates
("System shall support MFA") while epics are broad descriptions
("Authentication and access control infrastructure"). The semantic gap is
too large for embeddings alone.

### Solution: Three-Signal Hybrid Score

```
base_similarity     = cosine_similarity(req_embedding, epic_embedding)
keyword_boost       = min(keyword_match_count / 8.0, 1.0) * 0.50
learning_boost      = pattern_match_from_session_corrections (up to +0.20)
final_score         = min(base_similarity + keyword_boost + learning_boost, 1.0)
```

- **Embeddings** capture semantic similarity (broad strokes)
- **Keywords** (LLM-extracted per epic) capture domain vocabulary (precision)
- **Learning** (session-scoped corrections) adapts to the specific project

### Confidence Tiers

| Tier | Threshold | Action |
|------|-----------|--------|
| HIGH | ≥ 0.70 | Auto-assigned, shown as confirmation |
| MEDIUM | 0.50 – 0.70 | Shown as radio button (suggested epic + alternatives) |
| LOW | < 0.50 | Shown as multiselect (human picks from all epics) |

### Three Assignment Modes

| Mode | Approach | Cost | Use Case |
|------|----------|------|----------|
| Fast | Embeddings + keywords only | ~$0.02 | Quick first pass |
| High Accuracy | Fast + LLM reasoning for LOW items | ~$0.50 | Production use |
| Deep | LLM reasoning for every item | ~$5.00 | Maximum accuracy |

### Result

After introducing the keyword boost, high-confidence matches went from 0% to
~80% of assignments. The learning boost adds another ~5-10% as the human
makes corrections during the session.

---

## 8. File Reference

Key files in the automated-estimator codebase for future reference:

### Core Architecture
- `app.py` — Pipeline orchestrator, pass registry, page routing
- `passes/base.py` — `Pass` abstract base class and `PassResult` dataclass
- `passes/INTERFACE.md` — The pass contract specification
- `ae-config.yaml` — All model IDs, prompt templates, thresholds, UI settings

### Pass 1: Binning
- `pass_01_binning/binning_pass.py` — Legacy monolithic pass (upload + categorize)
- `pass_01_binning/upload_pass.py` — Refactored upload-only pass
- `pass_01_binning/categorize_pass.py` — Refactored categorization pass
- `pass_01_binning/agent_topic_creator.py` — LLM-based topic/bin generation and refinement
- `pass_01_binning/topic_selection_ui.py` — Topic creation wizard UI
- `pass_01_binning/sequential_review.py` — Two-stage quality review (LOW → MEDIUM)
- `pass_01_binning/semantic_binning.py` — Cosine similarity engine, embedding cache

### Pass 2: Classification
- `pass_02_classification/classification_pass.py` — All UI and routing
- `pass_02_classification/agent_classification_assistant.py` — LLM interaction (interview, commands, Q&A)
- `pass_02_classification/semantic_search.py` — Embedding pipeline, keyword expansion, confidence assessment
- `pass_02_classification/kb_search.py` — Knowledge base RAG (markdown chunking + semantic search)

### Pass 3: Epics
- `pass_03_epics/epic_creation_pass.py` — Pass entry point and UI
- `pass_03_epics/agent_epic_assigner.py` — Hybrid matching algorithm (v2)
- `pass_03_epics/ai_assignment_ui.py` — Three-tier review workflow
- `pass_03_epics/requirements_helpers.py` — Chat + checkbox requirement selection
- `pass_03_epics/generate_glance.py` — AI summary generation
- `pass_03_epics/AI_EPIC_ASSIGNMENT.md` — Algorithm design rationale (v1 → v2)

### Pass 4: Estimation
- `pass_04_estimation/estimation_pass.py` — Complete pass implementation
- `database/db_utils.py` — `export_to_excel()`, `backfill_original_spreadsheet()`

### Data Layer
- `database/db_utils.py` — All project database operations
- `database/topics_db.py` — Global topics database operations
- `database/seeds/default_topics.sql` — Seed data for system topics
- `database/migrations/` — Numbered schema migration files
