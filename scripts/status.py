#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall status: what the night is doing, in one card.

    python3 status.py show     [--dir <task folder>] [--json]   the card: state, last action, checks, what waits for you
    python3 status.py stop     [--dir <task folder>]            the night ends after the current step (a STOP file)
    python3 status.py continue [--dir <task folder>]            STOP goes away, the night goes on
    python3 status.py push     [--dir <task folder>]            the card onto pocketcall's board (the phone shows it)

The card is built only from files the night already keeps - ~/.nightcall/active.json, PLAN.md,
PROGRESS.md, checklist.json, LEDGER.jsonl, STOP, MORNING.md - never from memory. Without --dir the folder
of the night that is on is used. Standard library only.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ledger  # noqa: E402

HOME = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
LAST = 160
MARKER = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
DONE_WORDS = ("done", "closed", "✓", "ok")


def active():
    try:
        with open(os.path.join(HOME, "active.json"), encoding="utf-8") as fh:
            run = json.load(fh)
        return run if isinstance(run, dict) else {}
    except (OSError, ValueError):
        return {}


def text_of(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def short(text, size=LAST):
    line = " ".join(str(text or "").split())
    return line if len(line) <= size else line[: size - 1] + "…"


def plan_steps(folder):
    """(done, total) from the PLAN.md table: a row is done when its status cell says so; the empty skeleton row is no step."""
    done = total = 0
    for line in text_of(os.path.join(folder, "PLAN.md")).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit() or not cells[1]:
            continue
        total += 1
        if cells[-1].lower().startswith(DONE_WORDS):
            done += 1
    return done, total


def section(text, title):
    """The lines under '## <title>' up to the next heading, comments and blanks left out."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith(title.lower())
            continue
        if inside and line.strip() and not line.strip().startswith("<!--"):
            out.append(line.strip())
    return out


def last_action(folder):
    journal = section(text_of(os.path.join(folder, "PROGRESS.md")), "Journal")
    return short(MARKER.sub("", journal[-1])) if journal else ""


def checks(folder):
    """(closed, total) of the checklist: an item is closed only with its evidence (checklist.py close)."""
    try:
        with open(os.path.join(folder, "checklist.json"), encoding="utf-8") as fh:
            items = json.load(fh).get("items", [])
    except (OSError, ValueError, AttributeError):
        return 0, 0
    items = [i for i in items if isinstance(i, dict)]
    return len([i for i in items if i.get("state") == "done"]), len(items)


def card(folder, now=None):
    now = datetime.datetime.now() if now is None else now
    folder = os.path.abspath(os.path.expanduser(folder))
    run = active()
    mine = bool(run) and os.path.realpath(run.get("folder", "")) == os.path.realpath(folder)
    until = ""
    if mine:
        try:
            until = datetime.datetime.fromisoformat(run["until"]).strftime("%H:%M")
        except (KeyError, ValueError):
            pass
    if os.path.exists(os.path.join(folder, "MORNING.md")):
        state = "done"
    elif os.path.exists(os.path.join(folder, "STOP")):
        state = "stopped"
    elif mine:
        state = "working"
    elif os.path.exists(os.path.join(folder, "PLAN.md")):
        state = "idle"
    else:
        state = "none"
    steps_done, steps_total = plan_steps(folder)
    closed, items = checks(folder)
    wants = ledger.read(folder)
    waits = [w for w in wants if w["verdict"] == "pending"]
    held = section(text_of(os.path.join(folder, "PROGRESS.md")), "Check in the morning")
    return {
        "folder": folder, "state": state, "until": until, "round": int(run.get("rounds", 0)) if mine else 0,
        "steps_done": steps_done, "steps_total": steps_total, "checks_done": closed, "checks_total": items,
        "last": last_action(folder),
        "waits": [{"id": w["id"], "what": w["what"], "meanwhile": w["default"]} for w in waits],
        "decided": len(wants) - len(waits), "held": len(held),
        "can_stop": state == "working", "can_continue": state in ("stopped", "idle"),
        "at": time.time(),
    }


def steps_text(c):
    return f"{c['steps_done']}/{c['steps_total']}" if c["steps_total"] else ""


def checks_text(c):
    return f"{c['checks_done']}/{c['checks_total']}" if c["checks_total"] else ""


def board_state(c):
    return {"working": "working", "done": "done", "stopped": "failed"}.get(c["state"], "")


def summary(c):
    """The card in one line, for the board's note and the phone."""
    bits = []
    if steps_text(c):
        bits.append("steps " + steps_text(c))
    if checks_text(c):
        bits.append("checks " + checks_text(c))
    if c["waits"]:
        bits.append(f"waits for you: {len(c['waits'])}")
    if c["last"]:
        bits.append("last: " + c["last"])
    return short(" · ".join(bits), 160)


def render(c):
    names = {"working": "WORKING", "done": "DONE: the report MORNING.md is written", "stopped": "STOPPED by the STOP file",
             "idle": "NOT RUNNING: the plan is there, the night is not armed", "none": "NO NIGHT in this folder"}
    out = [f"Night: {names[c['state']]}" + (f", until {c['until']}" if c["until"] and c["state"] == "working" else ""),
           f"Folder: {c['folder']}"]
    if c["state"] == "working":
        out.append(f"Rounds so far: {c['round']}")
    out.append("Steps: " + (f"{c['steps_done']} of {c['steps_total']} done" if c["steps_total"] else "no plan yet"))
    out.append("Checks: " + (f"{c['checks_done']} of {c['checks_total']} closed with evidence" if c["checks_total"]
                             else "no checklist"))
    out.append("Last action: " + (c["last"] or "nothing written in PROGRESS.md yet"))
    if c["waits"]:
        out.append(f"Waits for you ({len(c['waits'])}):")
        for w in c["waits"]:
            out.append(f"  {w['id']}. {w['what']}" + (f" (meanwhile: {w['meanwhile']})" if w["meanwhile"] else ""))
    else:
        out.append("Waits for you: nothing in the ledger" + (f"; {c['held']} default(s) to check in the morning"
                                                             if c["held"] else ""))
    if c["decided"]:
        out.append(f"Decided by you so far: {c['decided']}")
    if c["can_stop"]:
        out.append("Stop: `status.py stop` (or the STOP button on the phone) - the night ends after this step.")
    if c["can_continue"]:
        out.append("Continue: `status.py continue` (or the Continue button on the phone).")
    return "\n".join(out)


def find_folder(given):
    if given:
        return os.path.abspath(os.path.expanduser(given))
    return active().get("folder", "")


def push(folder):
    """The card onto pocketcall's board through night.py board. Never raises: the night does not wait on a phone."""
    c = card(folder)
    state = board_state(c)
    if not state:
        return 0
    import night
    args = argparse.Namespace(dir=folder, state=state, note=summary(c), rest=0, kind="", hours=0, end=0, box=False,
                              meter="", say=False, steps=steps_text(c), checks=checks_text(c), last=c["last"],
                              waits=len(c["waits"]))
    try:
        return night.cmd_board(args)
    except Exception:  # noqa: BLE001
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall status: what the night is doing, in one card.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "stop", "continue", "push"):
        p = sub.add_parser(name)
        p.add_argument("--dir", default="")
        if name == "show":
            p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    folder = find_folder(a.dir)
    if not folder or not os.path.isdir(folder):
        print("No night folder: give --dir <task folder> or start a night with /nightcall:start.")
        return 1
    if a.cmd == "show":
        c = card(folder)
        print(json.dumps(c, indent=2, ensure_ascii=False) if a.json else render(c))
        return 0
    if a.cmd == "stop":
        with open(os.path.join(folder, "STOP"), "w", encoding="utf-8") as fh:
            fh.write(f"stopped with status.py at {time.strftime('%H:%M')}\n")
        push(folder)
        print("STOP is set: the night ends after the current step. `status.py continue` takes it back.")
        return 0
    if a.cmd == "continue":
        if os.path.exists(os.path.join(folder, "MORNING.md")):
            print("The night is over: MORNING.md is written. Start a new one with /nightcall:start.")
            return 1
        try:
            os.remove(os.path.join(folder, "STOP"))
        except OSError:
            pass
        mine = os.path.realpath(active().get("folder", "")) == os.path.realpath(folder)
        push(folder)
        print("STOP is gone." + (" The night goes on." if mine else
                                  " The night is not armed: run /nightcall:start with this folder to put it back on."))
        return 0
    return push(folder)


if __name__ == "__main__":
    sys.exit(main())
