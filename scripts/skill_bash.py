"""Measure what skills that grant unscoped Bash do with the shell, in the October 2026 repositories.

Usage: python scripts/skill_bash.py WORKDIR [--dataset data/2026-10/dataset.json] [--out data/2026-10/skill-bash]

Reads the files fetched by scripts/skill_bash_fetch.py (WORKDIR/src and WORKDIR/fetch_log.jsonl). Static only:
nothing is installed or run, and no matched text is written out, only rule names and line numbers. Standard
library only.

For each skill whose allowed-tools grants "Bash" or "Bash(*)" (the skill-scan-gate SSG607 test), it reads:

- the commands in its SKILL.md: lines in fenced blocks labelled as a shell (bash, sh, zsh, console, powershell
  and similar), lines in unlabelled or plain-text fenced blocks and inline code spans whose first word is a known
  command (KNOWN_COMMANDS), with "$ " prompts removed and backslash continuations joined;
- the scripts bundled with it: files under the skill's folder with a script extension (SCRIPT_EXT) or a shebang.

Each command's first word (after environment assignments, sudo, env, time and similar wrappers) is its head; the
number of distinct heads is the number of Bash(head:*) rules that would cover the skill's documented commands.
Behaviour rules (BEHAVIOURS) are regular expressions applied to the SKILL.md command lines and to every
non-comment line of the bundled scripts. Writes skills.csv, repos.csv and results.json.
"""
import argparse, csv, hashlib, json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEED = 20261026
SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console", "terminal", "shell-session", "sh-session", "shellsession",
               "powershell", "ps1", "pwsh", "ps", "fish", "cmd", "bat", "batch", "ksh"}
# Unlabelled or plain-text fences: a line counts when its first word is a known command. Fences in a programming
# language (python, js, json, yaml...) are code, not commands, and are skipped.
PLAIN_LANGS = {"", "text", "txt", "plain", "plaintext", "none", "output"}
KNOWN_COMMANDS = {
    "git", "gh", "python", "python3", "py", "node", "npm", "npx", "pnpm", "yarn", "bun", "bunx", "deno", "uv", "uvx",
    "pip", "pip3", "pipx", "poetry", "curl", "wget", "bash", "sh", "zsh", "cd", "ls", "cat", "grep", "rg", "find",
    "mkdir", "rm", "cp", "mv", "touch", "chmod", "chown", "sudo", "docker", "kubectl", "helm", "terraform", "aws",
    "gcloud", "az", "make", "go", "cargo", "rustc", "jq", "yq", "sed", "awk", "echo", "head", "tail", "wc", "sort",
    "xargs", "tar", "unzip", "zip", "ssh", "scp", "rsync", "brew", "apt", "apt-get", "yum", "dnf", "pacman",
    "export", "source", "open", "xdg-open", "pytest", "ruff", "black", "eslint", "prettier", "tsc", "java", "mvn",
    "gradle", "dotnet", "ruby", "gem", "bundle", "php", "composer", "perl", "psql", "mysql", "sqlite3", "redis-cli",
    "ffmpeg", "convert", "magick", "pandoc", "code", "claude", "codex", "gemini", "vercel", "wrangler", "firebase",
    "supabase", "flyctl", "heroku", "ollama", "tmux", "screen", "osascript", "pbcopy", "pbpaste", "say", "diff",
    "tree", "pwd", "which", "env", "printenv", "kill", "pkill", "ps", "lsof", "crontab", "launchctl", "systemctl",
    "Invoke-WebRequest", "Invoke-RestMethod", "Remove-Item", "Get-ChildItem", "Set-ExecutionPolicy", "pwsh",
    "powershell", "iwr", "irm", "tee", "ln", "du", "df", "date", "sleep", "base64", "openssl", "gpg", "eval",
    "playwright", "agent-browser", "mcp", "skills", "sqlcmd", "dbt", "bq", "gsutil", "firebase", "netlify", "doctl",
    "railway", "pm2", "nohup", "timeout", "time", "watch", "less", "more", "vim", "nano", "cut", "tr", "uniq",
    "basename", "dirname", "realpath", "stat", "file", "md5sum", "shasum", "sha256sum", "nc", "ncat", "dig",
    "nslookup", "ping", "traceroute", "nmap", "rmdir", "test", "true", "false", "set", "unset", "alias", "./",
    "semgrep", "trivy", "bandit", "gitleaks", "trufflehog", "snyk", "ansible", "ansible-playbook", "pre-commit",
    "mypy", "pyright", "jest", "vitest", "cypress", "lighthouse", "k6", "hugo", "flutter", "dart", "xcodebuild",
    "xcrun", "swift", "adb", "gradlew", "./gradlew", "sam", "cdk", "pulumi", "serverless", "sls", "rails", "rake",
    "alembic", "prisma", "drizzle-kit", "kubectx", "minikube", "kind", "podman", "docker-compose", "just", "task",
    "cmake", "ninja", "clang", "gcc", "javac", "kotlin", "mix", "elixir", "stack", "cabal", "zig", "rustup", "nvm",
    "pyenv", "conda", "mamba", "pdm", "hatch", "tox", "nox", "twine", "turbo", "nx", "lerna", "deno", "tsx",
    "ts-node", "biome", "golangci-lint", "shellcheck", "hadolint", "actionlint", "yamllint", "markdownlint",
    "codeql", "osv-scanner", "grype", "syft", "cosign", "vault", "op", "doppler", "stripe", "shopify", "expo",
    "eas", "fastlane", "pod", "sf", "sfdx", "databricks", "snowsql", "duckdb", "clickhouse", "mongosh", "kafka"}
