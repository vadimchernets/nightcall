"""The checklist: the person's words line for line, closed only with artifacts that are really there.
`python3 -m pytest tests/test_checklist.py`

A fake `claude` on PATH plays a lazy night: it writes MORNING.md after one step with items still open. The loop
must go on; the morning must start with "Not done"; a rewritten item, a fake commit, a file that is not there
and a test that never ran must not count.
"""
import json
import os
import stat
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_family import S, world  # noqa: E402

TASK = """# TASK

## What we build (the person's words, as dictated)
- A landing page for the bakery with today's bread.
- An order form that sends me an e-mail.
- The site must open fast on a phone.

## Never without the person
- publishing
"""


def chk(env, *args, inp=None):
    return subprocess.run([sys.executable, os.path.join(S, "checklist.py"), *args], capture_output=True, text=True,
                          env=env, input=inp, timeout=60)


def task_folder(root, git=True):
    task = os.path.join(root, "task")
    os.makedirs(task)
    open(os.path.join(task, "TASK.md"), "w").write(TASK)
    open(os.path.join(task, "PLAN.md"), "w").write("# Plan\n")
    if git:
        for a in (["init", "-q"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base"]):
            subprocess.run(["git", *a], cwd=task, check=True)
    return task


def items(task):
    return json.load(open(os.path.join(task, "checklist.json")))["items"]


def test_items_are_the_person_s_words_verbatim_and_not_the_forbidden_list():
    env, home, bindir, root = world()
    task = task_folder(root)
    assert chk(env, "make", "--dir", task).returncode == 0
    assert [i["words"] for i in items(task)] == ["A landing page for the bakery with today's bread.",
                                                 "An order form that sends me an e-mail.",
                                                 "The site must open fast on a phone."]
    assert all(i["state"] == "open" for i in items(task))
    assert os.path.exists(os.path.join(home, "checklists"))      # the words are kept outside the folder too


def test_a_rewritten_item_is_seen():
    env, home, bindir, root = world()
    task = task_folder(root)
    chk(env, "make", "--dir", task)
    data = json.load(open(os.path.join(task, "checklist.json")))
    data["items"][2]["words"] = "The site opens."
    data["items"][2]["state"] = "done"
    json.dump(data, open(os.path.join(task, "checklist.json"), "w"))
    r = chk(env, "verify", "--dir", task)
    assert r.returncode == 1 and 'the person said "The site must open fast on a phone."' in r.stdout


def test_a_fake_commit_a_missing_file_and_a_test_that_never_ran_do_not_close_an_item():
    env, home, bindir, root = world()
    task = task_folder(root)
    chk(env, "make", "--dir", task)
    for ev in ("deadbeef1234", "index.html", "PROGRESS.md", "night-loop.log", "test:bakery page renders"):
        assert chk(env, "close", "--dir", task, "--n", "1", "--evidence", ev).returncode == 1, ev
    open(os.path.join(task, "night-loop.log"), "w").write("ok test:bakery page renders\n")   # the agent's own words
    assert chk(env, "close", "--dir", task, "--n", "1", "--evidence", "test:bakery page renders").returncode == 1
    assert items(task)[0]["state"] == "open"


def test_a_real_file_commit_and_test_run_close_items():
    env, home, bindir, root = world()
    task = task_folder(root)
    chk(env, "make", "--dir", task)
    open(os.path.join(task, "index.html"), "w").write("<h1>Bread</h1>")
    assert chk(env, "close", "--dir", task, "--n", "1", "--evidence", "index.html").returncode == 0
    subprocess.run(["git", "add", "-A"], cwd=task, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "form"], cwd=task, check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=task, capture_output=True, text=True).stdout.strip()
    assert chk(env, "close", "--dir", task, "--n", "2", "--evidence", sha[:10]).returncode == 0
    r = chk(env, "test", "--dir", task, "--", sys.executable, "-c", "print('ok - phone loads in 0.8 s')")
    assert r.returncode == 0
    assert chk(env, "close", "--dir", task, "--n", "3", "--evidence", "test:phone loads in 0.8 s").returncode == 0
    assert chk(env, "status", "--dir", task).returncode == 0
    # a test log edited afterwards no longer counts
    log = [os.path.join(dp, f) for dp, _, fs in os.walk(os.path.join(task, ".nightcall")) for f in fs][0]
    open(log, "a").write("\nphone loads in 0.1 s\n")
    assert chk(env, "close", "--dir", task, "--n", "3", "--evidence", "test:phone loads in 0.1 s").returncode == 1


def test_the_morning_starts_with_not_done_and_marks_words_only():
    env, home, bindir, root = world()
    env["NIGHTCALL_LANG"] = "en"
    task = task_folder(root)
    chk(env, "make", "--dir", task)
    open(os.path.join(task, "index.html"), "w").write("x")
    chk(env, "close", "--dir", task, "--n", "1", "--evidence", "index.html")
    chk(env, "defer", "--dir", task, "--n", "2", "--why", "no mail server yet")
    os.remove(os.path.join(task, "index.html"))                # "done", but the artifact is gone: words only
    open(os.path.join(task, "MORNING.md"), "w").write("# Morning: bakery\n\n## Done\n- everything\n")
    assert chk(env, "morning", "--dir", task).returncode == 0
    text = open(os.path.join(task, "MORNING.md")).read()
    assert text.split("\n")[2] == "## Not done"
    assert "[1] A landing page for the bakery with today's bread. — words only" in text
    assert "[2] An order form that sends me an e-mail. — deferred: no mail server yet" in text
    assert "[3] The site must open fast on a phone." in text
    assert text.index("## Not done") < text.index("## Done")


def test_the_cold_check_is_one_outside_reviewer():
    env, home, bindir, root = world()
    task = task_folder(root)
    env["NIGHTCALL_COLD_CMD"] = "cat"                         # stands in for diffcall: echoes the question
    chk(env, "cold", "--dir", task)
    text = open(os.path.join(task, "cold-check.md")).read()
    assert "what was LOST" in text and "HALF-DONE" in text


LAZY = r"""#!/bin/bash
if [ "$1" = -p ]; then
  if printf '%s' "$2" | grep -q "night on the nightcall plugin is over"; then
    printf '# Morning\n\n## Done\n- all done\n' > MORNING.md; exit 0
  fi
  n=$(( $(cat rounds 2>/dev/null || echo 0) + 1 )); echo $n > rounds
  printf '# Morning\n\n## Done\n- all done, trust me\n' > MORNING.md      # claims the end after every step
  if [ "$n" = 2 ]; then echo "<h1>Bread</h1>" > index.html; python3 "$CHK" close --dir . --n 1 --evidence index.html >/dev/null; fi
  echo "step $n"
fi
"""


def test_a_lazy_night_with_an_open_item_goes_on_and_the_morning_starts_with_not_done():
    env, home, bindir, root = world()
    env.update({"NIGHTCALL_FAMILY": "off", "NIGHTCALL_MINE": "off", "NIGHTCALL_MAX_ROUNDS": "4", "NIGHTCALL_LANG": "en",
                "CHK": os.path.join(root, "scripts", "checklist.py"), "NIGHTCALL_COLD_CMD": "echo nothing lost"})
    lazy = os.path.join(bindir, "claude")
    open(lazy, "w").write(LAZY)
    os.chmod(lazy, os.stat(lazy).st_mode | stat.S_IEXEC)
    import shutil
    scripts = os.path.join(root, "scripts")
    shutil.copytree(S, scripts)
    open(os.path.join(scripts, "awake.sh"), "w").write("#!/usr/bin/env bash\necho awake-stub\n")
    task = task_folder(root, git=False)
    r = subprocess.run(["bash", os.path.join(scripts, "night-loop.sh"), task, "1"], capture_output=True, text=True,
                       env=env, timeout=120)
    log = open(os.path.join(task, "night-loop.log")).read()
    assert open(os.path.join(task, "rounds")).read().strip() == "4", log     # MORNING.md after step 1 did not end it
    assert "the night goes on" in log
    text = open(os.path.join(task, "MORNING.md")).read()
    assert text.split("\n")[2] == "## Not done", text
    assert "[2] An order form that sends me an e-mail." in text and "[3] The site must open fast" in text
    assert "confirmed by an artifact (file: index.html)" in text
    assert "nothing lost" in text
