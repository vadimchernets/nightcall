---
name: team
description: The roll call of helper AIs before the night, and their replacement during it. While the person is still here - every AI program of another company already installed by subscription (Codex/ChatGPT, Gemini/agy, Grok, Kimi, Qwen) and every free key (NVIDIA first, then Google AI Studio, Groq, OpenRouter) gets a test question; then Chrome is checked (Claude in Chrome connected, a tab opens, the person is signed in to ChatGPT, Gemini, Kimi, DeepSeek, Meta AI...), and the person is asked to press "Allow" now, not at night. At night - CLI, then the next CLI, then free keys, then only the web chats that passed the roll call, then Claude's own critics; every replacement is a line in PROGRESS.md. Use when the person says "which AIs are alive", "roll call", "connect other AIs", "check the helpers", "check the browser", "other AIs" (in any language), or during a night run every few hours.
argument-hint: "[folder of the night run]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/*) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 nightcall say scripts/*) Bash(open *) Bash(osascript *) Bash(date*) Read Write ToolSearch
---

# Nightcall: the team for tonight

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

Answer in the person's language. Claude is the main agent; these are its helpers. A helper counts
only if it **answered a question just now** — being installed or open in a tab is not being alive.
`<seats>` below is `<night folder>/seats.json` (no night folder yet: a `seats.json` in the task folder).

## 1. The roll call — while the person is still here

Everything the night will need from the person — a sign-in, a click on "Allow", a captcha —
happens now. At night nobody presses anything.

### a) Programs by subscription and free keys

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/team.py rollcall --out "<seats>"
```

Every program found (claude, codex, agy/gemini, grok, kimi, qwen) and every free key the person set
up earlier (the course lesson "Free AI keys": `NVIDIA_API_KEY` first — Kimi K3, then GLM-5.3, 30 s
each — then `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, in the environment or
`~/.nightcall/free-keys.env`; within a key the next model is tried on 429/503/404/timeout) gets "Connectivity check. Answer with one word: ok", 90
seconds each. Show the table as printed: **alive / limit (until HH:MM, if known) / not-signed-in / error /
timeout / not installed**. How to say it, with what fixes it:
- **limit** — the subscription allowance ran out; nothing to pay, it comes back by itself. With a
  time: it rejoins the night after that time.
- **not-signed-in** — installed but not signed in: run it once in a terminal and sign in, now.
- **not installed** — may be installed now if the person wants; otherwise the reserve covers it.
- **timeout / error** — skip tonight; the next check tries again.

Claude's own line is the main agent, not a helper: a second Claude is not a second opinion.

### b) The browser — is the way out to web chats alive?

