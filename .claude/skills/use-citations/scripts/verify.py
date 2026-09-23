#!/usr/bin/env python3
"""Check every citation in an answer against the corpus.

    python3 scripts/verify.py answer.json [--corpus DIR] [-o answer.verified.json]

For each cited quote it finds the span in the ingested source text, records
(doc, page, start, end) and a match grade, and fails the run if any quote can't
be located or any claim has no citation.

Grades: exact | elided ("..." inside the quote) | spanning (crosses a page
break) | fuzzy (>=0.88 similarity, quote drifted) | UNVERIFIED (fail).

Exit 0 = clean, 1 = problems found (details on stdout), 2 = bad input.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (answer_turns, corpus_root, die, flat_blocks,  # noqa: E402
                     load_doc, load_index, normalize, normalize_map, resolve_doc_id, save_json)

FUZZY_FLOOR = 0.88
WEAK_QUOTE_CHARS = 25
LONG_QUOTE_CHARS = 1200
ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)\s*")
# Figures are where a drifted quote does the most harm: a rate, cap, deadline or
# dollar amount that looks plausible but isn't what the document says.
FIGURE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


# Reference numbers (Section 11.1, SOW No. 3, Exhibit 4) are labels. Flagging them
# would bury the actual amounts in noise.
REFERENCE = re.compile(
    r"(?:no\.|nos\.|\u00a7{1,2}|section|sections|clause|article|exhibit|schedule|appendix|annex"
    r"|sow|amendment|addendum|part|rule|form|paragraph|item|page|p\.|pp\.|table|figure"
    # published guidance is named by number: Notice 2026-16 asserts nothing about 2026
    r"|notice|rev\.?\s?rul\.?|rev\.?\s?proc\.?|t\.?d\.?|plr|announcement|publication"
    r"|pub\.?\s?l\.?|reg\.?|regs\.?|cfr|c\.f\.r\.|u\.?s\.?c\.?a?|stat\.?|irb|bulletin|circular|docket"
    # research, clinical, technical and internal records label things by number too
    r"|study|trial|protocol|nct|doi|pmid|pmc|arm|cohort|phase|visit|cycle|grade|stage"
    r"|iso|iec|astm|ansi|rfc|ieee|sop|guideline|standard|spec|version|ver\.?|v\.?"
    r"|revision|rev|chapter|ch\.?|volume|vol\.?|issue|line|row|column|col\.?|fig\.?"
    r"|tbl\.?|appendix|policy|control|req\.?|requirement|question|q\.?"
    r")\s*$", re.I)
# Words that invert or gate a proposition. A fuzzy match that adds or drops one of
# these changes what the quote claims, even though the wording is nearly the same:
# "may not terminate" is 0.97 similar to "may terminate" and means the opposite.
POLARITY = frozenset("""not no never none neither nor without unless except excluding only
    shall must may cannot can will should prohibited permitted required void valid
    minimum maximum before after
    less more greater fewer exceed exceeds exceeding least most above below over under
    all any some each every either
    one two three four five six seven eight nine ten eleven twelve thirteen fourteen
    fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy
    eighty ninety hundred thousand million billion half quarter""".split())
# Words that negate what follows. A quote that begins right after one of them is the
# source's words with the meaning cut off: "less than thirty days" out of "not less
# than thirty days".
NEGATORS = frozenset("not no never neither nor without unless except excluding".split())
ELISION_MAX_GAP = 600   # about a long paragraph; a wider "..." gap is joining two passages, not trimming one
ELISION_WARN_GAP = 250

UNIT = re.compile(
    r"^\s*(?:%|percent|business\s+days?|calendar\s+days?|days?|weeks?|months?|years?"
    r"|dollars?|basis\s+points?|bps)\b", re.I)


def all_figures(text: str) -> set[str]:
    """Every number, for comparing a quote against the passage it matched."""
    return {m.group(0).lstrip("$").rstrip(".").rstrip("%").replace(",", "")
            for m in FIGURE.finditer(text)}


def figure_list(text: str) -> list[str]:
    """Every number in order, so a swap ("30 ... 60" quoted as "60 ... 30") shows."""
    return [m.group(0).lstrip("$").rstrip(".").rstrip("%").replace(",", "")
            for m in FIGURE.finditer(text)]


def salient_figures(text: str) -> set[str]:
    """Only figures that assert something: money, percentages, periods, and any
    number large enough to be an amount or a year."""
    out = set()
    for m in FIGURE.finditer(text):
        raw = m.group(0)
        if REFERENCE.search(text[max(0, m.start() - 24):m.start()]):
            continue
        # part of an identifier, not a quantity: 2000e-5, 1601.14(a), 42-6, 401(k)
        if re.match(r"[A-Za-z]|-\d|\(", text[m.end():m.end() + 2]) and not raw.startswith("$"):
            continue
        norm = raw.lstrip("$").rstrip(".").rstrip("%").replace(",", "")   # "36 percent" == "36%"
        if raw.startswith("$") or raw.endswith("%"):
            out.add(norm)
        elif UNIT.match(text[m.end():m.end() + 20]):
            out.add(norm)
        else:
            try:
                if float(norm) >= 1000:
                    out.add(norm)
            except ValueError:
                pass
    return out

try:
    from rapidfuzz.distance import Levenshtein as _lev  # optional, faster + better
except ImportError:
    _lev = None


def similarity(a: str, b: str) -> float:
    if _lev is not None:
        return _lev.normalized_similarity(a, b)
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


class Page:
    """A page's original text plus its normalized projection and offset map."""

    __slots__ = ("n", "text", "norm", "omap")

    def __init__(self, n: int, text: str):
        self.n = n
        self.text = text
        self.norm, self.omap = normalize_map(text)

    def orig_span(self, ns: int, ne: int) -> tuple[int, int]:
        if not self.omap:
            return 0, 0
        ns = max(0, min(ns, len(self.omap) - 1))
        ne = max(ns + 1, min(ne, len(self.omap)))
        start = self.omap[ns]
        end = self.omap[ne - 1] + 1
        return start, end


