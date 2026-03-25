"""Tests for kairos.server — MCP server core tools."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from kairos.embed import embed_contracts
from kairos.server import _load_contracts, _open_vec_connection, create_server

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample-contracts"


@pytest.fixture(scope="module")
def contracts_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a temporary directory with compute + vpc fixture contracts."""
    d = tmp_path_factory.mktemp("server-contracts")
    shutil.copy(FIXTURES_DIR / "valid-compute.yaml", d / "valid-compute.yaml")
    shutil.copy(FIXTURES_DIR / "valid-vpc.yaml", d / "valid-vpc.yaml")
    return d


@pytest.fixture(scope="module")
def db_path(tmp_path_factory: pytest.TempPathFactory, contracts_dir: Path) -> Path:
    """Run the embedding pipeline and return the database path."""
    db = tmp_path_factory.mktemp("server-db") / "test.db"
    total_chunks, total_contracts = embed_contracts(contracts_dir, db)
    assert total_chunks > 0
    assert total_contracts == 2
    return db


@pytest.fixture(scope="module")
def model():
    """Load the sentence-transformers model once for the test module."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture(scope="module")
def server(contracts_dir: Path, db_path: Path, model):
    """Create a Kairos MCP server with pre-populated state (no lifespan needed)."""
    mcp = create_server(contracts_dir, db_path)
    # Pre-populate the state dict so tools work without running the lifespan.
    state = mcp._kairos_state  # type: ignore[attr-defined]
    state["contracts"] = _load_contracts(contracts_dir)
    state["model"] = model
    state["conn"] = _open_vec_connection(db_path)

    yield mcp

    state["conn"].close()


class TestToolRegistration:
    """Verify the server exposes exactly the expected tools."""

    async def test_server_registers_four_tools(self, server):
        """The MCP server should register exactly 4 tools."""
        tools = await server.list_tools()
        tool_names = sorted(t.name for t in tools)
        assert tool_names == [
            "check_staleness",
            "find_relevant_contracts",
            "get_contract",
            "list_contracts",
        ]


class TestFindRelevantContracts:
    """Verify semantic search and deduplication in find_relevant_contracts."""

    async def test_docker_overlay_query_includes_compute(self, server):
        """find_relevant_contracts('Docker overlay network CIDR') should include compute."""
        result = await server.call_tool(
            "find_relevant_contracts",
            {"query": "Docker overlay network CIDR"},
        )
        # call_tool returns (list[TextContent], dict) for structured output
        content_list, structured = result
        text = content_list[0].text
        assert "compute" in text

    async def test_vpc_subnets_query_includes_vpc(self, server):
        """find_relevant_contracts('VPC subnets') should include vpc."""
        result = await server.call_tool(
            "find_relevant_contracts",
            {"query": "VPC subnets"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "vpc" in text

    async def test_results_include_matching_chunk_text(self, server):
        """Results should include the matching chunk text that explains *why* it matched."""
        result = await server.call_tool(
            "find_relevant_contracts",
            {"query": "Docker overlay network CIDR"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "**Matched chunk:**" in text

    async def test_results_deduplicate_by_repo(self, server):
        """Results should contain at most one entry per repo (deduplicated)."""
        result = await server.call_tool(
            "find_relevant_contracts",
            {"query": "infrastructure platform"},
        )
        content_list, structured = result
        text = content_list[0].text
        # Count the number of "## <repo_name>" headings — each repo appears once.
        headings = [line for line in text.split("\n") if line.startswith("## ")]
        repo_names = [h.split("(")[0].strip().lstrip("#").strip() for h in headings]
        # Verify no duplicates.
        assert len(repo_names) == len(set(repo_names)), (
            f"Duplicate repos found in results: {repo_names}"
        )

    async def test_results_include_full_contract_yaml(self, server):
        """Results should include the full contract YAML block."""
        result = await server.call_tool(
            "find_relevant_contracts",
            {"query": "Docker overlay network"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "**Full contract:**" in text
        assert "```yaml" in text


class TestGetContract:
    """Verify get_contract returns full YAML or error messages."""

    async def test_get_existing_contract(self, server):
        """get_contract('compute') should return full compute contract YAML."""
        result = await server.call_tool(
            "get_contract",
            {"repo_name": "compute"},
        )
        content_list, structured = result
        text = content_list[0].text
        # Should be valid YAML.
        data = yaml.safe_load(text)
        assert data["identity"]["name"] == "compute"
        assert "provides" in data
        assert "consumes" in data

    async def test_get_nonexistent_contract(self, server):
        """get_contract('nonexistent') should return an error listing available repos."""
        result = await server.call_tool(
            "get_contract",
            {"repo_name": "nonexistent"},
        )
        content_list, structured = result
        text = content_list[0].text
        assert "Error" in text
        assert "nonexistent" in text
        # Should list available repo names.
        assert "compute" in text
        assert "vpc" in text


class TestListContracts:
    """Verify list_contracts returns identity summaries for all loaded contracts."""

    async def test_list_returns_all_identities(self, server):
        """list_contracts() should return identity for all loaded contracts."""
        result = await server.call_tool("list_contracts", {})
        content_list, structured = result
        text = content_list[0].text
        # Should be valid YAML.
        identities = yaml.safe_load(text)
        assert isinstance(identities, list)
        names = [i["name"] for i in identities]
        assert "compute" in names
        assert "vpc" in names
        assert len(identities) == 2

    async def test_list_includes_identity_fields(self, server):
        """Each identity in the list should have all required fields."""
        result = await server.call_tool("list_contracts", {})
        content_list, structured = result
        text = content_list[0].text
        identities = yaml.safe_load(text)
        for ident in identities:
            assert "name" in ident
            assert "full_name" in ident
            assert "category" in ident
            assert "purpose" in ident
            assert "archetype" in ident
