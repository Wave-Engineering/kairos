"""Install Kairos MCP server configuration into Claude Code settings."""

from __future__ import annotations

import json
from pathlib import Path


def _settings_path(scope: str) -> Path:
    """Return the target settings file path for the given scope."""
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    return Path.cwd() / ".claude" / "settings.local.json"


def install_mcp_config(
    contracts_dir: Path,
    db_path: Path,
    scope: str = "project",
) -> Path:
    """Add kairos MCP server configuration to a Claude Code settings file.

    Args:
        contracts_dir: Path to the contracts directory (resolved to absolute).
        db_path: Path to the sqlite-vec database (resolved to absolute).
        scope: Either ``"project"`` (writes ``.claude/settings.local.json``
               in the current directory) or ``"user"`` (writes
               ``~/.claude/settings.json``).

    Returns:
        The path to the settings file that was written.

    Raises:
        ValueError: If scope is invalid or JSON is malformed.
    """
    if scope not in ("project", "user"):
        raise ValueError(f"Invalid scope: {scope!r} (must be 'project' or 'user')")

    contracts_dir = contracts_dir.resolve()
    db_path = db_path.resolve()

    settings_file = _settings_path(scope)

    # Read existing settings or start fresh.
    if settings_file.exists():
        raw = settings_file.read_text()
        try:
            settings = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON in {settings_file}: {exc}") from exc
    else:
        settings = {}

    # Merge kairos into mcpServers, preserving other servers.
    mcp_servers = settings.setdefault("mcpServers", {})
    if not isinstance(mcp_servers, dict):
        raise ValueError(
            f"Malformed settings in {settings_file}: "
            f"mcpServers must be an object, got {type(mcp_servers).__name__}"
        )
    mcp_servers["kairos"] = {
        "command": "kairos",
        "args": [
            "serve",
            "--contracts-dir",
            str(contracts_dir),
            "--db",
            str(db_path),
        ],
    }

    # Write back.
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    return settings_file
