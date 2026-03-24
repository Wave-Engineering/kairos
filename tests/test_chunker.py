"""Tests for kairos.chunker — contract decomposition into semantic chunks."""

from pathlib import Path

from kairos.chunker import chunk_contract
from kairos.models import Contract

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample-contracts"


class TestChunkCountAndMetadata:
    """Verify that chunk_contract produces the right number of chunks with correct metadata."""

    def test_chunk_count_matches_expected(self):
        """valid-compute.yaml should produce exactly 17 chunks.

        Breakdown:
          identity.purpose                    = 1
          provides.cloudformation_exports     = 2
          provides.docker_images              = 1
          provides.docker_networks            = 1
          provides.packages (empty)           = 0
          provides.secrets                    = 1
          provides.ci_templates (empty)       = 0
          consumes.cloudformation_imports     = 2
          consumes.docker_images              = 1
          consumes.secrets                    = 1
          consumes.repos                      = 1
          interfaces.api_endpoints            = 2
          gotchas                             = 3
          operational                         = 1
                                      Total  = 17
        """
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        assert len(chunks) == 17

    def test_all_chunks_have_non_empty_fields(self):
        """Every chunk must have non-empty text, repo_name, section, and field_path."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        for chunk in chunks:
            assert chunk.text, f"Empty text in chunk: {chunk}"
            assert chunk.repo_name, f"Empty repo_name in chunk: {chunk}"
            assert chunk.section, f"Empty section in chunk: {chunk}"
            assert chunk.field_path, f"Empty field_path in chunk: {chunk}"

    def test_all_chunks_have_correct_repo_name(self):
        """Every chunk should carry the contract's identity name as repo_name."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        for chunk in chunks:
            assert chunk.repo_name == "compute"


class TestIdentityChunk:
    """Verify the identity.purpose chunk content."""

    def test_identity_chunk_contains_repo_name(self):
        """The identity chunk text should contain the repo name."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        identity_chunks = [c for c in chunks if c.field_path == "identity.purpose"]
        assert len(identity_chunks) == 1
        assert "compute" in identity_chunks[0].text

    def test_identity_chunk_contains_purpose_text(self):
        """The identity chunk text should contain the purpose description."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        identity_chunks = [c for c in chunks if c.field_path == "identity.purpose"]
        assert "EC2" in identity_chunks[0].text or "compute" in identity_chunks[0].text.lower()

    def test_identity_chunk_section_is_identity(self):
        """The identity chunk should have section='identity'."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        identity_chunks = [c for c in chunks if c.field_path == "identity.purpose"]
        assert identity_chunks[0].section == "identity"


class TestGotchaChunks:
    """Verify that gotcha chunks include severity in their text."""

    def test_gotcha_chunks_include_severity(self):
        """Each gotcha chunk text must contain its severity level."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        gotcha_chunks = [c for c in chunks if c.section == "gotchas"]
        assert len(gotcha_chunks) == 3
        expected_severities = ["critical", "high", "medium"]
        for chunk, severity in zip(gotcha_chunks, expected_severities):
            assert severity in chunk.text, (
                f"Expected severity '{severity}' in gotcha chunk text: {chunk.text}"
            )

    def test_gotcha_chunks_include_summary_and_detail(self):
        """Each gotcha chunk text must contain both its summary and detail."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        gotcha_chunks = [c for c in chunks if c.section == "gotchas"]
        # First gotcha: severity=critical, summary about CDK user-data
        assert "CDK user-data" in gotcha_chunks[0].text
        assert "user_data_causes_replacement" in gotcha_chunks[0].text

    def test_gotcha_chunk_field_paths(self):
        """Gotcha chunks should have indexed field paths."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        gotcha_chunks = [c for c in chunks if c.section == "gotchas"]
        assert gotcha_chunks[0].field_path == "gotchas[0]"
        assert gotcha_chunks[1].field_path == "gotchas[1]"
        assert gotcha_chunks[2].field_path == "gotchas[2]"


