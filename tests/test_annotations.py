"""Tests for scripts/annotations.py and the selection in scripts/annotations_fetch.py. Offline, fixtures only."""
import csv
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import annotations as an  # noqa: E402
import annotations_fetch as af  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "annotations")


@pytest.fixture(scope="module")
def tools():
    ts, mentions = an.scan_repo(os.path.join(FIX, "work", "src", "fixture__repo"))
    assert mentions
    return {t["name"]: t for t in ts}


def test_every_fixture_tool_is_found_and_nothing_else(tools):
    assert set(tools) == {"list_files", "deleteFile", "send_email", "remove_user", "get_user", "search_notes",
                          "drop_table", "pay_invoice", "write_file", "fetch_page", "purge_cache", "show_status",
                          "ReadRecord", "TerminateSession", "purge_queue", "erase_disk", "set_voltage", "kill_job", "list_devices"}


@pytest.mark.parametrize("name,annotated", [
    ("list_files", True), ("deleteFile", False), ("send_email", True), ("remove_user", True), ("get_user", False),
    ("search_notes", True), ("drop_table", False), ("write_file", True), ("fetch_page", True),
    ("purge_cache", True), ("show_status", False), ("ReadRecord", True), ("TerminateSession", False),
    ("pay_invoice", False), ("erase_disk", False), ("purge_queue", True), ("set_voltage", True), ("kill_job", False),
    ("list_devices", True)])
def test_annotated(tools, name, annotated):
    assert tools[name]["annotated"] is annotated


def test_reference_counts_only_as_indirect(tools):
    assert tools["purge_queue"]["indirect"] and not tools["purge_queue"]["hint_inline"]
    assert tools["set_voltage"]["indirect"]
    assert not tools["erase_disk"]["indirect"] and not tools["pay_invoice"]["indirect"]


def test_client_calls_are_not_registrations(tools):
    assert "delete_everything" not in tools


def test_indirect_needs_a_hint_somewhere_in_the_repository(tmp_path):
    (tmp_path / "s.ts").write_text('server.registerTool("drop_db", { inputSchema: {}, annotations: SHARED }, h);\n')
    ts, mentions = an.scan_repo(str(tmp_path))
    assert not mentions and ts[0]["indirect"] and not ts[0]["annotated"]


@pytest.mark.parametrize("name,hint,value", [
    ("list_files", "readOnlyHint", "true"), ("list_files", "openWorldHint", "false"), ("list_files", "destructiveHint", ""),
    ("search_notes", "destructiveHint", "false"), ("write_file", "destructiveHint", "true"),
    ("fetch_page", "readOnlyHint", "true"), ("purge_cache", "idempotentHint", "true"),
    ("ReadRecord", "readOnlyHint", "true"), ("ReadRecord", "openWorldHint", "false")])
def test_hint_values(tools, name, hint, value):
    assert tools[name][hint] == value


def test_destructive_false_on_an_outward_tool_is_not_a_contradiction(tools):
    assert an.classify({"name": "send_sms", "window": "annotations: { destructiveHint: false }"}, "ts")["contradiction"] is False
    assert an.classify({"name": "delete_row", "window": "annotations: { destructiveHint: false }"}, "ts")["contradiction"] is True


def test_contradiction_is_a_destructive_name_marked_read_only(tools):
    assert tools["send_email"]["contradiction"]
    assert not tools["remove_user"]["contradiction"]
    assert not tools["list_files"]["contradiction"]


@pytest.mark.parametrize("name,cls", [
    ("deleteFile", "destructive"), ("send_email", "outward"), ("pay_invoice", "outward"), ("write_file", "outward"),
    ("TerminateSession", "destructive"), ("get_user", "read"), ("list_files", "read"), ("summarise", "other"),
    ("delegate_task", "other"), ("sendgrid_status", "read"), ("rewrite_prompt", "other"), ("retrieve_refund", "read"),
    ("email_send", "outward"), ("get_delete_status", "read"), ("list_payments", "read")])
def test_verb_class(name, cls):
    assert an.verb_class(name) == cls


def test_wilson_bounds():
    assert an.wilson(0, 0) == (0.0, 0.0)
    lo, hi = an.wilson(50, 100)
    assert 40 < lo < 50 < hi < 60
    assert an.wilson(0, 20)[0] == 0.0


def test_cluster_ci_is_deterministic_and_brackets_the_estimate():
    g = [(1, 4), (0, 10), (5, 5), (2, 8), (0, 3)]
    a = an.cluster_ci(g)
    assert a == an.cluster_ci(g)
    assert a[0] <= 100 * 8 / 30 <= a[1]


def test_selection_takes_only_server_json_repositories():
    data = json.load(open(os.path.join(FIX, "dataset.json")))
    assert af.select(data) == [("fixture/repo", "0" * 40), ("fixture/gone", "1" * 40)]


