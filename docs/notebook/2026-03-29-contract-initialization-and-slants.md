# Contract Initialization, Slants, and Findings

**Date:** 2026-03-29
**Participants:** BJ, epoch :clock4: (kairos)

Session exploring how Kairos should initialize a contract database from a
codebase. Started with a review of patterns from `automated-estimator`, then
evolved into a conceptual model for multi-perspective codebase inspection.

---

## Starting Point: The Problem

Kairos has four hand-authored contracts (vpc, compute, manifests, littleguy).
They were written by an agent doing ad-hoc deep dives of each codebase. There
is no repeatable workflow for producing new contracts. The question: **how
should an agent go from "here's a repo I've never seen" to "here's a complete,
accurate contract"?**

BJ's additional framing: contracts shouldn't be limited to source code repos.
Future use cases include document trees (requirements, designs), compliance
frameworks (NIST 800-53, ISO 27001), legal compliance (HIPAA), tool/API usage,
and even documentation voice consistency. For now, source tree contracts are
the focus, but the design must not foreclose the broader vision.

---

## Prior Art: automated-estimator

We studied the [automated-estimator](https://gitlab.com/analogicdev/internal/tools/automated-estimator) codebase in depth. Full
analysis in `docs/lessons-from-automated-estimator.md`. The key patterns that
carry forward:

### Call-and-Response Inference

The collaboration model where a human provides direction, the AI distills
complexity into a reviewable artifact, and the human issues refinement
instructions in natural language. The loop continues until the human accepts.
The topic creation wizard in Pass 1 is the purest example.

**Conclusion:** This is the right interaction model for contract authoring. The
agent explores, produces a draft, presents it section by section, and the human
refines via natural language.

### Confidence-Gated Actions

When the AI is uncertain, it surfaces the uncertainty explicitly with specific
reasons and gives the human calibrated choices (proceed, tighten threshold,
inspect all, cancel). Never silently acts on low confidence.

**Conclusion:** Discovery findings should have confidence scores. High-confidence
findings are auto-accepted, uncertain ones are surfaced for human review.

### Tiered Review (Progressive Disclosure)

Present only what's uncertain. HIGH confidence items are invisible (auto-
accepted). LOW items are shown first, then MEDIUM. Reduces cognitive load.

**Conclusion:** When presenting discovery results, tier them. Don't dump
everything on the human.

### Topics as Collections

In AE, a "topic" is a named collection of semantic categories (bins) that you
apply to requirements. You select which topics are relevant before processing
begins.

**Conclusion:** This concept carries forward but splits into two orthogonal
concepts in Kairos: Topics (subject matter) and Slants (analytical perspective).
See below.

---

## Key Concept: Topics vs. Slants

This was the central conceptual breakthrough of the session.

### The Problem with a Flat Scan

A naive `kairos init` would scan a repo and produce a flat list: "here's what
it provides, here's what it consumes, here are some gotchas." But this misses
the richness of what a codebase actually contains. Different stakeholders care
about different things. A compliance officer, an operator, and an onboarding
developer would all extract different insights from the same code.

### Topics = What You're Looking At (The Noun)

Topics are subject matter categories. Concrete concepts. If you were filing
things, topics are the labels on the file folders.

Examples: cybersecurity, networking, user authentication, Docker orchestration,
database management, CI/CD pipeline.

A contract **lives in** a topic. The vpc contract lives in a "networking" or
"infrastructure" topic. A Keycloak contract would live in an "authentication"
topic.

### Slants = How You're Looking At It (The Lens)

Slants are analytical perspectives. Orthogonal to topics. Each slant is like
a specialist editor reviewing a manuscript — they all read the same text but
notice fundamentally different things.

A slant is **applied across** topics. You can look at the VPC through a
constraints lens, a failure-modes lens, or a compliance lens — each produces
different insights about the same subject.

### They're Orthogonal Axes

```
                         Topics (subject matter)
                    VPC    Compute    Manifests    Auth
               ┌─────────┬──────────┬───────────┬────────┐
  constraints  │   ...    │   ...    │   ...     │  ...   │
               ├─────────┼──────────┼───────────┼────────┤
  implicit-    │   ...    │   ...    │   ...     │  ...   │
  constraints  │          │          │           │        │
               ├─────────┼──────────┼───────────┼────────┤
  failure-     │   ...    │   ...    │   ...     │  ...   │
  modes        │          │          │           │        │
               └─────────┴──────────┴───────────┴────────┘
```

Every cell is a potential set of findings. The topic tells you which contract
file they belong to. The slant tells you why they were captured and what kind
of insight they are.

### BJ's Book Editor Analogy

A book with multiple specialist editors:
- One focuses on grammar and syntax
- One focuses on continuity
- One checks character consistency against archetypes
- One reviews from a legal perspective (prior art, copyright)
- One from a marketing perspective
- One for content appropriateness

They all read the same book. They all produce notes. But a grammar editor's
notes and a legal editor's notes are completely different artifacts, found
through completely different analytical processes. You wouldn't ask them to
share a highlighting pass.

