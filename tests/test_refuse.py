"""`refuse:` keeps a tool visible and out of the permissions, so the agent
reads a refusal; `deny:` hides it. B-066 measured the difference: with the
tool hidden, agents edited through the shell without ever meeting a "no".
No model call: the CLI is a fake.

    python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402


def settings_of(cmd: list) -> dict:
    return json.loads(cmd[cmd.index("--settings") + 1])


class Permissions(unittest.TestCase):

    def test_refused_tools_leave_the_allow_list_and_nothing_else_does(self):
        got = run.permissions_for("Edit, Write,NotebookEdit")
        self.assertNotIn("Edit", got["allow"])
        self.assertNotIn("Write", got["allow"])
        self.assertIn("Read", got["allow"])
        self.assertIn("Bash(node:*)", got["allow"])
        self.assertEqual(got["deny"], run.HARNESS_PERMISSIONS["deny"])
        self.assertIn("Edit", run.HARNESS_PERMISSIONS["allow"])      # the default is untouched

    def test_nothing_refused_is_the_harness_default(self):
        self.assertIs(run.permissions_for(""), run.HARNESS_PERMISSIONS)

    def test_spec_tools_drop_the_pattern(self):
        self.assertEqual(run.spec_tools("Bash(rm:*), Edit,,Write"), ["Bash", "Edit", "Write"])


class Ask(unittest.TestCase):

    def call(self, **kw):
        fake = SimpleNamespace(stdout="", returncode=0, stderr="")
        with mock.patch.object(run.subprocess, "run", return_value=fake) as sp:
            reply = run.ask("p", **kw)
        return reply, sp

    def test_a_refused_tool_stays_visible_and_unpermitted(self):
        _, sp = self.call(refuse="Edit,Write", deny="Bash(rm:*)", neutral=True)
        cmd = sp.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--disallowedTools") + 1], "Bash(rm:*)")   # only the hidden one
        allow = settings_of(cmd)["permissions"]["allow"]
        self.assertNotIn("Edit", allow)
        self.assertNotIn("Write", allow)

    def test_without_refuse_the_settings_are_the_default(self):
        _, sp = self.call(neutral=True)
        self.assertIn("Edit", settings_of(sp.call_args.args[0])["permissions"]["allow"])

    def test_refuse_outside_the_neutral_session_is_an_error_not_a_silent_allow(self):
        reply, sp = self.call(refuse="Edit", neutral=False)
        self.assertIn("neutral session", reply.error)
        sp.assert_not_called()

    def test_run_one_passes_it(self):
        sc = run.Scenario(id="x", category="c", prompt="p", agent="a", refuse="Edit")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "ask", return_value=run.Reply(text="ok")) as ask, \
                mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
            run.run_one(sc)
        self.assertEqual(ask.call_args.kwargs["refuse"], "Edit")


class Loader(unittest.TestCase):

    def load(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text("- id: x\n  category: c\n  prompt: p\n" + extra)
            with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                return run.load_scenarios()

    def test_reads_refuse(self):
        self.assertEqual(self.load('  refuse: "Edit,Write"\n')[0].refuse, "Edit,Write")

    def test_a_tool_both_refused_and_allowed_or_hidden_is_refused_at_load(self):
        for extra in ('  refuse: "Edit"\n  allow: "Edit"\n', '  refuse: "Edit"\n  deny: "Edit,Write"\n'):
            with self.assertRaises(SystemExit):
                self.load(extra)


if __name__ == "__main__":
    unittest.main()
