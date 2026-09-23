#!/usr/bin/env python3
"""Ingest a folder of documents into a corpus that citations can point into.

    python3 scripts/ingest.py <path> [<path> ...] [--corpus DIR] [--images] [--force]

Writes DIR/index.json plus one DIR/docs/<id>.json per document. Each document is
split into pages and each page keeps its original text, unmodified. A citation
resolves to (doc, page, char offsets) in that text, which is what lets the quote
be checked and highlighted later.

Formats: .pdf .docx .txt .md .markdown .html .htm .rtf .csv .json
Scanned PDFs with no text layer are OCR'd automatically (see --ocr and ocr.py).
Files whose sha256 hasn't changed are skipped on re-run, so re-ingesting a big folder is cheap.
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import corpus_root, die, save_json  # noqa: E402

TEXT_EXT = {".txt", ".md", ".markdown", ".text", ".json", ".csv", ".rst"}
SUPPORTED = TEXT_EXT | {".pdf", ".docx", ".html", ".htm", ".rtf"}
SKIP_DIRS = {"node_modules", "venv", ".venv", "__pycache__", "site-packages",
             ".git", ".svn", "dist", "build", ".tox"}
SYNTH_PAGE_CHARS = 2800


# ---------------------------------------------------------------- extractors

def read_pdf(path: Path) -> tuple[list[str], bool]:
    import pymupdf

    with pymupdf.open(path) as doc:
        pages = [page.get_text("text") for page in doc]
    # Count blank pages instead of averaging characters per page. A 50-page scan with a
    # typed cover sheet averages 40 characters a page and would pass as a text PDF with
    # 49 blank pages.
    empty = sum(1 for p in pages if len(p.strip()) < 40)
    scanned = bool(pages) and empty >= max(1, (len(pages) + 1) // 2)
    return pages, scanned, empty


def render_pdf_images(path: Path, out_dir: Path, dpi: int = 110) -> int:
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            page.get_pixmap(dpi=dpi).save(out_dir / f"p{i}.png")
            n += 1
    return n


def read_docx(path: Path) -> list[str]:
    """Read a .docx with the stdlib: unzip, collect w:t runs, break lines on w:p and
    pages on w:br[@type=page] or lastRenderedPageBreak. It's the most common office
    format, so it shouldn't need an extra dependency."""
    import xml.etree.ElementTree as ET

    ns_w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    pages: list[list[str]] = [[]]
    for para in root.iter(f"{ns_w}p"):
        buf: list[str] = []
        hard_break = False
        for node in para.iter():
            if node.tag == f"{ns_w}t":
                buf.append(node.text or "")
            elif node.tag == f"{ns_w}tab":
                buf.append("\t")
            elif node.tag == f"{ns_w}br" and node.get(f"{ns_w}type") == "page":
                hard_break = True
            elif node.tag == f"{ns_w}lastRenderedPageBreak":
                hard_break = True
        pages[-1].append("".join(buf))
        if hard_break:
            pages.append([])
    return ["\n".join(p).strip() for p in pages if any(s.strip() for s in p)]


class _HTMLText(html.parser.HTMLParser):
    """Extract the text of an HTML page, leaving out navigation and other chrome.

    A captured web page is mostly navigation, cookie banners and footers. Quotes from
    those are useless, and they push the real text off the first page. So we skip
    those elements entirely, and if the page marks its content with <main> or
    <article>, we collect that separately (read_html decides whether to use it).
    """

    SKIP = {"script", "style", "noscript", "head", "nav", "header", "footer",
            "aside", "form", "button", "svg", "iframe", "template"}
    MAIN = {"main", "article"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
             "section", "article", "blockquote", "pre", "td", "th", "main"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.main_out: list[str] = []
        self._skip = 0
        self._main = 0

    def _sink(self) -> list[str]:
        return self.main_out if self._main else self.out

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
            return
        if tag in self.MAIN:
            self._main += 1
        if tag in self.BLOCK:
            self._sink().append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            if self._skip:
                self._skip -= 1
            return
        if tag in self.BLOCK:
            self._sink().append("\n")
        if tag in self.MAIN and self._main:
            self._main -= 1

    def handle_data(self, data):
        if not self._skip:
            self._sink().append(data)


def read_html(path: Path) -> str:
    p = _HTMLText()
    p.feed(path.read_text(errors="replace"))
    main = re.sub(r"\n{3,}", "\n\n", "".join(p.main_out)).strip()
    whole = re.sub(r"\n{3,}", "\n\n", "".join(p.out) + "".join(p.main_out)).strip()
    # use <main>/<article> only when it holds a real share of the page's text
    return main if len(main) > 400 and len(main) > 0.25 * len(whole) else whole


def read_rtf(path: Path) -> str:
    raw = path.read_text(errors="replace")
    raw = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), raw)
    raw = re.sub(r"\\par[d]?\b", "\n", raw)
    raw = re.sub(r"\{\\\*?[^{}]*\}", " ", raw)
    raw = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", raw)
    return re.sub(r"[{}]", "", raw)


