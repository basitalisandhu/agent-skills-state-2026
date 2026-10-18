# Do MCP servers say which tools are safe? Tool annotations in 304 public servers, October 2026

*Muhammad Basit Ali, 16 October 2026. A follow-up to [the October 2026 study](../README.md), using its sample and method. Data and text: CC BY 4.0. Code: MIT.*

MCP lets a server mark each tool with four hints: `readOnlyHint` (the tool changes nothing), `destructiveHint` (it may delete or overwrite), `idempotentHint` (calling it twice does no more than once) and `openWorldHint` (it reaches outside systems). Clients use them to decide when to ask the user before a call. The first report could not measure them: a server has to run to list its tools, we ran nothing, and only 10 repositories in the sample committed a tool list (all 986 tools in those lists had no annotations). This report reads the hints from the servers' source code instead.

## Key findings

- **Most servers mark nothing.** Of the 304 MCP server repositories whose tool registrations we could read, 188 of 304 (61.8%) annotate none of their tools (95% CI 56.3% to 67.1%). Only 69 of 304 (22.7%) annotate every tool.
- **About a third of tools carry a hint.** 6,243 of 17,688 (35.3%) tools are annotated (95% CI 23.4% to 47.1%, resampling repositories because tools cluster by server). The typical server annotates 29.4% of its tools (95% CI 24.5% to 34.6%).
- **Tools named for deleting, sending or paying are no better.** 1,099 tools have a name that says delete, remove, drop, purge, send, pay, transfer, write or similar. 366 of 1,099 (33.3%) are annotated and 214 of 1,099 (19.5%) say `destructiveHint: true` outright. In 83 of 117 (70.9%) repositories that ship such tools, none of them is annotated.
- **Read tools mostly do not say so.** Of 7,609 tools named get, list, search, read and so on, 2,095 of 7,609 (27.5%) declare `readOnlyHint: true`. A careful client has to ask before each of the other 5,514 calls, which trains people to click yes or to allow a whole server.
- **Wrong hints are rare.** 7 of 1,099 (0.6%) delete-or-send tools are marked read-only or non-destructive, in 3 of 304 (1.0%) repositories. Missing hints are the problem, not misleading ones.
- **Popularity barely helps.** 36 of 67 (53.7%) repositories with 100 or more stars set a hint somewhere in their source, against 106 of 237 (44.7%) with fewer; the confidence intervals overlap.

Every share above is checked against [`data/2026-10/annotations/results.json`](../data/2026-10/annotations/results.json) by [`tests/test_annotations.py`](../tests/test_annotations.py) in CI.

