"""Staleness checker for Kairos contracts.

Compares contract metadata (verified_at_commit, staleness_paths)
against git history to detect whether a contract may be out of date.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from kairos.models import Contract, StalenessReport


def check_staleness(contract: Contract, repo_path: Path) -> StalenessReport:
    """Check whether a contract is stale relative to git history.

    Compares the contract's ``verified_at_commit`` against HEAD in the
    repository at *repo_path*.  If any files matching ``staleness_paths``
    have changed between those two commits, the contract is considered
    STALE.

    Args:
        contract: A parsed Kairos contract.
        repo_path: Path to the git repository the contract describes.

    Returns:
        A StalenessReport with status CURRENT, STALE, or UNKNOWN.
    """
    repo_name = contract.identity.name

    # --- guard: repo must exist and be a git repo ---
    if not repo_path.is_dir():
        return StalenessReport(
            repo_name=repo_name,
            status="UNKNOWN",
            message="Repo not found",
        )

    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--git-dir"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return StalenessReport(
            repo_name=repo_name,
            status="UNKNOWN",
            message="Repo not found",
        )

    # --- guard: contract must have a verified_at_commit ---
    verified_commit = contract.verified_at_commit
    if not verified_commit:
        return StalenessReport(
            repo_name=repo_name,
            status="UNKNOWN",
            message="No verified_at_commit in contract",
        )

    # --- get HEAD ---
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        head_sha = result.stdout.strip()
    except subprocess.CalledProcessError:
        return StalenessReport(
            repo_name=repo_name,
            status="UNKNOWN",
            message="Could not determine HEAD",
        )

    # --- fast path: HEAD matches verified commit ---
    if head_sha.startswith(verified_commit) or verified_commit.startswith(head_sha):
        return StalenessReport(
            repo_name=repo_name,
            status="CURRENT",
            message="HEAD matches verified_at_commit",
        )

    # --- verify the verified_at_commit exists in the repo ---
    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "cat-file", "-t", verified_commit],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return StalenessReport(
            repo_name=repo_name,
            status="UNKNOWN",
            message=f"verified_at_commit {verified_commit} not found in repo",
        )

    # --- count commits since verified_at_commit ---
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "rev-list",
                "--count",
                f"{verified_commit}..HEAD",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        commits_since = int(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        commits_since = 0

    # --- check staleness paths ---
    staleness_paths = contract.staleness_paths
    if not staleness_paths:
        # No staleness paths defined — consider CURRENT if no paths to watch.
        return StalenessReport(
            repo_name=repo_name,
            status="CURRENT",
            message="No staleness_paths defined",
        )

    changed_files: list[str] = []
    for glob_pattern in staleness_paths:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_path),
                    "diff",
                    "--name-only",
                    f"{verified_commit}..HEAD",
                    "--",
                    glob_pattern,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            files = [f for f in result.stdout.strip().splitlines() if f]
            changed_files.extend(files)
        except subprocess.CalledProcessError:
            # If the diff command fails for a given pattern, skip it.
            pass

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique_files: list[str] = []
    for f in changed_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    if unique_files:
        return StalenessReport(
            repo_name=repo_name,
            status="STALE",
            message=f"{len(unique_files)} file(s) changed in staleness paths",
            changed_files=unique_files,
            commits_since=commits_since,
        )

    return StalenessReport(
        repo_name=repo_name,
        status="CURRENT",
        message="No changes in staleness paths since verified_at_commit",
        commits_since=commits_since,
    )


def check_all_staleness(
    contracts_dir: Path,
    workspace_path: Path,
) -> dict[str, StalenessReport]:
    """Check staleness for all contracts in a directory.

    Iterates over every ``*.yaml`` file in *contracts_dir*, parses each
    as a :class:`Contract`, and runs :func:`check_staleness` against the
    corresponding repository under *workspace_path*.

    The repository path is derived from the contract's
    ``identity.full_name`` (i.e. ``workspace_path / full_name``).

    Args:
        contracts_dir: Directory containing contract YAML files.
        workspace_path: Root directory containing the git repositories.

    Returns:
        A dict mapping ``identity.name`` to its :class:`StalenessReport`.
    """
    reports: dict[str, StalenessReport] = {}

    if not contracts_dir.is_dir():
        return reports

    for yaml_path in sorted(contracts_dir.glob("*.yaml")):
        try:
            contract = Contract.from_yaml(yaml_path)
        except Exception:
            # Skip files that cannot be parsed as contracts.
            continue

        repo_path = workspace_path / contract.identity.full_name
        report = check_staleness(contract, repo_path)
        reports[contract.identity.name] = report

    return reports
