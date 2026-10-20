"""Re-fetch the source code of the October 2026 repositories that ship an MCP server.json, at the commit in the dataset.

Usage: python scripts/annotations_fetch.py WORKDIR [--dataset data/2026-10/dataset.json] [--jobs 12]

Selection: every repository in the dataset with has_server_json true (399 in October 2026). Each one is fetched
with a blob-less, depth-1 fetch of the exact commit recorded in the dataset (falling back to the default branch,
recorded as "moved", when that commit is gone), then a non-cone sparse checkout of source files only. Tests,
vendored code, build output and node_modules are excluded. Git hooks, LFS and symbolic links are disabled, the
same caps as scripts/fetch.py apply (1 MB per file, 3,000 files, 30 MB per repository) and the .git folder is
removed. Nothing in a fetched repository is executed. Output: WORKDIR/src/<owner>__<name>/ and
WORKDIR/fetch_log.jsonl.
"""
import argparse, concurrent.futures as cf, json, os, shutil, subprocess

SRC_EXT = ["ts", "tsx", "mts", "cts", "js", "mjs", "cjs", "py", "go", "rs", "java", "kt", "cs"]
PATTERNS = [f"**/*.{e}" for e in SRC_EXT] + ["**/server.json"] + [
    f"!**/{d}/**" for d in ("node_modules", "dist", "build", "out", "vendor", "third_party", ".venv", "venv",
                            "test", "tests", "__tests__", "spec", "e2e", "coverage", ".next")] + [
    "!**/*.d.ts", "!**/*.min.js", "!**/*.test.*", "!**/*.spec.*", "!**/test_*.py", "!**/*_test.go", "!**/*_test.py"]
CAP_FILES, CAP_BYTES, CAP_FILE = 3000, 30_000_000, 1_000_000
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1", GIT_CONFIG_NOSYSTEM="1")
SAFE = ["-c", "core.hooksPath=/dev/null", "-c", "core.symlinks=false", "-c", "filter.lfs.smudge=",
        "-c", "filter.lfs.process=", "-c", "filter.lfs.required=false"]


def select(dataset):
    return [(r["repo"], r["commit"]) for r in dataset if r.get("has_server_json")]


def run(args, cwd=None, t=240):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=t, env=ENV)


def one(src, full, sha, patterns=None):
    dest = os.path.join(src, full.replace("/", "__"))
    meta = os.path.join(dest, ".fetched.json")
    if os.path.exists(meta):
        return json.load(open(meta))
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    try:
        run(["git", "init", "-q"], cwd=dest)
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"], cwd=dest)
        run(["git", "sparse-checkout", "set", "--no-cone", *(patterns or PATTERNS)], cwd=dest)
        state = "pinned"
        r = run(["git", *SAFE, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", sha], cwd=dest)
        if r.returncode:
            state = "moved"
            r = run(["git", *SAFE, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", "HEAD"], cwd=dest)
            if r.returncode:
                shutil.rmtree(dest, ignore_errors=True)
                return {"repo": full, "state": "unavailable"}
        r = run(["git", *SAFE, "checkout", "-q", "FETCH_HEAD"], cwd=dest, t=400)
        got = run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()
        shutil.rmtree(os.path.join(dest, ".git"), ignore_errors=True)
        nfiles = nbytes = removed = 0
        for root, dirs, files in os.walk(dest):
            for f in files:
                p = os.path.join(root, f)
                if os.path.islink(p):
                    os.remove(p); removed += 1; continue
                sz = os.path.getsize(p)
                if sz > CAP_FILE or nfiles >= CAP_FILES or nbytes + sz > CAP_BYTES:
                    os.remove(p); removed += 1; continue
                nfiles += 1; nbytes += sz
        m = {"repo": full, "state": state, "sha": got, "files": nfiles, "bytes": nbytes, "removed": removed,
             "checkout_rc": r.returncode}
        json.dump(m, open(meta, "w"))
        return m
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        return {"repo": full, "state": "timeout"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--dataset", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "2026-10", "dataset.json"))
    ap.add_argument("--jobs", type=int, default=12)
    a = ap.parse_args()
    todo = select(json.load(open(a.dataset)))
    src = os.path.join(a.workdir, "src"); os.makedirs(src, exist_ok=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex, open(os.path.join(a.workdir, "fetch_log.jsonl"), "w") as log:
        for i, m in enumerate(ex.map(lambda t: one(src, *t), todo)):
            log.write(json.dumps(m) + "\n"); log.flush()
            if i % 50 == 0:
                print(i, len(todo), flush=True)
    print("done", len(todo))


if __name__ == "__main__":
    main()
