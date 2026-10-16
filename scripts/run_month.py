"""Run the whole monthly index pipeline: search, sample, fetch, scan and analyse, for one month.

Usage:
    python scripts/run_month.py --month YYYY-MM [--work DIR] [--limit N] [--out DIR]

Needs GITHUB_TOKEN (or GH_TOKEN) in the environment for the code search and GraphQL calls. The
token is read once, sent only to api.github.com and never written, logged or passed to a child
process.

Steps, matching METHOD.md:
1. Search: the 31 code search queries of the first edition, three pages each, about seven seconds
   apart and waiting for the rate limit window to reset when GitHub says it is used up.
2. Sample: distinct non-fork repositories, excluding the author's own, sorted by name, then a
   random draw of 3,000 with a seed derived from the month (YYYYMM01).
3. Metadata from the GraphQL API, then a shallow, sparse, size-capped clone of agent configuration
   files only. Nothing in a fetched repository is executed.
4. Scan with the pinned tools (see TOOLS). Secret-rule findings are reduced to counts in memory as
   soon as skill-scan-gate returns; no value, file, line or fingerprint of a secret finding is kept.
   Each clone is deleted as soon as it has been scanned.
5. Analyse into data/YYYY-MM/: dataset.csv, dataset.json, stats.json, secret_rules_aggregate.csv.
   Precision is not re-measured and hooks are not hand-reviewed; the October 2026 precision applies
   and the trend notes say so. The month's files are copied to data/ as the latest month and its
   row is written to data/trend.csv.

--limit N is a dry run: one page of one query per kind, N repositories, output to a temporary
folder (or --out), and nothing in data/ is touched.
"""
import argparse
import collections
import concurrent.futures as cf
import csv
import datetime
import http.client
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
from hooknet import v3  # noqa: E402

FIRST_EDITION = "2026-10"
SAMPLE_SIZE = 3000
EXCLUDE_OWNERS = {"basitalisandhu"}
MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
PRIVATE_RULES = ("SSG203", "SSG405", "SSG501", "SSG502", "SSG503")  # per-repository counts withheld
SECRET_RULES = ("SSG405", "SSG501", "SSG502", "SSG503")
LATEST_FILES = ("dataset.csv", "dataset.json", "stats.json", "secret_rules_aggregate.csv")
PRECISION_NOTE = "precision not re-measured; October 2026 precision applies"

TOOLS = {
    "skill-scan-gate": {"version": "0.2.0", "commit": "e53fdc85c6be03f3e74dcf842a7b6892bfbea0de",
                        "repo": "https://github.com/basitalisandhu/skill-scan-gate"},
    "claude-code-tooling-skills": {"tag": "v0.1.1", "commit": "d5971fb609ce00c091fb0f538bf14150ba387455",
                                   "repo": "https://github.com/basitalisandhu/claude-code-tooling-skills"},
    "mcp-tools-lint": {"version": "0.2.0", "commit": "8540f7cb4cef023dc2f55f4af1c7e83278fc7346",
                       "repo": "https://github.com/basitalisandhu/mcp-tools-lint"},
}

# Fetch settings, as in fetch.py
PATTERNS = ["**/SKILL.md", "**/skills/**", "**/.claude-plugin/**", "**/hooks/hooks.json", "**/hooks/*.sh", "**/hooks/*.py",
            "**/hooks/*.js", "**/.mcp.json", "**/server.json", "/LICENSE*", "/LICENCE*", "/COPYING*", "/license*",
            "/SECURITY.md", "/security.md", "/.github/SECURITY.md", "/docs/SECURITY.md"]
BIN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".jar",
           ".whl", ".exe", ".dll", ".so", ".dylib", ".bin", ".mp4", ".mp3", ".wav", ".mov", ".woff", ".woff2", ".ttf",
           ".otf", ".psd", ".xlsx", ".docx", ".pptx", ".skill", ".pyc", ".class", ".o", ".a", ".node", ".wasm",
           ".sqlite", ".db", ".parquet", ".npy", ".pkl", ".pt", ".onnx"}
CAP_FILE_BYTES = 1_000_000
CAP_FILES = 3000
CAP_BYTES = 30_000_000

# Scan settings, as in scan.py and build.py
NET = re.compile(r"\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|nc|ncat|scp|rsync|ssh)\b|https?://|\bfetch\(|"
                 r"requests\.(get|post)|urllib|http\.client|axios", re.I)
FM = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(\r?\n|\Z)", re.S)
BROAD_WHEN = re.compile(r"\b(use (this|it|me)?\s*(skill\s*)?(when|whenever|if|for|to)|when (the )?(user|you|asked|working|"
                        r"needing|someone)|whenever|trigger(s|ed)? (on|when)|invoke when|activate when|applies when|use cases?:)", re.I)
