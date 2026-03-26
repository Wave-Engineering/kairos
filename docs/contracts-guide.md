# Contract Authoring Guide

This guide teaches you how to write effective Kairos contracts. The audience is both human developers writing contracts by hand and AI agents generating or updating them.

**Prerequisites:**

- The [contract schema](../contracts/schema.yaml) defines every valid field, type, and enum.
- The [contract template](../contracts/templates/contract-template.yaml) is your starting point for new contracts.
- The pilot contracts in [`contracts/repos/`](../contracts/repos/) (compute, vpc, littleguy, manifests) are real examples of finished contracts.

---

## 1. What Makes a Good Contract

A contract is context for AI agents, not documentation for humans. READMEs explain how to use a project. Contracts explain what a repo *is*, what it *provides*, what it *depends on*, and what will *bite you*.

### Contract Fidelity

The value of a contract depends entirely on how accurately it represents the repo's reality. This is called **contract fidelity**.

- **High fidelity:** Every field matches the current codebase. The `provides` section lists exactly what exists. The `gotchas` reflect real traps that still apply. The `staleness_paths` cover the files that actually matter.
- **Low fidelity:** Fields are copied from a template and never updated. Gotchas describe problems that were fixed months ago. The `verified_at_commit` points to a commit from before a major refactor.

A low-fidelity contract is worse than no contract. It gives agents false confidence about a repo's behavior, leading to mistakes that are harder to debug than starting from scratch.

**Fidelity is not a one-time achievement.** Every time you change a repo's infrastructure, interfaces, or dependencies, the contract's fidelity degrades unless you update it. The staleness tracking system (section 5) exists specifically to detect this drift.

### When to Create a Contract

Not every repo needs one. Create a contract when:

- Other repos depend on this repo's outputs (CloudFormation exports, Docker networks, secrets, images).
- AI agents regularly work in this repo and need context about its operational quirks.
- The repo has non-obvious gotchas that have burned people before.

Skip a contract when:

- The repo is a one-off script or throwaway prototype.
- Nothing else depends on it and agents never work in it.
- A README already covers everything an agent would need.

---

## 2. Identity Section

The `identity` section is the first thing agents read. It determines whether a contract is relevant to their current task.

### Schema Reference

All fields are required:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Short lookup key (e.g., `compute`) |
| `full_name` | string | Full repository name (e.g., `blueshift-compute`) |
| `category` | string | Logical grouping (e.g., `infrastructure`, `deployment`) |
| `purpose` | string | One paragraph: what this repo does and why it exists |
| `archetype` | enum | Architectural pattern this repo follows |

### Choosing `name` vs `full_name`

`name` is the short key used for lookups and cross-references between contracts. `full_name` is the full repository name as it appears in your Git hosting platform.

From the VPC contract:

```yaml
identity:
  name: vpc
  full_name: blueshift-vpc
```

And from the manifests contract:

```yaml
identity:
  name: manifests
  full_name: blueshift-manifests
```

The `name` should be what people actually say when referring to the repo. If your team says "the compute stack" and not "the blueshift-compute repository," use `compute` as the name.

### Selecting a `category`

Category is a free-form string that groups related repos. Use consistent terms across your contracts. The pilot contracts use:

- `infrastructure` -- repos that provision cloud resources (vpc, compute)
- `deployment` -- repos that define how services are deployed (littleguy, manifests)

Other reasonable categories include `application`, `library`, `tooling`, and `core`. Pick what fits your ecosystem and stay consistent.

### Writing a Strong `purpose`

The `purpose` field is the single most important sentence in the contract. It tells an agent what this repo does and why it matters, in one paragraph.

**Good -- from the compute contract:**

```yaml
purpose: >
  Provisions shared platform compute infrastructure for all Blueshift projects.
  Deploys an EC2 instance running Docker Swarm into the existing VPC
  (provisioned by blueshift-vpc), with security groups, IAM roles for SSM
  access, and EIP association. The EC2 user-data bootstraps Docker Swarm,
  OpenBao agent (secrets), Littleguy (SwarmCD), and SPIRE (workload identity).
  Platform services (Traefik, Keycloak, Portainer) are deployed as the
  'blueshift' Docker Swarm stack, creating the blueshift_public overlay
  network that all downstream app projects join.
```

This works because it answers: what does it provision? Where? What depends on it? What does it bootstrap?

**Bad:**

```yaml
purpose: "Infrastructure for the platform."
```

This tells an agent nothing. It cannot determine what the repo provides, what depends on it, or whether it is relevant to the current task.

