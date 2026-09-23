#!/usr/bin/env python3
"""Tests for use-citations.

    python3 tests/run.py [-v]

Phases, in the order they run:

  adversarial   an answer with one block per case in EXPECTED. Most are built to
                fail in a specific way and must be reported; the rest must pass
                without a false alarm. This is the most important group, because
                it checks that a quote the skill can't find really does stop the
                answer.
  integration   the example document sets end to end: ingest, verify,
                render, and a syntax check of the report's JavaScript.
  scans         per-page detection of image-only pages in PDFs.
  hybrid        local files and a captured web document in one corpus.
  registry      two sessions saving the corpus registry at once.
  follow-up     a second question added to an existing report.
  evals         the public eval set loads and scores.
  web           the captured web corpora, if they are registered on this machine.
                Skipped otherwise, so the suite never touches the network.

Exit 0 if everything passed or skipped, 1 otherwise.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CS = SKILL / "scripts"
EX = SKILL / "examples"
FIX = SKILL / "tests" / "fixtures"
VERBOSE = "-v" in sys.argv

PASS, FAIL, SKIP = "\033[32mpass\033[0m", "\033[31mFAIL\033[0m", "\033[33mskip\033[0m"
results: list[tuple[str, str, str]] = []


def record(state: str, name: str, detail: str = "") -> None:
    results.append((state, name, detail))
    if VERBOSE or state == FAIL:
        print(f"  {state}  {name}" + (f"  — {detail}" if detail else ""))


def check(cond: bool, name: str, detail: str = "") -> bool:
    record(PASS if cond else FAIL, name, "" if cond else detail)
    return cond


def run(script: str, *args: str) -> tuple[int, dict | None, str]:
    r = subprocess.run([sys.executable, str(CS / script), *args],
                       capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout), r.stderr
    except json.JSONDecodeError:
        return r.returncode, None, r.stderr + r.stdout


# ------------------------------------------------------------------ phase 1

EXPECTED = {
    "not-found":          ("problem", "not found"),
    "figure-swap":        ("problem", "does not appear in the matched source passage"),
    "uncited":            ("problem", "no citation"),
    "unknown-doc":        ("problem", "no document matches"),
    "elided":             ("grade", "elided"),
    "hyphen-wrap":        ("grade", "exact"),
    "typography":         ("grade", "exact"),
    "wrong-page":         ("warning", "cited page 7"),
    "bad-anchor":         ("warning", "anchor"),
    "ambiguous-and-weak": ("warning", "more than once"),
    # false positives count too: labels like "Notice 2026-16" or "ISO 9001" in the
    # claim shouldn't be checked as figures
    "doc-number":         ("no-warning", "appears in no cited quote"),
    # a word the PDF hyphenated across a line break should still match
    "soft-hyphen":        ("grade", "exact"),
    # a near-verbatim quote that inverts the meaning must fail outright
    "negation-flip":      ("problem", "the meaning is changed"),
    "modal-flip":         ("problem", "the meaning is changed"),
    # an ellipsis can't join two separate passages into one quote
    "elision-stitch":     ("problem", "two passages, not one quotation"),
    # there's no flag that lets a claim skip needing a source
    "uncited-escape":     ("problem", "no citation"),
    # a document can be cited by the display name given in meta.short_names
    "short-name":         ("grade", "exact"),
    # a percentage written as a word in the claim matches the % sign in the quote
    "percent-word":       ("no-warning", "appears in no cited quote"),
    # a compound wrapped at its own hyphen ("on-the-\njob") should match the compound
    "compound-hyphen":    ("grade", "exact"),
    # a statute section number is a label: "2000e-5" says nothing about the year 2000
    "statute-section":    ("no-warning", "appears in no cited quote"),
    # a match must start and end on a word boundary, and figures are compared whole
    "partial-figure":     ("problem", "does not appear in the matched source passage"),
    "footnote-digit":     ("problem", "does not appear in the matched source passage"),
    "subword-elision":    ("problem", "not found"),
    # quoting the source's words with its negation cut off reverses what it says
    "dropped-negator":    ("problem", "reverses the meaning"),
    # figures are compared in order, and written-out numbers and comparisons count
    "swapped-figures":    ("problem", "different order"),
    "comparison-flip":    ("problem", "the meaning is changed"),
    "number-word":        ("problem", "the meaning is changed"),
    # the Federal Register breaks section numbers after their en dash
    "endash-wrap":        ("grade", "exact"),
    # a "No." ending the previous sentence shouldn't count as a negation cut off from the quote
    "faq-no":             ("grade", "exact"),
}


def phase_adversarial(tmp: Path) -> None:
    print("\nadversarial — does the verifier actually catch what the skill promises?")
    corpus = tmp / "adversarial"
    code, out, err = run("ingest.py", str(FIX / "corpus"), "--corpus", str(corpus))
    if not check(code == 0 and out is not None, "fixture corpus ingests", err[-300:]):
        return

    answer = json.loads((FIX / "adversarial.json").read_text())
    case_at = {}
    for i, b in enumerate(answer["blocks"]):
        text = b.get("text", "")
        if text.startswith("CASE "):
            case_at[f"block{i}"] = text.split(":", 1)[0][5:].strip()

    work = tmp / "adversarial.json"
    work.write_text(json.dumps(answer))
    code, report, err = run("verify.py", str(work), "--corpus", str(corpus))
    if report is None:
        check(False, "adversarial answer verifies", err[-400:])
        return

    check(code == 1, "verify exits non-zero on a defective answer", f"exit={code}")
    check(report["failed"] >= 6, "multiple citations fail", f"failed={report['failed']}")
    check(report["clean"] is False, "answer is not reported clean")

    verified = json.loads((work.with_suffix(".verified.json")).read_text())
    ledger_by_at = {e["at"]: e for e in verified["verification"]["ledger"]}
    problems, warnings = report["problems"], report["warning_details"]

    for at, case in case_at.items():
        kind, needle = EXPECTED[case]
        if kind == "problem":
            hit = any(p.get("at") == at and needle in p["problem"] for p in problems)
            check(hit, f"{case}: reported as a problem", f"no problem at {at} matching {needle!r}")
        elif kind == "warning":
            hit = any(w.get("at") == at and needle in w["problem"] for w in warnings)
            check(hit, f"{case}: reported as a warning", f"no warning at {at} matching {needle!r}")
        elif kind == "no-warning":
            noise = [w["problem"] for w in warnings
                     if w.get("at") == at and needle in w["problem"]]
            check(not noise, f"{case}: raises no false figure warning", "; ".join(noise)[:160])
        else:
            got = ledger_by_at.get(at, {}).get("status")
            check(got == needle, f"{case}: graded {needle}", f"graded {got!r}")

    # the normalizer shouldn't just be lenient: real defects must fail while
    # typographic differences pass
    ok_grades = {e["status"] for e in verified["verification"]["ledger"]}
    check("UNVERIFIED" not in ok_grades, "verified ledger holds no failures")

    # the search record: missing, confirming searches only, and with a disconfirming search
    check(any(w.get("at") == "meta" and "no search record" in w["problem"] for w in warnings),
          "search record: absence is flagged")

    for label, entries, expect in [
        ("confirming-only is flagged", [{"q": "a query that confirms", "for": "confirm"}], True),
        ("a disconfirming search clears it",
         [{"q": "a query that confirms", "for": "confirm"},
          {"q": "a query that would undermine it", "for": "contradict"}], False),
    ]:
        variant = dict(answer, meta={**answer.get("meta", {}), "searches": entries})
        vpath = tmp / f"searches-{len(entries)}.json"
        vpath.write_text(json.dumps(variant))
        _, rep, verr = run("verify.py", str(vpath), "--corpus", str(corpus))
        if rep is None:
            check(False, f"search record: {label}", verr[-200:])
            continue
        flagged = any(w.get("at") == "meta" and "none marked" in w["problem"]
                      for w in rep["warning_details"])
        check(flagged is expect, f"search record: {label}",
              f"warning {'missing' if expect else 'raised'}")

    code, _, _ = run("render.py", str(work.with_suffix(".verified.json")),
                     "--corpus", str(corpus), "-o", str(tmp / "adv-report"))
    check(code != 0, "render refuses an answer with failed citations", f"exit={code}")


# ------------------------------------------------------------------ phase 2

CASES = [
    # name,      source dir,          answer,                       corpus,  citations
    ("orion", EX / "orion-contracts", EX / "orion-termination.json", None, 12),
    ("fleet", EX / "fleet",        EX / "fleet-diligence.json",   "fleet", 407),
]


def phase_integration(tmp: Path) -> None:
    print("\nintegration — the committed matters, end to end")
    for name, src, answer, _, expected in CASES:
        corpus = tmp / name
        code, out, err = run("ingest.py", str(src), "--corpus", str(corpus))
        if not check(code == 0 and out, f"{name}: ingests", err[-300:]):
            continue
        if name == "orion":
            check(out["ocr_documents"] == 1, "orion: the scanned counterpart is OCR'd",
                  f"ocr_documents={out['ocr_documents']}")
        check(not out["warnings"], f"{name}: ingests without warnings", str(out["warnings"])[:200])

        work = tmp / f"{name}.json"
        work.write_text(answer.read_text())
        code, report, err = run("verify.py", str(work), "--corpus", str(corpus))
        if not check(code == 0 and report, f"{name}: verifies clean", err[-300:]):
            continue
        check(report["failed"] == 0, f"{name}: no failed citations", f"failed={report['failed']}")
        check(report["verified"] == expected, f"{name}: {expected} citations verified",
              f"got {report['verified']}")

        out_dir = tmp / f"{name}-report"
        code, rendered, err = run("render.py", str(work.with_suffix(".verified.json")),
                                  "--corpus", str(corpus), "-o", str(out_dir))
        if not check(code == 0 and rendered, f"{name}: renders", err[-300:]):
            continue
        check_js(out_dir / "index.html", f"{name}: report JavaScript parses")


def phase_scans(tmp: Path) -> None:
    """Scanned pages are detected page by page. Two fixtures: five scans behind a
    typed cover sheet (should be treated as a scan), and a typed report with two
    image-only exhibits (shouldn't be, but ingest should warn about those pages)."""
    print("\nscans \u2014 per-page detection of image-only pages")
    corpus = tmp / "mixed"
    code, out, err = run("ingest.py", str(FIX / "corpus-mixed"), "--corpus", str(corpus), "--ocr", "off")
    if not check(code == 0 and out is not None, "mixed fixtures ingest", err[-300:]):
        return
    w = "\n".join(out["warnings"])
    check("exhibits-with-cover.pdf: no text layer" in w,
          "cover sheet over five scans is still a scan", w[:200])
    check("report-with-two-scans.pdf: 2 of 10 pages have no text layer" in w,
          "two image pages in a typed report are reported, not OCR'd", w[:200])


def phase_hybrid(tmp: Path) -> None:
    """A corpus that mixes files on disk with documents captured from the web. This
    is the usual setup: one index and one answer citing both kinds. The web document
    has to keep its provenance through verify and into the rendered page."""
    print("\nhybrid \u2014 local files and a captured web document in one corpus")
    corpus = tmp / "hybrid"
    code, out, err = run("ingest.py", str(FIX / "corpus-hybrid"), "--corpus", str(corpus))
    if not check(code == 0 and out is not None, "hybrid corpus ingests", err[-300:]):
        return
    check(out["documents"] == 2, "sidecar is metadata, not a third document", f"documents={out['documents']}")
    check(out["web_documents"] == 1, "the captured document is recognised as web-sourced",
          f"web_documents={out['web_documents']}")
    work = tmp / "hybrid-answer.json"
    work.write_text((FIX / "hybrid-answer.json").read_text())
    code, rep, err = run("verify.py", str(work), "--corpus", str(corpus))
    if not check(code == 0 and rep, "answer citing both kinds verifies clean", err[-300:]):
        return
    check(rep["verified"] == 2 and rep["failed"] == 0, "both citations located",
          f"verified={rep['verified']} failed={rep['failed']}")
    out_dir = tmp / "hybrid-report"
    code, rendered, err = run("render.py", str(work.with_suffix(".verified.json")),
                              "--corpus", str(corpus), "-o", str(out_dir))
    if not check(code == 0 and rendered, "hybrid report renders", err[-300:]):
        return
    html = (out_dir / "index.html").read_text()
    check(rendered.get("documents_listed") == 2, "Sources tab lists every document in the corpus, cited or not",
          f"listed={rendered.get('documents_listed')}")
    check("law.cornell.edu/uscode/text/26/152" in html and "2026-09-20" in html,
          "web provenance (URL and retrieval date) reaches the page")
    check("engagement-letter.md" in html, "the local file reaches the page by filename")

    # a regulation page that opens with its section heading gets that as its title,
    # instead of the file name (eCFR pages end the heading with a full stop)
    sys.path.insert(0, str(CS))
    from ingest import title_for  # noqa: E402
    got = title_for(Path("title-29-0a237027.html"), ["\u00a7 825.114 Inpatient care.\n\nInpatient care means an overnight stay."])
    check(got == "\u00a7 825.114 Inpatient care", "a section heading is used as the title", f"got {got!r}")


def phase_registry(tmp: Path) -> None:
    print("\nregistry — concurrent sessions must not lose each other's corpora")
    import importlib, os
    os.environ["CITATIONS_REGISTRY"] = str(tmp / "registry" / "corpora.json")
    sys.path.insert(0, str(CS))
    import _common
    importlib.reload(_common)
    try:
        # session A loads the empty registry, session B saves an entry, then A saves its stale copy
        stale = _common.load_registry()
        _common.save_registry({"corpora": {"b-corpus": {"path": str(tmp / "b")}}})
        stale["corpora"]["a-corpus"] = {"path": str(tmp / "a")}
        _common.save_registry(stale)
        now = _common.load_registry()["corpora"]
        check("a-corpus" in now and "b-corpus" in now,
              "a stale save merges instead of deleting another session's entry", str(sorted(now)))
        check(_common.forget_registry("b-corpus") and "b-corpus" not in _common.load_registry()["corpora"],
              "forget removes exactly the named entry")
        try:
            _common.corpus_root("no-such-corpus")
            check(False, "an unregistered bare name fails loudly instead of becoming ./name")
        except SystemExit as e:
            check("no corpus named" in str(e), "an unregistered bare name fails loudly instead of becoming ./name", str(e)[:120])
    finally:
        del os.environ["CITATIONS_REGISTRY"]
        importlib.reload(_common)


def phase_evals() -> None:
    """The public eval set should load and score. By my own rule it contains none
    of the questions I used while building the skill."""
    print("\nevals \u2014 the public question set")
    evals = SKILL.parent.parent.parent / "evals"
    qfile = evals / "questions.json"
    if not qfile.exists():
        record(SKIP, "evals: no question set present")
        return
    qs = json.loads(qfile.read_text())["questions"]
    check(len(qs) >= 24, f"evals: at least two dozen questions ({len(qs)})")
    check(all(q.get("source_url") and q.get("retrieved") for q in qs),
          "evals: every question records its public source and pull date")

    r = subprocess.run([sys.executable, str(evals / "run.py"), "list"], capture_output=True, text=True)
    check(r.returncode == 0 and f"{len(qs)} questions" in r.stdout, "evals: harness lists the set")
    tmp_out = Path(tempfile.mkdtemp(prefix="evals-")) / "RESULTS.md"
    r = subprocess.run([sys.executable, str(evals / "run.py"), "score", "--out", str(tmp_out)],
                       capture_output=True, text=True)
    check(r.returncode in (0, 1) and tmp_out.exists(), "evals: harness scores without touching the committed scorecard",
          r.stderr[-200:])
    check((evals / "RESULTS.md").exists(), "evals: committed RESULTS.md is present")


def check_js(page: Path, name: str) -> None:
    if not shutil.which("node"):
        record(SKIP, name, "node not installed")
        return
    html = page.read_text()
    try:
        js = html.split("<script>\n(function(){", 1)[1].rsplit("})();\n</script>", 1)[0]
    except IndexError:
        check(False, name, "could not locate the page script")
        return
    tmp = page.parent / "_check.js"
    tmp.write_text("(function(){" + js + "})")
    r = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
    check(r.returncode == 0, name, r.stderr[:200])
    tmp.unlink(missing_ok=True)


# ------------------------------------------------------------------ phase 3

PRIV = SKILL.parent.parent.parent / "private" / "examples"
# The list of private answers to re-check, and how many citations each should verify,
# lives in private/examples/web-checks.json. I keep the names out of this file because
# they describe private questions. Without that file the phase skips, as it will on any
# other machine.
WEB_CHECKS = PRIV / "web-checks.json"


def phase_web() -> None:
    print("\nweb — captured corpora, if they are on this machine")
    sys.path.insert(0, str(CS))
    from _common import load_registry  # noqa: E402

    registered = load_registry()["corpora"]
    if not WEB_CHECKS.exists():
        record(SKIP, "no private web checks on this machine")
        return
    checks = json.loads(WEB_CHECKS.read_text()).get("checks", [])
    for item in checks:
        name, answer, expected = item["corpus"], PRIV / item["answer"], item["citations"]
        if not answer.exists():
            record(SKIP, f"{name}: private answer not present on this machine")
            continue
        if name not in registered or not Path(registered[name]["path"], "index.json").exists():
            record(SKIP, f"{name}: not registered here")
            continue
        code, report, err = run("verify.py", str(answer), "--corpus", name)
        if not check(code == 0 and report, f"{name}: verifies clean", err[-300:]):
            continue
        check(report["verified"] == expected, f"{name}: {expected} citations verified",
              f"got {report['verified']}")


# ---------------------------------------------------------------------- main

def phase_followup(tmp: Path) -> None:
    print("\nfollow-up — a second question lands in the same report")
    corpus = tmp / "followup"
    code, _, err = run("ingest.py", str(FIX / "corpus"), "--corpus", str(corpus))
    if not check(code == 0, "fixture corpus ingests for the follow-up test", err[-200:]):
        return
    work = tmp / "fu"
    work.mkdir()
    answer = work / "answer.json"
    q1 = {"type": "claim", "text": "Either party can end the agreement on sixty days' notice.",
          "cites": [{"doc": "notice-provisions",
                     "quote": "Either party may terminate this Agreement for convenience upon sixty (60) days' prior written notice to the other party."}]}
    first = {"question": "What notice ends the agreement?", "summary": "Sixty days' notice, from either party.",
             "meta": {"title": "Ending the agreement", "report_id": "notice-test",
                      "searches": [{"q": "terminate for convenience", "for": "confirm"},
                                   {"q": "may not terminate", "for": "contradict"}]},
             "blocks": [q1], "gaps": []}
    answer.write_text(json.dumps(first))
    code, _, err = run("verify.py", str(answer), "--corpus", str(corpus))
    code, out, err = run("render.py", str(answer.with_suffix(".verified.json")), "--corpus", str(corpus),
                         "-o", str(work / "report"))
    if not check(code == 0 and out, "first question renders", err[-300:]):
        return
    check(out.get("report") == "notice-test", "the report takes the name the answer gave it", f"got {out.get('report')}")
    check(out.get("follow_up", "").startswith("/use-citations follow-up notice-test"),
          "the render output gives the follow-up command")

    url = "https://claude.ai/artifact/TESTfollowup123"
    code, _, err = run("report.py", "record", str(work / "report"), "--url", url)
    check(code == 0, "the published link is recorded against the report", err[-200:])
    for ref in ("notice-test", url):
        code, found, err = run("report.py", "find", ref)
        check(code == 0 and found and found.get("answer") == str(answer.resolve()),
              f"the report is found by {'name' if ref == 'notice-test' else 'link'}", err[-200:])
    code, found, _ = run("report.py", "find", "no-such-report")
    check(code == 1 and found and found.get("candidates") is not None,
          "an unknown name fails and lists the reports that do exist")

    # the follow-up: the first question moves into "turns" and the second is appended
    q2 = {"type": "claim", "text": "Ending it early costs half the remaining commitment.",
          "cites": [{"doc": "notice-provisions",
                     "quote": "Customer shall pay an early termination fee equal to fifty percent (50%) of the remaining minimum commitment as of the effective date of termination."}]}
    two = {"meta": {k: v for k, v in first["meta"].items() if k != "searches"},
           "turns": [{"question": first["question"], "summary": first["summary"], "blocks": [q1],
                      "searches": first["meta"]["searches"], "gaps": []},
                     {"question": "And what does ending it early cost?", "summary": "Half the remaining commitment.",
                      "asked": "2026-09-22", "blocks": [q2],
                      "searches": [{"q": "early termination fee", "for": "confirm"}], "gaps": []}]}
    answer.write_text(json.dumps(two))
    code, rep, err = run("verify.py", str(answer), "--corpus", str(corpus))
    if not check(code == 0 and rep, "a two-question answer verifies", err[-300:]):
        return
    ledger = json.loads(answer.with_suffix(".verified.json").read_text())["verification"]["ledger"]
    check([e["at"] for e in ledger] == ["block0", "block1"],
          "citation locations run on across questions", str([e["at"] for e in ledger]))
    check(any(w.get("at") == "turn1" and "none marked" in w["problem"] for w in rep["warning_details"]),
          "a follow-up with no search for contrary evidence is flagged on its own")
    code, out, err = run("render.py", str(answer.with_suffix(".verified.json")), "--corpus", str(corpus),
                         "-o", str(work / "report"))
    if not check(code == 0 and out, "the two-question report renders", err[-300:]):
        return
    check(out.get("report") == "notice-test" and out.get("questions") == 2,
          "the follow-up keeps the report's name", f"{out.get('report')}, {out.get('questions')} questions")
    _, found, _ = run("report.py", "find", "notice-test")
    check(found and found.get("questions") == 2 and found.get("url") == url,
          "the record shows two questions and keeps the link")

    v = json.loads(answer.with_suffix(".verified.json").read_text())
    v["turns"][1]["blocks"][0]["cites"][0]["quote"] += " And more."
    stale = work / "stale.verified.json"
    stale.write_text(json.dumps(v))
    code, _, _ = run("render.py", str(stale), "--corpus", str(corpus), "-o", str(work / "stale"))
    check(code != 0, "a follow-up edited after checking is refused")

    other = tmp / "fu-other"
    other.mkdir()
    (other / "answer.json").write_text(json.dumps(first))
    run("verify.py", str(other / "answer.json"), "--corpus", str(corpus))
    _, out, _ = run("render.py", str(other / "answer.verified.json"), "--corpus", str(corpus), "-o", str(other / "report"))
    check(out and out.get("report") == "notice-test-2", "a second report can't take a name in use",
          f"got {out and out.get('report')}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="citations-tests-") as td:
        tmp = Path(td)
        # render.py records every report it makes; keep test runs out of the real list
        os.environ["CITATIONS_REPORTS"] = str(tmp / "reports.json")
        phase_adversarial(tmp)
        phase_integration(tmp)
        phase_scans(tmp)
        phase_hybrid(tmp)
        phase_registry(tmp)
        phase_followup(tmp)
        phase_evals()
        phase_web()

    passed = sum(1 for s, _, _ in results if s == PASS)
    failed = [r for r in results if r[0] == FAIL]
    skipped = sum(1 for s, _, _ in results if s == SKIP)
    print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped")
    if failed:
        print("\nfailures:")
        for _, name, detail in failed:
            print(f"  ✗ {name}" + (f"\n      {detail}" if detail else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