1. **The tool.** Load the Claude in Chrome tools in one `ToolSearch` call
   (`select:` the `mcp__claude-in-chrome__*` names you see). Only an `enable…claude-in-chrome` tool
   is there → call it to switch Chrome on. None at all → the extension is not installed or not
   connected: tell the person plainly ("install the Claude in Chrome extension and sign in —
   https://claude.ai/chrome — it takes a minute"), then record
   `team.py web-mark --seats "<seats>" --browser "no-extension"` and go to (c).
   If the `anthropic-skills:chrome-browser` skill is available, follow it for tabs and permissions.
2. **A tab opens.** Look at the person's open tabs, then open **one new tab** — never reuse theirs.
   Chrome or the extension asks for a site permission or a confirmation → **ask the person to press
   "Allow" right now** ("you won't be here tonight, and without this click the reserve won't work"), wait
   for it, and try once more. A first failure means nothing; the second one counts.
   Record `web-mark --browser alive` (or `no-permission`).
3. **Each web chat, one at a time**, from `team.py web-sites` (ChatGPT, Gemini, Kimi, DeepSeek,
   Meta AI, Grok, Qwen, Mistral — the person may name others): open it in a new tab, read the page.
   - an input field for a message is there, no sign-in screen, no captcha → paste the short test
     question, press the site's own Send, wait for an answer on the page → **alive**;
   - a sign-in or "Log in" screen → **needs-sign-in** (never type a password; ask the person to sign in
     now, then check that site again);
   - a captcha / "verify you are human" → **captcha** (ask the person to pass it now);
   - the page does not load → **did-not-open**.

   After each site:
   ```
   sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/team.py web-mark --seats "<seats>" --site chatgpt --status alive
   ```
   The record in `seats.json` is `web-<site>`: alive / needs-sign-in / captcha / did-not-open.

### c) The result

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/team.py summary --seats "<seats>"
```
Say it as three lines and a to-do: **"Working tonight: …; reserve: …; not working: … — what to do
now: sign in to …, press …, install …"**. If there is not a single live helper of another company
(no program, no key, no web chat), say it honestly: "the night will run only on Claude's own
critics" — and offer to fix one thing before the person leaves. After a fix, run that part again.

Web chats are the **reserve** by default: they are used at night only when the programs and keys
are out, and the person saw the list in this roll call.

**One choice for the person: web chats at night or in the morning.** Ask it in one line with the
default in it: "Web chats that passed the roll call are the night reserve, used after programs and
keys (web: night). If you'd rather the browser is left alone at night — web: morning: questions for
them will go into morning-advice.md. Silence means night." Record the answer:
```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/team.py web-when --seats "<seats>" night   # or morning
```

## 2. At night — asking, with automatic replacement

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" nightcall say scripts/team.py ask --seats "<seats>" --progress "<night folder>/PROGRESS.md" --dir "<folder the helper may read>" [--who kimi] -
```
Question on standard input. The order is fixed:

1. a live CLI → at a limit or failure, the next live CLI of another company;
2. free keys, if they were set up and passed the roll call;
3. a web chat — **only those marked alive in the roll call** (`next` in the answer names it), and
   only with `web: night`; with `web: morning` the script itself appends the question to
   `<night folder>/morning-advice.md` (`"morning_advice"` in the answer) and the night goes on with step 4;
4. Claude's own critics: a fresh sub-agent with no memory of your reasoning — said out loud,
   never passed off as another company.

**Several helpers on one decision — blind.** Add `--blind "<folder>/council-N"` to each `ask`: the answer
is saved without a name on screen. Then `team.py blind --dir "<folder>/council-N"` gives "Answer A / B / C"
in random order; weigh and decide, and only after that `team.py reveal --dir …` says who was who
(a judge AI leans to the answer that sounds like itself).

Every replacement is written to `PROGRESS.md` by the script ("codex — limit until 03:15; replaced:
Kimi"). A CLI at its limit is marked "limit until HH:MM" in `seats.json` and comes back at the head of
the line after that time by itself. Quote a helper's answer as theirs; do not tidy it. Programs run
read-only: they may read and search, not change files or run commands.
`team.py next --seats "<seats>"` shows the current route without asking anyone.

## 3. At night — a web chat

When `ask` says `"next": {"route": "web", …}`:

1. **One site at a time, in its own new tab.** Opening two sites in one batch gives false "not
   allowed" errors.
2. **Never type a password.** A sign-in screen or a captcha → `web-mark --site <site> --status
   "needs-sign-in"` (or `captcha`) `--progress "<night folder>/PROGRESS.md"`, and go to the next live site,
   then to Claude's own critics.
3. **Paste by script into the page's input, not by keystrokes**, read the field back, press the
   site's own Send button. A blind Cmd+V can land in another window.
4. **Wait for the whole answer.** Keep the tab in front — a background tab stops generating
   halfway. "Text stopped growing" is not "done": wait for the copy button, expand "Show more",
   then read the answer's own block, not the whole page.
5. **Check it is the answer**, not your question (Kimi repeats it on the page) and not an old one.
6. Save it to `<night folder>/helpers/NN-<site>.md` with the address and the time, and count it:
   `team.py web-mark --seats "<seats>" --site <site> --answered`.

If the Poly A1 folder `Poly nov/agent/` is next to this plugin, it is the detailed, tested version
of these steps — follow it (`01-browser-check.md`, `05-fan-out.md`, `07-collect-answers.md`,
`12-known-pitfalls.md`).

## 4. Every two or three hours

`team.py rollcall --out "<seats>"` again (the web results are kept). Allowances come back; a helper
dead at midnight may be alive at four. For the morning report: `team.py used --seats "<seats>"` —
who really answered, and how many times.