> **What to check before you install an MCP server**
>
> 1. Open its tool definitions (search the source for `registerTool`, `server.tool`, `@mcp.tool`, `NewTool` or `McpServerTool`) and look for `readOnlyHint` and `destructiveHint`. Six servers in ten annotate no tool at all.
> 2. Treat a tool with no hints as able to change or delete things. That is what the specification's defaults say, and it is the only safe reading.
> 3. Check that any tool whose name says delete, remove, send, pay or write is not marked `readOnlyHint: true` or `destructiveHint: false`.
> 4. Hints are claims by the author, not guarantees. Allow-list read-only tools by name in your client, and keep the rest on "ask".
> 5. Pin the server to a version (the first report found 46.0% of configurations do not), so the hints you checked are the ones you run. A version pin alone may not be enough: the [RugSnare drift-watch corpus](https://github.com/Paraphern/rugsnare/tree/main/docs/servers) documents a server whose tool schema changed between installs of the same version because a floating dependency resolved differently, so a lockfile or a recorded tool-contract hash is the stronger check.

## Why this matters, and why it is not a vulnerability

The specification's defaults are cautious: a tool with no hints is assumed to be able to write, to be destructive and to reach the outside world. A client that follows them will ask before calling an unannotated delete tool, so a missing hint does not by itself let anything happen silently. The cost is elsewhere. When most tools carry no hints, a client cannot tell the 7,609 read-looking tools from the 1,099 delete-or-send ones, so it either asks about everything, and people learn to approve without reading, or the user allows the whole server and the question is never asked again. Hints are also untrusted unless the server is: they help an honest server get the right prompts, they do not stop a dishonest one.

## Method in brief

**Selection.** Every repository in the committed October 2026 dataset with an MCP `server.json` ([`data/2026-10/dataset.json`](../data/2026-10/dataset.json), `has_server_json` true): 399 repositories, a random subset of the study's random sample. That is under the 400-repository ceiling we set for re-fetching.

**Fetch.** [`scripts/annotations_fetch.py`](../scripts/annotations_fetch.py) fetched each one at the exact commit recorded in the dataset, blob-less and depth 1, with a sparse checkout of source files only (TypeScript, JavaScript, Python, Go, Rust, C#, Java and Kotlin; the last two were fetched but have no extraction patterns) and `server.json`. Tests, build output, vendored code and `node_modules` were left out, git hooks, LFS and symbolic links were disabled, and the study's caps applied (1 MB a file, 3,000 files and 30 MB a repository). Nothing was built, installed or run. 398 of 399 were fetched at their recorded commit; one repository was no longer available.

**Extraction.** [`scripts/annotations.py`](../scripts/annotations.py) finds tool registrations with patterns for the main SDKs: `server.tool(...)`, `registerTool(...)` and tool objects with an `inputSchema` in TypeScript and JavaScript, FastMCP decorators and `Tool(...)` objects in Python, `mcp.NewTool` and `mcp.Tool{...}` in Go, `#[tool]` in Rust and `[McpServerTool]` in C#. For each tool it reads the registration's own text and records which hints are set and to what. A tool counts as annotated when it sets at least one of the four hints, or passes its annotations by reference (a shared constant, a helper such as `annotationsFor(name)` or `**READ` keyword arguments) in a repository whose source sets a hint somewhere. An annotations object with only a title or a category does not count. A tool registered twice under the same name in one repository counts once. 304 repositories had at least one recognised registration (17,688 tools, median 14 a repository); 21 contained no source files (a manifest pointing at a remote server or a package published elsewhere) and 73 had source we did not recognise as tool registrations (other languages, SDKs or dynamic registration).

**Name classes.** A tool name is split into words, and the first word that is a known verb decides the class: *destructive* (delete, remove, drop, destroy, purge, erase, wipe, truncate, kill, terminate, revoke, uninstall, overwrite; 777 tools), *outward* (send, pay, transfer, charge, refund, write; 322 tools) or *read* (get, list, search, read, fetch, find, query, describe, show, lookup, view, check, count, inspect, status, info, retrieve; 7,609 tools). The first two together are the 1,099 "delete-or-send" tools. A name is a weak signal of behaviour, so the classes are labelled "named for", not "does".

**Contradictions.** A delete-or-send tool marked `readOnlyHint: true`, or a destructive-class tool marked `destructiveHint: false`. Sending a message is additive in the specification's sense, so `destructiveHint: false` on a send tool is not counted.

**Uncertainty.** Repository-level shares carry 95% Wilson intervals. Tool-level shares are clustered (one repository holds 1,531 tools), so their 95% intervals come from 2,000 bootstrap resamples of repositories (seed 20261016); they are wide, and the repository-level numbers are the more reliable ones.

## Hand check

We read 60 tools drawn at random from the 17,688 (seed 20261016) against their source; the verdicts are in [`data/2026-10/annotations/hand-check.csv`](../data/2026-10/annotations/hand-check.csv). 59 of 60 were real tool registrations (95% CI 91.1% to 99.7%); the other was a server's own name picked up next to a loop that registers tools by reference. For all 59, the annotated or not verdict and the name class matched our reading, including the 8 tools annotated by reference, each traced to a constant or helper that sets hints. One of those 59 was wrong in the first pass (markdown bold in a description read as a keyword spread) and the rule was fixed before the final run. An earlier 40-tool pass found four other extraction faults (client test calls read as registrations, category-only annotation objects counted as hints, quoted hint keys not parsed, test fixtures not skipped); all four were fixed and have tests.

## Results in detail

| Measure | Count | Denominator | Share | 95% CI |
|---|---|---|---|---|
| Repositories that annotate no tool | 188 | 304 | 61.8% | 56.3% to 67.1% |
| Repositories that annotate every tool | 69 | 304 | 22.7% | 18.3% to 27.7% |
| Repositories that set a hint anywhere in their source | 142 | 304 | 46.7% | 41.2% to 52.3% |
| Tools annotated | 6,243 | 17,688 | 35.3% | 23.4% to 47.1% |
| Tools with a hint written in the registration | 4,495 | 17,688 | 25.4% | 15.1% to 36.2% |
| Tools that set `readOnlyHint` | 4,171 | 17,688 | 23.6% | 13.9% to 33.9% |
| Tools that set `destructiveHint` | 2,685 | 17,688 | 15.2% | 7.5% to 24.9% |
| Tools that set `idempotentHint` | 1,971 | 17,688 | 11.1% | 5.2% to 19.0% |
| Tools that set `openWorldHint` | 2,216 | 17,688 | 12.5% | 5.6% to 21.2% |
| Delete-or-send tools annotated | 366 | 1,099 | 33.3% | 18.9% to 51.7% |
| Delete-or-send tools with `destructiveHint: true` | 214 | 1,099 | 19.5% | 8.9% to 33.0% |
| Destructive-class tools annotated | 277 | 777 | 35.6% | 19.8% to 52.5% |
| Destructive-class tools with `destructiveHint: true` | 194 | 777 | 25.0% | 11.2% to 40.7% |
| Outward-class tools annotated | 89 | 322 | 27.6% | 12.1% to 54.5% |
| Repositories with delete-or-send tools, none annotated | 83 | 117 | 70.9% | 62.2% to 78.4% |
| Read-named tools with `readOnlyHint: true` | 2,095 | 7,609 | 27.5% | 14.2% to 40.7% |
| Delete-or-send tools with a contradicting hint | 7 | 1,099 | 0.6% | 0.0% to 1.7% |

By verb, the money-moving names stand out: of the 42 tools named pay or charge, none is annotated; 34 of the 42 come from one repository. Of 582 tools named delete, 197 are annotated and 157 say `destructiveHint: true`. The full breakdown is under `destructive_by_verb` in `results.json`.

## Limitations

- **Static reading of source, not the running server.** We read what the code registers, not what `tools/list` returns. Hints added at run time, by middleware or by a framework default are missed, and a registration we do not recognise is not counted. 73 repositories with source and no recognised registration are outside the denominator; if they differ systematically, the shares would move.
- **Pattern matching.** The hand check bounds the error on what was extracted (59 of 60 real registrations), not what was missed. A tool's text runs to the next registration in the same file, so a hint belonging to a neighbour can occasionally be credited to it.
- **Names are not behaviour.** `send_message` and `delete_draft` are classed by their names. Some read tools are named otherwise and some delete tools hide behind verbs such as `reset` or `update`, which we leave out on purpose to keep the class conservative.
- **Clustering.** A few repositories hold thousands of tools, so pooled tool shares swing with them; read the repository-level shares and the per-repository mean first.
- **A subset of a sample.** These are the 399 repositories in the October 2026 sample that ship a `server.json`, which GitHub code search surfaced for the query in [`METHOD.md`](../METHOD.md). It is not a census of MCP servers, and the confidence intervals describe that pool.
- **Hints are not security.** A correct `readOnlyHint` is a claim by the author. This report measures whether servers make the claim, not whether it is true.

## Reproduce it

```sh
python scripts/annotations_fetch.py /tmp/ann          # about 10 minutes, 399 repositories, about 1 GB of source
python scripts/annotations.py /tmp/ann                # writes data/2026-10/annotations/
python -m pytest -q tests/test_annotations.py         # fixtures, no network
```

Repositories change and can disappear, so a later fetch may differ slightly; the fetch pins each repository to the commit in the dataset to keep that small. The outputs are [`results.json`](../data/2026-10/annotations/results.json) (every number here, with its interval), [`tools.csv`](../data/2026-10/annotations/tools.csv) (one row per tool: repository, file, line, name, class and each hint's value) and [`repos.csv`](../data/2026-10/annotations/repos.csv) (one row per selected repository, with the fetched commit).

The linter used in the first report, [mcp-tools-lint](https://github.com/basitalisandhu/mcp-tools-lint), checks a server's live tool list for missing annotations and for a delete-named tool marked read-only, if you want to run the same checks on a server you are about to install. It starts the server to ask for the list, so run it where you would run the server anyway.
