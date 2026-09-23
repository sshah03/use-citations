# Saving a set of documents to reuse, and sharing it

If you keep asking questions about the same documents, like the tax rules your team works
from or one client's contracts, you can save them as a named collection. Then you can
ask about them from any folder, and a colleague can use the same set by name. The
scripts call a collection a **corpus**, so you'll see that word in the commands.

You don't need to write any code. You'll type a few commands, and each one is shown in
full below.

## Where to type the commands

The commands go into the **Terminal** app. On a Mac, press Cmd+Space, type "Terminal" and
press Return. If you'd rather not, you can paste a command into Claude Code and ask it to
run it for you.

Start in the folder that has the skill in it (the one containing
`.claude/skills/use-citations`). Paste each line and press Return. The first line, the one
starting `CS=`, just saves you typing the long path to the scripts every time. You need to
run it again whenever you open a new Terminal window.

## Make one

```bash
CS=.claude/skills/use-citations/scripts

python3 $CS/corpus.py new us-tax ~/libraries/us-tax \
  --describe "Primary US federal tax authority: statute, regs, published rulings"
```

This creates a collection called `us-tax` in the folder `~/libraries/us-tax`. The skill
keeps its own files in a hidden `.citations` folder inside it. Your documents stay wherever
they are. The skill just keeps a short list of each collection's name and where it lives,
so it can find it again.

The words after `--describe` are a note to yourself and your colleagues about what's in it.

Then add documents. You can add files from your computer, pages from the web, or both:

```bash
python3 $CS/corpus.py add us-tax ~/Downloads/p17.pdf
python3 $CS/corpus.py add us-tax --url https://www.irs.gov/pub/irs-pdf/p501.pdf
python3 $CS/corpus.py add us-tax ~/libraries/us-tax/raw --images
```

The first line adds one file. The second downloads a document from a web address and
saves a copy. The third adds everything in a folder, and `--images` also saves a picture of
each PDF page so the report can show you the real page. Swap in your own files and web
addresses.

To see what you've got:

```bash
python3 $CS/corpus.py list          # all your collections, and how many documents each has
python3 $CS/corpus.py show us-tax   # the documents in one, with web addresses and dates
```

You don't need to type anything after a `#`. That's just a note about what the line does.

## Use it

In Claude Code, name the collection in your question:

```
/use-citations Using the us-tax collection, can I deduct a home office if I'm an employee?
```

If you run the scripts yourself, add `--corpus us-tax` to any of them:

```bash
python3 $CS/search.py "ordinary and necessary business expense" --corpus us-tax
python3 $CS/verify.py answer.json --corpus us-tax
python3 $CS/render.py answer.verified.json --corpus us-tax -o report
```

Or set it once, and it applies until you close that Terminal window:

```bash
export CITATIONS_CORPUS=us-tax
```

## Sharing it with someone

Tell them the name, what's in it, and what isn't. Something like:

> Use the **us-tax** collection. It has the Code sections, regulations and IRS rulings we
> work from, each saved in full with the date we saved it. It doesn't have state law,
> private letter rulings, or anything published after those dates. Ask with
> `/use-citations` and say "using the us-tax collection".

Telling them what isn't in it is the most important bit, because it stops people trusting
an answer about something the collection never covered.

If they don't have the documents on their computer, send them the folder. They can then
set it up with one command, putting the folder they saved it to in place of
`/wherever/they/put/it`:

```bash
python3 $CS/corpus.py new us-tax /wherever/they/put/it --describe "..."
```

## What to put in one

Some collections you keep and add to for years, like the tax rules you rely on. Others are
for a single client or deal, and you can delete them when the work is done. A few examples:

| Name | What's in it | When to update it |
|---|---|---|
| `us-tax` | the Code sections, regulations and IRS rulings you actually use | when new guidance comes out |
| `state-nexus` | each state's rules on when a business owes it tax | once a year |
| `<client>-msa` | one client's contracts: the agreement, amendments, statements of work, letters | for that client only |
| `policies` | your own handbook, security policy, data agreements | whenever one is revised |
| `diligence-<deal>` | a deal's data room, as you received it | once, then leave it alone |

Two things keep a collection trustworthy:

- **Don't change a data room collection after you've relied on it.** If more documents
  arrive, put them in a new collection, say `diligence-<deal>-r2`. That way you can always
  show what the documents said when you gave your answer.
- **Save a web page again instead of editing it.** Each saved page records the date it was
  saved. Saving it again gives you a second copy with a second date, which is exactly what
  you want if someone later asks what the page said when you relied on it.

## What a collection can't do

It only knows what you put in it. Every answer ends with a list of what the documents
don't settle, and that list is often the most useful part. Adding more documents won't
always make it shorter, but it will make it more accurate.
