"""Tests for kairos.staleness — contract staleness detection against git history.

All tests use the ``tmp_path`` fixture to create REAL temporary git
repositories.  No git operations are mocked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from kairos.models import Contract
from kairos.staleness import check_all_staleness, check_staleness


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    """Run a git command inside *repo* and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> str:
    """Initialise a git repo at *path* with an initial commit.

    Returns the SHA of the initial commit.
    """
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    _git(path, "config", "user.email", "test@test.com")
    _git(path, "config", "user.name", "Test")

    # Create a file so the initial commit is not empty.
    (path / "README.md").write_text("# hello\n")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial commit")
    return _git(path, "rev-parse", "HEAD")


def _make_contract_yaml(
    contracts_dir: Path,
    *,
    name: str,
    full_name: str,
    verified_at_commit: str,
    staleness_paths: list[str] | None = None,
) -> Path:
    """Write a minimal contract YAML file into *contracts_dir* and return its path."""
    data: dict = {
        "contract_version": "0.1.0",
        "identity": {
            "name": name,
            "full_name": full_name,
            "category": "infrastructure",
            "purpose": "Test contract",
            "archetype": "cdk-infra",
        },
        "verified_at_commit": verified_at_commit,
    }
    if staleness_paths is not None:
        data["staleness_paths"] = staleness_paths

    contracts_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = contracts_dir / f"{name}.yaml"
    yaml_path.write_text(yaml.dump(data, default_flow_style=False))
    return yaml_path


def _load_contract(yaml_path: Path) -> Contract:
    """Load a contract from a YAML file."""
    return Contract.from_yaml(yaml_path)


# ---------------------------------------------------------------------------
# Tests for check_staleness()
# ---------------------------------------------------------------------------


