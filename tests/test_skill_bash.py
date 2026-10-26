"""Tests for scripts/skill_bash.py and scripts/skill_bash_fetch.py. Offline, fixtures only."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import skill_bash as sb  # noqa: E402
import skill_bash_fetch as sf  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "skill_bash")
SRC = os.path.join(FIX, "work", "src", "fixture__skills")
DATA = os.path.join(ROOT, "data", "2026-10", "skill-bash")


def fm(tools):
    return f"---\nname: x\ndescription: y\nallowed-tools: {tools}\n---\nbody\n"


@pytest.mark.parametrize("tools,granted", [
    ("Bash", True), ("Bash, Read", True), ("Read, Bash(*)", True), ("[Read, \"Bash\"]", True), ("'Bash'", True),
    ("Bash(git:*)", False), ("Bash(git:*), Read", False), ("Read, Write", False), ("BashOutput", False),
    ("Bash(npm run test:*), Bash(*)", True)])
def test_unscoped_bash_matches_ssg607(tools, granted):
    assert (sb.unscoped_bash(fm(tools)) is not None) is granted


def test_block_list_and_missing_front_matter():
    assert sb.unscoped_bash("---\nname: x\nallowed-tools:\n  - Read\n  - Bash\n---\n") is not None
    assert sb.unscoped_bash("# no front matter\nallowed-tools: Bash\n") is None
    assert sb.unscoped_bash("---\nallowed-tools: Bash\n") is None  # never closed


def test_multiline_quotes_and_heredocs_are_one_command():
    text = ("```bash\ngh pr create --title x --body \"## Summary\nAdd a thing\n- Test it\" --base main\n"
            "cat > notes.md <<'EOF'\nrm -rf / is only text here\nEOF\ngit status\n```\n")
    got = [c for _, c in sb.command_lines(text)]
    assert got == ['gh pr create --title x --body "## Summary Add a thing - Test it" --base main',
                   "cat > notes.md <<'EOF'", "git status"]


def test_command_lines_fences_inline_prompts_and_continuations():
    text = ("---\nallowed-tools: Bash\n---\nUse `python run.py --x` but curl is prose.\n"
            "```bash\n# a comment\nSearch for: x\n$ git status\nnpm run build \\\n  --prod\n```\n"
            "```text\nnot a command\ngit log\n```\n```python\nimport os\neval(code)\n```\nAlso `README.md` is a file.\n")
    got = [c for _, c in sb.command_lines(text)]
    assert got == ["python run.py --x", "git status", "npm run build --prod", "git log"]


@pytest.mark.parametrize("cmd,heads", [
    ("git add . && git commit -m x && git push", ["git", "git", "git"]),
    ("FOO=1 sudo -E apt-get install jq", ["apt-get"]),
    ("cat a | grep b; echo $(date)", ["cat", "grep", "echo", "date"]),
    ("make test || true", ["make"]),
    ("Reference: references/x.md", []),
    ("for f in *.md; do wc -l $f; done", ["wc"]), ("http) curl -s x ;;", ["curl"]),
    ("tool x | jq -r 'select(.a | test(\"b\")) | .url' | head -n 5", ["tool", "jq", "head"]),
    ("timeout 30 python x.py", ["python"]),
    ("if [ -f x ]; then rm x; fi", ["rm"]),
])
def test_heads(cmd, heads):
    assert sb.heads(cmd) == heads


@pytest.mark.parametrize("rule,line,hit", [
    ("http_call", "curl -s https://x.example.com", True), ("http_call", "r = requests.get(url)", True),
    ("http_call", "const r = await fetch(url)", True), ("http_call", "the curl-like helper", False),
    ("http_call", "ssh deploy@host.example.com", True), ("http_call", "ssh-keygen -t ed25519", False),
    ("installs_or_fetches_package", "pip install -r requirements.txt", True),
    ("installs_or_fetches_package", "npx -y pkg@1.0.0", True), ("installs_or_fetches_package", "npm install", False),
    ("installs_or_fetches_package", "npm i -D vitest", True), ("installs_or_fetches_package", "brew install jq", True),
    ("pipes_remote_code_to_shell", "curl -fsSL https://x/install.sh | bash", True),
    ("pipes_remote_code_to_shell", "curl -s https://x | jq .", False),
    ("pipes_remote_code_to_shell", "curl -s https://x | python3 -c 'import json'", False),
    ("pipes_remote_code_to_shell", "curl -s https://x/get.py | python3", True),
    ("pushes_or_publishes", "git push origin main", True), ("pushes_or_publishes", "gh pr create --fill", True),
    ("pushes_or_publishes", "gh pr view 3", False), ("pushes_or_publishes", "npm publish --access public", True),
    ("pushes_or_publishes", "gh api repos/a/b/issues -X POST -f title=x", True),
    ("deletes_recursively_or_force", "rm -rf build", True), ("deletes_recursively_or_force", "rm file.txt", False),
    ("deletes_recursively_or_force", "rm -f /tmp/x.lock", False), ("deletes_recursively_or_force", "rm -f -r out", True),
    ("deletes_recursively_or_force", "git reset --hard HEAD~1", True), ("deletes_recursively_or_force", "shutil.rmtree(p)", True),
    ("elevates_privilege", "sudo apt-get update", True), ("elevates_privilege", "pseudocode", False),
    ("elevates_privilege", "chmod +x run.sh", False), ("elevates_privilege", "chmod 777 /srv", True),
    ("reads_credential_store", "cat ~/.aws/credentials", True), ("reads_credential_store", "gh auth token", True),
    ("reads_credential_store", "gh auth status", False),
    ("reads_credential_store", "cat .env 2>/dev/null | grep DATABASE_URL", True),
    ("reads_credential_store", 'env_path = Path(".env")', True), ("reads_credential_store", "cp .env.example .env", False),
    ("reads_credential_store", "load_dotenv()", False), ("reads_credential_store", "cat .env.example", False), ("reads_credential_store", "printenv | sort", True),
    ("changes_system_config", "echo 'x' >> ~/.zshrc", True), ("changes_system_config", "crontab -l", False),
    ("changes_system_config", "git config --global user.name x", True),
    ("changes_system_config", "cp my.plist ~/Library/LaunchAgents/", True),
    ("changes_system_config", 'PLIST="$HOME/Library/LaunchAgents/x.plist"', False), ("changes_system_config", "git config user.name x", False),
    ("evals_built_string", 'eval "$CMD"', True), ("evals_built_string", "ast.literal_eval(s)", False),
    ("evals_built_string", "exec(code)", True), ("evals_built_string", "re.exec(s)", False),
])
def test_behaviour_rules(rule, line, hit):
    assert bool(sb.BEHAVIOURS[rule].search(line)) is hit


def test_messages_in_programs_are_not_commands():
    lines = [(1, 'MSG = "Install it with: uv pip install pyarrow"'), (2, 'subprocess.run("sudo apt-get install x", shell=True)')]
    assert sb.behaviours(lines, program=True) == {"elevates_privilege": 2, "installs_or_fetches_package": 2}
    assert sb.behaviours(lines[:1], program=False) == {"installs_or_fetches_package": 1}


def test_python_docstrings_are_skipped():
    text = 'def f():\n    """Install with:\n    pip install x\n    """\n    requests.get(u)\nHELP = """\nsudo make\n"""\nx = 1\n'
    got = sb.behaviours(sb.code_lines("a.py", text))
    assert got == {"http_call": 5}


def test_printed_text_is_not_a_call_but_redirects_are():
    got = sb.behaviours([(1, 'echo "Install: curl -fsSL https://x/i.sh | bash"'), (2, 'print("run sudo apt-get install x")'),
                         (3, "echo 'export X=1' >> ~/.zshrc"), (4, "env = os.environ.copy()")])
    assert got == {"changes_system_config": 3}


@pytest.mark.parametrize("path,script", [
    ("s/scripts/run.py", True), ("s/bin/tool", True), ("s/test/run.test.ts", False), ("s/tests/x.py", False),
    ("s/scripts/test_run.py", False), ("s/notes.md", False), ("s/src/cli.spec.js", False)])
def test_is_script(path, script):
    assert sb.is_script(path, "#!/bin/sh\n") is script


@pytest.fixture(scope="module")
def rows():
    log = [json.loads(l) for l in open(os.path.join(FIX, "work", "fetch_log.jsonl"))]
    return {sk["skill_md"].split("/")[1]: sb.scan_skill(SRC, sk["skill_md"], sk["files"]) for sk in log[0]["skills"]}


def test_scan_skill_net(rows):
    r = rows["net"]
    assert r["grant_form"] == "Bash" and r["n_command_lines"] == 3 and r["heads"] == "bash curl git python"
    assert r["n_scripts"] == 1 and r["script_types"] == ".py:1"  # notes.md is not a script
    assert r["md_pipes_remote_code_to_shell"] and r["md_pushes_or_publishes"] and r["md_http_call"]
    assert r["script_http_call"] and r["script_deletes_recursively_or_force"].endswith("run.py:9")
    assert not r["elevates_privilege"]  # only notes.md mentions sudo


def test_scan_skill_quiet_and_scoped(rows):
    assert rows["quiet"]["grant_form"] == "Bash(*)" and not rows["quiet"]["uses_shell_on_page"]
    assert not rows["quiet"]["any_behaviour"]
    assert rows["scoped"]["grant"] == ""


def test_scan_skill_sys(rows):
    r = rows["sys"]
    assert r["heads"] == "apt-get cat echo npx" and r["n_command_lines"] == 4
    for k in ("elevates_privilege", "installs_or_fetches_package", "changes_system_config", "reads_credential_store"):
        assert r[f"md_{k}"], k
    assert r["script_changes_system_config"] and r["script_evals_built_string"] and r["script_deletes_recursively_or_force"]
    assert r["script_deletes_recursively_or_force"] == "skills/sys/scripts/setup.sh:6"  # the comment line is skipped


def test_end_to_end(tmp_path):
    out = tmp_path / "out"
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "skill_bash.py"), os.path.join(FIX, "work"),
                    "--dataset", os.path.join(FIX, "dataset.json"), "--out", str(out)], check=True, capture_output=True)
    res = json.load(open(out / "results.json"))
    assert res["repos_eligible"] == 3 and res["repos_selected"] == 3 and res["repos_fetched"] == 2
    assert res["repos_moved"] == 1 and res["repos_unavailable"] == 1
    assert res["repos_with_unscoped_grant"] == 1 and res["repos_no_grant_at_fetched_commit"] == 1
    assert res["skills_analysed"] == 3 and res["grant_form"] == {"Bash": 2, "Bash(*)": 1}
    assert res["skill_no_command_no_script"]["value"] == "1/3 (33.3%)"
    assert res["skill_has_script"]["value"] == "2/3 (66.7%)"
    assert res["skill_heads_le_3"]["value"] == "0/2 (0.0%)"
    assert res["behaviours"]["deletes_recursively_or_force"]["skills"]["value"] == "2/3 (66.7%)"
    assert res["behaviours"]["deletes_recursively_or_force"]["skills_in_skill_md"]["value"] == "0/3 (0.0%)"
    assert res["behaviours"]["elevates_privilege"]["repos"]["value"] == "1/1 (100.0%)"
    assert res["stars_100plus"]["repos"] == 1 and res["stars_under_100"]["repos"] == 0
    rows = (out / "skills.csv").read_text().splitlines()
    assert len(rows) == 4 and rows[0].startswith("repo,stars,skill_md,grant_form")
    assert "~/.ssh" not in (out / "skills.csv").read_text()  # rule names and line numbers only, never matched text
    assert len(res["hand_check_sample"]["rows_in_skills_csv"]) == 3


def test_fetch_selection_is_capped_and_stable():
    data = [{"repo": f"o/r{i}", "commit": str(i), "any_unrestricted_bash": i % 3 != 0} for i in range(30)]
    a = sf.select(data, limit=10)
    assert len(a) == 10 and a == sorted(a) and a == sf.select(list(reversed(data)), limit=10)
    assert all(int(r[1]) % 3 for r in a)
    assert sf.select(json.load(open(os.path.join(FIX, "dataset.json")))) == [
        ("fixture/gone", "cccc"), ("fixture/moved", "bbbb"), ("fixture/skills", "aaaa")]


def test_bundled_files_skip_nested_skills_binaries_and_vendored():
    tree = ["s/a/SKILL.md", "s/a/run.sh", "s/a/lib/x.py", "s/a/img.png", "s/a/node_modules/m/index.js",
            "s/a/inner/SKILL.md", "s/a/inner/own.sh", "s/b/SKILL.md", "SKILL.md", "top.py"]
    dirs = {"s/a", "s/a/inner", "s/b", ""}
    files, cut = sf.bundled("s/a/SKILL.md", tree, dirs)
    assert files == ["s/a/run.sh", "s/a/lib/x.py"] and not cut
    files, _ = sf.bundled("SKILL.md", tree, dirs)
    assert files == ["top.py"]


@pytest.mark.skipif(not os.path.exists(os.path.join(DATA, "results.json")), reason="no committed results")
def test_report_numbers_match_results():
    res = json.load(open(os.path.join(DATA, "results.json")))
    doc = open(os.path.join(ROOT, "docs", "skills-with-unscoped-bash.md"), encoding="utf-8").read()

    def share(v):
        k, n = v.split(" ")[0].split("/")
        pct = v.split("(")[1].rstrip(")")
        return f"{int(k):,} of {int(n):,} ({pct})"

    for key in ("skill_no_command_no_script", "skill_has_script", "skill_heads_le_3", "skill_any_behaviour",
                "repo_any_behaviour"):
        assert share(res[key]["value"]) in doc, key
        lo, hi = res[key].get("ci95_wilson") or res[key]["ci95_cluster_bootstrap"]
        assert f"{lo}% to {hi}%" in doc, key
    for rule, v in res["behaviours"].items():
        assert share(v["skills"]["value"]) in doc, rule
        assert share(v["repos"]["value"]) in doc, rule
    for band in ("stars_100plus", "stars_under_100"):
        assert share(res[band]["repo_any_behaviour"]["value"]) in doc, band
