---
name: ready
description: The checklist and the roll call before leaving the computer working for the night - power, sleep and the laptop lid, system updates that restart at night, network, disk space, Claude Code permissions that would stop the night on the first question, the subscription limit, the restore point and the fence (made by itself if missing) - and which helper AIs are really alive - subscription programs with a test question, free keys, and Chrome with the web chats the person is signed in to, with "Allow" pressed now while the person is still here. Use before a night run, or when the person says "what does it need to work all night", "check before the night", "roll call", "ready for overnight" (in any language).
argument-hint: "[task folder]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/*) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 nightcall say scripts/*) Bash(date*) Read Write ToolSearch
---

# Nightcall: ready for the night?

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
with one line saying nightcall "is paused" because this computer has no working Python 3 yet, tell the
person that in one plain line and go on by hand — never show them a Python error and stop.

The person said: $ARGUMENTS

Answer in the person's language. The person is still here: this is the last moment anything can be
signed in, allowed or clicked.

## 1. The computer

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/ready.py --dir "<task folder, if there is one>"
```


Show the result as three groups, short:

- **NOT OK — fix it now.** Each with its one action. Help the person do it right now, one at a
  time, and run the check again after. These are the reasons a night silently does nothing.
- **WATCH — look at it with your own eyes.** Things the script cannot read from here (the lid, the
  permission mode of this window, the Claude limit). One line each.
- **OK** — one line in total: "Everything else is fine: power, network, space…".

The one to stress every time: **permissions**. Ask the person to switch this window to a mode that
does not stop to ask (Shift+Tab until auto or accept edits) and prove it with one real step while
they are still here. A night that stopped at 23:05 on "Allow?" looks in the morning exactly like
a night that did nothing.

## 2. The roll call of helpers

Do `/nightcall:team` §1 in full, with `<seats>` = `<task folder>/seats.json`:

a) `team.py rollcall` — a table of every CLI by subscription and free key: alive / limit (until HH:MM) /
   not signed in / not installed;
b) the browser: Claude in Chrome connected (switch it on if only the enable tool is there), one new
   tab opens, each web chat (ChatGPT, Gemini, Kimi, DeepSeek, Meta AI…) checked one at a time — an
   input field, not a sign-in screen or a captcha, and a short test question answered. Any
   "Allow" or confirmation — **ask the person to press it now**;
c) `team.py summary` — "Working tonight: …; reserve: …; not working: … — what to do now".

No live helper of another company at all → say that the night will run with Claude's own critics
only, and offer to fix one thing (sign in, press, install) before the person leaves. Then run
`ready.py` once more: it reads `seats.json` too.

If the person wants the phone to see the night's progress, and the Poly A1 plugin `pocketcall` is
installed, offer its `leave` skill after this list.
