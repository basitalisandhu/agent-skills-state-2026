"""Tests for scripts/readme_pins.py and scripts/readme_pins_fetch.py. Offline, fixtures only."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import readme_pins as rp  # noqa: E402
import readme_pins_fetch as rf  # noqa: E402
import annotations_fetch as af  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "readme_pins")
DATA = os.path.join(ROOT, "data", "2026-10", "readme-pins")


@pytest.fixture(scope="module")
def scanned():
    return rp.scan_repo(os.path.join(FIX, "work", "src", "fixture__server"))


@pytest.fixture(scope="module")
def cmds(scanned):
    return {(c["launcher"], c["package"], c["version"]): c for c in scanned[0]}


def test_every_launch_command_is_found_and_nothing_else(cmds):
    assert set(cmds) == {
        ("npx", "@fixture/server", "latest"), ("npx", "@fixture/server", "1.4.2"), ("npx", "@fixture/server", ""),
        ("uvx", "fixture-mcp", ""), ("uvx", "fixture-mcp", "==0.3.1"), ("uvx", "fixture-tools", "latest"),
        ("docker run", "ghcr.io/fixture/server", ""), ("docker run", "ghcr.io/fixture/server", "@sha256:0123abcd"),
        ("docker run", "ghcr.io/fixture/server", "1.4.2"), ("npx", "mcp-remote", "^0.1"),
        ("npx", "@fixture/other", "next"), ("pipx run", "fixture-cli", ""), ("docker run", "fixture/sub", "latest")}


def test_prose_and_dev_tools_are_skipped(cmds):
    names = {k[1] for k in cmds}
    assert "in" not in names and "tsx" not in names and "@modelcontextprotocol/inspector" not in names


@pytest.mark.parametrize("key,pin", [
    (("npx", "@fixture/server", "latest"), "latest"), (("npx", "@fixture/server", "1.4.2"), "exact"),
    (("npx", "@fixture/server", ""), "unpinned"), (("uvx", "fixture-mcp", "==0.3.1"), "exact"),
    (("uvx", "fixture-tools", "latest"), "latest"), (("docker run", "ghcr.io/fixture/server", ""), "unpinned"),
    (("docker run", "ghcr.io/fixture/server", "@sha256:0123abcd"), "exact"), (("npx", "mcp-remote", "^0.1"), "range"),
    (("npx", "@fixture/other", "next"), "latest"), (("docker run", "fixture/sub", "latest"), "latest")])
def test_pin_class(cmds, key, pin):
    assert cmds[key]["pin_class"] == pin
    assert cmds[key]["floating"] is (pin != "exact")


def test_forms_and_auto_yes(cmds):
    assert cmds[("npx", "@fixture/server", "latest")]["form"] == "config"
    assert cmds[("npx", "@fixture/other", "next")]["form"] == "config"  # TOML
    assert cmds[("npx", "@fixture/server", "")]["form"] == "shell"
    assert cmds[("npx", "@fixture/server", "")]["auto_yes"] and not cmds[("uvx", "fixture-mcp", "")]["auto_yes"]


def test_readmes_and_declared_packages(scanned):
    _, readmes, decl = scanned
    assert readmes == ["README.md", os.path.join("packages", "sub", "README.md")]
    assert {(d["ecosystem"], d["identifier"], d["version"]) for d in decl} == {
        ("npm", "@fixture/server", "1.4.2"), ("pypi", "fixture-mcp", "0.3.1"), ("oci", "fixture/sub", "2.0.0")}


@pytest.mark.parametrize("launcher,spec,want", [
    ("npx", "pkg", ("npm", "pkg", "", "unpinned")),
    ("npx", "@s/p@2.0.0-beta.1", ("npm", "@s/p", "2.0.0-beta.1", "exact")),
    ("npx", "@s/p@~2.0", ("npm", "@s/p", "~2.0", "range")),
    ("npx", "pkg@1", ("npm", "pkg", "1", "range")),
    ("npx", "pkg@beta", ("npm", "pkg", "beta", "latest")),
    ("npx", "./dist/index.js", (None, "./dist/index.js", "", None)),
    ("npx", "$PKG", (None, "$PKG", "", None)),
    ("uvx", "pkg>=1.0", ("pypi", "pkg", ">=1.0", "range")),
    ("uvx", "My_Pkg==1.2", ("pypi", "my-pkg", "==1.2", "exact")),
    ("uvx", "pkg@0.9.1", ("pypi", "pkg", "==0.9.1", "exact")),
    ("uvx", "pkg[extra]", ("pypi", "pkg", "", "unpinned")),
    ("uvx", "git+https://github.com/a/b", ("git", "github.com/a/b", "", "unpinned")),
    ("uvx", "git+https://github.com/a/b@0123456789abcdef0123456789abcdef01234567", ("git", "github.com/a/b", "0123456789abcdef0123456789abcdef01234567", "exact")),
    ("npx", "github:a/b#v1.0.0", ("git", "a/b", "", "unpinned")),
    ("docker run", "mcp/fetch", ("oci", "mcp/fetch", "", "unpinned")),
    ("docker run", "docker.io/mcp/fetch:v1.2.3", ("oci", "mcp/fetch", "v1.2.3", "exact")),
    ("docker run", "localhost:5000/img", ("oci", "localhost:5000/img", "", "unpinned")),
    ("docker run", "img:2", ("oci", "img", "2", "range")),
    ("docker run", "img:main", ("oci", "img", "main", "latest")),
    ("docker run", "<your-image>", (None, "<your-image>", "", None)),
    ("docker run", "My/Image", ("oci", "My/Image", "", None)),
    ("pipx run", "package-name", (None, "package-name", "", None)),
    ("npx", "your-server", (None, "your-server", "", None)),
    ("npx", "@your/mcp-server", (None, "@your/mcp-server", "", None)),
])
def test_classify(launcher, spec, want):
    assert rp.classify(launcher, spec) == want


@pytest.mark.parametrize("launcher,args,spec", [
    ("npx", ["-y", "--package=@a/b@1.0.0", "b-cli"], "@a/b@1.0.0"),
    ("npx", ["--yes", "--", "pkg"], "pkg"),
    ("uvx", ["--python", "3.12", "--with", "x", "srv"], "srv"),
    ("uvx", ["--from", "srv==1.0.0", "srv-cmd"], "srv==1.0.0"),
    ("pipx run", ["--spec", "srv==2.0.0", "srv"], "srv==2.0.0"),
    ("docker run", ["-i", "--rm", "-e", "A=1", "--name", "x", "--env-file=.env", "img:1.0.0", "--flag"], "img:1.0.0"),
])
def test_package_spec(launcher, args, spec):
    assert rp.package_spec(launcher, args)[0] == spec


def test_launcher_normalisation():
    text = "```\npnpm dlx pkg@1.0.0\nyarn dlx pkg\nuv tool run srv\ndocker compose up\nbunx pkg@latest\n```\n"
    got = [(l, rp.package_spec(l, a)[0]) for _, l, a, _ in rp.find_commands(text)]
    assert got == [("pnpm dlx", "pkg@1.0.0"), ("yarn dlx", "pkg"), ("uv tool run", "srv"), ("bunx", "pkg@latest")]


def test_inline_code_counts_and_prose_does_not():
    text = "Install with `npx -y pkg@1.0.0`, or use npx pkg directly.\n"
    got = [rp.package_spec(l, a)[0] for _, l, a, _ in rp.find_commands(text)]
    assert got == ["pkg@1.0.0"]


def test_end_to_end(tmp_path):
    out = tmp_path / "out"
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "readme_pins.py"), os.path.join(FIX, "work"),
                    "--dataset", os.path.join(FIX, "dataset.json"), "--out", str(out)], check=True, capture_output=True)
    res = json.load(open(out / "results.json"))
    assert res["repos_selected"] == 3 and res["repos_fetched"] == 2 and res["repos_unavailable"] == 1
    assert res["repos_with_launch_command"] == 1 and res["repos_readme_no_launch_command"] == 1
    assert res["commands"] == 13
    assert res["commands_by_class"] == {"exact": 4, "range": 1, "latest": 4, "unpinned": 4}
    assert res["repo_any_floating"]["value"] == "1/1 (100.0%)"
    assert res["repo_all_floating"]["value"] == "0/1 (0.0%)"
    assert res["command_floating"]["value"] == "9/13 (69.2%)"
    own = res["own_package"]
    assert own["repos_with_own_launch_command"] == 1 and own["repos_registry_exact"] == 1
    assert own["repos_registry_exact_readme_floating"]["value"] == "1/1 (100.0%)"
    assert res["stars_100plus"]["repos"] == 1 and res["stars_under_100"]["repos"] == 0
    rows = (out / "commands.csv").read_text().splitlines()
    assert len(rows) == 14 and rows[0].startswith("repo,file,line,form,launcher")
    assert len(res["hand_check_sample"]["rows_in_commands_csv"]) == 13


def test_fetch_selection_and_patterns():
    data = json.load(open(os.path.join(FIX, "dataset.json")))
    assert af.select(data) == [("fixture/server", "aaaa"), ("fixture/other", "bbbb"), ("fixture/gone", "cccc")]
    assert "**/server.json" in rf.PATTERNS and "**/README.md" in rf.PATTERNS
    assert "!**/node_modules/**" in rf.PATTERNS and not any(p.endswith((".ts", ".py", ".js")) for p in rf.PATTERNS)


@pytest.mark.skipif(not os.path.exists(os.path.join(DATA, "results.json")), reason="no committed results")
def test_report_numbers_match_results():
    res = json.load(open(os.path.join(DATA, "results.json")))
    doc = open(os.path.join(ROOT, "docs", "mcp-readme-install-pins.md"), encoding="utf-8").read()

    def share(v):
        k, n = v.split(" ")[0].split("/")
        pct = v.split("(")[1].rstrip(")")
        return f"{int(k):,} of {int(n):,} ({pct})"

    for key in ("repo_any_floating", "repo_all_floating", "repo_any_exact", "repo_any_latest_tag", "command_floating"):
        assert share(res[key]["value"]) in doc, key
        lo, hi = res[key].get("ci95_wilson") or res[key]["ci95_cluster_bootstrap"]
        assert f"{lo}% to {hi}%" in doc, key
    own = res["own_package"]
    for key in ("repos_registry_exact_readme_floating", "repos_registry_exact_readme_all_floating"):
        assert share(own[key]["value"]) in doc, key
    for eco in ("npm", "pypi", "oci"):
        assert share(res["by_ecosystem"][eco]["repo_any_floating"]["value"]) in doc, eco
    for band in ("stars_100plus", "stars_under_100"):
        assert share(res[band]["repo_all_floating"]["value"]) in doc, band


def test_line_continuations_and_locally_built_images():
    text = ("```sh\ndocker build -t my-mcp .\ndocker run -i --rm my-mcp\ndocker run -d -p 8080:8080 \\\n"
            "  -e A=1 \\\n  ghcr.io/x/srv:1.2.3\n```\n")
    got = [(l, rp.package_spec(l, a)[0], line) for _, l, a, line in rp.find_commands(text)]
    assert got == [("docker run", "ghcr.io/x/srv:1.2.3", 4)]


def test_quoted_values_and_refresh_flags(tmp_path):
    (tmp_path / "README.md").write_text(
        '```\ndocker run -e TOOLS="gmail drive" ghcr.io/x/y\nuvx --refresh --from srv srv-cmd\n'
        'docker run -i --pull=always ghcr.io/x/z\nnpx -y plugins add a/b\n```\n')
    got = {(c["package"], c["pin_class"]) for c in rp.scan_repo(str(tmp_path))[0]}
    assert got == {("ghcr.io/x/y", "unpinned"), ("srv", "latest"), ("ghcr.io/x/z", "latest")}


def test_placeholders_and_shell_comments_are_skipped(tmp_path):
    (tmp_path / "README.md").write_text(
        "```sh\n# npx caches the package, so pin it\nnpx -y @a/mcp-<name>\nnpx --ignore-scripts srv@<plugin version>\n"
        "docker run -i ghcr.io/a/b:${TAG}\nnpx -y real-srv@2.0.0\n```\nAlso `npx -y inline-srv` here.\n")
    got = {(c["package"], c["pin_class"]) for c in rp.scan_repo(str(tmp_path))[0]}
    assert got == {("real-srv", "exact"), ("inline-srv", "unpinned")}


def test_hand_sample_is_stable_and_sized():
    cmds = [{"repo": f"r/{i}", "file": "README.md", "line": i, "package": "p"} for i in range(100)]
    a = rp.hand_sample(cmds, 10)
    assert len(a) == 10 and a == sorted(a) and a == rp.hand_sample(cmds, 10)
    kept = [cmds[i] for i in a]
    b = rp.hand_sample(cmds[:5] + cmds[50:], 10)
    assert {c["repo"] for c in kept if int(c["repo"][2:]) >= 50 or int(c["repo"][2:]) < 5} <= {(cmds[:5] + cmds[50:])[i]["repo"] for i in b}


def test_comment_line_does_not_swallow_the_next_command_and_yaml_config():
    text = "```sh\n# Or using uvx\nuvx --from intugle[streamlit] intugle-streamlit\n```\n\n```yaml\nsrv:\n  command: npx\n  args: [\"-y\", \"yaml-srv\"]\n```\n"
    got = [(l, rp.package_spec(l, a)[0]) for _, l, a, _ in rp.find_commands(text)]
    assert ("npx", "yaml-srv") in got and ("uvx", "intugle[streamlit]") in got and len(got) == 2
