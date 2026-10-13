# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/): the major version changes when the method changes in a way that makes months incomparable, the minor version when a measure or a month's data is added, and the patch version for corrections that do not change a published number.

## [Unreleased]

## [1.0.0] - 2026-10-13

First publication: "The state of public agent skills and MCP servers, October 2026".

### Added

- The October 2026 dataset in `data/2026-10/`: a random sample of 2,999 public repositories that ship a `SKILL.md`, a plugin or marketplace manifest or an MCP `server.json`, with `dataset.csv`, `dataset.json`, `stats.json`, the aggregate of secret-rule findings (counts only) and the precision table.
- The method in `METHOD.md`, the collection, scanning, statistics and chart scripts in `scripts/`, and the charts.
- `scripts/check_numbers.py`, run in CI, which checks the dataset shape and the README key findings against `stats.json`.
- The monthly index: a scheduled workflow that re-runs the scan on the 1st of each month and opens a pull request, `data/trend.csv` and the trend chart.
- Data licence (CC BY 4.0), code licence (MIT) and `CITATION.cff`.
