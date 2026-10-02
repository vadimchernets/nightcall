---
name: morning
description: Close the night and write the morning report MORNING.md in the task folder - first what needs the person's decision (defaults taken at night, open questions), then what was done (with how it was checked), what was not done and why, what to check, which helper AIs took part - built only from PROGRESS.md, PLAN.md and git log, never from memory. Then switches the coffee off. Use at the end of a night run, when the person says "what got done overnight", "morning report", "good morning, what's there" (in any language).
argument-hint: "[task folder]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(powershell *) Bash(git *) Bash(date*) Read Write
---

# Nightcall: good morning

The person said: $ARGUMENTS

Answer in the person's language. Find the night folder: the argument, or `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/night.py" status`.

## 1. Read, do not remember

Read `TASK.md`, `PLAN.md`, `PROGRESS.md`, `decisions.md` (or its older/localized name `решения.md`,
from before nightcall 0.3.4) and `morning-advice.md` (older/localized name `утро-совет.md`) if they
are there, and `git log --oneline` if the folder is under git.
Who of the helpers really answered: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" used --seats
"<folder>/seats.json"` (program, key or web chat, and how many answers).
The report is built **only** from these. A step with no line in `PROGRESS.md` saying how it was
checked is not "done" — it is "done, not checked".

## 2. Write `MORNING.md`

The order is fixed: what needs the person comes **first**.

```
# Morning: <task in one line>
Night: <start> – <end>. Steps in the plan: N. Done: X. Not done: Y.

## Needs your decision
- The AI council decided: <what> — why: <why> — advised by: <who> — undo: `git revert <hash>` — or fix it like this: "…" (each entry of decisions.md, mode `council`)
- Waiting for your answer: <question> — options: <…> — on hold without an answer: <what waits> (each `hold` entry; mode `morning` and the never-at-night list)
- <a default taken at night outside decisions.md> — chosen: <value> — to change it: <how> (from "Check in the morning" in PROGRESS.md)
- Questions for web chats, left for the morning: `morning-advice.md` (<how many>) — only if the file exists

## Done
- <step> — <result, where it is> — checked: <how>

## Not done
- <step> — <why: stuck after 3 tries / no time / waits for you> — <what was tried>

## Check (5 minutes)
1. <the most important thing to look at with your own eyes, with the file/path>
2. …
Restore point: <the git tag / copy from CLAUDE.md of the folder> — roll back: <command>.

## Who took part
- <who really answered (from `team.py used`), who fell out and why, who replaced whom, whose limit came back when>
- Next, if continuing tonight: <the next step>
```

"Needs your decision" is never left out: nothing to decide → one line "no decisions were made without you".
Questions waiting for an answer → end the section with one line to finish the work:
`/nightcall:start continuation: <task>; answers: 1) … 2) …` — the person fills in the answers and the
next run (day or night) finishes the paused steps.
"Check" is the most useful part after it: at most five items, the riskiest first, each one
something the person can open and look at.

## 3. Close the night

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/night.py" end
bash "${CLAUDE_PLUGIN_ROOT}/scripts/awake.sh" stop
```
(Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/awake-windows.ps1" -Stop`.)

## 4. Tell the person

Three lines, not the whole file: how many steps done out of how many, how many decisions the
council took (each can be undone) or how many questions wait for them, and the path to `MORNING.md`. No "everything went great" that the file does not show.
