---
name: start
description: Put Claude to work for the whole night on the person's task - plan and progress file in a task folder, the computer kept awake for 8 or 12 hours, work step by step with self-critique, other AIs of other companies brought in (their own subscription programs first, free browser chats if none), dead helpers replaced, and a morning report of what was done, what was not and what to check. Use when the person says "работай ночью", "поработай, пока я сплю", "ночная работа", "work overnight", "keep going while I sleep", "до утра", or gives a big task and says they are leaving for the night.
argument-hint: "<the task in your own words> [8|12 hours]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(date*) Bash(git *) Read Write Edit Glob Grep
---

# Nightcall: the night shift

The person said: $ARGUMENTS

Answer in the person's language. You are the **main agent for the night**. The person is about to
go to sleep: from the moment they leave, nobody will answer a question, press "Yes" or fix a
setting. Everything that needs them happens in the next five minutes, before they go.

## 0. Before they leave — five minutes, in this order

1. **The task in one sentence and the finish line.** Repeat the task back in one sentence and say
   what "done by morning" means — a thing that can be checked (a file exists, tests pass, a document
   of N sections, a list of 30 sources). If the person's words already say it, do not ask; state it.
   If something is truly unclear, ask **one** question with your default in it: «Если не ответите
   за 2 минуты — делаю так: …». Silence means go.

2. **How long.** 8 or 12 hours, or their own number. Default 8. Say until what time: `date`.

3. **The folder.** A task folder named `ночь-<date>-<short-name>` next to where the work is (or
   the folder the person named). Open the night:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/night.py" begin --dir "<folder>" --hours <H>
   ```
   with the person's task **word for word** on standard input — it becomes `TASK.md`, next to an
   empty `PLAN.md` and `PROGRESS.md`. Write the plan now (§1), while the person can still glance at it.
   If the work is code and the folder is not under git, run `git init` there and commit the start —
   one commit per step lets the person undo any step in the morning.

4. **The checklist.** Run `/nightcall:ready` (or `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ready.py" --dir "<folder>"`).
   Every НЕ is fixed **now**, with the person, while they are still here. Show СЛЕДИТЕ lines
   as one short list.

5. **Coffee.** Keep the computer awake: `/nightcall:awake <H>` — Mac, Linux or Windows is picked
   for you. It switches itself off at the end time.

6. **Permissions — the one that kills most nights.** Tell the person, plainly: «Один вопрос
   „разрешить?“ ночью остановит всю работу до утра.» Ask them to switch this window to a mode that
   does not stop to ask (Shift+Tab until **auto** mode, or **accept edits**), and then do one real
   step of the plan in front of them to prove no question pops up. For the sturdiest night — a fresh
   Claude for every step that survives a closed window and waits out the subscription limit — offer
   the loop instead:
   ```
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/night-loop.sh" "<folder>" <H>
   ```
   run in a separate terminal (Mac/Linux; on Windows from Git Bash or WSL).

7. **The team.** `/nightcall:team` — which other AIs are alive tonight. Results go to
   `<folder>/seats.json`. None alive is not a stop: helpers then come through free browser chats.

