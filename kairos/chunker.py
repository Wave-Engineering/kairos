"""Contract chunker — decomposes a Contract into fine-grained semantic Chunks."""

from __future__ import annotations

from kairos.models import Chunk, Contract


def chunk_contract(contract: Contract) -> list[Chunk]:
    """Decompose a contract into fine-grained semantic chunks with metadata.

    Each chunk represents a single meaningful piece of information
    (e.g., one CloudFormation export, one gotcha, one API endpoint)
    with a natural-language text and traceability metadata.

    Args:
        contract: A parsed Contract instance.

    Returns:
        A list of Chunk instances, one per semantic unit.
    """
    name = contract.identity.name
    chunks: list[Chunk] = []

    # --- identity.purpose ---
    chunks.append(
        Chunk(
            text=f"{name}: {contract.identity.purpose}",
            repo_name=name,
            section="identity",
            field_path="identity.purpose",
        )
    )

    # --- provides ---
    provides = contract.provides

    for i, export in enumerate(provides.get("cloudformation_exports", [])):
        chunks.append(
            Chunk(
                text=(
                    f"{name} provides CloudFormation export"
                    f" {export['name']}: {export['description']}"
                ),
                repo_name=name,
                section="provides",
                field_path=f"provides.cloudformation_exports[{i}]",
            )
        )

    for i, image in enumerate(provides.get("docker_images", [])):
        chunks.append(
            Chunk(
                text=f"{name} builds Docker image {image['name']}: {image['description']}",
                repo_name=name,
                section="provides",
                field_path=f"provides.docker_images[{i}]",
            )
        )

    for i, network in enumerate(provides.get("docker_networks", [])):
        chunks.append(
            Chunk(
                text=(
                    f"{name} creates Docker network"
                    f" {network['name']} ({network['scope']}): {network['description']}"
                ),
                repo_name=name,
                section="provides",
                field_path=f"provides.docker_networks[{i}]",
            )
        )

    for i, secret in enumerate(provides.get("secrets", [])):
        chunks.append(
            Chunk(
                text=(f"{name} manages secret at {secret['path']}: {secret['description']}"),
                repo_name=name,
                section="provides",
                field_path=f"provides.secrets[{i}]",
            )
        )

    # --- consumes ---
    consumes = contract.consumes

    for i, imp in enumerate(consumes.get("cloudformation_imports", [])):
        chunks.append(
            Chunk(
                text=(
                    f"{name} consumes CloudFormation export"
                    f" {imp['export']} from {imp['from']}: {imp['description']}"
                ),
                repo_name=name,
                section="consumes",
                field_path=f"consumes.cloudformation_imports[{i}]",
            )
        )

    for i, image in enumerate(consumes.get("docker_images", [])):
        chunks.append(
            Chunk(
                text=f"{name} uses Docker image {image['name']} from {image['source']}",
                repo_name=name,
                section="consumes",
                field_path=f"consumes.docker_images[{i}]",
            )
        )

    for i, secret in enumerate(consumes.get("secrets", [])):
        chunks.append(
            Chunk(
                text=(
                    f"{name} reads secret at {secret['path']}"
                    f" from {secret['from']}: {secret['description']}"
                ),
                repo_name=name,
                section="consumes",
                field_path=f"consumes.secrets[{i}]",
            )
        )

    for i, repo in enumerate(consumes.get("repos", [])):
        chunks.append(
            Chunk(
                text=f"{name} depends on {repo['name']}: {repo['relationship']}",
                repo_name=name,
                section="consumes",
                field_path=f"consumes.repos[{i}]",
            )
        )

    # --- interfaces ---
    interfaces = contract.interfaces

    for i, endpoint in enumerate(interfaces.get("api_endpoints", [])):
        chunks.append(
            Chunk(
                text=(
                    f"{name} exposes {endpoint['service']}"
                    f" at {endpoint['url']}: {endpoint['description']}"
                ),
                repo_name=name,
                section="interfaces",
                field_path=f"interfaces.api_endpoints[{i}]",
            )
        )

    # --- gotchas ---
    for i, gotcha in enumerate(contract.gotchas):
        chunks.append(
            Chunk(
                text=(
                    f"{name} gotcha ({gotcha['severity']}): {gotcha['summary']}. {gotcha['detail']}"
                ),
                repo_name=name,
                section="gotchas",
                field_path=f"gotchas[{i}]",
            )
        )

    # --- operational ---
    operational = contract.operational
    if operational:
        tech = operational.get("tech_stack", {})
        language = tech.get("language", "unknown")
        framework = tech.get("framework", "unknown")
        validation_cmd = operational.get("validation_command", "N/A")
        test_cmd = operational.get("test_command", "N/A")
        chunks.append(
            Chunk(
                text=(
                    f"{name} uses {language}/{framework},"
                    f" validate: {validation_cmd},"
                    f" test: {test_cmd}"
                ),
                repo_name=name,
                section="operational",
                field_path="operational",
            )
        )

    return chunks