TRIVIAL = {"true", "false", ":", "break", "continue", "return", "exit", "shift", "local", "declare", "typeset", "wait"}  # "|| true" and similar are not commands anyone needs to allow
WRAPPERS = {"sudo", "env", "time", "nohup", "exec", "command", "builtin", "timeout", "doas", "xargs", "nice", "stdbuf"}
KEYWORDS = {"if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done", "case", "esac", "function",
            "{", "}", "[[", "]]", "[", "]", "!", "in", "select", "(", ")", "&&", "||", "-", "--", "<<", ">>", ">", "<"}
SCRIPT_EXT = {".sh", ".bash", ".zsh", ".ksh", ".fish", ".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".rb",
              ".pl", ".ps1", ".psm1", ".bat", ".cmd", ".php", ".lua", ".go", ".rs", ".swift", ".kts", ".r", ".R"}

R = re.compile
BEHAVIOURS = {
    # A direct HTTP, socket or remote-shell call.
    "http_call": R(r"(?<![\w./-])(?:curl|wget|aria2c|httpie|xh|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|scp|sftp)\b(?![-.\w])"
                   r"|(?<![\w.-])ssh\s+(?:-\S+\s+)*[\w.-]*@?[\w.-]+\.[a-z]{2,}"
                   r"|\brequests\.(?:get|post|put|patch|delete|head|request|Session)\b|\burllib\.request\b|\burlopen\("
                   r"|\bhttpx\.(?:get|post|put|patch|delete|Client|AsyncClient|request|stream)\b|\baiohttp\.ClientSession\b"
                   r"|\bhttp\.client\.HTTPS?Connection\b|(?<![\w.$])fetch\(\s*[`'\"a-zA-Z_]|\baxios(?:\.\w+)?\("
                   r"|\b(?:https?)\.(?:get|request)\(|\bnew\s+WebSocket\(|\bwebsockets?\.connect\(|\bsocket\.create_connection\("
                   r"|\bnet/http\b|\bhttp\.(?:Get|Post|NewRequest)\(|\bNet::HTTP\b|\bWebClient\b|\bHttpClient\b|\bgot\(\s*['`\"]"),
    # Installs a package, or downloads and runs one (npx, uvx and similar).
    "installs_or_fetches_package": R(
        r"(?<![\w-])(?:pip3?|python3?\s+-m\s+pip|uv\s+pip)\s+install\b|(?<![\w-])uv\s+(?:add|tool\s+install)\b"
        r"|(?<![\w-])(?:npm|pnpm|bun)\s+(?:install|i|add)\s+(?:-\S+\s+)*[@\w]|(?<![\w-])yarn\s+(?:global\s+)?add\b"
        r"|(?<![\w-])npm\s+(?:install|i)\s+-g\b|(?<![\w-])(?:brew|cargo|gem|pipx)\s+install\b|(?<![\w-])go\s+(?:install|get)\b"
        r"|(?<![\w-])(?:apt|apt-get|yum|dnf|pacman|apk|choco|winget|scoop)\s+(?:-\S+\s+)*(?:install|add|-S)\b"
        r"|(?<![\w./-])(?:npx|bunx|pnpx|uvx)\s+\S|(?<![\w-])(?:pnpm|yarn)\s+dlx\b|(?<![\w-])pipx\s+run\b|(?<![\w-])uv\s+tool\s+run\b"),
    # Pipes downloaded code into an interpreter, or decodes and runs it.
    "pipes_remote_code_to_shell": R(
        r"\b(?:curl|wget|fetch)\b[^\n|]*\|\s*(?:sudo\s+)?(?:env\s+)?(?:ba|z|da|k|fi)?sh\b"
        r"|\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:python[0-9.]*|node|perl|ruby)\b(?!\s+-[ce]\b)"
        r"|\b(?:ba|z)?sh\s+(?:-c\s+)?[\"']?<?\(\s*(?:curl|wget)\b|\b(?:source|\.)\s+<\(\s*(?:curl|wget)\b"
        r"|\beval\s+[\"']?\$\(\s*(?:curl|wget)\b|\bbase64\s+(?:-d|--decode|-D)\b[^\n|]*\|\s*(?:ba|z)?sh\b"
        r"|\b(?:iex|Invoke-Expression)\b[^\n]*(?:iwr|irm|Invoke-WebRequest|Invoke-RestMethod|DownloadString)"),
    # Publishes or pushes: git push, a gh write, a package publish, an image push.
    "pushes_or_publishes": R(
        r"(?<![\w-])git\s+(?:-\S+\s+)*push\b|(?<![\w-])gh\s+(?:pr\s+(?:create|merge|comment|review|close|edit)"
        r"|issue\s+(?:create|comment|close|edit)|release\s+(?:create|upload|delete)|repo\s+(?:create|delete|edit)"
        r"|api\b[^\n]*(?:-X\s*|--method[\s=]+)(?:POST|PUT|PATCH|DELETE)|gist\s+create|workflow\s+run|secret\s+set)\b"
        r"|(?<![\w-])(?:npm|pnpm|yarn|cargo|gem)\s+publish\b|(?<![\w-])twine\s+upload\b|(?<![\w-])(?:uv|poetry)\s+publish\b"
        r"|(?<![\w-])docker\s+push\b|(?<![\w-])vercel\s+(?:deploy|--prod)\b|(?<![\w-])wrangler\s+(?:deploy|publish)\b"),
    # Deletes recursively or by force, or discards git history or work.
    "deletes_recursively_or_force": R(
        r"(?<![\w-])rm\s+(?:-\w+\s+)*(?:-[a-zA-Z]*[rR][a-zA-Z]*\s+|--recursive\s+)|(?<![\w-])rmdir\s+/s\b"
        r"|\bRemove-Item\b[^\n]*-(?:Recurse|Force)\b|\bshutil\.rmtree\(|\bfs(?:Promises)?\.(?:rm|rmSync|rmdir|rmdirSync)\([^\n]*recursive"
        r"|\brimraf\b|\bos\.RemoveAll\(|\bFileUtils\.rm_r[f]?\b|(?<![\w-])git\s+reset\s+--hard\b|(?<![\w-])git\s+clean\s+-[a-zA-Z]*f"
        r"|(?<![\w-])git\s+push\b[^\n]*(?:\s-f\b|--force)|(?<![\w-])git\s+branch\s+-D\b|\bfind\b[^\n]*\s-delete\b"),
    # Raises privilege or opens permissions.
    "elevates_privilege": R(
        r"(?<![\w-])(?:sudo|doas)\s+\S|(?<![\w-])su\s+-c\b|\brunas\b|(?<![\w-])chmod\s+(?:-R\s+)?(?:777|666|a\+rwx|[ugo]*\+s)\b"
        r"|\bSet-ExecutionPolicy\b[^\n]*(?:Bypass|Unrestricted)|-ExecutionPolicy\s+Bypass\b|\bStart-Process\b[^\n]*-Verb\s+RunAs"),
    # Reads a credential store: SSH, cloud and registry credential files, keychains, browser stores, gh auth token,
    # a .env file, or dumps the whole environment.
    "reads_credential_store": R(
        r"(?<![\w-])(?:~|\$HOME|\$\{HOME\}|%USERPROFILE%)/\.(?:aws|ssh|gnupg|kube|azure|docker)(?=/|\b)"
        r"|\.netrc\b|\.git-credentials\b|\.config/gcloud\b|\.config/gh/hosts\.yml|\bid_(?:rsa|ed25519|ecdsa|dsa)\b"
        r"|\bsecurity\s+(?:dump-keychain|find-generic-password|find-internet-password)\b|Library/Keychains"
        r"|\bsecret-tool\s+lookup\b|\bkeyring\.get_password\(|\bcmdkey\s+/list\b|\bLogin\s+Data\b|\bCookies\.binarycookies\b"
        r"|(?<![\w-])gh\s+auth\s+token\b|(?:^|;|&&|\|\||\$\(|`)\s*(?:printenv|env)\s*(?:$|>|\|(?!\|)|;|&|\)|`)"
        r"|\b(?:json\.dumps|print|pprint)\(\s*(?:dict\()?\s*os\.environ\s*\)?\s*[),]"
        r"|\bJSON\.stringify\(\s*process\.env\s*\)|/proc/(?:self|\d+)/environ\b"
        # Reads a .env file directly (loading it through a dotenv library is not counted).
        r"|(?<![\w-])(?:cat|less|more|head|tail|grep|rg|source|\.)\s+(?:-\S+\s+)*[^\n|;&]*?(?<![\w-])\.env(?!\.(?:example|sample|template|dist))(?:\.\w+)?\b"
        r"|\bPath\(\s*[\"']\.env[\"']\s*\)|\bopen\(\s*[\"'][^\"'\n]*\.env[\"']|readFileSync\([^)\n]*\.env[\"'`]"),
    # Changes the machine beyond the project: scheduled jobs, services, login items, shell start-up files,
    # global tool configuration, /etc.
    "changes_system_config": R(
        r"(?<![\w-])crontab\s+(?!-l\b)|(?<![\w-])launchctl\s+(?:load|bootstrap|enable|submit)\b|(?<![\w-])systemctl\s+(?:--user\s+)?(?:enable|start|daemon-reload)\b"
        r"|(?<![\w-])(?:cp|mv|ln\s+-\w+|install)\s+(?:-\S+\s+)*\S+\s+[\"']?(?:~|\$HOME|\$\{HOME\})/Library/Launch(?:Agents|Daemons)\b"
        r"|(?:>|\btee\b)\s*[\"']?(?:~|\$HOME|\$\{HOME\})/Library/Launch(?:Agents|Daemons)/|(?<![\w-])schtasks\s+/create\b|(?<![\w-])reg\s+add\b|\bNew-ItemProperty\b[^\n]*HK(?:LM|CU)"
        r"|>>?\s*[\"']?(?:~|\$HOME|\$\{HOME\})/\.(?:bashrc|zshrc|bash_profile|profile|zprofile|config/fish/config\.fish)\b"
        r"|(?:open|write_text|appendFile(?:Sync)?|writeFile(?:Sync)?)\([^\n]*\.(?:bashrc|zshrc|bash_profile|zprofile)\b"
        r"|(?:>|\btee\b(?:\s+-a)?)\s*/etc/|(?<![\w-])git\s+config\s+--global\b|(?<![\w-])npm\s+config\s+set\b|(?<![\w-])defaults\s+write\b"),
    # Builds a string and runs it: shell eval, Python exec or eval, JavaScript eval or new Function.
    "evals_built_string": R(r"(?<![\w-])eval\s+[\"'$`]|(?<![.\w])exec\(\s*(?![\"'])|(?<![.\w])eval\(\s*(?![\"'])|\bnew\s+Function\("),
}
B_ORDER = list(BEHAVIOURS)


