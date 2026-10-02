---
name: team
description: The roll call of helper AIs before the night, and their replacement during it. While the person is still here - every AI program of another company already installed by subscription (Codex/ChatGPT, Gemini/agy, Grok, Kimi, Qwen) and every free key (NVIDIA first, then Google AI Studio, Groq, OpenRouter) gets a test question; then Chrome is checked (Claude in Chrome connected, a tab opens, the person is signed in to ChatGPT, Gemini, Kimi, DeepSeek, Meta AI...), and the person is asked to press "Allow" now, not at night. At night - CLI, then the next CLI, then free keys, then only the web chats that passed the roll call, then Claude's own critics; every replacement is a line in PROGRESS.md. Use when the person says "кто из ИИ живой", "перекличка", "подключи другие ИИ", "проверь помощников", "проверь браузер", "other AIs", or during a night run every few hours.
argument-hint: "[folder of the night run]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(open *) Bash(osascript *) Bash(date*) Read Write ToolSearch
---

# Nightcall: the team for tonight

The person said: $ARGUMENTS

Answer in the person's language. Claude is the main agent; these are its helpers. A helper counts
only if it **answered a question just now** — being installed or open in a tab is not being alive.
`<seats>` below is `<night folder>/seats.json` (no night folder yet: a `seats.json` in the task folder).

## 1. The roll call — while the person is still here

Everything the night will need from the person — a sign-in, a click on «Разрешить», a captcha —
happens now. At night nobody presses anything.

### a) Programs by subscription and free keys

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" rollcall --out "<seats>"
```

Every program found (claude, codex, agy/gemini, grok, kimi, qwen) and every free key the person set
up earlier (the course lesson «Бесплатные ключи ИИ»: `NVIDIA_API_KEY` first — Kimi K3, then GLM-5.3, 30 s
each — then `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, in the environment or
`~/.nightcall/free-keys.env`; within a key the next model is tried on 429/503/404/timeout) gets «Проверка связи. Ответь одним словом: ок», 90
seconds each. Show the table as printed: **жив / лимит (до ЧЧ:ММ, если видно) / не вошли / сбой /
молчит / нет программы**. How to say it, with what fixes it:
- **лимит** — the subscription allowance ran out; nothing to pay, it comes back by itself. With a
  time: it rejoins the night after that time.
- **не вошли** — installed but not signed in: run it once in a terminal and sign in, now.
- **нет программы** — may be installed now if the person wants; otherwise the reserve covers it.
- **молчит / сбой** — skip tonight; the next check tries again.

Claude's own line is the main agent, not a helper: a second Claude is not a second opinion.

### b) The browser — is the way out to web chats alive?

