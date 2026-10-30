#!/usr/bin/env python3
"""
Turn a "Register a FAIR Data Point" issue into a new entry in registry.yaml.

    python3 scripts/register_from_issue.py --issue-body body.md --summary pr.md --title-file title.txt

The issue body (GitHub issue-form markdown, "### Label" sections) is untrusted input:
it is only read from a file, every value is checked, and the entry is written as
quoted YAML. The new entry is inserted at the end of the live section, before the
"Pending deployment" comment block, so the comments in registry.yaml survive.

Checks: the URL is http(s) and not registered yet, the ORCID iD has a valid checksum,
the ROR id looks like one, and the URL returns RDF (with the crawler's own fetch_rdf).
A URL that does not answer is still added, flagged in the pull request, because the
daily crawl records reachability anyway.

Ported from LeanFDP/staticfdp-index (issue template and register.html, April 2026).
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry.yaml"
NO_RESPONSE = {"", "_no response_", "none", "n/a", "-"}
LABELS = {"fdp root url": "url", "name": "label", "description": "description", "publisher": "publisher",
          "publisher ror": "publisher_ror", "contact": "contact", "your orcid id": "orcid",
          "notes for the crawler": "notes"}
PENDING_MARKER = "# ── Pending deployment"


class RegistrationError(Exception):
    pass


def fields_from_issue(body: str) -> dict:
    fields = {}
    for m in re.finditer(r"^###\s+(.+?)\s*$\n(.*?)(?=^###\s|\Z)", body, re.S | re.M):
        key = LABELS.get(m.group(1).strip().lower())
        if key:
            value = m.group(2).strip()
            fields[key] = "" if value.lower() in NO_RESPONSE else value
    return fields


def orcid_ok(orcid: str) -> bool:
    """ISO 7064 MOD 11-2 checksum of an ORCID iD."""
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid):
        return False
    digits = orcid.replace("-", "")
    total = 0
    for d in digits[:-1]:
        total = (total + int(d)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ("X" if check == 10 else str(check))


def entry_from_fields(f: dict, registered: set) -> dict:
    url = (f.get("url") or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc or any(c in url for c in " \n\"'<>"):
        raise RegistrationError(f"The FDP root URL must be an http(s) URL, got {url!r}.")
    if url in registered or url.rstrip("/") in {u.rstrip("/") for u in registered}:
        raise RegistrationError(f"{url} is already in registry.yaml.")
    label = " ".join((f.get("label") or "").split())
    if not label:
        raise RegistrationError("The name is required.")
    entry = {"url": url, "label": label[:200], "added": datetime.date.today().isoformat(),
             "contact": " ".join((f.get("contact") or "").split())[:200]}
    if f.get("publisher"):
        entry["publisher"] = " ".join(f["publisher"].split())[:200]
    ror = (f.get("publisher_ror") or "").strip()
    if ror:
        ror = ror if ror.startswith("https://ror.org/") else "https://ror.org/" + ror.split("/")[-1]
        if not re.fullmatch(r"https://ror\.org/0[a-z0-9]{6}\d{2}", ror):
            raise RegistrationError(f"{ror} does not look like a ROR identifier (https://ror.org/0xxxxxxNN).")
        entry["publisher_ror"] = ror
    orcid = (f.get("orcid") or "").strip().removeprefix("https://orcid.org/")
    if orcid:
        if not orcid_ok(orcid):
            raise RegistrationError(f"{orcid} is not a valid ORCID iD (the checksum does not match).")
        entry["registered_by"] = f"https://orcid.org/{orcid}"
    if f.get("description"):
        entry["description"] = " ".join(f["description"].split())[:1000]
    if f.get("notes"):
        entry["notes"] = f["notes"].strip()[:2000]
    return entry


def entry_yaml(entry: dict) -> str:
    """One registry item, indented like the hand-written ones."""
    lines = []
    for i, (k, v) in enumerate(entry.items()):
        prefix = "  - " if i == 0 else "    "
        if k == "notes":
            body = "\n".join("      " + l for l in v.splitlines())
            lines.append(f"{prefix}{k}:   >\n{body}")
        else:
            lines.append(f"{prefix}{(k + ':').ljust(8)} {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def insert(registry_text: str, block: str) -> str:
    i = registry_text.find(PENDING_MARKER)
    if i < 0:
        return registry_text.rstrip("\n") + "\n\n" + block
    j = registry_text.rfind("\n", 0, i)          # start of the marker's line
    head = registry_text[:j].rstrip("\n")
    return head + "\n\n" + block + "\n" + registry_text[j + 1:]


def check_url(url: str) -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from crawl import fetch_rdf  # noqa: E402 - reuse the crawler's content negotiation
    except Exception as e:  # noqa: BLE001
        return f"⚠️ Could not run the RDF check ({e})."
    g = fetch_rdf(url)
    if g is None:
        return "⚠️ The URL did not return parseable RDF just now. It is added anyway; the daily crawl will report it as failing until it answers."
    return f"✅ The URL returns RDF ({len(g)} triples)."


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--issue-body", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--title-file", required=True)
    ap.add_argument("--no-fetch", action="store_true", help="skip the RDF check (offline tests)")
    args = ap.parse_args()

    text = REGISTRY.read_text()
    registered = {e["url"] for e in (yaml.safe_load(text) or {}).get("fdps", []) or []}
    try:
        entry = entry_from_fields(fields_from_issue(Path(args.issue_body).read_text()), registered)
    except RegistrationError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    block = entry_yaml(entry)
    new_text = insert(text, block)
    parsed = yaml.safe_load(new_text)                # the result must still be valid YAML with the new entry
    assert any(e["url"] == entry["url"] for e in parsed["fdps"]), "entry not found after insert"
    REGISTRY.write_text(new_text)

    check = "RDF check skipped." if args.no_fetch else check_url(entry["url"])
    Path(args.title_file).write_text(f"Register FDP: {entry['label']}\n")
    Path(args.summary).write_text(
        f"Adds **{entry['label']}** to `registry.yaml`.\n\n"
        f"- URL: {entry['url']}\n"
        + (f"- Publisher: {entry.get('publisher', '')} {entry.get('publisher_ror', '')}\n" if entry.get("publisher") or entry.get("publisher_ror") else "")
        + (f"- Registered by: {entry['registered_by']}\n" if entry.get("registered_by") else "")
        + f"\n{check}\n\n```yaml\n{block}```\n\nAfter the merge, the next crawl (daily at 03:00 UTC, or *Run workflow*) includes it.\n")
    print(f"added {entry['url']}")


if __name__ == "__main__":
    main()
