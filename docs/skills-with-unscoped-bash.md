# What do skills that ask for the whole shell do with it? Unscoped Bash in 3,715 public skills, October 2026

*Muhammad Basit Ali, 26 October 2026. A follow-up to [the October 2026 study](../README.md), using its sample and method. Data and text: CC BY 4.0. Code: MIT.*

A skill's `allowed-tools` line decides what the agent may do while the skill is active without asking first. `Bash(git status:*)` lets it run one command; a bare `Bash` (or `Bash(*)`) lets it run anything. The first report found that 407 of 2,621 repositories with skills (15.5%) give at least one skill that unscoped `Bash`, 10,073 declarations in all. That number says the door is open. This report asks what happens behind it: when a skill asks for the whole shell, which commands does it actually show, does it need more than a handful of them, and how often does it download, delete, push, escalate or read credentials?

## Key findings

- **Three in ten never use the shell they ask for.** 1,109 of 3,715 (29.9%) skills that grant unscoped Bash show no shell command in their `SKILL.md` and ship no script (95% CI 26.3% to 33.5%). Counting each distinct `SKILL.md` text once, it is 658 of 2,569 (25.6%). For these, deleting `Bash` from `allowed-tools`, or scoping it, loses nothing the page asks for.
- **Most of the rest need only a few commands.** Of the 2,545 skills that do show shell commands, 1,418 of 2,545 (55.7%) use three or fewer distinct commands (95% CI 51.0% to 60.4%), so three or fewer `Bash(command:*)` rules would cover everything they document; 806 (31.7%) use exactly one. The median is three.
- **A third do something worth reading first.** 1,289 of 3,715 (34.7%) skills, in 279 of 392 (71.2%) repositories, document or ship at least one of nine riskier behaviours (95% CI 31.0% to 38.7% for skills, 66.5% to 75.4% for repositories). The most common are installing or fetching a package (15.7%), a direct HTTP call (14.4%), recursive deletion or discarding git work (9.2%) and running a built string with `eval` (8.4%).
- **The rarer behaviours are the ones a reviewer cares about most.** 186 skills (5.0%) push or publish (`git push`, `gh pr create`, `npm publish`), 74 (2.0%) pipe a download straight into a shell (`curl ... | bash`), 61 (1.6%) use `sudo` or open permissions, 50 (1.3%) read a credential store or a `.env` file, and 16 (0.4%) change the machine beyond the project (cron, launch agents, shell start-up files, global git config).
- **The risk is mostly on the page, not in a hidden script.** Only 647 of 3,715 (17.4%) ship any script. Of the 1,289 skills with a riskier behaviour, 1,154 show it in the `SKILL.md` commands the agent is told to run; 135 have it only in a bundled script. Reading the `SKILL.md` finds most of it.
- **Popularity does not help.** In repositories with 100 or more stars, 27 of 44 (61.4%) have a skill with a riskier behaviour, against 252 of 348 (72.4%) below 100 stars; the intervals overlap.

Every share above is checked against [`data/2026-10/skill-bash/results.json`](../data/2026-10/skill-bash/results.json) by [`tests/test_skill_bash.py`](../tests/test_skill_bash.py) in CI.

> **What to check before you install a skill that asks for Bash**
>
> 1. Open its `SKILL.md` and find `allowed-tools`. A bare `Bash` or `Bash(*)` means the agent can run any command while the skill is active, without asking.
> 2. Search the page for shell blocks and inline commands. If there are none and the skill ships no scripts, which is three skills in ten, remove `Bash` from `allowed-tools` in your copy.
> 3. If there are commands, list their first words. More than half of these skills use three or fewer; replace `Bash` with `Bash(git status:*)`, `Bash(python scripts/run.py:*)` and so on, so anything else still prompts.
> 4. Look for these on the page and in every bundled script: `curl` or `wget` piped into `sh` or `bash`; `sudo`; `rm -rf`, `git reset --hard`, `git push --force`; `git push`, `gh pr create`, `npm publish`; `pip install`, `npm install`, `npx`, `uvx`; `eval`; reads of `~/.ssh`, `~/.aws`, a keychain, `gh auth token` or `.env`; writes to `crontab`, `~/Library/LaunchAgents`, `~/.zshrc` or `git config --global`.
> 5. Scripts that live outside the skill's folder (a plugin's `tools/` or a path under your home directory) run with the same grant. Read them too; this study did not.
> 6. Treat a package the skill installs or runs with `npx` or `uvx` as part of the skill, and pin its version.
> 7. Re-read after every update. A skill that is harmless today can add a command tomorrow, and an unscoped grant will let it run without a prompt.

