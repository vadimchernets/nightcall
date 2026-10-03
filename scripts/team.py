#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall team: who helps Claude tonight - checked while the person is still here, replaced at night.

Claude is the main agent for the night. Its helpers are AIs of OTHER companies, in this order:

  1. programs by subscription already on this computer (codex, agy/gemini, grok, kimi, qwen);
  2. free keys, only if the person set them up earlier (the course lesson "Free AI keys"): NVIDIA
     (Kimi K3, GLM-5.3), Google AI Studio, Groq, OpenRouter free models - read from the environment or
     ~/.nightcall/free-keys.env; several models per key, the next one on 503/404/timeout (429: see
     limit_scope() - the free limit belongs to the project/account, not to the key);
  3. web chats in the person's own Chrome - only the sites that passed the roll call (web-mark),
     and only if the person chose `web: night` (default); with `web: morning` the question that
     would have gone to a web chat is saved in <folder>/morning-advice.md for the morning;
  4. Claude's own critics (a fresh sub-agent) - when nobody else is left, said out loud.

    python3 team.py list                              # who is installed
    python3 team.py rollcall --out seats.json         # the roll call: every CLI and key gets a test question
    python3 team.py probe [--out seats.json]          # same as rollcall (old name)
    python3 team.py web-sites                         # the web chats to check in Chrome
    python3 team.py web-mark --seats S --site chatgpt --status alive|needs-sign-in|captcha|did-not-open
    python3 team.py web-when --seats S night|morning  # the person's choice: web chats at night (default) or questions saved for the morning
    python3 team.py decide-when --seats S council|morning  # the person's forks in the road: the AI council decides (default) or everything to the morning
    python3 team.py decide --dir D --what … --why … --who … [--alt …] [--commit SHA]  # the council's decision -> decisions.md
    python3 team.py hold --dir D --question … [--waits …]   # "all to the morning": a question -> decisions.md, the task paused
    python3 team.py summary --seats seats.json        # "Working tonight / reserve / not working / what to do"
    python3 team.py ask [--who codex] [--seats S] [--progress PROGRESS.md] -   # question on stdin
    python3 team.py next --seats seats.json           # the route for the next question, no call made
    python3 team.py used --seats seats.json           # who really took part (for MORNING.md)
    python3 team.py ask --blind DIR -                 # the answer goes to DIR, the name stays hidden
    python3 team.py blind --dir DIR                   # all answers as "Answer A / B / C", no names
    python3 team.py reveal --dir DIR                  # who was A, B, C - only AFTER the decision

It never installs anything, never signs anyone in, never types a password and never spends money.
Command lines and the "dead" patterns come from the owner's V1 Synthesizer (real-deps.mjs).
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# (family, binary, argv builder, human name). Claude is not a helper: it is the one asking.
# Every helper runs READ-ONLY: it may read and search, it may not write or run commands.
HELPERS = [
    ("openai", "codex", lambda p: ["--search", "exec", "--skip-git-repo-check", "-s", "read-only", p],
     "ChatGPT (Codex)"),
    ("google", "agy", lambda p: ["-p", p], "Gemini (agy)"),
    ("google", "gemini", lambda p: ["-p", p], "Gemini"),
    # V1: headless `dontAsk` refuses even reads, so `auto` with explicit denials
    ("xai", "grok", lambda p: ["-p", p, "--permission-mode", "auto",
                               "--deny", "Write(**)", "--deny", "Edit(**)", "--deny", "Bash(*)",
                               "--max-turns", "20"], "Grok"),
    ("moonshot", "kimi", lambda p: ["-p", p], "Kimi"),
    ("alibaba", "qwen", lambda p: ["-p", p], "Qwen"),
]
# Claude itself is checked in the roll call too (the night stands on it), but never asked as a helper.
MAIN = ("anthropic", "claude", lambda p: ["-p", p], "Claude (main)")

# Free keys (the course lesson "Free AI keys"). Only used when the person already put the key in the
# environment or in ~/.nightcall/free-keys.env. OpenAI-compatible chat endpoints, free models only.
# Models and order as in Poly A1 src/duoAuto.ts (checked live 01.10.2026): the strongest free one first -
# NVIDIA (one build.nvidia.com key `nvapi-...`: Kimi K3 by Moonshot, then GLM-5.3 by Zhipu; ~40 requests a
# minute, may hang - so 30 s per model in the roll call), then Google AI Studio (Gemini Pro is no longer
# free - only Flash), Groq (Llama is not free since 16.08.2026 - 404; Qwen 3.8 and gpt-oss), OpenRouter :free
# (no free DeepSeek there any more; `openrouter/free` - any free model, the last hope).
# Within one key: 503/404/timeout -> the next model; 401/403 (key not accepted) -> the whole key is out.
# 429: the free limit is per project/account, not per key (checked 02.10.2026 - Google: "Rate limits are
# applied per project, not per API key", ai.google.dev/gemini-api/docs/rate-limits; Groq: "at the
# organization level", console.groq.com/docs/rate-limits; OpenRouter: "Making additional accounts or API
# keys will not affect your rate limits", openrouter.ai/docs/api/reference/limits; NVIDIA: per account).
# So a 429 never sends us to another key of the same provider: a daily limit pauses it until the end of
# the run (Google and Groq count per model - only that model; OpenRouter's free-models-per-day covers
# every :free model - the whole provider); a per-minute limit -> the next provider now, this one again
# at the end of the line.
# (name, env var, url, [models], label, seconds per model in the roll call or None)
FREE_KEYS = [
    ("nvidia", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1/chat/completions",
     ["moonshotai/kimi-k3", "z-ai/glm-5.3"], "NVIDIA (Kimi K3, GLM-5.3)", 30),
    ("google-ai-studio", "GEMINI_API_KEY",
     "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash"], "Gemini (AI Studio)", None),
    ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions",
     ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"], "Groq (Qwen 3.8, gpt-oss)", None),
    ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions",
     ["qwen/qwen3.8-27b:free", "nvidia/nemotron-3-super-120b-a12b:free", "openrouter/free"],
     "OpenRouter (free models)", None),
]
# HTTP codes after which the same key tries its next model (an empty answer - too).
NEXT_MODEL = (404, 408, 429, 500, 502, 503, 504)
# Answer ceilings as in duoAuto.ts: NVIDIA cuts short by default and Kimi/GLM reason first - 4096;
# Groq without a ceiling counts the whole window and answers 413 on the free per-minute token limit.
MAX_TOKENS = {"nvidia": 4096, "groq": 1500}


