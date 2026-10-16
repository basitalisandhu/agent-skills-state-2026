# The state of public agent skills and MCP servers, October 2026

*Muhammad Basit Ali, 13 October 2026. Dataset, method and scripts are in this repository. Data and text: CC BY 4.0. Code: MIT.*

*This is the first edition. The scan is re-run every month and each month's data is added alongside; see [Updated monthly](#updated-monthly).*

## Key findings

1. **82.0%** of repositories have no `SECURITY.md` (2,459 of 2,999). Even counting organisation-wide defaults, 80.7% have no security policy.
2. **46.0%** of repositories with a local MCP server run at least one that is not pinned to a version (159 of 346). Of those, 100 use `npx` with no exact version, 63 ask for `latest`, and 38 run a Python package with no version.
3. **32.7%** of repositories have no licence file at the root (982 of 2,999).
4. **15.5%** of skill repositories declare at least one skill with unrestricted `Bash` (407 of 2,621).
5. **12.6%** of skill repositories have at least one `SKILL.md` whose front matter fails YAML parsing (330 of 2,621).

## Follow-up report: MCP tool annotations

**[Do MCP servers say which tools are safe?](docs/mcp-tool-annotations.md)** (16 October 2026) answers the question the first edition could not: whether MCP servers mark their tools with `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint`. It re-fetched the source of the 399 repositories in this sample that ship a `server.json`, at the commits in the dataset, and read the tool registrations without running anything. Of the 304 servers whose registrations could be read (17,688 tools in all), 188 (61.8%) annotate none of their tools and only 69 (22.7%) annotate every one. Of the 1,099 tools named for deleting, sending, paying or writing, 214 (19.5%) declare `destructiveHint: true`. Every share has its denominator and a 95% confidence interval; the data is in [`data/2026-10/annotations/`](data/2026-10/annotations/) and the scripts are `scripts/annotations_fetch.py` and `scripts/annotations.py`. No number in this first edition changes.

## Charts

![Share of repositories with each finding, from 82.0% with no SECURITY.md down to 3.5% with a hook that calls a non-local host](charts/chart1-prevalence.png)

| Finding | Repositories | Denominator | Share |
|---|---|---|---|
| No SECURITY.md in the repository | 2,459 | 2,999 | 82.0% |
| Stdio MCP server not pinned to a version | 159 | 346 | 46.0% |
| No licence file at the root | 982 | 2,999 | 32.7% |
| A skill allows unrestricted Bash | 407 | 2,621 | 15.5% |
| A SKILL.md has no front matter | 346 | 2,621 | 13.2% |
| A SKILL.md front matter fails YAML parsing | 330 | 2,621 | 12.6% |
| A skill description is over 1,024 characters | 146 | 2,621 | 5.6% |
| A hook calls a non-local host (hand-verified) | 13 | 373 | 3.5% |

![Findings by GitHub star band: licences improve with popularity, security policies barely move and MCP pinning does not improve](charts/chart2-by-stars.png)

| Stars | Repositories | No SECURITY.md | No licence file | Repositories with stdio MCP | Unpinned MCP |
|---|---|---|---|---|---|
| 0 | 984 | 88.2% | 53.7% | 116 | 43.1% |
| 1 to 9 | 707 | 77.9% | 33.8% | 108 | 43.5% |
| 10 to 99 | 874 | 81.5% | 16.4% | 77 | 46.8% |
| 100 or more | 434 | 75.6% | 16.6% | 45 | 57.8% |

Licences improve with popularity. Security policies barely move, and pinning does not improve at all; the 100-plus band is the worst for MCP pinning, though on only 45 repositories.

![Precision of each check, from 100% for unrestricted Bash down to 0% for two of the secret rules](charts/chart3-precision.png)

| Check | Findings checked | Correct | Precision | Used? |
|---|---|---|---|---|
| Unrestricted Bash (SSG607) | 10 | 10 | 100% | yes |
| Unpinned MCP (SSG401, 402, 403) | 22 | 19 | 86% | yes |
| Front matter fails YAML parsing | 10 | 10 | 100% | yes |
| No licence file (SSG702), against GitHub | 982 | 968 | 99% | yes |
| No security policy (SSG701), against GitHub | 2,459 | 2,420 | 98% | yes |
| Description over 1,024 characters, against parser | 513 | 470 | 92% | yes |
| Missing 'Use when' (linter) | 10 | 1 | 10% | no |
| yaml-unsafe (linter) | 10 | 0 | 0% | no |
| Secret in MCP env (SSG405) | 10 | 0 | 0% | no |
| Hard-coded credential (SSG503) | 10 | 0 | 0% | no |
| Provider token (SSG502) | 10 | 0 | 0% | no |
| Private key block (SSG501) | 10 | 0 | 0% | no |

