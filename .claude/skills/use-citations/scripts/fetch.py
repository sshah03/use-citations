#!/usr/bin/env python3
"""Capture a web document whole, with provenance, so it can be cited.

    python3 scripts/fetch.py <url> [<url> ...] [--corpus NAME] [--as "Title"]

Downloads only the URLs given (there's no crawling), saves the raw bytes in
<corpus>/sources/, records where and when they came from, and ingests the result
so the document can be quoted like any local file.

**Why not just read the page?** A search snippet or a summary of a page can't be
quoted verbatim, anchored to a character offset, or re-checked a year later. The
page can also change after you read it, and the reader would have no way to tell.
So a citation to a web page needs the bytes, a retrieval timestamp and a hash.
This records:

    url, final_url (after redirects), retrieved_at (UTC), http status,
    content_type, sha256, byte length

The report then shows a web source as "as retrieved 2026-09-19", with a link to
the live URL next to the archived copy the quote was taken from.

Use the harness's own web search to find documents and this script to capture
them. Don't cite the search snippet itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import corpus_root, die, log  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/125.0 Safari/537.36 citations-skill/1.0 (document capture for citation)")
TIMEOUT = 45
MAX_BYTES = 200 * 1024 * 1024   # far bigger than any real document; refuse instead of reading it into memory
PAUSE = 1.0

EXT_BY_TYPE = {
    "application/pdf": ".pdf", "text/html": ".html", "application/xhtml+xml": ".html",
    "text/plain": ".txt", "text/markdown": ".md", "application/json": ".json",
    "application/rtf": ".rtf", "text/rtf": ".rtf", "text/csv": ".csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


def slugify(url: str, title: str | None) -> str:
    base = title or urllib.parse.urlparse(url).path.rsplit("/", 1)[-1] or \
        urllib.parse.urlparse(url).netloc
    base = re.sub(r"\.(html?|pdf|txt|json)$", "", base, flags=re.I)
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")[:70]
    return base or "document"


def html_title(raw: bytes) -> str | None:
    m = re.search(rb"<title[^>]*>(.*?)</title>", raw[:200_000], re.I | re.S)
    if not m:
        return None
    import html as htmlmod
    t = re.sub(r"\s+", " ", htmlmod.unescape(m.group(1).decode("utf-8", "replace"))).strip()
    for sep in ("|", "\u2013", "\u2014", " :: "):
        if sep in t:
            head = t.split(sep)[0].strip()
            if len(head) >= 15:
                t = head
                break
    return t[:160] or None


def fetch_one(url: str, sources: Path, as_title: str | None) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                return {"url": url, "error": f"{int(declared):,} bytes exceeds the {MAX_BYTES:,}-byte "
                                             f"capture limit \u2014 not a citable document"}
            raw = resp.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return {"url": url, "error": f"response exceeds the {MAX_BYTES:,}-byte capture limit"}
            info = {
                "url": url,
                "final_url": resp.geturl(),
                "status": resp.status,
                "content_type": (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower(),
                "charset": (resp.headers.get_content_charset() or None),
                "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
    except urllib.error.HTTPError as e:
        return {"url": url, "error": f"HTTP {e.code} {e.reason}"}
    except Exception as e:  # DNS, TLS, timeout, refused
        return {"url": url, "error": f"{type(e).__name__}: {e}"}

    if info["status"] != 200:
        info["warning"] = f"HTTP {info['status']} — not a plain success; check the captured text is the document"
    else:
        from urllib.parse import urlparse
        a, b = urlparse(url), urlparse(info["final_url"])
        if (a.netloc, a.path.rstrip("/")) != (b.netloc, b.path.rstrip("/")):
            info["warning"] = (f"redirected to {info['final_url']} — a landing page can answer with "
                               f"HTTP 200; check the captured text is the document you asked for")

    ctype = info["content_type"]
    ext = EXT_BY_TYPE.get(ctype)
    if ext is None:
        if ctype.startswith(("image/", "video/", "audio/")):
            return {"url": url, "error": f"{ctype} is not a document — nothing to quote"}
        ext = ".html" if b"<html" in raw[:2000].lower() else ".txt"

    title = as_title or (html_title(raw) if ext == ".html" else None)
    digest = hashlib.sha256(raw).hexdigest()
    stem = f"{slugify(url, title)}-{digest[:8]}"
    path = sources / f"{stem}{ext}"
    path.write_bytes(raw)

    info |= {"sha256": digest, "bytes": len(raw), "file": str(path),
             "title": title, "captured_from": "fetch.py"}
    Path(str(path) + ".source.json").write_text(json.dumps(info, indent=1))
    log(f"captured {len(raw):,} bytes of {ctype or 'unknown type'} → {path.name}")
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--as", dest="as_title", default=None,
                    help="title for the document (only sensible with one URL)")
    ap.add_argument("--images", action="store_true", help="render page images for captured PDFs")
    ap.add_argument("--no-ingest", action="store_true", help="capture only; do not ingest")
    args = ap.parse_args()

    root = corpus_root(args.corpus)
    sources = root / "sources"
    sources.mkdir(parents=True, exist_ok=True)

    results = []
    for i, url in enumerate(args.urls):
        if not urllib.parse.urlparse(url).scheme in ("http", "https"):
            results.append({"url": url, "error": "only http(s) URLs are supported"})
            continue
        if i:
            time.sleep(PAUSE)
        results.append(fetch_one(url, sources, args.as_title if len(args.urls) == 1 else None))

    captured = [r for r in results if "file" in r]
    failed = [r for r in results if "error" in r]

    if captured and not args.no_ingest:
        cmd = [sys.executable, str(Path(__file__).resolve().parent / "ingest.py"),
               *[r["file"] for r in captured], "--corpus", str(root)]
        if args.images:
            cmd.append("--images")
        r = subprocess.run(cmd, capture_output=True, text=True)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            die(f"captured the files but ingest failed:\n{r.stdout[-800:]}")
        ingested = json.loads(r.stdout)
    else:
        ingested = None

    print(json.dumps({
        "corpus": str(root),
        "warnings": [f"{c['url']}: {c['warning']}" for c in captured if c.get("warning")]
                    + (ingested or {}).get("warnings", []),
        "captured": [{k: v for k, v in c.items() if k in
                      ("url", "final_url", "status", "content_type", "bytes",
                       "sha256", "retrieved_at", "title", "file")} for c in captured],
        "failed": failed,
        "ingested": ingested and {"documents": ingested["documents"],
                                  "new": ingested["ingested"],
                                  "docs": ingested["docs"][-len(captured):]},
    }, indent=1, ensure_ascii=False))
    return 1 if failed and not captured else 0


if __name__ == "__main__":
    raise SystemExit(main())