---

## Key Concept: What a Slant IS

A slant has two properties:

1. **name** — The tag. Used for filtering and categorization.
2. **perspective** — A description of the analytical lens. Serves dual purpose:
   - **At discovery time:** The prompt preamble that tells an agent what to
     look for, what patterns to recognize, what questions to ask
   - **At consumption time:** The contextualization key that tells a reader
     "this finding was produced by an agent looking for this kind of thing"

The perspective IS the slant's identity. It's the editorial specialty.

### Example

```yaml
name: constraints
perspective: >
  You are reviewing this codebase to identify hard limits, resource
  ceilings, dependency locks, capacity boundaries, and environmental
  restrictions. Look for things that bound what the system can do —
  not what it chooses not to do (that's scope), but what it *cannot*
  do given its current design and dependencies.
```

### Initial Slant Ideas (Not Finalized)

| Slant | Focus |
|-------|-------|
| constraints | Hard limits, resource caps, version pins, provider quotas |
| requirements | Functional behaviors: what must be true for the system to work |
| non-goals | What the system explicitly delegates or refuses to handle |
| design-patterns | Architectural patterns in use |
| design-antipatterns | Known debt, coupling, brittleness |
| design-decisions | Conscious architectural choices and their rationale |
| scope-limits | Boundaries of what this system handles vs. external |
| implicit-constraints | Preconditions, invariants, input formats enforced in code but not documented |

Additional candidates discussed but not committed:
- failure-modes
- operational-runbooks
- security-surface
- data-lifecycle

### Open Question: Fixed vs. Extensible

**Conclusion reached:** Slants must be extensible. No UI required yet, but we
need to codify what a slant *is* so new ones can be defined. The schema should
be: name + perspective (at minimum). Preparation hints (focus areas, file
patterns) are optional and advisory.

---

## Key Concept: Findings

### The Problem with Going Straight to Contracts

A slant agent reviewing a codebase doesn't produce contract entries. It
produces insights — things it noticed from its particular perspective. These
insights:

- May synthesize information from multiple sources ("users are all left-handed"
  assembled from three paragraphs that never say that explicitly)
- May not have an obvious topic assignment yet
- May not map cleanly to any existing contract schema field
- May overlap with findings from other slants (same underlying fact, different
  analytical angle)

Going directly from codebase to contract skips a step. It's like going from
Data to Knowledge without addressing the Information link in the D2W chain.

### What a Finding Is

BJ's analogy: object detection vs. object discrimination.

- Object detection: "This is an object. I don't know what kind yet."
- Object discrimination: "This object is a basketball."

A finding is **object detection**. It says: "I found something that matters,
viewed from this perspective. I can tell you what I found, why it matters from
my slant, and where I found it. But I don't yet know what kind of contract
entry it becomes — or if it even does."

A finding is **pre-classification**. It's the output of a slant agent before
the discrimination/refinement pass.

### Properties of a Finding