def bounded(text: str, i: int, j: int, page: "Page | None" = None) -> bool:
    """A match must begin and end on a word boundary. Otherwise "not" is found inside
    "notice" and "$1" inside "$1,500"."""
    if i > 0 and text[i].isalnum() and text[i - 1].isalnum():
        # HTML extraction glues a heading to the sentence after it ("In generalNo
        # deduction"), so treat lowercase followed by a capital as a word boundary
        glued = False
        if page is not None and page.omap and i < len(page.omap):
            a, b = page.text[page.omap[i - 1]], page.text[page.omap[i]]
            glued = a.islower() and b.isupper()
        if not glued:
            return False
    if j < len(text) and text[j - 1].isalnum() and text[j].isalnum():
        return False
    # a figure cut short: "$1" out of "$1,500" or "2.5" out of "2.50"
    if (j + 1 < len(text) and text[j - 1].isdigit() and text[j] in ",."
            and text[j + 1].isdigit()):
        return False
    return True


def find_bounded(text: str, frag: str, pos: int = 0, page: "Page | None" = None) -> int:
    i = text.find(frag, pos)
    while i >= 0 and not bounded(text, i, i + len(frag), page):
        i = text.find(frag, i + 1)
    return i


def negated_before(text: str, i: int) -> str | None:
    """The negating word immediately before position i, in the same sentence. An FAQ
    that answers "...a takedown? No. You do not need..." has a "No" before the quote,
    but it belongs to the sentence before; only spaces, quote marks or an opening
    bracket may sit between the negator and the quote."""
    m = re.search(r"([a-z]+)[\s\"'(\[]*$", text[max(0, i - 24):i])
    return m.group(1) if m and m.group(1) in NEGATORS else None


def find_exact(page: Page, q: str) -> tuple[int, int, int] | None:
    i = find_bounded(page.norm, q, 0, page)
    if i < 0:
        return None
    count, k = 0, i
    while k >= 0:
        count += 1
        k = find_bounded(page.norm, q, k + 1, page)
    return i, i + len(q), count


