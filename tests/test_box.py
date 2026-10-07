"""The boxed night: `python3 -m pytest tests/test_box.py`.

Fake `docker`, `npx` and `security` on PATH record what they were asked and never reach a real
container, sandbox or Keychain, so these run anywhere. One test (NIGHTCALL_TEST_BOX_LIVE=1, macOS)
runs the real sandbox runtime and checks the walls from inside.
"""
import json
import os
import platform
import shutil
import stat
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOX = os.path.join(ROOT, "scripts", "box.sh")
LOOP = os.path.join(ROOT, "scripts", "night-loop.sh")
TOKEN = "sk-ant-oat01-TEST-TOKEN-VALUE"

FAKES = {
    # docker: `info` answers when FAKE_DOCKER_UP=1; every call is written down
    "docker": '#!/bin/bash\necho "docker $*" >> "$FAKE_LOG"\n'
              '[ "$1" = info ] && { [ "${FAKE_DOCKER_UP:-0}" = 1 ]; exit $?; }\n'
              '[ "$1" = image ] && exit 0\nexit 0\n',
    # npx: writes down its arguments and whether the token reached its environment
    "npx": '#!/bin/bash\necho "npx $*" >> "$FAKE_LOG"\n'
           'echo "token-in-env=${CLAUDE_CODE_OAUTH_TOKEN:+yes}" >> "$FAKE_LOG"\n',
    # security: a Keychain holding one claude token
    "security": '#!/bin/bash\necho "security $*" >> "$FAKE_LOG"\n'
                'case "$*" in *"-a claude"*) echo "%s";; *) exit 44;; esac\n' % TOKEN,
    "caffeinate": "#!/bin/bash\nsleep 1\n",
}


@pytest.fixture
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in FAKES.items():
        p = bin_dir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    folder = tmp_path / "task"
    folder.mkdir()
    (folder / "PLAN.md").write_text("# plan\n")
    log = tmp_path / "calls.log"
    e = dict(os.environ)
    for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "NIGHTCALL_BOX"):
        e.pop(k, None)
    e.update(PATH=f"{bin_dir}:{e['PATH']}", FAKE_LOG=str(log), NIGHTCALL_HOME=str(tmp_path / "nc"),
             NIGHTCALL_BOARD="off")
    return {"env": e, "folder": str(folder.resolve()), "log": log}


def run(args, e, **kw):
    return subprocess.run(["bash", BOX] + args, env=e, capture_output=True, text=True, timeout=60, **kw)


def calls(ctx):
    return ctx["log"].read_text() if ctx["log"].exists() else ""


def test_srt_rules_wall_off_the_home_folder(env):
    out = run(["rules", env["folder"]], env["env"])
    rules = json.loads(out.stdout)
    home = os.path.expanduser("~")
    fs = rules["filesystem"]
    assert home in fs["denyRead"]
    assert env["folder"] in fs["allowRead"] and env["folder"] in fs["allowWrite"]
    for secret in (".ssh", ".aws", "Desktop", "Documents"):
        assert not any(p.startswith(os.path.join(home, secret)) for p in fs["allowRead"] + fs["allowWrite"] if p != ROOT)
    assert os.path.join(home, ".claude", "settings.json") in fs["denyWrite"]   # no hooks planted for later
    assert ROOT not in fs["allowWrite"] and ROOT in fs["denyWrite"]                                            # the plugin stays as it is
    nets = rules["network"]["allowedDomains"]
    assert "api.anthropic.com" in nets and "claude.ai" in nets and "example.com" not in nets


def test_extra_hosts_from_env_and_folder(env):
    with open(os.path.join(env["folder"], "box-allow.txt"), "w") as f:
        f.write("# mine\nhuggingface.co\n")
    env["env"]["NIGHTCALL_BOX_ALLOW"] = "pypi.example.org"
    nets = json.loads(run(["rules", env["folder"]], env["env"]).stdout)["network"]["allowedDomains"]
    assert "huggingface.co" in nets and "pypi.example.org" in nets


def test_without_docker_the_box_is_the_sandbox_runtime(env):
    out = run(["plan", env["folder"]], env["env"])
    assert "mode: srt" in out.stdout
    assert "@anthropic-ai/sandbox-runtime" in out.stdout and "night-loop.sh" in out.stdout
    assert "token from the Keychain" in out.stdout
    assert TOKEN not in out.stdout


