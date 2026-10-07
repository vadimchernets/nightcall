#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nightcall family relay: when one person's subscription runs out, the next step goes on in the
account of another member of the family who said beforehand "while I'm away, my account carries
the family's work on".

    python3 family.py add     --name Dad --email dad@x.com [--config-dir default] [--engine claude|codex]
    python3 family.py consent --name Son --until "2026-10-12 09:00" --by Son [--folder <task folder>]
    python3 family.py revoke  --name Son
    python3 family.py check                     # who is really signed in where
    python3 family.py status
    python3 family.py pick    --folder <f>      # the next member: id<TAB>engine<TAB>config dir (- = usual)<TAB>name
    python3 family.py limit   --id <id>         # the round's output on stdin: when does this account come back
    python3 family.py relay   --folder <f> --from <id> --to <id>
    python3 family.py soonest                   # seconds until the first member's account is back
    python3 family.py settings --id <id>        # Claude Code settings for that member's round
    python3 family.py engines                   # which programs the family uses (claude, codex)

THE RULE (from PolyHelper V1, family-handoff.mjs): the context moves, the access never does.
  MOVES        the task: TASK.md, PLAN.md, PROGRESS.md and the files in the task folder. A fresh
               `claude -p` reads them at every round anyway, so the next account continues exactly
               where the previous one stopped.
  NEVER MOVES  logins, tokens, keys. Every member has their OWN Claude Code config folder
               (CLAUDE_CONFIG_DIR, or CODEX_HOME for Codex) and signs in there once, themselves,
               with the vendor's own login. family.json holds names, e-mail addresses, folder paths
               and consents - never a token. Nothing here reads, copies or replays a login.

