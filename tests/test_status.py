"""The transparent night: `python3 -m pytest tests/test_status.py`.

The ledger (what the AI wanted - what the person decided), the status card (state, last action, checks,
what waits, stop/continue) and the card on pocketcall's board. Everything runs in temp folders; a
stand-in board.py records its arguments, nothing reaches a phone.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_family import S  # noqa: E402

sys.path.insert(0, S)
import ledger  # noqa: E402
import status  # noqa: E402

FAKE_BOARD = """import json, os, sys
with open(os.environ["BOARD_LOG"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
"""

PLAN = """# Plan for the night

| # | Step | Done when | Status |
|---|------|-----------|--------|
| 1 | build the page | page opens | done |
| 2 | add tests | tests pass | done |
| 3 | ship it | deployed | waiting |
"""

PROGRESS = """# Night progress

## Journal
<!-- after each step -->
- 23:10 · step 1 · built the page · checked: opened it
- 01:40 · step 2 · tests added · checked: 12 pass

## Check in the morning
- chose the blue header
"""


def night_folder():
    folder = tempfile.mkdtemp()
    open(os.path.join(folder, "PLAN.md"), "w").write(PLAN)
    open(os.path.join(folder, "PROGRESS.md"), "w").write(PROGRESS)
    return folder


def env_for(home, **extra):
    env = dict(os.environ, NIGHTCALL_HOME=home, NIGHTCALL_BOARD="off", POCKETCALL_HOME=os.path.join(home, "pc"))
    env.update(extra)
    return env


def tool(name, env, *args):
    return subprocess.run([sys.executable, os.path.join(S, name), *args], capture_output=True, text=True, env=env,
                          timeout=60)


def arm(home, folder, minutes=60):
    until = time.strftime("%Y-%m-%dT%H:%M", time.localtime(time.time() + minutes * 60))
    with open(os.path.join(home, "active.json"), "w") as fh:
        json.dump({"folder": folder, "until": until, "rounds": 4, "session": "A"}, fh)


def test_ledger_want_decide_history():
    folder = tempfile.mkdtemp()
    first = ledger.want(folder, "send the invoice to the client", why="step 6", default="saved as a draft")
    second = ledger.want(folder, "delete the old backups")
    assert (first, second) == (1, 2)
    assert [w["verdict"] for w in ledger.read(folder)] == ["pending", "pending"]
    assert ledger.decide(folder, 1, "approved", note="ok, send")
    assert ledger.decide(folder, 2, "declined")
    assert not ledger.decide(folder, 9, "approved")           # no such want
    assert not ledger.decide(folder, 1, "maybe")              # not a verdict
    rows = ledger.read(folder)
    assert [w["verdict"] for w in rows] == ["approved", "declined"]
    assert rows[0]["default"] == "saved as a draft" and rows[0]["note"] == "ok, send"
    assert ledger.pending(folder) == []
    # the history stays: two wants and two decisions are four lines, the AI's words are never rewritten
    assert len(open(ledger.path_of(folder)).read().splitlines()) == 4
    text = ledger.render(rows)
    assert "approved" in text and "declined" in text and "meanwhile: saved as a draft" in text


def test_ledger_survives_a_torn_line_and_cli():
    folder = tempfile.mkdtemp()
    env = env_for(tempfile.mkdtemp())
    r = tool("ledger.py", env, "want", "--dir", folder, "--what", "buy the domain", "--why", "site needs it")
    assert json.loads(r.stdout)["id"] == 1
    with open(ledger.path_of(folder), "a") as fh:
        fh.write("{broken\n")
    assert tool("ledger.py", env, "pending", "--dir", folder).stdout.strip() == "1"
    assert "WAITS FOR YOU" in tool("ledger.py", env, "show", "--dir", folder).stdout
    assert tool("ledger.py", env, "decide", "--dir", folder, "--id", "1", "--verdict", "approved").returncode == 0
    assert tool("ledger.py", env, "decide", "--dir", folder, "--id", "7", "--verdict", "approved").returncode == 1
    assert tool("ledger.py", env, "pending", "--dir", folder).stdout.strip() == "0"


def test_card_of_a_running_night():
    home, folder = tempfile.mkdtemp(), night_folder()
    arm(home, folder)
    status.HOME = home
    ledger.want(folder, "publish the site", default="built, not published")
    c = status.card(folder)
    assert c["state"] == "working" and c["round"] == 4 and c["can_stop"] and not c["can_continue"]
    assert (c["steps_done"], c["steps_total"]) == (2, 3)
    assert c["last"].startswith("01:40") and "12 pass" in c["last"]
    assert [w["what"] for w in c["waits"]] == ["publish the site"] and c["held"] == 1
    line = status.summary(c)
    assert "steps 2/3" in line and "waits for you: 1" in line and "last: 01:40" in line
    text = status.render(c)
    assert "WORKING" in text and "Waits for you (1)" in text and "Stop:" in text


def test_card_states_and_empty_skeleton():
    home, folder = tempfile.mkdtemp(), tempfile.mkdtemp()
    status.HOME = home
    assert status.card(folder)["state"] == "none"
    skeleton = "| # | Step | Done when | Status |\n|---|---|---|---|\n| 1 |     |      | waiting |\n"
    open(os.path.join(folder, "PLAN.md"), "w").write(skeleton)
    c = status.card(folder)
    assert c["state"] == "idle" and c["steps_total"] == 0 and c["can_continue"]
    open(os.path.join(folder, "STOP"), "w").close()
    assert status.card(folder)["state"] == "stopped"
    open(os.path.join(folder, "MORNING.md"), "w").close()
    assert status.card(folder)["state"] == "done"


def test_stop_and_continue_from_the_cli():
    home, folder = tempfile.mkdtemp(), night_folder()
    env = env_for(home)
    arm(home, folder)
    r = tool("status.py", env, "stop", "--dir", folder)
    assert r.returncode == 0 and os.path.exists(os.path.join(folder, "STOP"))
    assert "STOPPED" in tool("status.py", env, "show", "--dir", folder).stdout
    r = tool("status.py", env, "continue", "--dir", folder)
    assert not os.path.exists(os.path.join(folder, "STOP")) and "goes on" in r.stdout
    assert "WORKING" in tool("status.py", env, "show", "--dir", folder).stdout
    open(os.path.join(folder, "MORNING.md"), "w").close()
    assert tool("status.py", env, "continue", "--dir", folder).returncode == 1     # the night is over
    assert tool("status.py", env, "show", "--dir", "/no/such/folder").returncode == 1


def test_show_uses_the_night_that_is_on_without_dir():
    home, folder = tempfile.mkdtemp(), night_folder()
    arm(home, folder)
    out = tool("status.py", env_for(home), "show", "--json")
    assert json.loads(out.stdout)["folder"] == os.path.abspath(folder)


def test_push_hands_the_card_to_the_board():
    home, folder = tempfile.mkdtemp(), night_folder()
    arm(home, folder)
    ledger.want(folder, "send the report to the client")
    fake = os.path.join(home, "board.py")
    open(fake, "w").write(FAKE_BOARD)
    log = os.path.join(home, "board.log")
    env = env_for(home, NIGHTCALL_BOARD=fake, BOARD_LOG=log)
    assert tool("status.py", env, "push", "--dir", folder).returncode == 0
    line = json.loads(open(log).read().splitlines()[-1])
    assert line[0] == "put" and "--state" in line and line[line.index("--state") + 1] == "working"
    assert "--steps=2/3" in line and "--waits=1" in line
    assert any(x.startswith("--last=01:40") for x in line)
    assert line[line.index("--folder") + 1] == os.path.abspath(folder)
    # a stopped night shows on the board as stopped
    open(os.path.join(folder, "STOP"), "w").close()
    tool("status.py", env, "push", "--dir", folder)
    again = json.loads(open(log).read().splitlines()[-1])
    assert again[again.index("--state") + 1] == "failed"


def test_stop_hook_pushes_the_card_each_round():
    home, folder = tempfile.mkdtemp(), night_folder()
    arm(home, folder)
    fake = os.path.join(home, "board.py")
    open(fake, "w").write(FAKE_BOARD)
    log = os.path.join(home, "board.log")
    env = env_for(home, NIGHTCALL_BOARD=fake, BOARD_LOG=log)
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(S), "hooks", "stop.py")], input='{"session_id":"A"}',
                       capture_output=True, text=True, env=env, timeout=60)
    assert '"block"' in r.stdout
    for _ in range(50):                      # the push runs in a process of its own
        if os.path.exists(log):
            break
        time.sleep(0.1)
    assert "--steps=2/3" in json.loads(open(log).read().splitlines()[-1])


def test_council_decisions_and_holds_land_in_the_ledger():
    home, folder = tempfile.mkdtemp(), tempfile.mkdtemp()
    env = env_for(home)
    team = os.path.join(S, "team.py")
    r = subprocess.run([sys.executable, team, "decide", "--dir", folder, "--what", "use postgres", "--why", "fits",
                        "--who", "codex", "--commit", "abc123"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, team, "hold", "--dir", folder, "--question", "pay for the domain?",
                        "--waits", "step 5"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    rows = ledger.read(folder)
    assert [w["what"] for w in rows] == ["the council decided: use postgres", "pay for the domain?"]
    assert "git revert abc123" in rows[0]["default"] and rows[1]["default"] == "on hold: step 5"
    assert all(w["verdict"] == "pending" for w in rows)
