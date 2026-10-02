# Nightcall

**Leave Claude Code working through the night on your task — and find a report in the morning.**

You tell Claude what to do and go to bed. Claude writes a plan, keeps the computer awake,
works step by step, checks and criticises its own work, asks other AIs you already have for a
second head — and in the morning you read what was done, what was not, and what to look at first.

```
/nightcall:start Разбери все мои заметки в папке «Идеи», собери из них план книги на 12 глав и черновик первой главы. 8 часов.
```

## Install

From the Poly A1 folder (nothing downloaded):

```
/plugin marketplace add <path to the Poly A1 folder>
/plugin install nightcall@poly-a1
```

From this folder on its own:

```
/plugin marketplace add <path to the nightcall folder>
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

Claude is the main agent. Helpers are AIs of **other companies** you already have.

**The roll call — before you leave** (`/nightcall:ready`, and the first step of `/nightcall:start`):

1. every program by subscription — `codex` (ChatGPT), `agy`/`gemini`, `grok`, `kimi`, `qwen` — and
   every free key you set up (the course lesson «Бесплатные ключи ИИ»: NVIDIA — Kimi K3 and GLM-5.3 on one key,
   Google AI Studio, Groq, OpenRouter) gets a test question — several models per key, the next one on
   429/503/404/timeout: **жив / лимит (до ЧЧ:ММ) / не вошли / нет программы**;
2. Chrome: Claude in Chrome connected, a tab opens, and each web chat you use (ChatGPT, Gemini,
   Kimi, DeepSeek, Meta AI…) shows an input field and answers a test question — or is marked
   «нужен вход» / «капча». Anything to allow or sign in, you do now, not at night;
3. «Ночью работают: …; запас: …; не работает: … — что сделать сейчас».

**At night** the order is fixed: a live program → the next program → free keys → a web chat that
passed the roll call (one site at a time, no passwords) → Claude's own critics. Every replacement is
a line in `PROGRESS.md`; a program at its limit comes back after the reset time; `MORNING.md` says
who really took part. Your one choice at the roll call: `web: night` (default — web chats are the
night reserve) or `web: morning` (`team.py web-when --seats seats.json morning`) — then a question
meant for a web chat is saved in `утро-совет.md` for the morning.

**Decisions that are usually yours** — one more choice before you leave, default «решает совет ИИ»:

- `council` (default) — Claude asks the live AIs (other companies, then its own critics), decides,
  and the night does not stop. It weighs the answers **blind** — «Ответ A / B / C», no company or
  model names (`team.py ask --blind DIR`, then `team.py blind --dir DIR`); names come out only after
  the decision (`team.py reveal --dir DIR`): a judge AI leans to the answer that sounds like itself. Each such decision is its own commit and an entry in `решения.md`
  (what, why, who advised, the other options); in the morning «Нужно Ваше решение» lists them, each
  with its own `git revert <commit>` and «исправить так: …».
- `morning` — such a fork is not decided: the step waits with a question, the night goes on with
  other steps; in the morning you answer, and `/nightcall:morning` gives one line to finish:
  `/nightcall:start продолжение: …; ответы: …`.

Never decided at night, in either mode: sending, publishing, paying, deleting with no way back,
signing in with a password.

**Every night has a safety net, made by itself:** `night.py begin` makes a restore point in the task
folder (no git → `git init` + a commit «перед ночью»; git → a commit + a tag `nightcall-before-<time>`)
and writes the fence rule into the folder's `CLAUDE.md`: work only inside this folder. The night is
bound to the Claude Code window that started it (`arm --session`), never to another open window.
The morning report starts with **«Нужно Ваше решение»**, then done / not done / to check / who took part.

```
python3 scripts/team.py rollcall --out seats.json
python3 scripts/team.py web-mark --seats seats.json --site chatgpt --status жив
python3 scripts/team.py web-when --seats seats.json night      # or morning
python3 scripts/team.py decide-when --seats seats.json council   # or morning
python3 scripts/team.py summary --seats seats.json
echo "Чего не хватает в этом плане?" | python3 scripts/team.py ask --seats seats.json --progress PROGRESS.md -
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
- A decision that needed you: by the council of AIs (its own commit, undo in the morning) or left for your morning answer — your choice before the night.
- No keys, no paid API, nothing bought, no passwords in files.

## License

Apache-2.0. Ideas borrowed from open source are credited in [NOTICE](NOTICE).

---

Note: some web services' terms of use are against automated use — that is why web chats are only the reserve by default, and you see the list in the roll call before the night.
