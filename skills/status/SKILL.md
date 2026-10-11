---
name: status
description: See what the night is doing right now, in one card - state (working, stopped, done), the last thing it did, how many plan steps are done and how many checks are closed with evidence, what waits for the person (the ledger "what the AI wanted - what you decided"), and the Stop / Continue switch. The same card goes to the phone through pocketcall's board. Use when the person asks "what is it doing", "how far is the night", "what is waiting for me", "stop the night", "continue", "what did you want to do that I have to approve", "approve / decline" (in any language), or before bed to check the night is on.
argument-hint: "[task folder]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/status.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 nightcall say scripts/status.py *) Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/ledger.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 nightcall say scripts/ledger.py *) Read
---

# Nightcall: what the night is doing

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

## The card

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/status.py show [--dir "<folder>"]
```

Without `--dir` it takes the night that is on. Read it back in plain words, in this order: the **state**
(working until HH:MM / stopped / done / not armed), the **last action**, **how far** (steps done of the plan, checks
closed with evidence), and **what waits for the person** first among the rest. The card is built only from files
the night keeps (`PLAN.md`, `PROGRESS.md`, `checklist.json`, `LEDGER.jsonl`, `STOP`, `MORNING.md`); say what it
says, never what you remember.

The phone sees the same card: after every round the night puts it on pocketcall's board (`status.py push`), so the
board page shows steps, checks, the last action and the number of things waiting, and the Telegram ring comes
with Stop and Continue.

## Stop and continue

- Stop: `scripts/status.py stop --dir "<folder>"` - a `STOP` file; the night ends after the step it is in, and the
  morning report is written from what is there.
- Continue: `scripts/status.py continue --dir "<folder>"` - the file goes away and the night goes on. A night that is
  over (`MORNING.md` written) is not resumed: start a new one with `/nightcall:start`.

## The ledger: what the AI wanted - what you decided

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/ledger.py show --dir "<folder>"
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/ledger.py decide --dir "<folder>" --id N --verdict approved|declined [--note "…"]
```

Each line is a thing the night wanted to do that is the person's to decide, with why, and what it did meanwhile.
Read the waiting ones out one by one, ask for one word each - approve or decline - and record it with `decide`.
An approved item is done by the next night or session as the person said; a declined one is dropped and the work
around it is undone as far as the restore point allows. Both stay in the ledger with the time, so the morning
report and the person can always see who chose what.
