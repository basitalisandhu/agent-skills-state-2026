"""Measure whether MCP server READMEs tell people to launch a pinned version, in the October 2026 repositories
that ship a server.json.

Usage: python scripts/readme_pins.py WORKDIR [--dataset data/2026-10/dataset.json] [--out data/2026-10/readme-pins]

Reads the files fetched by scripts/readme_pins_fetch.py (WORKDIR/src and WORKDIR/fetch_log.jsonl). Static only:
nothing is installed or run. Standard library only.

The READMEs read for a repository are the root README and the README next to each server.json. In them the
script finds launch commands, the commands a client config or a shell line uses to start an MCP server, in three
forms: a shell line (`npx -y pkg`, `claude mcp add x -- uvx pkg`, `docker run -i --rm image`), a JSON config
("command": "npx", "args": [...]) and a TOML config (command = "npx" / args = [...]). Launchers: npx, bunx,
pnpm dlx, yarn dlx, uvx, uv tool run, pipx run and docker run. Each launch command's package spec is classed:

- exact: an exact version (pkg@1.2.3, pkg==1.2.3, image:1.2.3) or a docker digest (image@sha256:...)
- range: a version range or a partial version (pkg@^1, pkg@1, pkg>=1.0, image:1)
- latest: an explicit moving tag (pkg@latest, pkg@next, image:latest, image:main)
- unpinned: no version at all (pkg, image)

range, latest and unpinned together are "floating": what runs can change without the README or the config
changing. Development tools (inspectors, test runners, build tools, installers) and local paths are left out;
see EXCLUDED_PACKAGES. Writes commands.csv, repos.csv and results.json.
"""
import argparse, csv, hashlib, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from annotations import wilson, cluster_ci, frac  # noqa: E402

SEED = 20261020
README_NAMES = {"readme.md", "readme", "readme.markdown", "readme.mdx"}
NODE_LAUNCHERS = {"npx", "bunx", "pnpm dlx", "yarn dlx", "pnpx"}
PY_LAUNCHERS = {"uvx", "uv tool run", "pipx run"}
LAUNCHERS = NODE_LAUNCHERS | PY_LAUNCHERS | {"docker run"}
# Packages run with a launcher that are not the MCP server: inspectors, build and test tools, scaffolders and
# installers that write a config rather than start a server. Compared on the bare name, lower case.
EXCLUDED_PACKAGES = {
    "@modelcontextprotocol/inspector", "@smithery/cli", "smithery", "@anthropic-ai/mcpb", "@anthropic-ai/dxt",
    "@modelcontextprotocol/create-server", "@anthropic-ai/claude-code", "tsx", "ts-node", "tsc", "typescript",
    "prettier", "eslint", "jest", "vitest", "nodemon", "rimraf", "concurrently", "cross-env", "shx", "npm", "yarn",
    "pnpm", "node", "wrangler", "vercel", "netlify-cli", "@biomejs/biome", "biome", "husky", "lint-staged",
    "turbo", "nx", "lerna", "playwright", "@playwright/test", "patch-package", "degit", "serve", "http-server",
    "mcp-inspector", "@wong2/mcp-cli", "mcp-cli", "add-mcp", "install-mcp", "@michaellatman/mcp-get", "mcp-get",
    "ruff", "black", "mypy", "pytest", "pre-commit", "hatch", "twine", "build", "pip-audit", "pyright", "isort",
    "flake8", "pylint", "tox", "nox", "poetry", "pdm", "cookiecutter", "copier", "mcp-publisher", "ty", "uv",
    "@mcpjam/inspector", "mcpjam", "repomix", "skills", "npm-check-updates", "ncu", "semantic-release",
    "changeset", "@changesets/cli", "jsr", "localtunnel", "ngrok", "pm2", "@anthropic/mcp-inspector",
    "@modelcontextprotocol/conformance", "convex", "plugins", "skild", "@vercel/skills", "supabase", "prisma", "drizzle-kit", "expo", "next",
    "vite", "esbuild", "rollup", "webpack", "jsdoc", "typedoc", "license-checker", "audit-ci", "knip",
}
EXCLUDED_PREFIXES = ("create-", "@modelcontextprotocol/create-")
# Moving tags that are not versions.
MOVING_TAGS = {"latest", "next", "main", "master", "stable", "edge", "nightly", "canary", "beta", "alpha", "dev", "head", "rc"}
EXACT_SEMVER = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.\-+]+)?$")
PEP440_EXACT = re.compile(r"^\d+(?:\.\d+){1,3}(?:(?:a|b|rc|\.post|\.dev)\d+)*$")
# docker run flags that take no value.
DOCKER_BOOL = {"-i", "-t", "-it", "-ti", "-d", "--rm", "--init", "--interactive", "--tty", "--detach", "--privileged",
               "-P", "--publish-all", "--read-only", "-q", "--quiet", "--sig-proxy", "--no-healthcheck", "-itd", "-dit"}
