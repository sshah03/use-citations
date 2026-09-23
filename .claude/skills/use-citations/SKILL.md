---
name: use-citations
version: 1.2.0
description: >
  Answer a question from a specific set of documents (contracts, statutes, rulings,
  guidelines, papers, policies, or sources it captures from the web) with every quote
  checked against the source file, and publish a report a reviewer can check. Run only
  when the user types /use-citations.
disable-model-invocation: true
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion, Artifact
metadata:
  last-updated: 2026-09-22
  install-scope: project-only while under test (.claude/skills/use-citations)
  outputs: verified answer JSON, markdown with footnotes, a published review artifact
---

# Grounded Citations

Answer only from the documents in front of you, quote the source exactly, and let a
script (not your own confidence) decide whether each quote is real.

**The rule this skill exists to enforce: every quote you write is checked against the
ingested bytes of the source file before anything reaches the user.** A quote that
cannot be located is treated as a fabricated citation, and the pipeline stops.

## Where the scripts live

Everything lives beside this file, wherever it is installed. That is `~/.claude/skills/use-citations/`
when installed for every project, or `<project>/.claude/skills/use-citations/` when it is
project-scoped:

```
SKILL.md  scripts/  templates/  references/  examples/  tests/
```

Resolve `SK` from wherever this SKILL.md sits; do not assume a working directory. Two
paths are used throughout (shell state may not persist between commands, so repeat them
where needed or use the literal paths):

```bash
SK=~/.claude/skills/use-citations        # or .claude/skills/use-citations in a project
CS=$SK/scripts
```

Run them with plain `python3`. They are stdlib-only except for PDF reading, which
installs PyMuPDF into a project-local venv at `.citations/venv` the first time a PDF
is ingested. No global installs, no network access at answer time.

## Pointing at a corpus

Every script takes `--corpus`, and it accepts a name as readily as a path. **Pass it
on every call.** Without it a script falls back to `$CITATIONS_CORPUS`, then to
`./.citations`. In a project directory that may be a stale corpus from another
matter, which returns real quotes from the wrong documents. The scripts print a note to
stderr when they fall back; read it.

```bash
python3 $CS/corpus.py list                 # what corpora exist, and what is in them
python3 $CS/search.py "ordinary and necessary" --corpus us-tax
```

Before ingesting anything, run `corpus.py list`. If a corpus already covers the
question, use it. Re-ingesting the same authority into a fourth directory makes it
unclear which copy of a document set to trust. When the user names the corpus to use, that
settles it: build there, even if another corpus holds some of the same documents. Make a new corpus for each matter rather than each question:

```bash
python3 $CS/corpus.py new orion-msa \
  --describe "Orion/Northwind contract file" --from ~/Documents/orion/docs --images
python3 $CS/corpus.py add orion-msa ~/Documents/orion/late-arrivals
```

Leave the folder out, as above. The collection then goes in
`~/.claude/citations/collections/<name>`, beside the list of collections. Give a folder
(`corpus.py new <name> <folder>`) only when the user names one. Never invent a new folder
in their home directory or anywhere else.

`$SK/references/corpora.md` is written to be handed to someone else. It explains how to build a
corpus for a practice area and how to tell colleagues to point at it.

## How it is started

Only by the user typing `/use-citations`. The skill never starts on its own, so when it runs,
the user has asked for a checked, cited report: every run ends with one (step 5), however
short the question.

```
/use-citations <question>                              a new report
/use-citations follow-up <question>                    add to this conversation's latest report
/use-citations follow-up <report> <question>           add to a named report
```

Follow-ups are covered under *Follow-up questions* below.

## The pipeline

Most questions arrive with no documents attached. You will build the corpus while
answering about as often as you are handed one, so step 1 has two starting points. Treat
both as normal.

### 1a. Documents you have to go and get

Web search finds documents, but it does not produce citable ones. A search snippet or a
summarized page cannot be quoted verbatim, anchored to an offset, or re-checked later.

