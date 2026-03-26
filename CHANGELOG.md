# Changelog

All notable changes to Kairos are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-03-25

### Added

- Contract schema (`contracts/schema.yaml`) with JSON Schema validation and contract template (`#14`)
- Python models and validation module (`kairos/models.py`, `kairos/schema.py`) (`#15`)
- Pilot contracts for vpc, compute, littleguy, and manifests (`#16`, `#17`)
- Contract chunker for fine-grained semantic decomposition (`kairos/chunker.py`) (`#19`)
- Staleness checker with git-based freshness detection (`kairos/staleness.py`) (`#18`)
- Static digest aggregation module and CLI (`kairos/aggregate.py`) (`#20`)
- Embedding pipeline with sentence-transformers and sqlite-vec (`kairos/embed.py`) (`#21`)
- MCP server with `find_relevant_contracts`, `get_contract`, `list_contracts` tools (`#22`)
- MCP server `check_staleness` tool for contract freshness via MCP (`#23`)
- CLI with four subcommands: `embed`, `serve`, `check-staleness`, `aggregate` (`#24`)
- Configuration reference (`docs/configuration.md`) and quickstart guide (`docs/quickstart.md`) (`#24`)
- End-to-end CLI round-trip and MCP lifespan tests (`#26`)
- Architecture and internals reference (`docs/architecture.md`) (`#31`)
- Contract authoring guide (`docs/contracts-guide.md`) (`#32`)
- Project scaffold: CI pipeline, Makefile, pyproject.toml, smoke tests (`#14`)
