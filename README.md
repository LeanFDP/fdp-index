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

## Querying with SPARQL

[`sparql.html`](https://fdp.semscape.org/fdp-index/sparql.html) runs SPARQL in the browser with [Comunica](https://comunica.dev), over `index.ttl` and the latest snapshot of every FDP the crawl reached. There is no server: the page loads those files from the site and queries them locally. It has example queries (catalogs, datasets by keyword, themes, publishers, licences, distributions), CSV and SPARQL-JSON downloads, and links that carry the query (`?query=…&sources=…`).

You can add your own sources: any RDF file, or `sparql@https://…/sparql` for a SPARQL endpoint that allows CORS (for example `sparql@https://sparql.uniprot.org/sparql`), so a query can join the index with other data.

This is not a SPARQL *endpoint* that other software can call: GitHub Pages only serves files. For that, point a SPARQL server (for example [Comunica's `comunica-sparql-file-http`](https://comunica.dev/docs/query/getting_started/setup_endpoint/)) at `index.ttl` and the snapshots.

## Related: the Lean FDP Index service

Mark Wilkinson's [Lean FDP Index](https://github.com/markwilkinson/lean-fdp-index) does the same job as a hosted service, running for ERDERA at <https://erdera-vp-index.linkeddata.systems/>. The two follow the same idea: a small index that records what each FDP returns, rechecks it daily and needs nothing from the FDP beyond its RDF. They differ in where they run and how you register.

| | This repository (fdp-index) | Lean FDP Index service |
|---|---|---|
| Runs on | GitHub Actions and Pages, no server | A server with a triplestore (Virtuoso) |
| Register | Issue form or pull request on `registry.yaml`, reviewed | `POST /` with `{"clientUrl": …}`, the FDP reference implementation's own ping, no review |
| Granularity | One entry per FDP root | One entry per resource: FDPs, catalogs, datasets, distributions and data services found by traversal |
| Daily recheck | Crawls every entry; failures are reported | Rechecks every entry; entries that keep failing are removed |
| Query | Static `index.ttl` / `index.jsonld`; SPARQL in the browser with `sparql.html` | Public SPARQL endpoint (`/sparql`), `GET /entries` JSON |

Static FDPs work with both: the service already indexes the document-based ERDERA WP13 FDP on GitHub Pages. You can register a Lean FDP in both places.

## Index outputs (gh-pages)

| File | Format | Description |
|------|--------|-------------|
| `index.jsonld` | JSON-LD | Full index — all FDP metadata |
| `index.ttl` | Turtle | Same, as Turtle |
| `index.html` | HTML | Human-browsable index |
| `sparql.html` | HTML | SPARQL in the browser (Comunica) over the index and the snapshots |
| `fdps/{slug}/snapshot.jsonld` | JSON-LD | Per-FDP metadata snapshot |
| `fdps/{slug}/snapshot.ttl` | Turtle | Per-FDP metadata snapshot |
| `crawl-report.json` | JSON | Last crawl stats + errors |

## Schemas

Shape validation of FDP metadata lives in the publish layer: the [FDP ecosystem template](https://github.com/LeanFDP/fdp-ecosystem-template) checks every node against ShEx shapes (`scripts/shapes/fdp-ecosystem.shex`, ported from [static-fdp](https://github.com/LeanFDP/static-fdp)). This index does not validate; it records what each FDP returns.
