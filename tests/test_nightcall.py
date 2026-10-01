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
    assert r.returncode == 0 and "ВКЛЮЧЕНО" in r.stdout, r.stdout + r.stderr
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
    assert "ВЫКЛЮЧЕНО" in r.stdout
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
    fake(bindir, "kimi", 'echo "ок"')
    env = {"NIGHTCALL_PATH": bindir + os.pathsep + "/usr/bin" + os.pathsep + "/bin",
           "OPENAI_API_KEY": "must-not-leak"}
    seats = os.path.join(tempfile.mkdtemp(), "seats.json")
    r = run([sys.executable, os.path.join(S, "team.py"), "probe", "--out", seats], env)
    data = json.load(open(seats, encoding="utf-8"))
    st = {s["программа"]: s["статус"] for s in data["помощники"]}
    assert st == {"codex": "лимит", "grok": "лимит",
                  "qwen": "не вошли", "kimi": "жив"}, st
    # ask codex first: without seats it fails and kimi answers instead
    fake(bindir, "kimi", 'env | grep -q OPENAI_API_KEY && echo LEAK || echo "ответ kimi"')
    r = run([sys.executable, os.path.join(S, "team.py"), "ask", "--who", "codex", "-"], env, "вопрос")
    out = json.loads(r.stdout)
    assert out["ok"] and out["программа"] == "kimi" and out["ответ"] == "ответ kimi", out
    assert out["не_смогли"][0]["статус"] == "лимит"


def team(args, env, inp=None):
    return run([sys.executable, os.path.join(S, "team.py")] + args, env, inp)


def test_rollcall_table_limit_time_and_missing():
    if platform.system() == "Windows":
        return
    bindir = tempfile.mkdtemp()
    fake(bindir, "claude", 'echo "ок"')
    fake(bindir, "codex", 'echo "You have hit your usage limit. Try again at 3:15 AM." >&2; exit 1')
    fake(bindir, "kimi", 'echo "ок"')
    env = {"NIGHTCALL_PATH": bindir, "NIGHTCALL_HOME": tempfile.mkdtemp()}
    seats = os.path.join(tempfile.mkdtemp(), "seats.json")
    r = team(["rollcall", "--out", seats], env)
    assert "нет программы" in r.stdout and "Grok" in r.stdout, r.stdout   # grok is not installed
    assert "Claude (главный)" in r.stdout and "лимит до 03:15" in r.stdout, r.stdout
    data = json.load(open(seats, encoding="utf-8"))
    codex = next(s for s in data["помощники"] if s["программа"] == "codex")
    assert codex["статус"] == "лимит" and codex["до"].endswith("03:15"), codex
    assert all(s["программа"] != "claude" for s in data["помощники"])   # the main one is not a helper