# npx-style flags that take a value (other flags are taken as boolean).
NODE_VALUE_FLAGS = {"-p", "--package", "-c", "--call", "--registry", "--cache", "--userconfig", "--prefix"}
PY_VALUE_FLAGS = {"--from", "--with", "-w", "--python", "-p", "--spec", "--index", "--index-url", "-i",
                  "--extra-index-url", "--with-requirements", "--with-editable", "--env-file", "-c", "--constraint",
                  "--refresh-package", "--reinstall-package", "--upgrade-package", "--directory", "--project"}

SHELL_RE = re.compile(r"(?<![\w./\"'-])(npx|bunx|pnpx|pnpm\s+dlx|yarn\s+dlx|uvx|uv\s+tool\s+run|pipx\s+run|docker\s+run)[ \t]+((?:[^\n`|;&<>]|<[^\n<>`]*>)*)")
CMD_KEY_RE = re.compile(r"""["']?command["']?[ \t]*[:=][ \t]*["']?(npx|bunx|pnpx|uvx|docker|pnpm|yarn|uv|pipx)(?:\.cmd|\.exe)?(?:["']|[ \t]*$)""", re.M)
ARGS_RE = re.compile(r"""["']?args["']?\s*[:=]\s*\[([^\]]*)\]""", re.S)
STR_RE = re.compile(r"""["']((?:[^"'\\\n]|\\.)*)["']""")


def norm_launcher(word, args):
    w = re.sub(r"\s+", " ", word)
    if w in ("pnpm", "yarn") and args and args[0] == "dlx":
        return f"{w} dlx", args[1:]
    if w == "uv" and args[:2] == ["tool", "run"]:
        return "uv tool run", args[2:]
    if w == "pipx" and args and args[0] == "run":
        return "pipx run", args[1:]
    if w == "docker":
        return ("docker run", args[1:]) if args and args[0] == "run" else (None, args)
    if w in ("pnpm", "yarn", "uv", "pipx"):
        return (w if w in LAUNCHERS else None), args
    return w, args


def shell_tokens(rest):
    rest = re.sub(r"\\\s*$", " ", rest)
    out = []
    for m in re.finditer(r"""(?:<[^<>]*>|[^\s'"<]+|'[^']*'|"[^"]*")+""", rest):
        t = m.group(0)
        if t.startswith("#"):
            break
        out.append(t.replace('"', "").replace("'", ""))
    return out


def built_locally(launcher, args, local_images):
    if launcher != "docker run" or not local_images:
        return False
    spec, _ = package_spec(launcher, args)
    return bool(spec) and norm_image(split_image(spec)[0]) in local_images