def parse_front_matter(text):
    """The same small YAML subset as skill-scan-gate 0.2.0: top-level key: value pairs, continuation lines joined
    with spaces. Returns {key: (value, line)} or None when there is no closed front matter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip().lstrip("﻿") != "---":
        return None
    out, key, buf, start, end = {}, None, [], 0, None
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() in ("---", "..."):
            end = i
            break
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            if key is not None:
                out[key] = (" ".join(buf).strip(), start)
            key, start = m.group(1), i
            value = m.group(2).strip()
            buf = [] if value in ("|", ">", "|-", ">-", "|+", ">+") else [value]
        elif key is not None:
            buf.append(line.strip())
    if end is None:
        return None
    if key is not None:
        out[key] = (" ".join(buf).strip(), start)
    fm = {k: (v.strip().strip("\"'"), n) for k, (v, n) in out.items()}
    fm["__end__"] = ("", end)
    return fm


def tool_entries(tools):
    return [e.strip().removeprefix("- ").strip().strip("\"'") for e in re.split(r",|\s+-\s+", tools.strip("[]").lstrip())]


def unscoped_bash(text):
    """The allowed-tools value when it grants Bash with no command scoping (skill-scan-gate SSG607), else None."""
    fm = parse_front_matter(text)
    if not fm or "allowed-tools" not in fm:
        return None
    tools = fm["allowed-tools"][0]
    if any(e in {"Bash", "Bash(*)"} for e in tool_entries(tools)):
        return tools
    return None


def first_word(line):
    m = re.match(r"\s*([^\s;|&()<>]+)", line)
    return m.group(1) if m else ""


def is_command_line(line):
    w = first_word(line)
    return w in KNOWN_COMMANDS or w.startswith(("./", "~/", "$HOME/", "${CLAUDE", "$CLAUDE", "scripts/", "bin/"))


def command_lines(text):
    """(line number, command) pairs a SKILL.md asks to be run in a shell, after the front matter."""
    fm = parse_front_matter(text)
    start = fm["__end__"][1] if fm else 0
    lines = text.splitlines()
    out, fence, lang, pending, pend_no, heredoc = [], None, "", "", 0, None

    def keep(no, body):
        if LABEL.match(body) and not is_command_line(body):
            return  # "Search for: x" inside a shell fence is prose
        if lang in SHELL_LANGS or (lang in PLAIN_LANGS and is_command_line(body)):
            out.append((no, body))

    for i, raw in enumerate(lines, 1):
        if i <= start:
            continue
        s = raw.strip()
        m = re.match(r"^(`{3,}|~{3,})\s*([\w+-]*)", s)
        if m and (fence is None or s.startswith(fence)):
            if fence is None:
                fence, lang = m.group(1), m.group(2).lower()
            else:
                if pending:
                    keep(pend_no, pending)
                fence, lang = None, ""
            pending, heredoc = "", None
            continue
        if fence is not None:
            if heredoc is not None:  # the body of a here-document is data, not commands
                if s == heredoc:
                    heredoc = None
                continue
            body = re.sub(r"^(?:\$|>|PS>|PS [^>]*>|❯)\s+", "", s)
            if not body or (not pending and body.startswith(("#", "//", "REM ", "::"))):
                continue
            if pending:
                body, no = pending + " " + body, pend_no
            else:
                no = i
            if body.endswith("\\") or body.endswith(" `"):
                pending, pend_no = body[:-1].rstrip(), no
                continue
            if len(re.findall(r'(?<!\\)"', body)) % 2 and len(body) < 4000:
                pending, pend_no = body, no  # a quoted argument runs on to the next line
                continue
            pending = ""
            keep(no, body)
            h = re.search(r"<<-?\s*['\"]?([A-Za-z_]\w*)['\"]?", body)
            if h:
                heredoc = h.group(1)
        else:
            for span in re.findall(r"(?<!`)`([^`\n]+)`(?!`)", raw):
                span = re.sub(r"^\$\s+", "", span.strip())
                if " " in span and is_command_line(span):
                    out.append((i, span))
    return out


LABEL = R(r"^[A-Z][\w ]{0,40}:(?:\s|$)")
SPLIT = R(r"\s*(?:&&|\|\||;|\||&(?!>))\s*")


def heads(cmd):
    """The distinct command heads in one command line, after wrappers and environment assignments."""
    out = []
    cmd = QUOTED.sub('""', cmd)  # a | or ; inside a quoted jq or sed program is not a pipe
    cmd = re.sub(r"\$\(|`", " ; ", cmd)
    for seg in SPLIT.split(cmd):
        toks = seg.strip().split()
        while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or toks[0] in WRAPPERS or toks[0] in KEYWORDS):
            wrapper = toks[0] in WRAPPERS
            toks = toks[1:]
            while wrapper and toks and (toks[0].startswith("-") or re.match(r"^\d+[smh]?$", toks[0])):
                toks = toks[1:]
        if not toks or seg.strip().split()[0] in ("for", "case", "select"):
            continue  # "for x in ...": the loop variable is not a command
        if toks[0].endswith(")") and "(" not in toks[0] and len(toks) > 1:
            toks = toks[1:]  # a case label such as http) before its command
        w = toks[0].strip("\"'()")
        if not w or w in KEYWORDS or w in TRIVIAL or w.startswith(("#", "-", "<", ">", "$((")) or re.match(r"^[\d>&]+$", w):
            continue
        if w.endswith(":") or not re.match(r"^[\w./~${}@+%-]+$", w):
            continue  # "Reference: x" in a shell fence is prose, not a command
        out.append(w)
    return out


def is_script(path, text):
    """A script bundled with the skill: a script extension or a shebang, and not a test file."""
    if TEST_FILE.search(path):
        return False
    ext = os.path.splitext(path)[1]
    return ext in SCRIPT_EXT or (ext == "" and text.startswith("#!"))


COMMENT = R(r"^\s*(?:#(?!!)|//|/\*|\*|--\s|REM\s|::|<#)")
# Lines that only print text: the quoted text is dropped before the rules run, so "echo 'run: curl ... | sh'" is
# not a call, while a redirect such as echo 'x' >> ~/.zshrc still counts.
OUTPUT = R(r"^\s*(?:echo|printf|print|puts|say|Write-(?:Host|Output|Error)|console\.(?:log|error|warn|info)|"
           r"(?:self\.)?(?:logger|log|logging)\.\w+|log_\w+|print_\w+|error|warn|warning|die|fail|info|usage)\b\s*\(?")
QUOTED = R(r"\"(?:[^\"\\\n]|\\.)*\"|'[^'\n]*'|`[^`\n]*`")
TEST_FILE = R(r"(?:^|/)(?:tests?|__tests__|spec|e2e|fixtures?)/|(?:^|/)test_[^/]*\.py$|_test\.(?:py|go)$|\.(?:test|spec)\.[cm]?[jt]sx?$")


def for_match(line):
    return QUOTED.sub('""', line) if OUTPUT.match(line) else line


def code_lines(path, text):
    """(line number, line) pairs of a script without comment lines and, in Python, without docstrings and other
    triple-quoted blocks, whose usage text often names commands the script never runs."""
    out, in_triple = [], None
    py = os.path.splitext(path)[1] == ".py" or text.startswith("#!/usr/bin/env python")
    for i, l in enumerate(text.splitlines(), 1):
        if py:
            marks = [m for m in ('"""', "'''") if m in l]
            if in_triple:
                if in_triple in l:
                    in_triple = None
                continue
            if marks:
                m = marks[0]
                if l.count(m) % 2 == 1:
                    in_triple = m
                if l.strip().startswith(("r" + m, m, "f" + m, "b" + m)) or re.match(r"^\s*\w+\s*=\s*[rfb]?" + m, l):
                    continue
        if not COMMENT.match(l):
            out.append((i, l))
    return out