def paginate(text: str, target: int = SYNTH_PAGE_CHARS) -> list[str]:
    """Split flat text into pseudo-pages of about `target` chars on paragraph
    boundaries. Citations need a page to point at, and the source drawer shouldn't
    have to show a whole file as one block. The split is deterministic, so page
    numbers stay the same across re-ingests."""
    paras = re.split(r"\n\s*\n", text)
    pages, buf, size = [], [], 0
    for para in paras:
        if size and size + len(para) > target:
            pages.append("\n\n".join(buf))
            buf, size = [], 0
        buf.append(para)
        size += len(para) + 2
    if buf:
        pages.append("\n\n".join(buf))
    return [p for p in pages if p.strip()] or [text]


# ----------------------------------------------------------------- titling

BANNER = re.compile(r"\b(EXECUTION COPY|EXECUTED|COUNTERPART|DRAFT|CONFIDENTIAL"
                    r"|RECEIVED|COPY|PAGE \d)\b", re.I)

# In law and tax a document's title is usually its number (Rev. Rul. 2024-14). Those
# lines are mostly digits and punctuation, so the generic heuristics in title_for
# score them badly, but they're what a reader needs to see on a pin cite.
DOCKET = re.compile(r"^(rev\.?\s?(rul|proc)\.?|notice\s+\d|t\.?d\.?\s?\d|p\.?l\.?r\.?"
                    r"|announcement\s|form\s+\d|publication\s+\d|circular\s|docket\s"
                    r"|case\s+no|no\.\s?\d|ruling\s+\d"
                    # the same convention outside law: trials, standards, specs, procedures
                    r"|nct\d|protocol\s+\S|study\s+\S|trial\s+\S|iso[/\s-]?\d|iec\s?\d"
                    r"|astm\s|ansi\s|ieee\s?\d|rfc\s?\d|sop\s?\S|doi:|guideline\s+\S"
                    r"|standard\s+\S|policy\s+\S|procedure\s+\S)", re.I)


def title_for(path: Path, pages: list[str]) -> str:
    """Find the title line on page 1, skipping running headers and stamps, and fall
    back to the filename.

    Documents often open with a header ("ACME / BETA - EXECUTION COPY") or a
    received stamp above the actual title, so we score the first few candidate
    lines and take the best one.
    """
    # a Markdown file that opens with a level-one heading: use the heading
    if path.suffix.lower() in {".md", ".markdown"}:
        first = next((ln.strip() for ln in (pages[0] if pages else "").splitlines() if ln.strip()), "")
        if re.match(r"#\s+\S", first):
            return first.lstrip("#").strip()
    # a regulation or statute page that opens with its section heading
    # ("§ 825.114 Inpatient care."): use that, even though it ends in a full stop
    first = next((ln.strip() for ln in (pages[0] if pages else "").splitlines() if ln.strip()), "")
    if re.match(r"\u00a7+\s*\d", first) and len(first) <= 110:
        return first.rstrip(".").strip()
    candidates: list[str] = []
    seen = 0
    for line in (pages[0] if pages else "").splitlines():
        line = line.strip().lstrip("#").strip()
        if not line:
            continue          # PDFs pad the masthead with blank lines, so keep going
        seen += 1
        words = line.split()
        if 1 < len(words) <= 18 and 6 <= len(line) <= 110 and not line.endswith((".", ";", ",")):
            candidates.append(line)
        if len(candidates) >= 5 or seen >= 14:
            break

    def score(indexed: tuple[int, str]) -> tuple[int, int]:
        i, line = indexed
        penalty = 0
        if len(line) > 64:
            penalty += 2
        if any(sep in line for sep in (" - ", " | ", " \u2013 ", "/")):
            penalty += 2
        if BANNER.search(line):
            penalty += 3
        if line[0] in "-\u2013\u2014*_" or line[-1] in "-\u2013\u2014*_":
            penalty += 3
        if line.startswith("(") or line.rstrip().endswith(":"):
            penalty += 3   # parentheticals and "Label:" lines aren't titles
        if line.startswith("("):
            penalty += 3
        if sum(c.isalpha() for c in line) < len(line) * 0.55:
            penalty += 2
        if DOCKET.match(line):
            penalty -= 4
        return (penalty, i)

    if candidates:
        return min(enumerate(candidates), key=score)[1]
    return re.sub(r"[_\-]+", " ", path.stem).strip()


