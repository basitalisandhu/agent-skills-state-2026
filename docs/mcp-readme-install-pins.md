# Do MCP server READMEs tell you which version to run? Install pins in 264 public servers, October 2026

*Muhammad Basit Ali, 20 October 2026. A follow-up to [the October 2026 study](../README.md), using its sample and method. Data and text: CC BY 4.0. Code: MIT.*

Most people install a local MCP server by copying a snippet from its README into a client config: `"command": "npx", "args": ["-y", "some-server"]`, `uvx some-server` or `docker run -i --rm some/image`. Whatever version that snippet names is the version people run. The first report measured the configurations committed to repositories and found that 159 of 346 (46.0%) start at least one server with no pinned version. This report asks where those lines come from: what the servers' own READMEs tell people to type.

## Key findings

- **READMEs almost never name a version.** Of the 264 MCP server repositories whose READMEs contain a launch command, 252 of 264 (95.5%) never pin an exact version in any of them (95% CI 92.2% to 97.4%). Only 12 of 264 (4.5%) show an exact version at least once (95% CI 2.6% to 7.8%), and 259 of 264 (98.1%) show at least one floating command (95% CI 95.6% to 99.2%).
- **The version is known; the README leaves it out.** 212 of these repositories ship a `server.json`, the manifest the official MCP Registry reads, that gives an exact version of their own package. In 202 of 212 (95.3%) the README's commands for that same package never name a version (95% CI 91.5% to 97.4%), and in 207 of 212 (97.6%) at least one of them floats (95% CI 94.6% to 99.0%).
- **A quarter ask for the newest release on every launch.** 69 of 264 (26.1%) repositories use an explicit moving tag: `@latest`, `:latest`, `--refresh` or similar (95% CI 21.2% to 31.8%). These commands pull a new release the next time the client starts, with no review in between.
- **Commands, not just repositories.** 817 of 835 (97.8%) distinct launch commands float (95% CI 96.1% to 99.1%, resampling repositories). 410 of the 576 `npx` commands (71.2%) also pass `-y`, which skips npx's prompt before it installs a package it has not seen.
- **Every ecosystem, every size.** For npm, 188 of 189 (99.5%) repositories show a floating command; for PyPI, 66 of 69 (95.7%); for container images, 53 of 55 (96.4%). Repositories with 100 or more stars are no different: 65 of 69 (94.2%) never pin, against 187 of 195 (95.9%) with fewer.

Every share above is checked against [`data/2026-10/readme-pins/results.json`](../data/2026-10/readme-pins/results.json) by [`tests/test_readme_pins.py`](../tests/test_readme_pins.py) in CI.

