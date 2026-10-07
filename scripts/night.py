#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall night: open and close a night run.

    python3 night.py begin --dir <task folder> --hours 8      # task text on stdin
    python3 night.py arm   --dir <task folder> --hours 8 --session <id> [--max-rounds 200]   # the person has left
    python3 night.py status
    python3 night.py end
    python3 night.py board --dir <task folder> --state working|limit|done|failed [--note <text>] [--rest <seconds>]

`begin` creates the task folder with TASK.md (the person's words, as given), a PLAN.md and a
PROGRESS.md skeleton if they are not there yet, and ALWAYS puts the night on a safety net, without
asking: a restore point (no git -> `git init` + a commit "before the night"; git -> a commit of what is
not committed + a tag `nightcall-before-<time>`) and the fence rule in the folder's CLAUDE.md:
work only inside this folder (course step "Fence and time machine"). `arm` - said when the person has left - writes
~/.nightcall/active.json, the switch the Stop hook reads to keep the session working until the end
time, bound to the session that started the night (`--session`, the hook's session_id), so another
Claude Code window open the same evening is never caught. They are separate on purpose: while the
person is still here, a turn that ends with a question to them must be allowed to end. `end`
removes the switch. `board` puts the night on pocketcall's board (one line per night: working, resting on
a limit until a given hour, done), so the phone sees it next to every other job and rings when the night
rests or ends; without pocketcall the line waits in ~/.pocketcall/board for it. NIGHTCALL_BOARD=off
leaves the board alone, NIGHTCALL_BOARD=<path to board.py> names pocketcall's script. Apart from that
line, nothing outside the task folder and ~/.nightcall is touched.
"""

import argparse
import datetime
import glob
import hashlib
import re
import time
import json
import os
import shutil
import subprocess
import sys

HOME = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
ACTIVE = os.path.join(HOME, "active.json")

PLAN = """# Plan for the night

The task is in TASK.md. Each step is one checkable thing. "Done" is a check, not a feeling.

| # | Step | Done when… | Status |
|---|-----|----------------|--------|
| 1 |     |                | waiting |
"""

PROGRESS = """# Night progress

Started: {start}. End no later than: {until}.

## Journal
<!-- after each step: time (date) · step · what was done · how it was checked · what's next -->

## Helpers
<!-- which other AIs are alive, which dropped out and why, who replaced them -->

## Check in the morning
<!-- disputed decisions made without the person, with the value that was chosen -->
"""


FENCE_MARK = "<!-- nightcall:fence -->"
FENCE = """
{mark}
## Nightcall night: the fence (course step "Fence and time machine")

- Work ONLY inside this folder: `{folder}`. Don't create, change or delete anything outside it
  (the home folder, the desktop, system files, other projects).
- Need a file from outside — copy it in and work with the copy.
- Don't delete anything for good: move it to `_removed/` or rely on the commit.
- Restore point before the night: {restore}. Roll everything back: `{undo}`.
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
        return f"a copy of the folder at {dest} (no git on this computer)", f"copy {dest} back"
    if code != 0:
        git(folder, "init", "-q")
    ident = git_ident(folder)
    git(folder, "add", "-A", ".")
    git(folder, *ident, "commit", "-q", "--allow-empty", "-m", "nightcall: before the night")
    git(folder, "tag", "-f", tag)
    top = git(folder, "rev-parse", "--show-toplevel")[1]
    if os.path.realpath(top) == os.path.realpath(folder):
        return f"git tag {tag}", f"git -C \"{folder}\" reset --hard {tag}"
    # the folder is a part of a bigger repository: roll back only this folder
    return f"git tag {tag}", f"git -C \"{folder}\" checkout {tag} -- ."


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
            fh.write("# Task for the night (in the person's own words)\n\n" + task + "\n")
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
        git(folder, *git_ident(folder), "commit", "-q", "-m", "nightcall: fence for the night", "--", "CLAUDE.md")
    print(f"Night folder ready: {folder}")
    print(f"  created: {', '.join(made) or 'nothing, the files were already there'}")
    print(f"  restore point: {restore}. Undo: {undo}")
    print("  fence: in the folder's CLAUDE.md — \"work only inside this folder\"")
    return 0


def cmd_arm(a):
    folder = os.path.abspath(os.path.expanduser(a.dir))
    if not os.path.exists(os.path.join(folder, "PLAN.md")):
        print(f"No PLAN.md in {folder} — run begin and make a plan first.")
        return 2
    now = datetime.datetime.now().replace(second=0, microsecond=0)
    until = now + datetime.timedelta(hours=a.hours)
    os.makedirs(HOME, exist_ok=True)
    with open(ACTIVE, "w", encoding="utf-8") as fh:
        json.dump({"folder": folder, "started": now.isoformat(timespec="minutes"),
                   "until": until.isoformat(timespec="minutes"), "max_rounds": a.max_rounds,
                   "rounds": 0, "session": clean_session(a.session)}, fh, ensure_ascii=False, indent=2)
    print(f"The night is on: {folder} until {until:%H:%M %d.%m}. The session returns to the next step by itself.")
    print(f"  Off switch: a file named STOP in this folder, or `python3 {os.path.abspath(__file__)} end`.")
    return 0


def clean_session(value):
    """`${CLAUDE_SESSION_ID}` left unexpanded or empty means: unknown, the hook binds by folder."""
    value = (value or "").strip()
    return "" if not value or value.startswith("${") or value.startswith("$") else value


def cmd_status(_):
    try:
        run = json.load(open(ACTIVE, encoding="utf-8"))
    except Exception:
        print("No night run is active right now.")
        return 1
    print(f"Night run active: {run['folder']} until {run['until']}, rounds {run.get('rounds', 0)}.")
    return 0


def cmd_end(_):
    if os.path.exists(ACTIVE):
        os.remove(ACTIVE)
        print("Night closed: the session no longer returns to work by itself.")
    else:
        print("There was no night run to close.")
    return 0


def board_script():
    """pocketcall's board.py: NIGHTCALL_BOARD, or the newest installed pocketcall plugin."""
    named = os.environ.get("NIGHTCALL_BOARD", "")
    if named:
        return named if os.path.isfile(named) else ""
    roots = [os.path.expanduser("~/.claude")]
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        roots.insert(0, os.environ["CLAUDE_CONFIG_DIR"])
    found = [f for r in roots for f in glob.glob(os.path.join(r, "plugins", "cache", "*", "pocketcall", "*",
                                                                 "scripts", "board.py"))]
    return max(found, key=os.path.getmtime) if found else ""


def cmd_board(a):
    """One line for the night on pocketcall's board. Never stops the night: any trouble is silent."""
    if os.environ.get("NIGHTCALL_BOARD", "").lower() == "off":
        return 0
    folder = os.path.abspath(a.dir)
    name = "night run: " + (os.path.basename(folder) or folder)
    # two nights in two folders of the same name are two lines
    job_id = ("nightcall-" + (re.sub(r"[^A-Za-z0-9_-]", "-", os.path.basename(folder))[:40] or "night")
              + "-" + hashlib.sha1(folder.encode("utf-8")).hexdigest()[:6])
    until = ""
    if a.rest and a.rest > 0:
        until = (datetime.datetime.now() + datetime.timedelta(seconds=a.rest)).strftime("%H:%M")
    script = board_script()
    if script:
        cmd = [sys.executable, script, "put", "--id", job_id, "--name", name, "--where", "nightcall",
               "--state", a.state, "--note", a.note, "--until", until, "--ring"]   # a night rings, away or not
        try:
            subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=30)
            return 0
        except (OSError, subprocess.SubprocessError):
            pass
    base = os.path.join(os.environ.get("POCKETCALL_HOME") or os.path.expanduser("~/.pocketcall"), "board")
    try:
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, job_id + ".json")
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump({"id": job_id, "name": name, "where": "nightcall", "state": a.state,
                       "note": " ".join(a.note.split())[:160], "until": until, "at": time.time()},
                      fh, ensure_ascii=False)
        os.chmod(path + ".tmp", 0o600)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall: open and close the night.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("begin")
    b.add_argument("--dir", required=True)
    b.add_argument("--hours", type=float, default=8)
    r = sub.add_parser("arm")
    r.add_argument("--dir", required=True)
    r.add_argument("--hours", type=float, default=8)
    r.add_argument("--max-rounds", type=int, default=200)
    r.add_argument("--session", default="", help="session_id of the window that started the night (${CLAUDE_SESSION_ID})")
    sub.add_parser("status")
    sub.add_parser("end")
    o = sub.add_parser("board")
    o.add_argument("--dir", required=True)
    o.add_argument("--state", required=True, choices=("working", "limit", "done", "failed"))
    o.add_argument("--note", default="")
    o.add_argument("--rest", type=int, default=0, help="seconds until the night goes on (a limit)")
    a = ap.parse_args(argv)
    return {"begin": cmd_begin, "arm": cmd_arm, "status": cmd_status, "end": cmd_end,
            "board": cmd_board}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
