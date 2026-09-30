#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall team: find the other AIs already on this computer, check which are alive, ask them.

Claude is the main agent for the night. This script finds its helpers: AI programs of OTHER
companies that the person already installed and signed in to with their own subscription
(ChatGPT/Codex, Gemini, Grok, Kimi, Qwen). It never installs anything, never signs anyone in,
never asks for a key and never spends money: it only drives what is already there.

    python3 team.py list                         # who is installed
    python3 team.py probe [--out seats.json]     # who is ALIVE right now (short test question)
    python3 team.py ask [--who codex] [--dir D] [--seats seats.json] -   # question on stdin

`ask` walks down the list: if the chosen helper is out of its allowance, not signed in or silent,
the next live helper of another company gets the same question, and the answer says who really
answered and who fell out and why. A helper that fails is marked dead in seats.json, so the rest
of the night does not wait on it again.

Command lines and the "dead" patterns are taken from the owner's V1 Synthesizer
(packages/synthesizer/real-deps.mjs): the same flags that run there every night.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

# (family, binary, argv builder, human name). Claude is absent on purpose: it is the one asking.
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

PROBE_TEXT = "Проверка связи. Ответь одним словом: ок"
PROBE_TIMEOUT = int(os.environ.get("NIGHTCALL_PROBE_TIMEOUT", "90"))
ASK_TIMEOUT = int(os.environ.get("NIGHTCALL_ASK_TIMEOUT", "900"))

# From V1 real-deps.mjs QUOTA_WORDS: the allowance ran out - not a breakage, it comes back by itself.
QUOTA = re.compile(r"\brate[ _-]?limit|\busage limit|\bquota\b|\b429\b|too many requests|limit reached|"
                   r"out of (?:extra )?(?:usage|credits)|resource[_ ]exhausted|payment required|"
                   r"\b402\b|balance (?:is )?exhausted|insufficient[ _](?:balance|credits?)", re.I)
AUTH = re.compile(r"not (?:logged|signed) in|please (?:log|sign) ?in|unauthori[sz]ed|\b401\b|"
                  r"authenticat|login required|no credentials|auth type|api key", re.I)

EXTRA_PATH = ["~/.local/bin", "~/.kimi-code/bin", "/opt/homebrew/bin", "/usr/local/bin",
              "~/.npm-global/bin", "~/AppData/Roaming/npm"]
# Keys in the environment are not passed on: a helper must use the person's SUBSCRIPTION sign-in,
# never a paid API key that happens to be set (V1 childEnv does the same).
SECRET = re.compile(r"(API[_-]?KEY|[_-]KEY|TOKEN|SECRET|PASSWORD|AUTH)$", re.I)


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


def installed():
    seen, out = set(), []
    for family, binary, _, label in HELPERS:
        if family in seen:
            continue
        path = which(binary)
        if path:
            seen.add(family)
            out.append({"семья": family, "программа": binary, "имя": label, "где": path})
    return out


def build(binary, prompt):
    return next(b for _, bin_, b, _ in HELPERS if bin_ == binary)(prompt)


def run(helper, prompt, timeout, cwd=None):
    t0 = time.time()
    try:
        done = subprocess.run([helper["где"], *build(helper["программа"], prompt)],
                              capture_output=True, text=True, timeout=timeout,
                              env=child_env(), cwd=cwd, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"ok": False, "статус": "молчит", "почему": f"не ответил за {timeout} с"}
    except OSError as e:
        return {"ok": False, "статус": "не запустился", "почему": str(e)}
    secs = round(time.time() - t0)
    text = (done.stdout or "").strip()
    err = (done.stderr or "").strip()
    failed = done.returncode != 0 or not text
    blob = f"{text}\n{err}"
    # some programs print "usage limit" as a normal short answer with exit code 0
    if (failed and QUOTA.search(blob)) or (not failed and len(text) < 300 and QUOTA.search(text)):
        return {"ok": False, "статус": "кончился запас", "секунд": secs,
                "почему": "у этой программы кончился запас по подписке — вернётся сам"}
    if failed and AUTH.search(blob):
        return {"ok": False, "статус": "не вошли", "секунд": secs,
                "почему": "программа не видит входа в аккаунт — человеку нужно войти в неё один раз"}
    if failed:
        last = (err.splitlines() or [f"код возврата {done.returncode}"])[-1][:300]
        return {"ok": False, "статус": "сбой", "секунд": secs, "почему": last}
    return {"ok": True, "статус": "жив", "секунд": secs, "ответ": text}


