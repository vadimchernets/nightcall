---
name: team
description: Find which other AIs can help tonight and prove they are alive - first AI programs of other companies already installed and signed in with the person's own subscription (Codex/ChatGPT, Gemini, Grok, Kimi, Qwen), each checked with a short test question; dead ones (out of allowance, not signed in, silent) are replaced by the next live one; if no program is alive, helpers come through free web chats in the browser, where Claude pastes the question and takes the answer back. Use when the person says "кто из ИИ живой", "подключи другие ИИ", "проверь помощников", "other AIs", or during a night run every few hours.
argument-hint: "[folder of the night run]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(open *) Bash(osascript *) Read Write
---

# Nightcall: the team for tonight

The person said: $ARGUMENTS

Answer in the person's language. Claude is the main agent; these are its helpers. A helper counts
only if it **answered a question just now** — being installed is not being alive.

## 1. Programs on this computer

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" probe --out "<night folder>/seats.json"
```
(no night folder yet: leave out `--out`). Each found program gets «Проверка связи. Ответь одним
словом: ок» with a 90-second ceiling. Show the result as the script prints it: ЖИВ / НЕТ and why.

How to say the reasons — without blame, and with what fixes it:
- **кончился запас** — the subscription allowance ran out. Not a breakage and nothing to pay: it
  comes back by itself. Tonight another helper takes its place.
- **не вошли** — the program is installed but not signed in. The person can fix it now in one
  minute (run the program once and sign in); at night — skip it.
- **молчит / сбой** — skip it tonight, try again at the next check.

Only programs of **other companies** count: a second Claude is not a second opinion.

## 2. Asking — with automatic replacement

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" ask --seats "<night folder>/seats.json" --dir "<folder the helper may read>" [--who kimi] -
```
Question on standard input. The answer says **who really answered** and who fell out on the way
(`не_смогли`). Quote the helper's answer as theirs; do not tidy it. Helpers run read-only: they
may read and search, they cannot change files or run commands.

## 3. Через браузер — when no program is alive

This is a full route, not a fallback to apologise for. The person's browser is usually signed in
to free chats of other companies: ChatGPT (chatgpt.com), Gemini (gemini.google.com), Grok
(grok.com), DeepSeek (chat.deepseek.com), Kimi (kimi.com), Qwen (chat.qwen.ai), Mistral
(chat.mistral.ai).

1. **Name the browser tool you have** — Claude in Chrome, the built-in browser, or on a Mac plain
   `open -a "Google Chrome" <url>` plus `osascript` to run JavaScript in the tab. No tool at all:
   hand the person the question as a block to paste, and ask them to paste the answer back — before
   they leave, not at night.
2. **Prove the tab is real**: read back the account name on the page. Signed out → that chat is
   not a helper tonight; say so and use another.
3. **One site per step.** Opening two sites in one batch gives false "not allowed" errors. A first
   failure means nothing — try once more before calling a chat unreachable.
4. **Paste by script into the page's input, not by keystrokes**, then read the field back and press
   the site's own Send button. A blind Cmd+V can land in another window.
5. **Wait for the whole answer.** Bring the tab to the front — a background tab stops generating
   halfway. "Text stopped growing" is not "done": wait for the copy button to appear, expand any
   "Show more", then read the answer's own block on the page, not the whole page.
6. **Check it is the answer, not your question** (Kimi repeats the question on the page) and not an
   old answer from the same tab.
7. Save it to `<night folder>/помощники/NN-<chat>.md` with the chat's address and the time.

If the Poly A1 folder `Poly nov/agent/` is next to this plugin, it is the detailed, tested version
of these steps — follow it (`01-browser-check.md`, `05-fan-out.md`, `07-collect-answers.md`,
`12-known-pitfalls.md`; `13-own-browser.md` for a separate browser that does not take over the screen).

## 4. At night — every two or three hours

Re-run the probe. Allowances come back; a helper dead at midnight may be alive at four. Write each
change in `PROGRESS.md` → «Помощники»: who, when, why, replaced by whom.