RULES = ["SSG101", "SSG102", "SSG103", "SSG104", "SSG201", "SSG202", "SSG203", "SSG204", "SSG301", "SSG302", "SSG303",
         "SSG304", "SSG305", "SSG306", "SSG401", "SSG402", "SSG403", "SSG404", "SSG405", "SSG406", "SSG501", "SSG502",
         "SSG503", "SSG601", "SSG602", "SSG603", "SSG604", "SSG605", "SSG606", "SSG607", "SSG701", "SSG702"]
DLR = ["yaml-unsafe", "description-too-long", "description-no-use-when", "description-missing", "front-matter-missing",
       "front-matter-unclosed", "name-missing", "name-mismatch", "name-format"]

TREND_FIELDS = [
    "month", "collected_on", "seed", "search_requests", "search_hits", "pool_repos", "sampled", "repos",
    "repos_with_skills", "repos_with_stdio_mcp", "repos_with_hooks", "skill_md_total",
    "no_security_md", "no_security_md_pct", "unpinned_mcp", "unpinned_mcp_pct",
    "unpinned_mcp_latest", "unpinned_mcp_latest_pct", "no_licence_file", "no_licence_file_pct",
    "unrestricted_bash_repos", "unrestricted_bash_repos_pct", "yaml_reject_repos", "yaml_reject_repos_pct",
    "no_front_matter_repos", "no_front_matter_repos_pct", "desc_over_1024_repos", "desc_over_1024_repos_pct",
    "hook_flag_in_hook_repos", "secret_rule_repos", "precision", "notes",
]
TREND_FRACTIONS = ("no_security_md", "unpinned_mcp", "unpinned_mcp_latest", "no_licence_file", "unrestricted_bash_repos",
                   "yaml_reject_repos", "no_front_matter_repos", "desc_over_1024_repos")
FRACTION = re.compile(r"^(\d+)/(\d+) \((\d+(?:\.\d+)?)%\)$")


# ---------------------------------------------------------------- pure parts (tested)

def parse_month(month):
    m = MONTH.match(month or "")
    if not m:
        raise ValueError(f"month must look like YYYY-MM, got {month!r}")
    return int(m.group(1)), int(m.group(2))


def derive_seed(month):
    """The sampling seed for a month: YYYYMM01 as an integer (2026-11 gives 20261101)."""
    y, m = parse_month(month)
    return y * 10000 + m * 100 + 1


def search_queries():
    """The 31 code search queries of the first edition: (kind, query, pages)."""
    q = []
    for a, b in [(0, 300), (301, 600), (601, 900), (901, 1200), (1201, 1500), (1501, 1800), (1801, 2100), (2101, 2500),
                 (2501, 3000), (3001, 3500), (3501, 4000), (4001, 4700), (4701, 5500), (5501, 6500), (6501, 8000),
                 (8001, 10000), (10001, 13000), (13001, 17000), (17001, 25000), (25001, 400000)]:
        q.append(("skill", f"filename:SKILL.md size:{a}..{b}", 3))
    for a, b in [(0, 400), (401, 800), (801, 1500), (1501, 400000)]:
        q.append(("plugin", f"filename:plugin.json path:.claude-plugin size:{a}..{b}", 3))
    for a, b in [(0, 1000), (1001, 3000), (3001, 400000)]:
        q.append(("marketplace", f"filename:marketplace.json path:.claude-plugin size:{a}..{b}", 3))
    for a, b in [(0, 800), (801, 1500), (1501, 3000), (3001, 400000)]:
        q.append(("mcp_server_json", f"filename:server.json modelcontextprotocol size:{a}..{b}", 3))
    return q


def dry_run_queries():
    """One page of the first query of each kind, for --limit."""
    seen, out = set(), []
    for kind, q, _ in search_queries():
        if kind not in seen:
            seen.add(kind)
            out.append((kind, q, 1))
    return out


def draw_sample(items, n, seed, exclude_owners=EXCLUDE_OWNERS):
    """Return (pool_size, [(repo, kinds)]): a seeded random draw of n distinct non-fork repositories.

    items are dicts with repo, owner, fork and kind. The pool is sorted before sampling, so the same
    items and seed always give the same draw, whatever order the items arrived in.
    """
    excl = {o.lower() for o in exclude_owners}
    kinds = {}
    for it in items:
        if it.get("fork") or str(it.get("owner", "")).lower() in excl:
            continue
        kinds.setdefault(it["repo"], set()).add(it["kind"])
    pool = sorted(kinds)
    picked = sorted(random.Random(seed).sample(pool, min(n, len(pool))))
    return len(pool), [(r, sorted(kinds[r])) for r in picked]


