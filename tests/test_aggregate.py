"""Tests for the aggregate module."""

from __future__ import annotations

from pathlib import Path

from kairos.aggregate import aggregate_contracts

# Fixture directory containing agg-repo-a.yaml, agg-repo-b.yaml, agg-repo-c.yaml
# with known provides/consumes relationships for deterministic testing.
_AGG_DIR = Path(__file__).resolve().parent / "fixtures" / "aggregate-contracts"


def test_output_contains_all_repo_names():
    """Test that the digest output contains all repository names."""
    markdown = aggregate_contracts(_AGG_DIR)

    assert "repo-a" in markdown
    assert "repo-b" in markdown
    assert "repo-c" in markdown


def test_dependency_table_shows_consumes_relationship():
    """Test that the dependency table shows repo-b consuming exports from repo-a."""
    markdown = aggregate_contracts(_AGG_DIR)

    # The table should show repo-a as provider, repo-b as consumer for VpcId
    assert "repo-a-VpcId" in markdown
    assert "repo-a-SubnetIds" in markdown

    # Find the dependency table section and verify the relationship
    lines = markdown.splitlines()
    table_lines = [line for line in lines if "|" in line and "repo-a" in line and "repo-b" in line]
    assert len(table_lines) >= 1, (
        "Expected at least one dependency table row with repo-a providing to repo-b"
    )


def test_gotchas_sorted_by_severity():
    """Test that gotchas are sorted by severity: critical before high before medium before low."""
    markdown = aggregate_contracts(_AGG_DIR)

    # Extract just the gotchas section
    gotchas_start = markdown.index("## Aggregated Gotchas")
    gotchas_section = markdown[gotchas_start:]

    # Find positions of severity markers
    critical_pos = gotchas_section.index("[CRITICAL]")
    high_pos = gotchas_section.index("[HIGH]")
    medium_positions = [
        i for i in range(len(gotchas_section)) if gotchas_section[i:].startswith("[MEDIUM]")
    ]
    low_pos = gotchas_section.index("[LOW]")

    # critical should come before high
    assert critical_pos < high_pos, "CRITICAL should appear before HIGH"

    # high should come before medium
    assert high_pos < medium_positions[0], "HIGH should appear before MEDIUM"

    # medium should come before low
    assert medium_positions[0] < low_pos, "MEDIUM should appear before LOW"


def test_repos_sorted_by_category():
    """Test that repos are sorted by category: infrastructure, core, apps."""
    markdown = aggregate_contracts(_AGG_DIR)

    # In the Repository Summaries section, repo-a (infrastructure) should
    # appear before repo-b (core), which should appear before repo-c (apps).
    summaries_start = markdown.index("## Repository Summaries")
    summaries_section = markdown[summaries_start:]

    repo_a_pos = summaries_section.index("org-repo-a")
    repo_b_pos = summaries_section.index("org-repo-b")
    repo_c_pos = summaries_section.index("org-repo-c")

    assert repo_a_pos < repo_b_pos, "infrastructure (repo-a) should appear before core (repo-b)"
    assert repo_b_pos < repo_c_pos, "core (repo-b) should appear before apps (repo-c)"


def test_aggregate_with_real_contracts():
    """Test aggregation against the real pilot contracts in contracts/repos/."""
    real_contracts_dir = Path(__file__).resolve().parent.parent / "contracts" / "repos"
    if not real_contracts_dir.is_dir():
        return  # Skip if not available

    markdown = aggregate_contracts(real_contracts_dir)

    # Should contain all 4 pilot contracts
    assert "vpc" in markdown
    assert "compute" in markdown
    assert "manifests" in markdown
    assert "littleguy" in markdown

    # The dependency table should show compute consuming vpc's CF exports
    assert "blueshift-vpc-{env}-VpcId" in markdown

    # Should have platform overview with contract count
    assert "4 contracts" in markdown


def test_dependency_table_shows_secret_consumption():
    """Test that secret consumes entries with 'from' appear in the dependency table."""
    markdown = aggregate_contracts(_AGG_DIR)

    # repo-c consumes a secret from repo-b
    assert "secret/app/db-password" in markdown

    # Find the row in the dependency table
    lines = markdown.splitlines()
    secret_rows = [line for line in lines if "|" in line and "repo-b" in line and "repo-c" in line]
    assert len(secret_rows) >= 1, (
        "Expected at least one dependency table row with repo-b providing a secret to repo-c"
    )


def test_aggregate_empty_directory(tmp_path: Path):
    """Test aggregation with an empty directory produces valid markdown."""
    markdown = aggregate_contracts(tmp_path)

    assert "# Kairos Ecosystem Digest" in markdown
    assert "0 contracts" in markdown


def test_aggregate_nonexistent_directory(tmp_path: Path):
    """Test aggregation with a nonexistent directory produces valid markdown."""
    nonexistent = tmp_path / "does-not-exist"
    markdown = aggregate_contracts(nonexistent)

    assert "# Kairos Ecosystem Digest" in markdown
    assert "0 contracts" in markdown