def clean(text):
    """Reasoning aloud (`<think>`, also cut off), model service tokens (Kimi K3 on NVIDIA ends with
    `<|close|>message`), and "User Safety: safe" from openrouter/free's filter model - not an answer."""
    out = re.sub(r"<think>[\s\S]*?</think>", "", text)
    out = re.sub(r"<think>[\s\S]*$", "", out)
    out = re.sub(r"(?:<\|[^|>\n]{1,40}\|>[A-Za-z_]{0,20}\s*)+$", "", out)
    out = re.sub(r"<\|[^|>\n]{1,40}\|>", "", out).strip()
    if len(out) < 200 and re.match(r"^(user |agent |response )?safety\s*:\s*(safe|unsafe)\b", out, re.I):
        return ""
    return out

# Web chats in the person's Chrome: the reserve. Checked in the roll call, one site at a time.
WEB_SITES = [
    ("chatgpt", "https://chatgpt.com/", "ChatGPT"),
    ("gemini", "https://gemini.google.com/app", "Gemini"),
    ("kimi", "https://www.kimi.com/", "Kimi"),
    ("deepseek", "https://chat.deepseek.com/", "DeepSeek"),
    ("meta", "https://www.meta.ai/", "Meta AI"),
    ("grok", "https://grok.com/", "Grok"),
    ("qwen", "https://chat.qwen.ai/", "Qwen"),
    ("mistral", "https://chat.mistral.ai/chat", "Mistral"),
]
WEB_STATES = ("alive", "needs-sign-in", "captcha", "did-not-open", "no-browser")

PROBE_TEXT = "Connectivity check. Answer with one word: ok"
PROBE_TIMEOUT = int(os.environ.get("NIGHTCALL_PROBE_TIMEOUT", "90"))
ASK_TIMEOUT = int(os.environ.get("NIGHTCALL_ASK_TIMEOUT", "900"))

# From V1 real-deps.mjs QUOTA_WORDS: the allowance ran out - not a breakage, it comes back by itself.
# A helper (CLI or web chat) may answer in its own language on a localized machine or account, not
# just English - one lang/<code>.json per language (loaded by _load_lang_tables() below), joined
# into the regex below, so detection is not English-only.
LANG_DIR = Path(__file__).resolve().parent.parent / "lang"


