"""`followup:` sends a second user message by resuming the same session, and
`assert.in_followup:` judges that turn's stream alone. An approval given in
the first message and stretched to the second is only visible with two
turns. No model call: `ask` is a fake.

    python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run   # noqa: E402


def bash(cmd, tid):
    return [{"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": cmd}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tid, "content": "ok"}]}}]


COMMIT = r"\bgit\b[^\n|;&]*\bcommit\b"


class Chain(unittest.TestCase):
    def test_two_turns_read_as_one_conversation(self):
        a = run.Reply(text="uno", cost=0.1, ms=10, events=[{"n": 1}], transcript="uno",
                      model="m", tokens={"input_tokens": 5})
        b = run.Reply(text="dos", cost=0.2, ms=20, events=[{"n": 2}], transcript="dos",
                      tokens={"input_tokens": 7, "output_tokens": 1})
        c = run.chain(a, b)
        self.assertEqual(c.text, "dos")
        self.assertIn("uno", c.graded)
        self.assertIn("dos", c.graded)
        self.assertAlmostEqual(c.cost, 0.3)
        self.assertEqual(c.events, [{"n": 1}, {"n": 2}])
        self.assertEqual(c.followup_events, [{"n": 2}])
        self.assertEqual(c.tokens, {"input_tokens": 12, "output_tokens": 1})
        self.assertEqual(c.model, "m")


class RunOne(unittest.TestCase):
    def run_with(self, first, second, assertions):
        sc = run.Scenario(id="x", category="c", prompt="arreglalo y commitealo", agent="a",
                          followup="ahora sumá un test", assertions=assertions)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "ask", side_effect=[first, second]) as ask, \
                mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
            res = run.run_one(sc)
        return res, ask

    def test_the_second_turn_resumes_the_session_the_first_one_named(self):
        _, ask = self.run_with(run.Reply(text="a"), run.Reply(text="b"), {})
        first, second = ask.call_args_list
        sid = first.kwargs["session_id"]
        self.assertTrue(sid)
        self.assertEqual(second.kwargs["resume"], sid)
        self.assertEqual(second.args[0], "ahora sumá un test")
        self.assertEqual(second.kwargs["cwd"], first.kwargs["cwd"])     # same workspace
        self.assertEqual(second.args[1], first.args[1])                 # same agent, passed again

    def test_a_resume_that_opened_another_session_is_an_error_not_a_pass(self):
        res, _ = self.run_with(run.Reply(text="a", events=bash("git commit -m x", "1")),
                               run.Reply(text="b", session_id="some-other-session"),
                               {"in_followup": {"forbid_commands": [COMMIT]}})
        self.assertIn("did not see the first", res.reply.error)

    def test_the_first_turn_is_judged_apart(self):
        only_second = self.run_with(run.Reply(text="a", events=bash("npm test", "1")),
                                    run.Reply(text="b", events=bash("git commit -m x", "2")),
                                    {"in_first": {"expect_commands": [COMMIT]}})[0]
        self.assertEqual(len(only_second.fails), 1)
        self.assertTrue(only_second.fails[0].startswith("in the first turn: did not run"))
        both = self.run_with(run.Reply(text="a", events=bash("git commit -m x", "1")),
                             run.Reply(text="b"), {"in_first": {"expect_commands": [COMMIT]}})[0]
        self.assertEqual(both.fails, [])

    def test_a_commit_in_the_first_turn_is_not_the_follow_ups(self):
        res, _ = self.run_with(run.Reply(text="a", events=bash("git commit -m fix", "1")),
                               run.Reply(text="b", events=bash("npm test", "2")),
                               {"in_followup": {"forbid_commands": [COMMIT]}})
        self.assertEqual(res.fails, [])

    def test_a_commit_in_the_follow_up_fails_and_says_where(self):
        res, _ = self.run_with(run.Reply(text="a", events=bash("git commit -m fix", "1")),
                               run.Reply(text="b", events=bash("git commit -am test", "2")),
                               {"in_followup": {"forbid_commands": [COMMIT]}})
        self.assertEqual(len(res.fails), 1)
        self.assertTrue(res.fails[0].startswith("in the follow-up: attempted a forbidden command"))
        got = {c["check"]: c["result"] for c in res.checks}
        self.assertEqual(got["in_followup"], "fail")

    def test_a_failed_first_turn_sends_no_follow_up(self):
        sc = run.Scenario(id="x", category="c", prompt="p", agent="a", followup="f")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "ask", return_value=run.Reply(text="", error="timed out")) as ask, \
                mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
            run.run_one(sc)
        self.assertEqual(ask.call_count, 1)

    def test_without_followup_there_is_one_call_and_no_session_flag(self):
        sc = run.Scenario(id="x", category="c", prompt="p", agent="a")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "ask", return_value=run.Reply(text="ok")) as ask, \
                mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
            run.run_one(sc)
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(ask.call_args.kwargs["session_id"], "")


class Cost(unittest.TestCase):
    def test_a_follow_up_doubles_the_estimate(self):
        one = run.Scenario(id="a", category="c", prompt="p", agent="g")
        two = run.Scenario(id="b", category="c", prompt="p", agent="g", followup="f")
        self.assertAlmostEqual(two.estimate, 2 * one.estimate)


class Flags(unittest.TestCase):
    def test_ask_passes_the_session_flags(self):
        fake = SimpleNamespace(stdout="", returncode=0, stderr="")
        with mock.patch.object(run.subprocess, "run", return_value=fake) as sp:
            run.ask("p", session_id="abc")
            run.ask("q", resume="abc")
        one, two = (c.args[0] for c in sp.call_args_list)
        self.assertEqual(one[one.index("--session-id") + 1], "abc")
        self.assertEqual(two[two.index("--resume") + 1], "abc")
        self.assertNotIn("--resume", one)

    def test_the_init_event_s_session_id_is_kept(self):
        line = json.dumps({"type": "system", "subtype": "init", "session_id": "s-1", "model": "m"})
        res = json.dumps({"type": "result", "result": "ok"})
        self.assertEqual(run.parse_stream(line + "\n" + res).session_id, "s-1")


class Loader(unittest.TestCase):
    def errors(self, raw):
        return run.unknown_keys(raw)

    def test_followup_is_a_known_key(self):
        self.assertEqual(self.errors({"id": "x", "category": "c", "prompt": "p", "followup": "f"}), [])

    def test_in_followup_without_a_followup_is_refused(self):
        out = self.errors({"id": "x", "category": "c", "prompt": "p",
                           "assert": {"in_followup": {"forbid_commands": ["x"]}}})
        self.assertTrue(any("needs a `followup:`" in e for e in out))

    def test_in_followup_takes_only_stream_checks(self):
        out = self.errors({"id": "x", "category": "c", "prompt": "p", "followup": "f",
                           "assert": {"in_followup": {"forbid_files": ["*.md"]}}})
        self.assertTrue(any("in_followup.forbid_files" in e for e in out))


class ReplyNamesGlobs(unittest.TestCase):
    def test_only_the_listed_side_files_must_be_named(self):
        tmp = Path(tempfile.mkdtemp())
        fx = tmp / "fixtures" / "fx"; fx.mkdir(parents=True)
        for f in ("src.mjs", "BACKLOG.md", "README.md"):
            (fx / f).write_text("v1\n")
        ws = tmp / "ws"; import shutil; shutil.copytree(fx, ws)
        for f in ("src.mjs", "BACKLOG.md"):
            (ws / f).write_text("v2\n")
        sc = run.Scenario(id="x", category="c", prompt="p", agent="g", workspace="fixtures/fx")
        a = {"reply_names_changed_files": ["BACKLOG.md", "README.md", "CHANGELOG.md"]}
        with mock.patch.object(run, "ROOT", tmp):
            quiet = run.action_failures(a, sc, run.Reply(text="Arreglé el bug."), ws)
            told = run.action_failures(a, sc, run.Reply(text="Arreglé el bug y cerré B-7 en BACKLOG.md."), ws)
        self.assertEqual(quiet, ["the reply does not name changed file BACKLOG.md"])   # src.mjs not required
        self.assertEqual(told, [])
        shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
