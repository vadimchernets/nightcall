"""Nightcall tests: run with `python3 -m pytest tests` (or `python3 tests/test_nightcall.py`).

The keep-awake test really starts the Mac/Linux coffee for a few seconds and checks that the
process is gone afterwards - by itself, and after `stop`.
"""

import datetime
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")
LANG_DIR = os.path.join(ROOT, "lang")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def fixture(path):
    """One sample message from tests/fixtures/<path> (own-language text, kept out of this file)."""
    with open(os.path.join(FIXTURES, path), encoding="utf-8") as fh:
        return fh.read().strip()


def run(cmd, env=None, inp=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(cmd, capture_output=True, text=True, env=e, input=inp, timeout=120)


def test_bash_syntax():
    for f in ("awake.sh", "awake-mac.sh", "awake-linux.sh", "night-loop.sh"):
        assert run(["bash", "-n", os.path.join(S, f)]).returncode == 0, f


def test_powershell_syntax():
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        return  # no PowerShell here; checked on Windows
    code = ("$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e)"
            "|Out-Null; if($e.Count){$e;exit 1}" % os.path.join(S, "awake-windows.ps1"))
    assert run([pwsh, "-NoProfile", "-Command", code]).returncode == 0


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def test_awake_starts_ends_by_itself_and_stops():
    if platform.system() not in ("Darwin", "Linux"):
        return
    home = tempfile.mkdtemp()
    env = {"NIGHTCALL_HOME": home}
    name = "awake-mac" if platform.system() == "Darwin" else "awake-linux"
    # bad input is refused
    assert run(["bash", os.path.join(S, "awake.sh"), "abc"], env).returncode == 2
    assert run(["bash", os.path.join(S, "awake.sh"), "25"], env).returncode == 2
    # 3 seconds: on, then gone by itself
    r = run(["bash", os.path.join(S, "awake.sh"), "3s"], env)
    assert r.returncode == 0 and "ON" in r.stdout, r.stdout + r.stderr
    pid = open(os.path.join(home, name + ".pid")).read().strip()
    assert pid_alive(pid)
    assert run(["bash", os.path.join(S, "awake.sh"), "status"], env).returncode == 0
    time.sleep(5)
    assert not pid_alive(pid), "coffee did not end by itself"
    assert run(["bash", os.path.join(S, "awake.sh"), "status"], env).returncode == 1
    # 1 minute: on, then stop removes it
    run(["bash", os.path.join(S, "awake.sh"), "1m"], env)
    pid = open(os.path.join(home, name + ".pid")).read().strip()
    assert pid_alive(pid)
    r = run(["bash", os.path.join(S, "awake.sh"), "stop"], env)
    assert "OFF" in r.stdout
    time.sleep(0.5)
    assert not pid_alive(pid), "stop did not remove the process"


def fake(bindir, name, body):
    p = os.path.join(bindir, name)
    with open(p, "w") as fh:
        fh.write("#!/bin/sh\n" + body + "\n")
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)


def test_team_probe_and_replacement():
    if platform.system() == "Windows":
        return
    bindir = tempfile.mkdtemp()
    fake(bindir, "codex", 'echo "ERROR: Your workspace is out of credits." >&2; exit 1')
    fake(bindir, "grok", 'echo "API error (status 402 Payment Required)" >&2; exit 1')
    fake(bindir, "qwen", 'echo "No auth type is selected." >&2; exit 1')
    fake(bindir, "kimi", 'echo "ok"')
    env = {"NIGHTCALL_PATH": bindir + os.pathsep + "/usr/bin" + os.pathsep + "/bin",
           "OPENAI_API_KEY": "must-not-leak"}
    seats = os.path.join(tempfile.mkdtemp(), "seats.json")
    r = run([sys.executable, os.path.join(S, "team.py"), "probe", "--out", seats], env)
    data = json.load(open(seats, encoding="utf-8"))
    st = {s["program"]: s["status"] for s in data["helpers"]}
    assert st == {"codex": "limit", "grok": "limit",
                  "qwen": "not-signed-in", "kimi": "alive"}, st
    # ask codex first: without seats it fails and kimi answers instead
    fake(bindir, "kimi", 'env | grep -q OPENAI_API_KEY && echo LEAK || echo "kimi answer"')
    r = run([sys.executable, os.path.join(S, "team.py"), "ask", "--who", "codex", "-"], env, "question")
    out = json.loads(r.stdout)
    assert out["ok"] and out["program"] == "kimi" and out["answer"] == "kimi answer", out
    assert out["could_not"][0]["status"] == "limit"


def team(args, env, inp=None):
    return run([sys.executable, os.path.join(S, "team.py")] + args, env, inp)