class TestProvidesChunks:
    """Verify provides section chunks."""

    def test_cloudformation_export_chunks(self):
        """Each CloudFormation export should produce a chunk with correct text template."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        cf_chunks = [c for c in chunks if "cloudformation_exports" in c.field_path]
        assert len(cf_chunks) == 2
        assert "provides CloudFormation export" in cf_chunks[0].text
        assert "blueshift-compute-{env}-InstanceId" in cf_chunks[0].text

    def test_docker_image_chunks(self):
        """Each provided Docker image should produce a chunk."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        img_chunks = [c for c in chunks if "provides.docker_images" in c.field_path]
        assert len(img_chunks) == 1
        assert "builds Docker image" in img_chunks[0].text
        assert "blueshift-mutator" in img_chunks[0].text

    def test_docker_network_chunks(self):
        """Each provided Docker network should produce a chunk."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        net_chunks = [c for c in chunks if "provides.docker_networks" in c.field_path]
        assert len(net_chunks) == 1
        assert "creates Docker network" in net_chunks[0].text
        assert "blueshift_public" in net_chunks[0].text
        assert "swarm" in net_chunks[0].text

    def test_secret_provide_chunks(self):
        """Each provided secret should produce a chunk."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        secret_chunks = [c for c in chunks if "provides.secrets" in c.field_path]
        assert len(secret_chunks) == 1
        assert "manages secret at" in secret_chunks[0].text

    def test_empty_arrays_produce_no_chunks(self):
        """Empty provides arrays (packages, ci_templates) produce zero chunks."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        pkg_chunks = [c for c in chunks if "packages" in c.field_path]
        ci_chunks = [c for c in chunks if "ci_templates" in c.field_path]
        assert len(pkg_chunks) == 0
        assert len(ci_chunks) == 0


class TestConsumesChunks:
    """Verify consumes section chunks."""

    def test_cloudformation_import_chunks(self):
        """Each CloudFormation import should produce a chunk with correct text template."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        cf_chunks = [c for c in chunks if "cloudformation_imports" in c.field_path]
        assert len(cf_chunks) == 2
        assert "consumes CloudFormation export" in cf_chunks[0].text
        assert "from vpc" in cf_chunks[0].text

    def test_consumed_docker_image_chunks(self):
        """Each consumed Docker image should produce a chunk."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        img_chunks = [c for c in chunks if "consumes.docker_images" in c.field_path]
        assert len(img_chunks) == 1
        assert "uses Docker image" in img_chunks[0].text
        assert "swarm-cd" in img_chunks[0].text

    def test_consumed_secret_chunks(self):
        """Each consumed secret should produce a chunk."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        secret_chunks = [c for c in chunks if "consumes.secrets" in c.field_path]
        assert len(secret_chunks) == 1
        assert "reads secret at" in secret_chunks[0].text
        assert "from registry" in secret_chunks[0].text

    def test_repo_dependency_chunks(self):
        """Each repo dependency should produce a chunk."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        repo_chunks = [c for c in chunks if "consumes.repos" in c.field_path]
        assert len(repo_chunks) == 1
        assert "depends on vpc" in repo_chunks[0].text


class TestInterfacesChunks:
    """Verify interfaces section chunks."""

    def test_api_endpoint_chunks(self):
        """Each API endpoint should produce a chunk with correct text template."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        api_chunks = [c for c in chunks if "api_endpoints" in c.field_path]
        assert len(api_chunks) == 2
        assert "exposes keycloak" in api_chunks[0].text
        assert "auth.{DOMAIN}" in api_chunks[0].text


class TestOperationalChunk:
    """Verify the operational chunk."""

    def test_operational_chunk_content(self):
        """The operational chunk should contain language, framework, and commands."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        op_chunks = [c for c in chunks if c.section == "operational"]
        assert len(op_chunks) == 1
        text = op_chunks[0].text
        assert "python/aws-cdk" in text
        assert "validate:" in text
        assert "test:" in text

    def test_operational_chunk_field_path(self):
        """The operational chunk should have field_path='operational'."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        chunks = chunk_contract(contract)
        op_chunks = [c for c in chunks if c.section == "operational"]
        assert op_chunks[0].field_path == "operational"


class TestMinimalContract:
    """Verify that a minimal contract produces only identity + operational chunks."""

    def test_minimal_contract_produces_only_identity_chunk(self):
        """A contract with no provides/consumes/gotchas produces only identity.purpose.

        The minimal fixture has no operational section either, so only
        the identity.purpose chunk is produced.
        """
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-minimal.yaml")
        chunks = chunk_contract(contract)
        assert len(chunks) == 1
        assert chunks[0].section == "identity"
        assert chunks[0].field_path == "identity.purpose"

    def test_minimal_contract_no_empty_section_chunks(self):
        """A minimal contract should not produce chunks for missing sections."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-minimal.yaml")
        chunks = chunk_contract(contract)
        sections = {c.section for c in chunks}
        assert "provides" not in sections
        assert "consumes" not in sections
        assert "gotchas" not in sections
        assert "interfaces" not in sections