## Why this matters

Claude Code and similar hosts treat `allowed-tools` as pre-approval: while a skill is active, the tools it lists run without the usual permission prompt. With a scoped rule such as `Bash(npm test:*)` the host still asks before anything else. With bare `Bash` it does not ask at all, so the only review a command gets is whatever the user did before installing the skill. A skill's instructions can also be changed by the content it reads (a web page, an issue, a file in the repository), so an unscoped grant turns a prompt injection that reaches the skill into shell access.

None of this says any skill is malicious. Most of what we found is ordinary developer work: install a dependency, run a test, call an API, clean up a build folder. The point is narrower. For a third of these skills the grant is unused, for more than half of the rest three rules would do, and for the third that do something riskier the user is the only checkpoint. A narrower grant costs the author a line and keeps the host's prompt in place for everything the skill did not say it needed.

## Method in brief

**Selection.** Every repository in [`data/2026-10/dataset.json`](../data/2026-10/dataset.json) with `any_unrestricted_bash` true (407), cut to the 400 with the smallest SHA-256 of `20261026/<repository>` to stay under the study's 400-repository ceiling for re-fetching. 393 were fetched at the commit recorded in the dataset on 26 October 2026; 7 were no longer available. One fetched repository had no unscoped grant in the files read, leaving 392.

**Fetch.** [`scripts/skill_bash_fetch.py`](../scripts/skill_bash_fetch.py) fetches each commit's tree without file contents, then downloads only the blobs it wants by object id and writes them out directly, so no checkout, git hook, filter or LFS step runs. It reads up to 2,000 `SKILL.md` files a repository (190,618 of 302,859 in all; the cap bites only on large mirrors) and finds 10,255 that grant unscoped Bash, using the same test as skill-scan-gate SSG607 (`Bash` or `Bash(*)` among the `allowed-tools` entries). For up to 20 of those a repository (the smallest SHA-256 of seed, repository and path; 112 repositories had more), it fetches the files bundled with the skill: every text file under the skill's folder that is not under a nested folder with its own `SKILL.md`, at most 300 files and 1 MB a file per skill, within the study's caps of 3,000 files and 30 MB a repository. Nothing was installed, built or run.

**What counts as a command.** [`scripts/skill_bash.py`](../scripts/skill_bash.py) reads the body of each `SKILL.md`: every line in a fenced block labelled as a shell (`bash`, `sh`, `zsh`, `console`, `powershell` and similar), lines in unlabelled or plain-text fences and inline code spans whose first word is a known command (the `KNOWN_COMMANDS` list in the script), with `$ ` prompts removed, backslash continuations and multi-line quoted arguments joined, and here-document bodies and comments skipped. Fences in a programming language (Python, JavaScript, JSON, YAML) are code to write, not commands, and are skipped. A **script** is a bundled file with a script extension or a shebang, other than a test file.

**Heads.** A command's head is its first word after environment assignments and wrappers such as `sudo`, `env` and `timeout`, for each part of a pipeline or `&&` chain. Shell keywords, loop variables, case labels and `true`, `false`, `break` and similar are not heads. The number of distinct heads is the number of `Bash(head:*)` rules that would cover the skill's documented commands.

