---
name: morning
description: Close the night and write the morning report MORNING.md in the task folder - first what needs the person's decision (defaults taken at night, open questions), then what was done (with how it was checked), what was not done and why, what to check, which helper AIs took part - built only from PROGRESS.md, PLAN.md and git log, never from memory. Then switches the coffee off. Use at the end of a night run, when the person says "что сделано за ночь", "утренний отчёт", "morning report", "доброе утро, что там".
argument-hint: "[task folder]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(powershell *) Bash(git *) Bash(date*) Read Write
---

# Nightcall: good morning

The person said: $ARGUMENTS

Answer in the person's language. Find the night folder: the argument, or `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/night.py" status`.

## 1. Read, do not remember

Read `TASK.md`, `PLAN.md`, `PROGRESS.md`, `решения.md` and `утро-совет.md` if they are there, and `git log --oneline` if the folder is under git.
Who of the helpers really answered: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" used --seats
"<folder>/seats.json"` (program, key or web chat, and how many answers).
The report is built **only** from these. A step with no line in `PROGRESS.md` saying how it was
checked is not "done" — it is «сделано, не проверено».

## 2. Write `MORNING.md`

The order is fixed: what needs the person comes **first**.

```
# Утро: <task in one line>
Ночь: <start> – <end>. Шагов в плане: N. Сделано: X. Не сделано: Y.

## Нужно Ваше решение
- Решил совет ИИ: <what> — почему: <why> — советовали: <who> — отменить: `git revert <hash>` — или исправить так: «…» (each entry of решения.md, mode `council`)
- Ждёт Вашего ответа: <question> — варианты: <…> — без ответа стоит: <what waits> (each `hold` entry; mode `morning` and the never-at-night list)
- <a default taken at night outside решения.md> — выбрано: <value> — поменять: <how> (from «Проверить утром» in PROGRESS.md)
- Вопросы для веб-чатов, отложенные на утро: `утро-совет.md` (<how many>) — only if the file exists

## Сделано
- <step> — <result, where it is> — проверено: <how>

## Не сделано
- <step> — <why: stuck after 3 tries / no time / waits for you> — <what was tried>

## Проверить (5 минут)
1. <the most important thing to look at with your own eyes, with the file/path>
2. …
Точка возврата: <the git tag / copy from CLAUDE.md of the folder> — откатить: <command>.

## Кто участвовал
- <who really answered (from `team.py used`), who fell out and why, who replaced whom, whose limit came back when>
- Дальше, если продолжать сегодня ночью: <the next step>
```

«Нужно Ваше решение» is never left out: nothing to decide → one line «решений без вас не было».
Questions waiting for an answer → end the section with one line to finish the work:
`/nightcall:start продолжение: <task>; ответы: 1) … 2) …` — the person fills in the answers and the
next run (day or night) finishes the paused steps.
«Проверить» is the most useful part after it: at most five items, the riskiest first, each one
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
