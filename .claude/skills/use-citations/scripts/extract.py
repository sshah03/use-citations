#!/usr/bin/env python3
"""Pull the same data point out of every document in a corpus, with a quote per cell.

    python3 scripts/extract.py --fields fields.json                 # worksheet
    python3 scripts/extract.py --fields fields.json --answer grid.json   # table block

This is for diligence grids: say 80 contracts, one row each, one column per data
point, with every filled cell carrying the sentence it came from. Reading 80
documents into context to build that grid is expensive and error-prone. Also, the
most useful finding is often what's missing (the four contracts with no liability
cap), and a grid makes that visible.

**The worksheet is a draft to review.** Each cell pairs a value with the exact
sentence it was read from. Check every cell against its quote before it goes into
a deliverable, fix what the pattern got wrong, and let verify.py check each quote
independently.

Fields file, a list of columns:

    [{"name": "Governing law",
      "query": "governing law state jurisdiction conflict of laws",
      "rules": [{"match": "laws of the State of ([A-Za-z ]+?),", "value": "$1"}],
      "absent": "Not addressed"}]

`query` ranks the pages by BM25. `rules` are tried in order against each page in
that ranking and the first match wins, so rules can tell "60 days" apart from
"expressly excluded" and from silence. A field with no `rules` just returns its
best passages for a person or a model to read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import corpus_root, die, load_doc, load_index, resolve_doc_id  # noqa: E402
from search import load_bm25, search  # noqa: E402

MAX_QUOTE = 340
SENT_END = re.compile(r"(?<=[.;:!?])\s|\n{2,}")


def sentence_around(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen a regex match to the sentence around it, capped at MAX_QUOTE chars so
    a cell quote stays readable."""
    left = 0
    for m in SENT_END.finditer(text, 0, start):
        left = m.end()
    right = len(text)
    m = SENT_END.search(text, end)
    if m:
        right = m.start() + 1
    if right - left > MAX_QUOTE:
        left = max(left, start - MAX_QUOTE // 2)
        right = min(right, end + MAX_QUOTE // 2)
    return left, right


def apply_rules(text: str, rules: list[dict]) -> tuple[str, int, int] | None:
    for rule in rules:
        m = re.search(rule["match"], text, re.I | re.S)
        if not m:
            continue
        value = rule.get("value", "$0")
        for g in range(len(m.groups()), 0, -1):
            value = value.replace(f"${g}", (m.group(g) or "").strip())
        value = value.replace("$0", m.group(0).strip())
        return value, m.start(), m.end()
    return None


def pages_by_relevance(root: Path, index: dict, doc_id: str, query: str, limit: int) -> list[int]:
    hits = search(root, index, query, limit, doc_id)
    order = [h["page"] for h in hits]
    doc = load_doc(root, doc_id)
    for p in doc["page_text"]:                    # then every other page, in document order
        if p["n"] not in order:
            order.append(p["n"])
    return order


def extract(root: Path, index: dict, doc_id: str, field: dict, depth: int) -> dict:
    doc = load_doc(root, doc_id)
    text_by_page = {p["n"]: p["text"] for p in doc["page_text"]}
    order = pages_by_relevance(root, index, doc_id, field["query"], depth)

    if field.get("rules"):
        for pno in order:
            got = apply_rules(text_by_page[pno], field["rules"])
            if got:
                value, ms, me = got
                s, e = sentence_around(text_by_page[pno], ms, me)
                return {"value": value, "page": pno, "quote": text_by_page[pno][s:e].strip(),
                        "matched": True}
        return {"value": field.get("absent", None), "page": None, "quote": None, "matched": False}

    hits = search(root, index, field["query"], 2, doc_id)
    return {"value": None, "page": hits[0]["page"] if hits else None,
            "quote": hits[0]["text"] if hits else None, "matched": False,
            "candidates": [{"page": h["page"], "text": h["text"]} for h in hits]}


def row_label(row: dict, how: str) -> str:
    if how.startswith("field:"):
        cell = row["cells"].get(how.split(":", 1)[1])
        if cell and cell.get("value"):
            return cell["value"]
        return row["file"]
    return row["file"] if how == "file" else row["title"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fields", required=True)
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--docs", nargs="*", help="limit to these documents (default: all)")
    ap.add_argument("--depth", type=int, default=4, help="pages to rank per field before scanning")
    ap.add_argument("--label", default="Document", help="header for the first column")
    ap.add_argument("--row-label", default="title",
                    help="what names each row: title | file | field:<NAME>. Use a field when "
                         "the documents share a title, which a set of contracts usually does.")
    ap.add_argument("--out", default=None, help="write the worksheet JSON here")
    ap.add_argument("--answer", default=None,
                    help="also write an answer.json containing the table block")
    ap.add_argument("--title", default=None, help="table heading for --answer")
    args = ap.parse_args()

    root = corpus_root(args.corpus)
    index = load_index(root)
    fields = json.loads(Path(args.fields).read_text())
    if not isinstance(fields, list) or not fields:
        die("--fields must be a non-empty JSON list of column definitions")

    ids = [d["id"] for d in index["docs"]]
    if args.docs:
        ids = [resolve_doc_id(index, d) or die(f"unknown document: {d}") for d in args.docs]
    load_bm25(root, index)                        # build the index once here so every field reuses it

    meta = {d["id"]: d for d in index["docs"]}
    worksheet = []
    for did in ids:
        row = {"doc": did, "title": meta[did]["title"], "file": meta[did]["filename"], "cells": {}}
        for field in fields:
            row["cells"][field["name"]] = extract(root, index, did, field, args.depth)
        worksheet.append(row)

    coverage = {f["name"]: sum(1 for r in worksheet if r["cells"][f["name"]]["matched"])
                for f in fields}
    summary = {"corpus": str(root), "documents": len(worksheet),
               "fields": [f["name"] for f in fields], "matched": coverage,
               "silent": {k: len(worksheet) - v for k, v in coverage.items()}}

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"summary": summary, "rows": worksheet}, ensure_ascii=False, indent=1))
        summary["worksheet"] = args.out

    if args.answer:
        # a field used as the row label doesn't also get its own column
        label_field = (args.row_label.split(":", 1)[1] if args.row_label.startswith("field:")
                       else None)
        cols = [f for f in fields if f["name"] != label_field]
        table = {"type": "table", "text": args.title or "Extracted terms",
                 "columns": [args.label] + [f["name"] for f in cols], "rows": []}
        for row in worksheet:
            cells = [{"text": row_label(row, args.row_label)}]
            for field in cols:
                c = row["cells"][field["name"]]
                cell = {"text": c["value"] if c["value"] is not None else "—"}
                if c["matched"] and c["quote"]:
                    cell["cites"] = [{"doc": row["doc"], "quote": c["quote"]}]
                cells.append(cell)
            table["rows"].append(cells)
        Path(args.answer).write_text(json.dumps({
            "question": args.title or "Extracted terms across the document set",
            "blocks": [table]}, ensure_ascii=False, indent=1))
        summary["answer"] = args.answer

    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
