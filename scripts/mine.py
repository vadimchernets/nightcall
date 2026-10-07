#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall "my subscriptions": one person, several subscriptions of their own - Claude, then
Codex, then Gemini CLI. When the Claude limit runs out (or is about to), the next step goes on in
your own Codex, then your own Gemini; when the Claude limit is back, the work comes back to Claude.
The phone hears "switched to Codex - the work goes on".

    python3 mine.py on  [--order claude,codex,gemini] [--below 10]
    python3 mine.py off
    python3 mine.py status                    # which subscriptions, signed in or not, resting until, left %
    python3 mine.py meter [--json]            # how much is left in each subscription, one line
    python3 mine.py pick  [--after <engine>]  # the engine for the next round (the first in order that is free)
    python3 mine.py limit --engine <engine>   # the round's output on stdin: when does it come back
    python3 mine.py relay --folder <f> --from <engine> --to <engine>
    python3 mine.py soonest                   # seconds until the first subscription is back
    python3 mine.py engines                   # the programs in the order (claude codex gemini)
    python3 mine.py capture                   # Claude Code's statusLine command: keeps the "left %" reading

HOW THE WORK MOVES. The night loop starts a fresh program for every step, and that program reads
TASK.md, PLAN.md and PROGRESS.md in the task folder. So the step that Claude did not finish is taken
by Codex from the same files, and the next one by Claude again: the files carry the work, not the
session. Every change of hands goes into PROGRESS.md ("Relay").