def find_elided(page: Page, fragments: list[str]) -> tuple[int, int, int] | None:
    """Quotes with '...' must match each fragment in order on the same page.
    Returns (start, end, widest gap) so the caller can refuse a quote that stitches
    two unrelated passages together with an ellipsis."""
    pos, first, last, gap = 0, None, None, 0
    for frag in fragments:
        i = find_bounded(page.norm, frag, pos, page)
        if i < 0:
            return None
        if first is None:
            first = i
        else:
            gap = max(gap, i - last)
        last = i + len(frag)
        pos = last
    return (first, last, gap) if first is not None else None


def polarity_delta(quote_norm: str, page: Page, ns: int, ne: int) -> set[str]:
    """Polarity words inserted into or deleted from the quote relative to the source.

    This diffs the word sequences. Comparing sets would miss cases like "shall refund
    ... not performed", which already contains "not", being changed to "shall not
    refund". Tokens at either edge of the source window are ignored because the fuzzy
    match aligns loosely there."""
    ws = ns
    while ws > 0 and page.norm[ws - 1].isalpha():
        ws -= 1
    we = ne
    while we < len(page.norm) and page.norm[we].isalpha():
        we += 1
    q = re.findall(r"[a-z]+", quote_norm)
    src = re.findall(r"[a-z]+", page.norm[ws:we])
    edge = {0, 1, len(src) - 1, len(src) - 2}
    flipped: set[str] = set()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, src, q, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        dropped = [w for k, w in enumerate(src[i1:i2], i1) if w in POLARITY and k not in edge]
        added = [w for w in q[j1:j2] if w in POLARITY]
        # count a replace only if it swaps polarity words, not when it just changes
        # ordinary words that sit next to one
        flipped.update(set(dropped) ^ set(added))
    return flipped


def find_fuzzy(page: Page, q: str) -> tuple[int, int, float] | None:
    """Anchor on the longest shared block, then score a same-length window.
    This catches the usual case of a real quote that was lightly reworded."""
    if len(q) < 12 or not page.norm:
        return None
    sm = difflib.SequenceMatcher(None, q, page.norm, autojunk=False)
    block = sm.find_longest_match(0, len(q), 0, len(page.norm))
    if block.size < max(10, int(0.3 * len(q))):
        return None
    start = max(0, block.b - block.a)
    best = (0.0, start, start + len(q))
    for shift in (0, -12, 12, -30, 30):
        s = max(0, min(start + shift, len(page.norm)))
        e = min(len(page.norm), s + len(q))
        score = similarity(q, page.norm[s:e])
        if score > best[0]:
            best = (score, s, e)
    score, s, e = best
    return (s, e, score) if score >= FUZZY_FLOOR else None