**Search to find documents, use `fetch.py` to capture them, then cite the capture.**

```bash
python3 $CS/fetch.py https://www.irs.gov/pub/irs-pdf/p501.pdf --corpus us-tax --images
```

`--images` renders page images for any PDF captured. It does nothing for an HTML page,
so it is safe to pass always.

That stores the raw bytes, records the URL, the final URL after redirects, a UTC
retrieval timestamp, the HTTP status and a sha256, and ingests the result. The report
then shows the archived copy the quote came from, beside a link to the live page and
the date it was taken.

These rules matter most for web sources:

- **Never quote from a search result, a snippet, or the `WebFetch` tool.** WebFetch
  returns processed content rather than the original bytes, so a citation cannot be
  anchored in it. Capture anything you intend to cite.
- **The same goes for MCP tools and connectors** (Drive, Notion, a case-law database). Their
  results are text in your context, not a saved source, and writing them to a file yourself
  and ingesting it would only verify your own transcript. Use a connector to find a
  document. If it can hand back the original file or a public URL, save that with
  `fetch.py` or `ingest.py`. If it can't, say so in `gaps` and ask the user for the file.
- **Capture the whole document, not the part you think you need.** Exceptions often sit
  in the sections you would have skipped.
- **Go to the authority, not the aggregator.** Prefer irs.gov to a tax blog, the court's own
  site to a case summary, and the regulator to the trade press. If only a secondary
  source is available, cite it as a secondary source and say so.
- **Say when the web sources were retrieved**, once, in the summary or an opening
  note: "sources captured from irs.gov on 20 September 2026". The report dates each
  citation individually. The prose only needs to tell the reader that the sources are
  dated captures of pages that may since have changed.
- Report a capture that fails (paywall, 403, JavaScript-only page); do not paper over
  it. Say the document could not be captured and leave the claim uncited or cut.
  Some authorities block plain HTTP clients but publish the same text through a
  machine-readable route: PubMed abstracts via NCBI E-utilities (`efetch ... rettype=abstract&retmode=text`,
  ≤3 requests/s), PMC full text via Europe PMC's REST API, regulations via govinfo or eCFR
  when the agency's own site refuses. These routes serve the authority's own copies, so they are not aggregators.
- **Read the `failed` and `warnings` lists in the fetch output before you quote anything.** A client-side
  rendered page returns HTTP 200 and real bytes while yielding almost no text, so the
  capture looks successful but contains nothing quotable. `fetch.py` flags an
  HTML page that yields under 300 characters at any size (a bot challenge, a captcha),
  or a large one (over 20 KB) yielding under 1,500 characters or under 1% of its bytes.
  It also warns on a non-200 status and on a redirect to a different page (a landing
  page answers with HTTP 200 and looks like a capture). A flag means you should look at
  the document, not discard it: `search.py --show` the document.
  If the text is the complete page (a one-question FAQ, a short statute section), it
  is a source. Cite it and say in `why` that the capture was short. If it is navigation
  chrome, a cookie banner or a loading stub, it is not a source. Find the document elsewhere and
  put the failure in `gaps`. The report marks a flagged document either way.

### 1b. Documents you already have

```bash
python3 $CS/ingest.py ~/Documents/orion --images
```

This splits every document into pages and stores the original text under `./.citations/`.
`--images` also renders PDF pages as PNGs so the report can show the real page.
Re-running is cheap: unchanged files are skipped by hash.

Read the output. **Never cite a document that failed to ingest.**

A PDF with no text layer is OCR'd automatically. macOS Vision needs nothing installed;
`ocrmypdf` or `tesseract` are used instead when present. An OCR'd document always gets
its page images rendered, because for a scan the image is the evidence and the text is
an inference from it. This has two consequences:

- Pages flagged below 0.80 confidence appear in `warnings`. Read any quote from them
  against the page image in the drawer before you rely on it, and say in the claim's
  `why` that the passage came off a scan.
