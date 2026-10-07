---
name: family
description: Family relay for long runs - the night, the weekend, a week away. Each member of the family (or of a family team) is added with their own e-mail and their own Claude Code (or Codex) sign-in folder, signs in there once as themselves, and says until when their account may carry the family's work on. Then, when one person's subscription limit runs out in the middle of the run, the next round goes on in the next member's own account instead of waiting, and every change of hands is a line in PROGRESS.md. Use when the person says "family", "continue on my son's account", "we are all away for the weekend", "when my limit runs out let the family carry on", "family relay", "second subscription" (in any language).
argument-hint: "[add | consent | check | status]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/*) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 nightcall say scripts/*) Bash(date*) Read
---

# Nightcall: the family relay

## Running nightcall's scripts (Mac, Linux, Windows)

Every script command on this page is written for the **Bash** tool and starts with
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/…`. If your shell tool is **PowerShell** (Windows
without Git Bash), only the start changes: write the launcher's path bare, with no quotes and no `&`
— `${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 nightcall say scripts/…` — and keep the rest, on one line; that is the
form this skill's permission covers. Only if that path has a space in it, write
`& "${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1" …` instead (the person is then asked once). Text for standard input:
`@'…'@ | ${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 …` (`| & "…"` if the path has a space) instead of `<<'EOF'` — also asked once.
Never call `python3`, `python` or `py` yourself: the launcher finds a real Python 3.8+ (`python`,
then `py -3`, then `python3`) and never starts the Microsoft Store or Apple stub. If it answers
with one line saying nightcall "is paused" until this computer has Python 3, tell the
person that in one plain line and go on by hand — never show them a Python error and stop.

The person said: $ARGUMENTS

Answer in the person's language.

The rule: **the context moves, the access never does.** The task (TASK.md, PLAN.md, PROGRESS.md, the files) is read
by a fresh Claude at every round anyway, so the next account continues where the previous one stopped. Each member's
sign-in stays in their own folder; nightcall never touches it.

1. **The person who runs the nights comes first**, on this computer's usual sign-in:
   ```
   sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/family.py add --name "<name>" --email "<their account e-mail>" --config-dir default
   ```

2. **Each member of the family**, with their own account (`--engine codex` for a ChatGPT/Codex subscription):
   ```
   sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/family.py add --name "<name>" --email "<their e-mail>"
   ```
   Show the script's lines as they are - they include the family wording and the one sign-in command. The member
   runs that command themselves, in a terminal, once (it opens the vendor's own sign-in page).

3. **The member says until when their account carries the work on** - the weekend, the week, the night:
   ```
   sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/family.py consent --name "<name>" --by "<name>" --until "YYYY-MM-DD HH:MM"
   ```
   `--folder "<task folder>"` narrows it to one task. `revoke --name "<name>"` ends it at once.

4. **Check that everyone is really signed in as themselves:**
   ```
   sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/family.py check
   ```
   A line that says SIGN IN or WRONG comes with the exact command for that member.

5. **Run the night or the weekend through the loop** - the relay lives there, a fresh Claude per step:
   ```
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/night-loop.sh" "<folder>" <hours>
   ```
   For a weekend: `60` hours and `NIGHTCALL_MAX_ROUNDS=400`. When a limit runs out the loop notes when that account
   comes back, the next member's account takes the next round, and PROGRESS.md gets a "Relay" line; when every
   account is resting it waits for the first one to come back. `NIGHTCALL_FAMILY=off` runs on the usual sign-in only.
