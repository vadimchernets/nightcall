# Nightcall

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23107725.svg)](https://doi.org/10.5281/zenodo.23107725)

**Leave Claude Code working through the night on your task — and find a report in the morning.**

You tell Claude what to do and go to bed. Claude writes a plan, keeps the computer awake,
works step by step, checks and criticises its own work, asks other AIs you already have for a
second head — and in the morning you read what was done, what was not, and what to look at first.

```
/nightcall:start Go through all my notes in the "Ideas" folder, build a 12-chapter book outline from them, and draft the first chapter. 8 hours.
```

## Install

```
/plugin marketplace add https://raw.githubusercontent.com/vadimchernets/poly-a1-plugins/main/.claude-plugin/marketplace.json
/plugin install nightcall@poly-a1
```

The first line adds Poly A1's catalogue by its link - one file, no git and no GitHub account - and
later corrections reach you from the same place (Claude Code 2.1.224 or later; `claude update`). If
`poly-a1` is already there, from the Poly A1 folder or from before, skip it: the second line is enough.

Without internet, from the Poly A1 folder:

```
/plugin marketplace add <path to the Poly A1 folder>
/plugin install nightcall@poly-a1
```

Once there is internet, the folder is switched to the link in place, keeping everything installed
([how](https://github.com/vadimchernets/poly-a1-plugins/blob/main/OFFER-THESE.md#later-from-the-folder-to-github-without-losing-anything)). Never `/plugin marketplace remove poly-a1`: it uninstalls every plugin that came from
it and deletes their saved data.

## What is inside

| Skill | What it does |
|---|---|
| `/nightcall:start <task> [8\|12]` | The night shift: five minutes with you before you leave, then plan → step → check → self-critique → progress file, all night. |
| `/nightcall:awake 8` · `12` · `stop` | Coffee for the computer: Mac, Linux or Windows, no admin rights, switches itself off. |
| `/nightcall:team` | Which other AIs are alive tonight; dead ones are replaced; no programs → free web chats in the browser. |
| `/nightcall:ready` | The checklist before leaving: power, lid, updates, network, disk, permissions, limits. |
| `/nightcall:family` | The family relay: when one person's limit runs out, the next family member's own account carries the night or the weekend on. |
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

Three things you set by hand before you leave: the **laptop lid** open, the **charger** plugged in,
**system updates** paused for the night. `/nightcall:ready` walks you through them.

## Helper AIs

Claude is the main agent. Helpers are AIs of **other companies** you already have.

**The roll call — before you leave** (`/nightcall:ready`, and the first step of `/nightcall:start`):

1. every program by subscription — `codex` (ChatGPT), `agy`/`gemini`, `grok`, `kimi`, `qwen` — and
   every free key you set up (the course lesson "Free AI keys": NVIDIA — Kimi K3 and GLM-5.3 on one key,
   Google AI Studio, Groq, OpenRouter) gets a test question — several models per key, the next one on
   429/503/404/timeout: **alive / limit (until HH:MM) / not-signed-in / not installed**;
2. Chrome: Claude in Chrome connected, a tab opens, and each web chat you use (ChatGPT, Gemini,
   Kimi, DeepSeek, Meta AI…) shows an input field and answers a test question — or is marked
   "needs-sign-in" / "captcha". Anything to allow or sign in, you do now, not at night;
3. "Working tonight: …; reserve: …; not working: … — what to do now".

**At night** the order is fixed: a live program → the next program → free keys → a web chat that
passed the roll call (one site at a time, no passwords) → Claude's own critics. Every replacement is
a line in `PROGRESS.md`; a program at its limit comes back after the reset time; `MORNING.md` says
who really took part. Your one choice at the roll call: `web: night` (default — web chats are the
night reserve) or `web: morning` (`team.py web-when --seats seats.json morning`) — then a question
meant for a web chat is saved in `morning-advice.md` for the morning.

**Decisions that are usually yours** — one more choice before you leave, default "the AI council decides":

- `council` (default) — Claude asks the live AIs (other companies, then its own critics), decides,
  and the night does not stop. It weighs the answers **blind** — "Answer A / B / C", no company or
  model names (`team.py ask --blind DIR`, then `team.py blind --dir DIR`); names come out only after
  the decision (`team.py reveal --dir DIR`): a judge AI leans to the answer that sounds like itself. Each such decision is its own commit and an entry in `decisions.md`
  (what, why, who advised, the other options); in the morning **"Needs your decision"** lists them, each
  with its own `git revert <commit>` and "fix it like this: …".
- `morning` — such a fork is not decided: the step waits with a question, the night goes on with
  other steps; in the morning you answer, and `/nightcall:morning` gives one line to finish:
  `/nightcall:start continuation: …; answers: …`.

Never decided at night, in either mode: sending, publishing, paying, deleting with no way back,
signing in with a password.

**Every night has a safety net, made by itself:** `night.py begin` makes a restore point in the task
folder (no git → `git init` + a commit "before the night"; git → a commit + a tag `nightcall-before-<time>`)
and writes the fence rule into the folder's `CLAUDE.md`: work only inside this folder. The night is
bound to the Claude Code window that started it (`arm --session`), never to another open window.
The morning report starts with **"Needs your decision"**, then done / not done / to check / who took part.

```
python3 scripts/team.py rollcall --out seats.json
python3 scripts/team.py web-mark --seats seats.json --site chatgpt --status alive
python3 scripts/team.py web-when --seats seats.json night      # or morning
python3 scripts/team.py decide-when --seats seats.json council   # or morning
python3 scripts/team.py summary --seats seats.json
echo "What's missing from this plan?" | python3 scripts/team.py ask --seats seats.json --progress PROGRESS.md -
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

## The family relay: the weekend goes on

A family (or a family team) leaves for the weekend with a task running. When Dad's subscription runs
out on Saturday morning, the loop does not wait until it comes back: the next round runs in Son's own
account, the one Son signed in to himself, and so on through everyone who said yes. The context moves,
the access never does - the task lives in TASK.md, PLAN.md and PROGRESS.md, every member's sign-in
stays in their own Claude Code folder (`CLAUDE_CONFIG_DIR`; `CODEX_HOME` for a Codex subscription).

```
python3 scripts/family.py add --name Dad --email dad@example.com --config-dir default
python3 scripts/family.py add --name Son --email son@example.com      # prints Son's one sign-in command
python3 scripts/family.py consent --name Son --by Son --until "2026-10-12 09:00"
python3 scripts/family.py check                                        # who is really signed in where
NIGHTCALL_MAX_ROUNDS=400 bash scripts/night-loop.sh "<task folder>" 60
```

Before each change of hands the loop asks the vendor's CLI who is signed in in that member's folder
and takes only the account the member named. Every change is a "Relay" line in PROGRESS.md and in
`~/.nightcall/family-log.jsonl`; `/nightcall:morning` lists it under "Who took part".

## Principles

- Files carry the night, not memory: `TASK.md`, `PLAN.md`, `PROGRESS.md`, `MORNING.md`.
- "Done" is a check, not a feeling. Three failed attempts → the step is marked and skipped.
- A decision that needed you: by the council of AIs (its own commit, undo in the morning) or left for your morning answer — your choice before the night.
- No keys, no paid API, nothing bought, no passwords in files.

## License

Apache-2.0. Ideas borrowed from open source are credited in [NOTICE](NOTICE).
