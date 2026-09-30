---
name: morning
description: Close the night and write the morning report MORNING.md in the task folder - what was done (with how it was checked), what was not done and why, what the person should check first, which decisions were taken without them, which helper AIs took part - built only from PROGRESS.md, PLAN.md and git log, never from memory. Then switches the coffee off. Use at the end of a night run, when the person says "что сделано за ночь", "утренний отчёт", "morning report", "доброе утро, что там".
argument-hint: "[task folder]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(powershell *) Bash(git *) Bash(date*) Read Write
---

# Nightcall: good morning

The person said: $ARGUMENTS

Answer in the person's language. Find the night folder: the argument, or `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/night.py" status`.

## 1. Read, do not remember

Read `TASK.md`, `PLAN.md`, `PROGRESS.md`, and `git log --oneline` if the folder is under git.
The report is built **only** from these. A step with no line in `PROGRESS.md` saying how it was
checked is not "done" — it is «сделано, не проверено».

## 2. Write `MORNING.md`

```
# Утро: <task in one line>
Ночь: <start> – <end>. Шагов в плане: N. Сделано: X. Не сделано: Y.

## Сделано
- <step> — <result, where it is> — проверено: <how>

## Не сделано
- <step> — <why: stuck after 3 tries / no time / waits for you> — <what was tried>

## Проверьте сначала (5 минут)
1. <the most important thing to look at with your own eyes, with the file/path>
2. …

## Решено без вас
- <decision> — выбрано: <value> — поменять: <how>

## Помощники
- <who answered, who fell out and why, who replaced whom>

## Дальше
- <the next step if the person wants to continue tonight>
```

"Проверьте сначала" is the most useful part: at most five items, the riskiest first, each one
something the person can open and look at.

## 3. Close the night

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/night.py" end
bash "${CLAUDE_PLUGIN_ROOT}/scripts/awake.sh" stop
```
(Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/awake-windows.ps1" -Stop`.)

## 4. Tell the person

Three lines, not the whole file: how many steps done out of how many, the first thing to check,
and the path to `MORNING.md`. No "everything went great" that the file does not show.
