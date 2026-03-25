"""Tests for the check_staleness MCP tool in kairos.server.

Uses real temporary git repositories — no git operations are mocked.
Reuses the ``_init_repo`` / ``_make_contract_yaml`` patterns from
``test_staleness.py``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from kairos.embed import embed_contracts
from kairos.server import _load_contracts, _open_vec_connection, create_server


# ---------------------------------------------------------------------------
# Helpers (reused patterns from test_staleness.py)
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample-contracts"


@pytest.fixture()
def workspace_and_shas(tmp_path: Path) -> tuple[Path, str, str]:
    """Create a workspace with real git repos and return (workspace, sha_compute, sha_vpc)."""
    ws = tmp_path / "workspace"

    repo_compute = ws / "blueshift-compute"
    sha_compute = _init_repo(repo_compute)

    repo_vpc = ws / "blueshift-vpc"
    sha_vpc = _init_repo(repo_vpc)

    return ws, sha_compute, sha_vpc


@pytest.fixture()
def workspace(workspace_and_shas: tuple[Path, str, str]) -> Path:
    """Return just the workspace path."""
    return workspace_and_shas[0]


@pytest.fixture()
def contracts_with_shas(tmp_path: Path, workspace_and_shas: tuple[Path, str, str]) -> Path:
    """Create contract YAML files with verified_at_commit pointing at the real repo HEADs."""
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()

    _, sha_compute, sha_vpc = workspace_and_shas

    _make_contract_yaml(
        contracts_dir,
        name="compute",
        full_name="blueshift-compute",
        verified_at_commit=sha_compute,
        staleness_paths=["infrastructure/stacks/**"],
    )
    _make_contract_yaml(
        contracts_dir,
        name="vpc",
        full_name="blueshift-vpc",
        verified_at_commit=sha_vpc,
        staleness_paths=["infrastructure/stacks/**"],
    )

    return contracts_dir


@pytest.fixture()
def db_for_staleness(tmp_path: Path, contracts_with_shas: Path) -> Path:
    """Run the embedding pipeline on the staleness test contracts."""
    db = tmp_path / "staleness-test.db"
    embed_contracts(contracts_with_shas, db)
    return db


@pytest.fixture()
def staleness_server(contracts_with_shas: Path, db_for_staleness: Path, workspace: Path):
    """Create a Kairos MCP server with workspace_path and pre-populated state."""
    from sentence_transformers import SentenceTransformer

    mcp = create_server(contracts_with_shas, db_for_staleness, workspace_path=workspace)
    state = mcp._kairos_state  # type: ignore[attr-defined]
    state["contracts"] = _load_contracts(contracts_with_shas)
    state["model"] = SentenceTransformer("all-MiniLM-L6-v2")
    state["conn"] = _open_vec_connection(db_for_staleness)
    state["workspace_path"] = workspace

    yield mcp

    state["conn"].close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckStalenessSingleRepo:
    """Tests for check_staleness with a specific repo_name."""

    async def test_current_repo_returns_current(self, staleness_server):
        """check_staleness('vpc') returns CURRENT for a fresh contract."""
        result = await staleness_server.call_tool(
            "check_staleness",
            {"repo_name": "vpc"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "CURRENT" in text
        assert "vpc" in text

    async def test_nonexistent_repo_name_returns_error(self, staleness_server):
        """check_staleness('nonexistent') returns an error with available repos."""
        result = await staleness_server.call_tool(
            "check_staleness",
            {"repo_name": "nonexistent"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "Error" in text
        assert "nonexistent" in text
        assert "compute" in text
        assert "vpc" in text


class TestCheckStalenessAllRepos:
    """Tests for check_staleness with no repo_name (all contracts)."""

    async def test_all_repos_returns_reports(self, staleness_server):
        """check_staleness() with no argument returns a report for every loaded contract."""
        result = await staleness_server.call_tool(
            "check_staleness",
            {},
        )
        content_list, structured = result
        text = content_list[0].text
        # Both contracts should appear.
        assert "compute" in text
        assert "vpc" in text
        # Both should be CURRENT since no changes were made after verified_at_commit.
        assert "CURRENT" in text


class TestCheckStalenessNoWorkspace:
    """Tests for check_staleness when workspace_path is not configured."""

    @pytest.fixture()
    def server_no_workspace(self, tmp_path: Path):
        """Create a server WITHOUT workspace_path configured."""
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        _make_contract_yaml(
            contracts_dir,
            name="test",
            full_name="test-repo",
            verified_at_commit="abc123",
        )

        db = tmp_path / "test.db"
        embed_contracts(contracts_dir, db)

        from sentence_transformers import SentenceTransformer

        mcp = create_server(contracts_dir, db)  # No workspace_path
        state = mcp._kairos_state  # type: ignore[attr-defined]
        state["contracts"] = _load_contracts(contracts_dir)
        state["model"] = SentenceTransformer("all-MiniLM-L6-v2")
        state["conn"] = _open_vec_connection(db)
        # workspace_path is NOT set — simulates missing --workspace

        yield mcp

        state["conn"].close()

    async def test_missing_workspace_returns_error(self, server_no_workspace):
        """Missing workspace_path returns an informative error message."""
        result = await server_no_workspace.call_tool(
            "check_staleness",
            {"repo_name": "test"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "Error" in text
        assert "workspace_path not configured" in text
        assert "--workspace" in text


class TestStalenessReportFields:
    """Tests that staleness report output includes expected fields."""

    async def test_report_includes_status_and_message(self, staleness_server):
        """Staleness report includes status and message fields."""
        result = await staleness_server.call_tool(
            "check_staleness",
            {"repo_name": "vpc"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "**Status:**" in text
        assert "**Message:**" in text

    async def test_stale_report_includes_changed_files_and_commits(
        self, staleness_server, workspace
    ):
        """A STALE report includes changed_files and commits_since fields."""
        # Make the compute repo stale by changing a file in staleness_paths.
        repo_compute = workspace / "blueshift-compute"
        infra_dir = repo_compute / "infrastructure" / "stacks"
        infra_dir.mkdir(parents=True)
        (infra_dir / "stack.py").write_text("# changed\n")
        _git(repo_compute, "add", ".")
        _git(repo_compute, "commit", "-m", "modify infra stack")

        result = await staleness_server.call_tool(
            "check_staleness",
            {"repo_name": "compute"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "STALE" in text
        assert "**Changed files:**" in text
        assert "infrastructure/stacks/stack.py" in text
        assert "**Commits since verification:**" in text