def locate(pages: list[Page], quote: str) -> dict:
    """Try, in order: exact -> elided -> across a page break -> fuzzy."""
    q = normalize(quote)
    if not q:
        return {"status": "UNVERIFIED", "reason": "empty quote"}

    for page in pages:
        hit = find_exact(page, q)
        if hit:
            ns, ne, count = hit
            neg = negated_before(page.norm, ns)
            if neg and q.split(" ", 1)[0] not in NEGATORS:
                return {"status": "UNVERIFIED", "page": page.n,
                        "source_text": page.text[max(0, page.orig_span(ns, ne)[0] - 40):
                                                 page.orig_span(ns, ne)[1]],
                        "reason": f"the source reads \u201c{neg}\u201d immediately before this "
                                  f"quote \u2014 starting the quote after it reverses the meaning"}
            s, e = page.orig_span(ns, ne)
            return {"status": "exact", "page": page.n, "start": s, "end": e,
                    "score": 1.0, "ambiguous": count > 1}

    frags = [normalize(f) for f in ELLIPSIS.split(quote) if normalize(f)]
    if len(frags) > 1:
        for page in pages:
            hit = find_elided(page, frags)
            if hit:
                ns, ne, gap = hit
                pos = ns
                for frag in frags:
                    at = find_bounded(page.norm, frag, pos, page)
                    neg = negated_before(page.norm, at)
                    if neg and frag.split(" ", 1)[0] not in NEGATORS:
                        return {"status": "UNVERIFIED", "page": page.n,
                                "reason": f"the source reads \u201c{neg}\u201d immediately before "
                                          f"the fragment \u201c{frag[:40]}\u201d \u2014 the ellipsis "
                                          f"drops a negation"}
                    pos = at + len(frag)
                if gap > ELISION_MAX_GAP:
                    return {"status": "UNVERIFIED", "page": page.n,
                            "reason": f"the ellipsis skips {gap} characters \u2014 these fragments "
                                      f"are two passages, not one quotation"}
                s, e = page.orig_span(ns, ne)
                return {"status": "elided", "page": page.n, "start": s, "end": e,
                        "score": 1.0, "gap": gap}

    for a, b in zip(pages, pages[1:]):          # sentence split by a page break
        joined = Page(a.n, a.text + "\n" + b.text)
        hit = find_exact(joined, q)
        if hit:
            ns, ne, _ = hit
            s, e = joined.orig_span(ns, ne)
            if s < len(a.text) < e:
                return {"status": "spanning", "page": a.n, "start": s,
                        "end": min(e, len(a.text)), "score": 1.0,
                        "also_pages": [b.n], "continues": True}

    best = None
    for page in pages:
        hit = find_fuzzy(page, q)
        if hit and (best is None or hit[2] > best[1]["score"]):
            s, e = page.orig_span(hit[0], hit[1])
            best = (page, {"status": "fuzzy", "page": page.n, "start": s, "end": e,
                           "score": round(hit[2], 3)}, hit[0], hit[1])
    if best:
        page, res = best[0], best[1]
        res["source_text"] = page.text[res["start"]:res["end"]]
        # read the source's figures whole: a window that ends inside "$1,500" holds "$1"
        ws, we = res["start"], res["end"]
        while ws > 0 and re.match(r"[\w$.,]", page.text[ws - 1]):
            ws -= 1
        while we < len(page.text) and re.match(r"[\w.,%]", page.text[we]):
            we += 1
        whole = page.text[ws:we]
        invented = all_figures(quote) - all_figures(whole)
        qf = [f for f in figure_list(quote) if f in all_figures(whole)]
        sf = [f for f in figure_list(whole) if f in set(qf)]
        if not invented and qf != sf[:len(qf)] and sorted(qf) == sorted(sf[:len(qf)]):
            return {"status": "UNVERIFIED", "page": res["page"],
                    "source_text": res["source_text"],
                    "reason": f"quote gives the figures in a different order from the source "
                              f"({', '.join(qf)} against {', '.join(sf[:len(qf)])}) \u2014 "
                              f"they have been swapped"}
        if invented:
            return {"status": "UNVERIFIED", "page": res["page"],
                    "source_text": res["source_text"],
                    "reason": f"quote states {', '.join(sorted(invented))}, which does not "
                              f"appear in the matched source passage"}
        flipped = polarity_delta(q, page, best[2], best[3])
        if flipped:
            return {"status": "UNVERIFIED", "page": res["page"],
                    "source_text": res["source_text"],
                    "reason": f"quote and source differ on {', '.join(sorted(flipped))} \u2014 "
                              f"the meaning is changed, not the wording"}
        return res

    return {"status": "UNVERIFIED", "reason": "quote not found in this document"}