**Rules of thumb:**

- Start with the primary action: "Provisions...", "Renders...", "Contains..."
- Name the key things it creates or manages.
- Mention upstream dependencies and downstream consumers.
- Keep it to one paragraph -- save details for `provides`/`consumes`.

### Selecting an `archetype`

The `archetype` signals to agents what patterns to expect. The schema defines these values:

| Archetype | When to use |
|-----------|-------------|
| `cdk-infra` | AWS CDK stacks that provision cloud resources |
| `swarm-service` | Services deployed as part of a Docker Swarm stack |
| `compose-standalone` | Standalone Docker Compose deployments |
| `config-only` | Repos that only contain configuration (no code that runs) |
| `docs-only` | Documentation-only repos |
| `meta-tooling` | Build tools, CI templates, renderers, orchestrators |
| `library` | Reusable code packages consumed by other repos |

From the pilot contracts:

- `compute` and `vpc` use `cdk-infra` because they are CDK stacks.
- `littleguy` uses `compose-standalone` because it is a standalone Docker Compose deployment.
- `manifests` uses `meta-tooling` because it renders and delivers compose files for other repos.

---

## 3. Provides / Consumes

The `provides` and `consumes` sections define the dependency graph between repos. They are the core of what makes contracts useful: an agent working in repo A can discover that repo B provides the export it needs, or that changing an output in repo A will break repo C.

### What Goes in `provides`

Everything that other repos, services, or agents can depend on from this repo:

| Sub-field | What to list |
|-----------|-------------|
| `cloudformation_exports` | CF exports other stacks import |
| `docker_images` | Images this repo builds and publishes |
| `docker_networks` | Networks this repo creates that others join |
| `packages` | Libraries published to package registries |
| `secrets` | Secret paths this repo manages or seeds |
| `ci_templates` | CI/CD templates other repos include |

### What Goes in `consumes`

Everything this repo depends on from elsewhere:

| Sub-field | What to list |
|-----------|-------------|
| `cloudformation_imports` | CF exports imported from other stacks |
| `docker_images` | Images pulled from registries |
| `secrets` | Secret paths read from vault or other sources |
| `repos` | Direct repo-to-repo relationships |

### Granularity: When to List Individually vs. Group

List items individually when they are independently consumable. The VPC contract lists each CloudFormation export separately because other repos import them one at a time:

```yaml
provides:
  cloudformation_exports:
    - name: "blueshift-vpc-{env}-VpcId"
      description: "VPC ID for the shared Blueshift VPC"
    - name: "blueshift-vpc-{env}-VpcCidr"
      description: "VPC CIDR block (10.0.0.0/16)"
    - name: "blueshift-vpc-{env}-PublicSubnetIds"
      description: "Comma-separated public subnet IDs across 2 AZs"
    - name: "blueshift-vpc-{env}-PrivateSubnetIds"
      description: "Comma-separated private subnet IDs across 2 AZs"
    - name: "blueshift-vpc-{env}-AvailabilityZones"
      description: "Comma-separated availability zone names used by the VPC"
    - name: "blueshift-vpc-{env}-IngressEipPublicIp"
      description: "Ingress Elastic IP public address for Traefik reverse proxy"
    - name: "blueshift-vpc-{env}-IngressEipAllocationId"
      description: "Ingress Elastic IP allocation ID for EIP association in compute stack"
```

Use empty arrays when a category does not apply rather than omitting it entirely. This tells agents "I checked and there are none" rather than "I forgot to check":

```yaml
provides:
  cloudformation_exports: []
  docker_images: []
  docker_networks: []
  packages: []
  secrets: []
  ci_templates: []
```

This pattern is used by the VPC contract (which provides exports but no images, networks, packages, secrets, or templates) and by the manifests contract (which consumes many things but provides nothing to the ecosystem directly).

### Cross-Referencing Between Contracts

The `from` field in `consumes` entries should match the `name` field in the providing contract's `identity` section. This is how agents trace dependencies across the graph.

From the compute contract, which imports VPC exports:

```yaml
consumes:
  cloudformation_imports:
    - export: "blueshift-vpc-{env}-VpcId"
      from: vpc
      description: "VPC to deploy EC2 instances into"
```

The `from: vpc` matches `identity.name: vpc` in the VPC contract. An agent can follow this reference to find the VPC contract and learn about the export.

Similarly, the littleguy contract references secrets provided by other repos:

