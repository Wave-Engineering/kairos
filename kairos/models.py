"""Data models for Kairos contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ContractIdentity:
    """Identity section of a contract."""

    name: str
    full_name: str
    category: str
    purpose: str
    archetype: str


@dataclass
class Chunk:
    """A fine-grained semantic chunk extracted from a contract.

    Each chunk represents a single meaningful piece of information
    (e.g., one CloudFormation export, one gotcha, one API endpoint)
    with metadata for traceability.
    """

    text: str
    repo_name: str
    section: str
    field_path: str


@dataclass
class StalenessReport:
    """Result of checking a contract's freshness against git history."""

    repo_name: str
    status: str  # "CURRENT", "STALE", or "UNKNOWN"
    message: str = ""
    changed_files: list[str] = field(default_factory=list)
    commits_since: int = 0


@dataclass
class Contract:
    """A parsed Kairos contract with typed access to all sections.

    Wraps the raw YAML data and provides structured access to
    contract fields through the identity, provides, consumes,
    interfaces, operational, gotchas, and metadata sections.
    """

    contract_version: str
    identity: ContractIdentity
    raw: dict[str, Any]

    @classmethod
    def from_yaml(cls, path: Path) -> Contract:
        """Load and parse a contract YAML file.

        Args:
            path: Path to the contract YAML file.

        Returns:
            A Contract instance with typed access to all sections.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file is not valid YAML.
            KeyError: If required fields are missing.
        """
        with open(path) as f:
            data = yaml.safe_load(f)

        identity_data = data["identity"]
        identity = ContractIdentity(
            name=identity_data["name"],
            full_name=identity_data["full_name"],
            category=identity_data["category"],
            purpose=identity_data["purpose"],
            archetype=identity_data["archetype"],
        )

        return cls(
            contract_version=data["contract_version"],
            identity=identity,
            raw=data,
        )

    @property
    def provides(self) -> dict[str, Any]:
        """Access the provides section of the contract."""
        return self.raw.get("provides", {})

    @property
    def consumes(self) -> dict[str, Any]:
        """Access the consumes section of the contract."""
        return self.raw.get("consumes", {})

    @property
    def interfaces(self) -> dict[str, Any]:
        """Access the interfaces section of the contract."""
        return self.raw.get("interfaces", {})

    @property
    def operational(self) -> dict[str, Any]:
        """Access the operational section of the contract."""
        return self.raw.get("operational", {})

    @property
    def gotchas(self) -> list[dict[str, Any]]:
        """Access the gotchas section of the contract."""
        return self.raw.get("gotchas", [])

    @property
    def staleness_paths(self) -> list[str]:
        """Access the staleness_paths field."""
        return self.raw.get("staleness_paths", [])

    @property
    def last_verified(self) -> str | None:
        """Access the last_verified date."""
        return self.raw.get("last_verified")

    @property
    def verified_at_commit(self) -> str | None:
        """Access the verified_at_commit SHA."""
        return self.raw.get("verified_at_commit")
