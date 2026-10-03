#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall ready: what has to be true for the night to actually work - checked, not assumed.

    python3 ready.py [--dir <task folder>]

Each line is OK, NOT OK (fix it now, before you go to bed) or WATCH (cannot be read from here - one
thing for the person to look at). Nothing is changed on the computer: this only reads.
"""

import argparse
import glob
import os
import platform
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SYS = platform.system()
rows = []


def row(state, what, do=""):
    rows.append((state, what, do))


def sh(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def check_power():
    if SYS == "Darwin":
        out = sh(["pmset", "-g", "batt"])
        if "AC Power" in out:
            row("OK", "Power is on mains.")
        elif out:
            row("NOT OK", "The laptop is on battery — it will run down overnight and the work will stop.",
                "Plug in the charger.")
        return
    if SYS == "Linux":
        bats = glob.glob("/sys/class/power_supply/BAT*")
        online = any(open(f).read().strip() == "1" for f in glob.glob("/sys/class/power_supply/*/online"))
        if not bats or online:
            row("OK", "Power is on mains.")
        else:
            row("NOT OK", "The laptop is on battery.", "Plug in the charger.")
        return
    if SYS == "Windows":
        out = sh(["powershell", "-NoProfile", "-Command",
                  "(Get-CimInstance Win32_Battery).BatteryStatus"])
        if not out.strip() or out.strip() == "2":
            row("OK", "Power is on mains.")
        else:
            row("NOT OK", "The laptop is on battery.", "Plug in the charger.")


def check_awake():
    home = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
    if SYS == "Windows":
        home = os.path.join(os.environ.get("LOCALAPPDATA", home), "nightcall")
    until = next((open(f, encoding="utf-8").read().strip() for f in glob.glob(os.path.join(home, "awake-*.until"))), "")
    if until:
        row("OK", f"Caffeine is on until {until}.")
    else:
        row("NOT OK", "Caffeine is not on — the computer will sleep as soon as you step away.",
            "Skill /nightcall:awake 8 (or 12).")
    row("WATCH", "The laptop lid: keep it open for the night.",
        "Turn the screen brightness all the way down instead of closing it.")


def check_updates():
    if SYS == "Darwin":
        v = sh(["defaults", "read", "/Library/Preferences/com.apple.SoftwareUpdate",
                "AutomaticallyInstallMacOSUpdates"]).strip()
        if v == "1":
            row("NOT OK", "macOS installs updates by itself and may reboot overnight.",
                "System Settings → General → Software Update → (i) next to \"Automatic Updates\" → "
                "turn off \"Install macOS updates\" for tonight.")
        else:
            row("OK", "macOS will not reboot overnight on its own for updates.")
    elif SYS == "Windows":
        row("WATCH", "Windows Update can reboot overnight.",
            "Settings → Windows Update → \"Pause for 1 week\".")
    elif SYS == "Linux":
        auto = any("Automatic-Reboot \"true\"" in open(f, errors="ignore").read()
                   for f in glob.glob("/etc/apt/apt.conf.d/*unattended*"))
        if auto:
            row("NOT OK", "Automatic updates are set to reboot.", "Postpone them for tonight.")
        else:
            row("OK", "No automatic reboot after updates in sight.")


def check_network():
    try:
        socket.create_connection(("api.anthropic.com", 443), timeout=6).close()
        row("OK", "Internet is up, Claude is reachable.")
    except OSError:
        row("NOT OK", "No connection to Claude — the night needs it.",
            "Check Wi-Fi; a cable is better.")
    row("WATCH", "Wi-Fi can drop during sleep and when the network changes.",
        "Don't take the computer anywhere; a VPN that drops is better turned off for the night.")


def check_disk(folder):
    free = shutil.disk_usage(folder or os.path.expanduser("~")).free / 1e9
    if free < 5:
        row("NOT OK", f"Only {free:.1f} GB free.", "Free up space — files grow overnight.")
    else:
        row("OK", f"Disk space: {free:.0f} GB.")


def check_claude():
    if shutil.which("claude"):
        row("OK", "Claude Code is installed.")
    else:
        row("NOT OK", "The claude command is not found in this window.", "Run the night from Claude Code.")
    row("WATCH", "Permissions: nobody is here to click \"Yes\" at night — one question stops the whole night.",
        "Before you leave: Shift+Tab to auto mode (or accept edits), or the night loop "
        "scripts/night-loop.sh. Check on one step that no question pops up.")
    row("WATCH", "Claude's subscription limit: once it runs out, the work waits until it resets.",
        "Type /usage and see how much is left. The night loop waits out the reset and continues by itself.")


def check_team(folder):
    out = sh([sys.executable, os.path.join(HERE, "team.py"), "list"], timeout=20)
    n = sum(1 for line in out.splitlines() if line.startswith("  "))
    if n:
        row("OK", f"Other AI subscription programs found: {n}. Whether they're alive — the roll call will show.")
    else:
        row("WATCH", "No other AI subscription programs — the reserve is free keys and web chats in Chrome.",
            "Install and sign in to at least one (codex, gemini/agy, kimi, grok, qwen) — or sign in "
            "to 2–3 web chats in Chrome (ChatGPT, Gemini, Kimi, DeepSeek, Meta AI).")
    seats = os.path.join(folder, "seats.json") if folder else ""
    if seats and os.path.exists(seats):
        sys.path.insert(0, HERE)
        import team as T  # reuse load_seats(): also migrates seats.json written before the English rename
        try:
            data = T.load_seats(seats) or {}
        except ValueError:
            data = {}
        alive = [s for s in data.get("helpers", []) + data.get("keys", []) if s.get("status") == "alive"]
        web = [w for w in data.get("web", []) if w.get("status") == "alive"]
        if alive or web:
            row("OK", f"Roll call done: {len(alive)} program(s)/key(s) alive, {len(web)} web chat(s) in reserve.")
        else:
            row("NOT OK", "Roll call: not one other company's helper is alive — tonight's second head "
                "is Claude's own critics.", "Sign in to a program or web chat now and repeat the roll call.")
        if data.get("web_when") == "morning":
            row("OK", "Web chats: in the morning (web: morning) — at night the question for them goes "
                "into morning-advice.md.")
        if not data.get("web"):
            row("WATCH", "The browser hasn't been checked yet: web chats are the reserve for when limits hit.",
                "Skill /nightcall:ready, step \"Browser roll call\" — while you're still here.")
    else:
        row("WATCH", "No roll call yet: the helpers' being alive hasn't been checked.",
            "Skill /nightcall:ready does it by itself: programs, keys and web chats in Chrome.")


def check_folder(folder):
    """The safety net of the night: a restore point and the fence (course step "Fence and time machine"). Never a refusal:
    whatever is missing, `night.py begin` makes it by itself."""
    if not folder:
        return
    tags = sh(["git", "-C", folder, "tag", "--list", "nightcall-before-*"]).split()
    if tags:
        row("OK", f"Restore point: present (git tag {sorted(tags)[-1]}) — everything can be rolled back in the morning.")
    elif os.path.isdir(folder) and sh(["git", "-C", folder, "rev-parse", "--git-dir"]).strip():
        row("OK", "Restore point: will be created — night.py begin will make a \"before the night\" commit and tag.")
    else:
        row("OK", "Restore point: will be created — night.py begin will run git init and a \"before the night\" commit.")
    claude_md = os.path.join(folder, "CLAUDE.md")
    try:
        fenced = "nightcall:fence" in open(claude_md, encoding="utf-8").read()
    except OSError:
        fenced = False
    row("OK", "Fence: " + ("present — the folder's CLAUDE.md says \"work only inside this folder\"." if fenced else
                                "will be written into the folder's CLAUDE.md by night.py begin."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="the task folder")
    a = ap.parse_args()
    check_power(); check_awake(); check_updates(); check_network()
    check_disk(a.dir); check_claude(); check_team(a.dir); check_folder(a.dir)
    print("Before the night:")
    for state, what, do in rows:
        print(f"  {state:<8} {what}" + (f"\n           → {do}" if do else ""))
    bad = sum(1 for r in rows if r[0] == "NOT OK")
    print(f"Total: {bad} NOT OK, {sum(1 for r in rows if r[0] == 'WATCH')} WATCH, "
          f"{sum(1 for r in rows if r[0] == 'OK')} OK.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
