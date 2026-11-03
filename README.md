# FDP Index

A serverless FAIR Data Point index backed entirely by GitHub. This is the canonical index of the [Lean FDP](https://fdp.semscape.org) family; it replaces [staticfdp-index](https://github.com/LeanFDP/staticfdp-index), whose registration form now lives here.

- **Registry** — `registry.yaml` in this repo lists every FDP root to crawl
- **Crawl** — a GitHub Actions workflow runs every day at 03:00 UTC, crawls all registered FDPs, and commits results to the `gh-pages` branch
- **Index** — served as static files from GitHub Pages at `https://fdp.semscape.org/fdp-index/`
- **Ping** — FDP repos trigger a re-crawl by sending a GitHub Repository Dispatch event (no server needed)

## Adding your FDP

**Option A — Registration form (recommended):**
Fill in the [registration page](https://fdp.semscape.org/fdp-index/register.html). It looks up your organisation in [ROR](https://ror.org) and checks your ORCID iD, then opens a prefilled issue ([*Register a FAIR Data Point*](https://github.com/LeanFDP/fdp-index/issues/new?template=register-fdp.yml)). The *Register FDP from issue* workflow (`scripts/register_from_issue.py`) checks the URL, fetches it once to see that it returns RDF, and opens a pull request that adds the entry to `registry.yaml`. Edit the issue to run it again. Once merged, your FDP is crawled in the next daily run. The publisher's ROR id is added to the index as `dcterms:publisher` when the FDP does not state a publisher itself.

**Option B — Pull request:**
Add an entry to `registry.yaml` yourself and open a PR. The registration page also shows the entry to paste.

**Option C — Automated ping from your FDP repo:**
In your FDP repo's `publish.yml`, add:
```yaml
- name: Ping FDP index
  run: |
    curl -sf -X POST \
      -H "Authorization: Bearer ${{ secrets.FDPINDEX_DISPATCH_TOKEN }}" \
      -H "Accept: application/vnd.github.v3+json" \
      -H "Content-Type: application/json" \
      -d '{"event_type":"fdp-ping","client_payload":{"url":"${{ vars.FDP_ROOT_URL }}"}}' \
      https://api.github.com/repos/LeanFDP/fdp-index/dispatches
```
`FDPINDEX_DISPATCH_TOKEN` must be a fine-grained PAT with `contents:write` on this repo.
On first ping your FDP is added to `registry.yaml` automatically.

## Dead FDPs and notifications

After every crawl, `scripts/status.py` compares the result with the previous one and keeps, for each FDP, since when it fails and why (`status.json` on the site).

| When | What happens |
|---|---|
| 3 failed crawls in a row | The FDP is marked **down** on the index page, and an issue labelled [`fdp-down`](https://github.com/LeanFDP/fdp-index/issues?q=label%3Afdp-down) is opened with the error, the date it started and the contact from the registry |
| Failing for 30 days (and at least 10 crawls) | A pull request proposes removing it from `registry.yaml`. Nothing is removed until a maintainer merges it; if the FDP has moved, change its URL instead |
| It answers again | The issue gets a comment and is closed; an open removal PR is closed too |

The thresholds are at the top of `scripts/status.py`. If GitHub Actions may not open pull requests in this repository (*Settings → Actions → General*), the removal is pushed to a `status/remove-…` branch and the issue links to it.

**Getting told when your FDP stops answering:**

- **GitHub:** list your account under `watchers:` for your entry in `registry.yaml` (the registration form has a field for it, and adds whoever submits it). Watchers are mentioned in the outage issue, so GitHub notifies them by e-mail and keeps them subscribed until it closes. Anyone can also subscribe to an open `fdp-down` issue, or watch the repository for issues.
- **No GitHub account:** follow an Atom feed in any feed reader, or a feed-to-e-mail service:
  - all outages and recoveries: <https://fdp.semscape.org/fdp-index/status.atom>
  - one FDP: `https://fdp.semscape.org/fdp-index/fdps/{slug}/status.atom` (linked from its card on the index page)

```yaml
  - url:      https://fdp.example.org
    label:    "Example FDP"
    watchers: ["your-github-login"]
```

If `status.json` is missing, the history is rebuilt from the earlier crawl reports on the `gh-pages` branch, so existing outages keep their start date.

## Index outputs (gh-pages)

| File | Format | Description |
|------|--------|-------------|
| `index.jsonld` | JSON-LD | Full index — all FDP metadata |
| `index.ttl` | Turtle | Same, as Turtle |
| `index.html` | HTML | Human-browsable index |
| `fdps/{slug}/snapshot.jsonld` | JSON-LD | Per-FDP metadata snapshot |
| `fdps/{slug}/snapshot.ttl` | Turtle | Per-FDP metadata snapshot |
| `crawl-report.json` | JSON | Last crawl stats + errors |
| `status.json` | JSON | Per-FDP state (up, failing, down, removal proposed), failing since, last error, issue; last 100 events |
| `status.atom` | Atom | Outages and recoveries of all FDPs |
| `fdps/{slug}/status.atom` | Atom | Outages and recoveries of one FDP |

## Schemas

Shape validation of FDP metadata lives in the publish layer: the [FDP ecosystem template](https://github.com/LeanFDP/fdp-ecosystem-template) checks every node against ShEx shapes (`scripts/shapes/fdp-ecosystem.shex`, ported from [static-fdp](https://github.com/LeanFDP/static-fdp)). This index does not validate; it records what each FDP returns.