# ---------------------------------------------------------------------- walk

def iter_files(paths: list[str]) -> list[Path]:
    """Walk the given paths, skipping hidden directories and toolchain folders.

    The pruning matters: a folder that has been ingested once contains a
    `.citations/` venv, and without pruning the walk would pick up several hundred
    licence files as documents.
    """
    found: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            found.append(p)
            continue
        if not p.is_dir():
            die(f"no such path: {p}")
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = sorted(d for d in dirnames
                                 if not d.startswith(".") and d not in SKIP_DIRS)
            for name in sorted(filenames):
                if name.startswith((".", "~$")) or name.endswith(".source.json"):
                    continue
                f = Path(dirpath) / name
                if f.suffix.lower() in SUPPORTED:
                    found.append(f)
    return found


# ---------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--corpus", default=None, help="corpus dir (default ./.citations)")
    ap.add_argument("--images", action="store_true",
                    help="also render PDF page images for the source drawer")
    ap.add_argument("--force", action="store_true", help="re-ingest unchanged files")
    ap.add_argument("--ocr", default="auto", choices=["auto", "off", "force"],
                    help="auto: OCR any PDF with no text layer (default). "
                         "force: OCR every PDF. off: leave scans uncitable.")
    ap.add_argument("--ocr-dpi", type=int, default=300)
    ap.add_argument("--ocr-engine", default="auto")
    args = ap.parse_args()

    root = corpus_root(args.corpus)
    files = iter_files(args.paths)
    if not files:
        die("no supported documents found")

    if any(f.suffix.lower() == ".pdf" for f in files):
        from _common import ensure_deps
        ensure_deps(["pymupdf"], ["pymupdf"], root)

    index_file = root / "index.json"
    index = json.loads(index_file.read_text()) if index_file.exists() else {"docs": []}
    by_path = {d["path"]: d for d in index["docs"]}
    next_n = 1 + max((int(d["id"][1:]) for d in index["docs"] if d["id"][1:].isdigit()), default=0)

    added = skipped = 0
    warnings: list[str] = []
    for f in files:
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        sidecar = Path(str(f) + ".source.json")
        source = json.loads(sidecar.read_text()) if sidecar.exists() else None
        prior = by_path.get(str(f.resolve()))
        if prior and prior["sha256"] == digest and not args.force:
            skipped += 1
            continue

        ext = f.suffix.lower()
        scanned = False
        ocr_info = None
        try:
            if ext == ".pdf":
                pages, scanned, empty_pages = read_pdf(f)
                if empty_pages and not scanned and args.ocr != "force":
                    warnings.append(
                        f"{f.name}: {empty_pages} of {len(pages)} pages have no text layer and "
                        f"were not OCR'd \u2014 likely scanned exhibits inside a text document. "
                        f"Re-run with --ocr force if you need to cite them.")
                if args.ocr != "off" and (scanned or args.ocr == "force"):
                    from ocr import LOW_CONFIDENCE, ocr_pdf
                    res = ocr_pdf(f, args.ocr_dpi, args.ocr_engine, root)
                    pages = [p["text"] for p in res["pages"]]
                    ocr_info = {k: res[k] for k in
                                ("engine", "dpi", "mean_confidence", "low_confidence_pages")}
                    ocr_info["confidence"] = [p["confidence"] for p in res["pages"]]
                    scanned = False
                    if res["low_confidence_pages"]:
                        warnings.append(
                            f"{f.name}: OCR confidence below {LOW_CONFIDENCE} on page(s) "
                            f"{', '.join(map(str, res['low_confidence_pages']))} \u2014 check any "
                            f"quote from them against the page image before relying on it")
                    if not res["chars"]:
                        warnings.append(f"{f.name}: OCR produced no text; the scan may be blank "
                                        f"or unreadable at {args.ocr_dpi} dpi")
            elif ext == ".docx":
                pages = read_docx(f)
                if len(pages) == 1:
                    pages = paginate(pages[0])
            elif ext in {".html", ".htm"}:
                pages = paginate(read_html(f))
            elif ext == ".rtf":
                pages = paginate(read_rtf(f))
            else:
                pages = paginate(f.read_text(errors="replace"))
        except Exception as exc:  # warn and move on; one bad file shouldn't stop the run
            warnings.append(f"{f.name}: {type(exc).__name__}: {exc}")
            continue

        # An HTML page that yields almost no text is the web version of a scan with no
        # text layer: the download succeeded, but there's nothing in it to quote.
        #
        # Thresholds were calibrated on six real captures. The text-to-bytes ratio
        # doesn't separate good captures from bad ones, because modern pages are mostly
        # chrome: an IRS press release with its full article came in at 3.8%, while a
        # statute page was 12.7% and a real occupation table 12.3%. Absolute text volume
        # does separate them. The one failed capture yielded 836 characters, and every
        # real document had several thousand. The ratio test is kept only to catch a
        # very large page that yields almost nothing.
        text_chars = sum(len(t) for t in pages)
        raw_bytes = f.stat().st_size
        thin = ext in {".html", ".htm"} and (
            text_chars < 300                                 # a bot challenge or captcha page
            or (raw_bytes > 20_000 and (text_chars < 1_500 or text_chars < 0.01 * raw_bytes)))
        if thin:
            warnings.append(
                f"{f.name}: {raw_bytes:,} bytes of HTML yielded only {text_chars:,} characters "
                f"of text ({text_chars / raw_bytes:.1%}) \u2014 almost certainly site navigation "
                f"rather than the document, from a page rendered client-side or behind a "
                f"consent wall. Check it before citing anything from it; the document is "
                f"usually available elsewhere.")

        if scanned:
            warnings.append(f"{f.name}: no text layer (scanned image PDF) and --ocr off \u2014 "
                            f"it cannot be cited. Re-run without --ocr off.")

        doc_id = prior["id"] if prior else f"d{next_n}"
        if not prior:
            next_n += 1

        # always render page images for an OCR'd PDF, so the reader can check the
        # inferred text against the scan
        n_images = 0
        if ext == ".pdf" and (args.images or ocr_info):
            n_images = render_pdf_images(f, root / "pages" / doc_id)

        record = {
            "id": doc_id,
            "title": title_for(f, pages),
            "filename": f.name,
            "path": str(f.resolve()),
            "type": ext.lstrip("."),
            "sha256": digest,
            "pages": len(pages),
            "chars": sum(len(p) for p in pages),
            "page_label": "p." if ext == ".pdf" else "\u00a7",
            "images": n_images,
            "scanned": scanned,
            "thin": thin,
            "ocr": ocr_info,
            "source": source,
        }
        if source and source.get("title"):
            record["title"] = source["title"]
        conf = (ocr_info or {}).get("confidence") or []
        save_json(root / "docs" / f"{doc_id}.json", {**record, "page_text": [
            {"n": i, "text": t,
             **({"ocr_confidence": conf[i - 1]} if i <= len(conf) and conf[i - 1] is not None else {})}
            for i, t in enumerate(pages, 1)]})
        by_path[record["path"]] = record
        added += 1

    index["docs"] = sorted(by_path.values(), key=lambda d: int(d["id"][1:]))
    save_json(index_file, index)

    # delete the BM25 index; search.py rebuilds it when it's missing or older than index.json
    (root / "bm25.json").unlink(missing_ok=True)

    print(json.dumps({
        "corpus": str(root),
        "ingested": added,
        "unchanged": skipped,
        "documents": len(index["docs"]),
        "pages": sum(d["pages"] for d in index["docs"]),
        "ocr_documents": sum(1 for d in index["docs"] if d.get("ocr")),
        "web_documents": sum(1 for d in index["docs"] if (d.get("source") or {}).get("url")),
        "low_yield_documents": sum(1 for d in index["docs"] if d.get("thin")),
        "warnings": warnings,
        "docs": [{"id": d["id"], "title": d["title"], "pages": d["pages"],
                  "chars": d["chars"], "file": d["filename"],
                  **({"ocr": d["ocr"]["engine"],
                      "ocr_confidence": d["ocr"]["mean_confidence"]} if d.get("ocr") else {}),
                  **({"url": d["source"]["url"], "retrieved": d["source"]["retrieved_at"]}
                     if (d.get("source") or {}).get("url") else {})}
                 for d in index["docs"]],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