def code_spans(text):
    """(start, end) offsets of fenced code blocks, indented code lines and inline code spans."""
    spans = [m.span() for m in re.finditer(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", text)]
    spans += [m.span() for m in re.finditer(r"(?m)^(?: {4}|\t)\S.*$", text)]
    spans += [m.span() for m in re.finditer(r"`[^`\n]+`", text)]
    return spans


def find_commands(text):
    """Yield (form, launcher, args, line) for each launch command in a README's text. Shell lines count only
    inside code (a fenced or indented block or an inline code span), so prose that mentions npx is skipped."""
    seen_spans = []
    code = code_spans(text)
    # images built locally in the same README are not fetched from a registry
    local_images = {norm_image(split_image(t)[0]) for t in re.findall(r"docker\s+(?:buildx\s+)?build\b[^\n]*?(?:-t|--tag)[ =]+(\S+)", text)}
    for m in CMD_KEY_RE.finditer(text):
        tail = text[m.end(): m.end() + 600]
        a = ARGS_RE.search(tail)
        if not a or CMD_KEY_RE.search(tail[: a.start()]):
            continue
        args = [s.encode().decode("unicode_escape", "ignore") if "\\" in s else s for s in STR_RE.findall(a.group(1))]
        launcher, args = norm_launcher(m.group(1), args)
        if launcher and not built_locally(launcher, args, local_images):
            seen_spans.append((m.start(), m.end() + a.end()))
            yield "config", launcher, args, text.count("\n", 0, m.start()) + 1
    joined = re.sub(r"\\[ \t]*\n", lambda m: " " * len(m.group(0)), text)  # shell line continuations
    for m in SHELL_RE.finditer(joined):
        if any(s <= m.start() < e for s, e in seen_spans) or not any(s <= m.start() < e for s, e in code):
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        prefix = text[line_start: m.start()]
        # skip prose mentions such as "use npx to run" and JSON string values (handled above)
        if re.search(r"""["']\s*:\s*["']?$|["']$""", prefix):
            continue
        # a shell comment inside a code block ("# npx caches the package"), not an inline code span
        if re.match(r"\s*#(?!!)", prefix) and "`" not in prefix:
            continue
        toks = shell_tokens(m.group(2))
        launcher, args = norm_launcher(m.group(1), toks)
        if launcher and not built_locally(launcher, args, local_images):
            yield "shell", launcher, args, text.count("\n", 0, m.start()) + 1


def package_spec(launcher, args):
    """Return (spec, flags) for a launch command: the package or image the launcher fetches."""
    flags = []
    if launcher == "docker run":
        i = 0
        while i < len(args):
            t = args[i]
            if t.startswith("-"):
                flags.append(t)
                if t not in DOCKER_BOOL and "=" not in t:
                    i += 1
                i += 1; continue
            return t, flags
        return None, flags
    value_flags = NODE_VALUE_FLAGS if launcher in NODE_LAUNCHERS else PY_VALUE_FLAGS
    pkg_from, i = None, 0
    while i < len(args):
        t = args[i]
        if t == "--":
            i += 1; continue
        if t.startswith("-"):
            flags.append(t.split("=", 1)[0])
            key, _, val = t.partition("=")
            if key in ("--from", "--spec", "-p", "--package") and not (launcher in PY_LAUNCHERS and key == "-p"):
                v = val or (args[i + 1] if i + 1 < len(args) else None)
                pkg_from = pkg_from or v
            if key in value_flags and not val:
                i += 1
            i += 1; continue
        return (pkg_from or t), flags
    return pkg_from, flags


def split_node(spec):
    if spec.startswith("@"):
        name, _, ver = spec[1:].partition("@"); return "@" + name, ver
    name, _, ver = spec.partition("@"); return name, ver


def split_py(spec):
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)(\[[^\]]*\])?\s*(.*)$", spec)
    if not m:
        return spec, ""
    return m.group(1), m.group(3).strip()


def split_image(spec):
    if "@sha256:" in spec:
        img, _, dig = spec.partition("@"); return img, "@" + dig
    last = spec.rsplit("/", 1)[-1]
    if ":" in last:
        img, _, tag = spec.rpartition(":"); return img, tag
    return spec, ""


