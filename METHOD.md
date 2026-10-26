# Method: the state of public agent skills and MCP servers

Collected and scanned on 13 October 2026 by Muhammad Basit Ali (GitHub: basitalisandhu).

## 1. Corpus

**Source.** The GitHub REST code search API (`GET /search/code`), called through `gh api` with an authenticated account. Code search excludes forks by default.

**Queries.** 31 queries, each read for up to three pages of 100 results (93 requests in total, about nine seconds apart to stay under the code search limit of 10 requests per minute):

| Target | Query | Size bands |
|---|---|---|
| Agent skills | `filename:SKILL.md size:a..b` | 20 bands from 0 to 400,000 bytes |
| Plugin manifests | `filename:plugin.json path:.claude-plugin size:a..b` | 4 bands |
| Marketplace manifests | `filename:marketplace.json path:.claude-plugin size:a..b` | 3 bands |
| MCP registry manifests | `filename:server.json modelcontextprotocol size:a..b` | 4 bands |

Size bands exist because a single code search query returns at most 1,000 results. GitHub's reported totals (approximate) ran from 73,728 to 564,224 SKILL.md files per band, from 1,348 to 15,360 plugin manifests, 2,456 to 31,808 marketplace manifests and 1,136 to 11,040 server.json files. No request failed and no response was marked incomplete. Every band hit the 300-result read cap we set, so the corpus is **a sample, not a census**: it is weighted towards whatever GitHub's "best match" ordering puts first within each size band.

