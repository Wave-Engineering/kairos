"""MCP server for Kairos — exposes contract tools for AI agents."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from kairos.embed import search
from kairos.models import Contract, StalenessReport
from kairos.staleness import check_all_staleness as _check_all_staleness
from kairos.staleness import check_staleness as _check_staleness


def _load_contracts(contracts_dir: Path) -> dict[str, Contract]:
    """Load all contract YAML files into a dict keyed by identity.name.

    Args:
        contracts_dir: Directory containing contract YAML files.

    Returns:
        A dict mapping repo name to Contract instance.
    """
    contracts: dict[str, Contract] = {}
    if not contracts_dir.is_dir():
        return contracts

    for yaml_path in sorted(contracts_dir.glob("*.yaml")):
        try:
            contract = Contract.from_yaml(yaml_path)
            contracts[contract.identity.name] = contract
        except Exception:
            # Skip files that cannot be parsed as contracts.
            continue

    return contracts


def _open_vec_connection(db_path: Path) -> sqlite3.Connection:
    """Open a sqlite connection with the sqlite-vec extension loaded.

    Args:
        db_path: Path to the sqlite-vec database file.

    Returns:
        An open sqlite3.Connection with sqlite-vec loaded.
    """
    import sqlite_vec

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _format_staleness_report(report: StalenessReport) -> str:
    """Format a StalenessReport as human-readable text.

    Args:
        report: A StalenessReport to format.

    Returns:
        A formatted string with status, message, changed files, and commits since.
    """
    lines: list[str] = [
        f"## {report.repo_name}",
        f"**Status:** {report.status}",
        f"**Message:** {report.message}",
    ]

    if report.changed_files:
        lines.append(f"**Changed files:** {', '.join(report.changed_files)}")

    if report.commits_since > 0:
        lines.append(f"**Commits since verification:** {report.commits_since}")

    return "\n".join(lines)


def create_server(
    contracts_dir: Path,
    db_path: Path,
    workspace_path: Path | None = None,
) -> FastMCP:
    """Create and configure a Kairos MCP server.

    Loads all contract YAML files into memory, opens the sqlite-vec database,
    and loads the sentence-transformers model. Registers four tools:
    check_staleness, find_relevant_contracts, get_contract, and list_contracts.

    Args:
        contracts_dir: Directory containing contract YAML files.
        db_path: Path to the sqlite-vec database file.
        workspace_path: Root directory containing the git repositories.
            Required for the check_staleness tool.

    Returns:
        A configured FastMCP server instance ready to run.
    """
    # State holders — populated in lifespan.  Stored on the mcp instance
    # as ``_kairos_state`` so test code can pre-populate it without running
    # the lifespan.
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(server: FastMCP):
        from sentence_transformers import SentenceTransformer

        state["contracts"] = _load_contracts(contracts_dir)
        state["model"] = SentenceTransformer("all-MiniLM-L6-v2")
        state["conn"] = _open_vec_connection(db_path)
        state["workspace_path"] = workspace_path

        yield state

        state["conn"].close()

    mcp = FastMCP(
        "kairos",
        lifespan=lifespan,
        instructions=(
            "When answering questions about repositories, infrastructure, "
            "or cross-repo dependencies, consult the kairos MCP tools "
            "(find_relevant_contracts, get_contract, list_contracts) "
            "before searching local files."
        ),
    )
    mcp._kairos_state = state  # type: ignore[attr-defined]

    @mcp.tool()
    def check_staleness(repo_name: str | None = None) -> str:
        """Check whether contracts are stale relative to git history.

        When called with a specific repo_name, checks just that contract.
        When called without arguments, checks all loaded contracts.

        Args:
            repo_name: Repository name to check (e.g., "vpc"). If None,
                checks all loaded contracts.
        """
        workspace = state.get("workspace_path")
        if workspace is None:
            return "Error: workspace_path not configured. Pass --workspace to the serve command."

        contracts = state["contracts"]

        if repo_name is not None:
            # Single repo check.
            contract = contracts.get(repo_name)
            if contract is None:
                available = sorted(contracts.keys())
                return (
                    f"Error: no contract found for '{repo_name}'. "
                    f"Available repos: {', '.join(available)}"
                )

            repo_path = workspace / contract.identity.full_name
            report = _check_staleness(contract, repo_path)
            return _format_staleness_report(report)

        # All repos check.
        reports = _check_all_staleness(contracts_dir, workspace)
        if not reports:
            return "No contracts found."

        sections: list[str] = []
        for name in sorted(reports.keys()):
            sections.append(_format_staleness_report(reports[name]))
        return "\n\n---\n\n".join(sections)

    @mcp.tool()
    def find_relevant_contracts(query: str, top_k: int = 3) -> str:
        """Find contracts semantically relevant to a natural-language query.

        Searches the embedding database for chunks matching the query, then
        deduplicates by repository (keeping the best-matching chunk per repo)
        and returns the full contract YAML for the top_k most relevant repos.

        Args:
            query: Natural-language search query (e.g., "Docker overlay network CIDR").
            top_k: Maximum number of contracts to return (default: 3).
        """
        contracts = state["contracts"]
        model = state["model"]
        conn = state["conn"]

        # Search with a higher internal limit to allow deduplication.
        raw_results = search(query, model, db_path, top_k=top_k * 5, conn=conn)

        # Deduplicate by repo_name — keep only the best (lowest distance) chunk per repo.
        best_per_repo: dict[str, tuple[Any, float]] = {}
        for chunk, distance in raw_results:
            if chunk.repo_name not in best_per_repo:
                best_per_repo[chunk.repo_name] = (chunk, distance)
            elif distance < best_per_repo[chunk.repo_name][1]:
                best_per_repo[chunk.repo_name] = (chunk, distance)

        # Sort by distance ascending (most similar first) and take top_k.
        sorted_results = sorted(best_per_repo.values(), key=lambda x: x[1])
        top_results = sorted_results[:top_k]

        if not top_results:
            return "No matching contracts found."

        # Build response with full contract YAML and matching context.
        sections: list[str] = []
        for chunk, distance in top_results:
            repo_name = chunk.repo_name
            contract = contracts.get(repo_name)

            section_lines = [
                f"## {repo_name} (score: {distance:.4f})",
                "",
                f"**Matched chunk:** {chunk.text}",
                "",
            ]

            if contract:
                section_lines.append("**Full contract:**")
                section_lines.append("```yaml")
                section_lines.append(yaml.dump(contract.raw, default_flow_style=False).rstrip())
                section_lines.append("```")
            else:
                section_lines.append(
                    f"*Contract data for '{repo_name}' not loaded "
                    f"(available: {', '.join(sorted(contracts.keys()))})*"
                )

            sections.append("\n".join(section_lines))

        return "\n\n---\n\n".join(sections)

    @mcp.tool()
    def get_contract(repo_name: str) -> str:
        """Get the full contract YAML for a specific repository.

        Args:
            repo_name: The repository name (e.g., "compute", "vpc").
        """
        contracts = state["contracts"]
        contract = contracts.get(repo_name)

        if contract is None:
            available = sorted(contracts.keys())
            return (
                f"Error: no contract found for '{repo_name}'. "
                f"Available repos: {', '.join(available)}"
            )

        return yaml.dump(contract.raw, default_flow_style=False)

    @mcp.tool()
    def list_contracts() -> str:
        """List all loaded contracts with their identity summaries.

        Returns a YAML list of identity objects for all loaded contracts.
        """
        contracts = state["contracts"]

        identities: list[dict[str, str]] = []
        for name in sorted(contracts.keys()):
            contract = contracts[name]
            ident = contract.identity
            identities.append(
                {
                    "name": ident.name,
                    "full_name": ident.full_name,
                    "category": ident.category,
                    "purpose": ident.purpose,
                    "archetype": ident.archetype,
                }
            )

        return yaml.dump(identities, default_flow_style=False)

    return mcp


def main(
    contracts_dir: str,
    db: str,
    workspace: str | None = None,
) -> None:
    """Entry point for running the Kairos MCP server.

    Args:
        contracts_dir: Path to the directory containing contract YAML files.
        db: Path to the sqlite-vec database file.
        workspace: Path to the root workspace containing git repositories.
    """
    workspace_path = Path(workspace).resolve() if workspace else None
    server = create_server(
        contracts_dir=Path(contracts_dir).resolve(),
        db_path=Path(db).resolve(),
        workspace_path=workspace_path,
    )
    server.run(transport="stdio")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python -m kairos.server <contracts_dir> <db_path> [workspace_path]",
            file=sys.stderr,
        )
        sys.exit(1)
    workspace_arg = sys.argv[3] if len(sys.argv) > 3 else None
    main(sys.argv[1], sys.argv[2], workspace=workspace_arg)