def reduce_secret_findings(ssg):
    """Split a skill-scan-gate result into a copy without private-rule findings, and their counts.

    Nothing from a private-rule finding (evidence, file, line, fingerprint) survives: only the rule
    name is counted. The input is not modified.
    """
    if not isinstance(ssg, dict):
        return {"_error": "no result"}, collections.Counter()
    counts = collections.Counter()
    public = []
    for f in ssg.get("findings", []) or []:
        rule = f.get("rule") if isinstance(f, dict) else None
        if rule in PRIVATE_RULES:
            counts[rule] += 1
        elif rule:
            public.append({k: f.get(k) for k in ("rule", "file", "line")})
    out = {k: v for k, v in ssg.items() if k in ("tool", "version", "filesScanned", "_error")}
    out["findings"] = public
    return out, counts


def secret_aggregate(per_repo_counts, n_repos):
    """Rows for secret_rules_aggregate.csv from a list of per-repository Counters (counts only)."""
    rows = []
    for r in PRIVATE_RULES:
        rows.append([r, sum(c.get(r, 0) for c in per_repo_counts), sum(c.get(r, 0) > 0 for c in per_repo_counts), n_repos])
    rows.append(["any of SSG405/SSG501/SSG502/SSG503", sum(c.get(r, 0) for c in per_repo_counts for r in SECRET_RULES),
                 sum(any(c.get(r, 0) for r in SECRET_RULES) for c in per_repo_counts), n_repos])
    return rows


def build_row(rec, meta, kinds):
    """One dataset row from a scan record, mirroring build.py. Hooks are flagged but not hand-reviewed."""
    m = meta or {}
    inv = rec["inventory"] if isinstance(rec.get("inventory"), dict) else {}
    ssg = rec["ssg"] if isinstance(rec.get("ssg"), dict) else {}
    rc = collections.Counter(f["rule"] for f in ssg.get("findings", []))
    rc.update(rec.get("secret_counts", {}))
    dl = rec.get("desc_lint") if isinstance(rec.get("desc_lint"), dict) else {}
    per_skill = collections.defaultdict(set)
    for s in dl.get("skills", []):
        for f in s.get("findings", []):
            per_skill[f["rule"]].add(s.get("file"))
    y = rec.get("yaml", [])
    mcp = inv.get("mcp_servers", [])
    stdio = [s for s in mcp if s.get("type") in ("stdio", "") and s.get("command")]
    port = rec["portability"].get("findings", []) if isinstance(rec.get("portability"), dict) else []
    hooks = inv.get("hooks", [])
    ml = rec.get("mcplint", {"lists": 0, "tools": 0, "dialect": 0, "no_annotations": 0})
    pres = rec.get("present", {})
    row = {
        "repo": rec["fetched"]["repo"], "commit": rec["fetched"]["sha"], "found_by": ";".join(sorted(kinds or [])),
        "stars": m.get("stargazerCount"), "owner_type": (m.get("owner") or {}).get("__typename"), "archived": m.get("isArchived"),
        "created_at": m.get("createdAt"), "pushed_at": m.get("pushedAt"), "language": (m.get("primaryLanguage") or {}).get("name"),
        "github_licence_spdx": (m.get("licenseInfo") or {}).get("spdxId"), "github_security_policy": m.get("isSecurityPolicyEnabled"),
        "files_fetched": rec["fetched"]["files"], "bytes_fetched": rec["fetched"]["bytes"],
        "n_skill_md": len(y), "has_plugin_json": pres.get("plugin.json", False),
        "has_marketplace_json": pres.get("marketplace.json", False), "has_server_json": pres.get("server.json", False),
        "has_mcp_json": pres.get(".mcp.json", False), "has_hooks_json": pres.get("hooks.json", False),
        "n_hooks": len(hooks), "n_mcp_servers": len(mcp), "n_mcp_stdio": len(stdio),
        "ssg_total_public_rules": sum(v for k, v in rc.items() if k not in PRIVATE_RULES), "ssg_error": "_error" in ssg,
    }
    for r in RULES:
        if r not in PRIVATE_RULES:
            row[r] = rc.get(r, 0)
    for r in DLR:
        row["dl_" + r] = len(per_skill.get(r, ()))
    row["n_skills_linted"] = len(dl.get("skills", []))
    row["n_skill_yaml_reject"] = sum(1 for s in y if s["yaml"] == "reject")
    row["n_skill_no_front_matter"] = sum(1 for s in y if s["yaml"] == "no-front-matter")
    row["n_skill_desc_over_1024"] = sum(1 for s in y if (s["desc_len"] or 0) > 1024)
    row["n_skill_with_desc"] = sum(1 for s in y if s["has_desc"])
    row["n_skill_no_broad_when"] = sum(1 for s in y if s["has_desc"] and not s["broad_when"])
    row["n_portability_findings"] = len(port)
    row["any_unrestricted_bash"] = rc["SSG607"] > 0
    row["mcp_tool_lists_linted"] = ml["lists"]
    row["mcp_tools_linted"] = ml["tools"]
    row["mcp_tools_dialect_error"] = ml["dialect"]
    row["mcp_tools_no_annotations"] = ml["no_annotations"]
    row["hook_network_flag"] = bool(v3({"inventory": inv, "hook_scripts_net": rec.get("hook_scripts_net", [])}))
    row["hook_network_review"] = ""  # hand review is part of the first edition only
    row["any_unpinned_mcp"] = (rc["SSG401"] + rc["SSG402"] + rc["SSG403"]) > 0
    row["no_licence_file"] = rc["SSG702"] > 0
    row["no_security_md"] = rc["SSG701"] > 0
    row["any_yaml_reject"] = row["n_skill_yaml_reject"] > 0
    row["any_yaml_unsafe_flag"] = row["dl_yaml-unsafe"] > 0
    row["any_desc_over_1024"] = row["n_skill_desc_over_1024"] > 0
    row["any_no_use_when"] = row["dl_description-no-use-when"] > 0
    row["any_no_broad_when"] = row["n_skill_no_broad_when"] > 0
    return row


