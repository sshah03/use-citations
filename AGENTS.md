# Notes for AI agents

## Installing use-citations for a user

If someone has asked you to install this skill, these are the steps. Tell them briefly
what you're about to do, then do it.

1. **Check the basics.** You need `git` and Python 3.10 or newer. Run `python3 --version`.
   If Python is missing or older than 3.10, stop and tell them: on a Mac they can get it
   from https://www.python.org/downloads/. It works on macOS and Linux; it hasn't been
   tested on Windows, so say so if that's what they're on.

2. **Download it.** Clone the repo to `~/.claude/use-citations`, unless they asked for a
   different place:

   ```bash
   git clone https://github.com/sshah03/use-citations.git ~/.claude/use-citations
   ```

   If that folder already exists and is a clone of this repo, run `git -C
   ~/.claude/use-citations pull` instead of cloning again.

3. **Make it available to Claude Code.** Link the skill folder into their personal skills
   folder:

   ```bash
   mkdir -p ~/.claude/skills
   ln -s ~/.claude/use-citations/.claude/skills/use-citations ~/.claude/skills/use-citations
   ```

   If `~/.claude/skills/use-citations` already exists, look at what it is before doing
   anything. If it's already a link to this clone, you're done with this step. If it's
   something else, don't delete or overwrite it: tell them what's there and ask.

4. **Check it works.** Run the test suite. It doesn't need the internet and takes a
   minute or two:

   ```bash
   python3 ~/.claude/use-citations/.claude/skills/use-citations/tests/run.py
   ```

   It should end with "0 failed". A few tests are skipped on a fresh install, which is
   expected. If anything fails, show them the failure rather than carrying on.

5. **Tell them how to use it.** Keep it short:
   - Type `/use-citations` followed by a question, for example
     `/use-citations Is there an age limit on claiming my child as a dependent?`
   - Add `follow-up` to ask another question in the same report.
   - The first time they give it a PDF, it sets up a small PDF reader in the folder they're
     working in. That's normal.
   - If `/use-citations` doesn't show up, they should start a new Claude Code session.

To update later: `git -C ~/.claude/use-citations pull`. To uninstall: remove the link at
`~/.claude/skills/use-citations`, and delete `~/.claude/use-citations` if they want the
files gone too.

## Working on this repo

- The skill is in `.claude/skills/use-citations/`. `SKILL.md` is what Claude follows when
  someone types `/use-citations`; the scripts do the reading, searching, checking and
  report building.
- Run the tests after any change: `python3 .claude/skills/use-citations/tests/run.py`.
  Some verifier messages are matched word for word by the tests and by the report page,
  so don't reword them without updating both.
- Write docs and comments in plain English for people who aren't developers: "the
  documents" rather than "the corpus", no legal or academic jargon where a normal word
  works.
- Public examples and eval questions must come from public sources (government FAQ
  pages, public datasets). Don't add questions or examples from anyone's private work.
