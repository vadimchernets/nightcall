#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall team: who helps Claude tonight - checked while the person is still here, replaced at night.

Claude is the main agent for the night. Its helpers are AIs of OTHER companies, in this order:

  1. programs by subscription already on this computer (codex, agy/gemini, grok, kimi, qwen);
  2. free keys, only if the person set them up earlier (course step 12A): OpenRouter free models,
     Groq, Google AI Studio - read from the environment or ~/.nightcall/free-keys.env;
  3. web chats in the person's own Chrome - only the sites that passed the roll call (web-mark);
  4. Claude's own critics (a fresh sub-agent) - when nobody else is left, said out loud.

    python3 team.py list                              # who is installed
    python3 team.py rollcall --out seats.json         # the roll call: every CLI and key gets a test question
    python3 team.py probe [--out seats.json]          # same as rollcall (old name)
    python3 team.py web-sites                         # the web chats to check in Chrome
    python3 team.py web-mark --seats S --site chatgpt --status жив|нужен вход|капча|не открылся
    python3 team.py summary --seats seats.json        # «Ночью работают / запас / не работает / что сделать»
    python3 team.py ask [--who codex] [--seats S] [--progress PROGRESS.md] -   # question on stdin
    python3 team.py next --seats seats.json           # the route for the next question, no call made
    python3 team.py used --seats seats.json           # who really took part (for MORNING.md)

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
MAIN = ("anthropic", "claude", lambda p: ["-p", p], "Claude (главный)")

# Free keys (course step 12A). Only used when the person already put the key in the environment or
# in ~/.nightcall/free-keys.env. OpenAI-compatible chat endpoints, free models only.
FREE_KEYS = [
    ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions",
     "deepseek/deepseek-chat-v3-0324:free", "OpenRouter (бесплатная модель)"),
    ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions",
     "llama-3.3-70b-versatile", "Groq"),
    ("google-ai-studio", "GEMINI_API_KEY",
     "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "gemini-2.5-flash", "Gemini (AI Studio)"),
]

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
WEB_STATES = ("жив", "нужен вход", "капча", "не открылся", "нет браузера")

PROBE_TEXT = "Проверка связи. Ответь одним словом: ок"
PROBE_TIMEOUT = int(os.environ.get("NIGHTCALL_PROBE_TIMEOUT", "90"))
ASK_TIMEOUT = int(os.environ.get("NIGHTCALL_ASK_TIMEOUT", "900"))

# From V1 real-deps.mjs QUOTA_WORDS: the allowance ran out - not a breakage, it comes back by itself.
QUOTA = re.compile(r"\brate[ _-]?limit|\busage limit|\bquota\b|\b429\b|too many requests|limit reached|"
                   r"out of (?:extra )?(?:usage|credits)|resource[_ ]exhausted|payment required|"
                   r"\b402\b|balance (?:is )?exhausted|insufficient[ _](?:balance|credits?)|"
                   r"hit your limit|лимит", re.I)
AUTH = re.compile(r"not (?:logged|signed) in|please (?:log|sign) ?in|unauthori[sz]ed|\b401\b|"
                  r"authenticat|login required|no credentials|auth type|api key|войдите", re.I)