def split_fraction(s):
    m = FRACTION.match(str(s))
    if not m:
        raise ValueError(f"not an 'a/b (p%)' value: {s!r}")
    return int(m.group(1)), int(m.group(2)), float(m.group(3))


def trend_row(month, stats, run):
    """One row of data/trend.csv from a month's stats.json and its run details."""
    row = {"month": month, "collected_on": run.get("collected_on", ""), "seed": run.get("seed", ""),
           "search_requests": run.get("search_requests", ""), "search_hits": run.get("search_hits", ""),
           "pool_repos": run.get("pool_repos", ""), "sampled": run.get("sampled", ""), "repos": stats["repos"],
           "repos_with_skills": stats["repos_with_skills"], "repos_with_stdio_mcp": stats["repos_with_stdio_mcp"],
           "repos_with_hooks": stats["repos_with_hooks"], "skill_md_total": stats["skill_md_total"]}
    for k in TREND_FRACTIONS:
        a, _, p = split_fraction(stats[k])
        row[k] = a
        row[k + "_pct"] = p
    row["hook_flag_in_hook_repos"] = split_fraction(stats["hook_flag_in_hook_repos"])[0]
    row["secret_rule_repos"] = run.get("secret_rule_repos", "")
    row["precision"] = run.get("precision", PRECISION_NOTE)
    row["notes"] = run.get("notes", "")
    return row


