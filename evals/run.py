#!/usr/bin/env python3
"""Evals for use-citations: a public question set, and a scorer for runs against it.

    python3 evals/run.py list                 # the set, with run status
    python3 evals/run.py score [ID ...]       # score every run present (or the ones named)
    python3 evals/run.py score --out FILE     # write the scorecard elsewhere (the test suite does)
    python3 evals/run.py rebuild ID           # recreate a run's corpus from its recorded sources.json

A corpus is the set of source documents captured for one run. Corpora aren't committed
(they hold captured documents and a venv). Each run records the URLs it captured in
sources.json, and `rebuild` captures them again so you can re-verify a run on another machine.

The set lives in evals/questions.json. Every question is quoted word for word from a public
source that publishes its own reference answer (an agency FAQ, or a labelled dataset), so a
run can be checked against that answer as well as scored mechanically. None of the questions
I asked while building the skill are in the set.

A run is a directory evals/runs/<id>/ holding the answer.json the skill produced,
verified against the corpus registered as `eval-<id>`. An optional judgment.json
records what only a person can score:
    {"agrees_with_reference": "yes|partial|no", "notes": "..."}

Scored mechanically, per run:
    verified / failed / warnings, match grades
    a disconfirming search recorded (a search for material that would undermine the answer)
    circular: every citation points at the FAQ page the question came from
    low-yield captures cited (captures flagged as short or near-empty; reported, not failed)
    documents captured vs cited, gaps stated
A run passes when nothing failed, a disconfirming search was recorded, the citations aren't
circular, and (if judged) the answer doesn't disagree with the reference.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SK = HERE.parent / ".claude" / "skills" / "use-citations"
CS = SK / "scripts"
sys.path.insert(0, str(CS))
from _common import corpus_root, load_registry  # noqa: E402

QUESTIONS = HERE / "questions.json"
RUNS = HERE / "runs"
RESULTS_MD = HERE / "RESULTS.md"
RESULTS_JSON = HERE / "results.json"


def questions() -> list[dict]:
    return json.loads(QUESTIONS.read_text())["questions"]


def corpus_for(qid: str) -> Path | None:
    name = f"eval-{qid}"
    if name in load_registry()["corpora"]:
        return corpus_root(name)
    local = RUNS / qid / ".citations"
    return local if (local / "index.json").exists() else None


def score_one(q: dict) -> dict:
    qid = q["id"]
    run_dir = RUNS / qid
    answer = run_dir / "answer.json"
    out = {"id": qid, "domain": q["domain"], "status": "pending"}
    if not answer.exists():
        return out
    root = corpus_for(qid)
    if root is None:
        return {**out, "status": "no-corpus"}

    r = subprocess.run([sys.executable, str(CS / "verify.py"), str(answer), "--corpus", str(root),
                        "--lenient", "-o", str(run_dir / "answer.verified.json")],
                       capture_output=True, text=True)
    try:
        v = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {**out, "status": "verify-error", "error": (r.stderr or r.stdout)[-200:]}

    verified = json.loads((run_dir / "answer.verified.json").read_text())
    index = json.loads((root / "index.json").read_text())
    by_id = {d["id"]: d for d in index["docs"]}
    cited_ids = {e["doc"] for e in v.get("ledger", []) or verified["verification"]["ledger"]}
    cited_urls = {(by_id[d].get("source") or {}).get("url") for d in cited_ids if d in by_id}
    src = q.get("source_url", "")
    circular = bool(cited_urls) and all(u == src for u in cited_urls)
    low_yield_cited = any(by_id[d].get("thin") for d in cited_ids if d in by_id)
    searches = v.get("searches") or []
    has_contra = any(str(s.get("for", "")).lower().startswith("contra") for s in searches)

    judgment = {}
    jf = run_dir / "judgment.json"
    if jf.exists():
        judgment = json.loads(jf.read_text())
    agrees = judgment.get("agrees_with_reference")

    passed = (v["failed"] == 0 and has_contra and not circular
              and agrees != "no")
    return {**out, "status": "run",
            "citations": v["citations"], "verified": v["verified"], "failed": v["failed"],
            "warnings": v["warnings"], "grades": v["grades"],
            "searches": len(searches), "disconfirming": has_contra,
            "docs_in_corpus": v["documents_in_corpus"], "docs_cited": v["documents_cited"],
            "circular": circular, "low_yield_cited": low_yield_cited,
            "gaps": len(verified.get("gaps") or []),
            "agrees_with_reference": agrees, "notes": judgment.get("notes", ""),
            "pass": passed}


def cmd_list() -> int:
    qs = questions()
    print(f"{len(qs)} questions\n")
    for q in qs:
        state = "run" if (RUNS / q["id"] / "answer.json").exists() else "pending"
        print(f"  {q['id']:14} {q['domain']:18} {state:8} {q['question'][:70]}")
    return 0


def cmd_score(ids: list[str], out_md: Path = RESULTS_MD, out_json: Path = RESULTS_JSON) -> int:
    qs = [q for q in questions() if not ids or q["id"] in ids]
    rows = [score_one(q) for q in qs]
    run = [r for r in rows if r["status"] == "run"]
    passed = [r for r in run if r["pass"]]
    # A fresh clone has answers but no corpora, so don't overwrite the real scorecard with an empty one.
    if not run and out_md == RESULTS_MD and RESULTS_MD.exists() and "of" in RESULTS_MD.read_text()[:400]:
        print("no run has a corpus on this machine; leaving the committed RESULTS.md untouched.\n"
              "Rebuild a corpus with: python3 evals/run.py rebuild <id>", file=sys.stderr)
        return 1

    lines = [f"# Eval results", "",
             f"Scored {date.today().isoformat()} · {len(run)} of {len(qs)} questions run · "
             f"{len(passed)} pass", "",
             "An answer passes if every quote was found in its source, Claude searched for "
             "evidence that the answer might be wrong, the answer doesn't just cite the FAQ page "
             "the question came from, and (where I checked) it doesn't disagree with the "
             "official answer. [evals/README.md](README.md) explains how it all works.", "",
             "What the columns mean: **cites** is how many quotes the answer has. **verified** "
             "and **failed** are how many were and weren't found in the saved documents. "
             "**warn** is things the checker flagged for a person to look at without failing "
             "the answer, such as a wrong page number or a quote that appears twice. "
             "**disconf.** is whether Claude searched for evidence against its answer. "
             "**circular** is whether it only cited the FAQ page. **agrees** is my judgment of "
             "whether it matches the official answer.", "",
             "| id | domain | cites | verified | failed | warn | disconf. | circular | agrees | pass |",
             "|---|---|---:|---:|---:|---:|:-:|:-:|:-:|:-:|"]
    for r in rows:
        if r["status"] != "run":
            lines.append(f"| {r['id']} | {r['domain']} | | | | | | | | *{r['status']}* |")
            continue
        lines.append(f"| {r['id']} | {r['domain']} | {r['citations']} | {r['verified']} | {r['failed']} | "
                     f"{r['warnings']} | {'yes' if r['disconfirming'] else 'no'} | "
                     f"{'YES' if r['circular'] else 'no'} | {r['agrees_with_reference'] or '—'} | "
                     f"{'pass' if r['pass'] else 'FAIL'} |")
    if run:
        tot_c = sum(r["citations"] for r in run); tot_v = sum(r["verified"] for r in run)
        lines += ["", f"Altogether: {tot_v} of {tot_c} quotes found, "
                  f"{sum(r['failed'] for r in run)} not found. "
                  f"{sum(1 for r in run if r['disconfirming'])} of {len(run)} answers searched for evidence against themselves, "
                  f"and {sum(1 for r in run if r['circular'])} only cited the FAQ page."]
        notes = [(r["id"], r["notes"]) for r in run if r.get("notes")]
        if notes:
            lines += ["", "## Notes", "", "For each answer I checked by hand: what the official answer says, and how the skill's answer compares.", ""] + [f"- **{i}**: {n}" for i, n in notes]
    out_md.write_text("\n".join(lines) + "\n")
    out_json.write_text(json.dumps({"scored": date.today().isoformat(), "rows": rows}, indent=1))
    print("\n".join(lines))
    return 0


def cmd_rebuild(qid: str) -> int:
    src = RUNS / qid / "sources.json"
    if not src.exists():
        print(f"no sources.json for {qid}", file=sys.stderr); return 2
    urls = [d["url"] for d in json.loads(src.read_text())["documents"] if d.get("url")]
    if not urls:
        print(f"{qid}: sources.json lists no URLs (local-file corpus); nothing to rebuild", file=sys.stderr); return 2
    r = subprocess.run([sys.executable, str(CS / "corpus.py"), "new", f"eval-{qid}", str(RUNS / qid),
                        "--describe", f"eval run: {qid} (rebuilt)", "--force", "--url", *urls])
    return r.returncode


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] not in ("list", "score", "rebuild"):
        print(__doc__); return 2
    if args[0] == "list":
        return cmd_list()
    if args[0] == "rebuild":
        return cmd_rebuild(args[1]) if len(args) > 1 else 2
    out_md, out_json, ids = RESULTS_MD, RESULTS_JSON, []
    rest = args[1:]
    if "--out" in rest:
        i = rest.index("--out"); out_md = Path(rest[i + 1]); out_json = out_md.with_suffix(".json")
        rest = rest[:i] + rest[i + 2:]
    return cmd_score(rest, out_md, out_json)


if __name__ == "__main__":
    raise SystemExit(main())
