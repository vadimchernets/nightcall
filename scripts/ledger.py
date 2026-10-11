#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall ledger: what the AI wanted - what the person approved.

One line per thing the AI wanted to do that is the person's to decide (spend money, send a message,
delete, publish, change something outside the fence). At night nobody answers, so the AI writes the
want down, does the safe part and goes on; in the morning the person answers each one with one word.

    python3 ledger.py want    --dir <task folder> --what <text> [--why <text>] [--default <what was done meanwhile>]
    python3 ledger.py decide  --dir <task folder> --id N --verdict approved|declined [--note <text>]
    python3 ledger.py show    --dir <task folder> [--json] [--pending]
    python3 ledger.py pending --dir <task folder>        # just the number, for scripts

The ledger is LEDGER.jsonl in the task folder: one JSON object per line, appended whole. A decision is
a second line with the same id, so the history of every want stays (the AI's words are never edited).
Standard library only.
"""

import argparse
import json
import os
import sys
import time

NAME = "LEDGER.jsonl"
VERDICTS = ("approved", "declined")
CUT = 300


def path_of(folder):
    return os.path.join(os.path.abspath(os.path.expanduser(folder)), NAME)


def short(text, size=CUT):
    line = " ".join(str(text or "").split())
    return line if len(line) <= size else line[: size - 1] + "…"


def read(folder):
    """Every want with its latest decision folded in: [{id, at, what, why, default, verdict, decided_at, note}]."""
    wants, order = {}, []
    try:
        with open(path_of(folder), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not isinstance(row.get("id"), int):
            continue
        if row.get("kind") == "want":
            wants[row["id"]] = {"id": row["id"], "at": row.get("at", 0), "what": row.get("what", ""),
                                "why": row.get("why", ""), "default": row.get("default", ""),
                                "verdict": "pending", "decided_at": 0, "note": ""}
            order.append(row["id"])
        elif row.get("kind") == "decision" and row["id"] in wants and row.get("verdict") in VERDICTS:
            wants[row["id"]].update(verdict=row["verdict"], decided_at=row.get("at", 0), note=row.get("note", ""))
    return [wants[i] for i in order]


def pending(folder):
    return [w for w in read(folder) if w["verdict"] == "pending"]


def append(folder, row):
    """One whole line in one write: two writers at once never tear each other's line."""
    path = path_of(folder)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def want(folder, what, why="", default="", now=None):
    rows = read(folder)
    new_id = (max([w["id"] for w in rows]) if rows else 0) + 1
    append(folder, {"kind": "want", "id": new_id, "at": now or time.time(), "what": short(what),
                    "why": short(why), "default": short(default)})
    return new_id


def decide(folder, item, verdict, note="", now=None):
    if verdict not in VERDICTS or not any(w["id"] == item for w in read(folder)):
        return False
    append(folder, {"kind": "decision", "id": item, "at": now or time.time(), "verdict": verdict, "note": short(note)})
    return True


def when(epoch):
    return time.strftime("%d.%m %H:%M", time.localtime(epoch)) if epoch else "-"


def render(rows):
    if not rows:
        return "The ledger is empty: the AI wanted nothing that was yours to decide."
    out = ["What the AI wanted - what you decided:"]
    for w in rows:
        mark = {"pending": "WAITS FOR YOU", "approved": "approved", "declined": "declined"}[w["verdict"]]
        out.append(f"{w['id']}. [{mark}] {w['what']}")
        if w["why"]:
            out.append(f"     why: {w['why']}")
        if w["default"]:
            out.append(f"     meanwhile: {w['default']}")
        if w["verdict"] != "pending":
            out.append(f"     {w['verdict']} {when(w['decided_at'])}" + (f": {w['note']}" if w["note"] else ""))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall ledger: what the AI wanted - what the person approved.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("want")
    w.add_argument("--dir", required=True)
    w.add_argument("--what", required=True)
    w.add_argument("--why", default="")
    w.add_argument("--default", default="", help="what was done meanwhile (the safe part)")
    d = sub.add_parser("decide")
    d.add_argument("--dir", required=True)
    d.add_argument("--id", type=int, required=True)
    d.add_argument("--verdict", required=True, choices=VERDICTS)
    d.add_argument("--note", default="")
    s = sub.add_parser("show")
    s.add_argument("--dir", required=True)
    s.add_argument("--json", action="store_true")
    s.add_argument("--pending", action="store_true")
    p = sub.add_parser("pending")
    p.add_argument("--dir", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "want":
        print(json.dumps({"id": want(a.dir, a.what, a.why, a.default), "ledger": path_of(a.dir)}))
        return 0
    if a.cmd == "decide":
        if not decide(a.dir, a.id, a.verdict, a.note):
            print(f"No want number {a.id} in {path_of(a.dir)}.")
            return 1
        print(f"{a.id}: {a.verdict}")
        return 0
    if a.cmd == "pending":
        print(len(pending(a.dir)))
        return 0
    rows = pending(a.dir) if a.pending else read(a.dir)
    print(json.dumps(rows, indent=2, ensure_ascii=False) if a.json else render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
