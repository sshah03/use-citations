# Privacy

use-citations is a Claude Code plugin that runs on your own computer. This is everything
it does with your information.

**What it collects:** nothing. There's no tracking, analytics or usage data, and no
account. The author of this plugin receives nothing from you.

**Your documents** stay on your computer. The plugin's scripts read them there to search
them and check quotes, and save what they read in a `.citations` folder beside them, or
in `~/.claude/citations` for a named collection. Claude reads the passages it searches, as
it does with any file you open in Claude. That's covered by
[Anthropic's privacy policy](https://www.anthropic.com/legal/privacy), not by this plugin.

**Downloads:** the first time you give it a PDF, it installs PyMuPDF from PyPI into
`.citations/venv`, and on a Mac, pyobjc for reading scans. When you ask it to use a web
source, it downloads that page or PDF from the site it's on. Those requests go to PyPI and
to the site, and contain nothing about your documents or question.

**Reports:** a report you publish is uploaded to claude.ai as a private page, which only
you can see until you share it. It includes the pages the answer quotes from. If a document
can't leave your computer, don't publish the report.

**Deleting it:** remove the `.citations` folders it made, `~/.claude/citations`, and any
reports you published. Uninstalling the plugin removes its own files.

Questions: [open an issue](https://github.com/sshah03/use-citations/issues).