8. **Say goodbye with the facts:** until what time the computer stays awake, how many steps are in
   the plan, which helpers are alive, where the morning report will be (`<folder>/MORNING.md`), and
   how to stop everything early (a file named `STOP` in the folder). Then arm the night — from here
   on a finished turn goes straight back to the next step (§4):
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/night.py" arm --dir "<folder>" --hours <H>
   ```
   and start working — do not wait for a reply. (With the loop script instead, do not arm: the loop
   itself starts a fresh Claude for every step.)

## 1. The plan — before the first step

Write `PLAN.md`: 5–20 steps, each one **a checkable thing**, with its own "done when…" column.
Order: what the rest depends on first; risky and unclear things early, while there is time to go
around them. A step that cannot be checked is two steps or a wrong step. The plan is fixed: during
the night you may **add** steps and **mark** steps as skipped with a reason, but never quietly
change what "done" means (Anthropic, "Effective harnesses for long-running agents").

For a large plan, show it to one live helper (§3) with the question «Чего не хватает в этом плане и
какой шаг самый рискованный?» and fold in what holds up. One round, not a debate.

## 2. Every step — the same loop

1. `date` — every step starts with the real time. Check it against the end time; the last hour is
   for finishing and the report, not for new big things.
2. Read `PROGRESS.md` (the last lines are where you are) and the next step in `PLAN.md`.
3. Do the step fully. Real results only: a file you wrote, a command you ran, a page you read.
4. **Check it by its "done when…"**: run the test, open the file, count the items.
5. **Self-critique.** Read the result as a strict reviewer who did not write it: what is wrong,
   missing, invented, unverified? For an important step, get a **fresh pair of eyes** — a sub-agent
   with no memory of your reasoning, or a live helper of another company (§3). Fix what holds up
   **once**. Perfectionist reviewers never say "ok"; the check against "done when…" closes a step,
   not the reviewer's mood.
6. **Write it down** in `PROGRESS.md`: time · step · what was done · how it was checked · what is
   next. If the folder is under git: one commit per step, the message says what and why.
7. Mark the step in `PLAN.md` and go straight to the next one.

**Stuck rule.** Three honest attempts at a step without success → mark it «не вышло: <why>», write
what you tried, and move on to the next step. One stuck step must not eat the night.

**Nobody to ask.** A decision that would normally be the person's: take the reasonable default,
do it, and put it in «Проверить утром» in `PROGRESS.md` with the value you chose. Never stop and
wait for an answer.

**Nothing is deleted at night** that cannot be brought back: move to a `_убрано/` folder instead,
or rely on the git commit.

## 3. Other AIs — helpers, not a decoration

Use them where a second head changes the result: the plan, a hard decision, a finished part of
the text or code, facts you are not sure of. Not on every sentence.

**First — programs already on this computer** (the person's own subscriptions, no extra cost):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team.py" ask --seats "<folder>/seats.json" --dir "<folder>" -
```
with the question on standard input. Ask the question **as a question** — never paste your own
answer into it: an AI shown an answer agrees with it. Give it the paths of the files to read, not
their contents, when they are in `<folder>`.

The script walks down the live helpers of other companies: if the first one is out of allowance,
not signed in or silent, the next one gets the same question, and the dead one is marked in
`seats.json` so the rest of the night does not wait on it again. Every two or three hours, or after
a helper dies, re-check who is alive: `/nightcall:team` — allowances come back.

**None alive — through the browser.** Follow `/nightcall:team`, section "Через браузер": open a free
chat of another company in the person's browser, paste the question, wait for the full answer, take
it off the page. If the Poly A1 folder `Poly nov/agent/` is next to this plugin, its files are the
detailed method (`05-fan-out.md` to paste, `07-collect-answers.md` to take the answer).

**Write down every answer that changed something** in `PROGRESS.md`, with who said it. A helper that
did not answer is written down too: «Grok — кончился запас, заменён Kimi». A pair that did not happen
is said out loud, never faked by asking yourself twice.

## 4. Keeping the night going

While the night is open, this plugin's Stop hook sends the session back to the next step each time
you finish a turn — until the end time, `MORNING.md`, or a `STOP` file. So **do not end a turn
with a question to the person**: they are asleep. End it by doing the next step.

If the Claude subscription limit runs out, the session pauses; the loop script (§0.6) waits and
continues by itself. In a plain session, the person will see where it stopped in `PROGRESS.md`.

## 5. Morning

When every step is done, or at the end time: `/nightcall:morning`. It writes `MORNING.md`,
closes the night and switches the coffee off.

## What never happens at night

- No passwords, keys or card numbers are written into any file, and none are asked for.
- Nothing is bought, no paid API is used: only the person's subscriptions and free web chats.
- Nothing is sent to other people (mail, messages, posts) unless that was the task.
- No success is claimed that is not in `PROGRESS.md` with how it was checked.
