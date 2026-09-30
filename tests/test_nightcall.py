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
    assert st == {"codex": "кончился запас", "grok": "кончился запас",
                  "qwen": "не вошли", "kimi": "жив"}, st
    # ask codex first: without seats it fails and kimi answers instead
    fake(bindir, "kimi", 'env | grep -q OPENAI_API_KEY && echo LEAK || echo "ответ kimi"')
    r = run([sys.executable, os.path.join(S, "team.py"), "ask", "--who", "codex", "-"], env, "вопрос")
    out = json.loads(r.stdout)
    assert out["ok"] and out["программа"] == "kimi" and out["ответ"] == "ответ kimi", out
    assert out["не_смогли"][0]["статус"] == "кончился запас"


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
