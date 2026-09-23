"""Shared helpers: dependency bootstrap, corpus IO, text normalization, quote resolution.

Every script imports this first. Heavy deps (pymupdf, rapidfuzz) are optional and
installed on demand into a project-local venv at .citations/venv.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

CORPUS_DIRNAME = ".citations"
VENV_DIRNAME = "venv"

# --------------------------------------------------------------------------
# dependency bootstrap
# --------------------------------------------------------------------------

def ensure_deps(mods: list[str], packages: list[str], corpus_root: Path) -> None:
    """Make `mods` importable, installing `packages` into a project-local venv.

    Pure-stdlib paths never call this; PDF reading and OCR do. A second call from
    deeper in the pipeline (ingest needs pymupdf, then ocr needs pyobjc) installs
    into the venv we are already running in rather than re-execing again.
    Set CITATIONS_NO_BOOTSTRAP=1 to fail loudly instead of installing.
    """
    missing = [m for m in mods if not _importable(m)]
    if not missing:
        return
    if os.environ.get("CITATIONS_NO_BOOTSTRAP") == "1":
        die(f"missing modules: {', '.join(missing)}\n"
            f"install them yourself, or unset CITATIONS_NO_BOOTSTRAP to auto-install into "
            f"{corpus_root / VENV_DIRNAME}")

    if os.environ.get("CITATIONS_IN_VENV") == "1":
        _pip_install(Path(sys.executable), packages)
        still = [m for m in mods if not _importable(m)]
        if still:
            die(f"installed {' '.join(packages)} but {', '.join(still)} is still missing")
        return

    venv = corpus_root / VENV_DIRNAME
    py = venv / "bin" / "python"
    if not py.exists():
        log(f"creating dependency venv at {venv} (one time)")
        corpus_root.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    _pip_install(py, packages)
    os.execve(str(py), [str(py), *sys.argv], dict(os.environ, CITATIONS_IN_VENV="1"))


def _importable(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def _pip_install(python: Path, packages: list[str]) -> None:
    log(f"installing {' '.join(packages)} (one time)")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *packages],
        check=True)
    importlib.invalidate_caches()


def log(msg: str) -> None:
    print(f"  [citations] {msg}", file=sys.stderr)


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


# --------------------------------------------------------------------------
# normalization
#
# Source PDFs are full of typographic noise that a model will silently rewrite
# when it quotes: curly quotes, en/em dashes, ligatures, soft hyphens, hard line
# wraps. We compare on a normalized projection but always return offsets into the
# ORIGINAL page text, so the drawer highlights exactly what is on the page.
# --------------------------------------------------------------------------

_PUNCT_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "…": "...", "­": "",
}


def normalize_char(ch: str) -> str:
    if ch in _PUNCT_MAP:
        return _PUNCT_MAP[ch]
    if ch.isspace():
        return " "
    return ch


# When a PDF breaks a line inside a word or a hyphenated token, the text would
# normalize to "ques- tion" or "1.448- 2(b)(2)" and never match the quote someone
# would actually write. Em dashes at a line end are punctuation and are left alone.
# A real compound that breaks at its own hyphen ("on-the-\njob") would join to
# "on-thejob", so every hyphen between two letters is dropped on both sides
# (_WORD_HYPHEN below) and "on-the-job", "on-thejob" and "onthejob" compare equal.
# Between letters the hyphen is typography, like curly quotes. Beside a digit it
# is part of the token.
# Soft hyphenation: a word broken across lines between two letters ("ques-\ntion").
# The hyphen belongs to the break and is dropped with it.
_SOFT_WRAP = re.compile(r"(?<=[A-Za-z])[-\u2010\u2011][ \t]*\r?\n[ \t]*(?=[a-z])")
# A hyphen next to a digit or symbol is part of the token and stays. Only the line
# break is removed ("\u00a7 1.448-\n2(c)" -> "\u00a7 1.448-2(c)").
_HARD_WRAP = re.compile(r"(?<=[-\u2010\u2011])[ \t]*\r?\n[ \t]*")
_WORD_HYPHEN = re.compile(r"(?<=[A-Za-z])[-\u2010\u2011](?=[A-Za-z])")
# The Federal Register sets section numbers with an en dash ("\u00a7 1.163\u201316") and
# breaks lines after it. Between two digits the dash is part of the number, so only the
# break is removed. A spaced en dash used as punctuation is left alone.
_NUM_DASH_WRAP = re.compile(r"(?<=\d\u2013)[ \t]*\r?\n[ \t]*(?=\d)")


SUPERSCRIPTS = frozenset("\u00b9\u00b2\u00b3\u2070\u2071\u2074\u2075\u2076\u2077\u2078\u2079"
                           "\u207a\u207b\u207c\u207d\u207e\u207f\u2080\u2081\u2082\u2083"
                           "\u2084\u2085\u2086\u2087\u2088\u2089")


def normalize_map(text: str) -> tuple[str, list[int]]:
    """Return (normalized_text, offset_map) where offset_map[i] is the index in
    `text` that produced normalized_text[i]. Runs of whitespace collapse to one
    space; case is folded; ligatures are decomposed."""
    out: list[str] = []
    omap: list[int] = []
    dewrap = {i for m in _SOFT_WRAP.finditer(text) for i in range(m.start(), m.end())}
    dewrap |= {i for m in _HARD_WRAP.finditer(text) for i in range(m.start(), m.end())}
    dewrap |= {m.start() for m in _WORD_HYPHEN.finditer(text)}
    dewrap |= {i for m in _NUM_DASH_WRAP.finditer(text) for i in range(m.start(), m.end())}
    prev_space = True  # strip leading space
    for i, ch in enumerate(text):
        if i in dewrap:
            continue
        sub = normalize_char(ch)
        if sub == "":
            continue
        if sub == " ":
            if prev_space:
                continue
            out.append(" ")
            omap.append(i)
            prev_space = True
            continue
        prev_space = False
        if sub in SUPERSCRIPTS:        # a footnote marker, not part of the number: $500¹
            continue
        sub = unicodedata.normalize("NFKD", sub)
        sub = "".join(c for c in sub if not unicodedata.combining(c)).lower()
        if not sub:
            continue
        for c in sub:
            out.append(c)
            omap.append(i)
    while out and out[-1] == " ":
        out.pop()
        omap.pop()
    return "".join(out), omap


def normalize(text: str) -> str:
    return normalize_map(text)[0]


# --------------------------------------------------------------------------
# corpus IO
# --------------------------------------------------------------------------

REGISTRY = Path(os.environ.get("CITATIONS_REGISTRY") or (Path.home() / ".claude" / "citations" / "corpora.json"))


def load_registry() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text())
        except json.JSONDecodeError:
            return {"corpora": {}}
    return {"corpora": {}}


def locked_json_update(path: Path, key: str, fn) -> None:
    """Apply fn(current) to the JSON file at path under a lock and write the result
    atomically. fn always sees the file as it is on disk, never a caller's older copy,
    so two sessions writing at once don't drop each other's entries. The lock is
    advisory (fcntl). Where fcntl is missing the write is still atomic, just unlocked."""
    import tempfile
    try:
        import fcntl
    except ImportError:          # Windows: no fcntl; fall through to an unlocked atomic write
        fcntl = None
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    with open(lock, "w") as lf:
        if fcntl:
            fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            try:
                current = json.loads(path.read_text()) if path.exists() else {key: {}}
            except json.JSONDecodeError:
                current = {key: {}}
            current.setdefault(key, {})
            fn(current)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.stem + "-", suffix=".json")
            with os.fdopen(fd, "w") as f:
                json.dump(current, f, indent=1)
            os.replace(tmp, path)
        finally:
            if fcntl:
                fcntl.flock(lf, fcntl.LOCK_UN)


def _registry_update(fn) -> None:
    locked_json_update(REGISTRY, "corpora", fn)


def save_registry(reg: dict) -> None:
    """Merge the caller's entries into the registry. This never removes an entry,
    because a caller holding a copy loaded a minute ago would delete whatever another
    session added since. Use forget_registry() to remove one."""
    _registry_update(lambda cur: cur["corpora"].update(reg.get("corpora", {})))


def forget_registry(name: str) -> bool:
    found = []
    _registry_update(lambda cur: found.append(cur["corpora"].pop(name, None) is not None))
    return bool(found and found[0])


# --------------------------------------------------------------------------
# answers with more than one question
# --------------------------------------------------------------------------

def answer_turns(answer: dict) -> list[dict]:
    """The questions in an answer, in order. A report that has had follow-ups keeps them
    in `turns`; a single-question answer keeps its question, summary, blocks and gaps at
    the top level and is treated as one turn. The block lists returned are the answer's
    own, not copies, so the verifier's in-place annotations land in the file it writes."""
    turns = answer.get("turns")
    if turns:
        return turns
    return [{"question": answer.get("question"), "summary": answer.get("summary"),
             "blocks": answer.setdefault("blocks", []), "gaps": answer.get("gaps", []),
             "searches": (answer.get("meta") or {}).get("searches") or []}]