```yaml
consumes:
  secrets:
    - path: git_token
      from: compute
      description: >
        GitLab PAT (GL_READ_TOKEN) for cloning private repos. Pre-existing
        Docker secret created by CDK user-data on the Swarm node.
```

### The `repos` Sub-Field

Use `consumes.repos` to express relationships that do not fit neatly into the other categories. The `relationship` field should be a sentence explaining the dependency:

```yaml
consumes:
  repos:
    - name: compute
      relationship: >
        CDK user-data in blueshift-compute downloads littleguy files, substitutes
        SSM placeholders, creates Docker secrets, and deploys the littleguy stack.
    - name: sites
      relationship: >
        SwarmCD polls a site-order repo (rendered from blueshift-sites via
        blueshift-manifests) for the baked compose file it deploys.
```

---

## 4. Gotchas

Gotchas are the highest-value section of a contract. They capture non-obvious traps that have burned people (or will burn people) -- things that are not apparent from reading the code.

### Schema Reference

Each gotcha has three required fields:

```yaml
gotchas:
  - severity: critical    # critical, high, medium, or low
    summary: "One-line description of the trap"
    detail: >
      Full explanation: what triggers it, what the impact is,
      and how to avoid or mitigate it.
```

### Severity Guidelines

| Severity | Use when... | Example |
|----------|------------|---------|
| `critical` | Getting this wrong destroys infrastructure, causes data loss, or requires manual recovery | "user_data changes trigger EC2 replacement" (compute) |
| `high` | Getting this wrong causes deployment failures, broken environments, or significant debugging time | "envsubst only substitutes whitelisted variables" (manifests) |
| `medium` | Getting this wrong causes confusion, unexpected behavior, or minor operational issues | "Network removal failure is expected during stack teardown" (littleguy) |
| `low` | Worth knowing but unlikely to cause real problems | Style preferences, minor operational notes |

From the compute contract, here is a well-calibrated `critical` gotcha:

```yaml
- severity: critical
  summary: "user_data_causes_replacement=True — any user-data change destroys the EC2 instance"
  detail: >
    The CDK stack sets user_data_causes_replacement=True on the EC2
    instance. Any modification to the user-data script (adding a
    bootstrap phase, changing a curl URL, editing comments) triggers
    full EC2 replacement: instance termination, new instance creation,
    new IP, Swarm re-initialization, all services offline during
    replacement. This is intentional for consistency but dangerous if
    not understood.
```

And here is a well-calibrated `high` gotcha from the manifests contract:

```yaml
- severity: high
  summary: "envsubst only substitutes whitelisted variables"
  detail: >
    render.sh explicitly whitelists which ${VAR} placeholders are substituted
    (DOMAIN, REGISTRY, ENV, CLUSTER, COPPERMIND_PATH, AWS_REGION, and AMP_*
    variables). Adding a new placeholder to compose fragments requires adding
    it to the envsubst whitelist in render.sh AND to site.yaml parsing.
    Unwhitelisted variables silently remain as literal ${VAR} in the output.
```

### What Belongs in Gotchas vs. Repo Docs

**Gotchas:** Non-obvious traps that an agent or developer would not discover without reading specific code or having been burned before. Things where the "obvious" action is wrong.

**Repo docs:** How-to instructions, setup steps, API references, architectural explanations. Things that are useful but not dangerous to miss.

Ask yourself: "If someone skipped this, would something break or would they just be less informed?" If it would break, it is a gotcha. If they would just be less informed, it belongs in docs.

### Writing Actionable Gotchas

Every gotcha should follow the pattern: **if X happens, then Y is the consequence, and Z is how to avoid it.**

**Good -- from the VPC contract:**

```yaml
- severity: critical
  summary: "Cannot delete VPC stack while consuming stacks reference its exports"
  detail: >
    CloudFormation prevents stack deletion if any export is still imported
    by another stack. Teardown order must be: application stacks first,
    then compute, then VPC. Use 'aws cloudformation list-imports
    --export-name blueshift-vpc-{env}-VpcId' to check for dependents
    before attempting deletion.
```

This tells you: what can go wrong (deletion blocked), why (CF export imports), and what to do instead (specific teardown order and verification command).

**Bad:**

```yaml
- severity: high
  summary: "Be careful with stack deletion"
  detail: "Deleting stacks in the wrong order can cause problems."
```

This is vague. An agent cannot determine what the correct order is, what "problems" means, or how to verify it is safe to proceed.

### Temporal Gotchas

Some gotchas are true now but will change. Document them anyway, and note that they are temporal:

```yaml
- severity: medium
  summary: "VPC and Elastic IP have RETAIN removal policy"
  detail: >
    Both the VPC and ingress EIP have RemovalPolicy.RETAIN set in CDK.
    A 'cdk destroy' will NOT delete these resources — they must be
    manually cleaned up in the AWS console. This prevents accidental
    destruction but creates orphaned resources if forgotten.
```

When the situation changes, update or remove the gotcha. Stale gotchas erode contract fidelity.

---

## 5. Staleness Tracking

Staleness tracking is how Kairos detects contract drift. Without it, a contract silently becomes a liar after the underlying repo changes.

### How It Works

Two fields work together:

- `staleness_paths` -- file globs identifying which codebase files, if changed, suggest the contract needs review.
- `verified_at_commit` -- the git SHA at which the contract was last verified as accurate.

When Kairos checks staleness, it compares files matching `staleness_paths` against the `verified_at_commit`. If any matching file has changed since that commit, the contract is flagged as **STALE**.

There is also a `last_verified` field (ISO 8601 date) that records when the contract was last verified, for human readability.

### When to Use `staleness_paths`

Use them when the contract covers infrastructure, interfaces, or configuration that lives in specific files. This is almost always.

From the compute contract:

```yaml
staleness_paths:
  - "infrastructure/stacks/**"
  - "infrastructure/app.py"
  - "scripts/ci/deploy.sh"
  - "scripts/ci/validate.sh"
  - ".gitlab-ci.yml"
```

From the manifests contract:

```yaml
staleness_paths:
  - "services/*/compose.yml"
  - "services/_base/**"
  - "services/_variants/**"
  - "sites/*/site.yaml"
  - "scripts/ci/render.sh"
  - "scripts/ci/push-site-order.sh"
  - ".gitlab-ci.yml"
```

### Glob Pattern Guidance

**Broad patterns** (e.g., `"infrastructure/**"`) catch more changes but trigger more false positives. Good for repos where any infrastructure change likely affects the contract.

**Narrow patterns** (e.g., `"infrastructure/stacks/compute_stack.py"`) are more precise but risk missing relevant changes in adjacent files.

The pilot contracts strike a balance: they use `**` globs for directories that are densely relevant (like `infrastructure/stacks/`) and specific filenames for isolated files (like `.gitlab-ci.yml`).

**Skip staleness_paths** only when the contract describes something that rarely changes (e.g., a `docs-only` repo where the contract is essentially the README).

### The Staleness Lifecycle

```
CURRENT  →  code changes in staleness_paths  →  STALE  →  review contract  →  update contract + verified_at_commit  →  CURRENT
```

When updating `verified_at_commit`, set it to the current HEAD commit of the repo:

```yaml
last_verified: "2026-03-24"
verified_at_commit: "dcf85096ff908437862553438b045e38d204ed66"
```

A short SHA is also acceptable:

```yaml
verified_at_commit: "d1ac514"
```

---

## 6. Dependencies Section

The full dependency picture spans several sections: `consumes.cloudformation_imports`, `consumes.docker_images`, `consumes.secrets`, and `consumes.repos`. Together, they tell agents what must exist before this repo can function.

### Hard vs. Soft Dependencies

**Hard dependencies** are things that must exist or the repo fails to deploy. CloudFormation imports are the clearest example -- if the export does not exist, the stack deployment fails:

```yaml
consumes:
  cloudformation_imports:
    - export: "blueshift-vpc-{env}-VpcId"
      from: vpc
      description: "VPC to deploy EC2 instances into"
```

**Soft dependencies** are things that the repo uses but can survive without. A Docker image pulled from a registry is a soft dependency if the service has a fallback or degraded mode:

```yaml
consumes:
  docker_images:
    - name: "openbao/openbao"
      source: "openbao/openbao:2.5.1"
```

The schema does not distinguish between hard and soft dependencies. Use the `description` field to clarify:

```yaml
consumes:
  secrets:
    - path: "/blueshift/{env}/openbao/role_id"
      from: compute
      description: "OpenBao AppRole role ID for openbao-agent bootstrap, seeded by deploy.sh from COPPERMIND_ROLE_ID CI variable"
```

### How Agents Use Dependency Information

When an agent is asked to work on repo A, it queries Kairos for relevant contracts. If repo A's contract shows it consumes exports from repo B, the agent can:

1. Pull repo B's contract to understand the export format.
2. Check if repo B's contract is stale (which might mean the export has changed).
3. Understand the blast radius of changes to repo B.