- `--ocr off` leaves scans uncited rather than OCR'ing them. `--ocr force` re-reads a
  PDF whose embedded text layer you distrust. A bad text layer under a scan is worse
  than none, because nothing flags it.

### 2. Search the corpus: read passages, not whole files

```bash
python3 $CS/search.py "termination for convenience" -n 8
python3 $CS/search.py --show d2:7      # one full page (add --plain for text only)
python3 $CS/search.py --list           # what is in the corpus
```

Hits come back as original source text with a doc and page anchor. Copy quotes out
of these hits. Do not retype them from memory, fix the document's typos, or reflow its
words. Collapsing a PDF's line breaks to spaces is fine, because whitespace and
line-wrap hyphenation are normalized before matching; words are not. A quote is
evidence, and evidence is reproduced as found.

Search several ways before concluding something is absent: the term of art, the
plain-language phrase, and the statutory or section number. A question is not answered
until you have searched for what would *contradict* your answer.

For a large corpus, search rather than reading files into context. For a handful of
short documents, `--show` each one in full.

### 3. Draft the answer as JSON

Write `answer.json`. The structure is in `$SK/references/answer-schema.md`, and
`$SK/examples/orion-termination.json` is a complete worked example. The shape:

```json
{"question": "...", "summary": "...",
 "meta": {"searches": [{"q": "termination for convenience", "for": "confirm"},
                       {"q": "may not terminate", "for": "contradict"}]},
 "blocks": [{"type": "claim",
             "text": "SOW No. 3 overrides Section 11.1 and sets a 30-day notice period.",
             "cites": [{"doc": "d3", "anchor": "sets a 30-day notice period",
                        "quote": "Customer may terminate this SOW for convenience upon thirty (30) days' prior written notice",
                        "why": "optional: why this passage settles the point"}]}],
 "gaps": ["..."]}
```

These habits turn a citation into something a reader can check:

**Write it to be read.** Give the page a `meta.title` of eight words or fewer. The
question itself can be a paragraph and must not be the headline. Keep the `summary` to
two or three sentences. Claims flow together as paragraphs, so write them as prose, use
`"break": true` to start a new paragraph, and use `"list": "steps"` for a procedure.
In anything the reader sees (the summary, claims, notes, gaps and the chat reply), call
the collection "the documents" or "the sources", never "the corpus", and say "saved"
rather than "captured" or "ingested". Those are the scripts' words, not the reader's.
Keep the chat reply to the answer and the report: don't pass on the session's own notices,
such as connectors waiting to be signed in, unless the answer needed one of them.
The schema has the details.

**The summary is not verified.** It is the sentence a reader acts on and the only prose
with no citation of its own, so it must not say anything the claims below do not establish.
The verifier warns when it carries a figure that no quote does. Do not put a sentence in it
that came from a search-engine summary rather than a captured document.

**Anchor every citation.** `anchor` is a substring of the claim it sits in: the exact
phrase this source establishes. The report underlines that phrase and puts the marker
straight after it, so a reader sees *which words* are sourced rather than a number at
the end of a paragraph. Anchor the narrowest phrase that the source actually supports.

**One proposition, one citation.** If a sentence needs three sources, split it into three
sentences or give it three anchors. A pile of markers after a long
sentence does not tell the reader which source carries which part.

**Record how you found the sources.** Put every search you ran in `meta.searches` as
`{"q": "...", "for": "confirm" | "contradict"}`. Include web searches that found documents,
tagged `"where": "web"`, and at least one search run to find what would undermine the
answer. Verification warns when the list is missing and warns again
when nothing in it is disconfirming. The list is a disclosure and guarantees nothing. It
shows a reader the shape of your search, and that is the only evidence separating a grounded
answer from a recalled one with real quotes attached.

**Cite by name, skip the page.** `"MSA"` resolves as readily as `"d2"`. If you leave `page`
out, the verifier fills it in, which gives you one fewer number to get wrong.

