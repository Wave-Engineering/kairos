"""Command-line interface for Kairos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kairos.aggregate import aggregate_contracts
from kairos.embed import embed_contracts
from kairos.install import install_mcp_config
from kairos.staleness import check_all_staleness


# ANSI colour helpers (disabled when stdout is not a terminal).
def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _supports_color()

_GREEN = "\033[32m" if _COLOR else ""
_YELLOW = "\033[33m" if _COLOR else ""
_RED = "\033[31m" if _COLOR else ""
_RESET = "\033[0m" if _COLOR else ""

_STATUS_COLORS = {
    "CURRENT": _GREEN,
    "STALE": _YELLOW,
    "UNKNOWN": _RED,
}


def _colorize(status: str) -> str:
    color = _STATUS_COLORS.get(status, "")
    return f"{color}{status}{_RESET}"


def _cmd_check_staleness(args: argparse.Namespace) -> int:
    """Run the check-staleness sub-command."""
    contracts_dir = Path(args.contracts_dir).resolve()
    workspace = Path(args.workspace).resolve()

    if not contracts_dir.is_dir():
        print(f"Error: contracts directory not found: {contracts_dir}", file=sys.stderr)
        return 1

    reports = check_all_staleness(contracts_dir, workspace)

    if not reports:
        print("No contracts found.")
        return 0

    # Determine column widths for a pretty table.
    name_width = max(len(name) for name in reports)
    status_width = max(len(r.status) for r in reports.values())

    # Header
    print(f"{'REPO':<{name_width}}  {'STATUS':<{status_width}}  SUMMARY")
    print(f"{'-' * name_width}  {'-' * status_width}  {'-' * 40}")

    exit_code = 0
    for name, report in reports.items():
        colored_status = _colorize(report.status)
        # Pad raw status for alignment (color codes are zero-width).
        padding = " " * (status_width - len(report.status))
        summary = report.message
        if report.changed_files:
            summary += f" ({', '.join(report.changed_files)})"
        print(f"{name:<{name_width}}  {colored_status}{padding}  {summary}")

        if report.status == "STALE":
            exit_code = 1

    return exit_code


def _cmd_aggregate(args: argparse.Namespace) -> int:
    """Run the aggregate sub-command."""
    contracts_dir = Path(args.contracts_dir).resolve()
    output_path = Path(args.output).resolve()

    if not contracts_dir.is_dir():
        print(f"Error: contracts directory not found: {contracts_dir}", file=sys.stderr)
        return 1

    markdown = aggregate_contracts(contracts_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)
    print(f"Digest written to {output_path}")
    return 0


def _cmd_embed(args: argparse.Namespace) -> int:
    """Run the embed sub-command."""
    contracts_dir = Path(args.contracts_dir).resolve()
    db_path = Path(args.db).resolve()

    if not contracts_dir.is_dir():
        print(f"Error: contracts directory not found: {contracts_dir}", file=sys.stderr)
        return 1

    total_chunks, total_contracts = embed_contracts(contracts_dir, db_path)
    print(f"Embedded {total_chunks} chunks across {total_contracts} contracts into {db_path}")

    # Breadcrumb: suggest next steps with resolved absolute paths.
    print()
    print("Next steps:")
    print()
    print("  Start the MCP server:")
    print(f"    kairos serve --contracts-dir {contracts_dir} --db {db_path}")
    print()
    print("  Or install into Claude Code settings:")
    print(f"    kairos install --contracts-dir {contracts_dir} --db {db_path}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    """Run the install sub-command."""
    contracts_dir = Path(args.contracts_dir).resolve()
    db_path = Path(args.db).resolve()

    if not contracts_dir.is_dir():
        print(f"Error: contracts directory not found: {contracts_dir}", file=sys.stderr)
        return 1

    try:
        settings_file = install_mcp_config(contracts_dir, db_path, scope=args.scope)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Kairos MCP server configured in {settings_file}")
    print()
    print("  Contracts: " + str(contracts_dir))
    print("  Database:  " + str(db_path))
    print()
    print("Restart Claude Code to activate the new MCP server.")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Run the MCP server sub-command."""
    from kairos.server import main as serve_main

    contracts_dir = Path(args.contracts_dir).resolve()
    db_path = Path(args.db).resolve()

    if not contracts_dir.is_dir():
        print(f"Error: contracts directory not found: {contracts_dir}", file=sys.stderr)
        return 1

    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        return 1

    workspace = getattr(args, "workspace", None)
    serve_main(str(contracts_dir), str(db_path), workspace=workspace)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``kairos`` CLI."""
    parser = argparse.ArgumentParser(
        prog="kairos",
        description="Kairos — structured context system for AI agents",
    )
    subparsers = parser.add_subparsers(dest="command")

    # -- check-staleness --
    sp_stale = subparsers.add_parser(
        "check-staleness",
        help="Check contract staleness against git history",
    )
    sp_stale.add_argument(
        "--contracts-dir",
        required=True,
        help="Path to the directory containing contract YAML files",
    )
    sp_stale.add_argument(
        "--workspace",
        required=True,
        help="Path to the root workspace containing git repositories",
    )
    sp_stale.set_defaults(func=_cmd_check_staleness)

    # -- aggregate --
    sp_agg = subparsers.add_parser(
        "aggregate",
        help="Generate a static markdown digest from contract files",
    )
    sp_agg.add_argument(
        "--contracts-dir",
        required=True,
        help="Path to the directory containing contract YAML files",
    )
    sp_agg.add_argument(
        "--output",
        required=True,
        help="Path to write the output markdown file",
    )
    sp_agg.set_defaults(func=_cmd_aggregate)

    # -- embed --
    sp_embed = subparsers.add_parser(
        "embed",
        help="Embed contract chunks into a sqlite-vec database",
    )
    sp_embed.add_argument(
        "--contracts-dir",
        required=True,
        help="Path to the directory containing contract YAML files",
    )
    sp_embed.add_argument(
        "--db",
        required=True,
        help="Path to the sqlite-vec database file",
    )
    sp_embed.set_defaults(func=_cmd_embed)

    # -- serve --
    sp_serve = subparsers.add_parser(
        "serve",
        help="Run the Kairos MCP server (stdio transport)",
    )
    sp_serve.add_argument(
        "--contracts-dir",
        required=True,
        help="Path to the directory containing contract YAML files",
    )
    sp_serve.add_argument(
        "--db",
        required=True,
        help="Path to the sqlite-vec database file",
    )
    sp_serve.add_argument(
        "--workspace",
        default=None,
        help="Path to the root workspace containing git repositories (enables staleness checks)",
    )
    sp_serve.set_defaults(func=_cmd_serve)

    # -- install --
    sp_install = subparsers.add_parser(
        "install",
        help="Add Kairos MCP server to Claude Code settings",
    )
    sp_install.add_argument(
        "--contracts-dir",
        required=True,
        help="Path to the directory containing contract YAML files",
    )
    sp_install.add_argument(
        "--db",
        required=True,
        help="Path to the sqlite-vec database file",
    )
    sp_install.add_argument(
        "--scope",
        choices=["project", "user"],
        default="project",
        help="Where to write settings: 'project' (.claude/settings.local.json) "
        "or 'user' (~/.claude/settings.json). Default: project",
    )
    sp_install.set_defaults(func=_cmd_install)

    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
