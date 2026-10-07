#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall checklist: the person's own words, line for line, as the list of what "done" means - and an item
closes only with an artifact that is really there. A long run (a night, a weekend) loses things and stops early
when "done" is a feeling; here "done" is a list the agent cannot rewrite unseen.

    python3 checklist.py make    --dir <task folder> [--from <file with the person's words>]
    python3 checklist.py test    --dir <f> -- <test command...>     runs the tests and keeps their log as evidence
    python3 checklist.py close   --dir <f> --n 3 --evidence <commit sha | file path | test:<name>>
    python3 checklist.py defer   --dir <f> --n 3 --why "<why>"       deferred is still OPEN
    python3 checklist.py status  --dir <f> [--json]                 "open 2 of 9 (1 deferred)"; exit 1 while open
    python3 checklist.py verify  --dir <f>                          items rewritten or removed since `make`
    python3 checklist.py cold    --dir <f>                          one cold check of the finished night (diffcall)
    python3 checklist.py morning --dir <f>                          MORNING.md starts with "Not done"

THE WORDS. `make` takes the person's words verbatim: the file given with --from, else `goal.md`, else TASK.md's
section with the person's words (its heading says "words" / "\u0441\u043b\u043e\u0432\u0430"), else TASK.md itself - one item per line,
only the list marker taken off, nothing paraphrased. checklist.json keeps each item's words with their sha256,
and a copy of the words goes to ~/.nightcall/checklists/<folder id>.json (outside the task folder). `verify` and
the morning report show any item whose words were rewritten, or that disappeared.

THE EVIDENCE is checked, not believed: a commit must exist in the folder's git; a file must exist in the folder
(not the checklist, the plan, the journal or a log); a test - `test:<name>` - counts only if <name> appears in
the log of a run made by `checklist.py test`, whose sha256 sits in the ledger outside the folder. A string the
agent wrote into some file is not a test that ran.

THE COLD CHECK is one, and not ours: NIGHTCALL_COLD_CMD (a command; the question comes on stdin), else the
installed diffcall's review over the folder. Its answer goes to cold-check.md and into MORNING.md.

Files: <folder>/checklist.json, <folder>/.nightcall/test-runs/*.log, ~/.nightcall/checklists/ (NIGHTCALL_HOME).
Every write is a temporary file and one rename.
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = "checklist.json"
HOME = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
NOT_EVIDENCE = {FILE, "PLAN.md", "PROGRESS.md", "MORNING.md", "TASK.md", "goal.md", "cold-check.md",
                "decisions.md", "night-loop.log", "steer.log"}
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
WORDS_HEAD = re.compile(r"words|\u0441\u043b\u043e\u0432\u0430|\u0441\u043b\u0456\u0432|palabras|palavras", re.I)
NEVER_HEAD = re.compile(r"never|forbidden|\u0437\u0430\u043f\u0440\u0435\u0449|\u0431\u0435\u0437 \u043c\u0435\u043d\u044f|\u0437\u0430\u0431\u043e\u0440\u043e\u043d|\u0431\u0435\u0437 \u043c\u0435\u043d\u0435|nunca|prohib|proib", re.I)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def folder_id(folder):
    return sha(os.path.realpath(folder))[:16]


def write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def snapshot_path(folder):
    return os.path.join(HOME, "checklists", folder_id(folder) + ".json")


def ledger_path(folder):
    return os.path.join(HOME, "checklists", folder_id(folder) + ".tests.json")


def source_text(folder, given):
    """(file name, the lines that are the person's words)."""
    for name in ([given] if given else []) + ["goal.md", "TASK.md"]:
        path = name if os.path.isabs(name) else os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        lines = open(path, encoding="utf-8").read().splitlines()
        if os.path.basename(path) == "TASK.md" and not given:
            # TASK.md written by /nightcall:start: the person's words stand under their own heading
            out, inside = [], False
            for line in lines:
                if line.startswith("#"):
                    inside = bool(WORDS_HEAD.search(line)) and not NEVER_HEAD.search(line)
                    continue
                if inside:
                    out.append(line)
            if any(x.strip() for x in out):
                return os.path.basename(path), out
            out, skip = [], False
            for line in lines:
                if line.startswith("#"):
                    skip = bool(NEVER_HEAD.search(line))
                    continue
                if not skip:
                    out.append(line)
            return os.path.basename(path), out
        return os.path.basename(path), lines
    return "", []


def items_of(lines):
    """One item per line, verbatim: only the list marker comes off; empty lines and comments are not items."""
    out = []
    for line in lines:
        text = BULLET.sub("", line).strip()
        if not text or text.startswith("<!--") or set(text) <= set(".-_*"):
            continue
        out.append(text)
    return out


def load(folder):
    data = read_json(os.path.join(folder, FILE), {})
    return data if isinstance(data, dict) and isinstance(data.get("items"), list) else {"items": []}


def save(folder, data):
    write_json(os.path.join(folder, FILE), data)


def counts(items):
    open_ = [i for i in items if i.get("state") != "done"]
    return len(open_), len(items), len([i for i in items if i.get("state") == "deferred"])


def line_of(items):
    o, total, d = counts(items)
    if not total:
        return "no checklist"
    if not o:
        return f"all {total} items closed with evidence"
    return f"open {o} of {total}" + (f" ({d} deferred)" if d else "")


def git_commit(folder, ev):
    if not re.fullmatch(r"[0-9a-f]{7,40}", ev):
        return False
    return subprocess.run(["git", "-C", folder, "cat-file", "-e", ev + "^{commit}"],
                          capture_output=True).returncode == 0


def real_file(folder, ev):
    path = os.path.realpath(ev if os.path.isabs(ev) else os.path.join(folder, ev))
    root = os.path.realpath(folder)
    if not (path.startswith(root + os.sep) and os.path.isfile(path)):
        return False
    rel = os.path.relpath(path, root)
    return (os.path.basename(path) not in NOT_EVIDENCE and not rel.startswith(".nightcall" + os.sep)
            and not rel.endswith(".log") and not rel.startswith("MORNING"))


def ran_test(folder, name):
    """The name appears in a log of a test run made by `checklist.py test` - and that log is unchanged."""
    for rec in read_json(ledger_path(folder), []):
        try:
            text = open(rec["log"], encoding="utf-8", errors="replace").read()
        except (OSError, KeyError):
            continue
        if sha(text) == rec.get("sha") and name in text:
            return True
    return False


def proof(folder, evidence):
    ev = evidence.strip()
    if ev.startswith("test:"):
        name = ev[5:].strip()
        return "test" if len(name) >= 3 and ran_test(folder, name) else ""
    if git_commit(folder, ev):
        return "commit"
    if real_file(folder, ev):
        return "file"
    return ""


def rewritten(folder, data):
    """[(n, original words, now)] for every item whose words changed or vanished since `make`."""
    snap = read_json(snapshot_path(folder), {})
    now = {i.get("n"): i for i in data.get("items", [])}
    out = []
    for orig in snap.get("items", []):
        cur = now.get(orig["n"])
        if not cur:
            out.append((orig["n"], orig["words"], None))
        elif sha(cur.get("words", "")) != orig["sha"] or cur.get("sha") != orig["sha"]:
            out.append((orig["n"], orig["words"], cur.get("words", "")))
    return out


# --- commands -------------------------------------------------------------------------------------

def cmd_make(a):
    folder = os.path.abspath(a.dir)
    if load(folder)["items"] and not a.force:
        print(f"{FILE} is already there: {line_of(load(folder)['items'])}.")
        return 0
    src, lines = source_text(folder, a.source)
    words = items_of(lines)
    if not words:
        print("No words of the person to make the checklist from: goal.md or TASK.md (or --from <file>).")
        return 2
    items = [{"n": k + 1, "words": w, "sha": sha(w), "state": "open", "evidence": ""} for k, w in enumerate(words)]
    data = {"source": src, "made": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "items": items}
    save(folder, data)
    write_json(snapshot_path(folder), {"folder": folder, "source": src,
                                       "items": [{"n": i["n"], "words": i["words"], "sha": i["sha"]} for i in items]})
    print(f"{FILE}: {len(items)} items, the person's words from {src}, line for line.")
    return 0


def cmd_test(a):
    folder = os.path.abspath(a.dir)
    command = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not command:
        print("Give the test command after --, e.g. checklist.py test --dir . -- npm test")
        return 2
    p = subprocess.run(command, cwd=folder, capture_output=True, text=True)
    text = f"$ {' '.join(shlex.quote(c) for c in command)}\nexit {p.returncode}\n{p.stdout}\n{p.stderr}"
    runs = os.path.join(folder, ".nightcall", "test-runs")
    os.makedirs(runs, exist_ok=True)
    log = os.path.join(runs, datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + str(os.getpid()) + ".log")
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(text)
    ledger = read_json(ledger_path(folder), [])
    ledger.append({"log": log, "sha": sha(text), "exit": p.returncode, "at": datetime.datetime.now().isoformat()})
    write_json(ledger_path(folder), ledger)
    sys.stdout.write(p.stdout[-4000:])
    print(f"\ntest run kept as evidence: {os.path.relpath(log, folder)} (exit {p.returncode})")
    return p.returncode


def find(items, n):
    return next((i for i in items if i.get("n") == n), None)


def cmd_close(a):
    folder = os.path.abspath(a.dir)
    data = load(folder)
    item = find(data["items"], a.n)
    if not item:
        print(f"No item {a.n} in {FILE}.")
        return 2
    kind = proof(folder, a.evidence)
    if not kind:
        print(f"Item {a.n} stays open: '{a.evidence}' is not a commit of this folder, a file in it, or a test that "
              f"ran through `checklist.py test`.")
        return 1
    item.update(state="done", evidence={"kind": kind, "ref": a.evidence.strip()})
    save(folder, data)
    print(f"Item {a.n} closed ({kind}). {line_of(data['items'])}.")
    return 0


def cmd_defer(a):
    folder = os.path.abspath(a.dir)
    data = load(folder)
    item = find(data["items"], a.n)
    if not item:
        print(f"No item {a.n} in {FILE}.")
        return 2
    item.update(state="deferred", evidence={"kind": "deferred", "ref": a.why})
    save(folder, data)
    print(f"Item {a.n} deferred - it stays open. {line_of(data['items'])}.")
    return 0


def cmd_status(a):
    folder = os.path.abspath(a.dir)
    items = load(folder)["items"]
    o, total, d = counts(items)
    changed = rewritten(folder, load(folder))
    if a.json:
        print(json.dumps({"open": o, "total": total, "deferred": d, "rewritten": len(changed), "line": line_of(items)}))
    else:
        print(line_of(items) + (f"; {len(changed)} rewritten" if changed else ""))
    return 1 if o else 0


def cmd_verify(a):
    folder = os.path.abspath(a.dir)
    changed = rewritten(folder, load(folder))
    for n, orig, now in changed:
        print(f"item {n}: the person said \"{orig}\"" + (f", the list now says \"{now}\"" if now is not None else ", it is gone"))
    if not changed:
        print("every item still says what the person said")
    return 1 if changed else 0


def diffcall_cli():
    roots = [os.environ["CLAUDE_CONFIG_DIR"]] if os.environ.get("CLAUDE_CONFIG_DIR") else []
    roots.append(os.path.expanduser("~/.claude"))
    found = [p for r in roots for p in glob.glob(os.path.join(r, "plugins", "cache", "*", "diffcall", "*", "cli.mjs"))]
    return max(found, key=os.path.getmtime) if found else ""


COLD_QUESTION = ("Cold check of an unattended run. Compare checklist.json (the person's own words, line for line) and "
                 "TASK.md with the work in this folder and its git log. Answer as a list, each point with the item "
                 "number or the file: 1) what was LOST - asked for but missing; 2) what was HALF-DONE - closed or "
                 "claimed in PROGRESS.md but not really finished.")


def cmd_cold(a):
    """One cold check, by a reviewer that is not this night's agent: NIGHTCALL_COLD_CMD, else diffcall."""
    folder = os.path.abspath(a.dir)
    own = os.environ.get("NIGHTCALL_COLD_CMD", "")
    cli = "" if own else diffcall_cli()
    who, answer = "", ""
    try:
        if own:
            p = subprocess.run(shlex.split(own), input=COLD_QUESTION, capture_output=True, text=True, timeout=3600,
                               cwd=folder)
            who, answer = own.split()[0], p.stdout.strip()
        elif cli:
            p = subprocess.run(["node", cli, "review", "--dir", folder, "--wait-all", COLD_QUESTION],
                               capture_output=True, text=True, timeout=3600, cwd=folder)
            who, answer = "diffcall", p.stdout.strip()
        else:
            who = "no cold reviewer on this computer (install diffcall, or set NIGHTCALL_COLD_CMD)"
    except (OSError, subprocess.SubprocessError) as exc:
        who = f"no answer ({exc.__class__.__name__})"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(os.path.join(folder, "cold-check.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Cold check ({stamp}, {who})\n\n{answer}\n")
    print(f"cold-check.md written ({who}).")
    return 0


WORDS = {
    "en": {"not_done": "Not done", "confirmed": "confirmed by an artifact", "words_only": "words only",
           "deferred": "deferred", "rewritten": "rewritten at night - the person said", "gone": "removed at night - the person said",
           "all_closed": "every item of the checklist is closed with an artifact", "cold": "The cold check (another company's AI): what was lost, what was half-done",
           "done_items": "Checklist items closed"},
    "ru": {"not_done": "\u041d\u0435 \u0441\u0434\u0435\u043b\u0430\u043d\u043e", "confirmed": "\u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e \u0430\u0440\u0442\u0435\u0444\u0430\u043a\u0442\u043e\u043c", "words_only": "\u0442\u043e\u043b\u044c\u043a\u043e \u0441\u043b\u043e\u0432\u0430",
           "deferred": "\u043e\u0442\u043b\u043e\u0436\u0435\u043d\u043e", "rewritten": "\u043f\u0435\u0440\u0435\u043f\u0438\u0441\u0430\u043d\u043e \u043d\u043e\u0447\u044c\u044e \u2014 \u0447\u0435\u043b\u043e\u0432\u0435\u043a \u0441\u043a\u0430\u0437\u0430\u043b", "gone": "\u0443\u0434\u0430\u043b\u0435\u043d\u043e \u043d\u043e\u0447\u044c\u044e \u2014 \u0447\u0435\u043b\u043e\u0432\u0435\u043a \u0441\u043a\u0430\u0437\u0430\u043b",
           "all_closed": "\u0432\u0441\u0435 \u043f\u0443\u043d\u043a\u0442\u044b \u0447\u0435\u043a-\u043b\u0438\u0441\u0442\u0430 \u0437\u0430\u043a\u0440\u044b\u0442\u044b \u0430\u0440\u0442\u0435\u0444\u0430\u043a\u0442\u0430\u043c\u0438", "cold": "\u0425\u043e\u043b\u043e\u0434\u043d\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 (\u0418\u0418 \u0434\u0440\u0443\u0433\u043e\u0439 \u043a\u043e\u043c\u043f\u0430\u043d\u0438\u0438): \u0447\u0442\u043e \u043f\u043e\u0442\u0435\u0440\u044f\u043d\u043e, \u0447\u0442\u043e \u043d\u0435\u0434\u043e\u0434\u0435\u043b\u0430\u043d\u043e",
           "done_items": "\u0417\u0430\u043a\u0440\u044b\u0442\u044b\u0435 \u043f\u0443\u043d\u043a\u0442\u044b \u0447\u0435\u043a-\u043b\u0438\u0441\u0442\u0430"},
    "uk": {"not_done": "\u041d\u0435 \u0437\u0440\u043e\u0431\u043b\u0435\u043d\u043e", "confirmed": "\u043f\u0456\u0434\u0442\u0432\u0435\u0440\u0434\u0436\u0435\u043d\u043e \u0430\u0440\u0442\u0435\u0444\u0430\u043a\u0442\u043e\u043c", "words_only": "\u043b\u0438\u0448\u0435 \u0441\u043b\u043e\u0432\u0430",
           "deferred": "\u0432\u0456\u0434\u043a\u043b\u0430\u0434\u0435\u043d\u043e", "rewritten": "\u043f\u0435\u0440\u0435\u043f\u0438\u0441\u0430\u043d\u043e \u0432\u043d\u043e\u0447\u0456 \u2014 \u043b\u044e\u0434\u0438\u043d\u0430 \u0441\u043a\u0430\u0437\u0430\u043b\u0430", "gone": "\u0432\u0438\u0434\u0430\u043b\u0435\u043d\u043e \u0432\u043d\u043e\u0447\u0456 \u2014 \u043b\u044e\u0434\u0438\u043d\u0430 \u0441\u043a\u0430\u0437\u0430\u043b\u0430",
           "all_closed": "\u0443\u0441\u0456 \u043f\u0443\u043d\u043a\u0442\u0438 \u0447\u0435\u043a-\u043b\u0438\u0441\u0442\u0430 \u0437\u0430\u043a\u0440\u0438\u0442\u0456 \u0430\u0440\u0442\u0435\u0444\u0430\u043a\u0442\u0430\u043c\u0438", "cold": "\u0425\u043e\u043b\u043e\u0434\u043d\u0430 \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u043a\u0430 (\u0428\u0406 \u0456\u043d\u0448\u043e\u0457 \u043a\u043e\u043c\u043f\u0430\u043d\u0456\u0457): \u0449\u043e \u0432\u0442\u0440\u0430\u0447\u0435\u043d\u043e, \u0449\u043e \u043d\u0435\u0434\u043e\u0440\u043e\u0431\u043b\u0435\u043d\u043e",
           "done_items": "\u0417\u0430\u043a\u0440\u0438\u0442\u0456 \u043f\u0443\u043d\u043a\u0442\u0438 \u0447\u0435\u043a-\u043b\u0438\u0441\u0442\u0430"},
    "es": {"not_done": "No hecho", "confirmed": "confirmado por un artefacto", "words_only": "solo palabras",
           "deferred": "aplazado", "rewritten": "reescrito de noche; la persona dijo", "gone": "borrado de noche; la persona dijo",
           "all_closed": "todos los puntos de la lista cerrados con artefactos", "cold": "La revisi\u00f3n en fr\u00edo (IA de otra empresa): qu\u00e9 se perdi\u00f3, qu\u00e9 qued\u00f3 a medias",
           "done_items": "Puntos de la lista cerrados"},
    "pt": {"not_done": "N\u00e3o feito", "confirmed": "confirmado por um artefato", "words_only": "s\u00f3 palavras",
           "deferred": "adiado", "rewritten": "reescrito \u00e0 noite; a pessoa disse", "gone": "removido \u00e0 noite; a pessoa disse",
           "all_closed": "todos os itens da lista fechados com artefatos", "cold": "A verifica\u00e7\u00e3o a frio (IA de outra empresa): o que se perdeu, o que ficou pela metade",
           "done_items": "Itens da lista fechados"},
}


def morning_words():
    code = os.environ.get("NIGHTCALL_LANG", "")
    if not code:
        try:
            pc = os.environ.get("POCKETCALL_HOME") or os.path.expanduser("~/.pocketcall")
            code = json.load(open(os.path.join(pc, "remote.json"), encoding="utf-8")).get("lang", "")
        except Exception:
            code = ""
    code = (code or os.environ.get("LC_ALL") or os.environ.get("LANG") or "en")[:2].lower()
    return WORDS.get(code, WORDS["en"])


def not_done_block(folder):
    w = morning_words()
    data = load(folder)
    lines = [f"## {w['not_done']}", ""]
    for n, orig, now in rewritten(folder, data):
        lines.append(f"- [{n}] {w['gone'] if now is None else w['rewritten']}: \"{orig}\"")
    done = []
    for i in data["items"]:
        ev = i.get("evidence") or {}
        if i.get("state") == "done":
            ok = isinstance(ev, dict) and proof(folder, ev.get("ref", "")) == ev.get("kind")
            if ok:
                done.append(f"- [{i['n']}] {i['words']} \u2014 {w['confirmed']} ({ev.get('kind')}: {ev.get('ref')})")
            else:                                  # "done" whose artifact is not there (any more): words only, NOT done
                lines.append(f"- [{i['n']}] {i['words']} \u2014 {w['words_only']}")
        elif i.get("state") == "deferred":
            lines.append(f"- [{i['n']}] {i['words']} \u2014 {w['deferred']}: {ev.get('ref', '') if isinstance(ev, dict) else ''}")
        else:
            lines.append(f"- [{i['n']}] {i['words']}")
    if len(lines) == 2:
        lines.append(f"- {w['all_closed']}")
    try:
        cold = open(os.path.join(folder, "cold-check.md"), encoding="utf-8").read().split("\n", 1)[1].strip()
    except (OSError, IndexError):
        cold = ""
    if cold:
        lines += ["", f"**{w['cold']}**", "", cold]
    if done:
        lines += ["", f"**{w['done_items']}**", ""] + done
    return "\n".join(lines) + "\n", w["not_done"]


def cmd_morning(a):
    """MORNING.md starts with "Not done": open, deferred, words-only and rewritten items, and the cold check."""
    folder = os.path.abspath(a.dir)
    p = os.path.join(folder, "MORNING.md")
    text = open(p, encoding="utf-8").read() if os.path.exists(p) else "# Morning\n"
    block, head = not_done_block(folder)
    heads = "|".join(re.escape(x["not_done"]) for x in WORDS.values())
    body = re.sub(rf"(?ms)^## (?:{heads})\b.*?(?=^## |\Z)", "", text)     # one "Not done", ours, at the top
    lines = body.split("\n")
    title = lines[0] if lines and lines[0].startswith("# ") else "# Morning"
    rest = "\n".join(lines[1:] if lines and lines[0].startswith("# ") else lines).strip()
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(f"{title}\n\n{block}\n{rest}\n")
    os.replace(tmp, p)
    print(f"MORNING.md starts with {head}.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall checklist: the person's words, closed with artifacts.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make")
    p.add_argument("--dir", required=True)
    p.add_argument("--from", dest="source", default="")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("test")
    p.add_argument("--dir", required=True)
    p.add_argument("command", nargs=argparse.REMAINDER)
    p = sub.add_parser("close")
    p.add_argument("--dir", required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--evidence", required=True)
    p = sub.add_parser("defer")
    p.add_argument("--dir", required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--why", required=True)
    p = sub.add_parser("status")
    p.add_argument("--dir", required=True)
    p.add_argument("--json", action="store_true")
    for name in ("verify", "cold", "morning"):
        p = sub.add_parser(name)
        p.add_argument("--dir", required=True)
    a = ap.parse_args(argv)
    return {"make": cmd_make, "test": cmd_test, "close": cmd_close, "defer": cmd_defer, "status": cmd_status,
            "verify": cmd_verify, "cold": cmd_cold, "morning": cmd_morning}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
