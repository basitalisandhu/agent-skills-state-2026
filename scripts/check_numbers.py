"""Check the published datasets, the trend file and the README's key findings.

Usage: python scripts/check_numbers.py [--month YYYY-MM]

Standard library only. Exit code 0 when everything matches, 1 otherwise.

Checks, for every data/YYYY-MM/ folder (or only --month) and for the latest copies in data/:
1. dataset.csv and dataset.json each have stats["repos"] rows and the same columns.
2. The columns the analysis needs are present, and no per-repository column exists for the
   secret rules whose counts are withheld (SSG203, SSG405, SSG501, SSG502, SSG503).
3. The month's row in data/trend.csv matches its stats.json.
4. data/dataset.csv, dataset.json, stats.json and secret_rules_aggregate.csv are copies of the latest month.
5. In the README's "Key findings" section (the first edition's text), every "A of B (C%)" matches a
   fraction in data/2026-10/stats.json, and every other number appears somewhere in it.
"""
import argparse
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
FIRST_EDITION = "2026-10"
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
LATEST_FILES = ("dataset.csv", "dataset.json", "stats.json", "secret_rules_aggregate.csv")
TREND_FRACTIONS = ("no_security_md", "unpinned_mcp", "unpinned_mcp_latest", "no_licence_file", "unrestricted_bash_repos",
                   "yaml_reject_repos", "no_front_matter_repos", "desc_over_1024_repos")
WITHHELD = ("SSG203", "SSG405", "SSG501", "SSG502", "SSG503")
REQUIRED = [
    "repo", "commit", "stars", "owner_type", "created_at", "github_licence_spdx", "github_security_policy",
    "n_skill_md", "has_plugin_json", "has_marketplace_json", "has_server_json", "has_mcp_json",
    "n_hooks", "n_mcp_stdio", "SSG401", "SSG402", "SSG403", "SSG601", "SSG606", "SSG607",
    "n_skill_yaml_reject", "n_skill_no_front_matter", "n_skill_desc_over_1024", "n_skill_with_desc",
    "n_portability_findings", "any_unrestricted_bash", "hook_network_flag", "hook_network_review",
    "any_unpinned_mcp", "no_licence_file", "no_security_md", "any_yaml_reject", "any_desc_over_1024",
]
FRACTION = re.compile(r"^(\d+)/(\d+) \((\d+(?:\.\d+)?)%\)$")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
CLAIM = re.compile(r"(\d[\d,]*) of (\d[\d,]*) \((\d+(?:\.\d+)?)%\)")


def num(s):
    return float(s.replace(",", ""))


def stats_numbers(stats):
    """Return (fractions, numbers): every a/b (p%) triple and every number found in stats.json."""
    fractions, numbers = set(), set()

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            numbers.add(float(v))
        elif isinstance(v, str):
            m = FRACTION.match(v)
            if m:
                fractions.add((num(m.group(1)), num(m.group(2)), num(m.group(3))))
            for n in NUMBER.findall(v):
                numbers.add(num(n))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(stats)
    return fractions, numbers


def key_findings(readme):
    m = re.search(r"^## Key findings\s*$(.*?)^## ", readme, re.S | re.M)
    if not m:
        return None
    return [ln for ln in m.group(1).splitlines() if ln.startswith("- ")]