# In a program (not a shell script), shell-style commands inside string literals are usually messages ("Install
# with: pip install x"), unless the line hands them to a shell or a process.
SHELL_STYLE = {"installs_or_fetches_package", "pushes_or_publishes", "elevates_privilege", "deletes_recursively_or_force",
               "changes_system_config", "pipes_remote_code_to_shell"}
PROGRAM_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".rb", ".php", ".lua", ".go", ".rs", ".swift", ".kts", ".r", ".R", ".pl"}
RUNS = R(r"\b(?:subprocess|os\.system|os\.popen|Popen|check_output|check_call|execSync|execFileSync|spawnSync|spawn|"
         r"exec(?:File)?|child_process|shell_exec|system|run_cmd|run_command|sh|bash|\$|Command::new|exec\.Command)\b\s*[(.`]")


def behaviours(lines, program=False):
    """{rule: first line number} over (line number, text) pairs."""
    hit = {}
    for no, line in lines:
        line = for_match(line)
        bare = QUOTED.sub('""', line) if program and not RUNS.search(line) else line
        for k, rx in BEHAVIOURS.items():
            if k not in hit and rx.search(bare if k in SHELL_STYLE else line):
                hit[k] = no
    return hit


def scan_skill(root, skill_md, files):
    text = open(os.path.join(root, skill_md), encoding="utf-8", errors="replace").read()
    grant = unscoped_bash(text)
    fm = parse_front_matter(text) or {}
    entries = tool_entries(fm["allowed-tools"][0]) if "allowed-tools" in fm else []
    cmds = command_lines(text)
    hd = Counter(x for _, c in cmds for x in heads(c))
    md_hits = behaviours(cmds)
    scripts, sc_hits, langs = [], {}, Counter()
    for f in files:
        p = os.path.join(root, f)
        if not os.path.isfile(p):
            continue
        try:
            t = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if not is_script(f, t):
            continue
        scripts.append(f)
        langs[os.path.splitext(f)[1].lower() or "shebang"] += 1
        lines = code_lines(f, t)
        for k, no in behaviours(lines, program=os.path.splitext(f)[1] in PROGRAM_EXT).items():
            sc_hits.setdefault(k, f"{f}:{no}")
    row = {"skill_md": skill_md, "grant": grant or "", "grant_form": "Bash(*)" if "Bash(*)" in entries else "Bash",
           "also_scoped_bash": any(e.startswith("Bash(") and e != "Bash(*)" for e in entries),
           "n_tools_listed": len([e for e in entries if e]), "sha256": hashlib.sha256(text.encode()).hexdigest(),
           "n_command_lines": len(cmds), "n_heads": len(hd), "heads": " ".join(sorted(re.sub(r"[A-Za-z0-9]{32,}", "<long>", x) for x in hd)), "n_files": len(files),
           "n_scripts": len(scripts), "script_types": " ".join(f"{k}:{v}" for k, v in sorted(langs.items()))}
    for k in B_ORDER:
        row[f"md_{k}"] = md_hits.get(k, "")
        row[f"script_{k}"] = sc_hits.get(k, "")
        row[k] = k in md_hits or k in sc_hits
    row["any_behaviour"] = any(row[k] for k in B_ORDER)
    row["uses_shell_on_page"] = bool(cmds) or bool(scripts)
    return row


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; hw = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (round(100 * max(0, c - hw), 1), round(100 * min(1, c + hw), 1))