class TestCheckStalenessCurrent:
    """Contracts should report CURRENT when nothing has changed."""

    def test_no_changes_since_verified_commit(self, tmp_path: Path):
        """A contract whose verified_at_commit equals HEAD is CURRENT."""
        repo = tmp_path / "my-repo"
        sha = _init_repo(repo)

        contracts_dir = tmp_path / "contracts"
        yaml_path = _make_contract_yaml(
            contracts_dir,
            name="myrepo",
            full_name="my-repo",
            verified_at_commit=sha,
            staleness_paths=["*.py"],
        )
        contract = _load_contract(yaml_path)

        report = check_staleness(contract, repo)
        assert report.status == "CURRENT"
        assert report.repo_name == "myrepo"
        assert report.changed_files == []

    def test_changes_outside_staleness_paths(self, tmp_path: Path):
        """Changes in files NOT matching staleness_paths still report CURRENT."""
        repo = tmp_path / "my-repo"
        sha = _init_repo(repo)

        # Add a commit that modifies a file outside staleness_paths.
        (repo / "docs").mkdir()
        (repo / "docs" / "notes.txt").write_text("some docs\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "add docs")

        contracts_dir = tmp_path / "contracts"
        yaml_path = _make_contract_yaml(
            contracts_dir,
            name="myrepo",
            full_name="my-repo",
            verified_at_commit=sha,
            staleness_paths=["src/**"],
        )
        contract = _load_contract(yaml_path)

        report = check_staleness(contract, repo)
        assert report.status == "CURRENT"
        assert report.changed_files == []
        assert report.commits_since > 0


class TestCheckStalenessStale:
    """Contracts should report STALE when staleness_paths have been touched."""

    def test_changes_in_staleness_paths(self, tmp_path: Path):
        """A contract where staleness_paths files changed reports STALE."""
        repo = tmp_path / "my-repo"
        sha = _init_repo(repo)

        # Add a commit that modifies a file matching staleness_paths.
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("print('hello')\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "add app.py")

        contracts_dir = tmp_path / "contracts"
        yaml_path = _make_contract_yaml(
            contracts_dir,
            name="myrepo",
            full_name="my-repo",
            verified_at_commit=sha,
            staleness_paths=["src/**"],
        )
        contract = _load_contract(yaml_path)

        report = check_staleness(contract, repo)
        assert report.status == "STALE"
        assert "src/app.py" in report.changed_files
        assert report.commits_since >= 1

    def test_multiple_staleness_paths(self, tmp_path: Path):
        """Changes matching any of several staleness_paths globs trigger STALE."""
        repo = tmp_path / "my-repo"
        sha = _init_repo(repo)

        (repo / "infra").mkdir()
        (repo / "infra" / "stack.ts").write_text("// stack\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "add stack")

        contracts_dir = tmp_path / "contracts"
        yaml_path = _make_contract_yaml(
            contracts_dir,
            name="myrepo",
            full_name="my-repo",
            verified_at_commit=sha,
            staleness_paths=["src/**", "infra/**"],
        )
        contract = _load_contract(yaml_path)

        report = check_staleness(contract, repo)
        assert report.status == "STALE"
        assert "infra/stack.ts" in report.changed_files


class TestCheckStalenessUnknown:
    """Contracts should report UNKNOWN when the repo cannot be inspected."""

    def test_nonexistent_repo_path(self, tmp_path: Path):
        """A contract pointing at a non-existent path reports UNKNOWN."""
        contracts_dir = tmp_path / "contracts"
        yaml_path = _make_contract_yaml(
            contracts_dir,
            name="ghost",
            full_name="ghost-repo",
            verified_at_commit="deadbeef",
            staleness_paths=["*.py"],
        )
        contract = _load_contract(yaml_path)

        report = check_staleness(contract, tmp_path / "no-such-repo")
        assert report.status == "UNKNOWN"
        assert "not found" in report.message.lower()

    def test_path_is_not_a_git_repo(self, tmp_path: Path):
        """A directory that is not a git repo reports UNKNOWN."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()

        contracts_dir = tmp_path / "contracts"
        yaml_path = _make_contract_yaml(
            contracts_dir,
            name="plain",
            full_name="plain",
            verified_at_commit="deadbeef",
            staleness_paths=["*.py"],
        )
        contract = _load_contract(yaml_path)

        report = check_staleness(contract, plain_dir)
        assert report.status == "UNKNOWN"
        assert "not found" in report.message.lower()

    def test_missing_verified_at_commit(self, tmp_path: Path):
        """A contract with no verified_at_commit reports UNKNOWN."""
        repo = tmp_path / "my-repo"
        _init_repo(repo)

        # Write contract without verified_at_commit.
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "contract_version": "0.1.0",
            "identity": {
                "name": "myrepo",
                "full_name": "my-repo",
                "category": "infrastructure",
                "purpose": "Test",
                "archetype": "cdk-infra",
            },
        }
        yaml_path = contracts_dir / "myrepo.yaml"
        yaml_path.write_text(yaml.dump(data, default_flow_style=False))
        contract = _load_contract(yaml_path)

        report = check_staleness(contract, repo)
        assert report.status == "UNKNOWN"
        assert "verified_at_commit" in report.message.lower()

    def test_verified_commit_not_in_repo(self, tmp_path: Path):
        """A contract whose verified_at_commit does not exist in the repo reports UNKNOWN."""
        repo = tmp_path / "my-repo"
        _init_repo(repo)

        contracts_dir = tmp_path / "contracts"
        yaml_path = _make_contract_yaml(
            contracts_dir,
            name="myrepo",
            full_name="my-repo",
            verified_at_commit="0000000000000000000000000000000000000000",
            staleness_paths=["*.py"],
        )
        contract = _load_contract(yaml_path)

        report = check_staleness(contract, repo)
        assert report.status == "UNKNOWN"
        assert "not found in repo" in report.message.lower()


# ---------------------------------------------------------------------------
# Tests for check_all_staleness()
# ---------------------------------------------------------------------------


class TestCheckAllStaleness:
    """Integration tests for the batch staleness checker."""

    def test_iterates_multiple_contracts(self, tmp_path: Path):
        """check_all_staleness returns a report for each contract YAML."""
        workspace = tmp_path / "workspace"

        # Create two repos.
        repo_a = workspace / "project-a"
        sha_a = _init_repo(repo_a)

        repo_b = workspace / "project-b"
        sha_b = _init_repo(repo_b)

        # Make one stale.
        (repo_b / "src").mkdir()
        (repo_b / "src" / "main.py").write_text("# code\n")
        _git(repo_b, "add", ".")
        _git(repo_b, "commit", "-m", "add main.py")

        contracts_dir = tmp_path / "contracts"
        _make_contract_yaml(
            contracts_dir,
            name="alpha",
            full_name="project-a",
            verified_at_commit=sha_a,
            staleness_paths=["src/**"],
        )
        _make_contract_yaml(
            contracts_dir,
            name="beta",
            full_name="project-b",
            verified_at_commit=sha_b,
            staleness_paths=["src/**"],
        )

        reports = check_all_staleness(contracts_dir, workspace)

        assert "alpha" in reports
        assert "beta" in reports
        assert reports["alpha"].status == "CURRENT"
        assert reports["beta"].status == "STALE"

    def test_empty_contracts_dir(self, tmp_path: Path):
        """An empty contracts directory returns an empty dict."""
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        reports = check_all_staleness(contracts_dir, workspace)
        assert reports == {}

    def test_nonexistent_contracts_dir(self, tmp_path: Path):
        """A nonexistent contracts directory returns an empty dict."""
        reports = check_all_staleness(
            tmp_path / "no-such-dir",
            tmp_path / "workspace",
        )
        assert reports == {}

    def test_skips_unparseable_files(self, tmp_path: Path):
        """Files that are not valid contracts are silently skipped."""
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        (contracts_dir / "bad.yaml").write_text("not: a: valid: contract\n")

        workspace = tmp_path / "workspace"
        repo = workspace / "project-a"
        sha = _init_repo(repo)

        _make_contract_yaml(
            contracts_dir,
            name="alpha",
            full_name="project-a",
            verified_at_commit=sha,
            staleness_paths=["src/**"],
        )

        reports = check_all_staleness(contracts_dir, workspace)
        # The bad file is skipped, but the valid contract is processed.
        assert "alpha" in reports
        assert len(reports) == 1


# ---------------------------------------------------------------------------
# Tests for CLI
# ---------------------------------------------------------------------------


class TestCli:
    """Tests for the kairos CLI check-staleness command."""

    def test_cli_check_staleness_current(self, tmp_path: Path, capsys):
        """CLI reports CURRENT for up-to-date contracts."""
        from kairos.cli import main

        workspace = tmp_path / "workspace"
        repo = workspace / "my-repo"
        sha = _init_repo(repo)

        contracts_dir = tmp_path / "contracts"
        _make_contract_yaml(
            contracts_dir,
            name="myrepo",
            full_name="my-repo",
            verified_at_commit=sha,
            staleness_paths=["src/**"],
        )

        exit_code = main(
            [
                "check-staleness",
                "--contracts-dir",
                str(contracts_dir),
                "--workspace",
                str(workspace),
            ]
        )

        captured = capsys.readouterr()
        assert "CURRENT" in captured.out
        assert exit_code == 0

    def test_cli_check_staleness_stale_exit_code(self, tmp_path: Path, capsys):
        """CLI returns exit code 1 when any contract is STALE."""
        from kairos.cli import main

        workspace = tmp_path / "workspace"
        repo = workspace / "my-repo"
        sha = _init_repo(repo)

        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("# code\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "add app")

        contracts_dir = tmp_path / "contracts"
        _make_contract_yaml(
            contracts_dir,
            name="myrepo",
            full_name="my-repo",
            verified_at_commit=sha,
            staleness_paths=["src/**"],
        )

        exit_code = main(
            [
                "check-staleness",
                "--contracts-dir",
                str(contracts_dir),
                "--workspace",
                str(workspace),
            ]
        )

        captured = capsys.readouterr()
        assert "STALE" in captured.out
        assert exit_code == 1

    def test_cli_no_contracts(self, tmp_path: Path, capsys):
        """CLI handles an empty contracts directory gracefully."""
        from kairos.cli import main

        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        exit_code = main(
            [
                "check-staleness",
                "--contracts-dir",
                str(contracts_dir),
                "--workspace",
                str(workspace),
            ]
        )

        captured = capsys.readouterr()
        assert "No contracts found" in captured.out
        assert exit_code == 0

    def test_cli_missing_contracts_dir(self, tmp_path: Path, capsys):
        """CLI reports an error for missing contracts directory."""
        from kairos.cli import main

        exit_code = main(
            [
                "check-staleness",
                "--contracts-dir",
                str(tmp_path / "nonexistent"),
                "--workspace",
                str(tmp_path),
            ]
        )

        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()
        assert exit_code == 1
