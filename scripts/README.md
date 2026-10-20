# Scripts

These are the scripts that produced the dataset, plus `check_numbers.py`, which CI runs. They use Python 3.12 and the standard library, except `scan.py` (PyYAML) and `charts.py` (matplotlib).

**A rerun gives a different sample.** GitHub code search results change every day, so the same queries and the same seed draw different repositories. What reproduces is the method; expect the shares to move by a few points, not the exact numbers in this report.

## Working folder

Every script takes a working folder (`W` below) as its first argument. Set it up once:

```sh
W=$HOME/skills-state && mkdir -p "$W/raw" "$W/out" "$W/tools" "$W/bin"
cp scripts/*.py "$W/bin/"
python3.12 -m venv "$W/venv"
"$W/venv/bin/pip" install pyyaml matplotlib git+https://github.com/basitalisandhu/skill-scan-gate
git clone https://github.com/basitalisandhu/claude-code-tooling-skills "$W/tools/claude-code-tooling-skills"
git clone https://github.com/basitalisandhu/mcp-tools-lint "$W/tools/mcp-tools-lint"
(cd "$W/tools/mcp-tools-lint" && npm ci && npm run build)
```

`build.py` imports `hooknet.py` from `$W/bin`, which is why the scripts are copied there. The method used skill-scan-gate 0.2.0 (commit e53fdc8), claude-code-tooling-skills commit d5971fb and mcp-tools-lint 0.2.0 (commit 8540f7c); check out those commits to match it. You need the GitHub CLI (`gh`) signed in for the search and metadata steps.

## Steps

```sh
PY="$W/venv/bin/python"

# 1. Search: 31 code search queries, 93 requests, about 15 minutes at the rate limit
$PY "$W/bin/collect.py" "$W/raw"

# 2. Sample: distinct non-fork repositories, random draw of 3,000 with seed 20261013
$PY "$W/bin/draw_sample.py" "$W" 3000 20261013

# 3. Fetch: metadata from the GraphQL API, then a sparse clone of agent configuration files only
$PY "$W/bin/meta.py" "$W/raw/sample.txt" "$W/raw/meta.jsonl"
$PY "$W/bin/fetch.py" "$W" "$W/raw/sample.txt"

# 4. Scan: skill-scan-gate, the description linter, inventory, portability, YAML parse; then committed MCP tool lists
$PY "$W/bin/scan.py" "$W"
$PY "$W/bin/mcplint.py" "$W"

# 5. Analyse: dataset, headline numbers, charts
$PY "$W/bin/build.py" "$W"
$PY "$W/bin/stats.py" "$W"
$PY "$W/bin/charts.py" "$W"
```

Nothing in a fetched repository is executed: `fetch.py` disables Git hooks, LFS smudging and symbolic links, and `mcplint.py` lints only JSON files already committed, without starting any server.

## Hand-made inputs

Three inputs come from reading findings by hand, as described in `METHOD.md`:

- `raw/hook_review.csv`: a header line, then one `folder,verdict` line for each repository that `hooknet.py` flags, where the verdict is `remote`, `local`, `unclear` or `not-network`. `build.py` reads it.
- `out/precision.csv`: the precision table. `sample.py RULE K SEED` and `secretsample.py RULE K SEED` print a random sample of findings to judge, one per repository; secret values are never printed.
- `raw/secret_triage.json`: the structural secret triage. `candidates.py` writes `raw/secret_candidates.json`; `livecheck.py` reads it as `raw/secret_candidates2.json` after review and writes `raw/secret_triage.json`. Neither prints a secret value. `build.py` uses only the total from this file; the file itself, which names repositories, must stay private.

## Monthly run

`run_month.py` runs every step above for one month in one command, with the pinned tool versions, and writes `data/YYYY-MM/`, the latest copies in `data/` and a row of `data/trend.csv`. It clones the two tool repositories into its working folder if they are missing; skill-scan-gate must be installed (`pip install "skill-scan-gate @ git+https://github.com/basitalisandhu/skill-scan-gate@e53fdc85c6be03f3e74dcf842a7b6892bfbea0de"`).

```sh
export GITHUB_TOKEN=...                              # never printed or written by the script
python scripts/run_month.py --month 2026-11 --limit 30   # dry run: 4 search requests, 30 repositories, temporary output
python scripts/run_month.py --month 2026-11              # full run, as the monthly workflow does
python scripts/check_numbers.py --month 2026-11
python scripts/plot_trend.py                         # charts/trend.png from data/trend.csv
```

Its pure parts are tested in `tests/test_run_month.py` (`python -m pytest -q tests`).

## Checking the published numbers

```sh
python3 scripts/check_numbers.py
```

For every month folder and for the latest copies in `data/`, it checks that `dataset.csv` and `dataset.json` have the row count in `stats.json`, the columns the analysis needs and none of the withheld secret-rule columns, and that the month's row in `data/trend.csv` matches. It also checks that the top-level files are copies of the latest month and that every number in the README's "Key findings" list matches `data/2026-10/stats.json`. CI runs it, and the tests, on every push and pull request.

## Follow-up: MCP tool annotations

`annotations_fetch.py` and `annotations.py` produce [`docs/mcp-tool-annotations.md`](../docs/mcp-tool-annotations.md) from the committed October 2026 dataset. Standard library only; the fetch needs `git` and network access, the analysis needs neither.

```sh
python scripts/annotations_fetch.py /tmp/ann       # re-fetch the 399 server.json repositories at their dataset commits
python scripts/annotations.py /tmp/ann             # write data/2026-10/annotations/{results.json,tools.csv,repos.csv}
python -m pytest -q tests/test_annotations.py      # offline, fixtures only
```

`hand-check.csv` in the same folder is written by hand, not by the script.

## Follow-up: README install pins

`readme_pins_fetch.py` and `readme_pins.py` produce [`docs/mcp-readme-install-pins.md`](../docs/mcp-readme-install-pins.md) from the same 399 repositories. Standard library only; the fetch needs `git` and network access, the analysis needs neither.

```sh
python scripts/readme_pins_fetch.py /tmp/pins      # re-fetch READMEs and server.json files at the dataset commits
python scripts/readme_pins.py /tmp/pins            # write data/2026-10/readme-pins/{results.json,commands.csv,repos.csv}
python -m pytest -q tests/test_readme_pins.py      # offline, fixtures only
```

`hand-check.csv` in the same folder is written by hand from the sample rows listed in `results.json`.
