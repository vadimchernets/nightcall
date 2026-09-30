#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall night: open and close a night run.

    python3 night.py begin --dir <task folder> --hours 8      # task text on stdin; files only
    python3 night.py arm   --dir <task folder> --hours 8 [--max-rounds 200]   # the person has left
    python3 night.py status
    python3 night.py end

`begin` creates the task folder with TASK.md (the person's words, as given), a PLAN.md and a
PROGRESS.md skeleton if they are not there yet. `arm` - said when the person has left - writes
~/.nightcall/active.json, the switch the Stop hook reads to keep the session working until the end
time. They are separate on purpose: while the person is still here, a turn that ends with a
question to them must be allowed to end. `end` removes the switch.
Nothing else on the computer is touched.
"""

import argparse
import datetime
import json
import os
import sys

HOME = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
ACTIVE = os.path.join(HOME, "active.json")

PLAN = """# План на ночь

Задание — в TASK.md. Каждый шаг — одно проверяемое дело. «Готово» — это проверка, а не ощущение.

| # | Шаг | Готово, когда… | Статус |
|---|-----|----------------|--------|
| 1 |     |                | ждёт   |
"""

PROGRESS = """# Ход ночи

Начато: {start}. Конец не позже: {until}.

## Журнал
<!-- после каждого шага: время (date) · шаг · что сделано · как проверено · что дальше -->

## Помощники
<!-- кто из других ИИ жив, кто выпал и почему, кем заменён -->

## Проверить утром
<!-- спорные решения, принятые без человека, с тем значением, которое выбрано -->
"""


def cmd_begin(a):
    folder = os.path.abspath(os.path.expanduser(a.dir))
    os.makedirs(folder, exist_ok=True)
    now = datetime.datetime.now().replace(second=0, microsecond=0)
    until = now + datetime.timedelta(hours=a.hours)
    task = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
    made = []
    if task and not os.path.exists(os.path.join(folder, "TASK.md")):
        with open(os.path.join(folder, "TASK.md"), "w", encoding="utf-8") as fh:
            fh.write("# Задание на ночь (словами человека)\n\n" + task + "\n")
        made.append("TASK.md")
    for name, body in (("PLAN.md", PLAN), ("PROGRESS.md", PROGRESS)):
        p = os.path.join(folder, name)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(body.format(start=f"{now:%d.%m %H:%M}", until=f"{until:%d.%m %H:%M}"))
            made.append(name)
    print(f"Папка ночи готова: {folder}")
    print(f"  создано: {', '.join(made) or 'ничего, файлы уже были'}")
    return 0


def cmd_arm(a):
    folder = os.path.abspath(os.path.expanduser(a.dir))
    if not os.path.exists(os.path.join(folder, "PLAN.md")):
        print(f"В {folder} нет PLAN.md — сначала begin и план.")
        return 2
    now = datetime.datetime.now().replace(second=0, microsecond=0)
    until = now + datetime.timedelta(hours=a.hours)
    os.makedirs(HOME, exist_ok=True)
    with open(ACTIVE, "w", encoding="utf-8") as fh:
        json.dump({"folder": folder, "started": now.isoformat(timespec="minutes"),
                   "until": until.isoformat(timespec="minutes"), "max_rounds": a.max_rounds,
                   "rounds": 0}, fh, ensure_ascii=False, indent=2)
    print(f"Ночь идёт: {folder} до {until:%H:%M %d.%m}. Сессия сама возвращается к следующему шагу.")
    print(f"  Выключатель: файл STOP в этой папке или `python3 {os.path.abspath(__file__)} end`.")
    return 0


def cmd_status(_):
    try:
        run = json.load(open(ACTIVE, encoding="utf-8"))
    except Exception:
        print("Ночной работы сейчас нет.")
        return 1
    print(f"Ночная работа идёт: {run['folder']} до {run['until']}, кругов {run.get('rounds', 0)}.")
    return 0


def cmd_end(_):
    if os.path.exists(ACTIVE):
        os.remove(ACTIVE)
        print("Ночь закрыта: сессия больше не возвращается к работе сама.")
    else:
        print("Ночной работы и так не было.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall: открыть и закрыть ночь.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("begin")
    b.add_argument("--dir", required=True)
    b.add_argument("--hours", type=float, default=8)
    r = sub.add_parser("arm")
    r.add_argument("--dir", required=True)
    r.add_argument("--hours", type=float, default=8)
    r.add_argument("--max-rounds", type=int, default=200)
    sub.add_parser("status")
    sub.add_parser("end")
    a = ap.parse_args(argv)
    return {"begin": cmd_begin, "arm": cmd_arm, "status": cmd_status, "end": cmd_end}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
