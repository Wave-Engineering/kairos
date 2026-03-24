"""Command-line interface for Kairos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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

    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