def flat_blocks(answer: dict) -> list[dict]:
    """Every block across every question, in reading order. Locators such as block12
    index into this list, in the verifier and the report alike."""
    return [b for t in answer_turns(answer) for b in (t.get("blocks") or [])]


class UnknownCorpus(SystemExit):
    pass


def corpus_root(path: str | os.PathLike | None) -> Path:
    """Resolve a --corpus value to a directory.

    Tries, in order: a registered corpus name, a path to a corpus, a path to a
    folder that contains one. With no value, falls back to $CITATIONS_CORPUS and
    then ./.citations. Names exist so a corpus is easy to refer to and to share,
    e.g. `--corpus us-tax` instead of a long path.
    """
    if path is None:
        path = os.environ.get("CITATIONS_CORPUS") or None

    looks_like_name = isinstance(path, str) and path and os.sep not in path and not path.startswith(".")
    if looks_like_name:
        entry = load_registry()["corpora"].get(path)
        if entry:
            return Path(entry["path"]).expanduser().resolve()
        if not Path(path).exists():
            # A bare name that is neither registered nor a directory shouldn't be treated
            # as a relative path, or ingest would quietly create ./<name>/.
            raise UnknownCorpus(f"error: no corpus named {path!r} is registered and no such "
                                f"directory exists — run corpus.py list, or corpus.py new {path} <path>")

    p = Path(path).expanduser() if path else Path.cwd() / CORPUS_DIRNAME
    if p.name != CORPUS_DIRNAME and (p / CORPUS_DIRNAME).exists():
        p = p / CORPUS_DIRNAME
    p = p.resolve()
    if path is None and not os.environ.get("CITATIONS_QUIET"):
        # No --corpus and no $CITATIONS_CORPUS. This is the case where the caller can get
        # a different document set than they meant (say, a stale ./.citations left over
        # from another project), so print which one is being used.
        idx = p / "index.json"
        if idx.exists():
            try:
                docs = json.loads(idx.read_text()).get("docs", [])
                first = (docs[0].get("title") or docs[0].get("filename")) if docs else "empty"
                print(f"note: no --corpus given; using {p} ({len(docs)} documents; first: {first!r})",
                      file=sys.stderr)
            except (json.JSONDecodeError, OSError):
                pass
    return p


