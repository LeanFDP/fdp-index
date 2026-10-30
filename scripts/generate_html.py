#!/usr/bin/env python3
"""
Generate a human-readable HTML index page from crawl-report.json
and the serialised RDF outputs in ./output/.

Writes: output/index.html
"""

import json
import datetime
from pathlib import Path

OUTPUT = Path("output")


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lean FDP Index</title>
  <style>
    :root {{
      --bg:       #f9f9f9;
      --surface:  #ffffff;
      --border:   #dde1e7;
      --accent:   #2563eb;
      --ok:       #16a34a;
      --err:      #dc2626;
      --warn:     #d97706;
      --text:     #1e293b;
      --muted:    #64748b;
      --radius:   8px;
      --mono:     "SFMono-Regular", Consolas, monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 1.5rem 2rem;
    }}
    header h1 {{ font-size: 1.5rem; font-weight: 700; }}
    header p  {{ color: var(--muted); font-size: 0.9rem; margin-top: 0.25rem; }}
    main {{
      max-width: 960px;
      margin: 2rem auto;
      padding: 0 1.5rem;
    }}
    .meta-bar {{
      display: flex;
      gap: 2rem;
      flex-wrap: wrap;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem 1.5rem;
      margin-bottom: 1.5rem;
      font-size: 0.875rem;
    }}
    .meta-bar .stat {{ display: flex; flex-direction: column; }}
    .meta-bar .stat .value {{ font-size: 1.5rem; font-weight: 700; color: var(--accent); }}
    .meta-bar .stat .label {{ color: var(--muted); }}
    .downloads {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      margin-bottom: 1.5rem;
      font-size: 0.85rem;
    }}
    .downloads a {{
      display: inline-block;
      padding: 0.3rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: 999px;
      color: var(--accent);
      text-decoration: none;
      background: var(--surface);
    }}
    .downloads a:hover {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    h2 {{ font-size: 1.1rem; margin: 1.5rem 0 0.75rem; color: var(--muted); text-transform: uppercase;
          letter-spacing: 0.05em; font-size: 0.78rem; }}
    .fdp-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem 1.5rem;
      margin-bottom: 1rem;
    }}
    .fdp-card.error {{ border-left: 4px solid var(--err); }}
    .fdp-card.ok    {{ border-left: 4px solid var(--ok);  }}
    .fdp-header {{ display: flex; align-items: flex-start; gap: 0.75rem; }}
    .status-dot {{
      width: 10px; height: 10px; border-radius: 50%;
      margin-top: 0.45rem; flex-shrink: 0;
    }}
    .status-dot.ok    {{ background: var(--ok);  }}
    .status-dot.error {{ background: var(--err); }}
    .fdp-title {{ font-weight: 600; font-size: 1rem; }}
    .fdp-url   {{
      font-family: var(--mono);
      font-size: 0.78rem;
      color: var(--accent);
      word-break: break-all;
    }}
    .fdp-url a {{ color: inherit; }}
    .fdp-stats {{
      display: flex;
      gap: 1.5rem;
      flex-wrap: wrap;
      margin-top: 0.75rem;
      font-size: 0.825rem;
      color: var(--muted);
    }}
    .fdp-stats .chip {{
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 0.15rem 0.5rem;
    }}
    .fdp-links {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      margin-top: 0.75rem;
      font-size: 0.8rem;
    }}
    .fdp-links a {{
      color: var(--accent);
      text-decoration: none;
      border-bottom: 1px solid transparent;
    }}
    .fdp-links a:hover {{ border-bottom-color: var(--accent); }}
    .fdp-links .sep {{ color: var(--border); }}
    .error-msg {{
      margin-top: 0.5rem;
      font-size: 0.8rem;
      color: var(--err);
      font-family: var(--mono);
    }}
    footer {{
      text-align: center;
      font-size: 0.8rem;
      color: var(--muted);
      padding: 2rem 1rem 3rem;
    }}
    footer a {{ color: var(--accent); }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f172a; --surface: #1e293b; --border: #334155;
        --text: #e2e8f0; --muted: #94a3b8;
      }}
    }}
  </style>
</head>
<body>

<header>
  <h1>Lean FDP Index</h1>
  <p>Daily-crawled index of <a href="https://www.go-fair.org/fair-principles/" style="color:var(--accent)">FAIR Data Points</a>
     hosted via <a href="https://github.com/LeanFDP" style="color:var(--accent)">Lean FDP / fdpCloud</a>.
     GitHub is the canonical source — no server required.</p>
</header>