def cluster_ci(groups, B=2000, seed=SEED):
    import random
    groups = [g for g in groups if g[1]]
    if not groups:
        return (0.0, 0.0)
    rnd = random.Random(seed); est = []
    for _ in range(B):
        s = [groups[rnd.randrange(len(groups))] for _ in groups]
        n = sum(x[1] for x in s); est.append(sum(x[0] for x in s) / n if n else 0)
    est.sort()
    return (round(100 * est[int(0.025 * B)], 1), round(100 * est[int(0.975 * B) - 1], 1))


def frac(k, n):
    return f"{k}/{n} ({100 * k / n:.1f}%)" if n else f"{k}/0"


def repo_share(repos, pred):
    k = sum(1 for r in repos if pred(r)); n = len(repos)
    return {"value": frac(k, n), "ci95_wilson": wilson(k, n)}


def skill_share(skills, pred):
    by = {}
    for s in skills:
        g = by.setdefault(s["repo"], [0, 0]); g[1] += 1; g[0] += bool(pred(s))
    k = sum(g[0] for g in by.values()); n = sum(g[1] for g in by.values())
    return {"value": frac(k, n), "ci95_cluster_bootstrap": cluster_ci(list(by.values())), "repos": len(by)}


def hand_sample(skills, n=60):
    order = sorted(range(len(skills)), key=lambda i: hashlib.sha256(f"{SEED}/{skills[i]['repo']}/{skills[i]['skill_md']}".encode()).hexdigest())
    return sorted(order[:n])


