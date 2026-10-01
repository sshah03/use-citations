#!/usr/bin/env python3
"""Check that the skill starts only when its command is typed.

    python3 evals/triggers.py            run every prompt in triggers.json
    python3 evals/triggers.py -k lease   only prompts containing "lease"

Each prompt goes to `claude -p` with this repo loaded as a plugin, in a scratch folder
holding a copy of the Orion example. A prompt marked "start" passes if the skill runs, and
one marked "skip" passes if it doesn't. A typed command doesn't go through the Skill tool,
so "runs" means Claude either loaded the skill or ran one of its scripts. Runs stop after a
few turns, so this checks the decision, not the answer. It needs Claude Code and a login, and costs a little per prompt, so it isn't
part of tests/run.py or CI. Run it after changing the skill's description.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "use-citations"


def run(prompt: str, work: Path) -> tuple[bool, str]:
    r = subprocess.run(
        ["claude", "-p", prompt, "--plugin-dir", str(ROOT), "--output-format", "stream-json",
         "--verbose", "--max-turns", "5",
         "--allowedTools", "Read,Glob,Grep,Skill,Bash(python3 *notices.py* take)"],
        cwd=work, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)
    started, next_step = False, ""
    for line in r.stdout.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") != "assistant":
            continue
        for c in e["message"].get("content", []):
            if c.get("type") == "tool_use" and (
                    (c["name"] == "Skill" and "use-citations" in json.dumps(c["input"]))
                    or "use-citations/scripts" in json.dumps(c["input"])):
                started = True
            elif c.get("type") == "tool_use" and "notices.py" in json.dumps(c["input"]):
                continue                       # the skill's first step, before it asks
            elif c.get("type") not in ("text", "tool_use"):
                continue                       # thinking isn't a step
            elif started and not next_step:
                next_step = ("asked first" if c.get("type") == "text" and "?" in c.get("text", "")
                             else "went straight to work")
    return started, next_step


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-k", help="only prompts containing this text")
    args = ap.parse_args()
    if not shutil.which("claude"):
        sys.exit("this needs Claude Code (the claude command) and a login")
    prompts = json.loads((Path(__file__).parent / "triggers.json").read_text(encoding="utf-8"))["prompts"]
    prompts = [p for p in prompts if not args.k or args.k.lower() in p["prompt"].lower()]
    passed = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(SKILL / "examples" / "orion-contracts", work / "orion-contracts")
        for p in prompts:
            started, how = run(p["prompt"], work)
            ok = started == (p["expect"] == "start")
            passed += ok
            print(f"{'pass' if ok else 'FAIL'}  {p['expect']:5}  {'started' if started else 'answered'}"
                  f"{', ' + how if how else ''}  | {p['prompt'][:70]}")
    print(f"\n{passed} of {len(prompts)} as expected")
    return 0 if passed == len(prompts) else 1


if __name__ == "__main__":
    sys.exit(main())