def test_web_marks_summary_and_no_helpers():
    env = {"NIGHTCALL_PATH": tempfile.mkdtemp(), "NIGHTCALL_HOME": tempfile.mkdtemp()}
    d = tempfile.mkdtemp()
    seats = os.path.join(d, "seats.json")
    team(["rollcall", "--out", seats], env)
    r = team(["summary", "--seats", seats], env)
    assert r.returncode == 1 and "только со своими" in r.stdout, r.stdout   # nobody alive: said honestly
    team(["web-mark", "--seats", seats, "--browser", "жив"], env)
    team(["web-mark", "--seats", seats, "--site", "chatgpt", "--status", "жив"], env)
    team(["web-mark", "--seats", seats, "--site", "gemini", "--status", "нужен вход"], env)
    team(["web-mark", "--seats", seats, "--site", "deepseek", "--status", "капча"], env)
    assert team(["web-mark", "--seats", seats, "--site", "kimi", "--status", "может быть"], env).returncode == 2
    data = json.load(open(seats, encoding="utf-8"))
    assert {w["сайт"]: w["статус"] for w in data["веб"]} == {
        "chatgpt": "жив", "gemini": "нужен вход", "deepseek": "капча"}
    r = team(["summary", "--seats", seats], env)
    assert r.returncode == 0 and "Запас: веб ChatGPT" in r.stdout, r.stdout
    assert "Gemini: откройте" in r.stdout and "DeepSeek" in r.stdout, r.stdout
    # the rollcall again keeps the browser results
    team(["rollcall", "--out", seats], env)
    assert len(json.load(open(seats, encoding="utf-8"))["веб"]) == 3
    # only sites that passed the roll call are in the night route, Claude critics last
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert [x["путь"] for x in route] == ["веб", "claude"] and route[0]["кто"] == "chatgpt", route
    # a site that answered at night is counted for the morning; a site that later asks for sign-in is logged
    prog = os.path.join(d, "PROGRESS.md")
    team(["web-mark", "--seats", seats, "--site", "chatgpt", "--answered"], env)
    team(["web-mark", "--seats", seats, "--site", "chatgpt", "--status", "нужен вход", "--progress", prog], env)
    assert "ChatGPT: жив → нужен вход" in open(prog, encoding="utf-8").read()
    assert "веб:chatgpt — ответов: 1" in team(["used", "--seats", seats], env).stdout


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
            body = json.dumps({"choices": [{"message": {"content": "ответ по ключу"}}]}).encode()
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
    team(["web-mark", "--seats", seats, "--site", "kimi", "--status", "жив"], env)
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert [(x["путь"], x["кто"]) for x in route] == [
        ("cli", "codex"), ("cli", "kimi"), ("ключ", "groq"), ("веб", "kimi"), ("claude", "claude-critics")], route
    # at night: codex hits the limit (reset time in 1 hour), kimi breaks -> the free key answers
    fake(bindir, "codex", 'echo "Rate limit reached, resets in 1h" >&2; exit 1')
    fake(bindir, "kimi", 'echo "segfault" >&2; exit 3')
    out = json.loads(team(["ask", "--seats", seats, "--progress", prog, "-"], env, "вопрос").stdout)
    assert out["ok"] and out["путь"] == "ключ" and out["ответ"] == "ответ по ключу", out
    assert seen["auth"] == "Bearer free-test-key"
    log = open(prog, encoding="utf-8").read()
    assert "лимит до" in log and "заменён: Groq" in log, log
    # the key breaks too -> the answer points to the live web chat, then Claude's own critics
    srv.shutdown()
    srv.server_close()
    out = json.loads(team(["ask", "--seats", seats, "--progress", prog, "-"], env, "вопрос").stdout)
    assert not out["ok"] and out["дальше"]["путь"] == "веб" and out["запас"][-1]["путь"] == "claude", out
    # codex's limit time passes -> it is back at the head of the route
    data = json.load(open(seats, encoding="utf-8"))
    for s in data["помощники"]:
        if s["программа"] == "codex":
            s["до"] = (datetime.datetime.now() - datetime.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
    json.dump(data, open(seats, "w", encoding="utf-8"), ensure_ascii=False)
    fake(bindir, "codex", 'echo "снова тут"')
    out = json.loads(team(["ask", "--seats", seats, "-"], env, "вопрос").stdout)
    assert out["ok"] and out["программа"] == "codex", out
    used = team(["used", "--seats", seats], env).stdout
    assert "ключ:groq" in used and "cli:codex" in used, used
    # the key value is never written to seats.json
    assert "free-test-key" not in open(seats, encoding="utf-8").read()


def test_reset_time_parsing():
    sys.path.insert(0, S)
    import team as T
    base = datetime.datetime(2026, 9, 30, 23, 0)
    assert T.reset_time("resets at 3am", base).strftime("%d %H:%M") == "01 03:00"
    assert T.reset_time("Try again at 14:30", base).strftime("%H:%M") == "14:30"
    assert T.reset_time("limit, resets in 2h 15m", base).strftime("%H:%M") == "01:15"
    assert T.reset_time("You are out of credits", base) is None


def test_night_begin_arm_hook_end():
    home = tempfile.mkdtemp()
    folder = os.path.join(tempfile.mkdtemp(), "ночь")
    env = {"NIGHTCALL_HOME": home}
    night = [sys.executable, os.path.join(S, "night.py")]
    hook = [sys.executable, os.path.join(ROOT, "hooks", "stop.py")]
    r = run(night + ["begin", "--dir", folder, "--hours", "1"], env, "сделай отчёт")
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
    # a folder that is not code and not under git: git init + commit «перед ночью» + tag + fence
    folder = tempfile.mkdtemp()
    open(os.path.join(folder, "заметки.txt"), "w").write("вечер")
    r = run(night + ["begin", "--dir", folder], env, "перепиши заметки")
    assert r.returncode == 0 and "точка возврата: git-тег nightcall-before-" in r.stdout, r.stdout + r.stderr
    log = run(["git", "-C", folder, "log", "--format=%s"]).stdout
    assert "nightcall: перед ночью" in log and "nightcall: забор на ночь" in log, log
    tag = run(["git", "-C", folder, "tag", "--list", "nightcall-before-*"]).stdout.split()[0]
    files = run(["git", "-c", "core.quotepath=false", "-C", folder, "ls-tree", "--name-only", tag]).stdout
    assert "заметки.txt" in files, files
    fence = open(os.path.join(folder, "CLAUDE.md"), encoding="utf-8").read()
    assert "nightcall:fence" in fence and "ТОЛЬКО внутри этой папки" in fence and folder in fence
    assert "reset --hard " + tag in fence
    # a git folder with the person's own CLAUDE.md: kept, uncommitted work committed, fence replaced not doubled
    open(os.path.join(folder, "CLAUDE.md"), "w").write("# Мои правила\n")
    open(os.path.join(folder, "новое.txt"), "w").write("не закоммичено")
    run(night + ["begin", "--dir", folder], env, "")
    text = open(os.path.join(folder, "CLAUDE.md"), encoding="utf-8").read()
    assert text.startswith("# Мои правила") and text.count("nightcall:fence") == 1, text
    assert run(["git", "-C", folder, "status", "--porcelain"]).stdout.strip() == ""
    # ready shows the restore point
    r = run([sys.executable, os.path.join(S, "ready.py"), "--dir", folder], env)
    assert "Точка возврата: есть" in r.stdout and "Забор (13A): есть" in r.stdout, r.stdout
    fresh = tempfile.mkdtemp()
    r = run([sys.executable, os.path.join(S, "ready.py"), "--dir", fresh], env)
    assert "Точка возврата: будет создана" in r.stdout and "Забор (13A): будет вписан" in r.stdout, r.stdout


def test_hook_bound_to_the_session_that_armed_the_night():
    home = tempfile.mkdtemp()
    folder = os.path.join(tempfile.mkdtemp(), "ночь")
    env = {"NIGHTCALL_HOME": home}
    night = [sys.executable, os.path.join(S, "night.py")]
    hook = [sys.executable, os.path.join(ROOT, "hooks", "stop.py")]
    run(night + ["begin", "--dir", folder], env, "задача")
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
    team(["web-mark", "--seats", seats, "--site", "chatgpt", "--status", "жив"], env)
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert route[0]["путь"] == "веб"          # default: web chats are the night reserve
    assert json.load(open(seats, encoding="utf-8")).get("веб_когда", "night") == "night"
    team(["web-when", "--seats", seats, "morning"], env)
    route = json.loads(team(["next", "--seats", seats], env).stdout)
    assert [x["путь"] for x in route] == ["claude"], route
    out = json.loads(team(["ask", "--seats", seats, "--dir", d, "-"], env, "Чего не хватает в плане?").stdout)
    assert out["утро_совет"] == os.path.join(d, "утро-совет.md") and out["дальше"]["путь"] == "claude"
    assert "Чего не хватает в плане?" in open(out["утро_совет"], encoding="utf-8").read()
    # the choice survives the next roll call
    team(["rollcall", "--out", seats], env)
    assert json.load(open(seats, encoding="utf-8"))["веб_когда"] == "morning"
    assert "(утром)" in team(["summary", "--seats", seats], env).stdout


def test_morning_template_puts_the_decision_first():
    text = open(os.path.join(ROOT, "skills", "morning", "SKILL.md"), encoding="utf-8").read()
    heads = [h for h in ("## Нужно Ваше решение", "## Сделано", "## Не сделано", "## Проверить", "## Кто участвовал")]
    pos = [text.index(h) for h in heads]
    assert pos == sorted(pos), pos
    loop = open(os.path.join(S, "night-loop.sh"), encoding="utf-8").read()
    assert "«Нужно Ваше решение»" in loop and "веб_когда" in loop and "night.py\" begin" in loop


def test_ready_runs():
    r = run([sys.executable, os.path.join(S, "ready.py")], {"NIGHTCALL_HOME": tempfile.mkdtemp()})
    assert "Перед ночью" in r.stdout and "Итого" in r.stdout, r.stdout + r.stderr


def test_manifest_and_skills():
    m = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    assert m["name"] == "nightcall"
    for s in ("start", "awake", "team", "ready", "morning"):
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
