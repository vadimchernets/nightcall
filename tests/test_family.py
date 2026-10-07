"""Family relay tests: `python3 -m pytest tests/test_family.py`.

A fake `claude` on PATH answers `auth status` from the sign-in folder it is pointed at
(CLAUDE_CONFIG_DIR, or FAKE_DEFAULT_CFG for the computer's usual sign-in) and, for `-p`, either says
"hit your limit" (a file named `limited` in that folder) or writes the round into rounds.txt.
Nothing reaches a real account.
"""
import datetime
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")

FAKE_CLAUDE = r"""#!/bin/bash
cfg=${CLAUDE_CONFIG_DIR:-$FAKE_DEFAULT_CFG}
if [ "$1" = auth ]; then
  if [ -f "$cfg/email" ]; then printf '{"loggedIn": true, "authMethod": "claude.ai", "email": "%s"}\n' "$(cat "$cfg/email")"
  else echo '{"loggedIn": false, "authMethod": "none"}'; fi
  exit 0
fi
if [ "$1" = -p ]; then
  if [ -f "$cfg/limited" ]; then echo "You've hit your limit - resets 3am"; exit 1; fi
  echo "round by $(cat "$cfg/email")" >> rounds.txt
  n=$(wc -l < rounds.txt | tr -d ' ')
  if [ "$n" -ge 3 ] && ! printf '%s' "$2" | grep -q "night on the nightcall plugin is over"; then echo done > MORNING.md; fi
  echo ok; exit 0
fi
exit 0
"""


def world():
    """A temp family home, a fake claude, and sign-in folders. Returns (env, home, bindir, root)."""
    root = tempfile.mkdtemp()
    home, bindir, dflt = (os.path.join(root, x) for x in ("home", "bin", "default-cfg"))
    for d in (home, bindir, dflt):
        os.makedirs(d)
    fake = os.path.join(bindir, "claude")
    with open(fake, "w") as fh:
        fh.write(FAKE_CLAUDE)
    os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "NIGHTCALL_FAMILY")}
    env.update({"NIGHTCALL_HOME": home, "FAKE_DEFAULT_CFG": dflt, "PATH": bindir + os.pathsep + env.get("PATH", "")})
    return env, home, bindir, root


def sign_in(folder, email, limited=False):
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, "email"), "w").write(email)
    if limited:
        open(os.path.join(folder, "limited"), "w").write("1")


def fam(env, *args, inp=None):
    return subprocess.run([sys.executable, os.path.join(S, "family.py"), *args], capture_output=True,
                          text=True, env=env, input=inp, timeout=60)


