#!/usr/bin/env python3
"""Search the corpus and return anchored, verbatim passages.

    python3 scripts/search.py "termination for convenience" [-n 8] [--doc d3] [--full]
    python3 scripts/search.py --show d1:7            # print one page in full
    python3 scripts/search.py --list                 # list documents

Returns the original source text (not paraphrased or re-wrapped) with a doc/page
anchor, so a quote copied out of a hit will verify byte for byte later. This is the
normal way to read a corpus: search, read the passages, quote from them. With a
large corpus, don't read whole PDFs into context.

BM25 in plain stdlib. The index rebuilds automatically when the corpus changes.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (corpus_root, die, load_doc, load_index, log,  # noqa: E402
                     normalize, resolve_doc_id, save_json, tokenize)

PASSAGE_CHARS = 700
PASSAGE_OVERLAP = 150
K1, B = 1.5, 0.75


def split_passages(text: str) -> list[tuple[int, int]]:
    """Split a page into windows of up to PASSAGE_CHARS that end on sentence
    boundaries. Windows overlap by about PASSAGE_OVERLAP chars so a sentence the
    answer needs isn't cut in half at the edge of a hit."""
    if len(text) <= PASSAGE_CHARS:
        return [(0, len(text))] if text.strip() else []
    bounds = [m.end() for m in re.finditer(r"(?<=[.;:!?])\s+|\n{2,}", text)]
    bounds = [0] + bounds + [len(text)]
    spans, start, i = [], 0, 0
    while i < len(bounds) - 1:
        end = start
        while i < len(bounds) - 1 and bounds[i + 1] - start <= PASSAGE_CHARS:
            i += 1
            end = bounds[i]
        if end <= start:                      # one sentence longer than a window: hard cut
            end = min(start + PASSAGE_CHARS, len(text))
            while i < len(bounds) - 1 and bounds[i] < end:
                i += 1
        spans.append((start, end))
        if end >= len(text):
            break
        start = max(end - PASSAGE_OVERLAP, start + 1)
        while i > 0 and bounds[i] > start:
            i -= 1
        i += 1
    return spans


def build_index(root: Path, index: dict) -> dict:
    passages, postings, lengths = [], defaultdict(list), []
    for meta in index["docs"]:
        doc = load_doc(root, meta["id"])
        for page in doc["page_text"]:
            for s, e in split_passages(page["text"]):
                toks = tokenize(page["text"][s:e])
                if not toks:
                    continue
                pid = len(passages)
                passages.append([meta["id"], page["n"], s, e])
                lengths.append(len(toks))
                for term, tf in Counter(toks).items():
                    postings[term].append([pid, tf])
    bm25 = {"passages": passages, "lengths": lengths, "postings": dict(postings),
            "n": len(passages), "avgdl": (sum(lengths) / len(lengths)) if lengths else 1.0}
    save_json(root / "bm25.json", bm25)
    log(f"indexed {len(passages)} passages across {len(index['docs'])} documents")
    return bm25


_BM25_CACHE: dict[tuple[str, float], dict] = {}


def load_bm25(root: Path, index: dict) -> dict:
    f = root / "bm25.json"
    if f.exists() and f.stat().st_mtime >= (root / "index.json").stat().st_mtime:
        key = (str(f), f.stat().st_mtime)
        if key not in _BM25_CACHE:
            _BM25_CACHE.clear()
            _BM25_CACHE[key] = json.loads(f.read_text())
        return _BM25_CACHE[key]
    bm = build_index(root, index)
    _BM25_CACHE.clear()
    return bm


