"""My subscriptions: `python3 -m pytest tests/test_mine.py`.

One person's own Claude -> Codex -> Gemini CLI carry the night in turn. Fake `claude`, `codex` and
`gemini` on PATH write each round into rounds.txt (or say "hit your limit" when a marker file says
so); the fake `codex app-server` answers account/rateLimits/read. Nothing reaches a real account.
"""
import datetime
import json
import os
import shutil
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_family import S, world  # noqa: E402

FAKE = r"""#!/bin/bash
me=$(basename "$0")
if [ "$me" = codex ] && [ "$1" = app-server ]; then
  # like the real app-server: it answers only while its stdin is still open - at EOF it exits without a word
  while read -r line; do
    case "$line" in
      *'"id": 1'*) echo '{"jsonrpc":"2.0","id":1,"result":{}}';;
      *'"id": 2'*)
        python3 -c "import os, select, sys; r = select.select([0], [], [], 0.5)[0]; sys.exit(1 if r and os.read(0, 1) == b'' else 0)" || exit 0
        echo "{\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"rateLimits\":{\"primary\":{\"usedPercent\":${CODEX_USED:-20},\"windowDurationMins\":300,\"resetsAt\":$(( $(date +%s) + 3600 ))},\"secondary\":{\"usedPercent\":5,\"windowDurationMins\":10080}}}}"; exit 0;;
    esac
  done
  exit 0
fi
if [ "$me" = gemini ] && [ -f "$MARKS/gemini-quota" ]; then
  echo "Error: [API Error: {\"error\":{\"code\":429,\"message\":\"Quota exceeded for quota metric 'Gemini 2.5 Pro Requests'\",\"status\":\"RESOURCE_EXHAUSTED\"}}]"; exit 1
fi
case " $* " in *" --full-auto "*) echo "error: unexpected argument '--full-auto' found" >&2; exit 2;; esac
if [ -f "$MARKS/$me-limited" ]; then echo "You've hit your usage limit - resets 3am"; exit 1; fi
echo "round by $me" >> rounds.txt
n=$(wc -l < rounds.txt | tr -d ' ')
if [ "$n" -ge "${ROUNDS:-3}" ]; then echo done > MORNING.md; fi
echo "step done"
"""


def setup():
    env, home, bindir, root = world()
    marks = os.path.join(root, "marks")
    os.makedirs(marks)
    for name in ("claude", "codex", "gemini"):
        path = os.path.join(bindir, name)
        open(path, "w").write(FAKE)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    env.update({"MARKS": marks, "NIGHTCALL_FAMILY": "off", "NIGHTCALL_LIMIT_WAIT": "2", "NIGHTCALL_LANG": "en"})
    return env, home, root, marks


def mine(env, *args, inp=None):
    return subprocess.run([sys.executable, os.path.join(S, "mine.py"), *args], capture_output=True, text=True,
                          env=env, input=inp, timeout=60)


def loop(env, root, rounds=3):
    scripts = os.path.join(root, "scripts")
    if not os.path.exists(scripts):
        shutil.copytree(S, scripts)
        open(os.path.join(scripts, "awake.sh"), "w").write("#!/usr/bin/env bash\necho awake-stub\n")
    task = os.path.join(root, "task")
    os.makedirs(task, exist_ok=True)
    for f in ("MORNING.md", "rounds.txt"):
        if os.path.exists(os.path.join(task, f)):
            os.unlink(os.path.join(task, f))
    open(os.path.join(task, "PLAN.md"), "w").write("# Plan\n| 1 | step | done | waiting |\n")
    env = dict(env, ROUNDS=str(rounds))
    r = subprocess.run(["bash", os.path.join(scripts, "night-loop.sh"), task, "1"], capture_output=True,
                       text=True, env=env, timeout=120)
    return task, r


def rounds(task):
    return open(os.path.join(task, "rounds.txt")).read().split("\n")[:-1]


def test_on_sets_the_order_and_status_shows_it():
    env, home, root, marks = setup()
    r = mine(env, "on", "--order", "claude,codex,gemini", "--below", "15")
    assert r.returncode == 0, r.stdout
    assert "Claude -> Codex -> Gemini" in r.stdout
    data = json.load(open(os.path.join(home, "mine.json")))
    assert data["order"] == ["claude", "codex", "gemini"] and data["below"] == 15
    assert oct(os.stat(os.path.join(home, "mine.json")).st_mode & 0o777) == "0o600"
    assert mine(env, "status", "--quiet").returncode == 0
    assert mine(env, "off").returncode == 0
    assert mine(env, "status", "--quiet").returncode == 1
    assert mine(env, "on", "--order", "claude,grok").returncode == 2


