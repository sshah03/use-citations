# Workflows

Besides answering a plain question, the skill handles five kinds of request. They all end
the same way: verify, render, publish.

## 1. A straight answer

This is the default. Search, write `claim` blocks under `heading`s, verify, render.

Order it the way the reader will use it: the answer first, then the conditions that apply
to it, then what follows from it, and what the documents don't settle at the end. Don't
describe how you searched.

## 2. Extraction grid: one question across many documents

For requests like "Pull the assignment clause from all 80 contracts", "What's the notice
period in each?", "What primary endpoint did each of these 40 trials use?", "Which of our
200 SOPs name a review interval?" or "What revenue-recognition policy does each
subsidiary's manual state?":

```bash
python3 scripts/extract.py --fields fields.json \
  --row-label field:Counterparty --label Counterparty \
  --out worksheet.json --answer grid.json
```

A fields file is a list of columns:

```json
[{"name": "Liability cap",
  "query": "limitation of liability aggregate liability exceeds cap damages",
  "rules": [
    {"match": "aggregate liability[^.]*?twelve \\(12\\) months preceding", "value": "12-month fees"},
    {"match": "have not agreed any aggregate cap", "value": "UNCAPPED"}],
  "absent": "Not addressed"}]
```

`query` ranks each document's pages for that column (by BM25, a standard keyword-matching
score). `rules` are tried against those pages in that order, and the first match wins. That
lets one column tell three cases apart: the document gives a value, the document expressly
excludes it, or the document says nothing. `absent` is what the cell says when nothing
matched.

When you write fields:

- **Write a rule for the "no" case too.** "There's no right to cancel for convenience" and
  "no text matched" look the same in the output unless a rule tells them apart, and they
  mean very different things.
- **Match a short value, quote the whole sentence.** `value` should be just the fact
  ("60 days"). The quote is widened to the surrounding sentence automatically, so anyone
  can check the cell.
- **Name rows from a field** when the documents all have the same title, which a stack of
  contracts, protocols or policies always does. `--row-label field:Counterparty` names each
  row from a value the sweep pulls out, so you don't end up with eighty identical headings.
  Use whatever the reader knows each row by: a trial registration number, a subsidiary's
  name, a procedure code.

Then check the results before you hand them over. Read every cell against its quote, look
at every row the rules didn't match, write the main findings yourself above the grid, and
verify the whole thing. A cell no rule could fill shows `—` and has no citation. Leave it
like that, and mention the missing information in `gaps` or in a finding. With a lot of
documents, what's missing is usually what the user most needs to know: if two contracts
out of eighty have no limitation of liability, those two are the answer.

## 3. Comparing documents, and redlines

For two versions of a document, or two parties' drafts, build a table with `Provision |
Document A | Document B | Effect of the difference`, and cite each side to its own document.
In the last column, say who the difference helps and why. A list of differences on its own
leaves the user to do the actual comparing.

For successive versions of one document, start with the changes that alter what it means.
Changes in wording come after, if at all. A renumbered section isn't worth mentioning, but
a deleted exception is.

## 4. Looking for contradictions

Run the same search across all the documents and look for answers that can't all be true.
Report each conflict as one claim with **both** quotes:

```jsonc
{ "type": "claim",
  "text": "The MSA and SOW No. 3 set different notice periods; the SOW governs itself because it names the section it supersedes.",
  "cites": [ {"doc":"d2","quote":"..."}, {"doc":"d3","quote":"..."}, {"doc":"d2","quote":"In the event of a conflict ..."} ] }
```

Always cite the provision that settles the conflict, as well as the two that cause it. If
nothing settles it, say so. A conflict nobody can resolve is itself worth reporting. Don't
guess which side wins.

## 5. Checking whether something is supported

For requests like "Is this claim, memo, filing or draft supported by the sources?"

For each statement, report the quotes that support it, the quotes that go against it, and
what the documents don't say. Set `confidence` to match what the sources actually show. A
statement that rests only on a recital, a draft, or an unsigned document isn't supported,
so say which of those it rests on.

---

## When sources disagree

Cite the rule that decides between them rather than just picking one.

**Contracts and agreements**

1. **An amendment beats the original.** A clause "deleted in its entirety and replaced"
   is gone. Quote the language that deletes it as well as the new text.
2. **A document that names what it overrides beats a general order-of-precedence
   clause.** Those clauses usually require the lower-ranked document to *name* the part it
   overrides, so check that it does.
3. **The specific beats the general**, and **the later effective date beats the earlier**,
   but only where no precedence clause says otherwise.
4. **Signed beats draft.** An unsigned document shows what someone intended. It doesn't
   show what was agreed.

**Law and tax.** Statute, then regulation, then binding ruling, then less formal agency
guidance, then case law in the relevant jurisdiction, then cases from elsewhere that are
only persuasive, then commentary. Never cite commentary for a point that the statute,
regulation or ruling in the documents already settles, and never present a case from
another jurisdiction as binding.

**Clinical and medical.** The current guideline beats an older edition. A systematic
review or meta-analysis beats a single trial. Randomised trials beat observational studies,
which beat case series, which beat single case reports. Check when each was published and
last revised before relying on it. A retracted or withdrawn paper counts as no evidence at
all, and the retraction is itself worth reporting.

**Research and technical.** Peer-reviewed beats preprint. The published version beats the
author's manuscript. The current standard, RFC or specification beats the one it replaced.
If a preprint is the only source, call it a preprint in the answer.

**Accounting and audit.** The official codification beats interpretive guidance, which
beats a firm's own practice aids, using the version in effect for the period being
reported. A standard that has been issued but isn't in effect yet is different from one
that is, so say which.

**Policies and internal records.** The current revision beats any earlier one, and the
copy held by whoever approves the policy beats a local or cached copy. If two revisions
are both in use, report that as something the organisation needs to know rather than a tie
to break.

Whatever the field, if nothing in the documents settles the conflict, say so. An unsettled
conflict is worth reporting. Don't guess which side wins.

## Delivering it

Publish the report, give the user the link, and answer the question in the chat reply as
well. Someone who asked in a chat window expects the answer there, not only behind a link.
Keep it to the summary: two or three sentences, the same ones that open the report. Then
add one line on what was checked ("30 quotes, all found in the sources") and the single
most important finding, especially one that complicates the answer. Don't paste the whole
report into the chat. The page is where the detail and the citations are.

If the report includes pages from the user's own files, say so in the same reply.

If anything came back `UNVERIFIED` and the user asked to publish anyway, render with
`--allow-unverified` so the failures show in red, and tell the user clearly which
statements aren't supported.