def search(root: Path, index: dict, query: str, limit: int, doc_filter: str | None) -> list[dict]:
    bm = load_bm25(root, index)
    if not bm["n"]:
        return []
    keep = None
    if doc_filter:
        did = resolve_doc_id(index, doc_filter) or die(f"unknown document: {doc_filter}")
        keep = did
    scores: dict[int, float] = defaultdict(float)
    for term in set(tokenize(query)):
        posts = bm["postings"].get(term)
        if not posts:
            continue
        idf = math.log(1 + (bm["n"] - len(posts) + 0.5) / (len(posts) + 0.5))
        for pid, tf in posts:
            if keep and bm["passages"][pid][0] != keep:
                continue
            dl = bm["lengths"][pid]
            scores[pid] += idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / bm["avgdl"]))
    if not scores:
        return []

    # Exact-phrase bonus. For citation work, a passage containing the query (or a
    # quoted fragment of it) literally matters much more than one that shares
    # scattered terms, so each phrase found adds a flat 6.0.
    phrases = re.findall(r'"([^"]{4,})"', query) or ([query] if len(query.split()) > 1 else [])
    normed = [normalize(p) for p in phrases]

    meta_by_id = {d["id"]: d for d in index["docs"]}
    cache: dict[str, dict] = {}
    hits = []
    for pid, score in sorted(scores.items(), key=lambda kv: -kv[1])[: limit * 4]:
        did, pno, s, e = bm["passages"][pid]
        doc = cache.setdefault(did, load_doc(root, did))
        text = doc["page_text"][pno - 1]["text"][s:e]
        if normed:
            nt = normalize(text)
            score += 6.0 * sum(1 for p in normed if p and p in nt)
        hits.append({
            "doc": did, "title": meta_by_id[did]["title"], "file": meta_by_id[did]["filename"],
            "page": pno, "page_label": meta_by_id[did].get("page_label", "p."),
            "start": s, "end": e, "score": round(score, 3), "text": text.strip(),
        })
    hits.sort(key=lambda h: -h["score"])

    out, seen = [], set()
    for h in hits:                         # at most one hit per page, so results spread out
        key = (h["doc"], h["page"])
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
        if len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?")
    ap.add_argument("-n", "--limit", type=int, default=8)
    ap.add_argument("--doc", help="restrict to one document (id, filename or title)")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--show", metavar="DOC:PAGE", help="print one full page")
    ap.add_argument("--plain", action="store_true", help="with --show: print the text only, no JSON")
    ap.add_argument("--list", action="store_true", help="list ingested documents")
    ap.add_argument("--full", action="store_true", help="widen hits to the whole page")
    args = ap.parse_args()

    root = corpus_root(args.corpus)
    index = load_index(root)

    if args.list:
        print(json.dumps({"corpus": str(root), "docs": index["docs"]}, indent=1))
        return 0

    if args.show:
        ref, _, pno = args.show.partition(":")
        did = resolve_doc_id(index, ref) or die(f"unknown document: {ref}")
        doc = load_doc(root, did)
        if not pno:
            if args.plain:
                for p in doc["page_text"]:
                    print(f"--- {did} p.{p['n']} — {doc['title']}\n{p['text']}")
                return 0
            print(json.dumps({"doc": did, "title": doc["title"], "pages": doc["pages"],
                              "page_text": doc["page_text"]}, indent=1))
            return 0
        n = int(pno)
        if not 1 <= n <= doc["pages"]:
            die(f"{did} has pages 1..{doc['pages']}")
        if args.plain:
            print(doc["page_text"][n - 1]["text"]); return 0
        print(json.dumps({"doc": did, "title": doc["title"], "page": n,
                          "text": doc["page_text"][n - 1]["text"]}, indent=1))
        return 0

    if not args.query:
        die("give a query, --show DOC:PAGE, or --list")

    hits = search(root, index, args.query, args.limit, args.doc)
    if args.full:
        cache = {}
        for h in hits:
            doc = cache.setdefault(h["doc"], load_doc(root, h["doc"]))
            h["text"] = doc["page_text"][h["page"] - 1]["text"]
            h["start"], h["end"] = 0, len(h["text"])
    print(json.dumps({"query": args.query, "hits": hits}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