<main>

  <div class="meta-bar">
    <div class="stat">
      <span class="value">{total}</span>
      <span class="label">Registered FDPs</span>
    </div>
    <div class="stat">
      <span class="value" style="color:var(--ok)">{succeeded}</span>
      <span class="label">Successfully crawled</span>
    </div>
    <div class="stat">
      <span class="value">{total_resources}</span>
      <span class="label">RDF resources indexed</span>
    </div>
    <div class="stat">
      <span class="value">{total_datasets}</span>
      <span class="label">Datasets discovered</span>
    </div>
    <div class="stat" style="margin-left:auto">
      <span class="value" style="font-size:0.95rem;color:var(--muted)">{crawled_at}</span>
      <span class="label">Last crawl (UTC)</span>
    </div>
  </div>

  <div class="downloads">
    <strong style="align-self:center;margin-right:0.25rem">Download index:</strong>
    <a href="index.jsonld">JSON-LD</a>
    <a href="index.ttl">Turtle</a>
    <a href="crawl-report.json">Crawl report (JSON)</a>
    <a href="https://github.com/LeanFDP/fdp-index">Source on GitHub</a>
    <a href="register.html">Register your FDP</a>
  </div>

  <h2>Registered FAIR Data Points</h2>

{fdp_cards}

</main>

<footer>
  <p>
    Data indexed under
    <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> ·
    <a href="register.html">Register your FDP</a>
  </p>
</footer>

</body>
</html>
"""


FDP_CARD_OK = """\
<div class="fdp-card ok">
  <div class="fdp-header">
    <div class="status-dot ok" title="Crawl succeeded"></div>
    <div>
      <div class="fdp-title">{label}</div>
      <div class="fdp-url"><a href="{url}" target="_blank" rel="noopener">{url}</a></div>
    </div>
  </div>
  <div class="fdp-stats">
    <span class="chip">{resources} resources</span>
    <span class="chip">{catalogs} catalog(s)</span>
    <span class="chip">{datasets} dataset(s)</span>
    <span>{elapsed}s crawl time</span>
  </div>
  <div class="fdp-links">
    <a href="{snapshot_jsonld}" target="_blank">Snapshot JSON-LD</a>
    <span class="sep">·</span>
    <a href="{snapshot_ttl}"    target="_blank">Snapshot Turtle</a>
    <span class="sep">·</span>
    <a href="{url}"             target="_blank">Live FDP root</a>
  </div>
</div>
"""


FDP_CARD_ERR = """\
<div class="fdp-card error">
  <div class="fdp-header">
    <div class="status-dot error" title="Crawl failed"></div>
    <div>
      <div class="fdp-title">{label}</div>
      <div class="fdp-url"><a href="{url}" target="_blank" rel="noopener">{url}</a></div>
    </div>
  </div>
  <div class="error-msg">Crawl failed — 0 resources retrieved. Check the FDP root URL is accessible.</div>
</div>
"""


def url_to_slug(url: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_-]", "_", url)[:80]


def main():
    report_path = OUTPUT / "crawl-report.json"
    if not report_path.exists():
        print(f"No crawl-report.json found at {report_path}", flush=True)
        return

    with open(report_path) as f:
        report = json.load(f)

    # Parse crawl timestamp
    try:
        dt = datetime.datetime.fromisoformat(report["crawled_at"].rstrip("Z"))
        crawled_at = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        crawled_at = report.get("crawled_at", "unknown")

    # Aggregate stats
    total_resources = sum(e["stats"].get("resources", 0) for e in report["fdps"])
    total_datasets  = sum(e["stats"].get("datasets",  0) for e in report["fdps"])

    # Build FDP cards
    cards = []
    for entry in report["fdps"]:
        s    = url_to_slug(entry["url"])
        base = f"fdps/{s}"
        if entry["status"] == "ok":
            cards.append(FDP_CARD_OK.format(
                label           = entry.get("label") or entry["url"],
                url             = entry["url"],
                resources       = entry["stats"].get("resources", 0),
                catalogs        = entry["stats"].get("catalogs",  0),
                datasets        = entry["stats"].get("datasets",  0),
                elapsed         = entry.get("elapsed_s", "?"),
                snapshot_jsonld = f"{base}/snapshot.jsonld",
                snapshot_ttl    = f"{base}/snapshot.ttl",
            ))
        else:
            cards.append(FDP_CARD_ERR.format(
                label = entry.get("label") or entry["url"],
                url   = entry["url"],
            ))

    html = HTML_TEMPLATE.format(
        total           = report["total"],
        succeeded       = report["succeeded"],
        total_resources = total_resources,
        total_datasets  = total_datasets,
        crawled_at      = crawled_at,
        fdp_cards       = "\n".join(cards),
    )

    out = OUTPUT / "index.html"
    out.write_text(html, encoding="utf-8")

    # Static pages (the registration form) are published next to the index.
    pages = Path(__file__).resolve().parent.parent / "pages"
    for page in sorted(pages.glob("*.html")):
        (OUTPUT / page.name).write_text(page.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"HTML index written to {out}")


if __name__ == "__main__":
    main()