def read_trend(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_trend(path, rows):
    rows = sorted(rows, key=lambda r: r["month"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TREND_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TREND_FIELDS})


def upsert_trend(path, row):
    rows = [r for r in read_trend(path) if r["month"] != row["month"]] + [row]
    write_trend(path, rows)


# ---------------------------------------------------------------- GitHub API

def is_rate_limited(code, headers):
    """True when an HTTP error is a rate limit to wait out, not a refusal to report.

    GitHub answers 429, or 403 with X-RateLimit-Remaining: 0 or a Retry-After header, when a limit is
    used up. Any other 403 means the token is not allowed to make the request, and waiting will not help.
    """
    if code == 429:
        return True
    if code != 403 or headers is None:
        return False
    return headers.get("X-RateLimit-Remaining") == "0" or bool(headers.get("Retry-After"))


class GitHub:
    """Minimal REST and GraphQL client. The token stays in this object and is sent only to api.github.com."""

    API = "https://api.github.com"

    def __init__(self, token):
        if not token:
            raise SystemExit("GITHUB_TOKEN (or GH_TOKEN) is not set")
        self._token = token
        self.requests = collections.Counter()
        self.waited_seconds = 0

    def _call(self, kind, url, body=None):
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "agent-skills-state-monthly"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        for attempt in range(6):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
            self.requests[kind] += 1
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    return payload, resp.headers
            except urllib.error.HTTPError as e:
                if is_rate_limited(e.code, e.headers):
                    reset = e.headers.get("X-RateLimit-Reset")
                    retry = e.headers.get("Retry-After")
                    wait = int(retry) if retry and retry.isdigit() else (max(5, int(reset) - int(time.time()) + 2) if reset else 60)
                    self._sleep(min(wait, 900))
                    continue
                if e.code == 403:
                    raise SystemExit(f"GitHub API refused a {kind} request (HTTP 403, not a rate limit): the token cannot use "
                                     "this endpoint. The monthly workflow needs a SEARCH_TOKEN secret; see docs/monthly-run.md") from None
                if e.code == 422:  # beyond the 1,000-result window, or a query the token cannot run
                    return None, e.headers
                if e.code >= 500:
                    self._sleep(30)
                    continue
                raise RuntimeError(f"GitHub API returned HTTP {e.code} for a {kind} request") from None
            except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError):
                self._sleep(30)
        raise RuntimeError(f"GitHub API {kind} request failed after retries")

    def _sleep(self, s):
        self.waited_seconds += s
        time.sleep(s)

    def search_code(self, q, page):
        url = f"{self.API}/search/code?" + urllib.parse.urlencode({"q": q, "per_page": 100, "page": page})
        d, h = self._call("search", url)
        # stay under the code search limit (10 a minute): pace, and wait out an empty window
        remaining = h.get("X-RateLimit-Remaining") if h else None
        reset = h.get("X-RateLimit-Reset") if h else None
        if remaining == "0" and reset:
            self._sleep(max(1, int(reset) - int(time.time()) + 2))
        else:
            self._sleep(7)
        return d

    def graphql(self, query):
        d, _ = self._call("graphql", f"{self.API}/graphql", {"query": query})
        return d or {}



def search(gh, queries):
    items, log = [], []
    for kind, q, pages in queries:
        for p in range(1, pages + 1):
            d = gh.search_code(q, p)
            if d is None and p == 1:
                raise SystemExit(f"code search rejected the first page of a {kind} query (HTTP 422); the token may not be "
                                 "allowed to search all of GitHub. See docs/monthly-run.md")
            if d is None:
                log.append({"kind": kind, "q": q, "page": p, "n": 0, "note": "beyond result window"})
                break
            n = len(d.get("items", []))
            log.append({"kind": kind, "q": q, "page": p, "total_count": d.get("total_count"),
                        "incomplete": d.get("incomplete_results"), "n": n})
            for it in d.get("items", []):
                rp = it["repository"]
                items.append({"kind": kind, "repo": rp["full_name"], "fork": rp.get("fork"), "owner": rp["owner"]["login"]})
            if n < 100:
                break
    return items, log


META_FIELDS = ("nameWithOwner isFork isArchived isPrivate stargazerCount forkCount createdAt pushedAt diskUsage "
               "isSecurityPolicyEnabled licenseInfo{spdxId key} owner{__typename login} primaryLanguage{name}")


def fetch_meta(gh, repos):
    meta = {}
    for i in range(0, len(repos), 50):
        chunk = repos[i:i + 50]
        parts = []
        for j, r in enumerate(chunk):
            o, n = r.split("/", 1)
            parts.append(f"r{j}: repository(owner:{json.dumps(o)}, name:{json.dumps(n)}) {{ {META_FIELDS} }}")
        d = (gh.graphql("query{ " + " ".join(parts) + " }") or {}).get("data") or {}
        for j, r in enumerate(chunk):
            meta[r] = d.get(f"r{j}")
        time.sleep(1)
    return meta


# ---------------------------------------------------------------- fetch and scan (never runs repository content)

def clean_env():
    """Environment for child processes: no tokens, no git prompts, no LFS, no system git config."""
    env = {k: v for k, v in os.environ.items() if "TOKEN" not in k.upper() and "SECRET" not in k.upper()}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1", GIT_CONFIG_NOSYSTEM="1")
    return env


def run(args, cwd=None, t=180):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=t, env=clean_env())