**Behaviours.** Nine regular-expression rules (`BEHAVIOURS` in the script) run over the `SKILL.md` command lines and over every non-comment line of the bundled scripts:

| Rule | What it matches |
|---|---|
| `installs_or_fetches_package` | `pip install`, `npm install <pkg>`, `brew`, `apt`, `cargo` and `go install`, and download-and-run launchers (`npx`, `uvx`, `pipx run`, `bunx`, `pnpm dlx`) |
| `http_call` | `curl`, `wget`, `Invoke-WebRequest`, `scp`, `ssh` to a host, and HTTP client calls in Python, JavaScript, Go, Ruby and .NET (`git` and `gh` network use is not counted here) |
| `deletes_recursively_or_force` | `rm -r`, `Remove-Item -Recurse`, `shutil.rmtree`, `fs.rm(..., recursive)`, `find -delete`, `git reset --hard`, `git clean -f`, `git push --force`, `git branch -D` |
| `evals_built_string` | shell `eval` of a variable or command output, Python `exec()` or `eval()` of a non-literal, JavaScript `new Function()` |
| `pushes_or_publishes` | `git push`, `gh pr create` or `merge`, `gh issue create`, `gh release create`, `gh api` with a write method, `npm`, `cargo`, `twine` or `uv publish`, `docker push`, deploy commands |
| `pipes_remote_code_to_shell` | a download piped into `sh`, `bash`, `python` or `node` (not `python -c` reading data), `bash <(curl ...)`, decoded base64 piped to a shell, `iex (irm ...)` |
| `elevates_privilege` | `sudo`, `doas`, `su -c`, `runas`, `chmod 777` or setuid, `Set-ExecutionPolicy Bypass` |
| `reads_credential_store` | `~/.ssh`, `~/.aws`, `~/.kube`, `~/.docker`, `.netrc`, `.git-credentials`, gcloud and gh config, SSH key names, keychain and keyring reads, `gh auth token`, a bare `env` or `printenv`, a dump of the whole environment, or a direct read of a `.env` file (loading it through a dotenv library is not counted) |
| `changes_system_config` | `crontab`, `launchctl load`, `systemctl enable`, copying into `~/Library/LaunchAgents`, `schtasks /create`, `reg add`, appending to shell start-up files, writing under `/etc`, `git config --global`, `npm config set`, `defaults write` |

Text that a line only prints (`echo`, `printf`, `print(...)`, logging calls) is dropped before the rules run, so `echo "Install with: curl ... | sh"` is not a call, while `echo 'x' >> ~/.zshrc` still counts. In programs (as opposed to shell scripts), shell-style commands inside string literals are ignored unless the line hands them to a process (`subprocess`, `os.system`, `execSync` and similar), and Python docstrings are skipped. The output files hold rule names and line numbers only, never the matched text.

**Uncertainty.** Skill-level shares are clustered (up to 20 skills a repository, and copies of the same skill appear across repositories), so their 95% intervals come from 2,000 bootstrap resamples of repositories (seed 20261026). Repository-level shares carry 95% Wilson intervals. The same shares counted once per distinct `SKILL.md` text are in `results.json` under `distinct_text`.

## Hand check

We read 60 skills drawn at random from the 3,715 (the 60 with the smallest SHA-256 of seed 20261026, repository and path) against their `SKILL.md` and bundled scripts; the verdicts are in [`data/2026-10/skill-bash/hand-check.csv`](../data/2026-10/skill-bash/hand-check.csv).

