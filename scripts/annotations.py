"""Measure MCP tool annotations in the source of the October 2026 repositories that ship a server.json.

Usage: python scripts/annotations.py WORKDIR [--dataset data/2026-10/dataset.json] [--out data/2026-10/annotations]

Reads the source fetched by scripts/annotations_fetch.py (WORKDIR/src and WORKDIR/fetch_log.jsonl). Static only:
nothing is imported, built or run. Standard library only.

For every source file it finds tool registrations with the patterns in PATTERNS (TypeScript and JavaScript SDK
calls and tool objects, Python FastMCP decorators and Tool(...) objects, Go mcp-go and go-sdk, Rust rmcp, C#),
takes the registration's own text (the "window": a decorator or attribute, or the text up to the next
registration in the same file, at most WINDOW_CAP characters) and records which of the four hints
(readOnlyHint, destructiveHint, idempotentHint, openWorldHint) it sets and to what value. Tool names are split
into words and classed by verb (DESTRUCTIVE_VERBS, READ_VERBS). Writes tools.csv, repos.csv and results.json.
"""
import argparse, csv, json, os, random, re

WINDOW_CAP = 6000
SRC_EXT = {".ts": "ts", ".tsx": "ts", ".mts": "ts", ".cts": "ts", ".js": "ts", ".mjs": "ts", ".cjs": "ts",
           ".py": "py", ".go": "go", ".rs": "rs", ".cs": "cs"}
NAME = r"([A-Za-z][A-Za-z0-9_.\-]{0,80})"
# (pattern id, language, regex). Group "name" is the tool name when the pattern carries one.
PATTERNS = [
    ("ts-call", "ts", re.compile(r"\.(?:tool|registerTool|addTool)\(\s*['\"`]" + NAME.replace("(", "(?P<name>", 1) + r"['\"`]")),
    ("ts-object", "ts", re.compile(r"(?<![\w.])name\s*:\s*['\"`]" + NAME.replace("(", "(?P<name>", 1) + r"['\"`]\s*,")),
    ("py-decorator", "py", re.compile(r"^[ \t]*@[\w.]*?tool\b(?:\s*\(|\s*$)", re.M)),
    ("py-Tool", "py", re.compile(r"\b(?:types\.)?Tool\(\s*name\s*=\s*['\"]" + NAME.replace("(", "(?P<name>", 1) + r"['\"]")),
    ("go-NewTool", "go", re.compile(r"\bmcp\.NewTool\(\s*\"" + NAME.replace("(", "(?P<name>", 1) + r"\"")),
    ("go-Tool", "go", re.compile(r"\b\w+\.Tool\{")),  # go-sdk, any import alias; Name: is read from the window
    ("rs-attr", "rs", re.compile(r"#\[tool\b")),
    ("cs-attr", "cs", re.compile(r"\[McpServerTool\b")),
]
HINTS = {
    "readOnlyHint": r"read_?only_?hint|\bReadOnly\b",
    "destructiveHint": r"destructive_?hint|\bDestructive\b",
    "idempotentHint": r"idempotent_?hint|\bIdempotent\b",
    "openWorldHint": r"open_?world_?hint|\bOpenWorld\b",
}
HINT_ANY = re.compile(r"(?i)read_?only_?hint|destructive_?hint|idempotent_?hint|open_?world_?hint")
# Annotations passed by reference (a shared constant, a helper call or **kwargs), so the hint values are elsewhere.
# They count as annotated only when the repository's source sets a hint somewhere.
INDIRECT = re.compile(r"(?i)\bannotations\s*[:=]\s*(?:\{\s*\.\.\.|(?!\{|&?(?:mcp\.|types\.)?ToolAnnotations\b|None\b|null\b|undefined\b|nil\b|\[)[A-Za-z_$])"
                      r"|\bannotat\w*\s*\((?!\s*\))|^\s*@[\w.]*?tool\s*\([^)]*\*\*[A-Za-z_]\w*\s*[,)]", re.M)
CLIENT_CALL = re.compile(r"await\s+[\w.]+\.$")
# Names that say the tool removes or overwrites something ("destructive") or acts on the outside world in a way
# that cannot be taken back but may be additive ("outward"). Together: "side-effect" tools.
DESTRUCTIVE_VERBS = {"delete", "del", "remove", "rm", "drop", "destroy", "purge", "erase", "wipe", "truncate", "kill",
                     "terminate", "revoke", "uninstall", "overwrite"}
OUTWARD_VERBS = {"send", "pay", "transfer", "charge", "refund", "write"}
READ_VERBS = {"get", "list", "search", "read", "fetch", "find", "query", "describe", "show", "lookup", "view", "check",
              "count", "inspect", "status", "info", "retrieve"}
