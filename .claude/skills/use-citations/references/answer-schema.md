# The answer file

The answer is one JSON file. `scripts/verify.py` reads it, resolves every quote to a
real span in a real file, and writes `<name>.verified.json` with the anchors filled in.

```jsonc
{
  "question": "The question as the user asked it.",
  "summary": "The answer in two or three sentences, for a reader who stops there.",
  "meta": {
    "title": "A short headline for the page: 'Age limits for claiming a child as a dependent'.",
    "report_id": "dependent-age-2025",   // short name for follow-ups; no spaces
    "matter": "Optional: the client or project, shown above the title.",
    "short_names": { "d2": "MSA" },  // optional: what the pin-cites say instead of the title
    "document_label": "Answer",        // optional override for the first tab's label.
                                       // Leave it out; the default is right.
    "searches": [                      // how the sources were found (see below)
      {"q": "qualifying child age test student under 24", "for": "confirm"},
      {"q": "age limit exception disabled no age test", "for": "contradict"}
    ],
    "authorities_label": "References"  // optional override for the citation-list heading.
                                       // Leave it out; the default is right.
  },
  "blocks": [ ... ],
  "gaps": [ "What the documents do not establish." ]
}
```

## `meta.title`: always write one

The title is the page heading, and the question goes underneath it. People often type a
paragraph of background before they get to the actual question, and as a headline that
would fill a phone screen before the answer even started. Write a title
of eight words or fewer that says what the page answers, in words the reader would use.
The full question is shown under it, clamped to two lines. Without a title, the page
falls back to the question, or to its first sentence with a question mark.

## `summary`: the answer, as you would say it in chat

Two or three sentences, no more. It's the first thing on the page and it's also what you
say in the chat reply, so it has to make sense on its own. The detail goes in the claims
below it. If the summary is turning into a paragraph, some of it belongs in the claims.

## `turns`: a report with follow-up questions

When a report has had a follow-up, keep each question in `turns`, in the order the user
asked them. The top-level `question`, `summary`, `blocks`, `gaps` and `meta.searches`
move into the first turn. `meta` stays at the top and covers the whole report.

```jsonc
{
  "meta": { "title": "...", "report_id": "dependent-age-2025", "short_names": { ... } },
  "turns": [
    { "question": "Is there an age limit on claiming my child as a dependent?",
      "title": "Age limits", "summary": "...",
      "searches": [ ... ], "blocks": [ ... ], "gaps": [ ... ] },
    { "question": "Does my child have to live with me?", "title": "Living with you",
      "asked": "2026-09-22", "summary": "...",
      "searches": [ ... ], "blocks": [ ... ], "gaps": [ ... ],
      "updates": { "turn": 1, "note": "Question 1 now mentions the residency test." } }
  ]
}
```

- Each turn has the same fields as a single answer, plus `asked` (the date). Add
  `updates` when this question corrected an earlier one. `turn` counts from 1.
- The verifier checks every turn. Each turn needs its own `searches`, including one
  marked `contradict`.
- Locators such as `block12` count the blocks of every turn in order. Citation numbers
  on the page continue across questions.
- An answer without `turns` is a single question, as before.

## `meta.searches`: how you found the sources

The verifier proves each quote is in its source. It can't tell whether you found those
sources by looking for an answer you already had in mind, and an answer you remembered
first and found sources for afterwards passes every other check here.

So the reader gets the list of searches instead. Each entry is `{"q": "...",
"for": "confirm" | "contradict"}`. Add `"where": "web"` to a search you ran to *find*
documents. Without it, the entry means a search of the corpus (the default). Record both
kinds. The web searches show which documents you went looking for, and the searches of the
saved documents show what you asked of them. Include at least one `contradict` entry: a
search for anything that would show the answer is *wrong*. Verification warns if the list
is missing, and again if none of the searches is marked `contradict`.

This lets the reader see how you went about it. It can't prove that the answer came from
the sources rather than from what you already knew.

## Blocks

Blocks render in order. There are four types.

### `claim`: the default, and the only one that asserts anything

```jsonc
{
  "type": "claim",
  "text": "Amendment No. 1 replaced the 60-day notice period with 120 days.",
  "cites": [
    {
      "doc": "d1",                    // id, filename, or title — all resolve
      "quote": "Section 11.1 ... is deleted in its entirety and replaced with the following: ...",
      "anchor": "120 days",           // optional but strongly preferred — see below
      "why": "Optional. Why this passage supports the claim; shown above the highlight.",
      "page": 3                       // optional — omit it and the verifier fills it in
    }
  ],
  "confidence": "high | medium | low",  // optional
  "note": "Optional. What would resolve a medium or low confidence."
}
```

#### How claims are laid out

