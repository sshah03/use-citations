#!/usr/bin/env python3
"""Find a published report again, so a follow-up question lands in it.

    python3 scripts/report.py list                       recent reports, newest first
    python3 scripts/report.py find <name-or-link>        one report: its answer file, corpus, link
    python3 scripts/report.py find --latest              the most recently updated report
    python3 scripts/report.py record <report-dir> --url <artifact link>

`render.py` gives every report a short name the first time it is built (the answer's
`meta.report_id`, or one made from its title) and records it here, beside the answer
file it came from and the corpus it was checked against. After publishing, `record`
adds the link. `/use-citations follow-up <name> <question>` uses `find` to get back to it.

Registrations live in ~/.claude/citations/reports.json (CITATIONS_REPORTS overrides
it). Like the corpus registry, it only records where things are.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import REGISTRY, die, locked_json_update  # noqa: E402

REPORTS = Path(os.environ.get("CITATIONS_REPORTS") or (REGISTRY.parent / "reports.json"))
STOP = set("a an the of for to in on and or is are do does how what which who when can "
           "our we you your my i it its with from by at this that be".split())


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict:
    try:
        return json.loads(REPORTS.read_text()).get("reports", {})
    except (OSError, json.JSONDecodeError):
        return {}


def slug(text: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]
    return "-".join(words[:4]) or "report"


def register(answer_path: Path, out_dir: Path, answer: dict, corpus_path: str) -> str:
    """Give the report a short name and record where it lives. The same answer file
    always keeps the name it was first given, and a new report never reuses a name
    that is taken."""
    answer_path, out_dir = answer_path.resolve(), out_dir.resolve()
    source = answer_path.with_name(answer_path.name.replace(".verified.json", ".json"))
    meta = answer.get("meta") or {}
    turns = answer.get("turns") or [answer]
    title = meta.get("title") or turns[0].get("title") or turns[0].get("question") or "Report"
    name: list[str] = []

    def update(cur: dict) -> None:
        reports = cur["reports"]
        mine = next((k for k, v in reports.items() if v.get("answer") == str(source)), None)
        rid = mine or meta.get("report_id") or slug(title)
        if not mine:
            base, n = rid, 2
            while rid in reports:
                rid, n = f"{base}-{n}", n + 1
        entry = reports.get(rid, {"created": now()})
        entry.update({"title": title, "answer": str(source), "verified": str(answer_path),
                      "dir": str(out_dir), "corpus_path": corpus_path,
                      "questions": len(turns), "updated": now()})
        reports[rid] = entry
        name.append(rid)

    locked_json_update(REPORTS, "reports", update)
    return name[0]


def match(reports: dict, ref: str) -> list[str]:
    ref = ref.strip().rstrip("/")
    if ref in reports:
        return [ref]
    by_url = [k for k, v in reports.items() if v.get("url") and v["url"].rstrip("/") == ref]
    if by_url:
        return by_url
    tail = ref.rsplit("/", 1)[-1]                        # an artifact link with a different prefix
    by_tail = [k for k, v in reports.items() if v.get("url") and v["url"].rstrip("/").endswith("/" + tail)]
    if by_tail and len(tail) > 8:
        return by_tail
    return [k for k in reports if k.startswith(ref)]


def row(rid: str, v: dict) -> dict:
    return {"name": rid, "title": v.get("title"), "questions": v.get("questions"),
            "url": v.get("url"), "updated": v.get("updated"), "answer": v.get("answer"),
            "dir": v.get("dir"), "corpus_path": v.get("corpus_path"),
            "answer_exists": Path(v.get("answer", "")).exists(),
            "corpus_exists": Path(v.get("corpus_path", "")).exists()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("find")
    f.add_argument("ref", nargs="?")
    f.add_argument("--latest", action="store_true")
    r = sub.add_parser("record")
    r.add_argument("dir", help="the report's output directory (or its answer file)")
    r.add_argument("--url", required=True)
    args = ap.parse_args()

    reports = load()
    newest = sorted(reports, key=lambda k: reports[k].get("updated", ""), reverse=True)

    if args.cmd == "list":
        print(json.dumps({"registry": str(REPORTS), "reports": [row(k, reports[k]) for k in newest[:25]]}, indent=1))
        return 0

    if args.cmd == "find":
        if args.latest or not args.ref:
            if not newest:
                die("no reports recorded yet")
            print(json.dumps(row(newest[0], reports[newest[0]]), indent=1))
            return 0
        hits = match(reports, args.ref)
        if len(hits) == 1:
            print(json.dumps(row(hits[0], reports[hits[0]]), indent=1))
            return 0
        print(json.dumps({"error": "no report matches" if not hits else "more than one report matches",
                          "ref": args.ref,
                          "candidates": [row(k, reports[k]) for k in (hits or newest[:10])]}, indent=1))
        return 1

    target = Path(args.dir).resolve()
    key = [k for k, v in reports.items() if target in (Path(v.get("dir", "")), Path(v.get("verified", "")),
                                                        Path(v.get("answer", "")))]
    if not key:
        die(f"no report recorded for {target} — render it first")

    def update(cur: dict) -> None:
        cur["reports"][key[0]].update({"url": args.url, "updated": now()})

    locked_json_update(REPORTS, "reports", update)
    print(json.dumps({"recorded": key[0], "url": args.url}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