def summarise(fetched, skills, selected, eligible):
    ok = [m for m in fetched if m["state"] in ("pinned", "moved")]
    by_repo = {}
    for s in skills:
        by_repo.setdefault(s["repo"], []).append(s)
    repos = [{"repo": r, "skills": v, **{k: any(s[k] for s in v) for k in B_ORDER + ["any_behaviour", "uses_shell_on_page"]},
              "any_script": any(s["n_scripts"] for s in v), "stars": v[0]["stars"]} for r, v in sorted(by_repo.items())]
    res = {"selection": "repositories in data/2026-10/dataset.json with any_unrestricted_bash true; the 400 with the "
                        "smallest SHA-256 of '20261026/<repo>'",
           "repos_eligible": eligible, "repos_selected": selected, "repos_fetched": len(ok),
           "repos_pinned_commit": sum(1 for m in ok if m["state"] == "pinned"),
           "repos_moved": sum(1 for m in ok if m["state"] == "moved"),
           "repos_unavailable": selected - len(ok),
           "skill_md_in_fetched_repos": sum(m["n_skill_md"] for m in ok),
           "skill_md_read": sum(m["n_skill_md_read"] for m in ok),
           "unscoped_grants_found": sum(m["n_unscoped"] for m in ok),
           "repos_with_unscoped_grant": len(repos),
           "repos_no_grant_at_fetched_commit": len(ok) - len(repos),
           "skills_analysed": len(skills), "skills_distinct_text": len({s["sha256"] for s in skills}),
           "repos_capped_at_20_skills": sum(1 for m in ok if m["n_unscoped"] > 20),
           "skills_with_truncated_files": sum(1 for s in skills if s["truncated"])}
    res["grant_form"] = dict(Counter(s["grant_form"] for s in skills))
    res["skill_no_command_no_script"] = skill_share(skills, lambda s: not s["uses_shell_on_page"])
    res["skill_has_script"] = skill_share(skills, lambda s: s["n_scripts"] > 0)
    res["skill_has_command"] = skill_share(skills, lambda s: s["n_command_lines"] > 0)
    res["skill_heads_le_3"] = skill_share([s for s in skills if s["n_command_lines"]], lambda s: s["n_heads"] <= 3)
    res["skill_heads_le_1"] = skill_share([s for s in skills if s["n_command_lines"]], lambda s: s["n_heads"] <= 1)
    res["skill_any_behaviour"] = skill_share(skills, lambda s: s["any_behaviour"])
    res["skill_also_scoped_bash"] = skill_share(skills, lambda s: s["also_scoped_bash"])
    hc = sorted(s["n_heads"] for s in skills if s["n_command_lines"])
    res["heads_median_when_commands"] = hc[len(hc) // 2] if hc else 0
    heads_all = Counter(h for s in skills for h in set(s["heads"].split()) if h)
    res["top_heads_by_skills"] = heads_all.most_common(15)
    res["behaviours"] = {}
    for k in B_ORDER:
        res["behaviours"][k] = {
            "skills": skill_share(skills, lambda s, k=k: s[k]),
            "skills_in_skill_md": skill_share(skills, lambda s, k=k: s[f"md_{k}"] != ""),
            "skills_in_scripts": skill_share(skills, lambda s, k=k: s[f"script_{k}"] != ""),
            "repos": repo_share(repos, lambda r, k=k: r[k])}
    distinct = {}
    for s in skills:
        distinct.setdefault(s["sha256"], s)
    d = list(distinct.values())
    res["distinct_text"] = {"skills": len(d),
                            "no_command_no_script": frac(sum(1 for s in d if not s["uses_shell_on_page"]), len(d)),
                            "any_behaviour": frac(sum(1 for s in d if s["any_behaviour"]), len(d)),
                            **{k: frac(sum(1 for s in d if s[k]), len(d)) for k in B_ORDER}}
    res["repo_any_behaviour"] = repo_share(repos, lambda r: r["any_behaviour"])
    res["repo_any_script"] = repo_share(repos, lambda r: r["any_script"])
    res["repo_all_unused"] = repo_share(repos, lambda r: not r["uses_shell_on_page"])
    for band, pred in (("stars_100plus", lambda r: r["stars"] >= 100), ("stars_under_100", lambda r: r["stars"] < 100)):
        sub = [r for r in repos if pred(r)]
        res[band] = {"repos": len(sub), "repo_any_behaviour": repo_share(sub, lambda r: r["any_behaviour"])}
    res["hand_check_sample"] = {"seed": SEED, "method": "60 smallest SHA-256 of seed/repo/skill_md",
                                "rows_in_skills_csv": [i + 2 for i in hand_sample(skills)]}
    return res, repos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--dataset", default=os.path.join(root, "data", "2026-10", "dataset.json"))
    ap.add_argument("--out", default=os.path.join(root, "data", "2026-10", "skill-bash"))
    a = ap.parse_args()
    import skill_bash_fetch as sf
    data = json.load(open(a.dataset))
    meta = {r["repo"]: r for r in data}
    selected = sf.select(data)
    eligible = sum(1 for r in data if r.get("any_unrestricted_bash"))
    log = {}
    for line in open(os.path.join(a.workdir, "fetch_log.jsonl")):
        m = json.loads(line); log[m["repo"]] = m
    fetched, skills = [], []
    for full, sha in selected:
        m = log.get(full, {"repo": full, "state": "unavailable"})
        fetched.append(m)
        if m["state"] not in ("pinned", "moved"):
            continue
        src = os.path.join(a.workdir, "src", full.replace("/", "__"))
        for sk in m["skills"]:
            row = scan_skill(src, sk["skill_md"], sk["files"])
            if not row["grant"]:
                continue
            skills.append({"repo": full, "stars": meta[full]["stars"], "truncated": sk["truncated"], **row})
    skills.sort(key=lambda s: (s["repo"], s["skill_md"]))
    res, repos = summarise(fetched, skills, len(selected), eligible)
    os.makedirs(a.out, exist_ok=True)
    cols = ["repo", "stars", "skill_md", "grant_form", "also_scoped_bash", "n_tools_listed", "n_command_lines",
            "n_heads", "heads", "n_files", "n_scripts", "script_types", "truncated", "uses_shell_on_page",
            "any_behaviour"] + B_ORDER + [f"md_{k}" for k in B_ORDER] + [f"script_{k}" for k in B_ORDER] + ["sha256"]
    with open(os.path.join(a.out, "skills.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore"); w.writeheader(); w.writerows(skills)
    with open(os.path.join(a.out, "repos.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["repo", "state", "fetched_commit", "dataset_commit", "stars", "n_skill_md", "n_skill_md_read",
                    "n_unscoped", "n_analysed"])
        an = Counter(s["repo"] for s in skills)
        for (full, sha), m in zip(selected, fetched):
            w.writerow([full, m["state"], m.get("sha", ""), sha, meta[full]["stars"], m.get("n_skill_md", ""),
                        m.get("n_skill_md_read", ""), m.get("n_unscoped", ""), an.get(full, 0)])
    json.dump(res, open(os.path.join(a.out, "results.json"), "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("repos_fetched", "skills_analysed", "skill_no_command_no_script", "skill_any_behaviour")}, indent=1))


if __name__ == "__main__":
    main()