def later(hours):
    return (datetime.datetime.now() + datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")


def members(home):
    return {m["id"]: m for m in json.load(open(os.path.join(home, "family.json")))["members"]}


def test_add_owner_and_member_own_folder_v1_wording():
    env, home, _, _ = world()
    r = fam(env, "add", "--name", "Dad", "--email", "dad@x.com", "--config-dir", "default")
    assert r.returncode == 0, r.stdout + r.stderr
    r = fam(env, "add", "--name", "Son", "--email", "son@x.com")
    assert r.returncode == 0, r.stdout
    son = members(home)["son"]
    assert son["config_dir"].startswith(home) and os.path.isdir(son["config_dir"])
    assert "CLAUDE_CONFIG_DIR=" in r.stdout and "claude auth login" in r.stdout
    # V1 family wording, word for word (family-handoff.mjs DISCLOSURE.signInYourself / toSender)
    assert "Sign in as yourself in the vendor's own CLI before you continue." in r.stdout
    assert "Another person will read this task." in r.stdout
    assert members(home)["dad"]["owner"] is True and son["owner"] is False


def test_same_account_twice_and_bad_email_are_refused():
    env, home, _, _ = world()
    fam(env, "add", "--name", "Dad", "--email", "dad@x.com", "--config-dir", "default")
    r = fam(env, "add", "--name", "Dad2", "--email", "DAD@x.com")
    assert r.returncode == 2 and "Two people - two quotas." in r.stdout, r.stdout
    assert fam(env, "add", "--name", "Kid", "--email", "nope").returncode == 2
    assert set(members(home)) == {"dad"}


def test_consent_is_the_members_own_and_in_the_future():
    env, home, _, _ = world()
    fam(env, "add", "--name", "Dad", "--email", "dad@x.com", "--config-dir", "default")
    fam(env, "add", "--name", "Son", "--email", "son@x.com")
    assert fam(env, "consent", "--name", "Son", "--by", "Dad", "--until", later(48)).returncode == 2
    assert fam(env, "consent", "--name", "Son", "--by", "Son", "--until", "2020-01-01 10:00").returncode == 2
    r = fam(env, "consent", "--name", "Son", "--by", "Son", "--until", later(48))
    assert r.returncode == 0 and "YOUR OWN account" in r.stdout, r.stdout
    assert members(home)["son"]["consent"]["by"] == "Son"
    assert fam(env, "revoke", "--name", "Son").returncode == 0
    assert members(home)["son"]["consent"] is None


def test_pick_skips_no_consent_wrong_sign_in_and_rests():
    env, home, _, root = world()
    sign_in(env["FAKE_DEFAULT_CFG"], "dad@x.com")
    fam(env, "add", "--name", "Dad", "--email", "dad@x.com", "--config-dir", "default")
    for name in ("Aunt", "Son", "Niece"):
        fam(env, "add", "--name", name, "--email", name.lower() + "@x.com")
    m = members(home)
    sign_in(m["aunt"]["config_dir"], "dad@x.com")       # someone else signed in in Aunt's folder
    sign_in(m["son"]["config_dir"], "son@x.com")
    sign_in(m["niece"]["config_dir"], "niece@x.com")    # signed in, but gave no consent
    for name in ("Aunt", "Son"):
        fam(env, "consent", "--name", name, "--by", name, "--until", later(48))
    r = fam(env, "pick")
    assert r.returncode == 0 and r.stdout.split("\t")[0] == "dad", r.stdout + r.stderr
    assert r.stdout.split("\t")[2] == "-"                  # usual sign-in: no folder forced
    r = fam(env, "limit", "--id", "dad", inp="You've hit your limit - resets 3am")
    assert "resting until" in r.stdout and members(home)["dad"]["limit_until"].endswith("03:00")
    r = fam(env, "pick", "--after", "dad")
    assert r.returncode == 0, r.stderr
    mid, engine, cfg, name = r.stdout.strip().split("\t")
    assert (mid, engine, name) == ("son", "claude", "Son") and cfg == m["son"]["config_dir"]
    assert "signed in as dad@x.com, not aunt@x.com" in r.stderr
    fam(env, "limit", "--id", "son", inp="usage limit reached")
    r = fam(env, "pick", "--after", "son")
    assert r.returncode == 1 and "Niece has not given consent" in r.stderr, r.stderr
    assert int(fam(env, "soonest").stdout) > 0
    check = fam(env, "check").stdout
    assert "WRONG" in check and "Ready to carry the work on: 0 of 4." in check, check


def test_family_json_keeps_no_login():
    env, home, _, _ = world()
    fam(env, "add", "--name", "Dad", "--email", "dad@x.com", "--config-dir", "default")
    fam(env, "add", "--name", "Son", "--email", "son@x.com")
    fam(env, "consent", "--name", "Son", "--by", "Son", "--until", later(5))
    raw = open(os.path.join(home, "family.json")).read().lower()
    for word in ("token", "sk-ant", "oauth", "password", "cookie"):
        assert word not in raw.replace("no logins, tokens or keys", ""), word


def test_weekend_loop_hands_over_to_the_son_and_writes_relay():
    """End to end: Dad's limit runs out at round one, Aunt's folder holds the wrong account, the loop
    goes on in Son's own folder at once (no 15-minute wait), PROGRESS.md gets the Relay line."""
    env, home, bindir, root = world()
    sign_in(env["FAKE_DEFAULT_CFG"], "dad@x.com", limited=True)
    fam(env, "add", "--name", "Dad", "--email", "dad@x.com", "--config-dir", "default")
    fam(env, "add", "--name", "Aunt", "--email", "aunt@x.com")
    fam(env, "add", "--name", "Son", "--email", "son@x.com")
    m = members(home)
    sign_in(m["aunt"]["config_dir"], "dad@x.com")
    sign_in(m["son"]["config_dir"], "son@x.com")
    for name in ("Aunt", "Son"):
        fam(env, "consent", "--name", name, "--by", name, "--until", later(60))
    scripts = os.path.join(root, "scripts")
    shutil.copytree(S, scripts)
    open(os.path.join(scripts, "awake.sh"), "w").write("#!/usr/bin/env bash\necho awake-stub\n")
    task = os.path.join(root, "task")
    os.makedirs(task)
    open(os.path.join(task, "PLAN.md"), "w").write("# Plan\n| 1 | step | done | waiting |\n")
    env.update({"NIGHTCALL_LIMIT_WAIT": "2", "NIGHTCALL_MAX_ROUNDS": "6"})
    r = subprocess.run(["bash", os.path.join(scripts, "night-loop.sh"), task, "1"], capture_output=True,
                       text=True, env=env, timeout=120)
    out = r.stdout + r.stderr
    rounds = open(os.path.join(task, "rounds.txt")).read().splitlines()
    assert rounds[:3] == ["round by son@x.com"] * 3, out
    assert os.path.exists(os.path.join(task, "MORNING.md")), out
    progress = open(os.path.join(task, "PROGRESS.md")).read()
    assert "## Relay" in progress and "Son carries the work on with their own account" in progress, progress
    assert "Dad's limit" in progress
    assert "family relay on" in out and "Aunt" not in "".join(rounds)
    log = [json.loads(x) for x in open(os.path.join(home, "family-log.jsonl"))]
    assert any(e["event"] == "relay" and e["to"] == "son" for e in log)


def test_without_family_the_loop_is_unchanged():
    env, home, bindir, root = world()
    loop = open(os.path.join(S, "night-loop.sh"), encoding="utf-8").read()
    assert 'NIGHTCALL_FAMILY:-on' in loop and 'family.py" status' in loop
    assert fam(env, "status").returncode == 1        # no family.json: status says so and the loop stays as before
