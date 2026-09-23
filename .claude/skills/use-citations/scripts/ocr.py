#!/usr/bin/env python3
"""OCR scanned PDFs so their text can be cited like any other source.

    python3 scripts/ocr.py file.pdf [--dpi 300] [--engine auto]   # print text + confidence
    # normally you do not call this: ingest.py runs it for any PDF with no text layer

Engines, in order of preference:

  ocrmypdf   best when installed; rebuilds a searchable PDF and keeps the page layout
  vision     macOS Vision framework via pyobjc; no system install, very good on English
  tesseract  the CLI, if it is on PATH

OCR text is inferred from pixels, so it's weaker evidence than a real text layer. When the
engine reports a confidence (Vision does), each page keeps its mean recognition confidence,
and the report shows it on that page next to the scan.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import corpus_root as default_corpus_root  # noqa: E402
from _common import die, ensure_deps, log  # noqa: E402

LOW_CONFIDENCE = 0.80


def available_engines() -> list[str]:
    out = []
    if shutil.which("ocrmypdf"):
        out.append("ocrmypdf")
    if sys.platform == "darwin":
        out.append("vision")
    if shutil.which("tesseract"):
        out.append("tesseract")
    return out


def pick_engine(requested: str) -> str:
    have = available_engines()
    if requested != "auto":
        if requested not in have:
            die(f"engine {requested!r} is not available here; found: {', '.join(have) or 'none'}")
        return requested
    if not have:
        die("no OCR engine available. On macOS this should not happen; otherwise install "
            "one:\n  brew install ocrmypdf     (best)\n  brew install tesseract")
    return have[0]


# ---------------------------------------------------------------- engines

def ocr_with_ocrmypdf(pdf: Path, dpi: int) -> list[tuple[str, float | None]]:
    """Rebuild the PDF with a text layer, then read it back the normal way."""
    import pymupdf

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "ocr.pdf"
        cmd = ["ocrmypdf", "--force-ocr", "--quiet", "--image-dpi", str(dpi), str(pdf), str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            die(f"ocrmypdf failed: {(r.stderr or r.stdout).strip()[:400]}")
        with pymupdf.open(out) as doc:
            return [(page.get_text("text"), None) for page in doc]


def ocr_with_tesseract(pdf: Path, dpi: int) -> list[tuple[str, float | None]]:
    import pymupdf

    pages: list[tuple[str, float | None]] = []
    with tempfile.TemporaryDirectory() as td, pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, 1):
            png = Path(td) / f"p{i}.png"
            page.get_pixmap(dpi=dpi).save(png)
            r = subprocess.run(["tesseract", str(png), "stdout", "--psm", "1"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                die(f"tesseract failed on page {i}: {r.stderr.strip()[:300]}")
            pages.append((r.stdout, None))
            log(f"ocr page {i}/{doc.page_count}")
    return pages


def ocr_with_vision(pdf: Path, dpi: int) -> list[tuple[str, float | None]]:
    """macOS Vision. Observations come back one per text line, each with a normalized
    box whose origin is bottom-left. Sorting by descending y, then ascending x, gives
    reading order for single-column documents."""
    import pymupdf
    import Quartz
    import Vision
    from Foundation import NSURL

    pages: list[tuple[str, float | None]] = []
    with tempfile.TemporaryDirectory() as td, pymupdf.open(pdf) as doc:
        total = doc.page_count
        for i, page in enumerate(doc, 1):
            png = Path(td) / f"p{i}.png"
            page.get_pixmap(dpi=dpi).save(png)

            src = Quartz.CGImageSourceCreateWithURL(
                NSURL.fileURLWithPath_(str(png)), None)
            image = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)

            req = Vision.VNRecognizeTextRequest.alloc().init()
            req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            req.setUsesLanguageCorrection_(True)
            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
            ok, err = handler.performRequests_error_([req], None)
            if not ok:
                die(f"Vision failed on page {i}: {err}")

            lines = []
            for obs in (req.results() or []):
                best = obs.topCandidates_(1)
                if not best:
                    continue
                box = obs.boundingBox()
                lines.append((round(box.origin.y, 3), box.origin.x,
                              best[0].string(), best[0].confidence()))
            lines.sort(key=lambda l: (-l[0], l[1]))
            text = "\n".join(l[2] for l in lines)
            conf = round(sum(l[3] for l in lines) / len(lines), 3) if lines else 0.0
            pages.append((text, conf))
            log(f"ocr page {i}/{total} — {len(lines)} lines, confidence {conf}")
    return pages


ENGINES = {"ocrmypdf": ocr_with_ocrmypdf, "vision": ocr_with_vision, "tesseract": ocr_with_tesseract}


def ocr_pdf(pdf: Path, dpi: int = 300, engine: str = "auto",
            corpus_root: Path | None = None) -> dict:
    # install deps into the working corpus's venv, never into a folder of the user's documents
    engine = pick_engine(engine)
    deps = ["pymupdf"]
    mods = ["pymupdf"]
    if engine == "vision":
        mods += ["Vision", "Quartz"]
        deps += ["pyobjc-framework-Vision", "pyobjc-framework-Quartz"]
    ensure_deps(mods, deps, corpus_root or default_corpus_root(None))

    log(f"OCR {pdf.name} with {engine} at {dpi} dpi")
    pages = ENGINES[engine](pdf, dpi)
    confs = [c for _, c in pages if c is not None]
    return {
        "engine": engine,
        "dpi": dpi,
        "pages": [{"text": t, "confidence": c} for t, c in pages],
        "mean_confidence": round(sum(confs) / len(confs), 3) if confs else None,
        "low_confidence_pages": [i for i, (_, c) in enumerate(pages, 1)
                                 if c is not None and c < LOW_CONFIDENCE],
        "chars": sum(len(t) for t, _ in pages),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--engine", default="auto", choices=["auto", *ENGINES])
    ap.add_argument("--text", action="store_true", help="print the text instead of a summary")
    args = ap.parse_args()

    pdf = Path(args.pdf).expanduser()
    if not pdf.exists():
        die(f"no such file: {pdf}")
    result = ocr_pdf(pdf, args.dpi, args.engine)
    if args.text:
        for i, p in enumerate(result["pages"], 1):
            print(f"\n----- page {i} (confidence {p['confidence']}) -----\n{p['text']}")
        return 0
    print(json.dumps({k: v for k, v in result.items() if k != "pages"}
                     | {"page_chars": [len(p["text"]) for p in result["pages"]],
                        "engines_available": available_engines()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