1. **The tool.** Load the Claude in Chrome tools in one `ToolSearch` call
   (`select:` the `mcp__claude-in-chrome__*` names you see). Only an `enable…claude-in-chrome` tool
   is there → call it to switch Chrome on. None at all → the extension is not installed or not
   connected: tell the person plainly («поставьте расширение Claude in Chrome и войдите в него —
   https://claude.ai/chrome — это минута»), then record
   `team.py web-mark --seats "<seats>" --browser "нет расширения"` and go to (c).
   If the `anthropic-skills:chrome-browser` skill is available, follow it for tabs and permissions.
2. **A tab opens.** Look at the person's open tabs, then open **one new tab** — never reuse theirs.
   Chrome or the extension asks for a site permission or a confirmation → **ask the person to press
   «Разрешить» right now** («ночью вас не будет, а без этого нажатия запас не заработает»), wait
   for it, and try once more. A first failure means nothing; the second one counts.
   Record `web-mark --browser жив` (or `нет разрешения`).
3. **Each web chat, one at a time**, from `team.py web-sites` (ChatGPT, Gemini, Kimi, DeepSeek,
   Meta AI, Grok, Qwen, Mistral — the person may name others): open it in a new tab, read the page.
   - an input field for a message is there, no sign-in screen, no captcha → paste the short test
     question, press the site's own Send, wait for an answer on the page → **жив**;
   - a sign-in or "Log in" screen → **нужен вход** (never type a password; ask the person to sign in
     now, then check that site again);
   - a captcha / "verify you are human" → **капча** (ask the person to pass it now);
   - the page does not load → **не открылся**.

   After each site:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" web-mark --seats "<seats>" --site chatgpt --status жив
   ```
   The record in `seats.json` is `web-<site>`: жив / нужен вход / капча / не открылся.

### c) The result

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" summary --seats "<seats>"
```
Say it as three lines and a to-do: **«Ночью работают: …; запас: …; не работает: … — что сделать
сейчас: войти в …, нажать …, поставить …»**. If there is not a single live helper of another company
(no program, no key, no web chat), say it honestly: «ночь пройдёт только со своими критиками
Claude» — and offer to fix one thing before the person leaves. After a fix, run that part again.

Web chats are the **reserve** by default: they are used at night only when the programs and keys
are out, and the person saw the list in this roll call.

**One choice for the person: web chats at night or in the morning.** Ask it in one line with the
default in it: «Веб-чаты, прошедшие перекличку, — ночной запас после программ и ключей (web: night).
Если хотите, чтобы ночью браузер не трогали, — web: morning: вопросы для них лягут в утро-совет.md.
Молчание — night.» Record the answer:
```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" web-when --seats "<seats>" night   # or morning
```

## 2. At night — asking, with automatic replacement

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" ask --seats "<seats>" --progress "<night folder>/PROGRESS.md" --dir "<folder the helper may read>" [--who kimi] -
```
Question on standard input. The order is fixed:

1. a live CLI → at a limit or failure, the next live CLI of another company;
2. free keys, if they were set up and passed the roll call;
3. a web chat — **only those marked жив in the roll call** (`дальше` in the answer names it), and
   only with `web: night`; with `web: morning` the script itself appends the question to
   `<night folder>/утро-совет.md` (`"утро_совет"` in the answer) and the night goes on with step 4;
4. Claude's own critics: a fresh sub-agent with no memory of your reasoning — said out loud,
   never passed off as another company.

**Several helpers on one decision — blind.** Add `--blind "<folder>/совет-N"` to each `ask`: the answer
is saved without a name on screen. Then `team.py blind --dir "<folder>/совет-N"` gives «Ответ A / B / C»
in random order; weigh and decide, and only after that `team.py reveal --dir …` says who was who
(a judge AI leans to the answer that sounds like itself).

Every replacement is written to `PROGRESS.md` by the script («codex — лимит до 03:15; заменён:
Kimi»). A CLI at its limit is marked «лимит до ЧЧ:ММ» in `seats.json` and comes back at the head of
the line after that time by itself. Quote a helper's answer as theirs; do not tidy it. Programs run
read-only: they may read and search, not change files or run commands.
`team.py next --seats "<seats>"` shows the current route without asking anyone.

## 3. At night — a web chat

When `ask` says `"дальше": {"путь": "веб", …}`:

1. **One site at a time, in its own new tab.** Opening two sites in one batch gives false "not
   allowed" errors.
2. **Never type a password.** A sign-in screen or a captcha → `web-mark --site <site> --status
   "нужен вход"` (or `капча`) `--progress "<night folder>/PROGRESS.md"`, and go to the next live site,
   then to Claude's own critics.
3. **Paste by script into the page's input, not by keystrokes**, read the field back, press the
   site's own Send button. A blind Cmd+V can land in another window.
4. **Wait for the whole answer.** Keep the tab in front — a background tab stops generating
   halfway. "Text stopped growing" is not "done": wait for the copy button, expand "Show more",
   then read the answer's own block, not the whole page.
5. **Check it is the answer**, not your question (Kimi repeats it on the page) and not an old one.
6. Save it to `<night folder>/помощники/NN-<site>.md` with the address and the time, and count it:
   `team.py web-mark --seats "<seats>" --site <site> --answered`.

If the Poly A1 folder `Poly nov/agent/` is next to this plugin, it is the detailed, tested version
of these steps — follow it (`01-browser-check.md`, `05-fan-out.md`, `07-collect-answers.md`,
`12-known-pitfalls.md`).

## 4. Every two or three hours

`team.py rollcall --out "<seats>"` again (the web results are kept). Allowances come back; a helper
dead at midnight may be alive at four. For the morning report: `team.py used --seats "<seats>"` —
who really answered, and how many times.
