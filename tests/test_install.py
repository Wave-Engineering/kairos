"""Tests for kairos.install — MCP server configuration into Claude Code settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kairos.install import install_mcp_config


class TestInstallMcpConfig:
    """Unit tests for install_mcp_config()."""

    def test_creates_settings_file(self, tmp_path: Path, monkeypatch):
        """Settings file is created when it doesn't exist."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        result = install_mcp_config(contracts, db, scope="project")

        expected = tmp_path / ".claude" / "settings.local.json"
        assert result == expected
        assert expected.exists()

        settings = json.loads(expected.read_text())
        assert "mcpServers" in settings
        assert "kairos" in settings["mcpServers"]

    def test_project_scope_path(self, tmp_path: Path, monkeypatch):
        """Project scope writes to .claude/settings.local.json in cwd."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        result = install_mcp_config(contracts, db, scope="project")

        assert result == tmp_path / ".claude" / "settings.local.json"

    def test_user_scope_path(self, tmp_path: Path, monkeypatch):
        """User scope writes to ~/.claude/settings.json."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        result = install_mcp_config(contracts, db, scope="user")

        assert result == tmp_path / ".claude" / "settings.json"

    def test_absolute_paths_in_config(self, tmp_path: Path, monkeypatch):
        """Contracts dir and db paths are resolved to absolute in the output."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        install_mcp_config(contracts, db, scope="project")

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        args = settings["mcpServers"]["kairos"]["args"]

        # All paths in args should be absolute.
        contracts_idx = args.index("--contracts-dir") + 1
        db_idx = args.index("--db") + 1
        assert Path(args[contracts_idx]).is_absolute()
        assert Path(args[db_idx]).is_absolute()

    def test_preserves_existing_servers(self, tmp_path: Path, monkeypatch):
        """Other MCP servers in the settings file are not overwritten."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        # Pre-populate with another MCP server.
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {
            "mcpServers": {
                "other-server": {
                    "command": "other",
                    "args": ["--flag"],
                }
            }
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(existing))

        install_mcp_config(contracts, db, scope="project")

        settings = json.loads((claude_dir / "settings.local.json").read_text())
        assert "other-server" in settings["mcpServers"]
        assert "kairos" in settings["mcpServers"]

    def test_updates_existing_kairos(self, tmp_path: Path, monkeypatch):
        """An existing kairos config is replaced with the new one."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        # Pre-populate with stale kairos config.
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {
            "mcpServers": {
                "kairos": {
                    "command": "kairos",
                    "args": ["serve", "--contracts-dir", "/old/path", "--db", "/old/db"],
                }
            }
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(existing))

        install_mcp_config(contracts, db, scope="project")

        settings = json.loads((claude_dir / "settings.local.json").read_text())
        args = settings["mcpServers"]["kairos"]["args"]
        assert "/old/path" not in args
        assert str(contracts.resolve()) in args

    def test_creates_directory(self, tmp_path: Path, monkeypatch):
        """.claude/ directory is created if it doesn't exist."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        assert not (tmp_path / ".claude").exists()

        install_mcp_config(contracts, db, scope="project")

        assert (tmp_path / ".claude").is_dir()

    def test_malformed_json_raises(self, tmp_path: Path, monkeypatch):
        """Malformed JSON in existing settings produces a clear error."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.local.json").write_text("{broken json")

        with pytest.raises(ValueError, match="Malformed JSON"):
            install_mcp_config(contracts, db, scope="project")

    def test_invalid_scope_raises(self, tmp_path: Path):
        """An invalid scope value raises ValueError."""
        with pytest.raises(ValueError, match="Invalid scope"):
            install_mcp_config(tmp_path, tmp_path / "db", scope="global")

    def test_malformed_mcp_servers_type_raises(self, tmp_path: Path, monkeypatch):
        """mcpServers that isn't a dict produces a clear error."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.local.json").write_text(json.dumps({"mcpServers": "not-a-dict"}))

        with pytest.raises(ValueError, match="mcpServers must be an object"):
            install_mcp_config(contracts, db, scope="project")

    def test_preserves_non_mcp_settings(self, tmp_path: Path, monkeypatch):
        """Non-MCP settings in the file are preserved."""
        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {"theme": "dark", "mcpServers": {}}
        (claude_dir / "settings.local.json").write_text(json.dumps(existing))

        install_mcp_config(contracts, db, scope="project")

        settings = json.loads((claude_dir / "settings.local.json").read_text())
        assert settings["theme"] == "dark"
        assert "kairos" in settings["mcpServers"]


class TestInstallCli:
    """CLI-level tests for kairos install subcommand."""

    def test_install_via_cli(self, tmp_path: Path, monkeypatch, capsys):
        """kairos install --scope project writes settings and prints confirmation."""
        from kairos.cli import main

        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        db = tmp_path / "test.db"

        exit_code = main(
            [
                "install",
                "--contracts-dir",
                str(contracts),
                "--db",
                str(db),
                "--scope",
                "project",
            ]
        )

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "configured" in captured.out
        assert "Restart Claude Code" in captured.out

        settings_file = tmp_path / ".claude" / "settings.local.json"
        assert settings_file.exists()

    def test_install_missing_contracts_dir(self, tmp_path: Path, capsys):
        """kairos install with nonexistent contracts dir returns error."""
        from kairos.cli import main

        exit_code = main(
            [
                "install",
                "--contracts-dir",
                str(tmp_path / "nonexistent"),
                "--db",
                str(tmp_path / "test.db"),
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_install_malformed_settings(self, tmp_path: Path, monkeypatch, capsys):
        """kairos install with malformed existing settings returns error."""
        from kairos.cli import main

        monkeypatch.chdir(tmp_path)
        contracts = tmp_path / "contracts"
        contracts.mkdir()

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.local.json").write_text("{broken")

        exit_code = main(
            [
                "install",
                "--contracts-dir",
                str(contracts),
                "--db",
                str(tmp_path / "test.db"),
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Malformed JSON" in captured.err


class TestEmbedBreadcrumbs:
    """Test that kairos embed prints next-step guidance."""

    def test_embed_prints_breadcrumbs(self, tmp_path: Path, capsys):
        """After successful embed, output includes next-step suggestions."""
        import shutil

        from kairos.cli import main

        fixtures = Path(__file__).parent / "fixtures" / "sample-contracts"
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        shutil.copy(fixtures / "valid-compute.yaml", contracts / "valid-compute.yaml")

        db = tmp_path / "test.db"

        exit_code = main(
            [
                "embed",
                "--contracts-dir",
                str(contracts),
                "--db",
                str(db),
            ]
        )

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Next steps:" in captured.out
        assert "kairos serve" in captured.out
        assert "kairos install" in captured.out
        # Paths should be absolute in the breadcrumb.
        assert str(contracts.resolve()) in captured.out
        assert str(db.resolve()) in captured.out
