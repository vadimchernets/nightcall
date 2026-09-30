---
name: ready
description: The checklist and the roll call before leaving the computer working for the night - power, sleep and the laptop lid, system updates that restart at night, network, disk space, Claude Code permissions that would stop the night on the first question, the subscription limit, git for undo - and which helper AIs are really alive - subscription programs with a test question, free keys, and Chrome with the web chats the person is signed in to, with "Allow" pressed now while the person is still here. Use before a night run, or when the person says "что нужно, чтобы ночью всё работало", "проверь перед ночью", "перекличка", "ready for overnight".
argument-hint: "[task folder]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(date*) Read Write ToolSearch
---

# Nightcall: ready for the night?

The person said: $ARGUMENTS

Answer in the person's language. The person is still here: this is the last moment anything can be
signed in, allowed or clicked.

## 1. The computer

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ready.py" --dir "<task folder, if there is one>"
```

(`python3` missing on Windows: try `py -3`, then `python`.)

Show the result as three groups, short:

- **НЕ — исправить сейчас.** Each with its one action. Help the person do it right now, one at a
  time, and run the check again after. These are the reasons a night silently does nothing.
- **СЛЕДИТЕ — посмотрите своими глазами.** Things the script cannot read from here (the lid, the
  permission mode of this window, the Claude limit). One line each.
- **ОК** — one line in total: «Остальное в порядке: питание, сеть, место…».

The one to stress every time: **permissions**. Ask the person to switch this window to a mode that
does not stop to ask (Shift+Tab until auto or accept edits) and prove it with one real step while
they are still here. A night that stopped at 23:05 on «Разрешить?» looks in the morning exactly like
a night that did nothing.

## 2. The roll call of helpers

Do `/nightcall:team` §1 in full, with `<seats>` = `<task folder>/seats.json`:

a) `team.py rollcall` — a table of every CLI by subscription and free key: жив / лимит (до ЧЧ:ММ) /
   не вошли / нет программы;
b) the browser: Claude in Chrome connected (switch it on if only the enable tool is there), one new
   tab opens, each web chat (ChatGPT, Gemini, Kimi, DeepSeek, Meta AI…) checked one at a time — an
   input field, not a sign-in screen or a captcha, and a short test question answered. Any
   «Разрешить» or confirmation — **ask the person to press it now**;
c) `team.py summary` — «Ночью работают: …; запас: …; не работает: … — что сделать сейчас».

No live helper of another company at all → say that the night will run with Claude's own critics
only, and offer to fix one thing (sign in, press, install) before the person leaves. Then run
`ready.py` once more: it reads `seats.json` too.

If the person wants the phone to see the night's progress, and the Poly A1 plugin `pocketcall` is
installed, offer its `leave` skill after this list.
