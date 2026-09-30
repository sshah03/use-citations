# use-citations

Ask Claude Code a research question and get an answer with every quote checked against
a saved copy of its source, whether that's a government site or a file on your computer.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

https://github.com/user-attachments/assets/7212a2e2-f890-4c6e-ac81-28bc4d308e7f

This is a Claude Code skill for questions where you need to see exactly where an answer
came from: contracts, tax rules, statutes, clinical guidelines, research papers, company
policies. Claude writes the answer in plain English and links each statement to the
passage it's based on. Before you see the answer, a separate program looks for every one
of those passages in the actual document, word for word. If it can't find one, the
answer isn't shown to you until that's fixed.

## Install

You need [Claude Code](https://claude.com/claude-code) and Python 3.10 or newer, on a
Mac, Linux or Windows.

The easy way is to let Claude do it. Start Claude Code and paste this in:

```
Install the use-citations skill from https://github.com/sshah03/use-citations. Follow the repo's AGENTS.md.
```

Claude installs it as a Claude Code plugin, checks that it works, and tells you how to
use it. The steps it follows are in [AGENTS.md](AGENTS.md) if you want to see them first.

To do it yourself instead, type these two lines into Claude Code, one at a time:

```
/plugin marketplace add sshah03/use-citations
/plugin install use-citations@use-citations
```

Then start a new Claude Code session, and `/use-citations` is ready. To see which Python
you have, type `python3 --version` in the Terminal. Most Macs already have it. If yours
doesn't, you can get it from [python.org](https://www.python.org/downloads/).

**On Windows**, install Python from [python.org](https://www.python.org/downloads/) and tick
"Add python.exe to PATH" in the installer. Check it with `python --version` (on Windows
it's usually `python`, not `python3`). To read scanned PDFs you also need Tesseract, the
free text-recognition program: in PowerShell, run `winget install UB-Mannheim.TesseractOCR`.
PDFs that already have text don't need it.

To update it later, type `/plugin marketplace update use-citations` in Claude Code, then
`/plugin update use-citations@use-citations`. To remove it, type
`/plugin uninstall use-citations@use-citations`.

**If you'd rather not use a plugin**, you can still install it by hand on a Mac or Linux
(on Windows, use the plugin). Open the Terminal
app (on a Mac, press Cmd+Space and type "Terminal"), paste these lines and press Return:

```bash
git clone https://github.com/sshah03/use-citations.git ~/.claude/use-citations
mkdir -p ~/.claude/skills
ln -s ~/.claude/use-citations/.claude/skills/use-citations ~/.claude/skills/use-citations
```

The first line downloads the skill, and the other two tell Claude Code where it is. To
update it later, run `git -C ~/.claude/use-citations pull`.

**If you installed it by hand and are switching to the plugin**, remove the old link after
installing the plugin, or `/use-citations` will keep running the old copy. In the Terminal: `rm ~/.claude/skills/use-citations`. You can also delete the old
folder, `~/.claude/use-citations`, if you want the files gone.

## Use

Start Claude Code by typing `claude` in the Terminal. Then type `/use-citations` and your
question:

```
/use-citations Is there an age limit on claiming my child as a dependent?
/use-citations follow-up Does my child have to live with me?
/use-citations follow-up dependent-age-2025 What if we're divorced?
/use-citations The contracts are in ~/Documents/orion-contracts. How much notice does the customer have to give to cancel?
```

You can point it at a folder of your own documents, or just ask, and it will find the
official sources online (irs.gov, the court's website, the government agency) and save a
copy of each one.

Each question gives you a report. Add `follow-up` to add another question to the report
you just made, or `follow-up` plus a report's name to add to one from an earlier
conversation. Each report shows its name, with a button that copies the command.

The skill only runs when you type `/use-citations`, so the rest of your Claude Code
session works as normal.

## What you get

Here's a real run, using one of the public test questions. You ask:

> /use-citations Is there an age limit on claiming my child as a dependent?

Claude gives you the short answer in the chat, with a link to the report:

> Yes. To be claimed as a **qualifying child**, your child must be under 19 at the end of
> the year, or under 24 if they're a student. They must also be younger than you (or your
> spouse, if you file jointly). There's no age limit if the child is permanently and
> totally disabled.

In the report, each statement has a small number after it. Click a number and the
document opens next to the answer, on the right page, with the passage highlighted. For
that last sentence, it's the tax code itself:

> "In the case of an individual who is permanently and totally disabled (as defined in
> section 22(e)(3)) at any time during such calendar year, the requirements of
> subparagraph (A) shall be treated as met with respect to such individual."
> *26 U.S.C. § 152, saved from uscode.house.gov*

Then you ask a follow-up in the same conversation:

> /use-citations follow-up Does my child have to live with me?

That's added to the same report as question 2:

> Generally yes. For your child to count as your qualifying child, they must have lived
> with you for more than half the year. Time away for school, illness, business, vacation,
> military service or detention in a juvenile facility still counts as time living with
> you.

This run took about three minutes for both questions. The 36 passages it cited, from IRS
Publication 501, the statute and two other IRS pages, were all found word for word.

The report also shows:

- what the documents don't answer, which is often the most useful part
- every document that was collected, including ones that weren't used, with where and
  when each one was saved
- how the answer was checked, including every search Claude ran, and the ones where it
  looked for evidence that it was wrong
- each follow-up question on the same page, with its own list of sources

Reports are private links on claude.ai. Nobody else can see one until you share it.

## What it checks, and what it can't

The checker rejects a quote if a number has been changed, two numbers have been swapped,
a number has been cut short, a "not" has been added or dropped, or two separate passages
have been joined together. It doesn't mind line breaks, different styles of quotation
marks, or a word split across two lines of a PDF.

What it can't check is whether Claude's plain-English sentence fairly sums up the
passage, or whether Claude actually got the answer from the documents rather than from
what it already knew. That's why every number in the report opens the passage itself,
and why the report lists every search. Read the passage before you rely on the sentence.

I tested it on 34 public questions that come with official answers, from the IRS, the
CFPB, the Department of Labor, the EEOC, the FDA, the Copyright Office and a medical
research dataset. All 372 passages it cited were found in their sources. The results are
in [evals/RESULTS.md](evals/RESULTS.md), and [evals/README.md](evals/README.md) explains
how to run the same questions yourself.

## Your documents, and what it downloads and sends

- Your files stay on your computer. Claude reads the parts of your documents it searches,
  the same as it would with any file you open in Claude Code.
- A report you publish includes the pages it quotes from. If a document can't leave your
  computer, don't publish the report. You can open it as a file on your computer instead.

Everything it runs, downloads or sends:

- **Its own Python scripts**, in the skill's folder. They read your documents, search them,
  check the quotes and build the report. They use only Python's standard library, except
  for reading PDFs.
- **A PDF reader, downloaded once.** The first time you give it a PDF, it installs
  [PyMuPDF](https://pypi.org/project/PyMuPDF/) 1.28.2 from PyPI into a folder beside your
  saved documents (`.citations/venv`), not into your system. On a Mac, reading a scanned PDF
  also installs pyobjc 12.2.2, which lets Python use the Mac's built-in text recognition.
- **Web pages you ask for.** When you ask about something that isn't in your files, Claude
  finds the official source and downloads that page or PDF straight from the site, so it
  can quote a saved copy. The site gets only the request for that page, with nothing about
  your question or your files. The request identifies itself as a desktop web browser,
  since some government sites turn away other programs.
- **Reports you publish** go to claude.ai as a private page that only you can see until you
  share it.

It sends nothing anywhere else. There's no tracking or usage data, and it keeps no record
outside the folders on your computer. See [PRIVACY.md](PRIVACY.md).

## What it can't do yet

- It can't save web pages that need a login, or pages that only load properly in a full
  browser. That includes PACER, EDGAR search and most data rooms.
- It doesn't read from apps you've connected to Claude, like Google Drive, Notion or a
  legal research service. Those return text Claude has already processed, and it only
  cites files it saved itself. To use a document from one of them, download the file and
  point it at the file.
- It searches for the words in your question. If a document uses different words for the
  same thing, it can miss it, so Claude tries several searches before saying something
  isn't there.
- It checks quotes. The reasoning between them, like which document wins when two
  disagree, or any arithmetic, is Claude's, and the report marks it so you can check it.
- On Windows, every test passes, but it has had much less real use than on a Mac. If
  something goes wrong there, please [open an issue](https://github.com/sshah03/use-citations/issues).
- None of this is legal, tax or medical advice.

## More

- [How it works](docs/how-it-works.md): the checker, the scripts, a worked example and the tests
- [SKILL.md](.claude/skills/use-citations/SKILL.md): the instructions Claude follows
- [AGENTS.md](AGENTS.md): install steps for Claude, and notes for working on the repo

## License

[MIT](LICENSE)
