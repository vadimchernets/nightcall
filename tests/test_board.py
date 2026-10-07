"""The night on pocketcall's board: `python3 -m pytest tests/test_board.py`.

night.py board hands each state to pocketcall's board.py when it is there (a stand-in here records
its arguments) and otherwise leaves the job file in ~/.pocketcall/board for it. The night loop
reports working at every round and done with the report at the end. Nothing reaches a phone.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_family import S, world  # noqa: E402

FAKE_BOARD = """import json, os, sys
with open(os.environ["BOARD_LOG"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
"""


def night(env, *args):
    return subprocess.run([sys.executable, os.path.join(S, "night.py"), *args], capture_output=True, text=True,
                          env=env, timeout=60)


def args_of(line):
    a = json.loads(line)
    out, i = {"cmd": a[0]}, 1
    while i < len(a):
        if i + 1 < len(a) and not a[i + 1].startswith("--"):
            out[a[i][2:]] = a[i + 1]
            i += 2
        else:
            out[a[i][2:]] = True
            i += 1
    return out


def test_without_pocketcall_the_line_waits_in_its_folder_with_the_hour_the_night_goes_on():
    env, home, bindir, root = world()
    env["NIGHTCALL_BOARD"] = os.path.join(root, "no-such-board.py")
    task = os.path.join(root, "My Book")
    os.makedirs(task)
    assert night(env, "board", "--dir", task, "--state", "limit", "--rest", "600", "--note", "resting").returncode == 0
    import glob
    found = glob.glob(os.path.join(env["POCKETCALL_HOME"], "board", "nightcall-My-Book-*.json"))
    assert len(found) == 1, found
    path = found[0]
    job = json.load(open(path))
    expect = (datetime.datetime.now() + datetime.timedelta(seconds=600)).strftime("%H:%M")
    assert (job["name"], job["where"], job["state"], job["note"]) == ("night run: My Book", "nightcall", "limit", "resting")
    assert job["until"] in (expect, (datetime.datetime.now() + datetime.timedelta(seconds=540)).strftime("%H:%M"))
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_off_leaves_the_board_alone():
    env, home, bindir, root = world()
    assert night(env, "board", "--dir", root, "--state", "done").returncode == 0
    assert not os.path.exists(os.path.join(env["POCKETCALL_HOME"], "board"))


def test_the_night_loop_reports_each_round_and_the_report_at_the_end():
    env, home, bindir, root = world()
    open(os.path.join(env["FAKE_DEFAULT_CFG"], "email"), "w").write("me@x.com")
    fake = os.path.join(root, "board.py")
    open(fake, "w").write(FAKE_BOARD)
    env.update({"NIGHTCALL_BOARD": fake, "BOARD_LOG": os.path.join(root, "board.log"),
                "NIGHTCALL_LIMIT_WAIT": "2", "NIGHTCALL_MAX_ROUNDS": "6", "NIGHTCALL_FAMILY": "off"})
    scripts = os.path.join(root, "scripts")
    shutil.copytree(S, scripts)
    open(os.path.join(scripts, "awake.sh"), "w").write("#!/usr/bin/env bash\necho awake-stub\n")
    task = os.path.join(root, "task")
    os.makedirs(task)
    open(os.path.join(task, "PLAN.md"), "w").write("# Plan\n| 1 | step | done | waiting |\n")
    r = subprocess.run(["bash", os.path.join(scripts, "night-loop.sh"), task, "1"], capture_output=True,
                       text=True, env=env, timeout=120)
    calls = [args_of(x) for x in open(env["BOARD_LOG"]).read().splitlines()]
    assert calls, r.stdout + r.stderr
    assert all(c["cmd"] == "put" and c["id"].startswith("nightcall-task-") and c["where"] == "nightcall"
               for c in calls)
    assert all(c.get("ring") is True and c["folder"] == task and "night-loop.sh" in c["resume"] for c in calls)
    states = [c["state"] for c in calls]
    assert states[0] == "working" and calls[0]["note"].startswith("until ")
    assert [c["note"] for c in calls[1:4]] == ["round 1", "round 2", "round 3"]
    assert states[-1] == "done" and "MORNING.md is ready" in calls[-1]["note"] and task in calls[-1]["note"]


def test_a_night_without_a_report_ends_as_stopped():
    env, home, bindir, root = world()
    env.update({"NIGHTCALL_BOARD": os.path.join(root, "absent.py"), "NIGHTCALL_FAMILY": "off"})
    scripts = os.path.join(root, "scripts")
    shutil.copytree(S, scripts)
    open(os.path.join(scripts, "awake.sh"), "w").write("#!/usr/bin/env bash\necho awake-stub\n")
    task = os.path.join(root, "task")
    os.makedirs(task)
    open(os.path.join(task, "PLAN.md"), "w").write("# Plan\n")
    open(os.path.join(task, "STOP"), "w").write("")
    # the closing step writes no MORNING.md (the fake claude has no sign-in here and says nothing)
    subprocess.run(["bash", os.path.join(scripts, "night-loop.sh"), task, "1"], capture_output=True, text=True,
                   env=env, timeout=120)
    import glob
    job = json.load(open(glob.glob(os.path.join(env["POCKETCALL_HOME"], "board", "nightcall-task-*.json"))[0]))
    assert job["state"] == "failed" and "stopped by the STOP file" in job["note"], job


def test_two_nights_in_folders_of_the_same_name_are_two_lines():
    env, home, bindir, root = world()
    env["NIGHTCALL_BOARD"] = os.path.join(root, "absent.py")
    for side in ("a", "b"):
        os.makedirs(os.path.join(root, side, "book"))
        night(env, "board", "--dir", os.path.join(root, side, "book"), "--state", "working")
    assert len(os.listdir(os.path.join(env["POCKETCALL_HOME"], "board"))) == 2


def test_a_killed_loop_says_so_on_the_board():
    import signal
    import time
    env, home, bindir, root = world()
    env.update({"NIGHTCALL_BOARD": os.path.join(root, "absent.py"), "NIGHTCALL_FAMILY": "off"})
    open(os.path.join(env["FAKE_DEFAULT_CFG"], "email"), "w").write("me@x.com")
    open(os.path.join(env["FAKE_DEFAULT_CFG"], "limited"), "w").write("1")     # every round rests on a limit
    env["NIGHTCALL_LIMIT_WAIT"] = "30"
    scripts = os.path.join(root, "scripts")
    shutil.copytree(S, scripts)
    open(os.path.join(scripts, "awake.sh"), "w").write("#!/usr/bin/env bash\necho awake-stub\n")
    task = os.path.join(root, "task")
    os.makedirs(task)
    open(os.path.join(task, "PLAN.md"), "w").write("# Plan\n")
    p = subprocess.Popen(["bash", os.path.join(scripts, "night-loop.sh"), task, "1"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import glob
    pattern = os.path.join(env["POCKETCALL_HOME"], "board", "nightcall-task-*.json")
    for _ in range(100):
        found = glob.glob(pattern)
        if found and json.load(open(found[0]))["state"] == "limit":
            break
        time.sleep(0.1)
    assert json.load(open(found[0]))["state"] == "limit"
    p.send_signal(signal.SIGTERM)
    time.sleep(0.5)        # bash runs the trap once its foreground sleep ends; give it the signal there too
    subprocess.run(["pkill", "-TERM", "-P", str(p.pid)], check=False)
    p.wait(timeout=40)
    assert json.load(open(found[0]))["state"] == "failed"
