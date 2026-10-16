# Querying the dataset

Worked examples against the committed October 2026 data, offline. Every output below is what the command prints on a fresh clone. Column meanings are in the [repository layout](../README.md#repository-layout) and [`METHOD.md`](../METHOD.md); the rule ids (`SSG401` and so on) are skill-scan-gate's.

You need `jq` for the first set and Python 3.12 (standard library only) for the second.

```sh
git clone https://github.com/basitalisandhu/agent-skills-state-2026
cd agent-skills-state-2026
```

## With jq, on `dataset.json`

`data/2026-10/dataset.json` is an array with one object per repository (2,999 of them).

**How many repositories configure a local MCP server, and how many leave one unpinned?** This is key finding 2.

```sh
jq '[.[] | select(.n_mcp_stdio > 0)] | {repos: length, unpinned: map(select(.any_unpinned_mcp)) | length}' data/2026-10/dataset.json
```

```json
{
  "repos": 346,
  "unpinned": 159
}
```

**Of those 159, how were they unpinned?** `SSG401` is an npm package through `npx` with no exact version, `SSG402` a Python package with no version, `SSG403` the `latest` tag. A repository can have more than one.

```sh
jq '[.[] | select(.n_mcp_stdio > 0 and .any_unpinned_mcp)]
    | {npm: map(select(.SSG401 > 0)) | length, python: map(select(.SSG402 > 0)) | length, latest: map(select(.SSG403 > 0)) | length}' \
  data/2026-10/dataset.json
```

```json
{
  "npm": 100,
  "python": 38,
  "latest": 63
}
```

**No `SECURITY.md`, by GitHub's primary language (top five).** `none` is a repository GitHub gives no language.

```sh
jq -r 'group_by(.language // "none")
       | map({lang: (.[0].language // "none"), n: length, no_sec: (map(select(.no_security_md)) | length)})
       | sort_by(-.n) | .[:5][] | "\(.lang)\t\(.n)\t\(.no_sec)"' data/2026-10/dataset.json
```

```text
Python	1090	897
TypeScript	540	395
none	328	303
JavaScript	326	272
Shell	219	194
```

## With Python, on `dataset.csv`

`data/2026-10/dataset.csv` holds the same rows. Booleans are the strings `True` and `False`.

**No `SECURITY.md` and no licence file, by the kind of file the repository was found by.** `found_by` lists every search that surfaced the repository, separated by `;`, so one repository can count under several kinds.

```python
import csv

rows = list(csv.DictReader(open("data/2026-10/dataset.csv", encoding="utf-8")))
kinds = {}
for r in rows:
    for k in r["found_by"].split(";"):
        g = kinds.setdefault(k, [0, 0, 0])
        g[0] += 1
        g[1] += r["no_security_md"] == "True"
        g[2] += r["no_licence_file"] == "True"
for k, (n, sec, lic) in sorted(kinds.items()):
    print(f"{k:16} {n:5}  no SECURITY.md {100*sec/n:5.1f}%  no licence {100*lic/n:5.1f}%")
```

```text
marketplace        352  no SECURITY.md  80.4%  no licence  22.2%
mcp_server_json    370  no SECURITY.md  59.2%  no licence  12.4%
plugin             437  no SECURITY.md  80.3%  no licence  16.0%
skill             1883  no SECURITY.md  87.0%  no licence  42.0%
```

**Unrestricted `Bash`, by the month the repository was created (last six months).** Only repositories with at least one `SKILL.md` count, the same denominator as key finding 4. October 2026 is a partial month (the sample was drawn on 13 October).

```python
import csv

rows = list(csv.DictReader(open("data/2026-10/dataset.csv", encoding="utf-8")))
by_month = {}
for r in rows:
    if int(r["n_skill_md"]) == 0:
        continue
    g = by_month.setdefault(r["created_at"][:7], [0, 0])
    g[0] += 1
    g[1] += r["any_unrestricted_bash"] == "True"
for month in sorted(by_month)[-6:]:
    n, bash = by_month[month]
    print(month, n, bash, f"{100*bash/n:.1f}%")
```

```text
2026-05 288 33 11.5%
2026-06 227 36 15.9%
2026-07 201 24 11.9%
2026-08 211 25 11.8%
2026-09 155 16 10.3%
2026-10 36 6 16.7%
```

Small groups like these move a lot from month to month; read them as a way into the data, not as findings.

**The headline numbers, straight from `stats.json`.**

```python
import json

s = json.load(open("data/2026-10/stats.json", encoding="utf-8"))
for k in ("no_security_md", "unpinned_mcp", "no_licence_file", "unrestricted_bash_repos", "yaml_reject_repos"):
    print(f"{k:24} {s[k]}")
```

```text
no_security_md           2459/2999 (82.0%)
unpinned_mcp             159/346 (46.0%)
no_licence_file          982/2999 (32.7%)
unrestricted_bash_repos  407/2621 (15.5%)
yaml_reject_repos        330/2621 (12.6%)
```

## Rebuild the published numbers and charts offline

The search, fetch and scan steps need the network and give a different sample each day, but the analysis steps can be re-run on the committed dataset. `stats.py` and `charts.py` read a working folder with an `out/` subfolder:

```sh
python3.12 -m venv .venv && . .venv/bin/activate
python -m pip install pyyaml==6.0.3 matplotlib
W=$(mktemp -d) && mkdir "$W/out"
cp data/2026-10/dataset.csv data/2026-10/precision.csv "$W/out/"
python scripts/stats.py "$W" > /dev/null
python scripts/charts.py "$W"
cmp "$W/out/chart-data.csv" data/2026-10/chart-data.csv && echo "chart data matches"
python - "$W" <<'PY'
import json, sys
a = json.load(open(f"{sys.argv[1]}/out/stats.json"))
b = json.load(open("data/2026-10/stats.json"))
print("stats.json matches" if a == b else [k for k in b if a.get(k) != b[k]])
PY
```

```text
ok
chart data matches
stats.json matches
```

`charts.py` needs `precision.csv` next to the dataset for the third chart; it is a hand-made input (see [`scripts/README.md`](../scripts/README.md#hand-made-inputs)). The rebuilt PNGs are in `$W/out/`.

The checks CI runs are the same as in [CONTRIBUTING.md](../CONTRIBUTING.md#set-up): `python scripts/check_numbers.py` and `python -m pytest -q tests`.
