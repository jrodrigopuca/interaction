"""`hide_commands:` builds a PATH on which a command does not exist (B-077),
so the agent meets "command not found" instead of a refusal. No model call:
two fake bin directories in a temp dir stand in for the real PATH.

    python3 -m unittest discover -s tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402


def tool(d: Path, name: str, says: str) -> None:
    f = d / name
    f.write_text(f"#!/bin/sh\necho {says}\n")
    f.chmod(0o755)


class PathWithout(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.a, self.b = self.tmp / "a", self.tmp / "b"
        self.a.mkdir()
        self.b.mkdir()
        tool(self.a, "rg", "rg-a")
        tool(self.a, "git", "git-a")       # same directory as the hidden one
        tool(self.b, "git", "git-b")       # shadowed by a/, as the shell would
        tool(self.b, "node", "node-b")
        (self.a / "subdir").mkdir()        # directories are not commands
        self.path = os.pathsep.join([str(self.a), "relative/dir", str(self.tmp / "missing"), str(self.b)])

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_hidden_command_is_absent_and_its_neighbours_are_not(self):
        got = Path(run.path_without(("rg",), self.path, self.tmp / "bin"))
        names = set(os.listdir(got))
        self.assertNotIn("rg", names)
        self.assertIn("git", names)
        self.assertIn("node", names)
        self.assertNotIn("subdir", names)

    def test_first_directory_wins_like_the_shell(self):
        got = Path(run.path_without(("rg",), self.path, self.tmp / "bin"))
        self.assertEqual(os.readlink(got / "git"), str(self.a / "git"))

    def test_command_v_fails_for_real(self):
        got = run.path_without(("rg",), self.path, self.tmp / "bin")
        env = {"PATH": got}
        miss = subprocess.run(["/bin/sh", "-c", "command -v rg"], env=env, capture_output=True)
        self.assertNotEqual(miss.returncode, 0)
        hit = subprocess.run(["/bin/sh", "-c", "git"], env=env, capture_output=True, text=True)
        self.assertEqual(hit.stdout.strip(), "git-a")
        nf = subprocess.run(["/bin/sh", "-c", "rg x"], env=env, capture_output=True)
        self.assertEqual(nf.returncode, 127)


class Env(unittest.TestCase):

    def test_without_the_field_the_env_is_as_before(self):
        self.assertIsNone(run.agent_env(False))
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=False):
            env = run.agent_env(True)
            self.assertEqual(env["PATH"], "/usr/bin:/bin")
            self.assertEqual(env["CLAUDE_CODE_SHELL"], run.NEUTRAL_SHELL)

    def test_a_path_replaces_path_and_keeps_the_neutral_shell(self):
        env = run.agent_env(True, "/tmp/hidden-bin")
        self.assertEqual(env["PATH"], "/tmp/hidden-bin")
        self.assertEqual(env["CLAUDE_CODE_SHELL"], run.NEUTRAL_SHELL)


class Field(unittest.TestCase):

    def test_absent_hides_nothing(self):
        self.assertEqual(run.hidden_commands(None, "x"), ())

    def test_list_of_names(self):
        self.assertEqual(run.hidden_commands(["ag", "fd"], "x"), ("ag", "fd"))

    def test_names_the_host_shadows_are_refused(self):
        # Claude Code's snapshot defines these as functions: hiding them from
        # PATH leaves the agent with them anyway (run 20261019-020803).
        for name in ("rg", "grep", "find", "pkill"):
            with self.subTest(name=name), self.assertRaises(SystemExit) as cm:
                run.hidden_commands(["ag", name], "x")
            self.assertIn(name, str(cm.exception.code))

    def test_anything_else_is_refused(self):
        for bad in ("ag", [], ["/opt/homebrew/bin/ag"], ["ag fd"], [1], {"ag": 1}, True):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                run.hidden_commands(bad, "x")


if __name__ == "__main__":
    unittest.main()