Claims are sentences, and claims that follow each other run together into one paragraph,
so write them to read like normal prose rather than a list of statements.

- `"break": true` on a claim starts a new paragraph with it. Aim for two to four claims
  per paragraph.
- `"list": "steps"` sets consecutive claims as a numbered list, and `"list": "bullets"`
  sets them as bullets. Use steps for a procedure where the order matters ("how do I
  claim it"). Use bullets for a set of conditions.
- A heading, note or table always ends a paragraph or list.
- `confidence` of `medium` or `low` shows as a small tag after the claim, with `note`
  as its tooltip. `high` shows nothing.

A claim with no `cites` fails verification, and nothing lets you skip that. If a sentence
is just setting things up, make it a `note`. If it's a finding you can't support, delete it.

#### `anchor`: put the citation where it belongs

`anchor` is a **substring of this claim's own `text`**: the exact phrase this source
supports. The report underlines that phrase and puts the citation number right after it,
the way a footnote number follows the words it supports. Without an anchor, the number
goes at the end of the sentence.

```jsonc
{ "type": "claim",
  "text": "SOW No. 3 overrides Section 11.1 for itself alone and sets a 30-day notice period.",
  "cites": [
    { "doc": "d3", "anchor": "sets a 30-day notice period", "quote": "..." },
    { "doc": "d2", "anchor": "overrides Section 11.1 for itself alone", "quote": "..." }
  ] }
```

Rules:
- Anchor the shortest phrase the source actually backs up. Anchoring the whole sentence
  is no better than not anchoring at all.
- It must match the claim text character for character. A mismatch is a warning, and
  the marker falls back to the end of the sentence.
- Overlapping anchors cannot be placed; the second one falls back. Pick phrases that do
  not overlap.
- Leave it out when one source supports the whole sentence.

### `heading`: a section label

```jsonc
{ "type": "heading", "text": "What it costs" }
```

### `note`: framing, transitions, caveats

```jsonc
{ "type": "note", "text": "The MSA's own initial term runs to 1 March 2027." }
```

A note shows in italics and doesn't need a citation. Don't use one to slip a finding past
the verifier without a source.

### `table`: the same question asked of many documents

```jsonc
{
  "type": "table",
  "text": "Which notice period governs what",       // optional heading
  "columns": ["What is being ended", "Notice", "Source of the rule"],
  "rows": [
    [
      { "text": "The MSA as a whole" },
      { "text": "120 days", "cites": [ { "doc": "d1", "quote": "..." } ] },
      { "text": "Amendment No. 1, § 1" }
    ]
  ]
}
```

Each cell is `{ "text": ..., "cites": [...] }`, or a plain string when the cell doesn't
claim anything. Each cell has its own citations, which is what lets a reader check a big
table one cell at a time.

## Writing quotes

- **Cite a document by its id, its title, its filename, or the name you gave it in
  `meta.short_names`.** All four resolve. A short name that two documents share does
  not.
- **Copy them from what `search.py` prints.** Never retype them from memory.
- Whitespace, line breaks and curly quotes are normalized before matching, so a quote
  copied across a PDF's hard line wraps still matches. Words, numbers and punctuation
  are not normalized.
- Use `...` to elide: `"Provider shall refund any prepaid fees ... as of the effective
  date of termination"`. Each fragment must appear in order on the same page, and the
  gap may not exceed 600 characters. An ellipsis joins parts of one passage; it must
  not join two passages. Gaps over 250 characters draw a warning.
- Quote the whole sentence that actually says it. A quote under ~25 characters draws a
  warning, because four words on their own don't prove anything.
- Copy the document's own mistakes. If the signed copy says `"ninety (90) (90)
  days"`, that's the quote. Point out the mistake in the claim.

## Grades the verifier assigns

| Grade | Meaning |
|---|---|
| `exact` | Found verbatim. |
| `elided` | Every `...` fragment found in order on one page. |
| `spanning` | The sentence runs across a page break; anchored on the first page. |
| `fuzzy` | Located at ≥ 0.88 similarity but not verbatim. A warning: replace your wording with the source's. |
| `UNVERIFIED` | Hard failure. Any of these: the quote is not found; the quote states a figure the matched passage does not; a near-match adds or drops a polarity word (*not, unless, shall, may, only, except…*), since "may not terminate" is 0.97 similar to "may terminate" and is a different claim; an ellipsis skips more than 600 characters, which stitches two passages into one quotation; the quote starts or ends inside a word or number ("$1" out of "$1,500"), begins just after a *not*, or gives the source's figures in a different order. |

The verified file adds a `verification` section: the counts, the grades, a `ledger` listing
every citation and exactly where it was found, `problems` and `warning_details`. That's the
record of what was checked. The report's "How it was checked" tab and the audit trail in
its Copy menu are built from it.
