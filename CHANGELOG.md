# What's changed

Updates reach you only when you update: `/plugin marketplace update use-citations` then
`/plugin update use-citations@use-citations` for the plugin, or
`git -C ~/.claude/use-citations pull` if you installed it by hand.

## 1.3.0 (October 1, 2026)

**Works in Cowork.** Add the plugin in claude.ai under Customize → Plugins, then type
`/use-citations` in a Cowork task with your documents attached. In Claude Code nothing
changes: it still runs only when you type `/use-citations`. It doesn't work in ordinary
claude.ai chat.

Also in this release:

- **A Claude Code plugin.** Install it with `/plugin marketplace add sshah03/use-citations`
  and `/plugin install use-citations@use-citations`. The hand install still works. If you
  switch, remove the old link (`rm ~/.claude/skills/use-citations`), or `/use-citations`
  keeps running the old copy.
- **Windows.** The scripts now work on Windows. They used to fail on the first PDF, and
  garbled curly quotes and dashes in documents.
- **Clause numbers in PDFs.** In some PDFs, often ones exported from Word, clause numbers
  like "12.1." came out in a list at the bottom of the page instead of in front of their
  clause. They're now put back. Documents you'd already saved keep their text.
- **A scan no longer stops a whole folder.** Without an OCR program, which is normal on
  Windows and Linux, one scanned PDF stopped every file in the folder from being read. Now
  the scan is skipped, with a note on how to install Tesseract.
- **What it downloads is pinned and listed.** PyMuPDF 1.28.2, and pyobjc 12.2.2 on a Mac.
  The README lists everything it runs, downloads or sends, and [PRIVACY.md](PRIVACY.md)
  covers your documents.

## 1.2.0 (September 22, 2026)

First public release.
