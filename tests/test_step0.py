"""Step 0 guard (hooks/python.sh): a hook runs only with a real Python 3, and never starts a stub.

The trap it closes: a Mac without Apple's Command Line Tools has /usr/bin/python3, and running it
pops Apple's "install developer tools?" window - in the middle of a lesson, on every hook. On
Windows the trap is the Microsoft Store stub. Every case here builds a fake PATH, so it runs the
same on any machine.
"""
import json
import os
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "hooks", "python.sh")
PLUGIN = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))["name"]


def tool(folder, name, body):
    path = os.path.join(folder, name)
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class StepZero(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        self.ran = os.path.join(self.tmp, "RAN")
        self.script = os.path.join(self.tmp, "hook.py")
        open(self.script, "w").write("print('hook ran')\n")
        # The minimum a shell needs, and nothing called python.
        for name in ("uname", "cat", "echo", "true"):
            for d in ("/usr/bin", "/bin"):
                if os.path.exists(os.path.join(d, name)):
                    os.symlink(os.path.join(d, name), os.path.join(self.bin, name))
                    break

    def run_guard(self, mode, env_extra):
        env = {"PATH": self.bin, "HOME": self.tmp}
        env.update(env_extra)
        p = subprocess.run(["/bin/sh", GUARD, PLUGIN, mode, self.script], env=env,
                           capture_output=True, text=True, timeout=20)
        return p.returncode, p.stdout, p.stderr

    def fake_python(self, name, works=True):
        # Records every run, so a test can prove a stub was never started.
        exit_code = 0 if works else 9009
        return tool(self.bin, name, 'echo x >> "%s"\n[ "$1" = -c ] && exit %d\nexec "%s" "$@"'
                    % (self.ran, exit_code, os.path.realpath(subprocess.check_output(
                        ["/bin/sh", "-c", "command -v python3"], text=True).strip())))

    def test_mac_without_command_line_tools_never_starts_the_apple_stub(self):
        stub = self.fake_python("python3")
        tool(self.bin, "xcode-select", "exit 2")
        for mode, said in (("say", True), ("quiet", False)):
            code, out, err = self.run_guard(mode, {"STEP0_OS": "Darwin", "STEP0_APPLE_STUB": stub})
            self.assertEqual(code, 0)
            self.assertFalse(os.path.exists(self.ran), "the Apple stub was started")
            self.assertEqual("paused" in out, said, out)
            if said:
                self.assertIn("xcode-select --install", out)
                self.assertEqual(len(out.strip().splitlines()), 1)

    def test_mac_with_command_line_tools_runs_the_hook(self):
        stub = self.fake_python("python3")
        dev = os.path.join(self.tmp, "CommandLineTools")
        os.makedirs(os.path.join(dev, "usr", "bin"))
        tool(os.path.join(dev, "usr", "bin"), "python3", "exit 0")
        tool(self.bin, "xcode-select", 'echo "%s"' % dev)
        code, out, err = self.run_guard("say", {"STEP0_OS": "Darwin", "STEP0_APPLE_STUB": stub})
        self.assertEqual((code, out.strip()), (0, "hook ran"), err)

    def test_mac_with_another_python_first_needs_no_command_line_tools(self):
        self.fake_python("python3")          # not the stub path, e.g. Homebrew or python.org
        tool(self.bin, "xcode-select", "exit 2")
        code, out, err = self.run_guard("say", {"STEP0_OS": "Darwin", "STEP0_APPLE_STUB": "/usr/bin/python3"})
        self.assertEqual((code, out.strip()), (0, "hook ran"), err)

    def test_windows_store_stub_is_skipped_and_python_is_found(self):
        self.fake_python("python3", works=False)   # the Microsoft Store alias
        self.fake_python("python")                 # python.org's name on Windows
        code, out, err = self.run_guard("say", {"STEP0_OS": "MINGW64_NT-10.0"})
        self.assertEqual((code, out.strip()), (0, "hook ran"), err)

    def test_no_python_at_all_is_one_line_and_exit_zero(self):
        self.fake_python("python3", works=False)
        code, out, err = self.run_guard("say", {"STEP0_OS": "Linux"})
        self.assertEqual(code, 0)
        self.assertIn("paused", out)
        self.assertEqual(self.run_guard("quiet", {"STEP0_OS": "Linux"})[:2], (0, ""))

    def test_every_hook_goes_through_the_guard(self):
        hooks = json.load(open(os.path.join(ROOT, "hooks", "hooks.json")))["hooks"]
        commands = [h["command"] for groups in hooks.values() for g in groups for h in g["hooks"]]
        self.assertTrue(commands)
        for c in commands:
            self.assertTrue(c.startswith('sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" %s ' % PLUGIN), c)
        # exactly one hook speaks, so the person hears the step-0 line once per session
        self.assertEqual(sum(" say " in c for c in commands), 0 if "SessionStart" not in hooks else 1)


if __name__ == "__main__":
    unittest.main()
