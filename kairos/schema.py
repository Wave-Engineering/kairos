"""Contract schema validation using JSON Schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jsonschema
import yaml


# Path to the schema file, relative to this module's location.
_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "contracts"
DEFAULT_SCHEMA_PATH = _SCHEMA_DIR / "schema.yaml"


@dataclass
class ValidationError:
    """A structured validation error from contract schema validation.

    Attributes:
        field_path: Dot-separated path to the field that failed validation
                    (e.g., 'identity.archetype').
        message: Human-readable description of the error.
        severity: Severity level of the error ('error' for schema violations).
    """

    field_path: str
    message: str
    severity: str = "error"


def _load_schema(schema_path: Path) -> dict:
    """Load the JSON Schema from a YAML file.

    Args:
        schema_path: Path to the schema YAML file.

    Returns:
        The parsed schema as a dictionary.
    """
    with open(schema_path) as f:
        return yaml.safe_load(f)


def validate_contract(
    yaml_path: Path,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> list[ValidationError]:
    """Validate a contract YAML file against the Kairos contract schema.

    Loads the JSON Schema from schema.yaml, parses the target YAML file,
    and validates it. Returns an empty list on success or a list of
    structured ValidationError instances on failure.

    Args:
        yaml_path: Path to the contract YAML file to validate.
        schema_path: Path to the JSON Schema YAML file. Defaults to
                     contracts/schema.yaml relative to the project root.

    Returns:
        An empty list if the contract is valid, or a list of ValidationError
        instances describing each validation failure.
    """
    schema = _load_schema(schema_path)

    with open(yaml_path) as f:
        contract_data = yaml.safe_load(f)

    validator = jsonschema.Draft202012Validator(schema)
    errors: list[ValidationError] = []

    for error in validator.iter_errors(contract_data):
        # Build a dot-separated field path from the deque of path elements.
        field_path = (
            ".".join(str(part) for part in error.absolute_path) if error.absolute_path else "(root)"
        )

        errors.append(
            ValidationError(
                field_path=field_path,
                message=error.message,
                severity="error",
            )
        )

    return errors