def check_dataset(folder, label):
    """Shape checks for one data folder: row counts, columns, no withheld secret-rule columns."""
    errors = []
    stats = json.load(open(os.path.join(folder, "stats.json"), encoding="utf-8"))
    with open(os.path.join(folder, "dataset.csv"), newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        rows = list(reader)
    js = json.load(open(os.path.join(folder, "dataset.json"), encoding="utf-8"))
    if len(rows) != stats["repos"]:
        errors.append(f"{label}: dataset.csv has {len(rows)} rows, stats.json says {stats['repos']}")
    if len(js) != stats["repos"]:
        errors.append(f"{label}: dataset.json has {len(js)} rows, stats.json says {stats['repos']}")
    if js and list(js[0].keys()) != columns:
        errors.append(f"{label}: dataset.json keys differ from dataset.csv columns")
    if len({r["repo"] for r in rows}) != len(rows):
        errors.append(f"{label}: dataset.csv has duplicate repositories")
    for c in REQUIRED:
        if c not in columns:
            errors.append(f"{label}: dataset.csv is missing column {c}")
    for c in columns:
        if any(w in c for w in WITHHELD):
            errors.append(f"{label}: dataset.csv has withheld secret-rule column {c}")
    if sum(1 for r in rows if int(r["n_skill_md"] or 0) > 0) != stats["repos_with_skills"]:
        errors.append(f"{label}: repositories with skills in dataset.csv do not match stats.json")
    agg = os.path.join(folder, "secret_rules_aggregate.csv")
    if os.path.exists(agg):
        head = open(agg, encoding="utf-8").readline().strip()
        if head != "rule,findings,repositories_with_finding,repositories_scanned":
            errors.append(f"{label}: secret_rules_aggregate.csv has unexpected columns")
    return errors, len(rows), len(columns)


def check_trend(month, stats):
    """The month's row in data/trend.csv must carry the same numbers as its stats.json."""
    path = os.path.join(DATA, "trend.csv")
    if not os.path.exists(path):
        return ["data/trend.csv is missing"]
    rows = [r for r in csv.DictReader(open(path, newline="", encoding="utf-8")) if r["month"] == month]
    if len(rows) != 1:
        return [f"data/trend.csv has {len(rows)} rows for {month}, expected 1"]
    r, errors = rows[0], []
    for k in ("repos", "repos_with_skills", "repos_with_stdio_mcp", "repos_with_hooks", "skill_md_total"):
        if num(r[k]) != float(stats[k]):
            errors.append(f"data/trend.csv {month} {k} is {r[k]}, stats.json says {stats[k]}")
    for k in TREND_FRACTIONS:
        m = FRACTION.match(stats[k])
        if not m or (num(r[k]), num(r[k + "_pct"])) != (num(m.group(1)), num(m.group(3))):
            errors.append(f"data/trend.csv {month} {k} does not match stats.json")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check the published datasets, trend and key findings.")
    ap.add_argument("--month", help="check only this month's folder (plus the latest copies and the README)")
    a = ap.parse_args(argv)
    errors, notes = [], []
    months = sorted(m for m in os.listdir(DATA) if MONTH.match(m) and os.path.isdir(os.path.join(DATA, m)))
    if FIRST_EDITION not in months:
        errors.append(f"data/{FIRST_EDITION}/ is missing")
    if a.month and a.month not in months:
        errors.append(f"data/{a.month}/ is missing")
    for m in ([a.month] if a.month else months):
        if m not in months:
            continue
        e, n, c = check_dataset(os.path.join(DATA, m), f"data/{m}")
        errors += e
        errors += check_trend(m, json.load(open(os.path.join(DATA, m, "stats.json"), encoding="utf-8")))
        notes.append(f"data/{m}: {n} rows, {c} columns")
    e, n, c = check_dataset(DATA, "data")
    errors += e
    if months:
        latest = months[-1]
        for fn in LATEST_FILES:
            top, src = os.path.join(DATA, fn), os.path.join(DATA, latest, fn)
            if not os.path.exists(src) or open(top, "rb").read() != open(src, "rb").read():
                errors.append(f"data/{fn} is not a copy of data/{latest}/{fn} (the latest month)")
        notes.append(f"data/: copy of {latest}")

    # The README's key findings are the first edition's text: check them against that month.
    stats = json.load(open(os.path.join(DATA, FIRST_EDITION, "stats.json"), encoding="utf-8"))
    findings = key_findings(open(os.path.join(ROOT, "README.md"), encoding="utf-8").read())
    if not findings:
        errors.append("README has no '## Key findings' list")
        findings = []
    fractions, numbers = stats_numbers(stats)
    checked = 0
    for line in findings:
        rest = line
        for x, y, p in CLAIM.findall(line):
            checked += 1
            if (num(x), num(y), num(p)) not in fractions:
                errors.append(f"'{x} of {y} ({p}%)' is not in data/{FIRST_EDITION}/stats.json: {line[:80]}")
            rest = rest.replace(f"{x} of {y} ({p}%)", " ")
        for v in NUMBER.findall(rest):
            checked += 1
            if num(v) not in numbers:
                errors.append(f"number {v} is not in data/{FIRST_EDITION}/stats.json: {line[:80]}")

    for e in errors:
        print("FAIL:", e)
    if errors:
        return 1
    print("OK: " + "; ".join(notes) + f"; no withheld columns; {checked} numbers in {len(findings)} key findings "
          f"match data/{FIRST_EDITION}/stats.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