def _load_lang_tables():
    """Every lang/<code>.json as {code: {"quota": [...], "auth": [...], ...}}. Each file's own
    recognition words, loaded fresh every import - never hand-copied into this script."""
    tables = {}
    for path in sorted(LANG_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            tables[path.stem] = json.load(fh)
    return tables


LANG = _load_lang_tables()
# nightcall <= 0.3.3 wrote Russian field/status names and file names; the migration table and the
# old file names live in lang/ru.json's own "legacy" section (read-only, see _migrate() below).
LEGACY = LANG.get("ru", {}).get("legacy", {})

QUOTA_WORDS = {code: data["quota"] for code, data in LANG.items()}
QUOTA = re.compile("|".join(w for words in QUOTA_WORDS.values() for w in words), re.I)
AUTH_WORDS = {code: data["auth"] for code, data in LANG.items()}
AUTH = re.compile("|".join(w for words in AUTH_WORDS.values() for w in words), re.I)
# "resets at 3am", "try again at 14:30", "until 5:00 PM", "resets in 2h 15m" (and the same patterns
# in every other lang/<code>.json)
RESET_AT_WORDS = {code: data["reset_at"] for code, data in LANG.items()}
RESET_AT = re.compile(r"(?:" + "|".join(w for words in RESET_AT_WORDS.values() for w in words) + r")\D{0,12}?"
                      r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", re.I)
RESET_IN_WORDS = {code: data["reset_in"] for code, data in LANG.items()}
RESET_IN_HOUR_WORDS = {code: data["reset_in_hour"] for code, data in LANG.items()}
RESET_IN_MIN_WORDS = {code: data["reset_in_min"] for code, data in LANG.items()}
RESET_IN = re.compile(
    r"\b(?:" + "|".join(w for words in RESET_IN_WORDS.values() for w in words) + r")\s+"
    r"(?:(\d+)\s*(?:" + "|".join(w for words in RESET_IN_HOUR_WORDS.values() for w in words) + r"))?\s*"
    r"(?:(\d+)\s*(?:" + "|".join(w for words in RESET_IN_MIN_WORDS.values() for w in words) + r"))?", re.I)

EXTRA_PATH = ["~/.local/bin", "~/.kimi-code/bin", "/opt/homebrew/bin", "/usr/local/bin",
              "~/.npm-global/bin", "~/AppData/Roaming/npm"]
# Keys in the environment are not passed on to programs: a helper must use the person's
# SUBSCRIPTION sign-in, never a paid API key that happens to be set (V1 childEnv does the same).
SECRET = re.compile(r"(API[_-]?KEY|[_-]KEY|TOKEN|SECRET|PASSWORD|AUTH)$", re.I)


def now():
    return datetime.datetime.now()


def hhmm(dt=None):
    return (dt or now()).strftime("%H:%M")


def child_env():
    env = {k: v for k, v in os.environ.items() if not SECRET.search(k)}
    if os.environ.get("NIGHTCALL_PATH"):          # tests: look ONLY here
        env["PATH"] = os.environ["NIGHTCALL_PATH"]
    else:
        extra = [os.path.expanduser(p) for p in EXTRA_PATH]
        env["PATH"] = os.pathsep.join([env.get("PATH", "")] + extra)
    env["NIGHTCALL_HELPER"] = "1"
    return env


def which(binary):
    return shutil.which(binary, path=child_env()["PATH"])


def installed(with_main=False):
    seen, out = set(), []
    rows = ([MAIN] if with_main else []) + HELPERS
    for family, binary, _, label in rows:
        if family in seen:
            continue
        path = which(binary)
        if path:
            seen.add(family)
            out.append({"family": family, "program": binary, "name": label, "path": path})
    return out


def build(binary, prompt):
    return next(b for _, bin_, b, _ in [MAIN] + HELPERS if bin_ == binary)(prompt)


def reset_time(text, base=None):
    """The clock time a limit comes back, if the message says it. None when it does not."""
    base = base or now()
    m = RESET_IN.search(text)
    if m and (m.group(1) or m.group(2)):
        return base + datetime.timedelta(hours=int(m.group(1) or 0), minutes=int(m.group(2) or 0))
    m = RESET_AT.search(text)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ap.startswith("p") and h < 12:
            h += 12
        if ap.startswith("a") and h == 12:
            h = 0
        if h > 23 or mi > 59:
            return None
        t = base.replace(hour=h, minute=mi, second=0, microsecond=0)
        if t <= base:
            t += datetime.timedelta(days=1)
        return t
    return None


def classify(ok_exit, text, err):
    failed = not ok_exit or not text
    blob = f"{text}\n{err}"
    # some programs print "usage limit" as a normal short answer with exit code 0
    if (failed and QUOTA.search(blob)) or (not failed and len(text) < 300 and QUOTA.search(text)):
        back = reset_time(blob)
        r = {"ok": False, "status": "limit",
             "why": "this program's subscription allowance ran out — it comes back by itself"}
        if back:
            r["until"] = back.strftime("%Y-%m-%d %H:%M")
            r["why"] = f"limit until {back.strftime('%H:%M')} — comes back by itself after that"
        return r
    if failed and AUTH.search(blob):
        return {"ok": False, "status": "not-signed-in",
                "why": "no sign-in to the account visible — the person needs to sign in once, now"}
    if failed:
        last = (err.splitlines() or ["empty answer"])[-1][:300]
        return {"ok": False, "status": "error", "why": last}
    return {"ok": True, "status": "alive", "answer": text}


def run(helper, prompt, timeout, cwd=None):
    t0 = time.time()
    try:
        done = subprocess.run([helper["path"], *build(helper["program"], prompt)],
                              capture_output=True, text=True, timeout=timeout,
                              env=child_env(), cwd=cwd, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "why": f"did not answer within {timeout}s"}
    except OSError as e:
        return {"ok": False, "status": "failed-to-start", "why": str(e)}
    r = classify(done.returncode == 0, (done.stdout or "").strip(), (done.stderr or "").strip())
    r["seconds"] = round(time.time() - t0)
    return r


# ---------- free keys (the course lesson "Free AI keys") ----------

def keys_file():
    home = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
    return os.path.join(home, "free-keys.env")


def configured_keys():
    """Free keys the person already set up. Values never printed, never written to seats.json."""
    found = {}
    path = keys_file()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                found[k.strip()] = v.strip().strip('"').strip("'")
    out = []
    for name, var, url, models, label, wait in FREE_KEYS:
        key = os.environ.get(var) or found.get(var)
        if key:
            url = os.environ.get("NIGHTCALL_KEY_URL_" + name.upper().replace("-", "_"), url)
            out.append({"key": name, "name": label, "url": url, "models": models, "wait": wait,
                        "_key": key})
    return out


def limit_scope(name, detail):
    """A 429: "minute" - per-minute limit (next provider now, this one again later); "model" - the daily
    limit of this model only (Google, Groq: quota per project AND model); "provider" - the daily limit of
    the whole provider (OpenRouter free-models-per-day, any other)."""
    d = (detail or "").lower()
    if name == "nvidia" or re.search(r"perminute|per.minute|free-models-per-min|\brpm\b|\btpm\b", d):
        return "minute"  # NVIDIA has no daily cap, only ~40 a minute
    return "model" if name in ("google-ai-studio", "groq") else "provider"


def run_key_model(k, model, prompt, timeout):
    """One model of one key. Returns (result, http code or 0 for a timeout / network error)."""
    msg = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    if k["key"] in MAX_TOKENS:
        msg["max_tokens"] = MAX_TOKENS[k["key"]]
    if k["key"] == "groq" and model.startswith("qwen/"):
        msg["reasoning_format"] = "hidden"
    body = json.dumps(msg).encode()
    req = urllib.request.Request(k["url"], data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + k["_key"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        text = clean(data["choices"][0]["message"].get("content") or "")
        r = classify(True, text, "")
        return r, (0 if not text else 200)  # empty -> the next model
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        r = classify(False, "", f"{e.code} {detail}")
        r["_detail"] = detail
        if e.code in (401, 403) and r["status"] == "error":
            r = {"ok": False, "status": "not-signed-in", "why": "key not accepted — check it now"}
        return r, e.code
    except Exception as e:  # noqa - network, timeout, bad JSON: all the same for the night
        return {"ok": False, "status": "error", "why": str(e)[:300]}, 0


def run_key(k, prompt, timeout, probe=False):
    """Every model of the key in turn: 429/503/404/timeout -> the next one; key not accepted -> stop."""
    t0 = time.time()
    wait = min(timeout, k["wait"]) if probe and k.get("wait") else timeout
    tried = []
    r = {"ok": False, "status": "error", "why": "no models"}
    for model in k["models"]:
        r, code = run_key_model(k, model, prompt, wait)
        if r["ok"]:
            r["model"] = model
            break
        tried.append(f"{model}: {r['why'][:120]}")
        if code == 429:
            scope = limit_scope(k["key"], r.pop("_detail", ""))
            if scope == "minute" and not probe:
                r["later"] = True  # the next provider now, this key once more at the end
                back = now() + datetime.timedelta(minutes=1)
                r["until"] = back.strftime("%Y-%m-%d %H:%M")
                r["why"] = f"per-minute limit — comes back at {back:%H:%M}"
                break
            if scope == "minute":
                continue  # the roll call only asks whether the key works at all
            if scope == "provider":
                break
            continue  # this model's daily quota is spent; the next model has its own
        r.pop("_detail", None)
        if code not in NEXT_MODEL and code != 0:
            break
    if not r["ok"] and len(tried) > 1:
        r["why"] = "; ".join(tried)[:600]
    r["seconds"] = round(time.time() - t0)
    return r


# ---------- seats.json ----------

# Written by nightcall <= 0.3.3 (Russian field names and status words), before the English rename.
# Read-only: old seats.json / blind-answer files made before the rename still load correctly; nothing
# is ever written back under these old names. Covered by test_reads_legacy_russian_seats_and_blind_files.
# The actual old names live in lang/ru.json's "legacy" section (LEGACY, loaded above) - not here.
LEGACY_KEYS = LEGACY.get("keys", {})
LEGACY_STATUS = LEGACY.get("status", {})


def _migrate(obj):
    """Rename old Russian keys/status words to the current English ones, recursively. Read-only."""
    if isinstance(obj, dict):
        out = {LEGACY_KEYS.get(k, k): _migrate(v) for k, v in obj.items()}
        if out.get("status") in LEGACY_STATUS:
            out["status"] = LEGACY_STATUS[out["status"]]
        return out
    if isinstance(obj, list):
        return [_migrate(v) for v in obj]
    return obj


def load_seats(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return _migrate(json.load(fh))
    return None


def save_seats(path, seats):
    if not path:
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(seats, fh, ensure_ascii=False, indent=2)


def limit_passed(s):
    """A helper out of allowance whose reset time has passed is worth one more try."""
    if s.get("status") != "limit" or not s.get("until"):
        return False
    try:
        return datetime.datetime.strptime(s["until"], "%Y-%m-%d %H:%M") <= now()
    except ValueError:
        return False


def usable(s):
    return s.get("status") == "alive" or limit_passed(s)


def web_when(seats):
    return "morning" if (seats or {}).get("web_when") == "morning" else "night"


def decide_when(seats):
    return "morning" if (seats or {}).get("decide_when") == "morning" else "council"


def route(seats, found=None, keys=None):
    """The order of replacement for the next question: CLI -> free key -> web -> Claude critics."""
    seats = seats or {}
    order = []
    cli = {s["program"]: s for s in seats.get("helpers", [])}
    for h in (found if found is not None else installed()):
        s = cli.get(h["program"])
        if s is None or usable(s):
            order.append({"route": "cli", "who": h["program"], "name": h["name"]})
    kst = {s["key"]: s for s in seats.get("keys", [])}
    for k in (keys if keys is not None else configured_keys()):
        s = kst.get(k["key"])
        if s is None or usable(s):
            order.append({"route": "key", "who": k["key"], "name": k["name"]})
    for w in seats.get("web", []):
        if w.get("status") == "alive" and web_when(seats) == "night":
            order.append({"route": "web", "who": w["site"], "name": w.get("name", w["site"]),
                          "url": w.get("url", "")})
    order.append({"route": "claude", "who": "claude-critics",
                  "name": "Claude's own critics (a fresh sub-agent, with no memory of the reasoning)"})
    return order


def log_progress(path, line):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"- {hhmm()} Helpers: {line}\n")


def note_answer(seats, kind, who):
    if seats is None:
        return
    seats.setdefault("participated", {})
    key = f"{kind}:{who}"
    seats["participated"][key] = seats["participated"].get(key, 0) + 1


# ---------- commands ----------

def cmd_list(_):
    found = installed()
    if not found:
        print("No other AI programs on this computer. That's not a dead end: the reserve is free "
              "keys (if set up) and web chats in Chrome that pass the roll call.")
        return 1
    print(f"Found {len(found)} program(s) of other companies:")
    for f in found:
        print(f"  {f['name']} — {f['program']} ({f['path']})")
    return 0


def table(rows):
    w = max([len(r[0]) for r in rows] + [10])
    print(f"  {'Who':<{w}}  {'Result':<14} Details")
    for name, st, why in rows:
        print(f"  {name:<{w}}  {st:<14} {why}")


def cmd_rollcall(args):
    old = load_seats(args.out) or {}
    rows, cli, keys = [], [], []
    have = installed(with_main=True)
    fams = {h["family"] for h in have}
    for family, binary, _, label in [MAIN] + HELPERS:
        if family not in fams:
            fams.add(family)
            rows.append((label, "not installed", f"{binary} is not installed — you can install it now"))
    for h in have:
        r = run(h, PROBE_TEXT, PROBE_TIMEOUT)
        row = {**{k: h[k] for k in ("family", "program", "name")}, "status": r["status"],
               "seconds": r.get("seconds"), "why": r.get("why", ""), "checked": hhmm()}
        if r.get("until"):
            row["until"] = r["until"]
        if h["program"] != "claude":
            cli.append(row)
        detail = f"answered in {r.get('seconds')}s" if r["ok"] else r.get("why", "")
        rows.append((h["name"], r["status"], detail))
    for k in configured_keys():
        r = run_key(k, PROBE_TEXT, PROBE_TIMEOUT, probe=True)
        row = {"key": k["key"], "name": k["name"], "status": r["status"],
               "why": r.get("why", ""), "checked": hhmm()}
        if r.get("until"):
            row["until"] = r["until"]
        keys.append(row)
        rows.append((f"{k['name']} (key)", r["status"],
                     f"answered in {r.get('seconds')}s ({r['model']})" if r["ok"] else r.get("why", "")))
    print("Roll call — subscription programs and free keys:")
    table(rows)
    seats = {"checked": now().strftime("%Y-%m-%d %H:%M"), "helpers": cli, "keys": keys,
             "web": old.get("web", []), "browser": old.get("browser", {}),
             "participated": old.get("participated", {}), "web_when": web_when(old),
             "decide_when": decide_when(old)}
    if args.out:
        save_seats(args.out, seats)
        print(f"Saved to {args.out}. Next — the browser (skill team, \"Browser roll call\"), "
              f"then: team.py summary --seats {args.out}")
    return 0 if any(usable(s) for s in cli + keys) else 1


def cmd_web_sites(_):
    for name, url, label in WEB_SITES:
        print(f"{name}\t{url}\t{label}")
    return 0


def cmd_web_mark(args):
    seats = load_seats(args.seats) or {"helpers": [], "keys": [], "web": []}
    if args.browser:
        seats["browser"] = {"status": args.browser, "why": args.why or "", "checked": hhmm()}
        save_seats(args.seats, seats)
        print(f"Browser: {args.browser}")
        return 0
    if not args.site:
        print("need --site or --browser", file=sys.stderr)
        return 2
    known = {n: (u, l) for n, u, l in WEB_SITES}
    site = args.site.lower()
    url, label = known.get(site, (args.url or "", args.site))
    web = [w for w in seats.setdefault("web", []) if w["site"] != site]
    prev = next((w for w in seats["web"] if w["site"] == site), {})
    if args.answered:
        note_answer(seats, "web", site)
        status = prev.get("status", "alive")
    else:
        status = args.status
        if status not in WEB_STATES:
            print(f"status: one of {', '.join(WEB_STATES)}", file=sys.stderr)
            return 2
    entry = {"site": site, "name": label, "url": url or prev.get("url", ""), "status": status,
             "why": args.why or prev.get("why", ""), "checked": hhmm()}
    web.append(entry)
    seats["web"] = web
    save_seats(args.seats, seats)
    if not args.answered and prev and prev.get("status") != status:
        log_progress(args.progress, f"web {label}: {prev.get('status')} → {status}"
                     + (f" ({args.why})" if args.why else ""))
    print(f"web-{site}: {status}")
    return 0


def cmd_web_when(args):
    seats = load_seats(args.seats) or {"helpers": [], "keys": [], "web": []}
    seats["web_when"] = args.when
    save_seats(args.seats, seats)
    print("web chats: " + ("night reserve (after programs and keys)" if args.when == "night" else
                          "in the morning — at night the question for them goes into morning-advice.md"))
    return 0


def cmd_decide_when(args):
    seats = load_seats(args.seats) or {"helpers": [], "keys": [], "web": []}
    seats["decide_when"] = args.when
    save_seats(args.seats, seats)
    print("human forks in the road: " + ("the AI council decides at night, each decision its own commit "
                                   "with an undo in the morning" if args.when == "council" else
                                   "all to the morning — the task is paused with a question, the night "
                                   "moves on to other parts"))
    return 0


DECISIONS_HEAD = ("# Decisions of the night\n\nForks in the road usually left to the person. In the "
                  "morning they come first in MORNING.md, under \"Needs your decision\".\n"
                  "Sending, publishing, paying, deleting without recovery, and signing in with a "
                  "password — the council never decides these; they always wait for morning.\n")


LEGACY_DECISIONS_NAME = LEGACY.get("decisions_file", "")  # written by nightcall <= 0.3.3; read-only fallback


def decisions_file(folder):
    folder = folder or os.getcwd()
    path = os.path.join(folder, "decisions.md")
    legacy = os.path.join(folder, LEGACY_DECISIONS_NAME) if LEGACY_DECISIONS_NAME else path
    if not os.path.exists(path) and os.path.exists(legacy):
        return legacy  # keep appending to the file the person already has
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DECISIONS_HEAD)
    return path


def cmd_decide(args):
    path = decisions_file(args.dir)
    undo = f"git revert {args.commit}" if args.commit else (args.undo or "manually: revert to how it was before the decision")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"\n## {now():%d.%m %H:%M} — the AI council decided: {args.what}\n"
                 f"- Why: {args.why}\n- Who advised: {args.who}\n"
                 f"- Other options: {args.alt or '—'}\n- Commit: {args.commit or '—'}\n"
                 f"- Undo: `{undo}`\n- Fix it like this: \"…\" — write it in the morning, Claude will redo it\n")
    print(json.dumps({"decisions": path, "undo": undo}, ensure_ascii=False))
    return 0


def cmd_hold(args):
    path = decisions_file(args.dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"\n## {now():%d.%m %H:%M} — waiting for your answer: {args.question}\n"
                 f"- On hold without an answer: {args.waits or '—'}\n- Options: {args.alt or '—'}\n- Your answer: \n")
    print(json.dumps({"decisions": path, "paused": args.waits or args.question}, ensure_ascii=False))
    return 0


LEGACY_MORNING_ADVICE_NAME = LEGACY.get("morning_advice_file", "")  # written by nightcall <= 0.3.3; read-only fallback


def save_for_morning(args, prompt):
    folder = args.dir or (os.path.dirname(os.path.abspath(args.seats)) if args.seats else os.getcwd())
    path = os.path.join(folder, "morning-advice.md")
    legacy = os.path.join(folder, LEGACY_MORNING_ADVICE_NAME) if LEGACY_MORNING_ADVICE_NAME else path
    if not os.path.exists(path) and os.path.exists(legacy):
        path = legacy  # keep appending to the file the person already has
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new:
            fh.write("# Questions for web chats — in the morning\n\nYou chose \"web: morning\": at night "
                     "these questions did not go to web chats. In the morning you can ask ChatGPT, "
                     "Gemini, Kimi… one at a time.\n")
        fh.write(f"\n## {now():%d.%m %H:%M}\n\n{prompt.strip()}\n")
    return path


def summarize(seats):
    work, reserve, broken, todo = [], [], [], []
    for s in seats.get("helpers", []):
        name = s["name"]
        if s["status"] == "alive":
            work.append(name)
        elif s["status"] == "limit":
            broken.append(f"{name} — limit" + (f" until {s['until'][-5:]}" if s.get("until") else ""))
            if s.get("until"):
                reserve.append(f"{name} (comes back after {s['until'][-5:]})")
        elif s["status"] == "not-signed-in":
            broken.append(f"{name} — not signed in")
            todo.append(f"sign in to {s['program']}: run it once in the terminal and sign in")
        else:
            broken.append(f"{name} — {s['status']}")
    for k in seats.get("keys", []):
        (reserve if k["status"] == "alive" else broken).append(
            f"{k['name']} (key)" + ("" if k["status"] == "alive" else f" — {k['status']}"))
    br = seats.get("browser", {})
    if br and br.get("status") != "alive":
        broken.append(f"Chrome browser — {br.get('status')}")
        todo.append("browser: install/enable the Claude in Chrome extension and click \"Allow\" now")
    for w in seats.get("web", []):
        if w["status"] == "alive":
            reserve.append(f"web {w['name']}" + (" (in the morning)" if web_when(seats) == "morning" else ""))
        else:
            broken.append(f"web {w['name']} — {w['status']}")
            if w["status"] in ("needs-sign-in", "captcha"):
                todo.append(f"{w['name']}: open {w.get('url') or w['site']} and sign in / pass the check")
    if not work and not reserve:
        todo.insert(0, "no other company's helper is alive at all — install and sign in to at least "
                       "one program (codex, gemini/agy, kimi, grok, qwen) or sign in to 2–3 web chats")
    return work, reserve, broken, todo


def cmd_summary(args):
    seats = load_seats(args.seats) or {}
    work, reserve, broken, todo = summarize(seats)
    print("Roll call summary:")
    print("  Working tonight: " + (", ".join(work) or "—"))
    print("  Reserve: " + (", ".join(reserve) or "—"))
    print("  Not working: " + (", ".join(broken) or "—"))
    print("  Human forks in the road: " + ("the AI council decides, in the morning — a list with an undo "
                                     "for each decision" if decide_when(seats) == "council" else
                                     "all to the morning — tasks with a question wait for you"))
    if not work and not reserve:
        print("  Tonight's second head is Claude's own critics (a fresh sub-agent). One program or web "
              "chat signed in now brings in another company:")
    if todo:
        print("  What to do now, while you're still here:")
        for t in todo:
            print(f"    - {t}")
    return 0 if (work or reserve) else 1


def cmd_next(args):
    print(json.dumps(route(load_seats(args.seats)), ensure_ascii=False, indent=2))
    return 0


def cmd_used(args):
    seats = load_seats(args.seats) or {}
    used = seats.get("participated", {})
    if not used:
        print("Tonight's second head was Claude's own critics: no other company's helper answered.")
        return 1
    for k, n in sorted(used.items(), key=lambda x: -x[1]):
        print(f"  {k} — answers: {n}")
    return 0


def cmd_ask(args):
    found = installed()
    seats = load_seats(args.seats)
    keys = configured_keys()
    order = [x for x in route(seats, found, keys) if x["route"] in ("cli", "key")]
    if args.who:
        first = [x for x in order if args.who.lower() == x["who"] or
                 any(h["family"] == args.who.lower() and h["program"] == x["who"] for h in found)]
        order = first + [x for x in order if x not in first]
    if not args.fallback:
        order = order[:1]
    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt
    tried = []
    again = set()
    for x in order:
        if x["route"] == "cli":
            h = next(h for h in found if h["program"] == x["who"])
            r = run(h, prompt, ASK_TIMEOUT, cwd=args.dir)
        else:
            k = next(k for k in keys if k["key"] == x["who"])
            r = run_key(k, prompt, ASK_TIMEOUT)
            if r.pop("later", False) and x["who"] not in again:
                again.add(x["who"])
                order.append(x)  # per-minute limit: back at the end of the line, once
        if r["ok"]:
            if tried:
                log_progress(args.progress, "; ".join(f"{t['who']} — {t['why']}" for t in tried)
                             + f"; replaced: {x['name']}")
            mark(args.seats, x, r)
            if args.blind:
                # Blind comparison (owner, 01.10.2026): a judge AI leans to the answer that sounds like
                # itself, so the answer is saved with its name and Claude sees it only as "Answer A".
                saved = save_blind(args.blind, x, r)
                print(json.dumps({"ok": True, "saved": saved, "could_not": len(tried),
                                  "next": f"team.py blind --dir {args.blind}"}, ensure_ascii=False))
                return 0
            print(json.dumps({"ok": True, "who": x["name"], "route": x["route"], "program": x["who"],
                              "seconds": r.get("seconds"), "could_not": tried, "answer": r["answer"]},
                             ensure_ascii=False))
            return 0
        tried.append({"who": x["name"], "status": r["status"], "why": r["why"]})
        mark(args.seats, x, r)
    now_seats = load_seats(args.seats)
    rest = [x for x in route(now_seats, found, keys) if x["route"] in ("web", "claude")]
    nxt = rest[0]
    morning = None
    if web_when(now_seats) == "morning" and any(w.get("status") == "alive" for w in (now_seats or {}).get("web", [])):
        morning = save_for_morning(args, prompt)
        log_progress(args.progress, f"question for web chats saved for the morning: {morning}")
    if tried:
        log_progress(args.progress, "; ".join(f"{t['who']} — {t['why']}" for t in tried)
                     + f"; next: {nxt['name']}")
    print(json.dumps({"ok": False, "could_not": tried,
                      "why": "no program and no key answered" if tried else
                      "no other company's program or key is alive",
                      "next": nxt, "reserve": rest, "morning_advice": morning}, ensure_ascii=False))
    return 1


# ---------- blind comparison: answers without names until the decision ----------

BLIND_KEY = ".who-is-who.json"
LEGACY_BLIND_KEY = LEGACY.get("blind_key_file", "")  # written by nightcall <= 0.3.3; read-only fallback
LEGACY_ANSWER_PREFIX = LEGACY.get("answer_prefix", "")  # same; new answers are always "answer-N.json"


def _is_answer_file(name):
    return name.endswith(".json") and (name.startswith("answer-") or
                                        (LEGACY_ANSWER_PREFIX and name.startswith(LEGACY_ANSWER_PREFIX)))


def save_blind(folder, x, r):
    os.makedirs(folder, exist_ok=True)
    n = len([f for f in os.listdir(folder) if _is_answer_file(f)]) + 1
    path = os.path.join(folder, f"answer-{n}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"who": x["name"], "route": x["route"], "answer": r["answer"]}, fh, ensure_ascii=False, indent=1)
    return path


def blind_answers(folder):
    """Every saved answer as "Answer A / B / C" in a random order; who is who goes to a file Claude
    does not read until it has decided. Also picks up answer-*.json files saved by nightcall <= 0.3.3
    under their pre-0.3.4 Russian-named prefix (see lang/ru.json legacy, old Russian field names) -
    read-only."""
    import random
    files = sorted(f for f in os.listdir(folder) if _is_answer_file(f))
    answers = [_migrate(json.load(open(os.path.join(folder, f), encoding="utf-8"))) for f in files]
    random.shuffle(answers)
    letters = [chr(ord("A") + i) if i < 26 else f"A{i}" for i in range(len(answers))]
    with open(os.path.join(folder, BLIND_KEY), "w", encoding="utf-8") as fh:
        json.dump({l: a["who"] for l, a in zip(letters, answers)}, fh, ensure_ascii=False, indent=1)
    return "\n\n".join(f"## Answer {l}\n\n{a['answer'].strip()}" for l, a in zip(letters, answers))


def cmd_blind(args):
    if not os.path.isdir(args.dir):
        print(f"no folder {args.dir}")
        return 1
    print(blind_answers(args.dir))
    print("\nNames are hidden. Decide first, then: team.py reveal --dir " + args.dir)
    return 0


def cmd_reveal(args):
    path = os.path.join(args.dir, BLIND_KEY)
    legacy = os.path.join(args.dir, LEGACY_BLIND_KEY) if LEGACY_BLIND_KEY else path
    if not os.path.exists(path) and os.path.exists(legacy):
        path = legacy
    if not os.path.exists(path):
        print("team.py blind hasn't run yet")
        return 1
    print(json.dumps(json.load(open(path, encoding="utf-8")), ensure_ascii=False))
    return 0


def mark(path, x, result):
    seats = load_seats(path)
    if not seats:
        return
    group, field = ("helpers", "program") if x["route"] == "cli" else ("keys", "key")
    for s in seats.get(group, []):
        if s.get(field) == x["who"]:
            s["status"], s["why"], s["checked"] = result["status"], result.get("why", ""), hhmm()
            if result.get("until"):
                s["until"] = result["until"]
            elif result["ok"]:
                s.pop("until", None)
    if result["ok"]:
        note_answer(seats, x["route"], x["who"])
    save_seats(path, seats)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall: other companies' AI helpers.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("rollcall", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--out", help="where to save who's alive (seats.json in the task folder)")
    sub.add_parser("web-sites")
    w = sub.add_parser("web-mark")
    w.add_argument("--seats", required=True)
    w.add_argument("--site", help="chatgpt, gemini, kimi, deepseek, meta, grok, qwen, mistral …")
    w.add_argument("--url")
    w.add_argument("--status", default="alive", help=" | ".join(WEB_STATES))
    w.add_argument("--why", default="")
    w.add_argument("--browser", help="the browser's own state: alive | no-extension | no-permission")
    w.add_argument("--answered", action="store_true", help="the site answered a question at night (for the morning)")
    w.add_argument("--progress", help="PROGRESS.md: log the change of state")
    ww = sub.add_parser("web-when")
    ww.add_argument("--seats", required=True)
    ww.add_argument("when", choices=["night", "morning"], help="night — web chats are the night reserve; morning — questions in the morning")
    dw = sub.add_parser("decide-when")
    dw.add_argument("--seats", required=True)
    dw.add_argument("when", choices=["council", "morning"],
                    help="council — the AI council decides forks in the road (default); morning — all to the morning")
    d = sub.add_parser("decide")
    d.add_argument("--dir", help="the task folder (decisions.md lives there)")
    d.add_argument("--what", required=True)
    d.add_argument("--why", required=True)
    d.add_argument("--who", required=True, help="who advised: codex, grok, its own critics…")
    d.add_argument("--alt", default="")
    d.add_argument("--commit", default="", help="this decision's commit — in the morning: git revert <commit>")
    d.add_argument("--undo", default="", help="how to undo it, if not git")
    h = sub.add_parser("hold")
    h.add_argument("--dir")
    h.add_argument("--question", required=True)
    h.add_argument("--waits", default="", help="what is on hold without an answer")
    h.add_argument("--alt", default="")
    for name in ("summary", "next", "used"):
        p = sub.add_parser(name)
        p.add_argument("--seats", required=True)
    a = sub.add_parser("ask")
    a.add_argument("prompt", help="the question, or - to read it from standard input")
    a.add_argument("--who", help="who to ask first: codex, agy, gemini, grok, kimi, qwen, openrouter…")
    a.add_argument("--seats", help="seats.json from the roll call: dead ones are skipped, newly dead ones are marked")
    a.add_argument("--progress", help="PROGRESS.md: every replacement, as a line")
    a.add_argument("--dir", help="a folder the helper may read (its working folder)")
    a.add_argument("--blind", metavar="DIR",
                   help="blind comparison: the answer goes to DIR with no name on screen; then blind and reveal")
    a.add_argument("--no-fallback", dest="fallback", action="store_false",
                   help="do not move on to the next one if the first does not answer")
    for name in ("blind", "reveal"):
        p = sub.add_parser(name)
        p.add_argument("--dir", required=True, help="the answers folder from ask --blind")
    args = ap.parse_args(argv)
    return {"list": cmd_list, "rollcall": cmd_rollcall, "probe": cmd_rollcall,
            "web-sites": cmd_web_sites, "web-mark": cmd_web_mark, "web-when": cmd_web_when,
            "decide-when": cmd_decide_when, "decide": cmd_decide, "hold": cmd_hold, "summary": cmd_summary,
            "next": cmd_next, "used": cmd_used, "ask": cmd_ask,
            "blind": cmd_blind, "reveal": cmd_reveal}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