def iter_cites(blocks: list[dict]):
    """Walk claims and table cells uniformly; yield (locator, claim_text, cite)."""
    for bi, block in enumerate(blocks):
        btype = block.get("type", "claim")
        if btype == "table":
            for ri, row in enumerate(block.get("rows", [])):
                for ci, cell in enumerate(row):
                    if isinstance(cell, str):
                        continue
                    for cite in cell.get("cites", []):
                        yield f"block{bi}.r{ri}c{ci}", cell.get("text", ""), cite
        else:
            for cite in block.get("cites", []):
                yield f"block{bi}", block.get("text", ""), cite


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answer")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("-o", "--out", default=None,
                    help="write the resolved answer (default: <answer>.verified.json)")
    ap.add_argument("--lenient", action="store_true",
                    help="report problems but exit 0 (never use for a deliverable)")
    args = ap.parse_args()

    src = Path(args.answer)
    if not src.exists():
        die(f"no such answer file: {src}")
    try:
        answer = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        die(f"{src} is not valid JSON: {exc}")

    root = corpus_root(args.corpus)
    index = load_index(root)
    # a report with follow-ups keeps each question in `turns`; locators index the
    # blocks of every question read in order, the same way the report numbers them
    turns = answer_turns(answer)
    blocks = flat_blocks(answer)
    if not blocks:
        die("answer has no 'blocks' — see references/answer-schema.md")
    multi = len(turns) > 1
    sum_at = lambda ti: f"turn{ti}.summary" if multi else "summary"   # noqa: E731

    page_cache: dict[str, list[Page]] = {}
    meta_by_id = {d["id"]: d for d in index["docs"]}
    problems: list[dict] = []
    warnings: list[dict] = []
    ledger: list[dict] = []
    used_docs: set[str] = set()

    # Names given in meta.short_names are how the answer tends to refer to documents,
    # so they resolve as references too, unless two documents share the same name.
    short = (answer.get("meta") or {}).get("short_names") or {}
    alias: dict[str, str | None] = {}
    for did_, name in short.items():
        key = str(name).strip().lower()
        alias[key] = None if key in alias else did_
    known = {d["id"] for d in index["docs"]}

    for loc, claim_text, cite in iter_cites(blocks):
        quote = (cite.get("quote") or "").strip()
        ref = str(cite.get("doc", "")).strip()
        did = alias.get(ref.lower()) if ref.lower() in alias else None
        if did is not None and did not in known:
            did = None
        if did is None and ref:
            did = resolve_doc_id(index, ref)

        if not did:
            cite["status"] = "UNVERIFIED"
            cite["reason"] = f"no document matches {ref!r}"
            problems.append({"at": loc, "claim": claim_text[:110], "quote": quote[:110],
                             "problem": cite["reason"]})
            continue
        if not quote:
            cite["status"] = "UNVERIFIED"
            cite["reason"] = "citation has no quote"
            problems.append({"at": loc, "claim": claim_text[:110], "problem": cite["reason"]})
            continue

        if did not in page_cache:
            doc = load_doc(root, did)
            page_cache[did] = [Page(p["n"], p["text"]) for p in doc["page_text"]]
        pages = page_cache[did]

        claimed_page = cite.get("page")
        result = locate(pages, quote)
        cite["doc"] = did
        cite["doc_title"] = meta_by_id[did]["title"]
        cite.update(result)
        used_docs.add(did)

        if result["status"] == "UNVERIFIED":
            problems.append({"at": loc, "doc": did, "claim": claim_text[:110],
                             "quote": quote[:160], "problem": result.get("reason", "not found")})
            continue

        if claimed_page and claimed_page != result["page"]:
            cite["page_corrected_from"] = claimed_page
            warnings.append({"at": loc, "doc": did,
                             "problem": f"cited page {claimed_page}, quote is on page {result['page']}"})
        if result["status"] == "fuzzy":
            warnings.append({"at": loc, "doc": did, "quote": quote[:110],
                             "problem": f"quote is not verbatim (similarity {result['score']}) — "
                                        f"replace it with the source text",
                             "source_text": result.get("source_text", "")[:200]})
        if result.get("gap", 0) > ELISION_WARN_GAP:
            warnings.append({"at": loc, "doc": did,
                             "problem": f"the ellipsis skips {result['gap']} characters \u2014 check "
                                        f"that the joined fragments still say what the source says"})
        if result.get("ambiguous"):
            warnings.append({"at": loc, "doc": did,
                             "problem": "quote occurs more than once in this document; "
                                        "anchored to the first occurrence"})
        if meta_by_id[did].get("thin"):
            warnings.append({"at": loc, "doc": did,
                             "problem": "this document was flagged at ingest as a low-yield "
                                        "capture (almost no text extracted) \u2014 confirm the "
                                        "quote is the document's content and not site navigation"})
        if len(normalize(quote)) < WEAK_QUOTE_CHARS:
            warnings.append({"at": loc, "doc": did, "quote": quote,
                             "problem": "quote is too short to be real evidence — quote the "
                                        "full operative sentence"})
        anchor = cite.get("anchor")
        if anchor and claim_text and anchor not in claim_text:
            warnings.append({"at": loc, "doc": did,
                             "problem": f"anchor {anchor[:60]!r} is not a substring of the claim, "
                                        f"so the marker falls at the end of the sentence instead of "
                                        f"after the phrase it supports"})
        if len(quote) > LONG_QUOTE_CHARS:
            warnings.append({"at": loc, "doc": did,
                             "problem": f"quote is {len(quote)} chars — cite the operative "
                                        f"passage, not the whole section"})
        ledger.append({"at": loc, "doc": did, "title": meta_by_id[did]["title"],
                       "page": result["page"], "status": result["status"],
                       "score": result.get("score"), "quote": quote})

    # a figure stated in the prose should come from some quote. Check against every
    # quote in the answer, since prose often repeats a figure cited a paragraph earlier.
    quoted_figures: set[str] = set()
    for _, _, c in iter_cites(blocks):
        quoted_figures |= all_figures(c.get("quote", ""))
    # The summary is what most readers act on, and it has no citations of its own. Flag
    # any figure in it that no quote contains.
    for ti, turn in enumerate(turns):
        summary = turn.get("summary") or ""
        for fig in sorted(salient_figures(summary) - quoted_figures):
            warnings.append({"at": sum_at(ti), "claim": summary[:110],
                             "problem": f"the summary states the figure {fig}, which appears in no cited "
                                        "quote — the summary is not verified; keep it to what the claims establish"})
    for bi, block in enumerate(blocks):
        if not block.get("cites") or block.get("type") in {"heading", "note"}:
            continue
        for fig in sorted(salient_figures(block.get("text", "")) - quoted_figures):
            warnings.append({"at": f"block{bi}", "claim": block.get("text", "")[:110],
                             "problem": f"the figure {fig} appears in no cited quote — confirm "
                                        f"it is derived from the sources, not invented"})

    # every substantive claim must carry at least one citation
    for bi, block in enumerate(blocks):
        btype = block.get("type", "claim")
        if btype in {"heading", "note", "table"}:
            continue
        if not block.get("cites"):
            problems.append({"at": f"block{bi}", "claim": block.get("text", "")[:140],
                             "problem": "claim has no citation — cite it, delete it, or mark "
                                        "it type 'note' if it is framing, not a finding"})

    # Search record. The verifier can't tell whether sources were found by searching
    # for an answer already in mind. Recording the searches lets a reader judge that,
    # and asking for at least one search meant to contradict the answer pushes back on it.
    # Each question is checked separately: a disconfirming search for the first question
    # doesn't cover a follow-up that only ran confirming searches.
    searches = []
    for ti, turn in enumerate(turns):
        own = turn.get("searches") or []
        searches += [{**x, "turn": ti} for x in own] if multi else own
        where = f"turn{ti}" if multi else "meta"
        field = f"turns[{ti}].searches" if multi else "meta.searches"
        if not own:
            warnings.append({"at": where,
                             "problem": f"no search record in {field} \u2014 a reader cannot tell "
                                        "whether these sources were found by looking for the answer "
                                        "you already expected"})
        elif not any(str(x.get("for", "")).lower().startswith("contra") for x in own):
            warnings.append({"at": where,
                             "problem": f"{len(own)} searches recorded, none marked "
                                        f"'contradict' \u2014 confirming searches test nothing"})

    verified = {
        **answer,
        "verification": {
            "corpus": str(root),
            "documents_in_corpus": len(index["docs"]),
            "documents_cited": len(used_docs),
            "searches": searches,
            "citations": len(ledger) + sum(1 for p in problems if "quote" in p),
            "verified": len(ledger),
            "failed": len([p for p in problems if "quote" in p]),
            "warnings": len(warnings),
            "clean": not problems,
            "grades": {g: sum(1 for x in ledger if x["status"] == g)
                       for g in {x["status"] for x in ledger}},
            "ledger": ledger,
            "problems": problems,
            "warning_details": warnings,
        },
    }
    out = Path(args.out) if args.out else src.with_suffix(".verified.json")
    save_json(out, verified)

    report = {k: v for k, v in verified["verification"].items() if k != "ledger"}
    report["out"] = str(out)
    print(json.dumps(report, indent=1, ensure_ascii=False))

    if problems and not args.lenient:
        print("\nFAILED: fix every problem above, then re-run verify. Do not render or "
              "deliver an answer with unverified citations.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