def test_rollcall_table_limit_time_and_missing():
    if platform.system() == "Windows":
        return
    bindir = tempfile.mkdtemp()
    fake(bindir, "claude", 'echo "ok"')
    fake(bindir, "codex", 'echo "You have hit your usage limit. Try again at 3:15 AM." >&2; exit 1')
    fake(bindir, "kimi", 'echo "ok"')
    env = {"NIGHTCALL_PATH": bindir, "NIGHTCALL_HOME": tempfile.mkdtemp()}
    seats = os.path.join(tempfile.mkdtemp(), "seats.json")
    r = team(["rollcall", "--out", seats], env)
    assert "not installed" in r.stdout and "Grok" in r.stdout, r.stdout   # grok is not installed
    assert "Claude (main)" in r.stdout and "limit until 03:15" in r.stdout, r.stdout
    data = json.load(open(seats, encoding="utf-8"))
    codex = next(s for s in data["helpers"] if s["program"] == "codex")
    assert codex["status"] == "limit" and codex["until"].endswith("03:15"), codex
    assert all(s["program"] != "claude" for s in data["helpers"])   # the main one is not a helper


def test_web_marks_summary_and_no_helpers():
    env = {"NIGHTCALL_PATH": tempfile.mkdtemp(), "NIGHTCALL_HOME": tempfile.mkdtemp()}
    d = tempfile.mkdtemp()
    seats = os.path.join(d, "seats.json")
    team(["rollcall", "--out", seats], env)
    r = team(["summary", "--seats", seats], env)
    assert r.returncode == 1 and "second head is Claude's own critics" in r.stdout, r.stdout   # nobody alive: said plainly
    team(["web-mark", "--seats", seats, "--browser", "alive"], env)
    team(["web-mark", "--seats", seats, "--site", "chatgpt", "--status", "alive"], env)
    team(["web-mark", "--seats", seats, "--site", "gemini", "--status", "needs-sign-in"], env)
    team(["web-mark", "--seats", seats, "--site", "deepseek", "--status", "captcha"], env)
    assert team(["web-mark", "--seats", seats, "--site", "kimi", "--status", "maybe"], env).returncode == 2
    data = json.load(open(seats, encoding="utf-8"))
    assert {w["site"]: w["status"] for w in data["web"]} == {
        "chatgpt": "alive", "gemini": "needs-sign-in", "deepseek": "captcha"}
    r = team(["summary", "--seats", seats], env)
    assert r.returncode == 0 and "Reserve: web ChatGPT" in r.stdout, r.stdout
    assert "Gemini: open" in r.stdout and "DeepSeek" in r.stdout, r.stdout
    # the rollcall again keeps the browser results
    team(["rollcall", "--out", seats], env)
    assert len(json.load(open(seats, encoding="utf-8"))["web"]) == 3
    # only sites that passed the roll call are in the night route, Claude critics last
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert [x["route"] for x in route] == ["web", "claude"] and route[0]["who"] == "chatgpt", route
    # a site that answered at night is counted for the morning; a site that later asks for sign-in is logged
    prog = os.path.join(d, "PROGRESS.md")
    team(["web-mark", "--seats", seats, "--site", "chatgpt", "--answered"], env)
    team(["web-mark", "--seats", seats, "--site", "chatgpt", "--status", "needs-sign-in", "--progress", prog], env)
    assert "ChatGPT: alive → needs-sign-in" in open(prog, encoding="utf-8").read()
    assert "web:chatgpt — answers: 1" in team(["used", "--seats", seats], env).stdout


