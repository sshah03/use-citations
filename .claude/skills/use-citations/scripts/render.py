#!/usr/bin/env python3
"""Build the reviewable citation report from a verified answer.

    python3 scripts/render.py answer.verified.json [-o report] [--corpus DIR]

Writes <out>/index.html, a self-contained page with the answer (each sourced
phrase cited inline), a source drawer that opens to the page with the quoted
passage highlighted, a browsable copy of every source, and an audit table of
every quote and its match grade.

Publish it with the Artifact tool:
    Artifact(file_path="<out>/index.html", files={...}, icon="document")
The command prints the exact `files` map when page images are bundled.

Refuses to render unverified citations unless given --allow-unverified, which
renders the page with the failures marked in red.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import answer_turns, corpus_root, die, flat_blocks, load_doc, load_index  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "report.html"
EMBED_BUDGET = 1_200_000     # chars of source text bundled into the page
IMAGE_BUDGET = 40            # page images copied alongside it


def short_name(title: str, limit: int = 30) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(" ", 1)[0]
    return (cut or title[:limit]) + "…"


def display_paths(paths: list[str]) -> dict[str, str]:
    """Paths as a reader of the published page should see them.

    The index stores absolute paths, which include the user's home directory, account
    name and often the client. A published report shows each file relative to the
    folder that holds the whole document set, e.g. `orion-contracts/MSA.pdf`.
    """
    if not paths:
        return {}
    try:
        base = Path(os.path.commonpath([str(Path(p).parent) for p in paths])).parent
    except ValueError:                                 # different drives
        return {p: Path(p).name for p in paths}
    return {p: os.path.relpath(p, base) for p in paths}


def collect_cites(blocks: list[dict]) -> list[dict]:
    out = []
    for block in blocks:
        if block.get("type") == "table":
            for row in block.get("rows", []):
                for cell in row:
                    if isinstance(cell, dict):
                        out += cell.get("cites", [])
        else:
            out += block.get("cites", [])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answer")
    ap.add_argument("-o", "--out", default="report")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--title", default=None, help="page <title> (default: derived from the question)")
    ap.add_argument("--allow-unverified", action="store_true")
    ap.add_argument("--full-corpus", action="store_true",
                    help="bundle every document, not just the cited ones")
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--full-paths", action="store_true",
                    help="show absolute local file paths (default: relative to the document set)")
    args = ap.parse_args()

    src = Path(args.answer)
    if not src.exists():
        die(f"no such file: {src}")
    answer = json.loads(src.read_text())
    if "verification" not in answer:
        die("this answer has not been verified — run scripts/verify.py first")

    v = answer["verification"]
    # `failed` counts bad quotes; `clean` also covers a claim with no citation at all,
    # which `verify.py --lenient` lets through and which shouldn't look verified
    if (v.get("failed") or v.get("clean") is False) and not args.allow_unverified:
        n = len(v.get("problems") or []) or v.get("failed")
        die(f"{n} verification problem(s) — a failed quote or an uncited claim. Fix them, or "
            f"re-run with --allow-unverified to publish the failures visibly flagged.", 1)
    # refuse an answer whose quotes were edited after verification
    ledger = {(e.get("at"), e.get("quote")) for e in v.get("ledger", [])}
    from verify import iter_cites  # noqa: E402
    stale = [at for at, _, c in iter_cites(flat_blocks(answer))
             if c.get("status") != "UNVERIFIED" and (at, c.get("quote")) not in ledger]
    if stale and not args.allow_unverified:
        die(f"{len(stale)} quote(s) changed since verification ({', '.join(stale[:3])}) — "
            f"re-run verify.py on the edited answer", 1)

    root = corpus_root(args.corpus)
    index = load_index(root)
    blocks = flat_blocks(answer)
    cites = collect_cites(blocks)

    cited_ids = [c["doc"] for c in cites if c.get("doc")]
    cited_pages: dict[str, set[int]] = {}
    for c in cites:
        if c.get("doc") and c.get("page"):
            cited_pages.setdefault(c["doc"], set()).add(c["page"])

    # Cited documents first, in full. Uncited documents follow so the Sources tab lists
    # the whole corpus, including what was captured but not used. Their text is bundled
    # only while the budget lasts (--full-corpus bundles all of it).
    order = [d["id"] for d in index["docs"] if d["id"] in set(cited_ids)]
    uncited = [d["id"] for d in index["docs"] if d["id"] not in set(order)]
    order += uncited

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / "pages"
    if img_dir.exists():
        shutil.rmtree(img_dir)

    overrides = (answer.get("meta") or {}).get("short_names", {})
    meta_by_id = {d["id"]: d for d in index["docs"]}
    shown = ({d["path"]: d["path"] for d in index["docs"]} if args.full_paths
             else display_paths([d["path"] for d in index["docs"]]))
    budget = EMBED_BUDGET
    images_left = 0 if args.no_images else IMAGE_BUDGET
    published_files: dict[str, str] = {}
    payload_docs: dict[str, dict] = {}

    for did in order:
        meta = meta_by_id[did]
        doc = load_doc(root, did)
        want = cited_pages.get(did, set())

        if meta["chars"] <= budget or (args.full_corpus and did in uncited):
            pages = doc["page_text"]
            partial = False
        elif did in uncited:                # listed, not bundled
            pages = []
            partial = True
        else:                               # keep the cited pages and their neighbours
            keep = {n for p in want for n in (p - 1, p, p + 1)}
            pages = [p for p in doc["page_text"] if p["n"] in keep]
            partial = len(pages) < meta["pages"]
        budget -= sum(len(p["text"]) for p in pages)

        images: dict[str, str] = {}
        src_img_dir = root / "pages" / did
        if meta.get("images") and src_img_dir.exists() and images_left > 0:
            # for a scan the page image is the source itself, so it is copied whatever
            # the text budget; only IMAGE_BUDGET limits it
            for n in sorted(want, key=lambda n: (not meta.get("ocr"), n)):
                png = src_img_dir / f"p{n}.png"
                if not png.exists() or images_left <= 0:
                    continue
                rel = f"pages/{did}/p{n}.png"
                dest = out_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(png, dest)
                images[str(n)] = rel
                published_files[rel] = str(dest)
                images_left -= 1

        payload_docs[did] = {
            "id": did,
            "title": meta["title"],
            "short": overrides.get(did) or short_name(meta["title"]),
            "filename": meta["filename"],
            "path": shown.get(meta["path"], meta["filename"]),
            "type": meta["type"],
            "pages": meta["pages"],
            "page_label": meta.get("page_label", "p."),
            "partial": partial,
            "ocr": meta.get("ocr"),
            "thin": meta.get("thin"),
            "source": meta.get("source"),
            "images": images,
            "page_text": pages,
        }

    # a follow-up finds the report by its short name. It is recorded with the answer
    # file and corpus, and printed on the page for the reader to copy
    from report import register  # noqa: E402
    report_id = register(src, out_dir, answer, str(root))

    turns = answer_turns(answer)
    payload = {
        "question": turns[0].get("question") or "Findings",
        "meta": answer.get("meta", {}),
        "generated": answer.get("generated") or date.today().isoformat(),
        "report_id": report_id,
        # every question in order; a single-question answer is a list of one
        "turns": [{"question": t.get("question"), "title": t.get("title"), "summary": t.get("summary"),
                   "asked": t.get("asked"), "updates": t.get("updates"), "gaps": t.get("gaps") or [],
                   "searches": t.get("searches") or [], "n_blocks": len(t.get("blocks") or [])}
                  for t in turns],
        "blocks": blocks,
        "verification": v,
        "docs": payload_docs,
    }

    first = turns[0]
    title = (args.title or (answer.get("meta") or {}).get("title") or first.get("title")
             or short_name(first.get("question") or "Source Review", 60))
    data = json.dumps(payload, ensure_ascii=False)
    if not args.full_paths:
        # catch anything else that still contains the home directory (the corpus path in
        # the verification record, a ledger entry) and publish it as ~
        home = str(Path.home())
        data = data.replace(json.dumps(home)[1:-1], "~")
    data = data.replace("<", "\\u003c")
    html = (TEMPLATE.read_text()
            .replace("__TITLE__", title.replace("<", "").replace("&", "&amp;"))
            .replace("__CITATION_DATA__", data))
    page = out_dir / "index.html"
    page.write_text(html)

    print(json.dumps({
        "page": str(page),
        "bytes": len(html),
        "documents_listed": len(payload_docs),
        "documents_bundled": sum(1 for d in payload_docs.values() if d["page_text"]),
        "pages_bundled": sum(len(d["page_text"]) for d in payload_docs.values()),
        "page_images": len(published_files),
        "citations": len(cites),
        "unverified": v.get("failed", 0),
        "report": report_id,
        "questions": len(turns),
        "follow_up": f"/use-citations follow-up {report_id} <question>",
        "after_publishing": f"python3 {Path(__file__).resolve().parent}/report.py record {out_dir} --url <artifact link>",
        "publish": {
            "file_path": str(page),
            "files": published_files or None,
            "icon": "document",
        },
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
