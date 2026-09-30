# Nightcall

**Leave Claude Code working through the night on your task — and find a report in the morning.**

You tell Claude what to do and go to bed. Claude writes a plan, keeps the computer awake,
works step by step, checks and criticises its own work, asks other AIs you already have for a
second head — and in the morning you read what was done, what was not, and what to look at first.

```
/nightcall:start Разбери все мои заметки в папке «Идеи», собери из них план книги на 12 глав и черновик первой главы. 8 часов.
```

## Install

```
/plugin marketplace add vadimchernets/nightcall
/plugin install nightcall@nightcall
```

## What is inside

| Skill | What it does |
|---|---|
| `/nightcall:start <task> [8\|12]` | The night shift: five minutes with you before you leave, then plan → step → check → self-critique → progress file, all night. |
| `/nightcall:awake 8` · `12` · `stop` | Coffee for the computer: Mac, Linux or Windows, no admin rights, switches itself off. |
| `/nightcall:team` | Which other AIs are alive tonight; dead ones are replaced; no programs → free web chats in the browser. |
| `/nightcall:ready` | The checklist before leaving: power, lid, updates, network, disk, permissions, limits. |
| `/nightcall:morning` | `MORNING.md`: done / not done / check first / decided without you. Switches everything off. |

## Coffee on its own (no Claude needed)

```
bash scripts/awake.sh 8          # Mac or Linux: 8 hours (12, 10h, 30m, status, stop)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\awake-windows.ps1 -Hours 12   # Windows
```

| System | How | Ends by itself |
|---|---|---|
| macOS | `caffeinate -dimsu -t <seconds>` (`NIGHTCALL_SCREEN=off` lets the screen go dark) | yes |
| Linux | `systemd-inhibit --what=idle:sleep:handle-lid-switch sleep <seconds>`, then `gnome-session-inhibit`, then a screensaver nudge | yes |
| Windows | hidden PowerShell holding `SetThreadExecutionState(ES_CONTINUOUS \| ES_SYSTEM_REQUIRED \| ES_DISPLAY_REQUIRED)` | yes |

What coffee does not cover, on any system: a **closed laptop lid** (sleep anyway — leave it open),
a **battery** running down (plug in), **system updates** that restart at night (pause them for the
night). `/nightcall:ready` checks what can be checked.

## Helper AIs

Claude is the main agent. Helpers are programs of **other companies** you already have by
subscription: `codex` (ChatGPT), `agy`/`gemini`, `grok`, `kimi`, `qwen`. Each is checked with a
short question before the night; one out of allowance or not signed in is skipped, and the next
live one gets the question. No programs at all → Claude opens free chats in your browser, pastes
the question and takes the answer back.

```
python3 scripts/team.py probe --out seats.json
echo "Чего не хватает в этом плане?" | python3 scripts/team.py ask --seats seats.json -
```

## The sturdiest night: the loop

One long session can die: the window closes, the limit runs out at 3 a.m. The loop starts a fresh
Claude for every step; the plan and progress files carry the night, and when the limit runs out it
waits and continues:

```
bash scripts/night-loop.sh "<task folder>" 8
```

Stops by itself at the end time, on `MORNING.md`, on a file named `STOP` in the folder, or at
`NIGHTCALL_MAX_ROUNDS` (60). Permission mode: `NIGHTCALL_PERMISSION_MODE` (default `auto`).

## Principles

- Files carry the night, not memory: `TASK.md`, `PLAN.md`, `PROGRESS.md`, `MORNING.md`.
- "Done" is a check, not a feeling. Three failed attempts → the step is marked and skipped.
- A decision that needed you is taken with a sensible default and listed under «Проверить утром».
- No keys, no paid API, nothing bought, no passwords in files.

## License

Apache-2.0. Ideas borrowed from open source are credited in [NOTICE](NOTICE).