The chart data is in [`data/2026-10/chart-data.csv`](data/2026-10/chart-data.csv) and the full precision table in [`data/2026-10/precision.csv`](data/2026-10/precision.csv).

## Updated monthly

This study is a monthly index. On the 1st of each month at 03:00 UTC a scheduled workflow ([`.github/workflows/monthly.yml`](.github/workflows/monthly.yml)) runs [`scripts/run_month.py`](scripts/run_month.py) end to end and opens a pull request with the results.

- **Re-measured each month:** the same 31 code search queries, a new random sample of 3,000 repositories (seed `YYYYMM01`, so November 2026 uses 20261101), the same sparse fetch of agent configuration files only, and the same scanners at the same pinned versions (skill-scan-gate 0.2.0 at e53fdc8, claude-code-tooling-skills v0.1.1, mcp-tools-lint 0.2.0 at 8540f7c). Every share in the dataset and `stats.json` is recomputed.
- **Not re-measured:** precision. The hand and automated precision checks were done once, for this first edition; later months reuse them and say "precision not re-measured" in the trend notes. Hooks are flagged automatically but not read by hand, and secret-rule findings are only counted, never triaged or named.
- **Where the data lives:** each month in `data/YYYY-MM/` (`dataset.csv`, `dataset.json`, `stats.json`, `secret_rules_aggregate.csv`). This first edition is in [`data/2026-10/`](data/2026-10/), with its precision table and chart data. `data/dataset.csv`, `data/dataset.json`, `data/stats.json` and `data/secret_rules_aggregate.csv` are always copies of the latest month, so existing links keep working. [`data/trend.csv`](data/trend.csv) has one row per month with the key findings and their denominators, drawn in `charts/trend.png`.

![Key findings by month](charts/trend.png)

## Method in one paragraph

We searched GitHub code search on 13 October 2026: 93 requests across 31 queries split by file size, which surfaced 7,456 distinct non-fork repositories. We drew 3,000 at random; one failed to download, leaving 2,999. This is a sample of what search surfaces, not a census of GitHub.

The sample is young and mostly small: 2,512 of the 2,999 (84%) were created in 2026, the median repository has 4 stars, and 434 have 100 or more. 2,621 contain at least one skill, 336,285 `SKILL.md` files in all, with a median of 10 per repository. 1,047 ship a plugin manifest, 913 a marketplace manifest, 373 an agent hook configuration and 346 at least one MCP server that runs as a local process.

We fetched only the agent configuration files, ran nothing, and scanned with skill-scan-gate 0.2.0, the description linter, inventory and portability scripts from claude-code-tooling-skills, and mcp-tools-lint 0.2.0, with a standard YAML parser as a reference. [`METHOD.md`](METHOD.md) lists every query, cap, version and precision check.

## The findings in detail

**1. Most repositories give no way to report a vulnerability.** 2,459 of 2,999 (82.0%) have no `SECURITY.md` in the repository; 2,420 (80.7%) have no security policy even counting organisation-wide defaults. Among repositories with 100 or more stars the figure is still 75.6% (of 434).

**2. Nearly half of the MCP configurations run code that can change under you.** Of the 346 repositories that configure a local MCP server, 159 (46.0%) start at least one with no pinned version: 100 (28.9%) run an npm package through `npx` with no exact version, 63 (18.2%) ask for the `latest` tag outright, and 38 (11.0%) run a Python package without a version. Each session start can fetch whatever the package owner, or anyone who takes over the package, published last.

![How unpinned local MCP servers are unpinned: 100 of 346 (28.9%) via npx with no exact version, 63 of 346 (18.2%) asking for latest, and 38 of 346 (11.0%) a Python package with no version](charts/mcp-pinning.png)

| How unpinned | Repositories | Denominator | Share |
|---|---|---|---|
| npm package via `npx`, no exact version (SSG401) | 100 | 346 | 28.9% |
| asks for `latest` (SSG403) | 63 | 346 | 18.2% |
| Python package with no version (SSG402) | 38 | 346 | 11.0% |

Groups overlap; the total unpinned is 159 of 346.

**3. A third ship with no licence.** 982 of 2,999 (32.7%) have no licence file at the root; GitHub's own licence detection finds none for 969. For zero-star repositories it is 53.7% (of 984); for repositories with 100 or more stars, 16.6% (of 434). Without a licence, a team has no clear right to copy a skill into its own repository.

**4. One in six skill repositories gives a skill the whole shell.** 407 of the 2,621 repositories with skills (15.5%) declare at least one skill whose `allowed-tools` grants `Bash` with no command scoping, 10,073 declarations in total. That is not proof of misuse, but it removes the host's chance to ask before each command.

**5. One in eight skill repositories has a skill whose header does not parse.** In 330 of 2,621 (12.6%) at least one `SKILL.md` has YAML front matter that a standard parser rejects, usually because a description contains an unquoted colon. That is 4,761 of 336,285 files (1.4%). A further 346 repositories (13.2%) contain a `SKILL.md` with no front matter at all. A host that cannot read the name and description cannot decide when to load the skill.