### 4. Verify (always, no exceptions)

```bash
python3 $CS/verify.py answer.json
```

Exit 0 means every quote was located. Anything else means fix and re-run. The verifier
grades each quote `exact`, `elided` (you used `...`), `spanning` (it crosses a page
break), `fuzzy` (it drifted), or `UNVERIFIED`.

When it reports a problem, fix the answer, never the check:

| It says | You do |
|---|---|
| quote not found | Search for the real language. If it does not exist, delete the claim. |
| quote states 25%, which does not appear in the source | You changed a figure. Take the source's number. |
| not verbatim (similarity 0.9) | Replace your wording with the `source_text` it printed. |
| quote and source differ on *not* — the meaning is changed | You inverted the sentence. There is no fix but the source's own words; if they do not say what you need, the claim is wrong. |
| the source reads “not” immediately before this quote | You started the quote after the negation. Start it one word earlier; the negation is the rule. |
| quote gives the figures in a different order | You swapped two numbers. Copy the sentence again from the `search.py` hit. |
| the ellipsis skips 1,140 characters — two passages, not one quotation | Quote each passage separately, as its own citation. |
| claim has no citation | Cite it, cut it, or retype it as `"type": "note"` if it is framing. |
| figure 2026 appears in no cited quote | Show the arithmetic in the claim, or drop the figure. |
| quote too short to be real evidence | Quote the whole operative sentence. |
| anchor is not a substring of the claim | Copy the phrase out of your own claim text exactly. |
| quote occurs more than once in the document | Quote more of the passage until it is unique. If the document genuinely repeats it, say so in `why` and leave the warning. |
| ellipsis skips N characters | Fine under 250. Above it, check the joined fragments still say what the source says; above 600 it fails as two passages. |

Do not use `--lenient`. It exists for debugging only, never for delivery.

### 5. Render and publish

```bash
python3 $CS/render.py answer.verified.json -o report
```

Then publish with the Artifact tool, using the `publish` block the command prints:

```
Artifact(file_path="report/index.html", files={...}, icon="document")
```