HOW MUCH IS LEFT (the sensor, from diffcall's capacity package, core-poly/capacity):
  Claude  Claude Code hands its statusLine command a JSON with `rate_limits` (five_hour / seven_day,
          used_percentage, resets_at) in an interactive session. `mine.py capture` as the statusLine
          command keeps the numbers (only numbers) in ~/.nightcall/quota/claude.json. A reading is used
          while it is fresh: 15 minutes for the five-hour window, 6 hours for the weekly one, never after
          the window's own reset time.
  Codex   `codex app-server`, method account/rateLimits/read - OpenAI's own numbers, read live.
  Gemini  publishes no remaining percentage: it moves on its own limit message.
With a fresh reading below the threshold (--below, default 10%) the work moves BEFORE the limit
stops a step in the middle; without one it moves on the limit message, as before.

Files: ~/.nightcall/mine.json, ~/.nightcall/quota/ (NIGHTCALL_HOME moves them). No login, token or
key is read or kept: each program uses its own usual sign-in on this computer.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import team as T  # noqa: E402  (reset-time parsing)

HOME = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
MINE = os.path.join(HOME, "mine.json")
QUOTA = os.path.join(HOME, "quota")
ENGINES = ("claude", "codex", "gemini")
NAMES = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini"}
UNKNOWN_BACK_MIN = int(os.environ.get("NIGHTCALL_MINE_UNKNOWN_BACK", "60"))
FRESH = {"5h": 15 * 60, "daily": 60 * 60, "weekly": 6 * 3600, "monthly": 12 * 3600}
ALIASES = [("5h", ("five_hour", "five-hour", "5h", "session", "primary")),
           ("weekly", ("seven_day", "week", "7d", "secondary")),
           ("monthly", ("month", "30d")),
           ("daily", ("day", "24h"))]
MINUTES = {300: "5h", 1440: "daily", 10080: "weekly", 43200: "monthly"}


def now():
    return datetime.datetime.now().replace(microsecond=0)


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def parse_time(value):
    try:
        return datetime.datetime.strptime((value or "").strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def load():
    try:
        with open(MINE, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data.setdefault("order", list(ENGINES))
            data.setdefault("below", 10)
            data.setdefault("resting", {})
            return data
    except Exception:
        pass
    return {}


def save(data):
    os.makedirs(HOME, mode=0o700, exist_ok=True)
    tmp = MINE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, MINE)


def installed(engine):
    return bool(shutil.which(engine))


def resting(data, engine, at=None):
    """The time this engine comes back, while it rests; None when it is free."""
    back = parse_time((data.get("resting") or {}).get(engine, ""))
    return back if back and back > (at or now()) else None


# --- how much is left -----------------------------------------------------------------------------

def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def epoch(v):
    """ISO text, epoch seconds or epoch milliseconds -> epoch seconds."""
    if num(v) is not None:
        return v / 1000.0 if v > 1e11 else float(v)
    if isinstance(v, str) and v.strip():
        if v.strip().isdigit():
            return epoch(int(v.strip()))
        try:
            return datetime.datetime.fromisoformat(v.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def window_type(name, row):
    mins = num(row.get("windowDurationMins") or row.get("window_minutes") or row.get("windowMinutes"))
    if mins in MINUTES:
        return MINUTES[mins]
    s = str(row.get("window") or row.get("type") or name or "").lower()
    for kind, words in ALIASES:            # seven_day before day: a week is not a day
        if any(w in s for w in words):
            return kind
    return s or "unknown"


def windows_of(block):
    """Claude's rate_limits (five_hour/seven_day, used_percentage, resets_at) and Codex's rateLimits
    (primary/secondary, usedPercent, windowDurationMins, resetsAt): the same shape, two spellings."""
    out = []
    if not isinstance(block, dict):
        return out
    for name, row in block.items():
        if not isinstance(row, dict):
            continue
        used = next((num(row.get(k)) for k in ("used_percentage", "usedPercent", "used_pct", "utilization")
                     if num(row.get(k)) is not None), None)
        left = next((num(row.get(k)) for k in ("remaining_percentage", "remainingPercent", "remaining_pct")
                     if num(row.get(k)) is not None), None)
        if used is None and left is None:
            continue
        if used is not None and used <= 1 and "utilization" in row and left is None:
            used = used * 100                  # utilization is a fraction
        left = left if left is not None else 100 - used
        out.append({"type": window_type(name, row), "left": max(0.0, min(100.0, float(left))),
                    "resets": epoch(row.get("resets_at") or row.get("resetsAt") or row.get("reset_at"))})
    return out


def fresh(windows, captured, at):
    """Only readings we can still vouch for: within the window's freshness and before its reset."""
    keep = []
    for w in windows:
        horizon = captured + FRESH.get(w["type"], FRESH["5h"])
        if w.get("resets"):
            horizon = min(horizon, w["resets"])
        if at <= horizon:
            keep.append(w)
    return keep


def read_cache(engine, at=None):
    at = time.time() if at is None else at
    try:
        with open(os.path.join(QUOTA, engine + ".json"), encoding="utf-8") as fh:
            entry = json.load(fh)
        return fresh(entry.get("windows") or [], float(entry.get("at") or 0), at), float(entry.get("at") or 0)
    except Exception:
        return [], 0.0


def write_cache(engine, windows, at=None):
    os.makedirs(QUOTA, mode=0o700, exist_ok=True)
    path = os.path.join(QUOTA, engine + ".json")
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump({"at": time.time() if at is None else at, "windows": windows}, fh)
    os.chmod(path + ".tmp", 0o600)
    os.replace(path + ".tmp", path)


def read_codex(timeout=8):
    """OpenAI's own numbers through `codex app-server` (initialize, then account/rateLimits/read)."""
    if os.environ.get("NIGHTCALL_MINE_CODEX_READ", "on") == "off" or not installed("codex"):
        return []
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"clientInfo": {"name": "nightcall", "version": "0.5.0"}}},
            {"jsonrpc": "2.0", "method": "initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": {}}]
    try:
        p = subprocess.run(["codex", "app-server"], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                           capture_output=True, text=True, timeout=timeout)
        lines = p.stdout.splitlines()
    except subprocess.TimeoutExpired as exc:
        lines = (exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")).splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("id") == 2 and isinstance(m.get("result"), dict):
            block = m["result"].get("rateLimits") or {}
            ws = windows_of({k: v for k, v in block.items() if k in ("primary", "secondary")})
            if ws:
                write_cache("codex", ws)
            return ws
    return []


def left(engine, live=True):
    """The tightest fresh reading for this engine (percent), or None when nobody can say."""
    ws = []
    if engine == "codex" and live:
        ws = read_codex()
    if not ws and engine in ("claude", "codex"):
        ws, _ = read_cache(engine)
    if not ws:
        return None
    tight = min(ws, key=lambda w: w["left"])
    return tight


def meter(data, live=True):
    out = []
    for e in data.get("order") or ENGINES:
        if not installed(e):
            continue
        w = left(e, live)
        back = resting(data, e)
        out.append({"engine": e, "left": round(w["left"]) if w else None, "window": w["type"] if w else "",
                    "resets": w.get("resets") if w else None, "resting_until": fmt(back) if back else ""})
    return out


def meter_line(rows):
    parts = []
    for r in rows:
        if r["resting_until"]:
            parts.append(f"{NAMES[r['engine']]} rests until {r['resting_until'][-5:]}")
        elif r["left"] is not None:
            parts.append(f"{NAMES[r['engine']]} {r['left']}%")
        else:
            parts.append(f"{NAMES[r['engine']]} ?")
    return " · ".join(parts)


# --- commands -------------------------------------------------------------------------------------

def cmd_on(a):
    order = [e.strip().lower() for e in a.order.split(",") if e.strip()]
    bad = [e for e in order if e not in ENGINES]
    if bad or not order:
        print(f"Unknown program: {', '.join(bad) or '-'}. Use: {', '.join(ENGINES)}.")
        return 2
    data = load() or {"resting": {}}
    data.update({"on": True, "order": order, "below": a.below})
    save(data)
    found = [e for e in order if installed(e)]
    missing = [e for e in order if not installed(e)]
    print(f"My subscriptions: {' -> '.join(NAMES[e] for e in order)}; the work moves on below {a.below}% left "
          f"or on a limit, and comes back to {NAMES[order[0]]} when it is back.")
    if missing:
        print(f"Not on this computer yet (skipped until installed): {', '.join(missing)}.")
    if not found:
        return 1
    return 0


def cmd_off(_):
    data = load()
    if data:
        data["on"] = False
        save(data)
    print("My subscriptions: off - the night uses Claude only and waits on its limit.")
    return 0


def cmd_status(a):
    data = load()
    if not data.get("on"):
        if not a.quiet:
            print("My subscriptions: off (python3 mine.py on).")
        return 1
    if a.quiet:
        return 0
    print(f"My subscriptions (move on below {data['below']}% left):")
    for r in meter(data):
        state = f"resting until {r['resting_until']}" if r["resting_until"] else "free"
        pct = f"{r['left']}% left ({r['window']})" if r["left"] is not None else "left: no reading"
        print(f"  {NAMES[r['engine']]:7} {state:28} {pct}")
    for e in data["order"]:
        if not installed(e):
            print(f"  {NAMES[e]:7} not installed")
    return 0


def cmd_meter(a):
    rows = meter(load() or {"order": list(ENGINES)})
    print(json.dumps(rows, ensure_ascii=False) if a.json else meter_line(rows))
    return 0


def choose(data, after=""):
    """The first program in the order that is installed, not resting and not nearly empty."""
    at = now()
    for e in data["order"]:
        if not installed(e) or resting(data, e, at):
            continue
        w = left(e, live=(e != after))
        if w is not None and w["left"] < float(data.get("below", 10)):
            # nearly empty: rest it until the window resets, so the step is not cut in the middle
            back = datetime.datetime.fromtimestamp(w["resets"]) if w.get("resets") else \
                at + datetime.timedelta(minutes=UNKNOWN_BACK_MIN)
            data.setdefault("resting", {})[e] = fmt(back)
            data.setdefault("why", {})[e] = f"{round(w['left'])}% left"
            save(data)
            continue
        return e
    return ""


def cmd_pick(a):
    data = load()
    if not data.get("on"):
        return 1
    e = choose(data, a.after)
    if e:
        print(e)
    return 0


def cmd_limit(a):
    data = load()
    text = sys.stdin.read() if not sys.stdin.isatty() else ""
    back = T.reset_time(text, now()) or (now() + datetime.timedelta(minutes=UNKNOWN_BACK_MIN))
    data.setdefault("resting", {})[a.engine] = fmt(back)
    data.setdefault("why", {})[a.engine] = "limit"
    save(data)
    print(f"{NAMES.get(a.engine, a.engine)} is resting until {fmt(back)}.")
    return 0


def cmd_relay(a):
    data = load()
    frm, to = a.__dict__["from"], a.to
    at = now()
    back = resting(data, frm, at) if frm else None
    if back:
        why = (data.get("why") or {}).get(frm, "limit")
        reason = f"{NAMES.get(frm, frm)}: {why}, back at {back:%H:%M}"
    elif frm and data.get("order") and to == data["order"][0]:
        reason = f"{NAMES.get(to, to)} is back"
    else:
        reason = "next round"
    line = (f"- {at:%d.%m %H:%M} {reason} -> {NAMES.get(to, to)} carries the work on (my own subscription; "
            f"the same TASK.md, PLAN.md, PROGRESS.md)")
    path = os.path.join(os.path.abspath(os.path.expanduser(a.folder)), "PROGRESS.md")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else "# Night progress\n"
    if "## Relay" not in text:
        text = text.rstrip() + "\n\n## Relay\n<!-- each change of hands: which subscription stopped, which carried on -->\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n" + line + "\n")
    print(line)
    return 0