> **What to check before you install an MCP server**
>
> 1. Look up the version you mean to run: the repository's `server.json`, its registry page or its latest release. Then write it into your config: `npx -y some-server@1.4.2`, `uvx some-server==0.9.1` (or `uvx some-server@0.9.1`), `docker run -i --rm some/image@sha256:...`. Nineteen READMEs in twenty will not do this for you.
> 2. Read `@latest`, `:latest`, `uvx --refresh`, `npx --prefer-online` and `docker run --pull always` as "install whatever was published last night, every time the client starts". A quarter of READMEs ask for that.
> 3. A bare name (`npx -y some-server`, `uvx some-server`, `some/image` with no tag) is not a pin either. You get whatever version your cache already holds, or the newest one on a fresh machine, so two people following the same README can run different code.
> 4. `npx -y` answers yes to the install prompt for you. Keep it only once the package and version are ones you chose.
> 5. Proxies count. All 17 repositories that tell you to run `mcp-remote` leave its version open; pin it like any other package.
> 6. An exact version pins the top-level package only. Its own dependencies can still float, so for a server you depend on, prefer a lockfile, an image digest or a recorded tool-contract hash, as the [RugSnare drift-watch corpus](https://github.com/Paraphern/rugsnare/tree/main/docs/servers) shows for servers whose tools changed under a fixed version.
> 7. Upgrade on purpose: read the changelog, change the pin, restart.

## Why this matters

A floating launch command means the code your agent runs is chosen by the package registry on the day you start the client, not by you. If a maintainer account is taken over, or a release ships a bug or a changed tool, everyone on a floating command picks it up on their next restart. An MCP server runs with the user's own permissions and often with API tokens in its environment, so that is the same exposure as an unpinned dependency in a production build, minus the lockfile.

This is not a vulnerability in any one server, and nothing here says any package is malicious. It is a default. The README is the template, people copy it, and the first report's 46.0% of unpinned committed configurations is what that template looks like downstream. The fix is cheap and sits with the maintainer: print the exact version in the README and bump it on release, as the 12 repositories that do already show. The MCP project's own quickstart and example pages use the same unpinned form; that is the subject of [modelcontextprotocol/modelcontextprotocol#3431](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3431).

## Method in brief

**Selection.** The same 399 repositories as the [tool annotations report](mcp-tool-annotations.md): every repository in [`data/2026-10/dataset.json`](../data/2026-10/dataset.json) with `has_server_json` true, a random subset of the study's random sample, under the 400-repository ceiling for re-fetching.

**Fetch.** [`scripts/readme_pins_fetch.py`](../scripts/readme_pins_fetch.py) reuses `scripts/annotations_fetch.py`: a blob-less, depth-1 fetch of the exact commit in the dataset, with git hooks, LFS and symbolic links disabled and the study's caps (1 MB a file, 3,000 files and 30 MB a repository). Only README files and `server.json` files were checked out; test, example, fixture, vendored and build folders were left out. Nothing was built, installed or run. 391 of 399 were fetched at their recorded commit on 20 October 2026; 8 repositories were no longer available (7 of them from one organisation).

**What counts as a launch command.** [`scripts/readme_pins.py`](../scripts/readme_pins.py) reads the root README and the README next to each `server.json`. It finds commands that fetch a published package or image and run it, for the launchers `npx`, `bunx`, `pnpm dlx`, `yarn dlx`, `uvx`, `uv tool run`, `pipx run` and `docker run`, in three forms: client configs in JSON, TOML or YAML (`"command": "npx"` with its `args`), shell lines (`claude mcp add x -- uvx pkg`, `docker run -i --rm image`, joined across `\` continuations) and inline code (`` `npx -y pkg` ``). Shell lines count only inside code, so prose that mentions npx is skipped, and shell comments are skipped. Left out: development tools (the MCP Inspector, test runners, build and lint tools, scaffolders, installers that write a config instead of starting a server; the list is `EXCLUDED_PACKAGES` in the script), local paths, placeholders such as `pkg@<version>` and `@scope/mcp-<name>`, and images built by a `docker build -t` in the same README. A command is counted once per repository for each distinct launcher, package and version text. 264 repositories had at least one launch command (835 commands, median 1 a repository, at most 116 in one repository); 124 had a README but no launch command, which is what a remote-only server, a source build or a `npm install -g` README looks like.

**Version classes.** Each command's package spec is classed as *exact* (`pkg@1.2.3`, `pkg==1.2.3`, `image:1.2.3`, an image digest, or a git source at a full commit hash), *range* (`pkg@^1`, `pkg>=1.0`, `image:1`), *latest* (an explicit moving tag: `latest`, `next`, `main`, other non-version tags, or a flag that re-resolves on every launch: `uvx --refresh`, `npx --prefer-online`, `docker run --pull always`) or *unpinned* (no version, including a git source at a branch). The last three are *floating*.

**The repository's own package.** A command is the repository's own when its package matches, by ecosystem and normalised name, a package that the repository's `server.json` declares. 303 repositories declare at least one npm, PyPI or container package; 219 of those have a README launch command for one of them, and in 212 the declared version is exact. Of the 14 exact own-package commands, 9 name the same version as `server.json` and 5 a different one.

**Uncertainty.** Repository-level shares carry 95% Wilson intervals. Command-level shares are clustered (one repository holds 116 commands), so their 95% intervals come from 2,000 bootstrap resamples of repositories (seed 20261020).

## Hand check

We read 60 commands drawn at random from the 835 (the 60 with the smallest SHA-256 of seed 20261020, repository, file, line and package, so the draw does not shift when unrelated rows change) against the README they came from; the verdicts are in [`data/2026-10/readme-pins/hand-check.csv`](../data/2026-10/readme-pins/hand-check.csv).

- 60 of 60 were real instructions to fetch and run a published package or image (95% CI 94.0% to 100%).
- 56 of 60 start the MCP server itself, or the package its `server.json` declares (95% CI 84.1% to 97.4%). The other 4 are a driver setup step run with `uvx` (the same README in a repository and its copy), an installer for the server and a news CLI from a package in the same monorepo. All four still fetch and run unpinned code, so they are kept, but the "launch command" label is about 93% precise.
- For 60 of 60 the version class (exact, range, latest or unpinned) matched our reading.

Two earlier passes over the same kind of sample found faults that were fixed, with tests, before the final run: prose mentions read as commands, placeholder names (`package-name`, `@your/mcp-server`, `pkg@<version>`), a shell comment that swallowed the command on the next line, quoted environment values that split `docker run` arguments, locally built images, and installer CLIs (`plugins add`, `skild install`). We also read every README line that mentions a launcher in the repositories where no command was found; that pass added YAML configs and git sources to the patterns, and what remains there is development tooling, prose and locally built images.

## Results in detail

| Measure | Count | Denominator | Share | 95% CI |
|---|---|---|---|---|
| Repositories that never show an exact version | 252 | 264 | 95.5% | 92.2% to 97.4% |
| Repositories with at least one floating command | 259 | 264 | 98.1% | 95.6% to 99.2% |
| Repositories with at least one exact version | 12 | 264 | 4.5% | 2.6% to 7.8% |
| Repositories with an explicit moving tag | 69 | 264 | 26.1% | 21.2% to 31.8% |
| Commands that float | 817 | 835 | 97.8% | 96.1% to 99.1% |
| Commands with an explicit moving tag | 115 | 835 | 13.8% | 9.2% to 20.8% |
| Own package: README never pins, `server.json` exact | 202 | 212 | 95.3% | 91.5% to 97.4% |
| Own package: some command floats, `server.json` exact | 207 | 212 | 97.6% | 94.6% to 99.0% |
| npm repositories with a floating command | 188 | 189 | 99.5% | 97.1% to 99.9% |
| PyPI repositories with a floating command | 66 | 69 | 95.7% | 88.0% to 98.5% |
| Container image repositories with a floating command | 53 | 55 | 96.4% | 87.7% to 99.0% |
| Git source repositories with a floating command | 9 | 9 | 100% | 70.1% to 100% |
| `npx` commands with `-y` | 410 | 576 | 71.2% | 60.2% to 82.6% |
| Repositories running `mcp-remote` unpinned | 17 | 17 | 100% | 81.6% to 100% |
| 100+ stars: never pin | 65 | 69 | 94.2% | 86.0% to 97.7% |
| Under 100 stars: never pin | 187 | 195 | 95.9% | 92.1% to 97.9% |

By class, the 835 commands split into 700 unpinned, 115 latest, 2 range and 18 exact. By launcher: 576 `npx`, 178 `uvx`, 65 `docker run`, 10 `bunx`, 4 `uv tool run` and 2 `pipx run`.

## Limitations

- **READMEs only.** We read the root README and the README beside each `server.json`. A docs site, a separate install page or a registry listing may give a pinned command that the README does not; a user who follows those is better off than these numbers suggest.
- **What "floating" means depends on the cache.** A bare `npx` or `uvx` name runs the version the machine cached first and does not by itself update later; a moving tag re-checks on every launch. Neither is a pin, but the risk is not the same, which is why the moving-tag share is reported on its own.
- **Static pattern matching.** The hand check bounds the error on what was found (60 of 60 real instructions, 56 of 60 server launches), not what was missed. Commands built from variables, generated by an install script or written in a form we did not recognise are not counted.
- **Clustering and copies.** Monorepos ship many READMEs with the same snippet; one repository has 116 commands. The repository-level shares are the ones to quote. A few repositories in the sample are copies of each other.
- **A subset of a sample.** These are the repositories in the October 2026 sample that ship a `server.json`, which GitHub code search surfaced for the query in [`METHOD.md`](../METHOD.md). They are not a census of MCP servers, and the intervals describe that pool. Eight repositories had gone by 20 October.
- **A pin is not a guarantee.** An exact version still trusts the maintainer and the registry, and its dependencies can float. This report measures whether READMEs name a version, not whether a pinned version is safe.

## Reproduce it

```sh
python scripts/readme_pins_fetch.py /tmp/pins         # about 15 minutes, 399 repositories, READMEs and server.json only
python scripts/readme_pins.py /tmp/pins               # writes data/2026-10/readme-pins/
python -m pytest -q tests/test_readme_pins.py         # fixtures, no network
```

Repositories change and can disappear, so a later fetch may differ slightly; the fetch pins each repository to the commit in the dataset to keep that small. The outputs are [`results.json`](../data/2026-10/readme-pins/results.json) (every number here, with its interval, and the hand-check sample's row numbers), [`commands.csv`](../data/2026-10/readme-pins/commands.csv) (one row per distinct launch command: repository, file, line, form, launcher, ecosystem, package, version text, class, `-y`, whether it is the repository's own package and the version its `server.json` declares) and [`repos.csv`](../data/2026-10/readme-pins/repos.csv) (one row per selected repository, with the fetched commit).

No number in the first edition or in the tool annotations report changes.