# Test and fixture folders the fetch did not already exclude; tools there are not shipped.
SKIP_DIRS = {"fixtures", "test-fixtures", "__fixtures__", "testdata", "mocks", "__mocks__", "node_modules", "dist", "build",
             "vendor", "test", "tests", "__tests__", "spec", "e2e"}


def words(name):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


def verb_class(name):
    """The class of the first word of the name that is a known verb (so retrieve_refund is a read, email_send outward)."""
    for w in words(name):
        if w in DESTRUCTIVE_VERBS:
            return "destructive"
        if w in OUTWARD_VERBS:
            return "outward"
        if w in READ_VERBS:
            return "read"
    return "other"


def hint_value(window, hint, lang):
    """'true', 'false', 'set' (present, value not a literal) or '' (absent)."""
    key = HINTS[hint] if lang == "cs" else HINTS[hint].split(r"|\b")[0]
    m = re.search(r"(?i)(?:" + key + r")\w*['\"]?\s*(?:[:=(]\s*|\)\s*\(\s*)?(true|false)\b", window)
    if m:
        return m.group(1).lower()
    return "set" if re.search(r"(?i)" + key, window) else ""


def py_window(text, start):
    """From a @...tool decorator to the end of the def line; name from name= or the function."""
    m = re.compile(r"^[ \t]*(?:async\s+)?def\s+(\w+)", re.M).search(text, start)
    if not m or m.start() - start > 3000:
        return None, None
    win = text[start:m.end()]
    n = re.search(r"\bname\s*=\s*['\"]([\w.\-]+)['\"]", win)
    return (n.group(1) if n else m.group(1)), win


def attr_window(text, start, lang):
    """Rust #[tool(...)] or C# [McpServerTool(...)]: up to the next fn / method name."""
    rx = r"\bfn\s+(\w+)" if lang == "rs" else r"\b(?:public|private|internal|static|async|Task<[^>]*>|[\w<>\[\]?]+)\s+(\w+)\s*\("
    m = re.compile(rx).search(text, start)
    if not m or m.start() - start > 3000:
        return None, None
    win = text[start:m.end()]
    n = re.search(r"\bname\s*=\s*\"([\w.\-]+)\"", win, re.I)
    return (n.group(1) if n else m.group(1)), win


def extract(text, lang):
    """Return a list of dicts: pattern, name, line, window."""
    hits = []
    for pid, plang, rx in PATTERNS:
        if plang != lang:
            continue
        for m in rx.finditer(text):
            if pid == "ts-call" and CLIENT_CALL.search(text[max(0, m.start() - 40):m.start() + 1]):
                continue  # a client calling a tool (await client.tool("x", ...)), not a registration
            hits.append((m.start(), pid, m.groupdict().get("name")))
    hits.sort()
    out = []
    for i, (pos, pid, name) in enumerate(hits):
        nxt = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        if pid == "py-decorator":
            name, win = py_window(text, pos)
        elif pid in ("rs-attr", "cs-attr"):
            name, win = attr_window(text, pos, lang)
        else:
            win = text[pos:min(nxt, pos + WINDOW_CAP)]
            if pid == "go-Tool":
                n = re.search(r"\bName\s*:\s*\"([\w.\-]+)\"", win[:800])
                name = n.group(1) if n else None
        if not name or win is None:
            continue
        if pid == "ts-object" and not re.search(r"\binput_?[sS]chema\b|\bparameters\s*:", win):
            continue  # a name: key that is not a tool definition
        out.append({"pattern": pid, "name": name, "line": text.count("\n", 0, pos) + 1, "window": win})
    return out


def classify(tool, lang):
    win = tool["window"]
    vals = {h: hint_value(win, h, lang) for h in HINTS}
    any_hint = any(vals.values())
    indirect = not any_hint and bool(INDIRECT.search(win))
    vc = verb_class(tool["name"])
    return {**{h: vals[h] for h in HINTS}, "hint_inline": any_hint, "indirect": indirect, "verb_class": vc,
            "contradiction": (vc in ("destructive", "outward") and vals["readOnlyHint"] == "true")
                             or (vc == "destructive" and vals["destructiveHint"] == "false")}


def scan_repo(path, counts=None):
    tools, mentions = [], False
    counts = counts if counts is not None else {}
    counts.setdefault("source_files", 0)
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d.lower() not in SKIP_DIRS)
        for f in sorted(files):
            lang = SRC_EXT.get(os.path.splitext(f)[1].lower())
            if not lang:
                continue
            counts["source_files"] += 1
            p = os.path.join(root, f)
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if HINT_ANY.search(text) or (lang == "cs" and re.search(r"\[McpServerTool\([^\]]*(ReadOnly|Destructive|Idempotent|OpenWorld)\s*=", text)):
                mentions = True
            for t in extract(text, lang):
                t.update(classify(t, lang), file=os.path.relpath(p, path), lang=lang)
                tools.append(t)
    for t in tools:
        t["annotated"] = t["hint_inline"] or (t["indirect"] and mentions)
    seen, uniq = set(), []
    for t in tools:  # the same tool registered twice in one repository (for example src and a copy) counts once
        if t["name"] not in seen:
            seen.add(t["name"]); uniq.append(t)
    return uniq, mentions


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (round(100 * max(0, c - h), 1), round(100 * min(1, c + h), 1))


