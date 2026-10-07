---
name: mine
description: My own subscriptions carry the work on in turn - one person, Claude first, then their own Codex (ChatGPT), then their own Gemini CLI. When the Claude limit runs out, or the remaining-% sensor says it is nearly spent, the next step of the night (or of a long build) goes on in Codex from the same TASK.md / PLAN.md / PROGRESS.md, and comes back to Claude when its limit is back; the phone hears "switched to Codex - the work goes on" and the board shows how much each subscription has left. Use when the person says "my subscriptions", "when Claude runs out switch to Codex", "use my ChatGPT too", "don't wait for the limit", "Gemini as a reserve", "how much is left in my subscription", "switch subscription" (in any language).
argument-hint: "[on | off | status | meter]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/*) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 nightcall say scripts/*) Bash(date*) Bash(command -v *) Read
---

# Nightcall: my subscriptions

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

The work lives in files, not in a session: every round of the night loop is a fresh program that reads TASK.md,
PLAN.md and PROGRESS.md. That is why the step Claude could not finish is taken by the person's own Codex from the very
same files - and the next one by Claude again, once its limit is back. Each program uses the person's own usual
sign-in on this computer; nothing about logins moves.

1. **Which programs are here** (each is optional; the order skips what is missing):
   ```
   command -v claude codex gemini
   ```
   Missing Codex: `npm i -g @openai/codex`, then `codex login` (ChatGPT subscription). Missing Gemini CLI:
   `npm i -g @google/gemini-cli`, then `gemini` once to sign in with the Google account. Show the commands; the person
   signs in themselves.

2. **Turn it on**, with the order, the threshold and the week's reserve (default: Claude -> Codex -> Gemini, move on
   below 10% of the five-hour window, and keep 20% of each week - when a week falls to its reserve, that subscription
   rests until its week resets, so one night does not burn the week; ask the person, `--reserve 0` spends it all):
   ```
   sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/mine.py on --order claude,codex,gemini --below 10 --reserve 20
   ```

3. **The remaining-% sensor for Claude** (once): Claude Code tells how much of the five-hour and weekly limits is left
   only to its status line. Add to `~/.claude/settings.json` (keep any statusLine the person already has - then
   say so and leave theirs; the move then happens on the limit message, which works too):
   ```json
   "statusLine": {"type": "command", "command": "python3 \"<real path of ${CLAUDE_PLUGIN_ROOT}>/scripts/mine.py\" capture"}
   ```
   The status line then shows "Claude 44% left (5h), resets 21:00", and the night reads the same number. Codex's
   number is read live from `codex app-server` (OpenAI's own figures). Gemini publishes none - it moves on its limit
   message.

4. **See it:**
   ```
   sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/mine.py status
   ```

5. **Run the night or the long build through the loop** (the switching lives there):
   ```
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/night-loop.sh" "<folder>" <hours>
   ```
   With pocketcall the night is one line on its board with the meter ("Claude rests until 21:00 · Codex 72% ·
   Gemini ?"), and the phone rings "switched to codex - the work goes on" at each change of hands. PROGRESS.md gets a
   "Relay" line every time. `/pocketcall:board` shows it at the desk; the phone's Stop and Continue buttons steer it.

`mine.py off` returns to Claude only (waiting on its limit). A family set up with `/nightcall:family` takes
precedence over "my subscriptions"; `NIGHTCALL_FAMILY=off` runs this mode even with a family list.
