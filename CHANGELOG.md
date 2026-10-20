# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/): the major version changes when the method changes in a way that makes months incomparable, the minor version when a measure or a month's data is added, and the patch version for corrections that do not change a published number.

## [Unreleased]

## [1.2.0] - 2026-10-20

A new measure: version pins in MCP server READMEs. No number published in 1.0.0 or 1.1.0 changes.

### Added

- `docs/mcp-readme-install-pins.md`: the follow-up report "Do MCP server READMEs tell you which version to run?", on whether the launch commands in the READMEs of the 399 sampled repositories that ship a `server.json` name an exact version, with denominators, 95% confidence intervals, a 60-command hand check, a "what to check before you install" list and limitations.
- `scripts/readme_pins_fetch.py` (re-fetches those repositories' READMEs and `server.json` files at the dataset's commits, nothing executed) and `scripts/readme_pins.py` (static extraction and classing of launch commands, standard library only).
- `data/2026-10/readme-pins/`: `results.json`, `commands.csv`, `repos.csv` and `hand-check.csv`.
- `tests/test_readme_pins.py` with fixtures for JSON, TOML, YAML and shell forms, and a check that every share in the report matches `results.json`.
- A README section, a `METHOD.md` section and a citation for the report; `CITATION.cff` is now version 1.2.0.
- A "Related datasets" section in the README linking the RugSnare drift-watch corpus, and a note on dependency drift in `docs/mcp-tool-annotations.md`.

### Changed

- `scripts/annotations_fetch.py`: `one()` takes an optional list of sparse-checkout patterns, so the README fetch can reuse it. Its default behaviour is unchanged.

## [1.1.0] - 2026-10-16

A new measure: MCP tool annotations. No number published in 1.0.0 changes.

### Added

- `docs/mcp-tool-annotations.md`: the follow-up report "Do MCP servers say which tools are safe?", on whether the 399 sampled repositories that ship a `server.json` set `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint` on their tools, with denominators, 95% confidence intervals, a 60-tool hand check and limitations.
- `scripts/annotations_fetch.py` (re-fetches those repositories' source at the dataset's commits, nothing executed) and `scripts/annotations.py` (static extraction of tool registrations and hints, standard library only).
- `data/2026-10/annotations/`: `results.json`, `tools.csv`, `repos.csv` and `hand-check.csv`.
- `tests/test_annotations.py` with fixtures for TypeScript, JavaScript, Python, Go, Rust and C# registrations, and a check that every share in the report matches `results.json`.
- A README section and citation for the follow-up report; `CITATION.cff` is now version 1.1.0.
- `docs/querying-the-dataset.md`: worked jq and Python examples on the committed October 2026 data, with their output, and an offline rebuild of `stats.json` and the charts.
- `docs/monthly-run.md`: the search token, a dry run and the time budget of the monthly run, with a measured dry run.
- The monthly workflow takes a `limit` input for a dry run that prints counts and timings and opens no pull request (#3).

### Changed

- `run_month.py` stops at once when code search refuses the token (a 403 that is not a rate limit, or a 422 on the first page of a query) instead of waiting or continuing with an empty sample, and reports search and scan timings (#3).
- The monthly workflow uses a `SEARCH_TOKEN` secret when one exists, and the workflow token otherwise (#3).

## [1.0.0] - 2026-10-13

First publication: "The state of public agent skills and MCP servers, October 2026".

### Added

- The October 2026 dataset in `data/2026-10/`: a random sample of 2,999 public repositories that ship a `SKILL.md`, a plugin or marketplace manifest or an MCP `server.json`, with `dataset.csv`, `dataset.json`, `stats.json`, the aggregate of secret-rule findings (counts only) and the precision table.
- The method in `METHOD.md`, the collection, scanning, statistics and chart scripts in `scripts/`, and the charts.
- `scripts/check_numbers.py`, run in CI, which checks the dataset shape and the README key findings against `stats.json`.
- The monthly index: a scheduled workflow that re-runs the scan on the 1st of each month and opens a pull request, `data/trend.csv` and the trend chart.
- Data licence (CC BY 4.0), code licence (MIT) and `CITATION.cff`.
