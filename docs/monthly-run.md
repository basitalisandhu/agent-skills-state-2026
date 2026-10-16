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