# "resets at 3am", "try again at 14:30", "until 5:00 PM", "resets in 2h 15m", "сброс в 03:00"
RESET_AT = re.compile(r"(?:reset[s]?|try again|available|until|до|сброс\w*)\D{0,12}?"
                      r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", re.I)
RESET_IN = re.compile(r"\b(?:in|через)\s+(?:(\d+)\s*(?:h|hours?|ч\w*))?\s*(?:(\d+)\s*(?:m|min\w*|мин\w*))?", re.I)

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
            out.append({"семья": family, "программа": binary, "имя": label, "где": path})
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
        r = {"ok": False, "статус": "лимит",
             "почему": "у этой программы кончился запас по подписке — вернётся сам"}
        if back:
            r["до"] = back.strftime("%Y-%m-%d %H:%M")
            r["почему"] = f"лимит до {back.strftime('%H:%M')} — потом вернётся сам"
        return r
    if failed and AUTH.search(blob):
        return {"ok": False, "статус": "не вошли",
                "почему": "не видно входа в аккаунт — человеку нужно войти один раз, сейчас"}
    if failed:
        last = (err.splitlines() or ["пустой ответ"])[-1][:300]
        return {"ok": False, "статус": "сбой", "почему": last}
    return {"ok": True, "статус": "жив", "ответ": text}


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
    r = classify(done.returncode == 0, (done.stdout or "").strip(), (done.stderr or "").strip())
    r["секунд"] = round(time.time() - t0)
    return r


# ---------- free keys (step 12A) ----------

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
    for name, var, url, model, label in FREE_KEYS:
        key = os.environ.get(var) or found.get(var)
        if key:
            url = os.environ.get("NIGHTCALL_KEY_URL_" + name.upper().replace("-", "_"), url)
            out.append({"ключ": name, "имя": label, "адрес": url, "модель": model, "_key": key})
    return out


def run_key(k, prompt, timeout):
    t0 = time.time()
    body = json.dumps({"model": k["модель"], "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(k["адрес"], data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + k["_key"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        text = (data["choices"][0]["message"]["content"] or "").strip()
        r = classify(True, text, "")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        r = classify(False, "", f"{e.code} {detail}")
        if e.code in (401, 403) and r["статус"] == "сбой":
            r = {"ok": False, "статус": "не вошли", "почему": "ключ не принят — проверьте его сейчас"}
    except Exception as e:  # noqa - network, timeout, bad JSON: all the same for the night
        r = {"ok": False, "статус": "сбой", "почему": str(e)[:300]}
    r["секунд"] = round(time.time() - t0)
    return r


# ---------- seats.json ----------

def load_seats(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def save_seats(path, seats):
    if not path:
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(seats, fh, ensure_ascii=False, indent=2)


def limit_passed(s):
    """A helper out of allowance whose reset time has passed is worth one more try."""
    if s.get("статус") != "лимит" or not s.get("до"):
        return False
    try:
        return datetime.datetime.strptime(s["до"], "%Y-%m-%d %H:%M") <= now()
    except ValueError:
        return False


def usable(s):
    return s.get("статус") == "жив" or limit_passed(s)


def route(seats, found=None, keys=None):
    """The order of replacement for the next question: CLI -> free key -> web -> Claude critics."""
    seats = seats or {}
    order = []
    cli = {s["программа"]: s for s in seats.get("помощники", [])}
    for h in (found if found is not None else installed()):
        s = cli.get(h["программа"])
        if s is None or usable(s):
            order.append({"путь": "cli", "кто": h["программа"], "имя": h["имя"]})
    kst = {s["ключ"]: s for s in seats.get("ключи", [])}
    for k in (keys if keys is not None else configured_keys()):
        s = kst.get(k["ключ"])
        if s is None or usable(s):
            order.append({"путь": "ключ", "кто": k["ключ"], "имя": k["имя"]})
    for w in seats.get("веб", []):
        if w.get("статус") == "жив":
            order.append({"путь": "веб", "кто": w["сайт"], "имя": w.get("имя", w["сайт"]),
                          "адрес": w.get("адрес", "")})
    order.append({"путь": "claude", "кто": "claude-critics",
                  "имя": "свои критики Claude (свежий субагент, без памяти о рассуждениях)"})
    return order


def log_progress(path, line):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"- {hhmm()} Помощники: {line}\n")


def note_answer(seats, kind, who):
    if seats is None:
        return
    seats.setdefault("участвовали", {})
    key = f"{kind}:{who}"
    seats["участвовали"][key] = seats["участвовали"].get(key, 0) + 1


# ---------- commands ----------

def cmd_list(_):
    found = installed()
    if not found:
        print("Других ИИ-программ на этом компьютере нет. Это не тупик: запас — бесплатные ключи "
              "(если настроены) и веб-чаты в Chrome, которые пройдут перекличку.")
        return 1
    print(f"Нашёл {len(found)} программ(ы) других компаний:")
    for f in found:
        print(f"  {f['имя']} — {f['программа']} ({f['где']})")
    return 0


def table(rows):
    w = max([len(r[0]) for r in rows] + [10])
    print(f"  {'Кто':<{w}}  {'Итог':<14} Подробности")
    for name, st, why in rows:
        print(f"  {name:<{w}}  {st:<14} {why}")


def cmd_rollcall(args):
    old = load_seats(args.out) or {}
    rows, cli, keys = [], [], []
    have = installed(with_main=True)
    fams = {h["семья"] for h in have}
    for family, binary, _, label in [MAIN] + HELPERS:
        if family not in fams:
            fams.add(family)
            rows.append((label, "нет программы", f"{binary} не установлен — можно поставить сейчас"))
    for h in have:
        r = run(h, PROBE_TEXT, PROBE_TIMEOUT)
        row = {**{k: h[k] for k in ("семья", "программа", "имя")}, "статус": r["статус"],
               "секунд": r.get("секунд"), "почему": r.get("почему", ""), "проверено": hhmm()}
        if r.get("до"):
            row["до"] = r["до"]
        if h["программа"] != "claude":
            cli.append(row)
        detail = f"ответил за {r.get('секунд')} с" if r["ok"] else r.get("почему", "")
        rows.append((h["имя"], r["статус"], detail))
    for k in configured_keys():
        r = run_key(k, PROBE_TEXT, PROBE_TIMEOUT)
        row = {"ключ": k["ключ"], "имя": k["имя"], "статус": r["статус"],
               "почему": r.get("почему", ""), "проверено": hhmm()}
        if r.get("до"):
            row["до"] = r["до"]
        keys.append(row)
        rows.append((f"{k['имя']} (ключ)", r["статус"],
                     f"ответил за {r.get('секунд')} с" if r["ok"] else r.get("почему", "")))
    print("Перекличка — программы по подписке и бесплатные ключи:")
    table(rows)
    seats = {"проверено": now().strftime("%Y-%m-%d %H:%M"), "помощники": cli, "ключи": keys,
             "веб": old.get("веб", []), "браузер": old.get("браузер", {}),
             "участвовали": old.get("участвовали", {})}
    if args.out:
        save_seats(args.out, seats)
        print(f"Записал в {args.out}. Дальше — браузер (скилл team, «Перекличка браузера»), "
              f"потом: team.py summary --seats {args.out}")
    return 0 if any(usable(s) for s in cli + keys) else 1


def cmd_web_sites(_):
    for name, url, label in WEB_SITES:
        print(f"{name}\t{url}\t{label}")
    return 0


def cmd_web_mark(args):
    seats = load_seats(args.seats) or {"помощники": [], "ключи": [], "веб": []}
    if args.browser:
        seats["браузер"] = {"статус": args.browser, "почему": args.why or "", "проверено": hhmm()}
        save_seats(args.seats, seats)
        print(f"Браузер: {args.browser}")
        return 0
    if not args.site:
        print("нужно --site или --browser", file=sys.stderr)
        return 2
    known = {n: (u, l) for n, u, l in WEB_SITES}
    site = args.site.lower()
    url, label = known.get(site, (args.url or "", args.site))
    web = [w for w in seats.setdefault("веб", []) if w["сайт"] != site]
    prev = next((w for w in seats["веб"] if w["сайт"] == site), {})
    if args.answered:
        note_answer(seats, "веб", site)
        status = prev.get("статус", "жив")
    else:
        status = args.status
        if status not in WEB_STATES:
            print(f"статус: один из {', '.join(WEB_STATES)}", file=sys.stderr)
            return 2
    entry = {"сайт": site, "имя": label, "адрес": url or prev.get("адрес", ""), "статус": status,
             "почему": args.why or prev.get("почему", ""), "проверено": hhmm()}
    web.append(entry)
    seats["веб"] = web
    save_seats(args.seats, seats)
    if not args.answered and prev and prev.get("статус") != status:
        log_progress(args.progress, f"веб {label}: {prev.get('статус')} → {status}"
                     + (f" ({args.why})" if args.why else ""))
    print(f"web-{site}: {status}")
    return 0


def summarize(seats):
    work, reserve, broken, todo = [], [], [], []
    for s in seats.get("помощники", []):
        name = s["имя"]
        if s["статус"] == "жив":
            work.append(name)
        elif s["статус"] == "лимит":
            broken.append(f"{name} — лимит" + (f" до {s['до'][-5:]}" if s.get("до") else ""))
            if s.get("до"):
                reserve.append(f"{name} (вернётся после {s['до'][-5:]})")
        elif s["статус"] == "не вошли":
            broken.append(f"{name} — не вошли")
            todo.append(f"войти в {s['программа']}: запустите её в терминале один раз и войдите")
        else:
            broken.append(f"{name} — {s['статус']}")
    for k in seats.get("ключи", []):
        (reserve if k["статус"] == "жив" else broken).append(
            f"{k['имя']} (ключ)" + ("" if k["статус"] == "жив" else f" — {k['статус']}"))
    br = seats.get("браузер", {})
    if br and br.get("статус") != "жив":
        broken.append(f"браузер Chrome — {br.get('статус')}")
        todo.append("браузер: поставить/включить расширение Claude in Chrome и нажать «Разрешить» сейчас")
    for w in seats.get("веб", []):
        if w["статус"] == "жив":
            reserve.append(f"веб {w['имя']}")
        else:
            broken.append(f"веб {w['имя']} — {w['статус']}")
            if w["статус"] in ("нужен вход", "капча"):
                todo.append(f"{w['имя']}: откройте {w.get('адрес') or w['сайт']} и войдите / пройдите проверку")
    if not work and not reserve:
        todo.insert(0, "нет ни одного живого помощника другой компании — поставьте и войдите хотя бы "
                       "в одну программу (codex, gemini/agy, kimi, grok, qwen) или войдите в 2–3 веб-чата")
    return work, reserve, broken, todo


def cmd_summary(args):
    seats = load_seats(args.seats) or {}
    work, reserve, broken, todo = summarize(seats)
    print("Итог переклички:")
    print("  Ночью работают: " + (", ".join(work) or "—"))
    print("  Запас: " + (", ".join(reserve) or "—"))
    print("  Не работает: " + (", ".join(broken) or "—"))
    if not work and not reserve:
        print("  Честно: живых помощников других компаний нет — ночь пройдёт только со своими "
              "критиками Claude (свежий субагент). Лучше исправить до ухода:")
    if todo:
        print("  Что сделать сейчас, пока вы рядом:")
        for t in todo:
            print(f"    - {t}")
    return 0 if (work or reserve) else 1


def cmd_next(args):
    print(json.dumps(route(load_seats(args.seats)), ensure_ascii=False, indent=2))
    return 0


def cmd_used(args):
    seats = load_seats(args.seats) or {}
    used = seats.get("участвовали", {})
    if not used:
        print("Помощники других компаний этой ночью не отвечали — работали только свои критики Claude.")
        return 1
    for k, n in sorted(used.items(), key=lambda x: -x[1]):
        print(f"  {k} — ответов: {n}")
    return 0


def cmd_ask(args):
    found = installed()
    seats = load_seats(args.seats)
    keys = configured_keys()
    order = [x for x in route(seats, found, keys) if x["путь"] in ("cli", "ключ")]
    if args.who:
        first = [x for x in order if args.who.lower() == x["кто"] or
                 any(h["семья"] == args.who.lower() and h["программа"] == x["кто"] for h in found)]
        order = first + [x for x in order if x not in first]
    if not args.fallback:
        order = order[:1]
    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt
    tried = []
    for x in order:
        if x["путь"] == "cli":
            h = next(h for h in found if h["программа"] == x["кто"])
            r = run(h, prompt, ASK_TIMEOUT, cwd=args.dir)
        else:
            k = next(k for k in keys if k["ключ"] == x["кто"])
            r = run_key(k, prompt, ASK_TIMEOUT)
        if r["ok"]:
            if tried:
                log_progress(args.progress, "; ".join(f"{t['кто']} — {t['почему']}" for t in tried)
                             + f"; заменён: {x['имя']}")
            mark(args.seats, x, r)
            print(json.dumps({"ok": True, "кто": x["имя"], "путь": x["путь"], "программа": x["кто"],
                              "секунд": r.get("секунд"), "не_смогли": tried, "ответ": r["ответ"]},
                             ensure_ascii=False))
            return 0
        tried.append({"кто": x["имя"], "статус": r["статус"], "почему": r["почему"]})
        mark(args.seats, x, r)
    rest = [x for x in route(load_seats(args.seats), found, keys) if x["путь"] in ("веб", "claude")]
    nxt = rest[0]
    if tried:
        log_progress(args.progress, "; ".join(f"{t['кто']} — {t['почему']}" for t in tried)
                     + f"; дальше: {nxt['имя']}")
    print(json.dumps({"ok": False, "не_смогли": tried,
                      "почему": "ни одна программа и ни один ключ не ответили" if tried else
                      "живых программ и ключей других компаний нет",
                      "дальше": nxt, "запас": rest}, ensure_ascii=False))
    return 1


def mark(path, x, result):
    seats = load_seats(path)
    if not seats:
        return
    group, field = ("помощники", "программа") if x["путь"] == "cli" else ("ключи", "ключ")
    for s in seats.get(group, []):
        if s.get(field) == x["кто"]:
            s["статус"], s["почему"], s["проверено"] = result["статус"], result.get("почему", ""), hhmm()
            if result.get("до"):
                s["до"] = result["до"]
            elif result["ok"]:
                s.pop("до", None)
    if result["ok"]:
        note_answer(seats, x["путь"], x["кто"])
    save_seats(path, seats)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall: помощники-ИИ других компаний.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("rollcall", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--out", help="куда записать, кто жив (seats.json в папке задачи)")
    sub.add_parser("web-sites")
    w = sub.add_parser("web-mark")
    w.add_argument("--seats", required=True)
    w.add_argument("--site", help="chatgpt, gemini, kimi, deepseek, meta, grok, qwen, mistral …")
    w.add_argument("--url")
    w.add_argument("--status", default="жив", help=" | ".join(WEB_STATES))
    w.add_argument("--why", default="")
    w.add_argument("--browser", help="состояние самого браузера: жив | нет расширения | нет разрешения")
    w.add_argument("--answered", action="store_true", help="сайт ответил на вопрос ночью (для утра)")
    w.add_argument("--progress", help="PROGRESS.md: записать смену состояния")
    for name in ("summary", "next", "used"):
        p = sub.add_parser(name)
        p.add_argument("--seats", required=True)
    a = sub.add_parser("ask")
    a.add_argument("prompt", help="вопрос или - для чтения со стандартного ввода")
    a.add_argument("--who", help="кого спросить первым: codex, agy, gemini, grok, kimi, qwen, openrouter…")
    a.add_argument("--seats", help="seats.json из переклички: мёртвых пропускаем, новых мёртвых отмечаем")
    a.add_argument("--progress", help="PROGRESS.md: каждая замена — строкой")
    a.add_argument("--dir", help="папка, которую помощник может читать (его рабочая папка)")
    a.add_argument("--no-fallback", dest="fallback", action="store_false",
                   help="не переходить к следующему, если первый не ответил")
    args = ap.parse_args(argv)
    return {"list": cmd_list, "rollcall": cmd_rollcall, "probe": cmd_rollcall,
            "web-sites": cmd_web_sites, "web-mark": cmd_web_mark, "summary": cmd_summary,
            "next": cmd_next, "used": cmd_used, "ask": cmd_ask}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