def norm_image(img):
    img = img.lower()
    for p in ("docker.io/library/", "docker.io/", "index.docker.io/library/", "index.docker.io/"):
        if img.startswith(p):
            img = img[len(p):]
    return img


def norm_py(name):
    return re.sub(r"[-_.]+", "-", name).lower()


PLACEHOLDER = re.compile(r"<(?![=\d])|[{}$]|\bVERSION\b|x\.y\.z|X\.Y\.Z|(?:^|[@/])your[-_/]|^(?:package[-_]name|pkg[-_]name|your[-_][\w-]+|my[-_]package|server[-_]name|image[-_]name|some[-_]package)$")


def classify(launcher, spec):
    """Return (ecosystem, name, version_text, pin_class). pin_class is exact, range, latest, unpinned or None
    (not a package: a local path, a URL, a variable or a placeholder)."""
    git = re.match(r"^(?:git\+(?:https?|ssh)://|github:|git@)(.+)$", spec or "")
    if git:  # a git source: pinned only to a full commit hash
        ref = re.search(r"(?:@|#)([0-9a-f]{40})\b", git.group(1))
        return "git", re.sub(r"[@#].*$", "", git.group(1)), (ref.group(1) if ref else ""), ("exact" if ref else "unpinned")
    if not spec or re.match(r"^(?:\.{0,2}/|~|\$|<|\{|%|file:|https?:|[A-Za-z]:\\)", spec) or spec.endswith((".js", ".ts", ".py", ".mjs", ".cjs")):
        return None, spec or "", "", None
    if PLACEHOLDER.search(spec):  # a placeholder such as pkg@<version> or @scope/mcp-<name>
        return None, spec, "", None
    if launcher == "docker run":
        img, tag = split_image(spec)
        if not re.match(r"^[a-z0-9][a-z0-9._\-/:]*$", img.lower()) or img.lower() != img:
            return "oci", img, tag, None
        if tag.startswith("@sha256:"):
            return "oci", norm_image(img), tag, "exact"
        if not tag:
            return "oci", norm_image(img), "", "unpinned"
        if tag.lower() in MOVING_TAGS:
            return "oci", norm_image(img), tag, "latest"
        if EXACT_SEMVER.match(tag):
            return "oci", norm_image(img), tag, "exact"
        if re.match(r"^v?\d+(?:\.\d+)?$", tag):
            return "oci", norm_image(img), tag, "range"
        return "oci", norm_image(img), tag, "latest"
    if launcher in NODE_LAUNCHERS:
        name, ver = split_node(spec)
        if not re.match(r"^(?:@[a-z0-9][\w.\-~]*/)?[a-z0-9][\w.\-~]*$", name):
            return "npm", name, ver, None
        if not ver:
            return "npm", name, "", "unpinned"
        if ver.lower() in MOVING_TAGS:
            return "npm", name, ver, "latest"
        if EXACT_SEMVER.match(ver):
            return "npm", name, ver, "exact"
        if re.match(r"^[\^~<>=*xX\d]", ver):
            return "npm", name, ver, "range"
        return "npm", name, ver, "latest"  # any other dist-tag moves
    name, ver = split_py(spec)
    if ver.startswith("@"):  # uvx pkg@1.2.3 and pkg@latest
        ver = ver[1:] if ver[1:].lower() in MOVING_TAGS else "==" + ver[1:]
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$", name):
        return "pypi", name, ver, None
    if not ver:
        return "pypi", norm_py(name), "", "unpinned"
    if ver.lower() in MOVING_TAGS:
        return "pypi", norm_py(name), ver, "latest"
    m = re.match(r"^===?\s*(\S+)$", ver)
    if m and PEP440_EXACT.match(m.group(1)):
        return "pypi", norm_py(name), ver, "exact"
    return "pypi", norm_py(name), ver, "range"


