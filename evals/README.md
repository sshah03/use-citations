# Evals

This folder is how I test the skill on real questions. It has a public set of questions
and a script that scores the skill's answers to them. The script doesn't judge how well an
answer is written. For each question it checks the things the skill promises:

- every quote is really in its source
- the answer is based on the law, regulation, agency guidance or study itself, and not on
  someone else's summary of it
- Claude searched for evidence that the answer might be wrong
- the answer agrees with the official answer, where the source gives one

## The questions

`questions.json` has 34 questions. Each one is copied word for word from a public website
that also publishes its own answer, so you can compare the skill's answer with the
official one.

| area | where the questions come from | how many |
|---|---|---:|
| health-research | PubMedQA (`pqa_labeled`), questions with yes/no/maybe answers | 6 |
| health-regulation | FDA, *Generic Drugs: Questions & Answers* | 4 |
| tax | IRS Frequently Asked Questions | 7 |
| law-ip | U.S. Copyright Office FAQ | 5 |
| law-employment | Department of Labor Wage and Hour FAQ; EEOC FAQ | 8 |
| consumer-finance | Ask CFPB | 4 |

PubMedQA is a public dataset from medical research. Each question comes with the summary
of a published study, and researchers have marked the answer as yes, no or maybe.

For every question, `questions.json` records the web page it came from and the date I
copied it. None of the questions I asked while building the skill are in this set. I'm
keeping those private. A few websites wouldn't load when I collected the questions (USPTO,
HHS's HIPAA pages, US Courts, the SEC and the Social Security Administration), so there's
nothing yet on patents, health privacy, federal court procedure or securities.

## What's in a run

A run is the skill's answer to one question. My runs aren't in the repo, only the scorecard
they produced ([`RESULTS.md`](RESULTS.md)), so to check the results you make your own (see
below). Each run has its own folder:

```
evals/runs/<id>/
  answer.json        what the skill produced
  judgment.json      {"agrees_with_reference": "yes|partial|no", "notes": "..."}   (manual)
  .citations/        the corpus, registered as eval-<id>
```

The `.citations` folder holds the documents saved for that question (the scripts call this
a corpus), and the skill can only quote from those. Each one also includes the FAQ page
the question came from. The answer isn't supposed to cite that page. It's there so the
scorer can catch an answer that just repeats the FAQ instead of going to the real source.

## Runs by a fresh copy of Claude

Ten of the runs (`ip-infringed`, `eeoc-confidential`, `pm-aneurysm-80`, `tax-address`,
`tax-1040x-efile`, `tax-lost-refund`, `tax-w2-vs-1099`, `emp-pay-stubs`, `fda-expiration`,
`fda-generic-side-effects`) were done by a fresh Claude that had never seen the skill or
the conversations I built it in. It got only the question, the name of the document
collection and where to save the answer, and was told to use `/use-citations`. All ten
answers passed the checker, eight of them first time. Each one also told me what it found
confusing in the instructions, and I used that to improve SKILL.md and the scripts. These
runs are marked `cold_start` in my results.

## Running the evals yourself

You'll need the skill installed (see the main [README](../README.md)). Then, for each
question you want to check:

1. Start Claude Code in this repo's folder by typing `claude` in the Terminal.
2. Ask the question with `/use-citations`, and tell Claude where to keep things. For
   example: `/use-citations Is there an age limit on claiming my child as a dependent?
   Build the document collection in evals/runs/tax-dependent-age/.citations and save the
   answer as evals/runs/tax-dependent-age/answer.json.` The question text and its id are
   in `questions.json`.
3. Compare the answer with the official one (also in `questions.json`), and write what you
   think in `evals/runs/<id>/judgment.json`, like this:
   `{"agrees_with_reference": "yes", "notes": "..."}`. Use `yes`, `partial` or `no`.
4. Score everything you've run:

```
python3 evals/run.py score
```

That rewrites `RESULTS.md` with your results. Your answers won't match mine word for word,
since Claude writes each one fresh and websites change, but the checks are the same: every
quote found, a search for evidence against the answer, no answer that just repeats the FAQ
page, and agreement with the official answer.

If you have a run's `sources.json` (the list of web addresses and file fingerprints behind
it), `python3 evals/run.py rebuild <id>` downloads those documents again so you can
re-check that answer instead of making a new one.

## What gets scored

```
python3 evals/run.py list          # the set, with run status
python3 evals/run.py score         # score every run present -> RESULTS.md, results.json
```

For each run, the scorer works these out on its own:

- **verified / failed / warnings**: how many quotes the checker found in the saved
  documents, how many it didn't, and anything it flagged for a person to look at.
- **disconfirming**: whether Claude recorded at least one search for evidence against its
  own answer (a search marked `contradict`).
- **circular**: whether every citation points at the FAQ page the question came from. If
  so, the answer has just repeated the page it was supposed to check.
- **low-yield cited**: whether a citation relies on a saved page that turned out to be
  almost empty. This is reported but doesn't fail the run. Some real FAQ pages only have
  one short question on them, so the skill now tells Claude to read a flagged page before
  deciding whether to use it.
- how many documents were saved compared with how many were cited, and how many open
  questions the answer lists.

One thing I check by hand: whether the answer agrees with what the IRS, the Copyright
Office, the CFPB, the Department of Labor, the EEOC, the FDA or the PubMedQA label says.
I write that in `judgment.json` with a note. The scorer reads my judgment, but it doesn't
make it.

A run **passes** if no quote failed, there was a search for evidence against the answer,
no citation is circular, and the answer doesn't disagree with the official one.

## Results

They're in [`RESULTS.md`](RESULTS.md). Running `score` rebuilds that file and puts
today's date on it, so the summary and table there are always the latest. This page just
explains what they mean.

## What this does and doesn't tell you

It tells you the safety checks work. Apart from my one judgment about whether the answer
agrees with the official one, it doesn't tell you whether an answer is actually *good*:
complete, in a sensible order, with the right caveats. Two answers can both pass while one
is much better than the other.

It also can't tell you whether Claude really got the answer from the documents, or knew it
already and found sources to fit afterwards. The scorer checks that the searches were
written down and that one of them looked for evidence against the answer. That lets you
see how Claude went about it, but it isn't proof.

## Adding a question

Add an entry to `questions.json` with:

- the question, exactly as it's written on the source website
- the source and its web address
- the date you copied it
- what kind of answer you expect
- which law, regulation or study you'd expect a good answer to rely on
- the official answer, if the source gives one

Then run the skill on it, saving the answer in `evals/runs/<id>/`, write your judgment, and
run `score`.