def test_replacement_order_cli_key_web_claude_and_limit_comes_back():
    if platform.system() == "Windows":
        return
    import http.server
    import threading
    seen = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen["auth"] = self.headers.get("Authorization")
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps({"choices": [{"message": {"content": "answer via key"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bindir, home, d = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    fake(bindir, "codex", 'echo "ok"')
    fake(bindir, "kimi", 'echo "ok"')
    with open(os.path.join(home, "free-keys.env"), "w") as fh:
        fh.write("GROQ_API_KEY=free-test-key\n")
    env = {"NIGHTCALL_PATH": bindir, "NIGHTCALL_HOME": home,
           "NIGHTCALL_KEY_URL_GROQ": "http://127.0.0.1:%d/v1/chat/completions" % srv.server_port}
    seats = os.path.join(d, "seats.json")
    prog = os.path.join(d, "PROGRESS.md")
    team(["rollcall", "--out", seats], env)
    team(["web-mark", "--seats", seats, "--site", "kimi", "--status", "alive"], env)
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert [(x["route"], x["who"]) for x in route] == [
        ("cli", "codex"), ("cli", "kimi"), ("key", "groq"), ("web", "kimi"), ("claude", "claude-critics")], route
    # at night: codex hits the limit (reset time in 1 hour), kimi breaks -> the free key answers
    fake(bindir, "codex", 'echo "Rate limit reached, resets in 1h" >&2; exit 1')
    fake(bindir, "kimi", 'echo "segfault" >&2; exit 3')
    out = json.loads(team(["ask", "--seats", seats, "--progress", prog, "-"], env, "question").stdout)
    assert out["ok"] and out["route"] == "key" and out["answer"] == "answer via key", out
    assert seen["auth"] == "Bearer free-test-key"
    log = open(prog, encoding="utf-8").read()
    assert "limit until" in log and "replaced: Groq" in log, log
    # the key breaks too -> the answer points to the live web chat, then Claude's own critics
    srv.shutdown()
    srv.server_close()
    out = json.loads(team(["ask", "--seats", seats, "--progress", prog, "-"], env, "question").stdout)
    assert not out["ok"] and out["next"]["route"] == "web" and out["reserve"][-1]["route"] == "claude", out
    # codex's limit time passes -> it is back at the head of the route
    data = json.load(open(seats, encoding="utf-8"))
    for s in data["helpers"]:
        if s["program"] == "codex":
            s["until"] = (datetime.datetime.now() - datetime.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
    json.dump(data, open(seats, "w", encoding="utf-8"), ensure_ascii=False)
    fake(bindir, "codex", 'echo "back again"')
    out = json.loads(team(["ask", "--seats", seats, "-"], env, "question").stdout)
    assert out["ok"] and out["program"] == "codex", out
    used = team(["used", "--seats", seats], env).stdout
    assert "key:groq" in used and "cli:codex" in used, used
    # the key value is never written to seats.json
    assert "free-test-key" not in open(seats, encoding="utf-8").read()


def test_reads_legacy_russian_seats_and_blind_files():
    """nightcall <= 0.3.3 wrote Russian field/status names and file names (now in lang/ru.json's
    "legacy" section). Files already on a person's disk from before the English rename must still
    be read correctly (read-only: nothing is written back under the old names). The old names
    themselves are read from lang/ru.json through team.py - not hand-copied here - so this stays
    correct if that table ever changes."""
    sys.path.insert(0, S)
    import team as T
    rev_keys = {v: k for k, v in T.LEGACY_KEYS.items()}
    rev_status = {v: k for k, v in T.LEGACY_STATUS.items()}

    bindir0 = tempfile.mkdtemp()
    fake(bindir0, "kimi", 'echo "ok"')
    env = {"NIGHTCALL_PATH": bindir0, "NIGHTCALL_HOME": tempfile.mkdtemp()}
    d = tempfile.mkdtemp()
    seats = os.path.join(d, "seats.json")
    old_seats = {
        rev_keys["helpers"]: [{rev_keys["family"]: "moonshot", rev_keys["program"]: "kimi",
                                rev_keys["name"]: "Kimi", rev_keys["path"]: "/bin/kimi",
                                rev_keys["status"]: rev_status["alive"], rev_keys["why"]: "",
                                rev_keys["checked"]: "01:00"}],
        rev_keys["keys"]: [],
        rev_keys["web"]: [{rev_keys["site"]: "chatgpt", rev_keys["name"]: "ChatGPT",
                            rev_keys["url"]: "https://chatgpt.com/", rev_keys["status"]: rev_status["alive"],
                            rev_keys["why"]: "", rev_keys["checked"]: "01:00"}],
        rev_keys["browser"]: {}, rev_keys["participated"]: {},
        rev_keys["web_when"]: "night", rev_keys["decide_when"]: "council",
    }
    json.dump(old_seats, open(seats, "w", encoding="utf-8"), ensure_ascii=False)
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert [(x["route"], x["who"]) for x in route] == [("cli", "kimi"), ("web", "chatgpt"),
                                                         ("claude", "claude-critics")], route
    assert "Working tonight: Kimi" in team(["summary", "--seats", seats], env).stdout
    r = run([sys.executable, os.path.join(S, "ready.py"), "--dir", d], env)
    assert "Roll call done: 1 program(s)/key(s) alive" in r.stdout, r.stdout

    # decisions.md / morning-advice.md: an old-named file already there keeps being used, not replaced
    legacy_decisions = os.path.join(d, T.LEGACY_DECISIONS_NAME)
    open(legacy_decisions, "w", encoding="utf-8").write("# Decisions of the night\n")
    out = json.loads(team(["decide", "--dir", d, "--what", "x", "--why", "y", "--who", "z"], env).stdout)
    assert out["decisions"] == legacy_decisions
    assert not os.path.exists(os.path.join(d, "decisions.md"))

    # a legacy blind answer file (old keys) is picked up together with a newly-saved one
    folder = tempfile.mkdtemp()
    with open(os.path.join(folder, T.LEGACY_ANSWER_PREFIX + "1.json"), "w", encoding="utf-8") as fh:
        json.dump({rev_keys["who"]: "Kimi", rev_keys["route"]: "cli", rev_keys["answer"]: "old answer"},
                   fh, ensure_ascii=False)
    bindir = tempfile.mkdtemp()
    fake(bindir, "grok", 'echo "new answer"')
    env2 = {"NIGHTCALL_PATH": bindir + os.pathsep + "/usr/bin" + os.pathsep + "/bin",
            "NIGHTCALL_HOME": tempfile.mkdtemp()}
    team(["ask", "--who", "grok", "--no-fallback", "--blind", folder, "-"], env2, "question")
    r = team(["blind", "--dir", folder], env2)
    assert "old answer" in r.stdout and "new answer" in r.stdout, r.stdout

    # reveal falls back to the old hidden mapping file when only it exists
    folder2 = tempfile.mkdtemp()
    with open(os.path.join(folder2, T.LEGACY_BLIND_KEY), "w", encoding="utf-8") as fh:
        json.dump({"A": "Kimi"}, fh, ensure_ascii=False)
    r = team(["reveal", "--dir", folder2], env)
    assert json.loads(r.stdout) == {"A": "Kimi"}, r.stdout


def test_night_loop_resolves_legacy_web_and_decide_choice():
    """night-loop.sh must read seats.json's web/decide choice through team.py's own
    load_seats()/web_when()/decide_when() - not by looking up the current key name itself - so a
    seats.json written before the English rename (Russian keys) still gives the person's real
    choice instead of silently falling back to the default (owner review, 02.10.2026)."""
    sys.path.insert(0, S)
    import team as T
    loop = open(os.path.join(S, "night-loop.sh"), encoding="utf-8").read()
    assert "T.web_when(T.load_seats(" in loop and "T.decide_when(T.load_seats(" in loop, loop
    d = tempfile.mkdtemp()
    seats = os.path.join(d, "seats.json")
    rev_keys = {v: k for k, v in T.LEGACY_KEYS.items()}
    json.dump({rev_keys["web_when"]: "morning", rev_keys["decide_when"]: "morning"},
              open(seats, "w", encoding="utf-8"), ensure_ascii=False)
    assert T.web_when(T.load_seats(seats)) == "morning"
    assert T.decide_when(T.load_seats(seats)) == "morning"


def test_reset_time_parsing():
    sys.path.insert(0, S)
    import team as T
    base = datetime.datetime(2026, 9, 30, 23, 0)
    assert T.reset_time("resets at 3am", base).strftime("%d %H:%M") == "01 03:00"
    assert T.reset_time("Try again at 14:30", base).strftime("%H:%M") == "14:30"
    assert T.reset_time("limit, resets in 2h 15m", base).strftime("%H:%M") == "01:15"
    assert T.reset_time("You are out of credits", base) is None
    # a helper (CLI or web chat) on a Russian-locale machine or Russian-UI account answers in
    # Russian, not English - the same reset wording must still parse (owner review, 02.10.2026)
    assert T.reset_time(fixture("ru/reset_at.txt"), base).strftime("%H:%M") == "03:00"
    assert T.reset_time(fixture("ru/reset_in.txt"), base).strftime("%H:%M") == "01:15"


def test_classifies_russian_quota_and_auth_messages():
    """The translator that renamed Russian field/status names to English (0.3.4) must not also
    narrow QUOTA/AUTH detection to English-only: a helper can still print Russian on a Russian-
    locale machine or account. QUOTA_WORDS/AUTH_WORDS keep a "ru" entry next to "en" for this."""
    sys.path.insert(0, S)
    import team as T
    r = T.classify(False, "", fixture("ru/quota.txt"))
    assert r["status"] == "limit" and r["until"].endswith("03:00"), r
    r = T.classify(False, "", fixture("ru/auth.txt"))
    assert r["status"] == "not-signed-in", r


def test_lang_files_share_the_same_category_keys():
    """Every lang/<code>.json recognises the same categories as lang/en.json (quota, auth,
    reset_at, reset_in, reset_in_hour, reset_in_min) - ru.json's extra "legacy" section aside."""
    names = sorted(f for f in os.listdir(LANG_DIR) if f.endswith(".json"))
    assert {"en.json", "ru.json", "es.json", "pt.json", "uk.json"} <= set(names)
    with open(os.path.join(LANG_DIR, "en.json"), encoding="utf-8") as fh:
        en_keys = set(json.load(fh))
    for name in names:
        with open(os.path.join(LANG_DIR, name), encoding="utf-8") as fh:
            keys = set(json.load(fh)) - {"legacy"}
        assert keys == en_keys, name


def test_each_language_table_is_loaded_and_recognises_a_sample():
    """team.py loads every lang/<code>.json (QUOTA_WORDS/AUTH_WORDS/... cover every language found
    there) and the combined recognizer catches one quota/auth/reset-time sample per language."""
    sys.path.insert(0, S)
    import team as T
    assert {"en", "ru", "es", "pt", "uk"} <= set(T.QUOTA_WORDS)
    samples = {
        "en": {"quota": "You have hit your limit for today.",
               "auth": "Please sign in to continue.",
               "reset": "limit reached, resets at 03:00"},
        "ru": {"quota": fixture("ru/quota.txt"), "auth": fixture("ru/auth.txt"),
               "reset": fixture("ru/reset_in.txt")},
        "es": {"quota": fixture("es/quota.txt"), "auth": fixture("es/auth.txt"),
               "reset": fixture("es/reset_at.txt")},
        "pt": {"quota": fixture("pt/quota.txt"), "auth": fixture("pt/auth.txt"),
               "reset": fixture("pt/reset_at.txt")},
        "uk": {"quota": fixture("uk/quota.txt"), "auth": fixture("uk/auth.txt"),
               "reset": fixture("uk/reset_at.txt")},
    }
    for code, s in samples.items():
        assert T.QUOTA.search(s["quota"]), (code, s["quota"])
        assert T.AUTH.search(s["auth"]), (code, s["auth"])
        assert T.reset_time(s["reset"]) is not None, (code, s["reset"])
    # Both reset paths ("at 03:00" and "in 2h 15m") in every language with fixtures.
    from datetime import datetime
    base = datetime(2026, 9, 1, 23, 0)
    for code in ("ru", "es", "pt", "uk"):
        assert T.reset_time(fixture(f"{code}/reset_at.txt"), base).strftime("%H:%M") == "03:00", code
        assert T.reset_time(fixture(f"{code}/reset_in.txt"), base).strftime("%H:%M") == "01:15", code


def test_everyday_words_are_not_a_quota():
    """An ordinary successful short answer must not read as "limit reached" in any language."""
    sys.path.insert(0, S)
    import team as T
    for text in ("La cuota mensual del gimnasio es de 30 euros.",
                 "Cada cota do fundo vale R$ 100 hoje.",
                 fixture("uk/not_quota.txt")):
        assert not T.QUOTA.search(text), text


def test_night_begin_arm_hook_end():
    home = tempfile.mkdtemp()
    folder = os.path.join(tempfile.mkdtemp(), "night")
    env = {"NIGHTCALL_HOME": home}
    night = [sys.executable, os.path.join(S, "night.py")]
    hook = [sys.executable, os.path.join(ROOT, "hooks", "stop.py")]
    r = run(night + ["begin", "--dir", folder, "--hours", "1"], env, "write a report")
    assert r.returncode == 0
    for f in ("TASK.md", "PLAN.md", "PROGRESS.md"):
        assert os.path.exists(os.path.join(folder, f)), f
    # not armed yet: the person is still here, a turn may end
    assert run(hook, env, '{"session_id":"A"}').stdout.strip() == ""
    run(night + ["arm", "--dir", folder, "--hours", "1", "--max-rounds", "2"], env)
    assert '"block"' in run(hook, env, '{"session_id":"A"}').stdout
    assert run(hook, env, '{"session_id":"B"}').stdout.strip() == ""   # other window is free
    assert '"block"' in run(hook, env, '{"session_id":"A"}').stdout
    assert run(hook, env, '{"session_id":"A"}').stdout.strip() == ""   # round ceiling
    run(night + ["arm", "--dir", folder, "--hours", "1"], env)
    open(os.path.join(folder, "STOP"), "w").close()
    assert run(hook, env, '{"session_id":"A"}').stdout.strip() == ""   # STOP file
    os.remove(os.path.join(folder, "STOP"))
    open(os.path.join(folder, "MORNING.md"), "w").close()
    assert run(hook, env, '{"session_id":"A"}').stdout.strip() == ""   # morning report
    os.remove(os.path.join(folder, "MORNING.md"))
    # past the end time: exactly one last round to write the report
    act = os.path.join(home, "active.json")
    d = json.load(open(act))
    d["until"] = (datetime.datetime.now() - datetime.timedelta(minutes=1)).isoformat()
    json.dump(d, open(act, "w"))
    assert "nightcall:morning" in run(hook, env, '{"session_id":"A"}').stdout
    assert run(hook, env, '{"session_id":"A"}').stdout.strip() == ""
    run(night + ["end"], env)
    assert not os.path.exists(act)


def test_begin_always_makes_restore_point_and_fence():
    if shutil.which("git") is None:
        return
    home = tempfile.mkdtemp()
    env = {"NIGHTCALL_HOME": home}
    night = [sys.executable, os.path.join(S, "night.py")]
    # a folder that is not code and not under git: git init + commit "before the night" + tag + fence
    folder = tempfile.mkdtemp()
    open(os.path.join(folder, "notes.txt"), "w").write("evening")
    r = run(night + ["begin", "--dir", folder], env, "rewrite the notes")
    assert r.returncode == 0 and "restore point: git tag nightcall-before-" in r.stdout, r.stdout + r.stderr
    log = run(["git", "-C", folder, "log", "--format=%s"]).stdout
    assert "nightcall: before the night" in log and "nightcall: fence for the night" in log, log
    tag = run(["git", "-C", folder, "tag", "--list", "nightcall-before-*"]).stdout.split()[0]
    files = run(["git", "-c", "core.quotepath=false", "-C", folder, "ls-tree", "--name-only", tag]).stdout
    assert "notes.txt" in files, files
    fence = open(os.path.join(folder, "CLAUDE.md"), encoding="utf-8").read()
    assert "nightcall:fence" in fence and "ONLY inside this folder" in fence and folder in fence
    assert "reset --hard " + tag in fence
    # a git folder with the person's own CLAUDE.md: kept, uncommitted work committed, fence replaced not doubled
    open(os.path.join(folder, "CLAUDE.md"), "w").write("# My rules\n")
    open(os.path.join(folder, "new.txt"), "w").write("not committed")
    run(night + ["begin", "--dir", folder], env, "")
    text = open(os.path.join(folder, "CLAUDE.md"), encoding="utf-8").read()
    assert text.startswith("# My rules") and text.count("nightcall:fence") == 1, text
    assert run(["git", "-C", folder, "status", "--porcelain"]).stdout.strip() == ""
    # ready shows the restore point
    r = run([sys.executable, os.path.join(S, "ready.py"), "--dir", folder], env)
    assert "Restore point: present" in r.stdout and "Fence: present" in r.stdout, r.stdout
    fresh = tempfile.mkdtemp()
    r = run([sys.executable, os.path.join(S, "ready.py"), "--dir", fresh], env)
    assert "Restore point: will be created" in r.stdout and "Fence: will be written" in r.stdout, r.stdout


def test_hook_bound_to_the_session_that_armed_the_night():
    home = tempfile.mkdtemp()
    folder = os.path.join(tempfile.mkdtemp(), "night")
    env = {"NIGHTCALL_HOME": home}
    night = [sys.executable, os.path.join(S, "night.py")]
    hook = [sys.executable, os.path.join(ROOT, "hooks", "stop.py")]
    run(night + ["begin", "--dir", folder], env, "task")
    run(night + ["arm", "--dir", folder, "--session", "NIGHT"], env)
    # another window finishes its turn first: it is NOT caught, and the night stays with NIGHT
    assert run(hook, env, json.dumps({"session_id": "OTHER", "cwd": folder})).stdout.strip() == ""
    assert '"block"' in run(hook, env, json.dumps({"session_id": "NIGHT", "cwd": "/"})).stdout
    assert json.load(open(os.path.join(home, "active.json")))["session"] == "NIGHT"
    # an unexpanded ${CLAUDE_SESSION_ID} is no session: bind only a window working in the task folder
    run(night + ["arm", "--dir", folder, "--session", "${CLAUDE_SESSION_ID}"], env)
    assert run(hook, env, json.dumps({"session_id": "ELSE", "cwd": tempfile.mkdtemp()})).stdout.strip() == ""
    assert '"block"' in run(hook, env, json.dumps({"session_id": "MINE", "cwd": folder})).stdout
    assert run(hook, env, json.dumps({"session_id": "ELSE", "cwd": folder})).stdout.strip() == ""


def test_web_when_morning_saves_question():
    bindir, home, d = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    env = {"NIGHTCALL_PATH": bindir, "NIGHTCALL_HOME": home}
    seats = os.path.join(d, "seats.json")
    team(["rollcall", "--out", seats], env)
    team(["web-mark", "--seats", seats, "--site", "chatgpt", "--status", "alive"], env)
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert route[0]["route"] == "web"          # default: web chats are the night reserve
    assert json.load(open(seats, encoding="utf-8")).get("web_when", "night") == "night"
    team(["web-when", "--seats", seats, "morning"], env)
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert [x["route"] for x in route] == ["claude"], route
    out = json.loads(team(["ask", "--seats", seats, "--dir", d, "-"], env, "What's missing from the plan?").stdout)
    assert out["morning_advice"] == os.path.join(d, "morning-advice.md") and out["next"]["route"] == "claude"
    assert "What's missing from the plan?" in open(out["morning_advice"], encoding="utf-8").read()
    # the choice survives the next roll call
    team(["rollcall", "--out", seats], env)
    assert json.load(open(seats, encoding="utf-8"))["web_when"] == "morning"
    assert "(in the morning)" in team(["summary", "--seats", seats], env).stdout


def test_morning_template_puts_the_decision_first():
    text = open(os.path.join(ROOT, "skills", "morning", "SKILL.md"), encoding="utf-8").read()
    heads = [h for h in ("## Needs your decision", "## Done", "## Not done", "## Check", "## Who took part")]
    pos = [text.index(h) for h in heads]
    assert pos == sorted(pos), pos
    loop = open(os.path.join(S, "night-loop.sh"), encoding="utf-8").read()
    assert "Needs your decision" in loop and "web_when" in loop and "night.py\" begin" in loop


def test_ready_runs():
    r = run([sys.executable, os.path.join(S, "ready.py")], {"NIGHTCALL_HOME": tempfile.mkdtemp()})
    assert "Before the night" in r.stdout and "Total" in r.stdout, r.stdout + r.stderr


def test_manifest_and_skills():
    m = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    assert m["name"] == "nightcall"
    for s in ("start", "awake", "team", "ready", "morning", "family"):
        text = open(os.path.join(ROOT, "skills", s, "SKILL.md"), encoding="utf-8").read()
        assert text.startswith("---\nname: %s\n" % s), s
    json.load(open(os.path.join(ROOT, "hooks", "hooks.json")))


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)


def test_decide_when_council_default_decide_and_hold():
    bindir, home, d = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    env = {"NIGHTCALL_PATH": bindir, "NIGHTCALL_HOME": home}
    seats = os.path.join(d, "seats.json")
    team(["rollcall", "--out", seats], env)
    assert json.load(open(seats, encoding="utf-8"))["decide_when"] == "council"   # default
    assert "the AI council decides" in team(["summary", "--seats", seats], env).stdout
    out = json.loads(team(["decide", "--dir", d, "--what", "table format — CSV", "--why", "easier to open",
                           "--who", "codex, its own critics", "--alt", "xlsx", "--commit", "abc1234"], env).stdout)
    assert out["undo"] == "git revert abc1234"
    text = open(out["decisions"], encoding="utf-8").read()
    assert "table format — CSV" in text and "git revert abc1234" in text and "Fix it like this" in text
    team(["decide-when", "--seats", seats, "morning"], env)
    team(["rollcall", "--out", seats], env)                 # the choice survives the next roll call
    assert json.load(open(seats, encoding="utf-8"))["decide_when"] == "morning"
    assert "all to the morning" in team(["summary", "--seats", seats], env).stdout
    team(["hold", "--dir", d, "--question", "Should we publish?", "--waits", "step 7"], env)
    assert "waiting for your answer: Should we publish?" in open(os.path.join(d, "decisions.md"), encoding="utf-8").read()


def test_free_key_tries_next_model_and_nvidia_goes_first():
    if platform.system() == "Windows":
        return
    import http.server
    import threading
    asked = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            model = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["model"]
            asked.append(model)
            if model == "moonshotai/kimi-k3":
                self.send_response(429)
                self.end_headers()
                self.wfile.write(b'{"error": "too many requests"}')
                return
            body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bindir, home, d = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    url = "http://127.0.0.1:%d/v1/chat/completions" % srv.server_port
    with open(os.path.join(home, "free-keys.env"), "w") as fh:
        fh.write("GROQ_API_KEY=g-test\nNVIDIA_API_KEY=n-test\n")
    env = {"NIGHTCALL_PATH": bindir, "NIGHTCALL_HOME": home,
           "NIGHTCALL_KEY_URL_GROQ": url, "NIGHTCALL_KEY_URL_NVIDIA": url}
    seats = os.path.join(d, "seats.json")
    r = team(["rollcall", "--out", seats], env)
    assert "z-ai/glm-5.3" in r.stdout, r.stdout + r.stderr
    assert asked[:2] == ["moonshotai/kimi-k3", "z-ai/glm-5.3"], asked
    keys = [k["key"] for k in json.load(open(seats, encoding="utf-8"))["keys"]]
    assert keys == ["nvidia", "groq"], keys
    assert all(k["status"] == "alive" for k in json.load(open(seats, encoding="utf-8"))["keys"])
    assert "n-test" not in open(seats, encoding="utf-8").read()


def test_blind_comparison_hides_names_until_reveal():
    """Owner, 01.10.2026: the judge sees "Answer A / B", names only after the decision."""
    if platform.system() == "Windows":
        return
    bindir = tempfile.mkdtemp()
    fake(bindir, "kimi", 'echo "option one: do it via a queue"')
    fake(bindir, "grok", 'echo "option two: do it right away"')
    env = {"NIGHTCALL_PATH": bindir + os.pathsep + "/usr/bin" + os.pathsep + "/bin",
           "NIGHTCALL_HOME": tempfile.mkdtemp()}
    folder = os.path.join(tempfile.mkdtemp(), "council")
    for who in ("kimi", "grok"):
        r = team(["ask", "--who", who, "--no-fallback", "--blind", folder, "-"], env, "question")
        out = json.loads(r.stdout)
        assert out["ok"] and "who" not in out and "answer" not in out, out
        assert who not in r.stdout.lower() and "Kimi" not in r.stdout and "Grok" not in r.stdout, r.stdout
    r = team(["blind", "--dir", folder], env)
    assert r.returncode == 0
    assert "Answer A" in r.stdout and "Answer B" in r.stdout, r.stdout
    assert "option one" in r.stdout and "option two" in r.stdout
    for name in ("kimi", "grok", "moonshot", "xai"):
        assert name not in r.stdout.lower(), r.stdout
    r = team(["reveal", "--dir", folder], env)
    who = json.loads(r.stdout)
    assert sorted(who) == ["A", "B"] and sorted(who.values()) == ["Grok", "Kimi"], who


def test_429_goes_to_the_next_provider_not_the_next_key():
    """Free limits are per project/account (Google, Groq, OpenRouter, NVIDIA docs, 02.10.2026)."""
    if platform.system() == "Windows":
        return
    import http.server
    import threading
    asked = []
    replies = {
        "moonshotai/kimi-k3": (429, b'{"error": {"message": "Too Many Requests"}}'),
        "gemini-3.8-flash": (429, b'[{"error": {"code": 429, "message": "You exceeded your current quota",'
                                  b' "details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}]'),
        "qwen/qwen3.8-27b:free": (429, b'{"error": {"message": "Rate limit exceeded: free-models-per-day"}}'),
    }

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            model = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["model"]
            asked.append(model)
            code, body = replies.get(model, (200, json.dumps(
                {"choices": [{"message": {"content": "answer " + model}}]}).encode()))
            self.send_response(code)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    home = tempfile.mkdtemp()
    url = "http://127.0.0.1:%d/v1/chat/completions" % srv.server_port
    with open(os.path.join(home, "free-keys.env"), "w") as fh:
        fh.write("NVIDIA_API_KEY=n\nGEMINI_API_KEY=g\nOPENROUTER_API_KEY=o\n")
    env = {"NIGHTCALL_PATH": tempfile.mkdtemp(), "NIGHTCALL_HOME": home, "NIGHTCALL_KEY_URL_NVIDIA": url,
           "NIGHTCALL_KEY_URL_GOOGLE_AI_STUDIO": url, "NIGHTCALL_KEY_URL_OPENROUTER": url}
    # NVIDIA per-minute -> straight to Google, not to GLM on the same account;
    # Gemini daily for 3.8 -> 3.6 has its own quota and answers
    r = team(["ask", "-"], env, "question")
    out = json.loads(r.stdout)
    assert out["ok"] and out["answer"] == "answer gemini-3.6-flash", out
    assert asked == ["moonshotai/kimi-k3", "gemini-3.8-flash", "gemini-3.6-flash"], asked
    # OpenRouter daily (free-models-per-day covers all :free) -> no other OpenRouter model
    asked.clear()
    replies["gemini-3.6-flash"] = replies["gemini-2.5-flash"] = replies["gemini-3.8-flash"]
    replies["z-ai/glm-5.3"] = replies["moonshotai/kimi-k3"]
    r = team(["ask", "-"], env, "question")
    out = json.loads(r.stdout)
    assert not out["ok"], out
    assert asked.count("qwen/qwen3.8-27b:free") == 1 and "openrouter/free" not in asked, asked
    # per-minute NVIDIA came back once at the end of the line (Kimi again), not GLM in between
    assert asked[0] == "moonshotai/kimi-k3" and asked[1] == "gemini-3.8-flash", asked
    assert asked.count("moonshotai/kimi-k3") == 2, asked
