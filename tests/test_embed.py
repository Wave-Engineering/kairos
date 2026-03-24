"""Tests for kairos.embed — embedding pipeline and semantic search."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kairos.chunker import chunk_contract
from kairos.models import Contract

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample-contracts"

# Expected chunk counts (verified in test_chunker.py and by inspection):
#   valid-compute.yaml = 17 chunks
#   valid-vpc.yaml     =  6 chunks (1 identity + 3 cf_exports + 1 gotcha + 1 operational)
#   valid-minimal.yaml =  1 chunk  (identity only)
#   valid-extra-fields.yaml = depends on content, but it's a valid contract
#
# We use a dedicated subdirectory with exactly compute + vpc for predictable counts.


@pytest.fixture(scope="module")
def embed_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a temporary directory with exactly two fixture contracts (compute + vpc)."""
    d = tmp_path_factory.mktemp("contracts")
    # Copy fixture files into the temp dir so we control exactly what gets embedded.
    import shutil

    shutil.copy(FIXTURES_DIR / "valid-compute.yaml", d / "valid-compute.yaml")
    shutil.copy(FIXTURES_DIR / "valid-vpc.yaml", d / "valid-vpc.yaml")
    return d


@pytest.fixture(scope="module")
def db_path(tmp_path_factory: pytest.TempPathFactory, embed_dir: Path) -> Path:
    """Run the embedding pipeline once and return the database path."""
    from kairos.embed import embed_contracts

    db = tmp_path_factory.mktemp("db") / "test.db"
    total_chunks, total_contracts = embed_contracts(embed_dir, db)
    assert total_chunks > 0
    assert total_contracts == 2
    return db


