# Notes for AI agents

## Installing use-citations for a user

If someone has asked you to install this skill, these are the steps. Tell them briefly
what you're about to do, then do it.

1. **Check the basics.** You need Python 3.10 or newer (and `git`, if installing by hand).
   Run `python3 --version`; on Windows, run `python --version`, since `python3` there is
   often a shortcut to the Microsoft Store that prints "Python was not found".
   If Python is missing or older than 3.10, stop and tell them they can get it from
   https://www.python.org/downloads/ (on Windows, tick "Add python.exe to PATH" in the
   installer). It works on macOS, Linux and Windows. On Windows, also check for Tesseract
   (`tesseract --version`). It's only needed for scanned PDFs, so if it's missing, tell
   them they can install it with `winget install UB-Mannheim.TesseractOCR` and carry on.
   On Windows, always use the plugin install, not the hand install, which needs symlinks.

2. **Install the plugin.** The repo is its own plugin marketplace:

   ```bash
   claude plugin marketplace add sshah03/use-citations
   claude plugin install use-citations@use-citations
   ```

   If it's already installed, run `claude plugin marketplace update use-citations` and
   `claude plugin update use-citations@use-citations` instead.

   If they'd rather not use a plugin, install it by hand as the README describes: clone
   the repo to `~/.claude/use-citations` and link
   `~/.claude/use-citations/.claude/skills/use-citations` into `~/.claude/skills/`. Then
   skip step 3, and in step 4 run the tests from
   `~/.claude/use-citations/.claude/skills/use-citations/tests/run.py`.

3. **Look for a hand install.** Installing by hand means cloning to
   `~/.claude/use-citations` and linking `~/.claude/skills/use-citations` to it. If that
   link is still there, `/use-citations` runs the old copy instead of the plugin. Check
   with `ls -la ~/.claude/skills/use-citations`. If it's a link into
   `~/.claude/use-citations`, tell them and offer to remove the link (`rm
   ~/.claude/skills/use-citations`), and the old folder too if they want the files gone.
   If it's anything else, don't touch it: tell them what's there and ask.

4. **Check it works.** Run the test suite from the installed copy. It doesn't need the
   internet and takes a minute or two:

   ```bash
   SK="$(claude plugin list --json | python3 -c "import json,sys; print(next(p['installPath'] for p in json.load(sys.stdin) if p['id'] == 'use-citations@use-citations'))")/.claude/skills/use-citations"
   python3 "$SK/tests/run.py"
   ```

   On Windows, use `python` in place of `python3` in both lines.

   It should end with "0 failed". A few tests are skipped on a fresh install, which is
   expected. If anything fails, show them the failure rather than carrying on.

5. **Tell them how to use it.** Keep it short:
   - Start a new Claude Code session first, so the plugin loads.
   - Type `/use-citations` followed by a question, for example
     `/use-citations Is there an age limit on claiming my child as a dependent?`
   - Add `follow-up` to ask another question in the same report.
   - The first time they give it a PDF, it sets up a small PDF reader beside the saved
     documents. That's normal.

To update later: `claude plugin marketplace update use-citations`, then `claude plugin
update use-citations@use-citations`. To uninstall: `claude plugin uninstall
use-citations@use-citations`.

## Working on this repo

- The skill is in `.claude/skills/use-citations/`. `SKILL.md` is what Claude follows when
  someone types `/use-citations`; the scripts do the reading, searching, checking and
  report building.
- The repo is also a Claude Code plugin: `.claude-plugin/plugin.json` points at
  `.claude/skills/`, and `.claude-plugin/marketplace.json` lists the plugin. Leave
  `version` out of both, so installs follow new commits. Check them with `claude plugin
  validate .`. In SKILL.md, refer to the skill's own files through `${CLAUDE_SKILL_DIR}`,
  never a fixed path, since the folder differs between a plugin install and a project.
- Don't add `disable-model-invocation: true` to SKILL.md. Cowork runs a typed skill by
  having Claude load it, and that setting forbids exactly that, so `/use-citations` would
  show in Cowork's menu and then do nothing. The skill stays typed-only through its
  description and the first lines of "How it is started" instead. `evals/triggers.py`
  checks that it starts only when typed or asked for by name.
- Run the tests after any change: `python3 .claude/skills/use-citations/tests/run.py`.
  Some verifier messages are matched word for word by the tests and by the report page,
  so don't reword them without updating both.
- Write docs and comments in plain English for people who aren't developers: "the
  documents" rather than "the corpus", no legal or academic jargon where a normal word
  works.
- Public examples and eval questions must come from public sources (government FAQ
  pages, public datasets). Don't add questions or examples from anyone's private work.