This is why keeping dependencies honest matters. A missing `consumes` entry means agents will not discover the relationship, and changes to the upstream repo will not trigger appropriate caution.

### Keeping the Dependency Graph Honest

Every time you add a new import, image reference, or secret read to your code, ask: "Is this reflected in my contract's `consumes` section?"

Every time you add a new export, network, or published artifact, ask: "Is this reflected in my contract's `provides` section?"

The compute contract lists five CloudFormation imports from VPC. If someone added a sixth import in the code but not in the contract, an agent would not know about it. The contract's fidelity degrades silently.

---

## 7. Common Mistakes

### Over-Documenting

Contracts are not READMEs. They should describe *what* a repo provides and consumes, not *how* to set up a development environment or *how* to run the test suite (though `operational.validation_command` and `operational.test_command` capture the specific commands).

**Too much:**

```yaml
purpose: >
  This repo provides infrastructure. To get started, clone the repo,
  install Python 3.11, run pip install -r requirements.txt, then
  export STACK_SUFFIX=dev and run cdk synth. You can also run the
  tests with pytest. The CI pipeline runs on merge to release branches.
```

**Just right -- from the compute contract:**

```yaml
purpose: >
  Provisions shared platform compute infrastructure for all Blueshift projects.
  Deploys an EC2 instance running Docker Swarm into the existing VPC
  (provisioned by blueshift-vpc), with security groups, IAM roles for SSM
  access, and EIP association.
```

Setup instructions belong in the repo's README or `operational` section. The `purpose` field is for *what* and *why*, not *how*.

### Under-Specifying Gotchas

Vague warnings help no one. "Be careful with deployments" is noise. Every gotcha needs a trigger, an impact, and a mitigation.

**Vague:**

```yaml
- severity: high
  summary: "Deployment can be tricky"
  detail: "Make sure you deploy things in the right order."
```

**Specific -- from the littleguy contract:**

```yaml
- severity: critical
  summary: "Docker configs are immutable — stack must be removed and redeployed"
  detail: >
    Docker Swarm configs (swarmcd_config, swarmcd_repos, swarmcd_stacks) are
    immutable once created. Any change to config.yaml, repos.yaml, or
    stacks.yaml requires 'docker stack rm littleguy' followed by a fresh
    deploy. The redeploy-littleguy.sh script handles this, but a naive
    'docker stack deploy' will fail silently with stale config.
```

### Stale `verified_at_commit`

A `verified_at_commit` that points to a commit from before a major refactor means the contract has not been reviewed against the current codebase. This defeats the purpose of staleness tracking.

When you make significant changes to a repo, update the contract:

```yaml
last_verified: "2026-03-24"
verified_at_commit: "dcf85096ff908437862553438b045e38d204ed66"
```

If you cannot verify the contract right now, leave `verified_at_commit` as-is. A stale flag is better than a false "current" flag.

### Missing `consumes` Entries

If your code imports a CloudFormation export, pulls a Docker image, or reads a secret, and that dependency is not in `consumes`, the dependency graph has a hole. Agents will not discover the relationship, and upstream changes will not trigger appropriate caution in your repo.

The compute contract lists all five CloudFormation imports from VPC, all consumed Docker images, all consumed secrets, and all repo-level relationships. This completeness is what makes the dependency graph trustworthy.

### Forgetting Empty Arrays

When a category does not apply, use an empty array rather than omitting the field:

```yaml
provides:
  cloudformation_exports: []
  docker_images: []
```

Omitting a field is ambiguous -- it could mean "none" or "I forgot to fill this in." An empty array explicitly says "I checked, and there are none." This distinction matters for contract fidelity.

---

## Getting Started

1. Copy the [contract template](../contracts/templates/contract-template.yaml) to `contracts/repos/<your-repo-name>.yaml`.
2. Fill in the `identity` section first -- especially the `purpose` field.
3. Audit your repo's code for provides (exports, images, networks) and consumes (imports, image pulls, secret reads).
4. Write gotchas for anything that has burned you or would surprise a newcomer.
5. Set `staleness_paths` to the files most likely to invalidate the contract.
6. Set `verified_at_commit` to the current HEAD of the repo.
7. Validate your contract against the [schema](../contracts/schema.yaml).

For the full field reference, see the [contract schema](../contracts/schema.yaml).

## See Also

- [Quickstart Guide](quickstart.md) -- install Kairos, write your first contract, and start querying
- [Configuration Reference](configuration.md) -- all CLI flags, MCP tools, and directory layout
- [Architecture Reference](architecture.md) -- technical internals, chunking strategy, and design decisions
