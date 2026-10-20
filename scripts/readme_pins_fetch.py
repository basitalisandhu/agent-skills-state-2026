"""Re-fetch the READMEs and server.json files of the October 2026 repositories that ship an MCP server.json.

Usage: python scripts/readme_pins_fetch.py WORKDIR [--dataset data/2026-10/dataset.json] [--jobs 12]

Same selection, commit pinning, safety settings and caps as scripts/annotations_fetch.py (399 repositories with
has_server_json true, each fetched blob-less and depth 1 at the commit in the dataset, hooks, LFS and symbolic
links disabled, .git removed). Only README files and server.json files are checked out. Nothing in a fetched
repository is executed. Output: WORKDIR/src/<owner>__<name>/ and WORKDIR/fetch_log.jsonl.
"""
import argparse, concurrent.futures as cf, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations_fetch as af  # noqa: E402

EXCLUDE = ("node_modules", "dist", "build", "out", "vendor", "third_party", ".venv", "venv", "test", "tests",
           "__tests__", "fixtures", "testdata", "examples", "example")
PATTERNS = ["**/README.md", "**/README", "**/README.markdown", "**/README.mdx", "**/readme.md", "**/Readme.md",
            "**/server.json"] + [f"!**/{d}/**" for d in EXCLUDE]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--dataset", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "2026-10", "dataset.json"))
    ap.add_argument("--jobs", type=int, default=12)
    a = ap.parse_args()
    todo = af.select(json.load(open(a.dataset)))
    src = os.path.join(a.workdir, "src"); os.makedirs(src, exist_ok=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex, open(os.path.join(a.workdir, "fetch_log.jsonl"), "w") as log:
        for i, m in enumerate(ex.map(lambda t: af.one(src, *t, patterns=PATTERNS), todo)):
            log.write(json.dumps(m) + "\n"); log.flush()
            if i % 50 == 0:
                print(i, len(todo), flush=True)
    print("done", len(todo))


if __name__ == "__main__":
    main()