WHAT MAKES IT FAMILY WORK, BY CONSTRUCTION:
  1. One person = one place. Two members with the same e-mail are refused: it would be the same
     account and the same quota anyway.
  2. The account that is signed in must be the one the member named. `pick` asks the vendor CLI
     (`claude auth status` in that member's folder) before every switch and skips a folder where
     somebody else is signed in, or nobody is.
  3. Standing consent is given by the member, for themselves, until a time they choose: only once
     their own folder is signed in as them, after the task is on screen, by typing their name in
     their own terminal (/dev/tty). The record is signed with a key kept in
     ~/.nightcall/family/<id>/consent.key; an unsigned or edited record is no consent. Revoke
     works at any moment, and a consent that has run out ends by itself.
  5. A family round runs without the API keys and tokens of the environment it was started from
     (night-loop.sh `env -u ...`), and with Claude Code settings that keep it out of the family's
     own places (`settings`). Folders 0700, files 0600.
  4. Every change of hands is written into the task's PROGRESS.md ("Relay") and
     ~/.nightcall/family-log.jsonl: who stopped, why, who continued, on whose consent.

Files: ~/.nightcall/family.json, ~/.nightcall/family-log.jsonl, ~/.nightcall/family/<id>/ (the
members' own config folders). NIGHTCALL_HOME moves all of them.
"""

import argparse
import datetime
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import team as T  # noqa: E402  (reset-time parsing, PATH for helper programs)

HOME = os.environ.get("NIGHTCALL_HOME", os.path.expanduser("~/.nightcall"))
FAMILY = os.path.join(HOME, "family.json")
LOG = os.path.join(HOME, "family-log.jsonl")
ENGINES = ("claude", "codex")
DEFAULT = "default"          # config dir "default": the person's usual ~/.claude (or ~/.codex)
# The family wording of PolyHelper V1 (byos-installer/src/family-handoff.mjs, DISCLOSURE), word for
# word with the product name swapped. These are the family texts; nothing is added to them.
DISCLOSURE = {
    "toSender": "Another person will read this task. Everything below - the conversation, the files, "
                "what is done and what is left - becomes visible to the profile you hand it to. Nothing about "
                "your accounts moves: they will work on their own subscription, with their own keys, signed in "
                "as themselves. Hand over only work you are willing for them to read.",
    "toRecipient": "You can read all of this before you decide, and you may refuse. If you take it, you "
                   "work on it with YOUR OWN account and your own quota - nothing of the sender's sign-in comes "
                   "with the task, and nightcall could not carry it even if you asked.",
    "twoQuotas": "Two people - two quotas. That is legal. One person must not farm accounts.",
    "signInYourself": "Sign in as yourself in the vendor's own CLI before you continue. nightcall never "
                      "signs anyone in and never replays anyone's login.",
}
UNKNOWN_BACK_MIN = int(os.environ.get("NIGHTCALL_FAMILY_UNKNOWN_BACK", "60"))
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def now():
    return datetime.datetime.now().replace(microsecond=0)


def parse_time(value):
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def load():
    try:
        with open(FAMILY, encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("members", [])
        return data
    except Exception:
        return {"members": []}


def private_dir(path):
    """Family places are the person's own: 0700 folders, 0600 files."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def private_file(path):
    if os.path.exists(path):
        os.chmod(path, 0o600)


def save(data):
    private_dir(HOME)
    data["note"] = ("nightcall family relay: names, e-mails, config folders and consents. No logins, "
                    "tokens or keys are kept here - each member signs in in their own folder.")
    tmp = FAMILY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    private_file(tmp)
    os.replace(tmp, FAMILY)


def journal(event, **fields):
    private_dir(HOME)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": fmt(now()), "event": event, **fields}, ensure_ascii=False) + "\n")
    private_file(LOG)


# ---------- the member's own consent: typed in the terminal, signed with the member's key ----------

def seal_dir(member):
    return os.path.join(HOME, "family", member["id"])


def seal_key(member, create=False):
    path = os.path.join(seal_dir(member), "consent.key")
    if create and not os.path.exists(path):
        private_dir(os.path.dirname(os.path.dirname(path)))
        private_dir(os.path.dirname(path))
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(os.urandom(32).hex())
    try:
        return open(path, encoding="utf-8").read().strip().encode()
    except OSError:
        return b""


def consent_body(member, c):
    return json.dumps({"id": member["id"], "email": member["email"], "until": c.get("until"),
                       "folder": c.get("folder"), "at": c.get("at"), "typed": c.get("typed")},
                      sort_keys=True, ensure_ascii=False).encode()


def sign(member, c):
    key = seal_key(member, create=True)
    return hmac.new(key, consent_body(member, c), hashlib.sha256).hexdigest()


def signed(member, c):
    key = seal_key(member)
    return bool(key and c.get("sig")) and hmac.compare_digest(
        c["sig"], hmac.new(key, consent_body(member, c), hashlib.sha256).hexdigest())


def ask_tty(question):
    """The member's own answer, from the terminal they sit at. None when there is no terminal
    (a Claude Code tool, a script): consent is then not given."""
    try:
        fd = os.open("/dev/tty", os.O_RDWR | getattr(os, "O_NOCTTY", 0))
    except OSError:
        return None
    try:
        os.write(fd, question.encode("utf-8"))
        line = b""
        while not line.endswith(b"\n"):
            chunk = os.read(fd, 1)
            if not chunk:
                break
            line += chunk
        return line.decode("utf-8", "replace").strip()
    except OSError:
        return None
    finally:
        os.close(fd)


def show_task(folder):
    """V1: "You can read all of this before you decide" - so the task is on screen first."""
    out = []
    if folder:
        for name in ("TASK.md", "PLAN.md", "PROGRESS.md"):
            path = os.path.join(folder, name)
            if os.path.exists(path):
                lines = open(path, encoding="utf-8").read().splitlines()
                out.append(f"----- {name} -----")
                out += lines[:80] + ([f"... ({len(lines) - 80} more lines in {path})"] if len(lines) > 80 else [])
        if not out:
            out.append(f"{folder}: no TASK.md or PLAN.md there yet.")
    else:
        known = set()
        try:
            known.add(json.load(open(os.path.join(HOME, "active.json"), encoding="utf-8"))["folder"])
        except Exception:
            pass
        try:
            for line in open(LOG, encoding="utf-8"):
                e = json.loads(line)
                if e.get("folder"):
                    known.add(e["folder"])
        except Exception:
            pass
        out.append("Every task folder of the family's night and weekend runs. Known so far:")
        out += [f"  {f}" for f in sorted(known)] or ["  (none yet)"]
    return "\n".join(out)


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "m%d" % (abs(hash(name)) % 100000)


def find(data, name_or_id):
    key = (name_or_id or "").strip().lower()
    for m in data["members"]:
        if m["id"] == key or m["name"].lower() == key:
            return m
    return None


def config_env(member):
    """The environment that points the vendor CLI at this member's own folder - and nothing else."""
    env = T.child_env()
    var = "CLAUDE_CONFIG_DIR" if member.get("engine", "claude") == "claude" else "CODEX_HOME"
    if member.get("config_dir") and member["config_dir"] != DEFAULT:
        env[var] = member["config_dir"]
    return env                # "default": the sign-in this computer already uses, untouched


def read_login(member):
    """Ask the vendor CLI who is signed in in this member's folder. {loggedIn, email}."""
    engine = member.get("engine", "claude")
    cmd = ["claude", "auth", "status"] if engine == "claude" else ["codex", "login", "status"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=config_env(member))
    except Exception as exc:
        return {"loggedIn": False, "email": "", "why": f"{cmd[0]} did not start: {exc}"}
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if engine == "claude":
        try:
            info = json.loads(r.stdout)
            return {"loggedIn": bool(info.get("loggedIn")), "email": (info.get("email") or "").lower(), "why": ""}
        except Exception:
            pass
    found = re.search(r"[^@\s\"']+@[^@\s\"']+\.[A-Za-z]{2,}", out)
    logged = r.returncode == 0 and not re.search(r"not logged in|not signed in|loggedIn\"?\s*:\s*false", out, re.I)
    return {"loggedIn": logged, "email": found.group(0).lower() if found else "", "why": ""}


def login_verdict(member, login=None):
    login = login or read_login(member)
    if not login["loggedIn"]:
        return "signed-out", f"nobody is signed in in {member['name']}'s folder"
    if not login["email"]:
        # Codex prints no address for some sign-in methods: a signed-in folder of its own is enough
        return "match", "signed in (the program names no address)"
    if login["email"] == member["email"].lower():
        return "match", f"signed in as {login['email']} - {member['name']}'s own account"
    return "mismatch", f"{member['name']}'s folder is signed in as {login['email']}, not {member['email']}"


def consent_ok(member, at, folder=None):
    c = member.get("consent") or {}
    if member.get("owner"):
        return True, "the person who started the run"
    until = parse_time(c.get("until"))
    if not until:
        return False, f"{member['name']} has not given consent"
    if not signed(member, c):
        return False, f"{member['name']}'s consent carries no signature of theirs"
    if until <= at:
        return False, f"{member['name']}'s consent ended at {fmt(until)}"
    if c.get("folder") and folder and os.path.realpath(c["folder"]) != os.path.realpath(folder):
        return False, f"{member['name']}'s consent covers {c['folder']} only"
    return True, f"consent until {fmt(until)}"


def limited(member, at):
    back = parse_time(member.get("limit_until"))
    return back if back and back > at else None


# ---------- commands ----------

def cmd_add(a):
    data = load()
    name, email = a.name.strip(), a.email.strip().lower()
    if not EMAIL.match(email):
        print(f"\"{a.email}\" is not an e-mail address. Give the address of {name}'s own account.")
        return 2
    if a.engine not in ENGINES:
        print(f"Engine is one of: {', '.join(ENGINES)}.")
        return 2
    if find(data, name):
        print(f"{name} is already in the family. `revoke`, then `add` again to change it.")
        return 2
    for m in data["members"]:
        if m["email"] == email and m.get("engine", "claude") == a.engine:
            print(f"{email} is already {m['name']}'s account. {DISCLOSURE['twoQuotas']}")
            return 2
    mid = slug(name)
    while any(m["id"] == mid for m in data["members"]):
        mid += "-2"
    if a.config_dir == DEFAULT:
        config = DEFAULT
    else:
        config = os.path.abspath(os.path.expanduser(a.config_dir or os.path.join(HOME, "family", mid, a.engine)))
        private_dir(HOME)
        if config.startswith(os.path.join(HOME, "family") + os.sep):
            private_dir(os.path.join(HOME, "family"))
            private_dir(os.path.dirname(config))
        private_dir(config)
    owner = not data["members"]          # the first member is the person who runs the nights
    member = {"id": mid, "name": name, "email": email, "engine": a.engine, "config_dir": config,
              "owner": owner, "consent": None, "limit_until": None, "added": fmt(now())}
    data["members"].append(member)
    save(data)
    journal("add", id=mid, name=name, engine=a.engine)
    var = "CLAUDE_CONFIG_DIR" if a.engine == "claude" else "CODEX_HOME"
    login = "claude auth login" if a.engine == "claude" else "codex login"
    print(f"{name} is in the family ({a.engine}, {'the usual folder' if config == DEFAULT else config}).")
    if config == DEFAULT:
        print(f"  {name} works in the usual sign-in of this computer - `check` shows who is signed in there.")
    else:
        print(f"  {DISCLOSURE['signInYourself']}")
        print(f"      {var}=\"{config}\" {login}      ({email})")
    if not owner:
        print(f"  {DISCLOSURE['toSender']}")
        print(f"  Then {name} says for how long their account may carry the family's work on:")
        print(f"      python3 \"{os.path.abspath(__file__)}\" consent --name \"{name}\" --by \"{name}\" --until \"YYYY-MM-DD HH:MM\"")
    return 0


def cmd_consent(a):
    data = load()
    m = find(data, a.name)
    if not m:
        print(f"No {a.name} in the family. `add` first.")
        return 2
    if a.by.strip().lower() not in (m["name"].lower(), m["id"]):
        print(f"Consent for {m['name']}'s account is given by {m['name']}, in their own words: --by \"{m['name']}\".")
        return 2
    until = parse_time(a.until)
    if not until or until <= now():
        print("--until is a time in the future, for example \"2026-10-12 09:00\".")
        return 2
    verdict, why = login_verdict(m)
    if verdict != "match":
        var = "CLAUDE_CONFIG_DIR" if m["engine"] == "claude" else "CODEX_HOME"
        login = "claude auth login" if m["engine"] == "claude" else "codex login"
        print(f"{why}. {DISCLOSURE['signInYourself']}")
        print(f"      {var}=\"{m['config_dir']}\" {login}")
        return 2
    folder = os.path.abspath(os.path.expanduser(a.folder)) if a.folder else None
    print(show_task(folder))
    print(DISCLOSURE["toRecipient"])
    typed = ask_tty(f"{m['name']}, type your name to let your account carry this on until {fmt(until)}: ")
    if typed is None:
        print(f"{m['name']} gives this consent in their own terminal - run the same command there.")
        return 7
    if typed.strip().lower() != m["name"].lower():
        print("Consent not given: the name typed is not " + m["name"] + ".")
        return 2
    c = {"until": fmt(until), "by": m["name"], "at": fmt(now()), "folder": folder, "typed": typed.strip(),
         "words": a.words or f"While I am away, my account carries the family's work on until {fmt(until)}."}
    c["sig"] = sign(m, c)
    m["consent"] = c
    save(data)
    journal("consent", id=m["id"], until=fmt(until), folder=folder)
    where = f"the task in {folder}" if folder else "the family's night and weekend runs"
    print(f"{m['name']}'s account carries {where} on until {fmt(until)}, when another member's limit runs out.")
    print(f"  `revoke --name \"{m['name']}\"` ends it at once.")
    return 0


def cmd_revoke(a):
    data = load()
    m = find(data, a.name)
    if not m:
        print(f"No {a.name} in the family.")
        return 2
    if a.remove:
        data["members"].remove(m)
        print(f"{m['name']} is out of the family list. Their sign-in folder stays where it is: {m['config_dir']}.")
    else:
        m["consent"] = None
        print(f"{m['name']}'s consent is withdrawn: their account takes no more family rounds.")
    save(data)
    journal("revoke", id=m["id"], removed=bool(a.remove))
    return 0


def rows(data, at, with_login=True):
    out = []
    for m in data["members"]:
        verdict, why = login_verdict(m) if with_login else ("", "")
        ok, cwhy = consent_ok(m, at)
        back = limited(m, at)
        out.append((m, verdict, why, ok, cwhy, back))
    return out


def cmd_check(a):
    data = load()
    if not data["members"]:
        print("No family yet: `add` the person who runs the nights first, then each member.")
        return 1
    at = now()
    ready = 0
    for m, verdict, why, ok, cwhy, back in rows(data, at):
        mark = {"match": "OK  ", "mismatch": "WRONG", "signed-out": "SIGN IN"}[verdict]
        state = f"limit until {fmt(back)}" if back else ("ready" if ok and verdict == "match" else "")
        print(f"{mark:7} {m['name']:<12} {m['engine']:<6} {why}; {cwhy}{'; ' + state if state else ''}")
        if verdict != "match":
            var = "CLAUDE_CONFIG_DIR" if m["engine"] == "claude" else "CODEX_HOME"
            login = "claude auth login" if m["engine"] == "claude" else "codex login"
            pre = "" if m["config_dir"] == DEFAULT else f"{var}=\"{m['config_dir']}\" "
            print(f"        {m['name']} signs in as themselves: {pre}{login}")
        ready += verdict == "match" and ok and not back
    print(f"Ready to carry the work on: {ready} of {len(data['members'])}.")
    return 0


def cmd_status(a):
    data = load()
    at = now()
    if not data["members"]:
        print("No family relay set up: the night runs on this computer's usual sign-in.")
        return 1
    for m, _, _, ok, cwhy, back in rows(data, at, with_login=False):
        print(f"{m['name']:<12} {m['engine']:<6} {'owner' if m.get('owner') else cwhy}"
              f"{'; limit until ' + fmt(back) if back else ''}")
    return 0


def cmd_pick(a):
    """The next member who can take a round. Order: the family list, starting after --after."""
    data = load()
    at = now()
    folder = os.path.abspath(os.path.expanduser(a.folder)) if a.folder else None
    members = data["members"]
    if a.after:
        idx = next((i for i, m in enumerate(members) if m["id"] == a.after), -1)
        if idx >= 0 and not limited(members[idx], at):
            members = [members[idx]] + members[idx + 1:] + members[:idx]   # stay with whoever has room
        elif idx >= 0:
            members = members[idx + 1:] + members[:idx + 1]
    skipped = []
    for m in members:
        if limited(m, at):
            skipped.append(f"{m['name']}: limit until {m['limit_until']}")
            continue
        ok, why = consent_ok(m, at, folder)
        if not ok:
            skipped.append(why)
            continue
        verdict, lwhy = login_verdict(m)
        if verdict != "match":
            skipped.append(lwhy)
            continue
        config = "-" if m["config_dir"] == DEFAULT else m["config_dir"]   # "-": the usual sign-in
        for s in skipped:
            print(s, file=sys.stderr)
        print(f"{m['id']}\t{m.get('engine', 'claude')}\t{config}\t{m['name']}")
        return 0
    for s in skipped:
        print(s, file=sys.stderr)
    return 1


def cmd_limit(a):
    data = load()
    m = find(data, a.id)
    if not m:
        print(f"No {a.id} in the family.")
        return 2
    text = sys.stdin.read() if not sys.stdin.isatty() else ""
    back = T.reset_time(text, now()) or (now() + datetime.timedelta(minutes=UNKNOWN_BACK_MIN))
    m["limit_until"] = fmt(back)
    save(data)
    journal("limit", id=m["id"], until=fmt(back))
    print(f"{m['name']}'s subscription is resting until {fmt(back)}.")
    return 0


def cmd_relay(a):
    data = load()
    frm, to = find(data, a.__dict__["from"]), find(data, a.to)
    if not to:
        print(f"No {a.to} in the family.")
        return 2
    at = now()
    why = f"{frm['name']}'s limit (back at {frm.get('limit_until') or '?'})" if frm and limited(frm, at) else "next round"
    _, cwhy = consent_ok(to, at)
    line = (f"- {at:%d.%m %H:%M} {why} -> {to['name']} carries the work on with their own account "
            f"({to['engine']}; {cwhy}). Logins did not move; the task did: TASK.md, PLAN.md, PROGRESS.md.")
    folder = os.path.abspath(os.path.expanduser(a.folder))
    path = os.path.join(folder, "PROGRESS.md")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else "# Night progress\n"
    head = "## Relay"
    if head not in text:
        text = text.rstrip() + f"\n\n{head}\n<!-- each change of hands in the family: who stopped, who carried on, on whose consent -->\n"
    text = text.rstrip() + "\n" + line + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    journal("relay", folder=folder, frm=frm["id"] if frm else None, to=to["id"])
    print(line)
    return 0


def child_settings(data, member):
    """Claude Code settings for a family round: the round reads and edits the task, never the family's
    own places - the other members' sign-in folders, the consent keys, the family list."""
    deny = []
    places = [os.path.join(HOME, "family"), FAMILY, LOG]
    for m in data["members"]:
        if m["id"] != member["id"] and m.get("config_dir") not in (None, "", DEFAULT):
            places.append(m["config_dir"])
    if member.get("config_dir") not in (None, "", DEFAULT):
        places.append(os.path.expanduser("~/.claude"))       # the usual sign-in is someone else's here
    for p in places:
        rule = "/" + os.path.realpath(p) if os.path.isabs(p) else p
        tail = "/**" if not p.endswith((".json", ".jsonl")) else ""
        deny += [f"Read({rule}{tail})", f"Edit({rule}{tail})"]
    return {"permissions": {"deny": deny}}


def cmd_engines(a):
    print(" ".join(sorted({m.get("engine", "claude") for m in load()["members"]})))
    return 0


def cmd_settings(a):
    data = load()
    m = find(data, a.id)
    if not m:
        return 2
    print(json.dumps(child_settings(data, m)))
    return 0


def cmd_soonest(a):
    data = load()
    at = now()
    backs = [limited(m, at) for m in data["members"] if consent_ok(m, at)[0]]
    backs = [b for b in backs if b]
    print(int((min(backs) - at).total_seconds()) + 30 if backs else 0)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightcall family relay.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("--name", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--engine", default="claude")
    p.add_argument("--config-dir", default="", help='"default" = this computer\'s usual sign-in')
    p = sub.add_parser("consent")
    p.add_argument("--name", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--until", required=True)
    p.add_argument("--folder", default="")
    p.add_argument("--words", default="")
    p = sub.add_parser("revoke")
    p.add_argument("--name", required=True)
    p.add_argument("--remove", action="store_true")
    sub.add_parser("check")
    sub.add_parser("status")
    p = sub.add_parser("pick")
    p.add_argument("--folder", default="")
    p.add_argument("--after", default="")
    p = sub.add_parser("limit")
    p.add_argument("--id", required=True)
    p = sub.add_parser("relay")
    p.add_argument("--folder", required=True)
    p.add_argument("--from", default="")
    p.add_argument("--to", required=True)
    sub.add_parser("soonest")
    p = sub.add_parser("settings")
    p.add_argument("--id", required=True)
    sub.add_parser("engines")
    a = ap.parse_args(argv)
    return {"add": cmd_add, "consent": cmd_consent, "revoke": cmd_revoke, "check": cmd_check,
            "status": cmd_status, "pick": cmd_pick, "limit": cmd_limit, "relay": cmd_relay,
            "soonest": cmd_soonest, "settings": cmd_settings, "engines": cmd_engines}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