- **Grant.** 60 of 60 grant unscoped Bash (95% CI 94.0% to 100%).
- **Shell on the page.** For 60 of 60 the label "shows a command or ships a script" matched our reading. Of the 26 labelled as showing neither, 26 of 26 really show no command and ship no script (95% CI 87.1% to 100%), but 5 describe shell work in prose ("check git log", "ensure `gh` is available") or delegate to a workflow file outside the skill, so "unused on the page" is not always "unused".
- **Three or fewer commands.** For 33 of 33 skills with commands the three-or-fewer class matched our reading (95% CI 89.6% to 100%). In 3 of them a line of prose inside a shell fence was counted as an extra head without changing the class.
- **Behaviours.** 17 of the 20 behaviour flags in the sample were correct (85.0%, 95% CI 64.0% to 94.8%). The 3 wrong ones were a regular expression string inside a code scanner read as `eval`, a mention of `git push` in inline code, and a `grep` pattern containing `uvx`. We found 2 missed behaviours, both in one skill: `npx -y` passed to `subprocess` as a list on the following line, and a read of a browser profile folder.

The rules were refined during this pass and two earlier passes over random skills, with a test for each fix: shell commands quoted in printed messages, docstrings and error strings; `rm -f` of a single file (no longer counted as deletion); `python -c` reading piped data; prose labels such as `Search for: x` inside shell fences; multi-line quoted arguments and here-documents; direct `.env` reads (added after the hand check found one). Because the last fixes were made on the same sample, the hand-check figures are somewhat optimistic; read the per-rule shares as approximate, and the rarer categories, where a few false positives matter most, with the most care.

## Results in detail

| Measure | Count | Denominator | Share | 95% CI |
|---|---|---|---|---|
| Skills with no shell command and no script | 1,109 | 3,715 | 29.9% | 26.3% to 33.5% |
| Skills that ship a script | 647 | 3,715 | 17.4% | 14.5% to 20.5% |
| Skills that show a shell command | 2,545 | 3,715 | 68.5% | 65.0% to 72.1% |
| Of those, three or fewer distinct commands | 1,418 | 2,545 | 55.7% | 51.0% to 60.4% |
| Of those, one command | 806 | 2,545 | 31.7% | 28.2% to 35.2% |
| Skills with any riskier behaviour | 1,289 | 3,715 | 34.7% | 31.0% to 38.7% |
| Repositories with a skill with any riskier behaviour | 279 | 392 | 71.2% | 66.5% to 75.4% |
| Repositories with a skill that ships a script | 179 | 392 | 45.7% | 40.8% to 50.6% |
| Repositories where no sampled skill shows a command or script | 31 | 392 | 7.9% | 5.6% to 11.0% |

By behaviour (skill-level intervals by resampling repositories, repository-level by Wilson):

| Behaviour | Skills | Share of 3,715 | 95% CI | In SKILL.md | In scripts | Repositories | Share of 392 | 95% CI |
|---|---|---|---|---|---|---|---|---|
| Installs or fetches a package | 585 of 3,715 (15.7%) | 15.7% | 14.0% to 17.6% | 564 | 31 | 220 of 392 (56.1%) | 56.1% | 51.2% to 61.0% |
| Direct HTTP call | 535 of 3,715 (14.4%) | 14.4% | 12.1% to 16.8% | 367 | 187 | 159 of 392 (40.6%) | 40.6% | 35.8% to 45.5% |
| Deletes recursively or discards git work | 342 of 3,715 (9.2%) | 9.2% | 6.3% to 12.5% | 291 | 76 | 86 of 392 (21.9%) | 21.9% | 18.1% to 26.3% |
| Runs a built string with eval | 312 of 3,715 (8.4%) | 8.4% | 5.5% to 11.7% | 269 | 45 | 58 of 392 (14.8%) | 14.8% | 11.6% to 18.7% |
| Pushes or publishes | 186 of 3,715 (5.0%) | 5.0% | 3.9% to 6.2% | 177 | 13 | 86 of 392 (21.9%) | 21.9% | 18.1% to 26.3% |
| Pipes a download into a shell | 74 of 3,715 (2.0%) | 2.0% | 0.9% to 3.4% | 71 | 7 | 24 of 392 (6.1%) | 6.1% | 4.1% to 8.9% |
| Elevates privilege | 61 of 3,715 (1.6%) | 1.6% | 1.2% to 2.1% | 54 | 10 | 47 of 392 (12.0%) | 12.0% | 9.1% to 15.6% |
| Reads a credential store or .env | 50 of 3,715 (1.3%) | 1.3% | 0.9% to 1.8% | 36 | 14 | 39 of 392 (9.9%) | 9.9% | 7.4% to 13.3% |
| Changes system configuration | 16 of 3,715 (0.4%) | 0.4% | 0.2% to 0.7% | 9 | 7 | 13 of 392 (3.3%) | 3.3% | 1.9% to 5.6% |

