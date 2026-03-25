"""E2E tests for kairos CLI — exercise full command paths through cli.main()."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from kairos.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample-contracts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    _git(path, "config", "user.email", "test@test.com")
    _git(path, "config", "user.name", "Test")
    (path / "README.md").write_text("# hello\n")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial commit")
    return _git(path, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def contracts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "contracts"
    d.mkdir()
    shutil.copy(FIXTURES_DIR / "valid-compute.yaml", d / "valid-compute.yaml")
    shutil.copy(FIXTURES_DIR / "valid-vpc.yaml", d / "valid-vpc.yaml")
    return d


# ---------------------------------------------------------------------------
# kairos embed
# ---------------------------------------------------------------------------


class TestEmbedCli:
    def test_embed_produces_database(self, contracts_dir: Path, tmp_path: Path, capsys):
        db = tmp_path / "test.db"

        exit_code = main(
            [
                "embed",
                "--contracts-dir",
                str(contracts_dir),
                "--db",
                str(db),
            ]
        )

        assert exit_code == 0
        assert db.exists()
        assert db.stat().st_size > 0

        captured = capsys.readouterr()
        assert "Embedded" in captured.out
        assert "chunks" in captured.out

    def test_embed_missing_contracts_dir(self, tmp_path: Path, capsys):
        exit_code = main(
            [
                "embed",
                "--contracts-dir",
                str(tmp_path / "nonexistent"),
                "--db",
                str(tmp_path / "test.db"),
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err


# ---------------------------------------------------------------------------
# kairos aggregate
# ---------------------------------------------------------------------------


class TestAggregateCli:
    def test_aggregate_produces_markdown(self, contracts_dir: Path, tmp_path: Path, capsys):
        output = tmp_path / "digest.md"

        exit_code = main(
            [
                "aggregate",
                "--contracts-dir",
                str(contracts_dir),
                "--output",
                str(output),
            ]
        )

        assert exit_code == 0
        assert output.exists()

        content = output.read_text()
        assert "compute" in content
        assert "vpc" in content

        captured = capsys.readouterr()
        assert "Digest written to" in captured.out

    def test_aggregate_missing_contracts_dir(self, tmp_path: Path, capsys):
        exit_code = main(
            [
                "aggregate",
                "--contracts-dir",
                str(tmp_path / "nonexistent"),
                "--output",
                str(tmp_path / "digest.md"),
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err


# ---------------------------------------------------------------------------
# kairos serve (error paths only — live serve blocks on stdio)
# ---------------------------------------------------------------------------


class TestServeCli:
    def test_serve_missing_contracts_dir(self, tmp_path: Path, capsys):
        exit_code = main(
            [
                "serve",
                "--contracts-dir",
                str(tmp_path / "nonexistent"),
                "--db",
                str(tmp_path / "test.db"),
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "contracts directory not found" in captured.err

    def test_serve_missing_db(self, contracts_dir: Path, tmp_path: Path, capsys):
        exit_code = main(
            [
                "serve",
                "--contracts-dir",
                str(contracts_dir),
                "--db",
                str(tmp_path / "nonexistent.db"),
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "database not found" in captured.err


# ---------------------------------------------------------------------------
# kairos check-staleness
# ---------------------------------------------------------------------------


class TestCheckStalenessCli:
    @pytest.fixture()
    def staleness_workspace(self, tmp_path: Path):
        """Create contracts with verified_at_commit pointing at real repos."""
        import yaml

        ws = tmp_path / "workspace"
        contracts = tmp_path / "contracts"
        contracts.mkdir()

        # Create a repo and a contract pointing at its HEAD.
        repo = ws / "blueshift-compute"
        sha = _init_repo(repo)

        data = {
            "contract_version": "0.1.0",
            "identity": {
                "name": "compute",
                "full_name": "blueshift-compute",
                "category": "infrastructure",
                "purpose": "Test contract",
                "archetype": "cdk-infra",
            },
            "verified_at_commit": sha,
            "staleness_paths": ["infrastructure/**"],
        }
        (contracts / "compute.yaml").write_text(yaml.dump(data))

        return contracts, ws

    def test_check_staleness_current(self, staleness_workspace, capsys):
        contracts, ws = staleness_workspace

        exit_code = main(
            [
                "check-staleness",
                "--contracts-dir",
                str(contracts),
                "--workspace",
                str(ws),
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "compute" in captured.out
        assert "CURRENT" in captured.out

    def test_check_staleness_missing_contracts_dir(self, tmp_path: Path, capsys):
        exit_code = main(
            [
                "check-staleness",
                "--contracts-dir",
                str(tmp_path / "nonexistent"),
                "--workspace",
                str(tmp_path),
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