def cluster_ci(groups, B=2000, seed=20261016):
    """95% bootstrap CI (percent) for sum(k)/sum(n) over groups=[(k, n)], resampling repositories."""
    groups = [g for g in groups if g[1]]
    if not groups:
        return (0.0, 0.0)
    rnd = random.Random(seed); est = []
    for _ in range(B):
        s = [groups[rnd.randrange(len(groups))] for _ in groups]
        n = sum(x[1] for x in s); est.append(sum(x[0] for x in s) / n if n else 0)
    est.sort()
    return (round(100 * est[int(0.025 * B)], 1), round(100 * est[int(0.975 * B) - 1], 1))


def mean_share_ci(shares, B=2000, seed=20261016):
    """Mean of per-repository shares (each repository weighs the same), in percent, with a 95% bootstrap CI."""
    if not shares:
        return {"value": 0.0, "ci95_bootstrap": (0.0, 0.0), "repos": 0}
    rnd = random.Random(seed); est = []
    for _ in range(B):
        s = [shares[rnd.randrange(len(shares))] for _ in shares]; est.append(sum(s) / len(s))
    est.sort()
    return {"value": round(100 * sum(shares) / len(shares), 1),
            "ci95_bootstrap": (round(100 * est[int(0.025 * B)], 1), round(100 * est[int(0.975 * B) - 1], 1)), "repos": len(shares)}


def frac(k, n):
    return f"{k}/{n} ({100 * k / n:.1f}%)" if n else f"{k}/0"