def test_claude_limit_hands_the_night_to_my_codex_with_the_same_files():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on")
    open(os.path.join(marks, "claude-limited"), "w").write("1")
    task, r = loop(env, root)
    assert rounds(task) == ["round by codex"] * 3, r.stdout + r.stderr
    progress = open(os.path.join(task, "PROGRESS.md")).read()
    assert "## Relay" in progress and "Claude: limit, back at 03:00 -> Codex carries the work on" in progress
    data = json.load(open(os.path.join(home, "mine.json")))
    assert data["resting"]["claude"].endswith("03:00")


def test_codex_spent_too_then_gemini_carries_on():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on")
    for m in ("claude", "codex"):
        open(os.path.join(marks, m + "-limited"), "w").write("1")
    task, r = loop(env, root)
    assert rounds(task) == ["round by gemini"] * 3, r.stdout + r.stderr
    assert "-> Gemini carries the work on" in open(os.path.join(task, "PROGRESS.md")).read()


def test_the_work_comes_back_to_claude_when_its_limit_is_over():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on")
    data = json.load(open(os.path.join(home, "mine.json")))
    past = (datetime.datetime.now() - datetime.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
    data["resting"] = {"claude": past}
    json.dump(data, open(os.path.join(home, "mine.json"), "w"))
    assert mine(env, "pick", "--after", "codex").stdout.strip() == "claude"
    task = os.path.join(root, "t")
    os.makedirs(task)
    r = mine(env, "relay", "--folder", task, "--from", "codex", "--to", "claude")
    assert "Claude is back -> Claude carries the work on" in r.stdout


def test_a_nearly_spent_claude_hands_over_before_the_limit_cuts_a_step():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on", "--below", "10")
    reset = int(time.time()) + 2 * 3600
    payload = {"model": {"id": "x"}, "rate_limits": {"five_hour": {"used_percentage": 96, "resets_at": reset},
                                                     "seven_day": {"used_percentage": 40}}}
    r = mine(env, "capture", inp=json.dumps(payload))
    assert r.stdout.startswith("Claude 4% left (5h), resets ")
    cache = json.load(open(os.path.join(home, "quota", "claude.json")))
    assert "model" not in json.dumps(cache)       # only numbers are kept
    task, r = loop(env, root)
    assert rounds(task) == ["round by codex"] * 3, r.stdout + r.stderr
    progress = open(os.path.join(task, "PROGRESS.md")).read()
    back = datetime.datetime.fromtimestamp(reset).strftime("%H:%M")
    assert f"Claude: 4% left, back at {back} -> Codex" in progress


def test_a_stale_claude_reading_is_not_used():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on")
    os.makedirs(os.path.join(home, "quota"))
    json.dump({"at": time.time() - 3600, "windows": [{"type": "5h", "left": 2, "resets": None}]},
              open(os.path.join(home, "quota", "claude.json"), "w"))
    assert mine(env, "pick").stdout.strip() == "claude"


def test_codex_left_is_read_live_from_its_app_server_and_the_meter_shows_it():
    env, home, root, marks = setup()
    env["CODEX_USED"] = "56"
    mine(env, "on", "--order", "codex,gemini")
    r = mine(env, "meter")
    assert r.stdout.strip() == "Codex 44% · Gemini ?", r.stdout + r.stderr
    rows = json.loads(mine(env, "meter", "--json").stdout)
    assert rows[0]["window"] == "5h" and rows[0]["left"] == 44
    env["CODEX_USED"] = "95"
    assert mine(env, "pick").stdout.strip() == "gemini"


def test_the_board_hears_the_switch_and_the_meter():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    board = os.path.join(root, "board.py")
    open(board, "w").write("import json, os, sys\nopen(os.environ['BOARD_LOG'], 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
    env.update({"NIGHTCALL_BOARD": board, "BOARD_LOG": os.path.join(root, "board.log")})
    mine(env, "on")
    open(os.path.join(marks, "claude-limited"), "w").write("1")
    loop(env, root)
    lines = [json.loads(x) for x in open(env["BOARD_LOG"]).read().splitlines()]
    said = [x for x in lines if "--say" in x]
    assert said and "switched to Codex - the work goes on" in said[0][said[0].index("--note") + 1], json.dumps(said)
    meters = [x[x.index("--meter") + 1] for x in lines if "--meter" in x]
    assert any("Claude rests until 03:00" in m for m in meters), meters


def test_the_family_takes_precedence_and_off_means_claude_only():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on")
    env["NIGHTCALL_MINE"] = "off"
    task, r = loop(env, root)
    assert rounds(task) == ["round by claude"] * 3


def week_low(env, used=85):
    reset = int(time.time()) + 3 * 86400
    payload = {"rate_limits": {"five_hour": {"used_percentage": 10}, "seven_day": {"used_percentage": used, "resets_at": reset}}}
    mine(env, "capture", inp=json.dumps(payload))
    return reset


def test_the_week_s_reserve_hands_the_night_over_early_and_the_board_says_so():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    r = mine(env, "on")
    assert "keeps 20% of its week" in r.stdout
    reset = week_low(env, used=85)                  # 15% of the week left: below the 20% reserve
    task, r = loop(env, root)
    assert rounds(task) == ["round by codex"] * 3, r.stdout + r.stderr
    back = datetime.datetime.fromtimestamp(reset)
    assert f"Claude: keeps 20% of the week, back at {back:%H:%M} -> Codex" in open(os.path.join(task, "PROGRESS.md")).read()
    data = json.load(open(os.path.join(home, "mine.json")))
    assert data["resting"]["claude"] == back.strftime("%Y-%m-%d %H:%M")
    assert mine(env, "meter").stdout.startswith("Claude keeps 20% of the week, back ")


def test_above_the_reserve_and_with_reserve_zero_claude_works_on():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on")
    week_low(env, used=70)                          # 30% left: above the reserve
    assert mine(env, "pick").stdout.strip() == "claude"
    mine(env, "on", "--reserve", "0")
    week_low(env, used=95)                          # 5% of the week, reserve off: spend it
    assert mine(env, "pick").stdout.strip() == "claude"


def test_codex_is_read_with_its_stdin_open_and_answers_nothing_once_it_is_closed():
    env, home, root, marks = setup()
    mine(env, "on", "--order", "codex")
    env["CODEX_USED"] = "30"
    rows = json.loads(mine(env, "meter", "--json").stdout)
    assert rows[0]["left"] == 70 and rows[0]["window"] == "5h"
    # the old way - everything written and stdin closed at once - gets no answer from such a server
    p = subprocess.run(["codex", "app-server"], input='{"id": 1}\n{"id": 2}\n', capture_output=True, text=True, env=env)
    assert '"id":2' not in p.stdout


def test_gemini_s_quota_message_is_a_limit_and_the_night_moves_on():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on", "--order", "gemini,claude")
    open(os.path.join(marks, "gemini-quota"), "w").write("1")
    task, r = loop(env, root)
    assert rounds(task) == ["round by claude"] * 3, r.stdout + r.stderr
    assert "Gemini: limit" in open(os.path.join(task, "PROGRESS.md")).read()


def test_a_week_reading_from_the_desk_holds_all_night_until_its_reset():
    env, home, root, marks = setup()
    env["NIGHTCALL_MINE_CODEX_READ"] = "off"
    mine(env, "on")
    os.makedirs(os.path.join(home, "quota"))
    reset = time.time() + 2 * 86400
    json.dump({"at": time.time() - 10 * 3600, "windows": [{"type": "weekly", "left": 12, "resets": reset},
                                                         {"type": "5h", "left": 90, "resets": None}]},
              open(os.path.join(home, "quota", "claude.json"), "w"))
    assert mine(env, "pick").stdout.strip() == "codex"     # 10 h old, but the week only shrinks until its reset


def test_the_phone_hears_the_switch_in_its_own_language():
    env, home, root, marks = setup()
    env["NIGHTCALL_LANG"] = "ru"
    r = mine(env, "say", "switched", "--to", "codex")
    assert r.stdout.strip() == "\u043f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0438\u043b\u0441\u044f \u043d\u0430 Codex \u2014 \u0440\u0430\u0431\u043e\u0442\u0430 \u0438\u0434\u0451\u0442"
    env["NIGHTCALL_LANG"] = "en"
    assert mine(env, "say", "switched", "--to", "gemini").stdout.strip() == "switched to Gemini - the work goes on"


def test_capture_keeps_the_person_s_own_status_line():
    env, home, root, marks = setup()
    payload = {"rate_limits": {"five_hour": {"used_percentage": 50}}}
    r = mine(env, "capture", "--then", "echo my-own-line", inp=json.dumps(payload))
    assert r.stdout.splitlines()[0] == "my-own-line" and "Claude 50% left" in r.stdout