def test_end_to_end_writes_results(tmp_path):
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "annotations.py"), os.path.join(FIX, "work"),
                    "--dataset", os.path.join(FIX, "dataset.json"), "--out", str(tmp_path)], check=True, capture_output=True)
    res = json.load(open(tmp_path / "results.json"))
    assert res["repos_selected"] == 2 and res["repos_fetched"] == 1 and res["repos_unavailable"] == 1
    assert res["tools"] == 19
    assert res["tool_annotated"]["value"] == "11/19 (57.9%)"
    assert res["destructive_tools"] == 11
    assert res["destructive_tool_contradiction"]["value"] == "1/11 (9.1%)"
    rows = list(csv.DictReader(open(tmp_path / "tools.csv")))
    assert len(rows) == 19 and {r["repo"] for r in rows} == {"fixture/repo"}
    repos = list(csv.DictReader(open(tmp_path / "repos.csv")))
    assert [r["state"] for r in repos] == ["unavailable", "pinned"]


@pytest.mark.parametrize("window,value", [
    ('annotations=types.ToolAnnotations(**{"category": "X", "readOnlyHint": True})', "true"),
    ("annotations={'readOnlyHint': False}", "false"),
    ("mcp.WithReadOnlyHintAnnotation(true)", "true"),
    ("annotations: { readOnlyHint: isSafe }", "set"),
    ("annotations: { title: 'x' }", "")])
def test_hint_value_forms(window, value):
    assert an.hint_value(window, "readOnlyHint", "ts") == value


def test_fixture_folders_are_skipped(tmp_path):
    d = tmp_path / "test-fixtures"; d.mkdir()
    (d / "a.go").write_text('_ = mcp.NewTool("write_thing", mcp.WithDescription("x"))\n')
    (tmp_path / "b.go").write_text('t := mcp.NewTool("read_thing", mcp.WithReadOnlyHintAnnotation(true))\n')
    ts, _ = an.scan_repo(str(tmp_path))
    assert [t["name"] for t in ts] == ["read_thing"]


def test_markdown_bold_in_a_description_is_not_a_kwargs_spread():
    win = '@mcp.tool(description="""Get it.\n\n**When to use**:\n- now\n""")\ndef get_it'
    assert not an.classify({"name": "get_it", "window": win}, "py")["indirect"]
    assert an.classify({"name": "get_it", "window": "@mcp.tool(**READ, timeout=5)\ndef get_it"}, "py")["indirect"]


# The committed results and the report page agree.

DATA = os.path.join(ROOT, "data", "2026-10", "annotations")
DOC = os.path.join(ROOT, "docs", "mcp-tool-annotations.md")
FRACTION = __import__("re").compile(r"^(\d+)/(\d+) \((\d+(?:\.\d+)?)%\)$")


def _published():
    """Every a/b/p triple and every interval in results.json, plus the hand check's own fractions."""
    res = json.load(open(os.path.join(DATA, "results.json")))
    fr, cis, nums = set(), set(), set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            if len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
                cis.add((float(v[0]), float(v[1])))
            for x in v:
                walk(x)
        elif isinstance(v, str) and FRACTION.match(v):
            a, b, p = FRACTION.match(v).groups()
            fr.add((int(a), int(b), float(p)))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.add(float(v))
    walk(res)
    hc = list(csv.DictReader(open(os.path.join(DATA, "hand-check.csv"))))
    k = sum(1 for r in hc if r["is_tool_registration"] == "yes")
    fr.add((k, len(hc), round(100 * k / len(hc), 1)))
    cis.add(an.wilson(k, len(hc)))
    return res, fr, cis, nums


def test_committed_files_match_results():
    res, _, _, _ = _published()
    assert len(list(csv.DictReader(open(os.path.join(DATA, "tools.csv"))))) == res["tools"]
    assert len(list(csv.DictReader(open(os.path.join(DATA, "repos.csv"))))) == res["repos_selected"]


def test_every_share_in_the_report_is_in_results():
    import re
    _, fr, cis, nums = _published()
    text = open(DOC, encoding="utf-8").read()
    n = lambda s: float(s.replace(",", ""))
    claims = re.findall(r"(\d[\d,]*) of (\d[\d,]*) \((\d+(?:\.\d+)?)%\)", text)
    assert len(claims) >= 10
    for a, b, p in claims:
        assert (n(a), n(b), float(p)) in fr, f"{a} of {b} ({p}%)"
    rows = re.findall(r"^\| [^|]+ \| ([\d,]+) \| ([\d,]+) \| ([\d.]+)% \| ([\d.]+)% to ([\d.]+)% \|$", text, re.M)
    assert len(rows) >= 15
    for a, b, p, lo, hi in rows:
        assert (n(a), n(b), float(p)) in fr, f"table row {a}/{b}"
        assert (float(lo), float(hi)) in cis, f"table interval {lo} to {hi}"
    for lo, hi in re.findall(r"95% CI ([\d.]+)% to ([\d.]+)%", text):
        assert (float(lo), float(hi)) in cis, f"interval {lo} to {hi}"
    for v in re.findall(r"typical server annotates ([\d.]+)%", text):
        assert float(v) in nums


def test_report_has_no_em_dash():
    assert "—" not in open(DOC, encoding="utf-8").read()
