"""Static digest aggregation for Kairos contracts.

Reads all contract YAML files from a directory and produces a markdown
ecosystem digest with repository summaries, dependency cross-references,
and aggregated gotchas.
"""

from __future__ import annotations

from pathlib import Path

from kairos.models import Contract

# Category sort order — infrastructure first, then deployment, core, apps.
_CATEGORY_ORDER = {
    "infrastructure": 0,
    "deployment": 1,
    "core": 2,
    "apps": 3,
}


def _category_sort_key(contract: Contract) -> tuple[int, str]:
    """Return a sort key that orders contracts by category then name."""
    order = _CATEGORY_ORDER.get(contract.identity.category, 99)
    return (order, contract.identity.name)


_SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


def _severity_sort_key(gotcha: dict) -> tuple[int, str]:
    """Return a sort key that orders gotchas by severity (critical first)."""
    order = _SEVERITY_ORDER.get(gotcha.get("severity", "low"), 99)
    return (order, gotcha.get("summary", ""))


def _load_contracts(contracts_dir: Path) -> list[Contract]:
    """Load and parse all contract YAML files from a directory.

    Args:
        contracts_dir: Directory containing contract YAML files.

    Returns:
        A list of parsed Contract instances.
    """
    contracts: list[Contract] = []
    if not contracts_dir.is_dir():
        return contracts

    for yaml_path in sorted(contracts_dir.glob("*.yaml")):
        try:
            contract = Contract.from_yaml(yaml_path)
            contracts.append(contract)
        except Exception:
            # Skip files that cannot be parsed as contracts.
            continue

    return contracts


def _build_dependency_table(contracts: list[Contract]) -> list[dict]:
    """Build a cross-reference table mapping provides to consumers.

    For each 'provides' entry across all contracts, find which contracts
    'consume' it. Uses the 'from' field in consumes entries to create
    the mapping.

    Args:
        contracts: List of parsed Contract instances.

    Returns:
        A list of dicts with keys: provider, export_name, consumer, description.
    """
    dependencies: list[dict] = []

    for consumer in contracts:
        consumer_name = consumer.identity.name
        consumes = consumer.consumes

        # CloudFormation imports reference a provider via the 'from' field.
        for imp in consumes.get("cloudformation_imports", []):
            dependencies.append(
                {
                    "provider": imp.get("from", "unknown"),
                    "export_name": imp.get("export", ""),
                    "consumer": consumer_name,
                    "description": imp.get("description", ""),
                }
            )

        # Secrets with a 'from' field reference a provider.
        for secret in consumes.get("secrets", []):
            if "from" in secret:
                dependencies.append(
                    {
                        "provider": secret["from"],
                        "export_name": secret.get("path", ""),
                        "consumer": consumer_name,
                        "description": secret.get("description", ""),
                    }
                )

        # Docker images with a 'from' field (if present).
        for image in consumes.get("docker_images", []):
            if "from" in image:
                dependencies.append(
                    {
                        "provider": image["from"],
                        "export_name": image.get("name", ""),
                        "consumer": consumer_name,
                        "description": image.get("source", ""),
                    }
                )

    return dependencies


def _render_platform_overview(contracts: list[Contract]) -> str:
    """Render the Platform Overview section.

    Args:
        contracts: Sorted list of parsed Contract instances.

    Returns:
        Markdown string for the platform overview section.
    """
    categories = sorted({c.identity.category for c in contracts})
    lines = [
        "## Platform Overview",
        "",
        f"**{len(contracts)} contracts** across {len(categories)} "
        f"{'category' if len(categories) == 1 else 'categories'}: "
        f"{', '.join(categories)}.",
        "",
    ]
    return "\n".join(lines)


def _render_repository_summaries(contracts: list[Contract]) -> str:
    """Render the Repository Summaries section.

    Args:
        contracts: Sorted list of parsed Contract instances.

    Returns:
        Markdown string for the repository summaries section.
    """
    lines = ["## Repository Summaries", ""]

    for contract in contracts:
        ident = contract.identity
        lines.append(f"### {ident.full_name}")
        lines.append("")
        lines.append(f"- **Name:** {ident.name}")
        lines.append(f"- **Category:** {ident.category}")
        lines.append(f"- **Archetype:** {ident.archetype}")
        lines.append(f"- **Purpose:** {ident.purpose.strip()}")
        lines.append("")

    return "\n".join(lines)


def _render_dependency_table(dependencies: list[dict]) -> str:
    """Render the Dependency Table section.

    Args:
        dependencies: List of dependency dicts from _build_dependency_table.

    Returns:
        Markdown string for the dependency table section.
    """
    lines = ["## Dependency Table", ""]

    if not dependencies:
        lines.append("No cross-repo dependencies found.")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Provider | Export | Consumer | Description |")
    lines.append("|----------|--------|----------|-------------|")

    for dep in dependencies:
        provider = dep["provider"]
        export_name = dep["export_name"]
        consumer = dep["consumer"]
        description = dep["description"].strip().replace("\n", " ")
        lines.append(f"| {provider} | {export_name} | {consumer} | {description} |")

    lines.append("")
    return "\n".join(lines)


def _render_gotchas(contracts: list[Contract]) -> str:
    """Render the Aggregated Gotchas section.

    Collects all gotchas across all contracts, sorts by severity
    (critical -> high -> medium -> low), and renders with repo attribution.

    Args:
        contracts: List of parsed Contract instances.

    Returns:
        Markdown string for the aggregated gotchas section.
    """
    all_gotchas: list[dict] = []
    for contract in contracts:
        for gotcha in contract.gotchas:
            all_gotchas.append(
                {
                    "repo": contract.identity.name,
                    "severity": gotcha.get("severity", "low"),
                    "summary": gotcha.get("summary", ""),
                    "detail": gotcha.get("detail", ""),
                }
            )

    all_gotchas.sort(key=_severity_sort_key)

    lines = ["## Aggregated Gotchas", ""]

    if not all_gotchas:
        lines.append("No gotchas found.")
        lines.append("")
        return "\n".join(lines)

    for gotcha in all_gotchas:
        severity = gotcha["severity"].upper()
        repo = gotcha["repo"]
        summary = gotcha["summary"]
        detail = gotcha["detail"].strip().replace("\n", " ")
        lines.append(f"- **[{severity}]** ({repo}) {summary}")
        lines.append(f"  - {detail}")
        lines.append("")

    return "\n".join(lines)


def aggregate_contracts(contracts_dir: Path) -> str:
    """Aggregate all contracts in a directory into a markdown ecosystem digest.

    Loads all ``*.yaml`` files from the contracts directory, parses each
    with ``Contract.from_yaml()``, sorts by category, and generates a
    markdown document with:

    - Platform Overview (contract count and categories)
    - Repository Summaries (identity details for each contract)
    - Dependency Table (cross-reference of provides/consumes)
    - Aggregated Gotchas (sorted by severity with repo attribution)

    Args:
        contracts_dir: Path to the directory containing contract YAML files.

    Returns:
        A string containing the full markdown digest.
    """
    contracts = _load_contracts(contracts_dir)
    contracts.sort(key=_category_sort_key)

    dependencies = _build_dependency_table(contracts)

    sections = [
        "# Kairos Ecosystem Digest",
        "",
        _render_platform_overview(contracts),
        _render_repository_summaries(contracts),
        _render_dependency_table(dependencies),
        _render_gotchas(contracts),
    ]

    return "\n".join(sections)