def cmd_soonest(_):
    data = load()
    at = now()
    backs = [resting(data, e, at) for e in data.get("order", []) if installed(e)]
    backs = [b for b in backs if b]
    print(int((min(backs) - at).total_seconds()) + 30 if backs else 0)
    return 0


def cmd_engines(_):
    print(" ".join(load().get("order") or []))
    return 0


def cmd_capture(_):
    """statusLine command: keep Claude's own remaining numbers, print one short line, never fail."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        block = next((payload[k] for k in ("rate_limits", "rateLimits") if isinstance(payload.get(k), dict)), None)
        ws = windows_of(block) if block else []
        if ws:
            write_cache("claude", ws)
            tight = min(ws, key=lambda w: w["left"])
            line = f"Claude {round(tight['left'])}% left ({tight['type']})"
            if tight.get("resets"):
                line += f", resets {datetime.datetime.fromtimestamp(tight['resets']):%H:%M}"
            print(line)
    except Exception:  # noqa: BLE001 - a status line never breaks the session
        pass
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall: my own subscriptions carry the work on in turn.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("on")
    p.add_argument("--order", default=",".join(ENGINES))
    p.add_argument("--below", type=float, default=10, help="move on when less than this %% is left")
    sub.add_parser("off")
    p = sub.add_parser("status")
    p.add_argument("--quiet", action="store_true")
    p = sub.add_parser("meter")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("pick")
    p.add_argument("--after", default="")
    p = sub.add_parser("limit")
    p.add_argument("--engine", required=True)
    p = sub.add_parser("relay")
    p.add_argument("--folder", required=True)
    p.add_argument("--from", default="")
    p.add_argument("--to", required=True)
    sub.add_parser("soonest")
    sub.add_parser("engines")
    sub.add_parser("capture")
    a = ap.parse_args(argv)
    return {"on": cmd_on, "off": cmd_off, "status": cmd_status, "meter": cmd_meter, "pick": cmd_pick,
            "limit": cmd_limit, "relay": cmd_relay, "soonest": cmd_soonest, "engines": cmd_engines,
            "capture": cmd_capture}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