A skill can show a behaviour in both its `SKILL.md` and a script, so the two middle columns can add up to more than the total.

Two notes on clustering. One widely copied skill pack accounts for 291 of the 3,715 skills (in 21 repositories) and for 190 of the 312 `eval` flags: its skills start with `eval "$(<helper> ...)"` to load settings from a local helper. Without it, `eval` would be a minor category. And 2,569 of the 3,715 skills have distinct text; counting each text once, 39.1% show a riskier behaviour and 25.6% show no command and no script, so the headline shares hold.

The commands these skills use most, by the number of skills that show them: `git` (737), `echo` (694), `grep` (572), `mkdir` (494), `cd` (467), `head` (443), `python` (431), `cat` (428), `ls` (428), `find` (412), `rm` (379), `wc` (365), `tr` (335), `npm` (324) and `curl` (323).

## Limitations

- **The page, not run time.** We read what a skill tells the agent to run and what its scripts contain. An agent with unscoped Bash can run commands the page never mentions, and a script can build a command we cannot see statically. "No command on the page" is a statement about the page.
- **Scripts outside the skill folder are not read.** Many skills call tools in a plugin's shared folder or under the user's home directory (`${CLAUDE_PLUGIN_ROOT}/tools/...`, `~/.claude/skills/...`). Those commands count as heads, but their contents were not fetched, so script-level behaviours are a lower bound.
- **Static pattern matching.** The hand check bounds the error on what was flagged (17 of 20 flags correct) and found 2 misses in 60 skills; it cannot bound recall precisely. Commands written in an unusual form, or behaviours spread across lines, are missed.
- **Documented is not executed.** A `sudo apt-get install` in a setup section may be meant for the user rather than the agent; we count it because, with unscoped Bash, the agent can run it without a prompt.
- **Three rules is a lower bound on effort, not a design.** Three or fewer heads means three `Bash(head:*)` rules would cover the documented commands; whether a rule as broad as `Bash(python:*)` is narrow enough is a separate judgement.
- **A subset of a sample.** These are up to 20 skills from each of 392 repositories in the October 2026 sample that GitHub code search surfaced, not a census, and the per-repository cap means large mirrors weigh less than their file counts. The 10,255 grants found at the fetched commits differ slightly from the first report's 10,073 because the file set and caps differ; no published number changes.

## Reproduce it

```sh
python scripts/skill_bash_fetch.py /tmp/bash        # about 25 minutes, 400 repositories, SKILL.md and bundled files only
python scripts/skill_bash.py /tmp/bash              # writes data/2026-10/skill-bash/
python -m pytest -q tests/test_skill_bash.py        # fixtures, no network
```

Repositories change and can disappear, so a later fetch may differ slightly; the fetch pins each repository to the commit in the dataset to keep that small. The outputs are [`results.json`](../data/2026-10/skill-bash/results.json) (every number here, with its interval, and the hand-check sample's row numbers), [`skills.csv`](../data/2026-10/skill-bash/skills.csv) (one row per skill: repository, path, grant form, number of command lines, heads, scripts and, for each rule, the first `SKILL.md` line or script line that matched, with a hash of the `SKILL.md` text) and [`repos.csv`](../data/2026-10/skill-bash/repos.csv) (one row per selected repository, with the fetched commit and counts).

No number in the first edition or in the earlier follow-up reports changes.