@pytest.fixture(scope="module")
def model():
    """Load the sentence-transformers model once for the test module."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture(scope="module")
def expected_chunk_count(embed_dir: Path) -> int:
    """Calculate the expected total chunk count from the fixture contracts."""
    total = 0
    for yaml_path in sorted(embed_dir.glob("*.yaml")):
        contract = Contract.from_yaml(yaml_path)
        total += len(chunk_contract(contract))
    return total


class TestEmbedCreatesDatabase:
    """Verify that embed_contracts creates a valid database file."""

    def test_database_file_exists(self, db_path: Path):
        """embed_contracts should create the sqlite database file."""
        assert db_path.exists()
        assert db_path.stat().st_size > 0

    def test_database_has_expected_row_count(self, db_path: Path, expected_chunk_count: int):
        """The database should have one row per semantic chunk."""
        import sqlite_vec

        conn = sqlite3.connect(str(db_path))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        meta_count = conn.execute("SELECT COUNT(*) FROM chunks_meta").fetchone()[0]
        vec_count = conn.execute("SELECT COUNT(*) FROM chunks_vec").fetchone()[0]
        conn.close()

        assert meta_count == expected_chunk_count
        assert vec_count == expected_chunk_count

    def test_vectors_have_384_dimensions(self, db_path: Path):
        """Each stored vector should have 384 dimensions (matching all-MiniLM-L6-v2)."""
        import sqlite_vec

        conn = sqlite3.connect(str(db_path))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        # Read first vector raw bytes from chunks_vec.
        row = conn.execute("SELECT embedding FROM chunks_vec LIMIT 1").fetchone()
        conn.close()

        assert row is not None
        raw_bytes = row[0]
        # Each float32 is 4 bytes; 384 dims = 1536 bytes.
        num_floats = len(raw_bytes) // 4
        assert num_floats == 384

    def test_metadata_fields_populated(self, db_path: Path):
        """Every metadata row should have non-empty repo_name, section, field_path, text."""
        import sqlite_vec

        conn = sqlite3.connect(str(db_path))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        rows = conn.execute(
            "SELECT repo_name, section, field_path, text FROM chunks_meta"
        ).fetchall()
        conn.close()

        assert len(rows) > 0
        for repo_name, section, field_path, text in rows:
            assert repo_name, "repo_name should not be empty"
            assert section, "section should not be empty"
            assert field_path, "field_path should not be empty"
            assert text, "text should not be empty"


class TestSearchSemanticRelevance:
    """Verify that search returns semantically relevant results."""

    def test_docker_query_returns_docker_chunks(self, db_path: Path, model):
        """search('Docker overlay network') should return chunks from compute contract
        that mention Docker networks, ranked higher than unrelated chunks."""
        from kairos.embed import search

        results = search("Docker overlay network", model, db_path, top_k=10)

        assert len(results) > 0

        # The top result should be from the compute contract (which has Docker networks).
        top_chunk, top_distance = results[0]
        assert top_chunk.repo_name == "compute"
        # The top chunk should mention Docker network content.
        assert "docker" in top_chunk.text.lower() or "network" in top_chunk.text.lower()

    def test_cloudformation_vpc_query_returns_vpc_chunks_first(self, db_path: Path, model):
        """search('CloudFormation export VPC') should return vpc-related chunks first."""
        from kairos.embed import search

        results = search("CloudFormation export VPC", model, db_path, top_k=10)

        assert len(results) > 0

        # At least one of the top-3 results should be from the vpc contract.
        top3_repos = [chunk.repo_name for chunk, _ in results[:3]]
        assert "vpc" in top3_repos, f"Expected 'vpc' in top 3 results, got repos: {top3_repos}"

    def test_search_returns_chunk_with_distance(self, db_path: Path, model):
        """Each search result should be a (Chunk, float) tuple."""
        from kairos.embed import search

        results = search("infrastructure", model, db_path, top_k=5)

        for chunk, distance in results:
            assert hasattr(chunk, "text")
            assert hasattr(chunk, "repo_name")
            assert hasattr(chunk, "section")
            assert hasattr(chunk, "field_path")
            assert isinstance(distance, float)

    def test_search_respects_top_k(self, db_path: Path, model):
        """search should return at most top_k results."""
        from kairos.embed import search

        results = search("infrastructure", model, db_path, top_k=3)
        assert len(results) <= 3


class TestEmbedIdempotent:
    """Verify that re-running embed replaces previous data."""

    def test_reembed_replaces_data(self, embed_dir: Path, tmp_path: Path):
        """Running embed_contracts twice should not double the row count."""
        from kairos.embed import embed_contracts

        db = tmp_path / "idempotent.db"

        # First run.
        chunks1, contracts1 = embed_contracts(embed_dir, db)
        assert chunks1 > 0

        # Second run — should replace, not append.
        chunks2, contracts2 = embed_contracts(embed_dir, db)
        assert chunks2 == chunks1
        assert contracts2 == contracts1

        # Verify actual row counts in the database.
        import sqlite_vec

        conn = sqlite3.connect(str(db))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        meta_count = conn.execute("SELECT COUNT(*) FROM chunks_meta").fetchone()[0]
        conn.close()

        assert meta_count == chunks1


class TestEmbedInvalidContracts:
    """Verify that invalid contracts are skipped without aborting."""

    def test_invalid_yaml_skipped(self, tmp_path: Path):
        """A directory with one valid and one invalid contract should still succeed."""
        from kairos.embed import embed_contracts

        # Create a valid contract.
        import shutil

        shutil.copy(FIXTURES_DIR / "valid-minimal.yaml", tmp_path / "valid.yaml")

        # Create an invalid YAML file (not a valid contract — missing identity).
        (tmp_path / "broken.yaml").write_text("this: is\nnot: a\nvalid: contract\n")

        db = tmp_path / "partial.db"
        total_chunks, total_contracts = embed_contracts(tmp_path, db)

        # The valid contract should have been processed.
        assert total_contracts == 1
        assert total_chunks >= 1

    def test_malformed_yaml_skipped(self, tmp_path: Path):
        """Completely malformed YAML should be skipped."""
        from kairos.embed import embed_contracts

        import shutil

        shutil.copy(FIXTURES_DIR / "valid-minimal.yaml", tmp_path / "good.yaml")

        # Write a file with invalid YAML syntax.
        (tmp_path / "malformed.yaml").write_text("{{{{not yaml at all::::\n")

        db = tmp_path / "malformed.db"
        total_chunks, total_contracts = embed_contracts(tmp_path, db)

        assert total_contracts == 1
        assert total_chunks >= 1
