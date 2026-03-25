"""Tests for the MCP server lifespan — verify state is correctly populated and cleaned up."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from kairos.embed import embed_contracts
from kairos.server import create_server

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample-contracts"


@pytest.fixture(scope="module")
def contracts_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("lifespan-contracts")
    shutil.copy(FIXTURES_DIR / "valid-compute.yaml", d / "valid-compute.yaml")
    shutil.copy(FIXTURES_DIR / "valid-vpc.yaml", d / "valid-vpc.yaml")
    return d


@pytest.fixture(scope="module")
def db_path(tmp_path_factory: pytest.TempPathFactory, contracts_dir: Path) -> Path:
    db = tmp_path_factory.mktemp("lifespan-db") / "test.db"
    embed_contracts(contracts_dir, db)
    return db


def _run_lifespan(mcp):
    """Return the low-level server's lifespan as an async context manager."""
    srv = mcp._mcp_server
    return srv.lifespan(srv)


class TestLifespanPopulatesState:
    """Verify the async lifespan correctly loads all state."""

    async def test_lifespan_loads_contracts(self, contracts_dir: Path, db_path: Path):
        mcp = create_server(contracts_dir, db_path)

        async with _run_lifespan(mcp):
            state = mcp._kairos_state  # type: ignore[attr-defined]
            assert "contracts" in state
            assert "compute" in state["contracts"]
            assert "vpc" in state["contracts"]
            assert len(state["contracts"]) == 2

    async def test_lifespan_loads_model(self, contracts_dir: Path, db_path: Path):
        mcp = create_server(contracts_dir, db_path)

        async with _run_lifespan(mcp):
            state = mcp._kairos_state  # type: ignore[attr-defined]
            assert "model" in state
            # SentenceTransformer has an encode method.
            assert hasattr(state["model"], "encode")

    async def test_lifespan_opens_connection(self, contracts_dir: Path, db_path: Path):
        mcp = create_server(contracts_dir, db_path)

        async with _run_lifespan(mcp):
            state = mcp._kairos_state  # type: ignore[attr-defined]
            assert "conn" in state
            assert isinstance(state["conn"], sqlite3.Connection)
            # Connection should be usable.
            cursor = state["conn"].execute("SELECT 1")
            assert cursor.fetchone() == (1,)

    async def test_lifespan_stores_workspace_path(self, contracts_dir: Path, db_path: Path):
        workspace = Path("/tmp/test-workspace")
        mcp = create_server(contracts_dir, db_path, workspace_path=workspace)

        async with _run_lifespan(mcp):
            state = mcp._kairos_state  # type: ignore[attr-defined]
            assert state.get("workspace_path") == workspace

    async def test_lifespan_stores_none_workspace_when_omitted(
        self, contracts_dir: Path, db_path: Path
    ):
        mcp = create_server(contracts_dir, db_path)

        async with _run_lifespan(mcp):
            state = mcp._kairos_state  # type: ignore[attr-defined]
            assert state.get("workspace_path") is None


class TestLifespanCleanup:
    """Verify the lifespan cleans up resources on exit."""

    async def test_lifespan_closes_connection_on_exit(self, contracts_dir: Path, db_path: Path):
        mcp = create_server(contracts_dir, db_path)

        async with _run_lifespan(mcp):
            state = mcp._kairos_state  # type: ignore[attr-defined]
            conn = state["conn"]
            # Connection should work inside the session.
            conn.execute("SELECT 1")

        # After session exits, connection should be closed.
        with pytest.raises(Exception):
            conn.execute("SELECT 1")
