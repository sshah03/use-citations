# How it works

This is the detail behind the [README](../README.md): what the checker looks for, where
the documents come from, the scripts, a worked example and the tests. You don't need any
of it to use the skill. It's here if you want to know what's going on, or to change it.

## The steps

```
documents ──▶ ingest.py ──▶ corpus (pages, offsets, page images)
                                │
question ──▶ search.py ─────────┤  passages as written, tagged doc:page
                                ▼
                 Claude writes answer.json: claims, each with quote + anchor
                                │
                          verify.py  ◀── exits 1 if any quote isn't in the source
                                │
                          render.py ──▶ report/index.html ──▶ published report
```

First the skill reads your documents and splits them into pages it can search (the
scripts call this saved set a *corpus*). Claude searches it and writes its answer as a
file, where every statement comes with the exact passage it relies on. Then the checker
looks for each passage in the document. Only if they're all found does the report get
built.

Each citation has three parts: which document, the passage copied word for word, and an
*anchor*, which is the phrase in Claude's sentence that the passage supports. The report
underlines that phrase and puts the citation number right after it.

## What the checker looks for

Claude doesn't get to decide whether a quote is real. The checker, `verify.py`, searches
the document for it word for word and stops the answer if it isn't there. It's
deliberately strict about the kinds of mistakes that change what a document says:

- **A changed number.** The contract says 50% and the quote says 25%.
- **Two numbers swapped.** "Deliver in 30 days, pay in 60" quoted as "deliver in 60, pay
  in 30".
- **A number cut short.** "$1" taken from "$1,500".
- **The meaning flipped.** "May not" quoted as "may", "less than" as "more than", or a
  quote that starts just after the word "not" so the "not" is lost.
- **A word found inside another word.** "not" matched inside "notice".
- **Two passages joined.** Separate sentences stitched together with "..." so they read
  as one.
- **A statement with no source.** Any claim without a citation.

It lets through differences that don't change the meaning: line breaks, straight or curly
quotation marks, letters PDFs sometimes join together (like "fi"), footnote markers, and
words or section numbers split across two lines.

Each quote gets a grade: `exact`, `elided` (it uses "..." inside one passage), `spanning`
(it runs across a page break), `fuzzy` (close but not word for word, so it's flagged), or
`UNVERIFIED` (not found, so the answer fails). The report won't be built if any quote
failed, if any statement has no citation, or if the answer was changed after it was
checked.

### What it can't catch

- **Whether a sentence fairly sums up its passage.** The answer is in plain English, and
  the checker only proves that the passage behind each citation is real. You still have
  to judge whether the sentence says the same thing, which is why every citation opens
  its passage.
- **Whether the answer really came from the documents.** Claude could know the answer
  already and then find quotes that back it up, and every check would pass. So each
  answer keeps a list of the searches Claude ran, including at least one where it looked
  for evidence that the answer is wrong, and the report shows that list. In testing, that
  search more than once found a document the first searches had missed, and it changed
  the answer.

## Where the documents come from

- **Your own files.** PDF, Word, web pages saved as HTML, Markdown, RTF and plain text.
  Files it has already read are skipped the next time.
- **The web.** Claude never quotes a search result or a summary of a page. `fetch.py`
  downloads the actual page or PDF from the official site and records its address, when
  it was saved, and a fingerprint of the file, so you can tell later if it changed. The
  report shows the date it was saved next to a link to the live page. It can't yet save
  pages that need a login or only load in a full browser, and it tells you when that
  happens. It also warns you about pages that download fine but turn out to be almost
  empty.
- **Scans.** If a PDF is just images of pages, the skill reads the text with OCR (text
  recognition, built into macOS). Quotes from a scan are marked as such, and a picture of
  the page is included so you can check the text against it.
- **Saved collections.** You can save a set of documents under a name, such as `us-tax`,
  and ask about it again later. [`references/corpora.md`](../.claude/skills/use-citations/references/corpora.md)
  explains how to set one up and share it.

## One question across many documents

"What's the notice period in each of these 80 contracts?" `extract.py` builds a table with
a row for each document and a column for each question, and every filled-in cell comes
with the sentence it was taken from. It can tell a contract that *says* there's no limit
apart from one that just doesn't mention a limit. The example that comes with it handles
80 contracts and six questions in under a second. Those contracts were made from
templates, though, so all this shows is that it can cope with the number of documents. It
doesn't show that its patterns will work on contracts written by different people.

## The scripts

`$CS` is short for `.claude/skills/use-citations/scripts`.

```bash
python3 $CS/ingest.py ~/Documents/orion-contracts --images   # read a folder
python3 $CS/fetch.py <url> --corpus us-tax               # save a web source
python3 $CS/corpus.py new us-tax                        # name a collection
python3 $CS/search.py "termination for convenience"      # search it
python3 $CS/verify.py answer.json                        # check every quote
python3 $CS/render.py answer.verified.json -o report     # build the report
python3 $CS/report.py find dependent-age-2025           # find a report for a follow-up
python3 $CS/extract.py --fields fields.json --out worksheet.json --answer grid.json
```

The format of the answer file is described in
[`references/answer-schema.md`](../.claude/skills/use-citations/references/answer-schema.md),
and the instructions Claude follows are in
[`SKILL.md`](../.claude/skills/use-citations/SKILL.md).

## A worked example

`examples/orion-contracts/` is a made-up set of contracts. The main agreement gives 60 days'
notice to cancel, an amendment changes that to 120 days, and a statement of work sets 30
days for itself. The fourth document is a scanned signature page, which shows the
amendment was actually signed.

```bash
CS=.claude/skills/use-citations/scripts
EX=.claude/skills/use-citations/examples
python3 $CS/ingest.py $EX/orion-contracts --images
python3 $CS/verify.py $EX/orion-termination.json
python3 $CS/render.py $EX/orion-termination.verified.json -o report
open report/index.html
```

## Tests

```bash
python3 .claude/skills/use-citations/tests/run.py [-v]
```

They don't need an internet connection. The main group gives the checker an answer with
29 deliberate mistakes and tricky cases, and makes sure every bad quote fails and every
harmless difference gets through. The rest run the examples from start to finish
(including a scanned page), check that scans are spotted, mix your own files with saved
web pages, make sure two sessions can't overwrite each other's collections, test
follow-up questions, and check the public test questions.

## Testing it against real questions

I tested it on 34 public questions that come with official answers, from the FAQ pages of
the IRS, the Copyright Office, the CFPB, the Department of Labor, the EEOC and the FDA,
plus a medical research dataset called PubMedQA. Across all 34, the answers cited 372
passages, and every one was found in its source. Three answers only partly matched the
official answer, and the scorecard explains why. The results are in
[`evals/RESULTS.md`](../evals/RESULTS.md), and [`evals/README.md`](../evals/README.md)
explains how I ran them and how you can run them yourself.

## Where things are

```
.claude/skills/use-citations/
  SKILL.md                     the instructions Claude follows
  scripts/                     ingest, ocr, fetch, corpus, search, extract,
                               verify, render, report
  templates/report.html        the report page
  references/                  answer format, workflows, sharing collections
  tests/                       the test suite and its fixtures
  examples/                    a made-up set of contracts, and 80 more for the table tool
evals/                         public test questions, the scorer, results
docs/                          this file
```