def fetch_one(full, dest):
    shutil.rmtree(dest, ignore_errors=True)
    try:
        r = run(["git", "-c", "core.hooksPath=/dev/null", "-c", "filter.lfs.smudge=", "-c", "filter.lfs.process=",
                 "-c", "filter.lfs.required=false", "clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout",
                 f"https://github.com/{full}.git", dest])
        if r.returncode:
            shutil.rmtree(dest, ignore_errors=True)
            return None, "clone_fail"
        run(["git", "sparse-checkout", "set", "--no-cone", *PATTERNS], cwd=dest)
        r = run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.symlinks=false", "checkout", "-q"], cwd=dest, t=300)
        removed = nfiles = nbytes = 0
        for root, dirs, files in os.walk(dest):
            if ".git" in dirs:
                dirs.remove(".git")
            for f in files:
                p = os.path.join(root, f)
                if os.path.islink(p) or os.path.splitext(f)[1].lower() in BIN_EXT:
                    os.remove(p)
                    removed += 1
                    continue
                try:
                    sz = os.path.getsize(p)
                except OSError:
                    continue
                if sz > CAP_FILE_BYTES or nfiles >= CAP_FILES or nbytes + sz > CAP_BYTES:
                    os.remove(p)
                    removed += 1
                    continue
                nfiles += 1
                nbytes += sz
        sha = run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()
        shutil.rmtree(os.path.join(dest, ".git"), ignore_errors=True)
        return {"repo": full, "sha": sha, "files": nfiles, "bytes": nbytes, "removed": removed, "checkout_rc": r.returncode}, "ok"
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        return None, "timeout"


def runj(args, t=240):
    try:
        p = run(args, t=t)
        return json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"_error": "no JSON output"}
    except Exception as e:  # noqa: BLE001
        return {"_error": type(e).__name__}


def skill_files(root):
    out = []
    for r, ds, fs in os.walk(root):
        ds[:] = [d for d in ds if d not in (".git", "node_modules")]
        out.extend(os.path.join(r, f) for f in fs if f == "SKILL.md")
    return out


def yaml_check(path):
    import yaml
    try:
        t = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return "unreadable", None
    m = FM.match(t)
    if not m:
        return "no-front-matter", None
    try:
        d = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return "reject", None
    if not isinstance(d, dict):
        return "not-mapping", None
    desc = d.get("description")
    return "ok", (desc if isinstance(desc, str) else None)


def present(root, name, in_plugin_dir):
    for r, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x != "node_modules"]
        if name in fs and (not in_plugin_dir or os.path.basename(r) == ".claude-plugin"):
            return True
    return False


def mcplint_dir(root, cli):
    """Lint committed tools/list JSON files with mcp-tools-lint (no server is started)."""
    res = {"lists": 0, "tools": 0, "dialect": 0, "no_annotations": 0}
    dialect, noann = set(), set()
    for r, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x != "node_modules"]
        for f in fs:
            if not f.endswith(".json"):
                continue
            p = os.path.join(r, f)
            try:
                t = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if '"inputSchema"' not in t:
                continue
            try:
                j = json.loads(t)
            except Exception:  # noqa: BLE001
                continue
            tools = j.get("tools") if isinstance(j, dict) else j if isinstance(j, list) else None
            if isinstance(j, dict) and isinstance(j.get("result"), dict):
                tools = j["result"].get("tools")
            if not isinstance(tools, list) or not tools or not all(isinstance(x, dict) and "name" in x for x in tools):
                continue
            try:
                pr = run(["node", cli, p, "-f", "json", "--fail-on", "none"], t=60)
                out = json.loads(pr.stdout)
            except Exception:  # noqa: BLE001
                out = {}
            res["lists"] += 1
            res["tools"] += len(tools)
            rel = os.path.relpath(p, root)
            for fd in (out.get("findings", []) if isinstance(out, dict) else []):
                key = (rel, fd.get("toolIndex"))
                if fd.get("ruleId") == "dialect-2020-12":
                    dialect.add(key)
                if fd.get("ruleId") == "missing-annotations":
                    noann.add(key)
    res["dialect"], res["no_annotations"] = len(dialect), len(noann)
    return res


def scan_one(root, fetched, tools):
    """Scan one fetched folder. Secret-rule findings are reduced to counts before anything is kept."""
    raw = runj([tools["ssg"], "scan", root, "--format", "json", "--fail-on", "none"])
    ssg, secret_counts = reduce_secret_findings(raw)
    del raw
    skills = skill_files(root)
    py = sys.executable
    dl = runj([py, "-I", tools["dl"], "--json", "--max-chars", "1024", root]) if skills else {}
    pc = runj([py, "-I", tools["pc"], "--json", root]) if skills else {}
    inv = runj([py, "-I", tools["inv"], "--json", root])
    for k in ("credential_paths", "urls", "shell_patterns", "files", "domains"):
        inv.pop(k, None)
    for s in (dl.get("skills", []) if isinstance(dl, dict) else []):
        f = s.get("file", "")
        s["file"] = os.path.relpath(f, root) if os.path.isabs(f) else f
    yres = []
    for s in skills:
        st, desc = yaml_check(s)
        yres.append({"yaml": st, "desc_len": len(desc) if desc else None,
                     "broad_when": bool(desc and BROAD_WHEN.search(desc)), "has_desc": bool(desc)})
    scripts = inv.get("scripts", []) if isinstance(inv, dict) else []
    hook_scripts_net = [{"path": s["path"], "network": s["network"]} for s in scripts
                        if "/hooks/" in "/" + s.get("path", "") and s.get("network")]
    return {"fetched": fetched, "ssg": ssg, "secret_counts": dict(secret_counts),
            "desc_lint": {"skills": [{"file": s.get("file"), "findings": [{"rule": f.get("rule")} for f in s.get("findings", [])]}
                                     for s in (dl.get("skills", []) if isinstance(dl, dict) else [])]},
            "portability": {"findings": pc.get("findings", []) if isinstance(pc, dict) else []},
            "inventory": {k: inv.get(k, []) for k in ("hooks", "mcp_servers", "kinds")} if isinstance(inv, dict) else {},
            "yaml": yres, "hook_scripts_net": hook_scripts_net, "mcplint": mcplint_dir(root, tools["mcplint"]),
            "present": {"plugin.json": present(root, "plugin.json", True), "marketplace.json": present(root, "marketplace.json", True),
                        "server.json": present(root, "server.json", False), ".mcp.json": present(root, ".mcp.json", False),
                        "hooks.json": present(root, "hooks.json", False)}}


