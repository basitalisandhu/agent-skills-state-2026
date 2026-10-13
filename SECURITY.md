# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 1.x | yes |

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting on this repository (Security tab, "Report a vulnerability") rather than a public issue. Include the file or workflow concerned and a minimal way to reproduce the problem. Do not include real credentials; a redacted example is enough.

You will get an acknowledgement within 7 days and a fix or a mitigation plan within 30 days for confirmed issues. Credit is given in the release notes unless you prefer otherwise.

## Scope

This repository holds a research dataset, the Python scripts that build it and the GitHub Actions workflows that re-run the scan each month. The scripts read public repository metadata and agent configuration files through the GitHub API and write CSV, JSON and chart files. They do not execute any content from the repositories they sample.

Issues of interest: a way for content in a sampled repository to run code or inject content into a generated file, a secret appearing in the dataset or in a workflow log (secret-rule findings are only counted, never stored in full), unsafe handling of the token used by the monthly workflow, and problems in the development tooling.

A wrong number, a mislabelled repository or a flawed method step is a data correction, not a vulnerability. Please open it publicly as described in [CONTRIBUTING.md](CONTRIBUTING.md). If a repository owner would like a row removed or a finding re-checked, the same route applies.