and record the link, so a follow-up can find the report again (the render output prints
this command, with the report's short name):

```bash
python3 $CS/report.py record report --url <artifact link>
```

Give the answer a `meta.report_id` when you first write it: a short name without spaces,
like `dependent-age-2025`. It appears on the page in the follow-up command. Without one,
`render.py` makes one from the title.

The reader gets the answer with each sourced phrase underlined and pin-cited inline,
a hover preview of the quote, and a drawer that opens to the exact page with the
passage highlighted. Below it, the citation list groups every citation by
document. A Sources tab lists the whole corpus, cited or not, so the reader sees what
was captured and what was left out. An Audit
tab lists every quote with its match grade and character offsets. Copy-as-Markdown
exports the answer with real footnotes; Copy audit trail exports the JSON ledger.

**Before you publish, check what the page carries.** The report embeds the text of every
cited page, and page images. For documents from the user's own machine, that means
client material goes to claude.ai. It stays private until the user shares it, but say so in
your reply ("the report includes the cited pages of your three contracts") so the user
can decide whether to share it with that in mind.

Every `/use-citations` run ends with a published report, even for a one-line answer. The
user typed the command to get one. Give the short answer in chat as well (see
`$SK/references/workflows.md`, *Delivering it*), but the chat reply goes with the report
and doesn't replace it. If the Artifact tool isn't available, render the report anyway,
say where the file is, and say that it couldn't be published.

## Follow-up questions

A follow-up adds a question to a report that already exists: same page, same link, same
corpus. It happens only when the user asks for it. Without the word `follow-up`,
`/use-citations` always starts a new report.

```
/use-citations follow-up <question>                  the latest report made in this conversation
/use-citations follow-up <report> <question>         a named report, from any conversation
```

`<report>` is the report's short name (`dependent-age-2025`) or its artifact link. A name has
no spaces, so if the first word after `follow-up` is a known name or a link, it is the
report and the rest is the question; otherwise all of it is the question.

1. **Find the report.** Named: `python3 $CS/report.py find <report>`. Not named: use the
   report you published earlier in this conversation. If there is none, run
   `report.py list` and ask which one with AskUserQuestion. Don't guess. If `find`
   fails, show the user the candidates it lists.
2. **Check it can be continued.** `find` prints the answer file, the corpus path and the
   link. If `answer_exists` or `corpus_exists` is false, say which is missing and stop.
   Rebuilding the corpus somewhere else would give the follow-up different evidence
   from the questions before it.
3. **Add the question.** Read the answer file. If it has no `turns` yet, move its
   `question`, `summary`, `blocks`, `gaps` and `meta.searches` into the first turn. Then
   append a new turn with its own `question` (as asked), `title`, `summary`, `asked`
   (today's date), `blocks`, `gaps` and `searches`. Leave earlier turns as they are, with
   one exception: when the follow-up shows an earlier answer was wrong or incomplete,
   correct that turn's blocks and record it on the new turn as
   `"updates": {"turn": 1, "note": "what changed"}`. The page flags the earlier section.
   The schema has the shape.
4. **Answer it the same way.** Search the report's corpus (`--corpus` with the path from
   `find`), including a search for what would contradict the new answer. Each question
   is held to that standard on its own. If the follow-up needs a document the corpus lacks,
   capture it into that same corpus.
5. **Verify, render and republish to the same link.** Render into the report's own
   directory (the `dir` from `find`). Publish with the Artifact tool: the same file path
   if you published it in this conversation, otherwise `url=<the link from find>`. Then
   run `report.py record <dir> --url <link>`.
6. **Reply** with the new question's summary, the link, and that it was added as
   question N of the report.

## How to be worth trusting

**Only the corpus counts.** You know a great deal about contract law, the tax code, and
medicine. None of it may enter the answer as a finding. If the documents do not address
something, that goes in `gaps`. A well-drawn gap list is often the most useful
part of the work, because it tells the reader what they still need to find.

**Prior knowledge is a way to find documents. It is never a way to reach conclusions.**
You will often recognise a question and know roughly where the answer lives. You may use
that to decide what to *search for*. Do not let it decide what the answer *is*: that is
the one failure this pipeline cannot catch. The verifier proves that every quote is real.
It does not prove that the answer came from the documents, so an answer assembled from
memory and then decorated with real quotes passes every check here.

Three habits keep the two apart:

- **Search for what would contradict you, not only for what you expect to find.** If you
  went looking for a document by name and found it, you have confirmed what you already
  believed without testing it. Run the opposite query before you write.
- **Capture the source that complicates the answer**, not only the ones that support it.
  A corpus that holds only supporting documents is one-sided, and the report's Sources
  tab shows a reader exactly which documents you chose to capture.
- **Write after reading, in the documents' own order of emphasis.** A summary you could
  have written before the first capture did not come from the documents.

The remaining risk is a stale prior: you remember something that used to be true, your
search is shaped by it, and you find an older document that confirms it. Every quote
verifies and the answer is still wrong. If you recognised the question up front, say so
in the claim's `why` or in `gaps`. "The ruling was located by searching for it by name"
is information a reader needs to weigh the answer.

**Never fill a hole with a plausible sentence.** "The agreement is silent on assignment"
is a finding. An invented assignment clause is a fabrication.

**Quote the operative language.** Quote the sentence that does the work, rather than the
recital that gestures at it or three words lifted from the middle of it. A reader should
be able to act on the quote alone.

**Reconcile before you report.** Sources in a set often disagree. Say which one
governs and why, and cite the thing that makes it govern. Every field has an order of
precedence, and applying the wrong one produces an answer that is properly cited and
still wrong:

- **Contracts**: an amendment that deletes and replaces beats the original; a named
  supersession beats a general precedence clause; executed beats draft.
- **Law and tax**: statute over regulation over binding ruling over sub-regulatory
  guidance over case law in the governing jurisdiction over persuasive authority over
  commentary. Never cite commentary for a point the primary source in the corpus settles.
- **Clinical**: the current guideline over a superseded edition; systematic review or
  meta-analysis over a single trial; randomised over observational over case series.
  A retracted or withdrawn paper is not evidence, and saying so is a finding.
- **Research and technical**: peer-reviewed over preprint, published version over
  author manuscript, the current standard or RFC over the one it obsoletes.
- **Accounting and audit**: authoritative codification over interpretive guidance over
  practice aids, at the version effective for the period being reported.
- **Policy and internal records**: the current revision over any earlier one, and the
  approving authority's copy over a local one.

Where two sources conflict and nothing in the corpus resolves it, say that. Report an
unresolved conflict as a finding; do not guess which side wins.
`$SK/references/workflows.md` has the patterns.

**Mark what you computed.** Arithmetic and date math are your own work, not the document's. Put
the inputs in quotes and flag the derivation in the claim's `why`.

**Record uncertainty in the confidence field.** Set `"confidence": "medium"` with a `note`
saying what would settle it, instead of hedging in the prose.

## Many documents, one question: the extraction grid

Reading eighty contracts into context to answer "what is the notice period in each" is
too expensive and too unreliable. `extract.py` does the sweep instead. It builds one row
per document and one column per data point, and every populated cell carries the
sentence it was read from:

```bash
python3 $CS/extract.py --fields fields.json \
  --row-label field:Counterparty --label Counterparty \
  --out worksheet.json --answer grid.json
```

A field is a column: a `query` that ranks pages by relevance, and ordered `rules` tried
against those pages until one matches. Rules let a column tell a value, an express
exclusion and silence apart. That distinction matters because in a portfolio review the
key finding is usually an absence: the sixteen agreements with no liability cap, rather
than the sixty-four with one. `$SK/examples/fields-diligence.json`
is a working six-column set.

**The worksheet is a proposal.** A rule matches a pattern; it does not read the document.
Before the grid becomes a deliverable:

1. Read every cell against its own quote. A rule that fires on the wrong sentence
   produces a confident wrong cell with a real quote attached.
2. Check the rows a rule did *not* match. Each is either real silence (a finding)
   or drafting your rule did not anticipate. Widen the rule, or read those documents.
3. Write the narrative findings above the grid yourself, with their own citations. The
   grid is the working record and does not contain the three sentences a partner acts on.
4. Run `verify.py` over the whole thing. Each cell's quote is checked like any other.

Drop the finished `table` block into an answer alongside your prose blocks, and render
as usual. Where a document says nothing, the cell reads `—` and carries no citation;
never invent one to fill a hole in the grid.

## When the user asks something else
- **Compare two documents** → a table of differences, each side cited to its own source.
- **Find contradictions across the set** → claims that pair the conflicting quotes.
- **"Is this claim supported?"** → verify it against the corpus and report which quotes
  support it, which cut against it, and what is simply absent.

## Cheap mistakes to avoid

- Ingesting into the wrong corpus, or building a fourth copy of one that exists.
  Run `corpus.py list` first.
- Citing a web page you read but never captured. If it is not in the corpus, the
  verifier cannot check it, and neither can anyone else.
- Trusting an extraction rule because it matched. A match means the pattern fired, not
  that the meaning is right.
- Treating an empty grid cell as "no risk". It means the sweep found nothing, which is
  either a finding or a gap in your rule, and you have to say which.
- Reading a 400-page PDF into context when `search.py` would have found the clause.
- Citing the same page for six different claims. That usually means one claim split
  into six, or five claims that the page does not actually support.
- Rendering before verifying, or editing the answer after verifying. The renderer refuses
  both, which costs you the round trip.