def corpus_manifest(root: Path) -> dict:
    f = root / "corpus.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def load_index(root: Path) -> dict:
    f = root / "index.json"
    if not f.exists():
        die(f"no corpus at {root} — run scripts/ingest.py first")
    return json.loads(f.read_text())


_DOC_CACHE: dict[str, dict] = {}


def load_doc(root: Path, doc_id: str) -> dict:
    f = root / "docs" / f"{doc_id}.json"
    if not f.exists():
        die(f"unknown document id: {doc_id}")
    key = str(f)
    if key not in _DOC_CACHE:
        if len(_DOC_CACHE) > 256:          # bound it; a corpus can be thousands of files
            _DOC_CACHE.clear()
        _DOC_CACHE[key] = json.loads(f.read_text())
    return _DOC_CACHE[key]


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1))


def resolve_doc_id(index: dict, ref: str) -> str | None:
    """Accept a doc id, exact title, filename, or unambiguous case-insensitive
    substring of either. Models cite by name far more reliably than by id."""
    docs = index["docs"]
    by_id = {d["id"]: d for d in docs}
    if ref in by_id:
        return ref
    ref_l = ref.strip().lower()
    for key in ("title", "filename"):
        exact = [d for d in docs if d.get(key, "").lower() == ref_l]
        if len(exact) == 1:
            return exact[0]["id"]
    stem = [d for d in docs if Path(d.get("filename", "")).stem.lower() == ref_l]
    if len(stem) == 1:
        return stem[0]["id"]
    partial = [
        d for d in docs
        if ref_l in d.get("title", "").lower() or ref_l in d.get("filename", "").lower()
    ]
    if len(partial) == 1:
        return partial[0]["id"]
    return None


# --------------------------------------------------------------------------
# tokenization (shared by BM25 index and search)
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.\-/']*")

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "at", "by", "is",
    "are", "was", "were", "be", "been", "as", "that", "this", "it", "with", "from",
    "any", "all", "such", "shall", "may", "will", "not", "no", "if", "but", "so",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(normalize(text)) if t not in _STOP and len(t) > 1]