def cmd_list(_):
    found = installed()
    if not found:
        print("Других ИИ-программ на этом компьютере нет. Это не тупик: помощники будут через "
              "бесплатные веб-чаты в браузере (скилл team, раздел «Через браузер»).")
        return 1
    print(f"Нашёл {len(found)} программ(ы) других компаний:")
    for f in found:
        print(f"  {f['имя']} — {f['программа']} ({f['где']})")
    return 0


def cmd_probe(args):
    found = installed()
    results = []
    for h in found:
        r = run(h, PROBE_TEXT, PROBE_TIMEOUT)
        row = {**{k: h[k] for k in ("семья", "программа", "имя")},
               "статус": r["статус"], "секунд": r.get("секунд"), "почему": r.get("почему", ""),
               "проверено": time.strftime("%H:%M")}
        results.append(row)
        mark = "ЖИВ " if r["ok"] else "НЕТ "
        print(f"  {mark} {h['имя']:<18} {r['статус']}" + (f" — {r['почему']}" if not r["ok"] else
                                                           f" ({r.get('секунд')} с)"), flush=True)
    alive = [r for r in results if r["статус"] == "жив"]
    print(f"Живых помощников: {len(alive)} из {len(found)} найденных.")
    if not alive:
        print("Ни одного живого — помощники этой ночью через бесплатные веб-чаты в браузере.")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"проверено": time.strftime("%Y-%m-%d %H:%M"), "помощники": results},
                      fh, ensure_ascii=False, indent=2)
        print(f"Записал в {args.out}")
    return 0 if alive else 1


def load_seats(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def cmd_ask(args):
    found = installed()
    seats = load_seats(args.seats)
    dead = set()
    if seats:
        dead = {s["программа"] for s in seats.get("помощники", []) if s.get("статус") != "жив"}
    order = [h for h in found if h["программа"] not in dead]
    if args.who:
        first = [h for h in order if args.who.lower() in (h["программа"], h["семья"])]
        order = first + [h for h in order if h not in first]
    if not args.fallback:
        order = order[:1]
    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt
    tried = []
    for h in order:
        r = run(h, prompt, ASK_TIMEOUT, cwd=args.dir)
        if r["ok"]:
            print(json.dumps({"ok": True, "кто": h["имя"], "программа": h["программа"],
                              "семья": h["семья"], "секунд": r["секунд"], "не_смогли": tried,
                              "ответ": r["ответ"]}, ensure_ascii=False))
            return 0
        tried.append({"кто": h["имя"], "статус": r["статус"], "почему": r["почему"]})
        mark_dead(args.seats, h, r)
    print(json.dumps({"ok": False, "не_смогли": tried,
                      "почему": "ни одна программа не ответила" if tried else
                      "живых программ других компаний нет",
                      "дальше": "через бесплатный веб-чат в браузере"}, ensure_ascii=False))
    return 1


def mark_dead(path, helper, result):
    seats = load_seats(path)
    if not seats:
        return
    for s in seats.get("помощники", []):
        if s["программа"] == helper["программа"]:
            s["статус"], s["почему"], s["проверено"] = result["статус"], result["почему"], time.strftime("%H:%M")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(seats, fh, ensure_ascii=False, indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall: помощники-ИИ других компаний.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("probe")
    p.add_argument("--out", help="куда записать, кто жив (seats.json в папке задачи)")
    a = sub.add_parser("ask")
    a.add_argument("prompt", help="вопрос или - для чтения со стандартного ввода")
    a.add_argument("--who", help="кого спросить первым: codex, agy, gemini, grok, kimi, qwen")
    a.add_argument("--seats", help="seats.json из probe: мёртвых пропускаем, новых мёртвых отмечаем")
    a.add_argument("--dir", help="папка, которую помощник может читать (его рабочая папка)")
    a.add_argument("--no-fallback", dest="fallback", action="store_false",
                   help="не переходить к следующему, если первый не ответил")
    args = ap.parse_args(argv)
    return {"list": cmd_list, "probe": cmd_probe, "ask": cmd_ask}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
