# Running the monthly index

The scheduled workflow [`.github/workflows/monthly.yml`](../.github/workflows/monthly.yml) runs `scripts/run_month.py` on the 1st of each month at 03:00 UTC and opens a pull request with the new month. This page says what it needs and how to check it before the 1st.

## The search token

The pipeline starts with GitHub code search across all public repositories (`GET /search/code`). The workflow passes `secrets.SEARCH_TOKEN` when that secret exists and falls back to the workflow's own `GITHUB_TOKEN` otherwise:

```yaml
GITHUB_TOKEN: ${{ secrets.SEARCH_TOKEN || github.token }}
```

If the workflow's own token is refused, `run_month.py` stops at once with a message naming this page, instead of waiting on a limit that will never reset or carrying on with an empty sample. To add a search token:

1. Create a fine-grained personal access token at <https://github.com/settings/personal-access-tokens/new> with **Public repositories (read-only)** access and no other permissions. Give it an expiry date and a name such as `agent-skills-state monthly search`.
2. In this repository, go to **Settings > Secrets and variables > Actions > New repository secret**, name it `SEARCH_TOKEN` and paste the token.
3. Run the dry run below to check it.

The token is read once by `run_month.py`, sent only to `api.github.com`, never printed and never passed to a child process.

## Dry run before the 1st

**Actions > Monthly index > Run workflow**, with `limit` set to a small number such as `30`. A dry run makes one search request per kind of file (4 in all), scans that many repositories, prints only counts and timings, writes nothing to `data/` and opens no pull request. From a terminal:

```sh
gh workflow run monthly.yml -f limit=30
gh run watch
```

The last line of the log is a JSON summary with `search_requests`, `search_hits`, `pool_repos`, `sampled`, `fetch_status`, `search_minutes`, `scan_minutes`, `workers` and `minutes`.

## Does it fit in the job limit?

The job has `timeout-minutes: 120`. A full run makes 93 search requests about seven seconds apart (about 11 minutes, more when GitHub asks it to wait), then fetches and scans 3,000 repositories in parallel. Scale `scan_minutes` from the dry run by 3,000 divided by `limit` to estimate the scan.

### Measured on 16 October 2026

A dry run with `limit=30` on `main` ([run 38852975815](https://github.com/basitalisandhu/agent-skills-state-2026/actions/runs/38852975815)), with no `SEARCH_TOKEN` secret, so on the workflow's own token:

```json
{"search_requests": 9, "graphql_requests": 1, "search_hits": 400, "pool_repos": 344, "sampled": 30,
 "fetch_status": {"ok": 30}, "search_minutes": 1.7, "scan_minutes": 0.1, "workers": 12, "minutes": 2.0,
 "repos": 30, "repos_with_skills": 24}
```

- **The workflow token can use code search.** All four queries returned results; the five extra requests were retries, which the script makes after waiting out a rate limit or a server error. No `SEARCH_TOKEN` is needed today; add one only if a later run stops with the 403 message above.
- **Time budget.** Search took 1.7 minutes for 4 pages, about 25 seconds a page with the waits; 93 pages at that pace is about 40 minutes. The scan took 0.1 minutes for 30 repositories on 12 workers, which scales to about 10 minutes for 3,000; the metadata step adds about 60 GraphQL requests. That is about an hour in all, inside the 120-minute limit, so the run needs no checkpointing at the default sample of 3,000. If a later dry run's estimate passes about 100 minutes, lower `SAMPLE_SIZE` in `scripts/run_month.py` or split the search across two jobs before the 1st.
- **Opening the pull request.** The repository allows GitHub Actions to create pull requests (Settings > Actions > General > Workflow permissions). A pull request opened with the workflow token does not start CI, which is why the job runs `check_numbers.py` itself and the pull request body says so.