def ensure_tools(tools_dir):
    """Clone the pinned tools if missing, check their commits and return the paths the scan needs."""
    os.makedirs(tools_dir, exist_ok=True)
    out = {}
    ssg = shutil.which("skill-scan-gate") or os.path.join(os.path.dirname(sys.executable), "skill-scan-gate")
    v = run([ssg, "--version"]).stdout.strip()
    if TOOLS["skill-scan-gate"]["version"] not in v:
        raise SystemExit(f"skill-scan-gate {TOOLS['skill-scan-gate']['version']} is required, found {v!r}")
    out["ssg"] = ssg
    for name in ("claude-code-tooling-skills", "mcp-tools-lint"):
        spec = TOOLS[name]
        d = os.path.join(tools_dir, name)
        if not os.path.isdir(os.path.join(d, ".git")):
            run(["git", "clone", "-q", spec["repo"], d], t=300)
            run(["git", "checkout", "-q", spec["commit"]], cwd=d)
        head = run(["git", "rev-parse", "HEAD"], cwd=d).stdout.strip()
        if head != spec["commit"]:
            raise SystemExit(f"{name} is at {head[:7]}, expected {spec['commit'][:7]}")
    lint = os.path.join(tools_dir, "mcp-tools-lint")
    cli = os.path.join(lint, "dist", "cli.js")
    if not os.path.exists(cli):
        for cmd in (["npm", "ci", "--no-audit", "--no-fund"], ["npm", "run", "build"]):
            p = run(cmd, cwd=lint, t=600)
            if p.returncode:
                raise SystemExit(f"mcp-tools-lint: {' '.join(cmd)} failed")
    out["mcplint"] = cli
    s = os.path.join(tools_dir, "claude-code-tooling-skills", "plugins", "cc-setup-tooling", "skills")
    out["dl"] = f"{s}/skill-description-linter/scripts/description_lint.py"
    out["pc"] = f"{s}/skill-portability-check/scripts/portability_check.py"
    out["inv"] = f"{s}/skill-supply-chain-review/scripts/skill_inventory.py"
    return out


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--month", default=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m"))
    ap.add_argument("--work", help="working folder for clones and tools (default: a new temporary folder)")
    ap.add_argument("--limit", type=int, help="dry run: search briefly and scan only this many repositories")
    ap.add_argument("--out", help="output folder (default data/YYYY-MM, or a temporary folder with --limit)")
    ap.add_argument("--workers", type=int, default=max(4, (os.cpu_count() or 2) * 3))
    a = ap.parse_args(argv)
    try:
        seed = derive_seed(a.month)
    except ValueError as e:
        ap.error(str(e))
    dry = a.limit is not None
    work = a.work or tempfile.mkdtemp(prefix="skills-index-")
    out = a.out or (tempfile.mkdtemp(prefix=f"skills-index-{a.month}-") if dry else os.path.join(DATA, a.month))
    if dry and os.path.abspath(out).startswith(os.path.abspath(DATA) + os.sep):
        raise SystemExit("a --limit dry run never writes into data/")
    if not dry and a.month == FIRST_EDITION:
        raise SystemExit(f"{FIRST_EDITION} is the hand-checked first edition; it is not regenerated")
    os.makedirs(out, exist_ok=True)
    started = time.time()
    tools = ensure_tools(os.path.join(work, "tools"))

    gh = GitHub(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    queries = dry_run_queries() if dry else search_queries()
    search_started = time.time()
    items, slog = search(gh, queries)
    search_minutes = round((time.time() - search_started) / 60, 1)
    print(f"search: {gh.requests['search']} requests, {len(items)} hits, {search_minutes} min", flush=True)
    pool, picked = draw_sample(items, a.limit if dry else SAMPLE_SIZE, seed)
    print(f"sample: {len(picked)} of {pool} distinct repositories, seed {seed}", flush=True)
    kinds = dict(picked)
    meta = fetch_meta(gh, [r for r, _ in picked])

    repos_dir = os.path.join(work, "repos")
    os.makedirs(repos_dir, exist_ok=True)
    status = collections.Counter()
    rows, secret_counts = [], []

    def one(full):
        dest = os.path.join(repos_dir, full.replace("/", "__"))
        fetched, st = fetch_one(full, dest)
        if not fetched:
            return full, st, None
        try:
            return full, st, scan_one(dest, fetched, tools)
        finally:
            shutil.rmtree(dest, ignore_errors=True)  # clones never outlive their scan

    scan_started = time.time()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, (full, st, rec) in enumerate(ex.map(one, [r for r, _ in picked])):
            status[st] += 1
            if rec:
                rows.append((full.replace("/", "__"), build_row(rec, meta.get(full), kinds.get(full))))
                secret_counts.append(collections.Counter(rec["secret_counts"]))
            if i % 100 == 0:
                print(f"scan: {i + 1}/{len(picked)} ({int(time.time() - started)}s)", flush=True)
    scan_minutes = round((time.time() - scan_started) / 60, 1)
    rows = [r for _, r in sorted(rows, key=lambda x: x[0])]
    if not rows:
        raise SystemExit("no repository was scanned")

    with open(os.path.join(out, "dataset.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out, "dataset.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    agg = secret_aggregate(secret_counts, len(rows))
    with open(os.path.join(out, "secret_rules_aggregate.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rule", "findings", "repositories_with_finding", "repositories_scanned"])
        w.writerows(agg)

    # headline numbers with the first edition's stats.py, in a scratch folder
    sw = tempfile.mkdtemp(prefix="skills-stats-", dir=work)
    os.makedirs(os.path.join(sw, "out"))
    shutil.copy(os.path.join(out, "dataset.csv"), os.path.join(sw, "out", "dataset.csv"))
    p = subprocess.run([sys.executable, os.path.join(HERE, "stats.py"), sw], capture_output=True, text=True, env=clean_env())
    if p.returncode:
        raise SystemExit("stats.py failed: " + p.stderr[-500:])
    stats = json.load(open(os.path.join(sw, "out", "stats.json"), encoding="utf-8"))
    for k in [k for k in stats if k.startswith("hook_review_")]:
        del stats[k]  # hooks are flagged automatically each month; only the first edition was read by hand
    collected = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    stats["run"] = {
        "month": a.month, "collected_on": collected, "seed": seed, "dry_run": dry,
        "search_requests": gh.requests["search"], "graphql_requests": gh.requests["graphql"],
        "search_hits": len(items), "search_wait_seconds": gh.waited_seconds,
        "incomplete_search_pages": sum(1 for x in slog if x.get("incomplete")),
        "pool_repos": pool, "sampled": len(picked), "fetch_status": dict(status),
        "secret_rule_repos": agg[-1][2], "minutes": round((time.time() - started) / 60, 1), "search_minutes": search_minutes,
        "scan_minutes": scan_minutes, "workers": a.workers,
        "tools": {k: {x: y for x, y in v.items() if x != "repo"} for k, v in TOOLS.items()},
        "precision": PRECISION_NOTE, "hook_network_review": "not done; hook_network_flag is the automatic v3 flag",
    }
    with open(os.path.join(out, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=1)

    if not dry:
        latest = max([m for m in os.listdir(DATA) if MONTH.match(m)] + [a.month])
        if a.month == latest:
            for fn in LATEST_FILES:
                shutil.copy(os.path.join(out, fn), os.path.join(DATA, fn))
        run_info = dict(stats["run"], notes="automatic monthly run; hooks flagged, not hand-reviewed; secret rules counted, not triaged")
        upsert_trend(os.path.join(DATA, "trend.csv"), trend_row(a.month, stats, run_info))
    print(json.dumps({"out": out, **{k: stats["run"][k] for k in ("search_requests", "graphql_requests", "search_hits",
                                                                    "pool_repos", "sampled", "fetch_status", "search_minutes", "scan_minutes", "workers", "minutes")},
                      "repos": stats["repos"], "repos_with_skills": stats["repos_with_skills"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
