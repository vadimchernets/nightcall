#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall Stop hook: while a night run is on, the session does not simply stop.

The Ralph-loop idea (github.com/anthropics/claude-code, plugins/ralph-wiggum): when Claude
finishes a turn, a Stop hook can send it back to work. Here it only does so while ALL of these hold:

  * ~/.nightcall/active.json exists (written by /nightcall:start, removed by /nightcall:morning);
  * the run belongs to THIS session (the first stop binds the session id; other windows are free);
  * the night's end time has not passed;
  * the task folder has no MORNING.md (the report means the night is over) and no STOP file
    (the person's own off switch: create a file named STOP in the task folder);
  * fewer than `max_rounds` rounds were sent back (a ceiling, so it can never spin forever).

Everything else lets the session stop as usual. Any error here also lets it stop.
"""

import datetime
import json
import os
import sys


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    home = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
    path = os.path.join(home, "active.json")
    try:
        with open(path, encoding="utf-8") as fh:
            run = json.load(fh)
    except Exception:
        return 0

    session = event.get("session_id", "")
    if run.get("session") and session and run["session"] != session:
        return 0
    folder = run.get("folder", "")
    if not folder or not os.path.isdir(folder):
        return 0
    if os.path.exists(os.path.join(folder, "MORNING.md")) or os.path.exists(os.path.join(folder, "STOP")):
        return 0
    try:
        until = datetime.datetime.fromisoformat(run["until"])
    except Exception:
        return 0
    if datetime.datetime.now() >= until:
        reason = ("Ночь кончилась по времени. Напиши утренний отчёт: выполни /nightcall:morning "
                  f"для папки {folder}.")
        # one last round to write the report, then never again
        if run.get("final_sent"):
            return 0
        run["final_sent"] = True
    else:
        rounds = int(run.get("rounds", 0))
        if rounds >= int(run.get("max_rounds", 200)):
            return 0
        run["rounds"] = rounds + 1
        reason = (f"Ночная работа ещё идёт (до {until:%H:%M}). Не останавливайся и ничего не спрашивай "
                  f"у человека — он спит. Открой {folder}/PROGRESS.md, возьми следующий шаг из PLAN.md, "
                  "сделай его, проверь, запиши итог в PROGRESS.md. Если все шаги сделаны — выполни "
                  "/nightcall:morning. Спорное решение — прими с разумным значением по умолчанию и "
                  "запиши в «Проверить утром».")
    if session and not run.get("session"):
        run["session"] = session
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(run, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
