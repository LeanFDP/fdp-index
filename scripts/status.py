#!/usr/bin/env python3
"""
FDP status history, outage issues, Atom feeds and reviewed removal
------------------------------------------------------------------
Runs after crawl.py. It compares this crawl with the previous status and keeps,
per registered FDP, since when it fails and why:

    python3 scripts/status.py --previous ../gh-pages/status.json --history ../gh-pages
    python3 scripts/status.py ... --github        # also open/close issues and pull requests

Outputs (next to the index, so they are published on gh-pages):
  output/status.json                   state per FDP + the last events
  output/status.atom                   Atom feed of all outages and recoveries
  output/fdps/{slug}/status.atom       Atom feed for one FDP

What happens to an FDP that stops answering:
  1. After DOWN_AFTER failed crawls in a row it is "down": an issue labelled
     fdp-down is opened, mentioning the entry's watchers and pointing to the feeds.
  2. After it has failed continuously for REMOVE_AFTER_DAYS days (and at least
     REMOVE_AFTER crawls), a pull request proposes removing it from registry.yaml.
     Nothing is removed until a maintainer merges it.
  3. When it answers again, the issue is closed and the removal PR (if any) closed.

Without a previous status.json, the history is rebuilt from the git history of
crawl-report.json on gh-pages (--history), so existing outages keep their start date.
Without --github nothing is written to GitHub; the planned actions are printed.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

# ── Config ────────────────────────────────────────────────────────────────────
DOWN_AFTER        = 3     # failed crawls in a row before an outage issue is opened
REMOVE_AFTER      = 10    # … and at least this many failed crawls
REMOVE_AFTER_DAYS = 30    # failing continuously this long → propose removal
MAX_EVENTS        = 100   # events kept in status.json and the feed
DOWN_LABEL        = "fdp-down"
SITE_URL          = "https://fdp.semscape.org/fdp-index/"
ROOT              = Path(__file__).resolve().parent.parent
OUTPUT            = Path("output")
GITHUB_LOGIN      = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


def slug(url: str) -> str:
    """Same slug as crawl.py, so per-FDP files sit together."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", url)[:80]


def parse_time(s: str) -> datetime.datetime:
    t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def marker(url: str) -> str:
    return f"<!-- fdp-status: {url} -->"


# ── State transitions ─────────────────────────────────────────────────────────

def blank(url: str, label: str) -> dict:
    return {"label": label, "state": "up", "consecutive_failures": 0, "first_failure": None,
            "last_ok": None, "last_checked": None, "last_error": None,
            "issue": None, "removal_pr": None}


def apply_report(status: dict, report: dict, registry: dict, record_events: bool = True) -> None:
    """Fold one crawl report into status (in place)."""
    when = report["crawled_at"]
    fdps = status.setdefault("fdps", {})
    events = status.setdefault("events", [])

    def event(kind, url, s, text):
        if record_events:
            events.append({"id": f"{when}/{kind}/{slug(url)}", "time": when, "type": kind,
                           "url": url, "label": s["label"], "text": text})

    for r in report.get("fdps", []):
        url = r["url"]
        reg = registry.get(url, {})
        s = fdps.setdefault(url, blank(url, r.get("label") or url))
        s["label"] = reg.get("label") or r.get("label") or s["label"]
        s["last_checked"] = when
        if r["status"] == "ok":
            if s["state"] != "up" and s["consecutive_failures"] >= DOWN_AFTER:
                event("recovered", url, s, f"{s['label']} answers again, after failing since {s['first_failure'][:10]}.")
            s.update(state="up", consecutive_failures=0, first_failure=None, last_ok=when, last_error=None)
        else:
            s["consecutive_failures"] += 1
            s["first_failure"] = s["first_failure"] or when
            s["last_error"] = r.get("error") or "no RDF resources retrieved"
            days = (parse_time(when) - parse_time(s["first_failure"])).days
            if s["state"] == "up":
                s["state"] = "failing"
            if s["state"] == "failing" and s["consecutive_failures"] >= DOWN_AFTER:
                s["state"] = "down"
                event("down", url, s, f"{s['label']} has not answered in {s['consecutive_failures']} crawls "
                                      f"(since {s['first_failure'][:10]}): {s['last_error']}.")
            if s["state"] == "down" and days >= REMOVE_AFTER_DAYS and s["consecutive_failures"] >= REMOVE_AFTER:
                s["state"] = "removal-proposed"
                event("removal-proposed", url, s, f"{s['label']} has failed for {days} days; "
                                                  "a pull request proposes removing it from the registry.")
    # Entries that left the registry
    for url in [u for u in fdps if u not in registry]:
        s = fdps.pop(url)
        status.setdefault("removed", []).append({"url": url, "label": s["label"], "issue": s.get("issue"),
                                                 "removal_pr": s.get("removal_pr")})
    del events[:-MAX_EVENTS]