| Property | Description |
|----------|-------------|
| **slant** | Which perspective produced it |
| **summary** | What was found (agent's synthesis — may not appear verbatim in any source) |
| **reasoning** | Why this matters from this slant's perspective |
| **confidence** | How certain the agent is that this is a real insight |
| **sources** | Provenance: which files/lines/docs the agent drew from |
| **topic** | NOT ASSIGNED YET at this stage |
| **contract_section** | NOT ASSIGNED YET at this stage |

### Sketch of a Finding

```yaml
finding:
  slant: constraints
  summary: "Private subnet egress relies on a single NAT Gateway in one AZ"
  reasoning: >
    The CDK stack sets nat_gateways=1 on the VPC construct. This is a
    deliberate cost optimization but means all private subnet egress
    routes through one AZ. If that AZ has an outage, egress fails.
  confidence: high
  sources:
    - file: infrastructure/stacks/blueshift_vpc_stack.py
      lines: [47, 52]
      what: "nat_gateways=1 parameter on ec2.Vpc construct"
    - file: README.md
      lines: [23]
      what: "Mentions cost optimization as rationale"
```

Note: This is a *sketch*, not a finalized schema. The finding concept needs
more work before we lock down fields.

---

## Key Concept: The Three-Stage Pipeline

The session converged on a three-stage model:

```
Stage 1: Slant-Based Discovery
  Codebase → [Slant Agents] → Findings

Stage 2: Refinement / Discrimination
  Findings → [Classification + Grouping + Human Review] → Contract Entries

Stage 3: Contract Assembly
  Contract Entries → [Structured into schema, cross-referenced] → Contracts
```

### Stage 1: Slant-Based Discovery

Each slant agent runs independently against the codebase. They are
parallelizable. Each produces a set of findings from its perspective.

**Key decision:** Each slant owns its own preparation. There is no universal
embedding pass before slanting. A constraints agent reads IaC configs and looks
for numeric parameters. An implicit-constraints agent traces code paths and
finds preconditions. A compliance agent maps behaviors against a control
catalog. Their workflows are fundamentally different — like a lawyer and a
style editor approaching the same manuscript.

**Rationale:** We considered a shared embedding pass, but concluded that
different slants would not benefit from the same embedding vector. What matters
to an API-expectations agent is not what matters to a requirements-management
agent. Forcing a shared preparation would either be too generic to be useful
or would bias toward one slant's needs.

### Stage 2: Refinement

Findings from all slants are merged and classified:
1. **Grouping** — multiple slants may have found aspects of the same thing
2. **Classification** — "this is a gotcha" / "this is a provides" / "this is
   something we don't have a schema field for yet"
3. **Topic assignment** — "this belongs in the vpc contract"
4. **Human review** — call-and-response, tiered by confidence

This is where the AE patterns apply most directly — tiered review, confidence
gating, dual-mode operation.

### Stage 3: Contract Assembly

Classified entries are assembled into the contract schema, validated, cross-
referenced against existing contracts, and written to YAML.

---

## The D2W Chain Mapping

This came up when discussing whether findings should go directly into contracts
or through an intermediate step.

| D2W Stage | Kairos Analog | Transformation |
|-----------|--------------|----------------|
| **Data** | Raw codebase | Files, configs, code, docs — unprocessed |
| **Information** | Findings | Slant agents extract meaning — "this matters, from this angle" |
| **Knowledge** | Contracts | Findings classified, assigned to topics, structured into schema |
| **Wisdom** | Ecosystem queries | Reasoning across contracts — "what breaks if I change this?" |

BJ's concern: jumping from Data (codebase) directly to Knowledge (contracts)
skips the Information stage. Findings *are* the Information stage. They capture
"what did we notice and why" before "how do we categorize and structure it."

---

## Open Questions (Not Yet Resolved)

### 1. Finding Deduplication Across Slants

When two slants find the same underlying fact but frame it differently, do we:
- Merge them into one finding with multiple slant tags?
- Keep them as separate findings that get merged during refinement?
- Something else?

The "single NAT gateway" fact might appear as:
- constraints slant: "resource capacity limitation"
- failure-modes slant: "single point of failure for egress"
- compliance slant: "violates HA requirements"

These are different *insights* about the same *fact*. The discrimination pass
needs to handle this.

### 2. Finding Schema

The sketch above is preliminary. What fields does a finding actually need?
Is `reasoning` separate from `summary`, or should they be one field? Do we
need a `severity` or `impact` field at the finding stage, or is that only
meaningful after classification?

### 3. How Does the Refinement Pass Work?

This is the least-defined stage. Is it:
- A single agent that reads all findings and classifies them?
- A call-and-response loop with the human for each finding?
- An automated first pass (group obvious ones) + human review for ambiguous ones?
- Something informed by AE's three-tier pattern?

### 4. Slant Preparation

We concluded each slant owns its own preparation. But should the slant
definition include preparation hints? If so, what form? File patterns?
Focus area descriptions? Tool suggestions?

### 5. Schema Extensions

The current contract schema (provides, consumes, interfaces, gotchas,
operational) may not have fields for everything findings produce. Do we:
- Extend the schema with new sections (constraints, decisions, scope)?
- Keep findings as a separate artifact alongside contracts?
- Let the refinement pass force findings into existing fields (lossy)?

### 6. Where Do Slant Definitions Live?

In the Kairos repo? In the contract schema? In a separate config? As MCP
resources? If they're extensible, users need to be able to define them
somewhere.

### 7. How Do Topics Get Assigned?

In AE, the human selects topics before processing. In Kairos, topic assignment
happens after findings are produced. Is topic assignment:
- Agent-suggested during refinement?
- Based on which repo/codebase the finding came from? (one repo = one topic?)
- A separate classification step?
- Human-assigned?

---

## Conclusions Reached

1. **Topics and slants are orthogonal.** Topics are subject matter (what).
   Slants are analytical perspectives (how). They compose as a matrix.

2. **A slant is defined by a name and a perspective.** The perspective serves
   dual purpose: prompting agents during discovery and contextualizing findings
   for consumers.

3. **Slants must be extensible.** No fixed taxonomy. The schema for a slant
   definition must be codified so new slants can be created.

4. **Discovery produces findings, not contracts.** Findings are pre-
   classification insights. They know which slant produced them but may not
   know their topic, type, or contract section yet.

5. **Each slant owns its own preparation.** No shared embedding pass. Different
   slants have fundamentally different exploration workflows.

6. **The pipeline is three stages: Discovery → Refinement → Assembly.** This
   maps to the D2W chain: Data → Information → Knowledge.

7. **automated-estimator patterns apply to refinement.** Call-and-response,
   confidence gating, tiered review, and dual-mode operation are all relevant
   to how findings become contracts.

---

## Next Steps (Not Prioritized)

- Formalize the slant definition schema (name + perspective + optional hints)
- Formalize the finding schema
- Design the refinement pipeline (findings → contract entries)
- Write a starter set of slant definitions
- Determine where slant definitions live in the repo
- Prototype: run 2-3 slants against an existing repo and see what findings
  look like in practice
- Consider schema extensions for contract entries that carry slant provenance