def refreshes(launcher, args):
    """uvx --refresh, npx --prefer-online and docker run --pull always re-resolve the version at each launch."""
    a = " ".join(args)
    if launcher in PY_LAUNCHERS:
        return bool(re.search(r"(?:^| )--refresh(?: |$)", a))
    if launcher in NODE_LAUNCHERS:
        return "--prefer-online" in args
    return bool(re.search(r"--pull[= ]always", a))


def excluded(name):
    n = (name or "").lower()
    return n in EXCLUDED_PACKAGES or n.startswith(EXCLUDED_PREFIXES)


def readme_paths(path):
    """The root README plus the README in each folder that holds a server.json."""
    out, sj = [], []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(dirs)
        for f in sorted(files):
            if f == "server.json":
                sj.append(os.path.join(root, f))
    dirs = {path} | {os.path.dirname(p) for p in sj}
    for d in sorted(dirs):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for f in names:
            if f.lower() in README_NAMES and os.path.isfile(os.path.join(d, f)):
                out.append(os.path.join(d, f)); break
    return out, sj


def declared_packages(sj_paths):
    out = []
    for p in sj_paths:
        try:
            d = json.load(open(p, encoding="utf-8", errors="replace"))
        except (ValueError, OSError):
            continue
        for pk in (d.get("packages") or []) if isinstance(d, dict) else []:
            if not isinstance(pk, dict):
                continue
            rt = (pk.get("registryType") or pk.get("registry_type") or pk.get("registry_name") or "").lower()
            ident = pk.get("identifier") or pk.get("name") or ""
            ver = str(pk.get("version") or "")
            eco = {"npm": "npm", "pypi": "pypi", "pip": "pypi", "oci": "oci", "docker": "oci"}.get(rt)
            if not eco or not ident:
                continue
            if eco == "oci":
                img, tag = split_image(ident); ident = norm_image(img); ver = ver or tag
            elif eco == "pypi":
                ident = norm_py(ident)
            out.append({"ecosystem": eco, "identifier": ident, "version": ver})
    return out


def scan_repo(path):
    """Return (commands, readmes, declared) for one fetched repository."""
    readmes, sj = readme_paths(path)
    cmds, seen = [], set()
    for rp in readmes:
        text = open(rp, encoding="utf-8", errors="replace").read()
        for form, launcher, args, line in find_commands(text):
            spec, flags = package_spec(launcher, args)
            eco, name, ver, pin = classify(launcher, spec)
            if pin is None or excluded(name):
                continue
            if pin == "unpinned" and refreshes(launcher, args):
                pin = "latest"  # fetches the newest release on every launch, like an explicit latest tag
            key = (launcher, name, ver)
            if key in seen:
                continue
            seen.add(key)
            cmds.append({"file": os.path.relpath(rp, path), "line": line, "form": form, "launcher": launcher,
                         "ecosystem": eco, "package": name, "version": ver, "pin_class": pin,
                         "floating": pin != "exact", "auto_yes": bool({"-y", "--yes"} & set(flags))})
    return cmds, [os.path.relpath(p, path) for p in readmes], declared_packages(sj)