def test_with_docker_up_the_box_is_a_container_without_the_key_in_it(env):
    env["env"]["FAKE_DOCKER_UP"] = "1"
    out = run(["plan", env["folder"], "6"], env["env"])
    assert "mode: docker" in out.stdout
    cmd = out.stdout
    assert '"--cap-add" "NET_ADMIN"' in cmd
    assert f'"-v" "{env["folder"]}:{env["folder"]}"' in cmd        # the task folder, and only it, writable
    assert ':/opt/nightcall:ro"' in cmd
    assert '"-e" "CLAUDE_CODE_OAUTH_TOKEN"' in cmd                   # the name, the value stays in the env
    assert TOKEN not in cmd
    assert "/.ssh" not in cmd and '"-v" "' + os.path.expanduser("~") + ':' not in cmd


def test_night_loop_box_flag_hands_the_night_to_the_box(env):
    out = subprocess.run(["bash", LOOP, "--box", env["folder"], "2"], env=env["env"], capture_output=True,
                         text=True, timeout=60)
    log = calls(env)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "srt --settings" in log and "night-loop.sh " + env["folder"] + " 2" in log
    assert "NIGHTCALL_IN_BOX=1" in log
    assert "token-in-env=yes" in log                                  # the run got the sign-in
    settings = [w for w in log.split() if w.endswith(".srt.json")][0]
    assert TOKEN not in open(settings).read()                         # and no file holds it
    assert "nightcall box (srt)" in open(os.path.join(env["folder"], "night-loop.log")).read()


def test_no_token_says_the_one_command(env, tmp_path):
    empty = tmp_path / "empty-keychain"
    empty.mkdir()
    (empty / "security").write_text("#!/bin/bash\nexit 44\n")
    (empty / "security").chmod(0o755)
    e = dict(env["env"], PATH=f"{empty}:{env['env']['PATH']}")
    out = run([env["folder"]], e, stdin=subprocess.DEVNULL)
    assert out.returncode == 3 and "box.sh key" in out.stdout
    assert "npx" not in calls(env)                                    # nothing started half signed-in


def test_stop_is_one_command(env):
    env["env"]["FAKE_DOCKER_UP"] = "1"
    sleeper = subprocess.Popen(["sleep", "60"])
    tag = subprocess.run(["bash", "-c", f"printf '%s' '{env['folder']}' | shasum | cut -c1-10"],
                         capture_output=True, text=True).stdout.strip()
    state = os.path.join(env["env"]["NIGHTCALL_HOME"], "box")
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, tag + ".pid"), "w") as f:
        f.write(str(sleeper.pid))
    out = run(["stop", env["folder"]], env["env"])
    assert sleeper.wait(timeout=5) != 0                               # the sandboxed night is gone
    assert f"docker rm -f nightcall-box-{tag}" in calls(env)          # and so is the container
    assert os.path.exists(os.path.join(env["folder"], "STOP"))
    assert "Stopped:" in out.stdout


@pytest.mark.skipif(os.environ.get("NIGHTCALL_TEST_BOX_LIVE") != "1" or platform.system() != "Darwin",
                    reason="live sandbox: NIGHTCALL_TEST_BOX_LIVE=1 on a Mac")
def test_live_walls_from_inside(tmp_path):
    folder = tmp_path / "task"
    folder.mkdir()
    rules = tmp_path / "rules.json"
    rules.write_text(subprocess.run(["bash", BOX, "rules", str(folder)], capture_output=True, text=True).stdout)
    probe = ('ls ~/.ssh >/dev/null 2>&1 && echo ssh-open || echo ssh-closed; '
             f'echo ok > "{folder}/w" && echo folder-writes; '
             'curl -s -m 8 -o /dev/null https://example.com && echo net-open || echo net-closed; '
             'security find-generic-password -s "Claude Code-credentials" >/dev/null 2>&1 && echo kc-open || echo kc-closed')
    out = subprocess.run(["npx", "-y", "-p", "@anthropic-ai/sandbox-runtime@0.0.79", "srt", "--settings", str(rules),
                          "--", "bash", "-c", probe], capture_output=True, text=True, timeout=180).stdout
    assert "ssh-closed" in out and "folder-writes" in out and "net-closed" in out and "kc-closed" in out
