#!/usr/bin/env python3
"""The boxed night's line on pocketcall's board - carried out of the box as data, never as a command.

Inside the box night.py writes its card into the box's own folder (POCKETCALL_HOME=<box home>/pocketcall).
This relay runs OUTSIDE the box, next to box.sh: it reads that card, keeps only the plain fields it knows
(one id - the one this folder's night has -, a state from the list, a short note, an HH:MM, a meter line),
and puts the line on the real board through pocketcall's board.py (so the phone rings as usual). The
card on the real board then carries the night's DATA: "folder", "hours", "box": true - pocketcall's
Continue builds the command from them itself. Whatever else the box wrote (a "resume" command, extra
fields, other cards) never leaves it.

    relay.py --src <box board folder> --folder <task folder> --hours N [--watch PID] [--once]
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATES = {"working", "limit", "done", "failed"}


def job_id(folder):  # the same id night.py gives this folder's night
    return ("nightcall-" + (re.sub(r"[^A-Za-z0-9_-]", "-", os.path.basename(folder))[:40] or "night")
            + "-" + hashlib.sha1(folder.encode("utf-8")).hexdigest()[:6])


def clean(raw, folder):
    """The card's fields the board may show, or None when the card is not this night's or not plain data."""
    if not isinstance(raw, dict) or raw.get("id") != job_id(folder):
        return None
    state = raw.get("state")
    if state not in STATES:
        return None
    text = lambda v, n: " ".join(str(v).split())[:n] if isinstance(v, (str, int, float)) else ""
    until = text(raw.get("until", ""), 5)
    return {"id": raw["id"], "state": state, "note": text(raw.get("note", ""), 160),
            "until": until if re.fullmatch(r"(\d\d:\d\d)?", until) else "",
            "meter": text(raw.get("meter", ""), 120)}


def board_home():
    return os.path.join(os.environ.get("POCKETCALL_HOME") or os.path.expanduser("~/.pocketcall"), "board")


def put(card, folder, hours):
    """The line on the real board: pocketcall's board.py when it is installed (it rings), then the data."""
    sys.path.insert(0, os.path.dirname(HERE))
    name = "night run: " + (os.path.basename(folder) or folder) + " (box)"
    try:
        import night
        script = night.board_script()
    except Exception:
        script = ""
    if script:
        cmd = [sys.executable, script, "put", "--id", card["id"], "--name", name, "--where", "nightcall",
               "--state", card["state"], "--note", card["note"], "--until", card["until"], "--ring"]
        try:
            r = subprocess.run(cmd + ["--folder", folder, "--meter", card["meter"]], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if r.returncode == 2:   # pocketcall before 0.5.0 knows no folder/meter
                subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
    path = os.path.join(board_home(), card["id"] + ".json")
    try:
        with open(path, encoding="utf-8") as fh:
            line = json.load(fh)
    except (OSError, ValueError):
        line = {"id": card["id"], "name": name, "where": "nightcall", "state": card["state"],
                "note": card["note"], "until": card["until"], "meter": card["meter"]}
    line.pop("resume", None)                     # a boxed night's Continue is built from the data below
    line.update({k: card[k] for k in ("state", "note", "until", "meter")})
    line.update({"folder": folder, "hours": hours, "box": True, "at": time.time()})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(line, fh, ensure_ascii=False)
    os.chmod(path + ".tmp", 0o600)
    os.replace(path + ".tmp", path)


def one_pass(src, folder, hours, seen):
    path = os.path.join(src, job_id(folder) + ".json")
    try:
        if os.path.getsize(path) > 65536:
            return
        stamp = os.stat(path).st_mtime_ns
        if seen.get("stamp") == stamp:
            return
        with open(path, encoding="utf-8") as fh:
            card = clean(json.load(fh), folder)
    except (OSError, ValueError):
        return
    seen["stamp"] = stamp
    if card and card != seen.get("card"):
        seen["card"] = card
        put(card, folder, hours)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--folder", required=True)
    ap.add_argument("--hours", type=int, default=8)
    ap.add_argument("--watch", type=int, default=0, help="go on while this process lives (box.sh)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=float, default=3)
    a = ap.parse_args(argv)
    folder = os.path.realpath(a.folder)
    seen = {}
    one_pass(a.src, folder, a.hours, seen)
    while not a.once and a.watch and alive(a.watch):
        time.sleep(a.every)
        one_pass(a.src, folder, a.hours, seen)
    one_pass(a.src, folder, a.hours, seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