def summarise(repos, cmds):
    ok = [r for r in repos if r["state"] in ("pinned", "moved")]
    with_readme = [r for r in ok if r["n_readmes"]]
    base = [r for r in ok if r["n_commands"]]
    by_repo = {}
    for c in cmds:
        by_repo.setdefault(c["repo"], []).append(c)

    def repo_share(pred, b):
        k = sum(1 for r in b if pred(r)); return {"value": frac(k, len(b)), "ci95_wilson": wilson(k, len(b))}

    def cmd_share(pred, keep=lambda c: True):
        groups = [(sum(1 for c in cs if keep(c) and pred(c)), sum(1 for c in cs if keep(c))) for cs in by_repo.values()]
        k = sum(g[0] for g in groups); n = sum(g[1] for g in groups)
        return {"value": frac(k, n), "ci95_cluster_bootstrap": cluster_ci(groups, seed=SEED), "repos": sum(1 for g in groups if g[1])}

    cs = lambda r: by_repo.get(r["repo"], [])
    out = {
        "selection": "every repository in data/2026-10/dataset.json with has_server_json true",
        "repos_selected": len(repos),
        "repos_fetched": len(ok),
        "repos_pinned_commit": sum(1 for r in ok if r["state"] == "pinned"),
        "repos_unavailable": len(repos) - len(ok),
        "repos_with_readme": len(with_readme),
        "repos_with_launch_command": len(base),
        "repos_readme_no_launch_command": len(with_readme) - len(base),
        "commands": len(cmds),
        "commands_by_launcher": {l: sum(1 for c in cmds if c["launcher"] == l) for l in sorted({c["launcher"] for c in cmds})},
        "commands_by_class": {k: sum(1 for c in cmds if c["pin_class"] == k) for k in ("exact", "range", "latest", "unpinned")},
        "repo_any_floating": repo_share(lambda r: any(c["floating"] for c in cs(r)), base),
        "repo_all_floating": repo_share(lambda r: all(c["floating"] for c in cs(r)), base),
        "repo_any_exact": repo_share(lambda r: any(not c["floating"] for c in cs(r)), base),
        "repo_any_latest_tag": repo_share(lambda r: any(c["pin_class"] == "latest" for c in cs(r)), base),
        "command_floating": cmd_share(lambda c: c["floating"]),
        "command_latest_tag": cmd_share(lambda c: c["pin_class"] == "latest"),
        "command_range": cmd_share(lambda c: c["pin_class"] == "range"),
        "by_ecosystem": {},
        "npx_auto_yes": cmd_share(lambda c: c["auto_yes"], lambda c: c["launcher"] == "npx"),
        "npx_auto_yes_and_floating": cmd_share(lambda c: c["auto_yes"] and c["floating"], lambda c: c["launcher"] == "npx"),
        "stars_100plus": {}, "stars_under_100": {},
    }
    for eco in ("npm", "pypi", "oci", "git"):
        b = [r for r in base if any(c["ecosystem"] == eco for c in cs(r))]
        out["by_ecosystem"][eco] = {
            "repos": len(b), "commands": sum(1 for c in cmds if c["ecosystem"] == eco),
            "repo_any_floating": repo_share(lambda r, e=eco: any(c["floating"] for c in cs(r) if c["ecosystem"] == e), b),
            "repo_all_floating": repo_share(lambda r, e=eco: all(c["floating"] for c in cs(r) if c["ecosystem"] == e), b),
            "command_floating": cmd_share(lambda c: c["floating"], lambda c, e=eco: c["ecosystem"] == e)}
    # The repository's own package: a launch command whose package matches a package its server.json declares.
    own = [r for r in base if r["own_commands"]]
    exact_decl = [r for r in own if r["own_declared_exact"]]
    out["own_package"] = {
        "repos_declaring_package": sum(1 for r in ok if r["declared_packages"]),
        "repos_with_own_launch_command": len(own),
        "repo_own_any_floating": repo_share(lambda r: r["own_floating"] > 0, own),
        "repo_own_all_floating": repo_share(lambda r: r["own_floating"] == r["own_commands"], own),
        "repos_registry_exact_readme_floating": repo_share(lambda r: r["own_floating"] > 0, exact_decl),
        "repos_registry_exact_readme_all_floating": repo_share(lambda r: r["own_floating"] == r["own_commands"], exact_decl),
        "repos_registry_exact": len(exact_decl),
        "own_exact_commands": sum(1 for c in cmds if c["own_package"] and not c["floating"]),
        "own_exact_matching_declared_version": sum(1 for c in cmds if c["own_package"] and not c["floating"]
                                                   and re.sub(r"^[=v@]+", "", c["version"]) == re.sub(r"^v", "", c["declared_version"])),
    }
    rem = [r for r in base if any(c["package"] == "mcp-remote" for c in cs(r))]
    out["mcp_remote"] = {"repos": len(rem), "commands": sum(1 for c in cmds if c["package"] == "mcp-remote"),
                         "repo_floating": repo_share(lambda r: any(c["floating"] for c in cs(r) if c["package"] == "mcp-remote"), rem)}
    largest = max(by_repo.items(), key=lambda kv: len(kv[1])) if by_repo else ("", [])
    out["largest_repo_commands"] = len(largest[1])
    out["commands_median_per_repo"] = sorted(len(v) for v in by_repo.values())[len(by_repo) // 2] if by_repo else 0
    for band, test in (("stars_under_100", lambda s: s < 100), ("stars_100plus", lambda s: s >= 100)):
        b = [r for r in base if test(r["stars"])]
        out[band] = {"repos": len(b), "repo_any_floating": repo_share(lambda r: any(c["floating"] for c in cs(r)), b),
                     "repo_all_floating": repo_share(lambda r: all(c["floating"] for c in cs(r)), b)}
    return out


def hand_sample(cmds, n=60, seed=SEED):
    """Row numbers (0-based, header excluded) of a random sample of commands.csv: the n rows with the smallest
    SHA-256 of seed, repository, file, line and package, so the draw does not shift when unrelated rows change."""
    key = lambda i: hashlib.sha256(f"{seed}|{cmds[i]['repo']}|{cmds[i]['file']}|{cmds[i]['line']}|{cmds[i]['package']}".encode()).hexdigest()
    return sorted(sorted(range(len(cmds)), key=key)[:n])


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--dataset", default=os.path.join(root, "data", "2026-10", "dataset.json"))
    ap.add_argument("--out", default=os.path.join(root, "data", "2026-10", "readme-pins"))
    a = ap.parse_args()
    meta = {r["repo"]: r for r in json.load(open(a.dataset)) if r.get("has_server_json")}
    log = {}
    for line in open(os.path.join(a.workdir, "fetch_log.jsonl")):
        m = json.loads(line); log[m["repo"]] = m
    repos, cmds = [], []
    for full in sorted(meta):
        f = log.get(full, {"state": "not_fetched"})
        r = {"repo": full, "stars": meta[full]["stars"], "state": f["state"], "commit": f.get("sha", ""),
             "n_readmes": 0, "n_commands": 0, "n_floating": 0, "declared_packages": 0, "own_commands": 0,
             "own_floating": 0, "own_declared_exact": False}
        if f["state"] in ("pinned", "moved"):
            cs, readmes, decl = scan_repo(os.path.join(a.workdir, "src", full.replace("/", "__")))
            for c in cs:
                c["repo"] = full
                d = [p for p in decl if p["ecosystem"] == c["ecosystem"] and p["identifier"].lower() == c["package"].lower()]
                c["own_package"] = bool(d)
                c["declared_version"] = d[0]["version"] if d else ""
            own = [c for c in cs if c["own_package"]]
            r.update(n_readmes=len(readmes), n_commands=len(cs), n_floating=sum(1 for c in cs if c["floating"]),
                     declared_packages=len(decl), own_commands=len(own), own_floating=sum(1 for c in own if c["floating"]),
                     own_declared_exact=any(EXACT_SEMVER.match(c["declared_version"]) or PEP440_EXACT.match(c["declared_version"]) for c in own))
            cmds += cs
        repos.append(r)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "repos.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(repos[0])); w.writeheader(); w.writerows(repos)
    cols = ["repo", "file", "line", "form", "launcher", "ecosystem", "package", "version", "pin_class", "floating",
            "auto_yes", "own_package", "declared_version"]
    with open(os.path.join(a.out, "commands.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(cmds)
    res = summarise(repos, cmds)
    res["hand_check_sample"] = {"seed": SEED, "size": 60, "rows_in_commands_csv": hand_sample(cmds)}
    json.dump(res, open(os.path.join(a.out, "results.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "hand_check_sample"}, indent=1))


if __name__ == "__main__":
    main()