**Deduplication and exclusions.** 9,300 search hits resolved to 7,456 distinct repositories (by full name). None were forks; none belonged to basitalisandhu (excluded by rule). From that pool we drew a simple random sample of **3,000 repositories** (Python `random.sample`, seed 20261013). One repository timed out during fetch, leaving **2,999** in the dataset. Repository metadata (stars, owner type, dates, GitHub's licence detection and security-policy flag) came from the GraphQL API on the same day; none of the 2,999 had been deleted, 2 were archived.

**What the sample contains.** 2,621 repositories have at least one file named exactly `SKILL.md` (336,285 files in total; median 10 per repository; the largest 26 repositories hold 21.9% of all files). 1,047 have a `.claude-plugin/plugin.json`, 913 a `.claude-plugin/marketplace.json`, 399 a `server.json`, 401 a `.mcp.json`, 373 an agent hook configuration and 346 at least one stdio MCP server configuration. 2,512 of the 2,999 were created in 2026; the median star count is 4; 434 have 100 or more stars; 598 are owned by organisations.

## 2. Fetch

Each repository was cloned with `git clone --depth 1 --filter=blob:none --no-checkout`, then a non-cone sparse checkout of only: `**/SKILL.md`, `**/skills/**`, `**/.claude-plugin/**`, `**/hooks/hooks.json`, `**/hooks/*.{sh,py,js}`, `**/.mcp.json`, `**/server.json`, root licence files, and `SECURITY.md` at the root, `.github/` or `docs/`. Git hooks and LFS smudging were disabled. After checkout we deleted symbolic links, binaries and archives (by extension), any file over 1 MB, and anything beyond 3,000 files or 30 MB per repository; the `.git` folder was then removed. Nothing in a fetched repository was executed.

## 3. Tools and versions

| Tool | Version | Source | Used for |
|---|---|---|---|
| skill-scan-gate | 0.2.0, commit e53fdc8 | github.com/basitalisandhu/skill-scan-gate | 32 rules: unrestricted Bash, encoded blobs, secret shapes, hook commands, MCP pinning, manifests, SECURITY.md, licence |
| description_lint.py | claude-code-tooling-skills commit d5971fb | github.com/basitalisandhu/claude-code-tooling-skills | description length (limit set to 1,024), `Use when` sentence, YAML-safety flag |
| portability_check.py | same commit | same | recorded in the dataset only; not hand-checked, not reported |
| skill_inventory.py | same commit | same | hooks, hook scripts with network imports, MCP server list |
| mcp-tools-lint | 0.2.0, commit 8540f7c | github.com/basitalisandhu/mcp-tools-lint | committed `tools/list` JSON files only |
| PyYAML | 6.0.3 | PyPI | ground truth for "front matter fails YAML parsing" |
| Python, matplotlib, git, gh | 3.12, 3.11.2, 2.39.5, 2.92.0 | | runtime, charts, fetch, API |

skill-scan-gate ran with `--fail-on none` and its default blob threshold (200). mcp-tools-lint can start a server to read its tool list; we did not, because that means running untrusted code. It ran only on JSON files already committed in the fetched folders that hold a `tools` array with `inputSchema` (17 files in 10 repositories, 986 tools).

## 4. Measures

All measures are per repository and are columns in `dataset.csv`. Denominators: all 2,999 repositories for licence and security policy; the 2,621 with a SKILL.md for skill measures; the 346 with a stdio MCP server for pinning; the 373 with a hook configuration for hooks.

- **Unrestricted Bash:** skill-scan-gate SSG607 (`allowed-tools` grants `Bash` or `Bash(*)`).
- **Unpinned MCP server:** SSG401 (npm package without exact version), SSG402 (Python package without exact version), SSG403 (`latest` tag).
- **No security policy / no licence:** SSG701, SSG702, cross-checked with GitHub's `isSecurityPolicyEnabled` and licence detection.
- **Front matter fails YAML parsing:** PyYAML `safe_load` raises an error on the text between the opening and closing `---`. Files with no front matter are counted separately.
- **Description over 1,024 characters:** PyYAML-parsed `description` length; the linter's `description-too-long` is recorded alongside.
- **Network use in hooks (v3):** an agent hook command that runs `curl`, `wget` or PowerShell web cmdlets or names a non-local URL, or a script under a `hooks/` folder with a network import or call. Front-end React hooks (`.ts`, `.tsx`, `.jsx`, `use*` files) and parse-only or socket-only imports are excluded. Every flagged repository was then opened by hand and classed as remote, local-only, unclear or not a network call (`hook_network_review`).
- **Secret-shaped strings:** SSG405, SSG501, SSG502, SSG503 and JWTs inside SSG203 blobs. See section 6.

## 5. Precision

Where a rule could be checked against an independent source, we did so on every finding (automated cross-check). Otherwise we drew a random sample, one finding per repository, opened each file and judged the finding true or false against the rule's own claim. Secret findings were judged from structure only (key name, value length and entropy, placeholder words, file path); no secret value was displayed. Full table: `precision.csv`.

| Rule or measure | Check | n | Precision | Decision |
|---|---|---|---|---|
| SSG607 unrestricted Bash | hand | 10 | 100% | kept |
| SSG401 npm unpinned | hand | 5 | 100% | kept |
| SSG403 latest tag | hand | 5 | 100% | kept |
| SSG402 Python unpinned | hand | 12 | 75% | kept; false positives are `uv run` of the server's own project |
| SSG203 encoded blob | hand, all 9 repositories | 9 | 100% | kept; per-repository counts withheld |
| PyYAML front-matter failure | hand | 10 | 100% | kept; 8 of 10 caused by the description, usually an unquoted colon |
| SSG702 no licence file | automated vs GitHub, 5 disagreements opened | 982 | 99% | kept; misses `LICENSE-APACHE` style names |
| SSG701 no security policy | automated vs GitHub | 2,459 | 98% | kept; 39 have an organisation-level policy |
| description over 1,024 (linter) | automated vs PyYAML | 513 | 92% | kept |
| hook network, any host (v3) | hand, all flagged | 34 | 88% | kept |
| hook network, non-local host (v3) | hand, all flagged | 34 | 44% | below 70%: only the hand-verified count is reported |
| hook network (v1, before refinement) | hand | 10 | 30% | replaced by v3 |
| linter `description-no-use-when` | hand | 12 | 42% | dropped |
| wider when-to-use phrase list | hand | 7 | 43% | dropped |
| linter `yaml-unsafe` | automated vs PyYAML | 38,442 | 12% | below 70%: replaced by the PyYAML parse (it flags valid YAML the linter's subset does not accept, such as lists and multi-line values) |
| SSG405 literal secret in MCP config | hand, structure only | 11 | 55% | below 70%: not reported as prevalence |
| SSG503 hard-coded credential | hand, structure only | 12 | 8% | below 70%: not reported as prevalence |
| SSG502 provider token | hand, structure only | 10 | 0% | below 70%: not reported as prevalence |
| SSG501 private key block | hand, structure only | 8 | 0% | below 70%: not reported as prevalence |

In total 147 findings were judged by hand (each repository in the hook census counted once) and four rules were cross-checked against another source on every finding.

## 6. Secrets and disclosure

The secret rules fire in 471 of 2,999 repositories, almost always on documentation: detection regexes in secret scanners, placeholder tokens in setup guides, example responses. Their precision is too low to report a prevalence. Instead we triaged every finding by structure: dropped placeholders, templates, regexes, test and fixture paths, values that repeat across repositories or more than five times in one, research corpora of generated or deliberately poisoned skills, blockchain addresses, password hashes, values with sequential characters, expired JWTs and teaching examples in security skills. What remained is **30 possible live credentials in 17 repositories**. This is a structural triage, not a verification: no credential was tried against any service.

Those 30 are listed only in a private disclosure file (repository, file, line, rule, a 12-character SHA-256 prefix of the value, value length) that is kept outside this repository and was used to notify each owner before publication: 4 were documented test values or shortened examples; of the other 13, 2 owners were contacted by email and 11 received a short public notice with no location, since none had private vulnerability reporting enabled. The public `dataset.csv` omits per-repository counts for SSG203, SSG405, SSG501, SSG502 and SSG503 so that it cannot point at those repositories; their totals are in `secret_rules_aggregate.csv`, the only figures in the report that do not come from `dataset.csv`.

## 7. Limitations

- **Sample, not census.** Code search ordering decides which repositories surface; the pool of 7,456 is itself a slice of a much larger population, and the 3,000 are a random draw from that slice.
- **Young corpus.** 84% of the repositories were created in 2026 and the median has 4 stars; most are personal or experimental. The star-band chart shows how the picture changes with popularity.
- **Default branch, one commit.** Each repository is measured at its default-branch head on 13 October 2026.
- **Static only.** Nothing was executed, so tool schemas of running MCP servers, hook behaviour at run time and what a skill actually does were not observed.
- **Partial fetch.** Only agent-configuration paths were fetched. A licence or SECURITY.md in an unusual location is missed by SSG701 and SSG702 (the GitHub cross-check bounds this at about 1 to 2%).
- **Rules measure presence, not harm.** Unrestricted Bash or an unpinned server is a review prompt, not proof of a problem.
- **Repository-level counts treat a mirror of 10,000 skills and a single skill the same.** File-level counts are given where they matter.
- **Precision samples are small** for some rules (5 to 12); the figures carry wide uncertainty and say nothing about recall.
- **YAML strictness.** "Fails YAML parsing" means PyYAML 6.0.3 `safe_load` rejects it. Agent hosts may parse front matter more leniently or more strictly.

## 8. Files

In this repository, for this first edition: `data/2026-10/dataset.csv` and `data/2026-10/dataset.json` (one row per repository), `data/2026-10/precision.csv`, `data/2026-10/secret_rules_aggregate.csv`, `data/2026-10/chart-data.csv`, `data/2026-10/stats.json`, the three charts in `charts/`, and the scripts in `scripts/` (`collect.py`, `draw_sample.py`, `meta.py`, `fetch.py`, `scan.py`, `mcplint.py`, `hooknet.py`, `build.py`, `stats.py`, `charts.py`; `sample.py` and `secretsample.py` for the precision samples; `candidates.py`, `livecheck.py` and `secretfeat.py` for the private secret triage; `check_numbers.py` for CI). `scripts/README.md` explains how to rerun them.

## 9. Monthly runs

From November 2026 the study is re-run on the 1st of each month by `.github/workflows/monthly.yml`, which calls `scripts/run_month.py --month YYYY-MM`. It follows sections 1 to 4 with these differences:

- **Seed.** The sample seed is derived from the month as `YYYYMM01` (20261101 for November 2026). The October seed, 20261013, was the collection date.
- **Token.** Search and metadata use the workflow's `GITHUB_TOKEN`. Search requests are paced about seven seconds apart and wait for the rate limit window to reset when GitHub reports it used up; request counts and waiting time are recorded in the month's `stats.json` under `run`.
- **Tools.** The same versions as section 3: skill-scan-gate 0.2.0 at commit e53fdc8, claude-code-tooling-skills tag v0.1.1 (commit d5971fb), mcp-tools-lint 0.2.0 at commit 8540f7c, PyYAML 6.0.3.
- **Precision is not re-measured.** Section 5 applies to every month; `data/trend.csv` marks later months "precision not re-measured". Hooks are flagged with the v3 rule but not read by hand, so `hook_network_review` is empty and the hand-verified hook count is a first-edition figure only.
- **Secrets.** Secret-rule findings are reduced to per-rule counts in memory as soon as skill-scan-gate returns; no value, file, line or fingerprint is kept, per-repository secret columns stay out of the dataset, and no structural triage or disclosure is done. Clones are deleted once scanned and are never uploaded.
- **Output.** `data/YYYY-MM/` holds `dataset.csv`, `dataset.json`, `stats.json` and `secret_rules_aggregate.csv`; the same files are copied to `data/` as the latest month, and a row is written to `data/trend.csv`. `scripts/check_numbers.py --month YYYY-MM` checks the month before the pull request is opened.

## 10. Follow-up: tool annotations (version 1.1.0)

On 16 October 2026 the 399 repositories in this sample with a `server.json` were re-fetched at the commits in `data/2026-10/dataset.json`, source files only, and their tool registrations read statically for the four MCP tool hints. Nothing was run. The selection, extraction rules, name classes, intervals, hand check and limitations are in [`docs/mcp-tool-annotations.md`](docs/mcp-tool-annotations.md); the data is in `data/2026-10/annotations/`. It changes no number in sections 1 to 9.

## 11. Follow-up: README install pins (version 1.2.0)

On 20 October 2026 the same 399 repositories were re-fetched at the commits in `data/2026-10/dataset.json`, README and `server.json` files only, and every launch command in their READMEs (`npx`, `bunx`, `pnpm dlx`, `yarn dlx`, `uvx`, `uv tool run`, `pipx run`, `docker run`) was classed as exact, range, latest or unpinned. Nothing was run. The selection, patterns, exclusions, version classes, intervals, hand check and limitations are in [`docs/mcp-readme-install-pins.md`](docs/mcp-readme-install-pins.md); the data is in `data/2026-10/readme-pins/`. It changes no number in sections 1 to 10.

## 12. Follow-up: what skills with unscoped Bash do (version 1.3.0)

On 26 October 2026, 400 of the 407 repositories with `any_unrestricted_bash` true were re-fetched at the commits in `data/2026-10/dataset.json`, `SKILL.md` files and the files bundled with up to 20 unscoped-Bash skills a repository only, and each skill's shell commands, distinct command heads and nine riskier behaviours were read statically. Nothing was run. The selection, rules, intervals, hand check and limitations are in [`docs/skills-with-unscoped-bash.md`](docs/skills-with-unscoped-bash.md); the data is in `data/2026-10/skill-bash/`. It changes no number in sections 1 to 11.