Two smaller results. In 146 of 2,621 skill repositories (5.6%) a description runs past 1,024 characters, a common host limit. And of the 373 repositories with hook configurations, 13 (3.5%) have a hook that, by default, calls a host other than the local machine (hand-verified); another 6 talk only to a local service. Across all 2,999, our hook check flagged 34 repositories; reading each one by hand, 30 make a network call of some kind and 15 reach a non-local host by default.

The MCP tool-schema check had little to work with, since a server has to run to list its tools and we ran nothing. In the 10 repositories that commit a tool list (986 tools), all 986 tools lack annotations and 836 declare a JSON Schema dialect that strict clients reject. Those lists are clustered and say little about MCP servers in general.

## Secrets: counted, not named

The secret-shaped-string rules fire in 471 of 2,999 repositories. Read by hand, almost all of those hits are documentation: secret-scanner regexes, placeholder tokens in setup guides, example API responses, deliberately poisoned research corpora. Reporting 471 as "repositories leaking secrets" would be wrong. We triaged every hit by structure, without displaying any value, and were left with 30 possible live credentials in 17 repositories. The totals per rule are in [`data/2026-10/secret_rules_aggregate.csv`](data/2026-10/secret_rules_aggregate.csv); the public dataset leaves out per-repository counts for the secret rules (SSG203, SSG405, SSG501, SSG502 and SSG503).

We drop the "missing when-to-use guidance" measure for a similar reason. The linter looks for the literal phrase "Use when", and in a hand check most descriptions it flagged did say when to use the skill, in other words or in another language.

## What this means for teams installing skills

- **Pin every MCP server.** Write `package@1.2.3`, never a bare name or `@latest`, and update on purpose. This is the most common finding that can run code without review, and it is a one-line fix.
- **Read `allowed-tools` before you install.** A skill that asks for unscoped `Bash` should explain why, or be scoped to the commands it needs.
- **Treat hooks as code that runs on every tool call.** Most hooks we read stay local, but some phone home on install or post session data to a webhook. Read the hook scripts, not only the manifest.
- **Check the licence before copying.** One in three repositories in this sample gives you no right to reuse the skill.
- **Lint your own skills in CI.** A colon in a description is enough to stop a host reading the skill header; it is cheap to catch and invisible until it bites.
- **Do not trust a scanner's secret count.** In this corpus most secret-shaped strings were examples. Use the findings as a reading list, then judge them.

## Reproduce it

1. Clone this repository and install the pinned scanners. See [`docs/reproducing.md`](docs/reproducing.md) for the exact commands and the time and token budget.
2. The search and download need a GitHub token with code search. The monthly workflow uses one stored as a repository secret.
3. Analyse with `scripts/build.py`, `scripts/stats.py` and `scripts/charts.py` to rebuild the dataset, the numbers in this report and the three charts.

To explore the data instead, [`docs/querying-the-dataset.md`](docs/querying-the-dataset.md) has worked jq and Python examples with their output, and shows how to rebuild `stats.json` and the charts offline from the committed dataset. [`docs/monthly-run.md`](docs/monthly-run.md) covers the scheduled run: the token, a dry run and the time budget.

## Files

| Path | What it is |
|---|---|
| `data/2026-10/dataset.csv` | One row per repository, with every measure and the commit we measured |
| `data/2026-10/dataset.json` | The same, as JSON |
| `data/2026-10/stats.json` | The shares and denominators used in this report |
| `data/2026-10/precision.csv` | Every precision check, with its sample size and result |
| `data/2026-10/chart-data.csv` | The values behind the three charts |
| `data/2026-10/secret_rules_aggregate.csv` | Counts per secret rule, no values |
| `data/dataset.csv`, `dataset.json`, `stats.json`, `secret_rules_aggregate.csv` | Copies of the latest month; `data/precision.csv` and `data/chart-data.csv` stay the first edition's |
| `data/trend.csv` | One row per month |
| `charts/` | The three first-edition charts and `trend.png` |
| `scripts/` | The search, download, scan, analysis and chart scripts |
| `METHOD.md` | The method, including every query and the precision checks |
| `CHANGELOG.md` | What changed between editions |

## Citation

If you use the data or the method, please cite:

```
Ali, M. B. (2026). The state of public agent skills and MCP servers, October 2026. https://github.com/basitalisandhu/agent-skills-state-2026
```

Or the BibTeX in [`CITATION.cff`](CITATION.cff).

## Licence

Data and text (the `data/` and `charts/` folders, this README and `METHOD.md`) are licensed under [CC BY 4.0](LICENSE-DATA). Code (the `scripts/` and `tests/` folders and the workflows) is licensed under the [MIT licence](LICENSE).