def summarise(repos, tools):
    ok = [r for r in repos if r["state"] in ("pinned", "moved")]
    with_tools = [r for r in ok if r["n_tools"]]
    by_repo = {}
    for t in tools:
        by_repo.setdefault(t["repo"], []).append(t)

    def tool_share(pred, base=lambda t: True):
        groups = [(sum(1 for t in ts if base(t) and pred(t)), sum(1 for t in ts if base(t))) for ts in by_repo.values()]
        k = sum(g[0] for g in groups); n = sum(g[1] for g in groups)
        return {"value": frac(k, n), "ci95_cluster_bootstrap": cluster_ci(groups), "repos": sum(1 for g in groups if g[1])}

    def repo_share(pred, base):
        k = sum(1 for r in base if pred(r)); return {"value": frac(k, len(base)), "ci95_wilson": wilson(k, len(base))}

    D = lambda t: t["verb_class"] in ("destructive", "outward")
    DD = lambda t: t["verb_class"] == "destructive"
    R = lambda t: t["verb_class"] == "read"
    out = {
        "selection": "every repository in data/2026-10/dataset.json with has_server_json true",
        "repos_selected": len(repos),
        "repos_fetched": len(ok),
        "repos_pinned_commit": sum(1 for r in ok if r["state"] == "pinned"),
        "repos_unavailable": len(repos) - len(ok),
        "repos_with_tools": len(with_tools),
        "repos_without_tools_no_source": sum(1 for r in ok if not r["n_tools"] and not r["source_files"]),
        "repos_without_tools_with_source": sum(1 for r in ok if not r["n_tools"] and r["source_files"]),
        "tools": len(tools),
        "tools_median_per_repo": sorted(r["n_tools"] for r in with_tools)[len(with_tools) // 2] if with_tools else 0,
        "tools_by_language": {l: sum(1 for t in tools if t["lang"] == l) for l in sorted({t["lang"] for t in tools})},
        "repo_any_hint_in_source": repo_share(lambda r: r["mentions_hint"], with_tools),
        "repo_all_tools_annotated": repo_share(lambda r: r["n_annotated"] == r["n_tools"], with_tools),
        "repo_no_tool_annotated": repo_share(lambda r: r["n_annotated"] == 0, with_tools),
        "tool_annotated": tool_share(lambda t: t["annotated"]),
        "tool_hint_inline": tool_share(lambda t: t["hint_inline"]),
        "repo_mean_share_annotated": mean_share_ci([r["n_annotated"] / r["n_tools"] for r in with_tools]),
        "destructive_repo_mean_share_annotated": mean_share_ci(
            [sum(1 for t in ts if D(t) and t["annotated"]) / sum(1 for t in ts if D(t)) for ts in by_repo.values() if any(D(t) for t in ts)]),
        "repos_with_destructive_tools": sum(1 for ts in by_repo.values() if any(D(t) for t in ts)),
        "repo_destructive_none_annotated": repo_share(lambda ts: not any(D(t) and t["annotated"] for t in ts),
                                                      [ts for ts in by_repo.values() if any(D(t) for t in ts)]),
        "repo_any_contradiction": repo_share(lambda ts: any(t["contradiction"] for t in ts), list(by_repo.values())),
        "destructive_tools": sum(1 for t in tools if D(t)),
        "destructive_tool_annotated": tool_share(lambda t: t["annotated"], D),
        "destructive_tool_destructiveHint_true": tool_share(lambda t: t["destructiveHint"] == "true", D),
        "destructive_tool_destructiveHint_false": tool_share(lambda t: t["destructiveHint"] == "false", D),
        "remove_tools": sum(1 for t in tools if DD(t)),
        "remove_tool_annotated": tool_share(lambda t: t["annotated"], DD),
        "remove_tool_destructiveHint_true": tool_share(lambda t: t["destructiveHint"] == "true", DD),
        "remove_tool_destructiveHint_false": tool_share(lambda t: t["destructiveHint"] == "false", DD),
        "outward_tools": sum(1 for t in tools if t["verb_class"] == "outward"),
        "outward_tool_annotated": tool_share(lambda t: t["annotated"], lambda t: t["verb_class"] == "outward"),
        "destructive_tool_readOnlyHint_true": tool_share(lambda t: t["readOnlyHint"] == "true", D),
        "destructive_tool_contradiction": tool_share(lambda t: t["contradiction"], D),
        "read_tools": sum(1 for t in tools if R(t)),
        "read_tool_readOnlyHint_true": tool_share(lambda t: t["readOnlyHint"] == "true", R),
        "hint_set": {h: tool_share(lambda t, h=h: bool(t[h])) for h in HINTS},
        "destructive_by_verb": {},
        "stars_100plus": {},
    }
    for v in sorted(DESTRUCTIVE_VERBS | OUTWARD_VERBS):
        ts = [t for t in tools if D(t) and v in words(t["name"])]
        if ts:
            out["destructive_by_verb"][v] = {"tools": len(ts), "annotated": sum(1 for t in ts if t["annotated"]),
                                             "destructiveHint_true": sum(1 for t in ts if t["destructiveHint"] == "true")}
    for band, test in (("0-99", lambda s: s < 100), ("100+", lambda s: s >= 100)):
        base = [r for r in with_tools if test(r["stars"])]
        names = {r["repo"] for r in base}
        groups = [(sum(1 for t in ts if t["annotated"]), len(ts)) for k, ts in by_repo.items() if k in names]
        k = sum(g[0] for g in groups); n = sum(g[1] for g in groups)
        out["stars_100plus" if band == "100+" else "stars_under_100"] = {
            "repos": len(base), "repo_any_hint_in_source": repo_share(lambda r: r["mentions_hint"], base),
            "tool_annotated": {"value": frac(k, n), "ci95_cluster_bootstrap": cluster_ci(groups)}}
    return out


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--dataset", default=os.path.join(root, "data", "2026-10", "dataset.json"))
    ap.add_argument("--out", default=os.path.join(root, "data", "2026-10", "annotations"))
    a = ap.parse_args()
    meta = {r["repo"]: r for r in json.load(open(a.dataset)) if r.get("has_server_json")}
    log = {}
    for line in open(os.path.join(a.workdir, "fetch_log.jsonl")):
        m = json.loads(line); log[m["repo"]] = m
    repos, tools = [], []
    for full in sorted(meta):
        f = log.get(full, {"state": "not_fetched"})
        r = {"repo": full, "stars": meta[full]["stars"], "language": meta[full]["language"] or "", "state": f["state"],
             "commit": f.get("sha", ""), "files": f.get("files", 0), "source_files": 0, "n_tools": 0, "n_annotated": 0, "mentions_hint": False}
        if f["state"] in ("pinned", "moved"):
            counts = {}
            ts, mentions = scan_repo(os.path.join(a.workdir, "src", full.replace("/", "__")), counts)
            r["source_files"] = counts["source_files"]
            for t in ts:
                t["repo"] = full
            tools += ts
            r.update(n_tools=len(ts), n_annotated=sum(1 for t in ts if t["annotated"]), mentions_hint=mentions)
        repos.append(r)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "repos.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(repos[0])); w.writeheader(); w.writerows(repos)
    cols = ["repo", "file", "line", "lang", "pattern", "name", "verb_class", "annotated", "hint_inline", "indirect", *HINTS, "contradiction"]
    with open(os.path.join(a.out, "tools.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(tools)
    res = summarise(repos, tools)
    json.dump(res, open(os.path.join(a.out, "results.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("destructive_by_verb", "hint_set")}, indent=1))


if __name__ == "__main__":
    main()
