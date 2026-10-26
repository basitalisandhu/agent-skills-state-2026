"""Re-fetch the skills that grant unscoped Bash, and the files bundled with them, at the commits in the dataset.

Usage: python scripts/skill_bash_fetch.py WORKDIR [--dataset data/2026-10/dataset.json] [--jobs 8]

Selection: the repositories in the dataset with any_unrestricted_bash true (407 in October 2026). To stay within
the study's 400-repository ceiling for re-fetching, the 400 with the smallest SHA-256 of "20261026/<repo>" are kept
(select()). Each one is fetched with a blob-less, depth-1 fetch of the exact commit recorded in the dataset
(falling back to the default branch, recorded as "moved", when that commit is gone), with git hooks and LFS
disabled. Nothing is checked out: the file list comes from the commit's tree, and the blobs wanted are fetched by
object id and written out directly, in two passes:

1. Every SKILL.md outside vendored, build and dependency folders (at most 2,000 a repository, the smallest
   SHA-256 first when there are more). Each is parsed with skill_bash.unscoped_bash(), the same test as
   skill-scan-gate SSG607 ("Bash" or "Bash(*)" in allowed-tools).
2. For at most 20 of the SKILL.md files that grant unscoped Bash (the smallest SHA-256 of seed, repository and
   path), the files bundled with the skill: every text file under the skill's folder that is not under a nested
   folder with its own SKILL.md, up to 300 files and 1 MB a file per skill, binaries and symbolic links left out.

The study's caps apply (3,000 files and 30 MB a repository) and the .git folder is removed. Nothing in a fetched
repository is executed. Output: WORKDIR/src/<owner>__<name>/ (with .fetched.json) and WORKDIR/fetch_log.jsonl.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, posixpath, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skill_bash as sb  # noqa: E402

SEED = 20261026
MAX_REPOS, MAX_SKILL_MD, MAX_SKILLS, MAX_SKILL_FILES = 400, 2000, 20, 300
CAP_FILES, CAP_BYTES, CAP_FILE = 3000, 30_000_000, 1_000_000
SKIP_DIRS = {"node_modules", "dist", "build", "out", "vendor", "third_party", ".venv", "venv", "__pycache__",
             ".git", ".next", "coverage", "site-packages"}
BIN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".pdf", ".zip", ".tar", ".gz", ".tgz", ".7z",
           ".rar", ".jar", ".whl", ".exe", ".dll", ".so", ".dylib", ".bin", ".mp4", ".mp3", ".wav", ".mov", ".woff",
           ".woff2", ".ttf", ".otf", ".psd", ".xlsx", ".xls", ".docx", ".pptx", ".skill", ".pyc", ".class", ".o",
           ".a", ".node", ".wasm", ".sqlite", ".db", ".parquet", ".npy", ".pkl", ".pt", ".onnx", ".bmp", ".tiff",
           ".avi", ".webm", ".m4a", ".flac", ".ogg", ".eot", ".keynote", ".key", ".dmg", ".iso", ".lock"}
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1", GIT_CONFIG_NOSYSTEM="1")
SAFE = ["-c", "core.hooksPath=/dev/null", "-c", "core.symlinks=false", "-c", "filter.lfs.smudge=",
        "-c", "filter.lfs.process=", "-c", "filter.lfs.required=false"]


def h(*parts):
    return hashlib.sha256("/".join(str(p) for p in parts).encode()).hexdigest()


def select(dataset, limit=MAX_REPOS):
    rows = [(r["repo"], r["commit"]) for r in dataset if r.get("any_unrestricted_bash")]
    return sorted(sorted(rows, key=lambda t: h(SEED, t[0]))[:limit])


def skipped(path):
    return any(part in SKIP_DIRS for part in path.split("/")[:-1])


def skill_dir(path):
    d = posixpath.dirname(path)
    return d


def bundled(skill_md, tree, all_skill_dirs):
    """Files bundled with the skill at skill_md: under its folder, not under a nested skill folder, not binary.
    tree is a list of paths. Returns (at most MAX_SKILL_FILES paths, shallowest first; whether any were cut)."""
    d = skill_dir(skill_md)
    pre = d + "/" if d else ""
    out = []
    for path in tree:
        if path == skill_md or not path.startswith(pre) or skipped(path):
            continue
        parent, nested = posixpath.dirname(path), False
        while parent != d and parent:
            if parent in all_skill_dirs:
                nested = True
                break
            parent = posixpath.dirname(parent)
        if nested:
            continue
        if os.path.splitext(path)[1].lower() in BIN_EXT:
            continue
        out.append(path)
    out.sort(key=lambda t: (t.count("/"), t))
    return out[:MAX_SKILL_FILES], len(out) > MAX_SKILL_FILES


def run(args, cwd=None, t=240, inp=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=t, env=ENV, input=inp)


def materialise(dest, entries, budget):
    """Fetch the blobs of entries [(path, oid)] in batches and write them under dest, skipping files over 1 MB and
    stopping at budget bytes. No checkout is run, so no git filter, hook or attribute applies; paths that would
    leave dest are skipped. Returns {path: bytes written}."""
    todo = [e for e in entries if not os.path.exists(os.path.join(dest, e[0]))]
    written = {}
    for i in range(0, len(todo), 1000):
        chunk = todo[i:i + 1000]
        run(["git", *SAFE, "-c", "fetch.negotiationAlgorithm=noop", "fetch", "-q", "--no-tags", "--no-write-fetch-head",
             "origin", "--stdin"], cwd=dest, t=600, inp="\n".join(e[1] for e in chunk) + "\n")
        p = subprocess.run(["git", "cat-file", "--batch"], cwd=dest, capture_output=True, timeout=600, env=ENV,
                           input=("\n".join(e[1] for e in chunk) + "\n").encode())
        buf, pos = p.stdout, 0
        for path, oid in chunk:
            nl = buf.index(b"\n", pos)
            header = buf[pos:nl].split()
            if len(header) < 3:
                pos = nl + 1
                continue
            n = int(header[2]); data = buf[nl + 1:nl + 1 + n]; pos = nl + 1 + n + 1
            target = os.path.abspath(os.path.join(dest, path))
            if not target.startswith(os.path.abspath(dest) + os.sep) or n > CAP_FILE or n > budget:
                continue
            budget -= n; written[path] = n
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(data)
    return written


def one(src, full, sha):
    dest = os.path.join(src, full.replace("/", "__"))
    meta = os.path.join(dest, ".fetched.json")
    if os.path.exists(meta):
        return json.load(open(meta))
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    try:
        run(["git", "init", "-q"], cwd=dest)
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"], cwd=dest)
        state = "pinned"
        r = run(["git", *SAFE, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", sha], cwd=dest)
        if r.returncode:
            state = "moved"
            r = run(["git", *SAFE, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", "HEAD"], cwd=dest)
            if r.returncode:
                shutil.rmtree(dest, ignore_errors=True)
                return {"repo": full, "state": "unavailable"}
        got = run(["git", "rev-parse", "FETCH_HEAD"], cwd=dest).stdout.strip()
        # No -l: asking for sizes would make git download every blob one by one.
        ls = run(["git", "ls-tree", "-r", "-z", "--full-tree", "FETCH_HEAD"], cwd=dest, t=300).stdout
        tree, oid = [], {}
        for entry in ls.split("\0"):
            if not entry or "\t" not in entry:
                continue
            info, path = entry.split("\t", 1)
            mode, typ, obj = info.split()
            if typ != "blob" or mode in ("120000", "160000"):
                continue
            tree.append(path); oid[path] = obj
        skill_mds = [p for p in tree if posixpath.basename(p) == "SKILL.md" and not skipped(p)]
        all_dirs = {skill_dir(p) for p in skill_mds}
        read = sorted(skill_mds, key=lambda p: h(SEED, full, p))[:MAX_SKILL_MD]
        sizes = materialise(dest, [(p, oid[p]) for p in read], CAP_BYTES)
        grants = []
        for p in read:
            fp = os.path.join(dest, p)
            try:
                text = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if sb.unscoped_bash(text) is not None:
                grants.append(p)
        chosen = sorted(sorted(grants, key=lambda p: h(SEED, full, p))[:MAX_SKILLS])
        skills, want, extra = [], set(read), []
        for p in chosen:
            files, truncated = bundled(p, tree, all_dirs)
            kept = []
            for f in files:
                if f not in want:
                    if len(want) >= CAP_FILES:
                        truncated = True
                        break
                    want.add(f); extra.append((f, oid[f]))
                kept.append(f)
            skills.append({"skill_md": p, "files": kept, "truncated": truncated})
        got_extra = materialise(dest, extra, CAP_BYTES - sum(sizes.values()))
        for sk in skills:
            n_before = len(sk["files"])
            sk["files"] = [f for f in sk["files"] if f in got_extra]
            sk["dropped_over_cap"] = n_before - len(sk["files"])
        shutil.rmtree(os.path.join(dest, ".git"), ignore_errors=True)
        nfiles = nb = 0
        for root, dirs, files in os.walk(dest):
            for f in files:
                fp = os.path.join(root, f)
                if os.path.islink(fp):
                    os.remove(fp); continue
                nfiles += 1; nb += os.path.getsize(fp)
        m = {"repo": full, "state": state, "sha": got, "n_skill_md": len(skill_mds), "n_skill_md_read": len(read),
             "n_unscoped": len(grants), "skills": skills, "files": nfiles, "bytes": nb}
        json.dump(m, open(meta, "w"))
        return m
    except (subprocess.TimeoutExpired, ValueError) as e:
        shutil.rmtree(dest, ignore_errors=True)
        return {"repo": full, "state": "timeout" if isinstance(e, subprocess.TimeoutExpired) else "error"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--dataset", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "2026-10", "dataset.json"))
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    todo = select(json.load(open(a.dataset)))
    src = os.path.join(a.workdir, "src"); os.makedirs(src, exist_ok=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex, open(os.path.join(a.workdir, "fetch_log.jsonl"), "w") as log:
        for i, m in enumerate(ex.map(lambda t: one(src, *t), todo)):
            log.write(json.dumps(m) + "\n"); log.flush()
            if i % 25 == 0:
                print(i, len(todo), flush=True)
    print("done", len(todo))


if __name__ == "__main__":
    main()
