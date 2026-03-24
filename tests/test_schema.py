"""Tests for kairos.schema — contract validation against JSON Schema."""

from pathlib import Path

import pytest
import yaml

from kairos.models import Contract
from kairos.schema import validate_contract

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample-contracts"
SCHEMA_PATH = Path(__file__).parent.parent / "contracts" / "schema.yaml"


class TestSchemaIsValidJsonSchema:
    """Verify that contracts/schema.yaml is itself a valid JSON Schema."""

    def test_schema_loads_as_yaml(self):
        """Schema file loads as valid YAML."""
        with open(SCHEMA_PATH) as f:
            schema = yaml.safe_load(f)
        assert isinstance(schema, dict)
        assert schema["type"] == "object"

    def test_schema_has_required_fields(self):
        """Schema defines contract_version and identity as required."""
        with open(SCHEMA_PATH) as f:
            schema = yaml.safe_load(f)
        assert "contract_version" in schema["required"]
        assert "identity" in schema["required"]

    def test_schema_allows_additional_properties(self):
        """Schema has additionalProperties: true at root for forward compatibility."""
        with open(SCHEMA_PATH) as f:
            schema = yaml.safe_load(f)
        assert schema["additionalProperties"] is True

    def test_schema_parseable_by_jsonschema(self):
        """Schema is parseable by the jsonschema library (Draft 2020-12)."""
        import jsonschema

        with open(SCHEMA_PATH) as f:
            schema = yaml.safe_load(f)
        # Creating a validator instance parses and validates the schema itself.
        validator = jsonschema.Draft202012Validator(schema)
        # Check the schema can be used for validation without error.
        validator.check_schema(schema)


class TestValidContracts:
    """Verify that valid contracts pass validation."""

    def test_valid_compute_passes(self):
        """A complete valid contract (compute) passes validation with no errors."""
        errors = validate_contract(FIXTURES_DIR / "valid-compute.yaml")
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_minimal_passes(self):
        """A contract with only required fields passes validation."""
        errors = validate_contract(FIXTURES_DIR / "valid-minimal.yaml")
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_extra_fields_passes(self):
        """A contract with additional fields not in the schema passes validation."""
        errors = validate_contract(FIXTURES_DIR / "valid-extra-fields.yaml")
        assert errors == [], f"Unexpected errors: {errors}"


class TestInvalidContracts:
    """Verify that invalid contracts fail validation with correct error details."""

    def test_missing_identity_fails(self):
        """A contract missing the required identity section fails validation."""
        errors = validate_contract(FIXTURES_DIR / "invalid-missing-identity.yaml")
        assert len(errors) > 0, "Expected validation errors for missing identity"
        # At least one error should reference 'identity' as a required field.
        identity_errors = [e for e in errors if "identity" in e.message.lower()]
        assert len(identity_errors) > 0, (
            f"Expected an error referencing 'identity', got: {[e.message for e in errors]}"
        )

    def test_missing_identity_error_field_path(self):
        """Missing identity error has the correct field path."""
        errors = validate_contract(FIXTURES_DIR / "invalid-missing-identity.yaml")
        # The error is at the root level because a required property is missing.
        identity_errors = [e for e in errors if "identity" in e.message.lower()]
        assert any(e.field_path == "(root)" for e in identity_errors), (
            f"Expected field_path '(root)' for missing required property, "
            f"got: {[e.field_path for e in identity_errors]}"
        )

    def test_bad_archetype_fails(self):
        """A contract with an invalid archetype enum value fails validation."""
        errors = validate_contract(FIXTURES_DIR / "invalid-bad-archetype.yaml")
        assert len(errors) > 0, "Expected validation errors for bad archetype"
        # At least one error should reference the enum constraint.
        archetype_errors = [
            e
            for e in errors
            if "identity.archetype" in e.field_path or "archetype" in e.message.lower()
        ]
        assert len(archetype_errors) > 0, (
            f"Expected an error referencing archetype enum, "
            f"got: {[(e.field_path, e.message) for e in errors]}"
        )

    def test_bad_archetype_error_references_enum(self):
        """Bad archetype error message references the enum constraint."""
        errors = validate_contract(FIXTURES_DIR / "invalid-bad-archetype.yaml")
        archetype_errors = [e for e in errors if "identity.archetype" in e.field_path]
        assert len(archetype_errors) > 0
        # The error message from jsonschema should mention the invalid value
        # or the enum values.
        error_msg = archetype_errors[0].message
        assert "invalid-value" in error_msg or "enum" in error_msg.lower(), (
            f"Expected error to reference enum or 'invalid-value', got: {error_msg}"
        )

    def test_all_errors_have_severity(self):
        """All validation errors have a severity field set."""
        errors = validate_contract(FIXTURES_DIR / "invalid-missing-identity.yaml")
        for error in errors:
            assert error.severity == "error"


class TestContractFromYaml:
    """Verify that Contract.from_yaml() loads and parses contracts correctly."""

    def test_from_yaml_loads_valid_contract(self):
        """Contract.from_yaml() successfully loads a valid contract."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        assert contract.contract_version == "0.1.0"
        assert contract.identity.name == "compute"
        assert contract.identity.full_name == "blueshift-compute"
        assert contract.identity.category == "infrastructure"
        assert contract.identity.archetype == "cdk-infra"
        assert "compute" in contract.identity.purpose.lower() or "EC2" in contract.identity.purpose

    def test_from_yaml_provides_section(self):
        """Contract.from_yaml() provides typed access to the provides section."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        provides = contract.provides
        assert "cloudformation_exports" in provides
        assert len(provides["cloudformation_exports"]) == 2

    def test_from_yaml_consumes_section(self):
        """Contract.from_yaml() provides typed access to the consumes section."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        consumes = contract.consumes
        assert "cloudformation_imports" in consumes
        assert consumes["cloudformation_imports"][0]["from"] == "vpc"

    def test_from_yaml_gotchas(self):
        """Contract.from_yaml() provides access to gotchas."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        gotchas = contract.gotchas
        assert len(gotchas) == 3
        assert gotchas[0]["severity"] == "critical"

    def test_from_yaml_staleness_paths(self):
        """Contract.from_yaml() provides access to staleness_paths."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        assert len(contract.staleness_paths) == 4
        assert "infrastructure/stacks/**" in contract.staleness_paths

    def test_from_yaml_metadata(self):
        """Contract.from_yaml() provides access to verification metadata."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        assert contract.last_verified == "2026-03-24"
        assert contract.verified_at_commit == "abc1234"

    def test_from_yaml_minimal_contract(self):
        """Contract.from_yaml() works with a minimal contract (only required fields)."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-minimal.yaml")
        assert contract.identity.name == "minimal"
        assert contract.provides == {}
        assert contract.consumes == {}
        assert contract.gotchas == []
        assert contract.staleness_paths == []

    def test_from_yaml_raises_on_missing_file(self):
        """Contract.from_yaml() raises FileNotFoundError for nonexistent files."""
        with pytest.raises(FileNotFoundError):
            Contract.from_yaml(Path("/nonexistent/path/contract.yaml"))

    def test_from_yaml_raw_contains_all_data(self):
        """Contract.from_yaml() stores the full raw YAML data."""
        contract = Contract.from_yaml(FIXTURES_DIR / "valid-compute.yaml")
        assert "provides" in contract.raw
        assert "consumes" in contract.raw
        assert "interfaces" in contract.raw
        assert "operational" in contract.raw
        assert "gotchas" in contract.raw