def rebuild_from_history(gh_pages: Path, registry: dict) -> dict:
    """Replay every crawl-report.json committed to gh-pages, oldest first."""
    status = {"fdps": {}, "events": []}
    try:
        commits = subprocess.run(["git", "-C", str(gh_pages), "log", "--reverse", "--format=%H", "--", "crawl-report.json"],
                                 capture_output=True, text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return status
    for c in commits:
        try:
            rep = json.loads(subprocess.run(["git", "-C", str(gh_pages), "show", f"{c}:crawl-report.json"],
                                            capture_output=True, text=True, check=True).stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        apply_report(status, rep, registry)
    status.pop("removed", None)
    print(f"Rebuilt status from {len(commits)} earlier crawl report(s).")
    return status


# ── Atom feeds ────────────────────────────────────────────────────────────────

def atom(title: str, feed_id: str, self_url: str, events: list) -> str:
    updated = events[-1]["time"] if events else datetime.datetime.now(datetime.timezone.utc).isoformat()
    out = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">',
           f"  <title>{escape(title)}</title>", f"  <id>{escape(feed_id)}</id>",
           f'  <link rel="self" href="{escape(self_url)}"/>', f'  <link href="{SITE_URL}"/>',
           f"  <updated>{escape(updated)}</updated>", "  <author><name>FDP Index</name></author>"]
    word = {"down": "Down", "recovered": "Back up", "removal-proposed": "Removal proposed"}
    for e in reversed(events):
        link = e.get("link") or e["url"]
        out += ["  <entry>", f"    <title>{escape(word.get(e['type'], e['type']))}: {escape(e['label'])}</title>",
                f"    <id>{escape(SITE_URL + '#' + e['id'])}</id>", f'    <link href="{escape(link)}"/>',
                f"    <updated>{escape(e['time'])}</updated>", f"    <summary>{escape(e['text'])}</summary>",
                f'    <category term="{escape(e["type"])}"/>', "  </entry>"]
    out.append("</feed>")
    return "\n".join(out) + "\n"


# ── GitHub (issues and pull requests) ─────────────────────────────────────────

class GitHub:
    def __init__(self, repo: str, token: str, live: bool):
        self.repo, self.token, self.live = repo, token, live

    def api(self, method: str, path: str, body=None, quiet=()):
        if not self.live:
            print(f"  [dry run] {method} {path}" + (f" {body.get('title', '')}" if body else ""))
            return {"number": None, "html_url": None} if method == "POST" else []
        req = urllib.request.Request(f"https://api.github.com/repos/{self.repo}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Accept": "application/vnd.github+json",
                                              "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as e:
            if e.code in quiet:
                return None
            print(f"  ✗ GitHub {method} {path}: HTTP {e.code} {e.read()[:300]!r}", file=sys.stderr)
            return None

    def ensure_label(self):
        if self.live:
            self.api("POST", "/labels", {"name": DOWN_LABEL, "color": "d73a4a",
                                         "description": "A registered FDP does not answer"}, quiet=(422,))

    def open_down_issues(self) -> dict:
        """url → issue number, from the marker in each open fdp-down issue."""
        found = {}
        for page in range(1, 6):
            items = self.api("GET", f"/issues?labels={DOWN_LABEL}&state=open&per_page=100&page={page}") or []
            for i in items:
                m = re.search(r"<!-- fdp-status: (\S+) -->", i.get("body") or "")
                if m and "pull_request" not in i:
                    found[m.group(1)] = i["number"]
            if len(items) < 100:
                break
        return found


def watchers_of(entry: dict) -> list:
    w = entry.get("watchers") or []
    return [x.lstrip("@") for x in (w if isinstance(w, list) else [w]) if GITHUB_LOGIN.match(str(x).lstrip("@"))]


def issue_body(url: str, s: dict, entry: dict, repo: str) -> str:
    feed = f"{SITE_URL}fdps/{slug(url)}/status.atom"
    watchers = watchers_of(entry)
    lines = [marker(url), "",
             f"**{s['label']}** has not answered the daily crawl {s['consecutive_failures']} times in a row.", "",
             f"- URL: {url}", f"- Failing since: {s['first_failure'][:16].replace('T', ' ')} UTC",
             f"- Last error: `{s['last_error']}`",
             f"- Last successful crawl: {s['last_ok'][:16].replace('T', ' ') + ' UTC' if s['last_ok'] else 'none on record'}"]
    if entry.get("contact"):
        lines.append(f"- Contact in the registry: {entry['contact']}")
    lines += ["", "This issue closes by itself when the FDP answers again. "
              f"If it keeps failing for {REMOVE_AFTER_DAYS} days, a pull request proposes removing it from "
              "`registry.yaml`; a maintainer decides.", ""]
    if watchers:
        lines += ["Watchers: " + " ".join("@" + w for w in watchers), ""]
    lines += ["**Get notified about this FDP:**",
              "- *Subscribe* to this issue (right-hand side), or",
              f"- add your GitHub account under `watchers:` for this entry in [registry.yaml](https://github.com/{repo}/blob/main/registry.yaml), or",
              f"- follow the Atom feed for this FDP: {feed} (any feed reader; feed-to-email services work too)."]
    return "\n".join(lines)


def remove_entry(text: str, url: str) -> str:
    """Remove one '- url:' block from registry.yaml, keeping every comment around it."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if re.match(r"^\s*-\s+url:\s*[\"']?" + re.escape(url) + r"[\"']?\s*$", l)), None)
    if start is None:
        return text
    end = start + 1
    while end < len(lines) and lines[end].startswith("    ") and not re.match(r"^\s*-\s", lines[end]):
        end += 1
    if start > 0 and lines[start - 1].strip() == "" and end < len(lines) and lines[end].strip() == "":
        end += 1                                  # don't leave two blank lines behind
    return "\n".join(lines[:start] + lines[end:])


def propose_removal(gh: GitHub, url: str, s: dict) -> int | None:
    branch = f"status/remove-{slug(url)}"[:120]
    text = (ROOT / "registry.yaml").read_text()
    new = remove_entry(text, url)
    if new == text:
        print(f"  ⚠ {url} not found in registry.yaml; no removal PR", file=sys.stderr)
        return None
    if not gh.live:
        print(f"  [dry run] branch {branch} removing {url}; PR 'Remove unreachable FDP: {s['label']}'")
        return None
    git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], check=True, capture_output=True, text=True)
    git("fetch", "-q", "origin", "main")
    git("checkout", "-q", "-B", branch, "origin/main")
    (ROOT / "registry.yaml").write_text(remove_entry((ROOT / "registry.yaml").read_text(), url))
    git("add", "registry.yaml")
    git("commit", "-q", "-m", f"Remove unreachable FDP: {s['label']}",
        "-m", f"{url} has failed every crawl since {s['first_failure'][:10]}.")
    git("push", "-q", "--force", "origin", branch)
    git("checkout", "-q", "-")
    body = (f"{marker(url)}\n\n**{s['label']}** ({url}) has not answered since {s['first_failure'][:10]} "
            f"({s['consecutive_failures']} crawls in a row). Last error: `{s['last_error']}`.\n\n"
            "This removes it from `registry.yaml`. Merge only if the FDP is really gone; if it has moved, "
            "change its URL here instead. If it answers again before you merge, this pull request is closed automatically.\n"
            + (f"\nCloses #{s['issue']}\n" if s.get("issue") else ""))
    pr = gh.api("POST", "/pulls", {"title": f"Remove unreachable FDP: {s['label']}", "head": branch,
                                   "base": "main", "body": body})
    if not pr or not pr.get("number"):              # 0 = branch pushed, PR left to a maintainer
        if s.get("issue"):
            gh.api("POST", f"/issues/{s['issue']}/comments", {"body":
                f"The removal is ready on branch `{branch}`, but GitHub Actions may not open pull requests here: "
                f"[open it](https://github.com/{gh.repo}/compare/main...{branch}?expand=1)."})
        return 0
    if s.get("issue"):
        gh.api("POST", f"/issues/{s['issue']}/comments", {"body":
            f"Still failing after {REMOVE_AFTER_DAYS} days. #{pr['number']} proposes removing it from the registry."})
    return pr["number"]


def sync_github(gh: GitHub, status: dict, registry: dict) -> None:
    gh.ensure_label()
    open_issues = gh.open_down_issues()
    for url, s in status["fdps"].items():
        entry = registry.get(url, {})
        s["issue"] = s.get("issue") or open_issues.get(url)
        if s["state"] in ("down", "removal-proposed") and not s["issue"]:
            i = gh.api("POST", "/issues", {"title": f"FDP unreachable: {s['label']}", "labels": [DOWN_LABEL],
                                           "body": issue_body(url, s, entry, gh.repo)})
            s["issue"] = (i or {}).get("number")
        if s["state"] == "removal-proposed" and s.get("removal_pr") is None:
            s["removal_pr"] = propose_removal(gh, url, s)
        if s["state"] in ("up", "failing") and s["issue"] and s["consecutive_failures"] == 0:
            gh.api("POST", f"/issues/{s['issue']}/comments", {"body": f"{s['label']} answers again (crawl of {s['last_ok'][:16].replace('T', ' ')} UTC). Closing."})
            gh.api("PATCH", f"/issues/{s['issue']}", {"state": "closed", "state_reason": "completed"})
            if s.get("removal_pr"):                  # a real PR number (0 means no PR was opened)
                gh.api("POST", f"/issues/{s['removal_pr']}/comments", {"body": "The FDP answers again, so it stays in the registry."})
                gh.api("PATCH", f"/pulls/{s['removal_pr']}", {"state": "closed"})
            s["issue"] = s["removal_pr"] = None
    for r in status.pop("removed", []):
        if r.get("issue"):
            gh.api("POST", f"/issues/{r['issue']}/comments", {"body": f"{r['label']} was removed from the registry. Closing."})
            gh.api("PATCH", f"/issues/{r['issue']}", {"state": "closed", "state_reason": "completed"})


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", default=str(OUTPUT / "crawl-report.json"))
    ap.add_argument("--previous", help="status.json from the last published index")
    ap.add_argument("--history", help="gh-pages checkout, to rebuild the status when there is no previous one")
    ap.add_argument("--github", action="store_true", help="open and close issues and pull requests (needs GITHUB_TOKEN)")
    args = ap.parse_args()

    registry = {e["url"]: e for e in (yaml.safe_load((ROOT / "registry.yaml").read_text()) or {}).get("fdps", []) or []}
    report = json.loads(Path(args.report).read_text())

    prev = Path(args.previous) if args.previous else None
    if prev and prev.exists():
        status = json.loads(prev.read_text())
    elif args.history:
        status = rebuild_from_history(Path(args.history), registry)
    else:
        status = {"fdps": {}, "events": []}
    apply_report(status, report, registry)

    repo = os.environ.get("GITHUB_REPOSITORY", "LeanFDP/fdp-index")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    if args.github and not token:
        sys.exit("--github needs GITHUB_TOKEN")
    sync_github(GitHub(repo, token, live=args.github), status, registry)

    # Link events to their issue once it exists
    for e in status["events"]:
        s = status["fdps"].get(e["url"])
        if s and s.get("issue") and not e.get("link"):
            e["link"] = f"https://github.com/{repo}/issues/{s['issue']}"

    status["updated"] = report["crawled_at"]
    status["rules"] = {"down_after_failed_crawls": DOWN_AFTER, "removal_after_days": REMOVE_AFTER_DAYS,
                       "removal_after_failed_crawls": REMOVE_AFTER}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n")
    (OUTPUT / "status.atom").write_text(atom("FDP Index: outages and recoveries", SITE_URL + "status.atom",
                                             SITE_URL + "status.atom", status["events"]))
    for url, s in status["fdps"].items():
        d = OUTPUT / "fdps" / slug(url)
        d.mkdir(parents=True, exist_ok=True)
        feed = f"{SITE_URL}fdps/{slug(url)}/status.atom"
        (d / "status.atom").write_text(atom(f"FDP Index: {s['label']}", feed, feed,
                                            [e for e in status["events"] if e["url"] == url]))

    for url, s in status["fdps"].items():
        if s["state"] != "up":
            print(f"  {s['state']:<17} {s['consecutive_failures']:>3}× since {s['first_failure'][:10]}  {url}")
    print(f"Status written: {len(status['fdps'])} FDP(s), {len(status['events'])} event(s).")


if __name__ == "__main__":
    main()
