#!/usr/bin/env python3
"""Name a corpus so it can be pointed at, shared and reused.

    python3 scripts/corpus.py new us-tax ~/libraries/tax --describe "IRC, regs, rulings"
    python3 scripts/corpus.py add us-tax ~/downloads/rev-rul-2024-14.pdf
    python3 scripts/corpus.py add us-tax --url https://www.irs.gov/pub/irs-pdf/p501.pdf
    python3 scripts/corpus.py list
    python3 scripts/corpus.py show us-tax
    python3 scripts/corpus.py forget us-tax          # unregister; files are left alone

Every other script accepts `--corpus us-tax` wherever it takes a path, so a corpus
built once can be used from any directory and referred to by name. Registrations
live in ~/.claude/citations/corpora.json; the documents stay wherever you put them.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (CORPUS_DIRNAME, corpus_manifest, corpus_root, die,  # noqa: E402
                     load_registry, save_registry, forget_registry)

HERE = Path(__file__).resolve().parent


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(script: str, args: list[str]) -> dict:
    """Run a sibling script and return its parsed JSON instead of letting it print.

    We print one combined JSON object at the end. Two objects on one stdout
    couldn't be parsed, and every caller of these scripts parses their output.
    """
    r = subprocess.run([sys.executable, str(HERE / script), *args],
                       capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    if r.returncode != 0:
        print(r.stdout, file=sys.stderr)
        raise SystemExit(r.returncode)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"output": r.stdout[-2000:]}


def summarize(steps: dict) -> dict:
    """Copy warnings, failed captures and a short list of captures up to the top
    level, where the caller will see them."""
    out: dict = {}
    warnings = list(steps.get("ingested", {}).get("warnings", []))
    warnings += list(steps.get("fetched", {}).get("warnings", []))
    failed = steps.get("fetched", {}).get("failed", [])
    if warnings:
        out["warnings"] = warnings
    if failed:
        out["failed_to_capture"] = failed
    if "fetched" in steps:
        out["captured"] = [{k: c.get(k) for k in ("url", "status", "bytes", "title")}
                           for c in steps["fetched"].get("captured", [])]
    return out


def describe(root: Path) -> dict:
    manifest = corpus_manifest(root)
    index_file = root / "index.json"
    docs = json.loads(index_file.read_text())["docs"] if index_file.exists() else []
    web = [d for d in docs if d.get("source", {}).get("url")]
    return {
        **manifest,
        "path": str(root),
        "documents": len(docs),
        "pages": sum(d["pages"] for d in docs),
        "ocr_documents": sum(1 for d in docs if d.get("ocr")),
        "web_documents": len(web),
        "low_yield_documents": sum(1 for d in docs if d.get("thin")),
        "exists": root.exists(),
        "ingested": index_file.exists(),
    }


def cmd_new(args) -> int:
    reg = load_registry()
    if args.name in reg["corpora"] and not args.force:
        die(f"{args.name!r} is already registered at "
            f"{reg['corpora'][args.name]['path']} — use --force to repoint it")
    root = Path(args.path).expanduser().resolve()
    if root.name != CORPUS_DIRNAME:
        root = root / CORPUS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    (root / "corpus.json").write_text(json.dumps({
        "name": args.name,
        "description": args.describe or "",
        "created": now(),
    }, indent=1))
    reg["corpora"][args.name] = {"path": str(root), "description": args.describe or "",
                                 "created": now()}
    save_registry(reg)

    steps = {}
    if args.from_:
        steps["ingested"] = run("ingest.py", [*args.from_, "--corpus", str(root),
                                              *(["--images"] if args.images else [])])
    if args.url:
        steps["fetched"] = run("fetch.py", [*args.url, "--corpus", str(root)])
    print(json.dumps({"registered": args.name, **describe(root),
                      **summarize(steps)}, indent=1))
    return 0


def cmd_add(args) -> int:
    root = corpus_root(args.name)
    if not args.paths and not args.url:
        die("give paths, --url, or both")
    steps = {}
    if args.paths:
        steps["ingested"] = run("ingest.py", [*args.paths, "--corpus", str(root),
                                              *(["--images"] if args.images else [])])
    if args.url:
        steps["fetched"] = run("fetch.py", [*args.url, "--corpus", str(root)])
    print(json.dumps({**describe(root), **summarize(steps)}, indent=1))
    return 0


def cmd_list(args) -> int:
    reg = load_registry()
    out = []
    for name, entry in sorted(reg["corpora"].items()):
        root = Path(entry["path"])
        d = describe(root) if root.exists() else {"path": entry["path"], "exists": False, "ingested": False}
        out.append({"name": name, "description": entry.get("description", ""), **d})
    print(json.dumps({"registry": str(__import__("_common").REGISTRY), "corpora": out}, indent=1))
    return 0


def cmd_show(args) -> int:
    root = corpus_root(args.name)
    info = describe(root)
    index_file = root / "index.json"
    if index_file.exists():
        docs = json.loads(index_file.read_text())["docs"]
        info["docs"] = [{"id": d["id"], "title": d["title"], "pages": d["pages"],
                         "file": d["filename"],
                         **({"url": d["source"]["url"],
                             "retrieved": d["source"]["retrieved_at"]}
                            if d.get("source", {}).get("url") else {}),
                         **({"low_yield": True} if d.get("thin") else {})}
                        for d in docs]
    print(json.dumps(info, indent=1))
    return 0


def cmd_forget(args) -> int:
    reg = load_registry()
    if args.name not in reg["corpora"]:
        die(f"{args.name!r} is not registered")
    entry = reg["corpora"][args.name]
    forget_registry(args.name)
    print(json.dumps({"forgot": args.name, "path": entry["path"],
                      "note": "the files were left in place"}, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="register a named corpus and optionally fill it")
    n.add_argument("name")
    n.add_argument("path", help="where the corpus lives (a .citations dir is created inside)")
    n.add_argument("--describe", default=None)
    n.add_argument("--from", dest="from_", nargs="*", default=[], help="documents to ingest now")
    n.add_argument("--url", nargs="*", default=[], help="URLs to capture now")
    n.add_argument("--images", action="store_true")
    n.add_argument("--force", action="store_true")
    n.set_defaults(fn=cmd_new)

    a = sub.add_parser("add", help="add documents or URLs to a corpus")
    a.add_argument("name")
    a.add_argument("paths", nargs="*")
    a.add_argument("--url", nargs="*", default=[])
    a.add_argument("--images", action="store_true")
    a.set_defaults(fn=cmd_add)

    l = sub.add_parser("list", help="every registered corpus")
    l.set_defaults(fn=cmd_list)

    s = sub.add_parser("show", help="what is in one corpus")
    s.add_argument("name")
    s.set_defaults(fn=cmd_show)

    f = sub.add_parser("forget", help="unregister a corpus without deleting it")
    f.add_argument("name")
    f.set_defaults(fn=cmd_forget)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
