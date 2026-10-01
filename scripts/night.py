#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall night: open and close a night run.

    python3 night.py begin --dir <task folder> --hours 8      # task text on stdin
    python3 night.py arm   --dir <task folder> --hours 8 --session <id> [--max-rounds 200]   # the person has left
    python3 night.py status
    python3 night.py end

`begin` creates the task folder with TASK.md (the person's words, as given), a PLAN.md and a
PROGRESS.md skeleton if they are not there yet, and ALWAYS puts the night on a safety net, without
asking: a restore point (no git -> `git init` + a commit «перед ночью»; git -> a commit of what is
not committed + a tag `nightcall-before-<time>`) and the fence rule in the folder's CLAUDE.md:
work only inside this folder (course step "Fence and time machine"). `arm` - said when the person has left - writes
~/.nightcall/active.json, the switch the Stop hook reads to keep the session working until the end
time, bound to the session that started the night (`--session`, the hook's session_id), so another
Claude Code window open the same evening is never caught. They are separate on purpose: while the
person is still here, a turn that ends with a question to them must be allowed to end. `end`
removes the switch. Nothing outside the task folder and ~/.nightcall is touched.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
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


FENCE_MARK = "<!-- nightcall:fence -->"
FENCE = """
{mark}
## Ночь nightcall: забор (шаг курса «Забор и машина времени»)

- Работай ТОЛЬКО внутри этой папки: `{folder}`. Ничего не создавай, не меняй и не удаляй за её
  пределами (домашняя папка, рабочий стол, системные файлы, другие проекты).
- Нужен файл снаружи — скопируй его внутрь и работай с копией.
- Ничего не удаляй насовсем: переноси в `_убрано/` или полагайся на коммит.
- Точка возврата перед ночью: {restore}. Откатить всё: `{undo}`.
"""


def git(folder, *args):
    try:
        r = subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as exc:  # git missing or hung
        return 127, str(exc)


def git_ident(folder):
    """Commit even where git has no user name set: a local identity for this one commit."""
    extra = []
    if git(folder, "config", "user.name")[0] != 0:
        extra += ["-c", "user.name=nightcall"]
    if git(folder, "config", "user.email")[0] != 0:
        extra += ["-c", "user.email=nightcall@localhost"]
    return extra


def restore_point(folder, now):
    """Always a way back to the evening state. Returns (what, how to undo)."""
    tag = f"nightcall-before-{now:%Y%m%d-%H%M}"
    code, _ = git(folder, "rev-parse", "--git-dir")
    if code == 127 or shutil.which("git") is None:
        # no git on this computer at all: a plain copy of the folder in ~/.nightcall/backups
        dest = os.path.join(HOME, "backups", f"{os.path.basename(folder)}-{now:%Y%m%d-%H%M}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.exists(dest):
            shutil.copytree(folder, dest, symlinks=True)
        return f"копия папки {dest} (git на компьютере нет)", f"скопируйте {dest} обратно"
    if code != 0:
        git(folder, "init", "-q")
    ident = git_ident(folder)
    git(folder, "add", "-A", ".")
    git(folder, *ident, "commit", "-q", "--allow-empty", "-m", "nightcall: перед ночью")
    git(folder, "tag", "-f", tag)
    top = git(folder, "rev-parse", "--show-toplevel")[1]
    if os.path.realpath(top) == os.path.realpath(folder):
        return f"git-тег {tag}", f"git -C \"{folder}\" reset --hard {tag}"
    # the folder is a part of a bigger repository: roll back only this folder
    return f"git-тег {tag}", f"git -C \"{folder}\" checkout {tag} -- ."


def fence(folder, restore, undo):
    path = os.path.join(folder, "CLAUDE.md")
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    if FENCE_MARK in old:
        old = old[:old.index(FENCE_MARK)].rstrip() + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(old + FENCE.format(mark=FENCE_MARK, folder=folder, restore=restore, undo=undo))


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
    tag_now = datetime.datetime.now()
    # the restore point first (the evening state as it was), then the fence on top of it
    restore, undo = restore_point(folder, tag_now)
    fence(folder, restore, undo)
    if restore.startswith("git"):
        git(folder, "add", "--", "CLAUDE.md")
        git(folder, *git_ident(folder), "commit", "-q", "-m", "nightcall: забор на ночь", "--", "CLAUDE.md")
    print(f"Папка ночи готова: {folder}")
    print(f"  создано: {', '.join(made) or 'ничего, файлы уже были'}")
    print(f"  точка возврата: {restore}. Откатить: {undo}")
    print("  забор: в CLAUDE.md папки — «работать только в этой папке»")
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
                   "rounds": 0, "session": clean_session(a.session)}, fh, ensure_ascii=False, indent=2)
    print(f"Ночь идёт: {folder} до {until:%H:%M %d.%m}. Сессия сама возвращается к следующему шагу.")
    print(f"  Выключатель: файл STOP в этой папке или `python3 {os.path.abspath(__file__)} end`.")
    return 0


def clean_session(value):
    """`${CLAUDE_SESSION_ID}` left unexpanded or empty means: unknown, the hook binds by folder."""
    value = (value or "").strip()
    return "" if not value or value.startswith("${") or value.startswith("$") else value


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
    r.add_argument("--session", default="", help="session_id окна, которое начало ночь (${CLAUDE_SESSION_ID})")
    sub.add_parser("status")
    sub.add_parser("end")
    a = ap.parse_args(argv)
    return {"begin": cmd_begin, "arm": cmd_arm, "status": cmd_status, "end": cmd_end}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
