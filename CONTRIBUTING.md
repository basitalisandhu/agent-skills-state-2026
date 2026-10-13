# Contributing

Thanks for considering a contribution. This is a research dataset, so the most useful contributions are corrections: a number that does not match the data, a repository that was measured wrongly, a step in [METHOD.md](METHOD.md) that is unclear or unsound, or a scan that should have been counted differently.

## Reporting a correction

Open an issue with:

- the claim or number, with the file and line (for example a row in `data/2026-10/dataset.csv` or a sentence in the README);
- what you believe is correct and the evidence (a link to the repository file, or the command that shows it);
- whether it changes a headline number.

A confirmed correction to published numbers is made in the data, recorded in [CHANGELOG.md](CHANGELOG.md) and noted in the README. Numbers are never edited silently.

## Set up

Requires Python 3.12. The checks used in CI run with:

```bash
git clone https://github.com/basitalisandhu/agent-skills-state-2026
cd agent-skills-state-2026
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install pytest==9.1.1 pyyaml==6.0.3
python3 scripts/check_numbers.py
python3 -m pytest -q tests
```

`scripts/check_numbers.py` verifies that the dataset shape and every number in the README key findings match `data/*/stats.json`.

## Before you open a pull request

- Change data and text together: if a row in a dataset file changes, regenerate `stats.json` and the charts with the scripts in `scripts/` and update the README so `check_numbers.py` passes.
- Do not add a new measure without describing it in `METHOD.md`, including its denominator and how its precision was checked.
- Monthly results arrive as pull requests from the scheduled workflow. Review those like any other change: the sample, the pinned scanner versions and the trend row should all be present.
- Keep the prose plain: say what was measured, in how many repositories, and what the limits are.

## Style

- Scripts use the standard library where possible; charts use matplotlib.
- Output is deterministic for a given seed. The sample seed for a month is `YYYYMM01`.
- Never commit a credential, even a revoked one. Secret findings are stored as counts by rule, never as values.

## Reporting security issues

See [SECURITY.md](SECURITY.md).
