"""Every sample records whom it handed work to, whether that was a named
agent or a fork, how deep it went and which skills the called agent loaded
(B-094). No model call: the streams are built by hand.

    python3 -m unittest discover -s tests
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402


def spawn(tid, agent, parent=None, description="do the thing"):
    inp = {"description": description, "prompt": "brief"}
    if agent:
        inp["subagent_type"] = agent
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [
        {"type": "tool_use", "id": tid, "name": "Agent", "input": inp}]}}


def call(name, parent, **inp):
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [
        {"type": "tool_use", "id": f"{name}-{parent}", "name": name, "input": inp}]}}


class Tree(unittest.TestCase):

    def test_a_named_agent_and_a_fork_are_told_apart(self):
        tree = run.delegation_tree([spawn("t1", "senior-dev"), spawn("t2", "fork")])
        self.assertEqual((tree["t1"]["agent"], tree["t1"]["kind"]), ("senior-dev", "agent"))
        self.assertEqual((tree["t2"]["agent"], tree["t2"]["kind"]), ("fork", "fork"))
        self.assertEqual(run.delegation_tree([spawn("t3", None)])["t3"]["agent"], "?")

    def test_depth_grows_with_each_spawn_made_from_inside_a_child(self):
        tree = run.delegation_tree([
            spawn("t1", "eng-manager"), spawn("t2", "ux-ui", parent="t1"),
            spawn("t3", "senior-dev", parent="t2"), spawn("t4", "qa")])
        self.assertEqual({k: v["depth"] for k, v in tree.items()},
                         {"t1": 1, "t2": 2, "t3": 3, "t4": 1})

    def test_the_skills_and_the_activity_of_the_called_agent_are_its_own(self):
        tree = run.delegation_tree([
            call("Skill", None, skill="lh-mockups"),                 # the caller's own
            spawn("t1", "senior-dev"),
            call("Read", "t1", file_path="a"),
            call("Skill", "t1", skill="local:lh-code-health"),
            call("Skill", "t1", skill="lh-code-health"),
            spawn("t2", "qa"), call("Bash", "t2", command="ls")])
        self.assertEqual(tree["t1"]["skills"], ["lh-code-health"])
        self.assertEqual(tree["t1"]["events"], 3)
        self.assertEqual((tree["t2"]["skills"], tree["t2"]["events"]), ([], 1))

    def test_odd_events_do_not_break_the_reading(self):
        events = [None, "text", {"type": "assistant", "message": "a string"},
                  {"type": "user", "message": {"content": "plain"}},
                  {"type": "assistant", "message": {"content": ["x", {"type": "text"}]}},
                  spawn("t1", "qa")]
        self.assertEqual(list(run.delegation_tree(events)), ["t1"])
        self.assertEqual(run.delegation_tree(None), {})


class ReadAgain(unittest.TestCase):
    """What a handoff costs in reading: the files the called agent read that
    its caller had already read, and which of those it did not go on to edit."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        (self.ws / "src").mkdir()

    def tearDown(self):
        shutil.rmtree(self.ws)

    def test_the_files_one_call_read(self):
        root = self.ws.resolve()
        inside = str(self.ws / "src" / "auth.js")
        self.assertEqual(run.files_read(
            {"name": "Read", "input": {"file_path": inside}}, root), ["src/auth.js"])
        bash = lambda cmd: run.files_read({"name": "Bash", "input": {"command": cmd}}, root)
        self.assertEqual(bash("cat src/db.js ./src/auth.js"), ["src/db.js", "src/auth.js"])
        self.assertEqual(bash("cd src && sed -n '1,40p' routes/invoices.js | head -5"),
                         ["routes/invoices.js"])
        self.assertEqual(bash("ls -la src; cat package.json"), ["package.json"])
        self.assertEqual(bash("grep -rn ownerId src"), [])
        self.assertEqual(bash("npm test"), [])
        self.assertEqual(bash("node src/app.js"), [])        # runs it, does not read it
        for name in ("a.js", "b.js", "notes.md"):
            (self.ws / "src" / name).write_text("x")
        self.assertEqual(bash("cat package.json src/*.js"),
                         ["package.json", "src/a.js", "src/b.js"])
        self.assertEqual(bash("cat src/[zzz"), [])
        self.assertEqual(bash("cat 'unbalanced"), [])
        self.assertEqual(run.files_read({"name": "Write", "input": {"file_path": inside}}, root), [])

    def test_only_what_the_caller_read_before_the_call_counts_as_read_again(self):
        f = lambda name: str(self.ws / "src" / name)
        tree = run.delegation_tree([
            call("Read", None, file_path=f("auth.js")),
            call("Bash", None, command="cat src/db.js"),
            spawn("t1", "senior-dev"),
            call("Read", "t1", file_path=f("auth.js")),          # read again, context only
            call("Read", "t1", file_path=f("db.js")),            # read again, then edited
            call("Read", "t1", file_path=f("orders.js")),        # new to the called agent
            call("Edit", "t1", file_path=f("db.js")),
            call("Read", None, file_path=f("orders.js")),        # the caller, afterwards
        ], self.ws)
        self.assertEqual(tree["t1"]["read"], ["src/auth.js", "src/db.js", "src/orders.js"])
        self.assertEqual(tree["t1"]["reread"], ["src/auth.js", "src/db.js"])
        self.assertEqual(tree["t1"]["reread_context"], ["src/auth.js"])

    def test_a_nested_call_is_measured_against_its_own_caller(self):
        f = lambda name: str(self.ws / "src" / name)
        tree = run.delegation_tree([
            call("Read", None, file_path=f("a.js")),
            spawn("t1", "ux-ui"),
            call("Read", "t1", file_path=f("b.js")),
            spawn("t2", "senior-dev", parent="t1"),
            call("Read", "t2", file_path=f("a.js")),
            call("Read", "t2", file_path=f("b.js")),
        ], self.ws)
        self.assertEqual(tree["t1"]["reread"], [])
        self.assertEqual(tree["t2"]["reread"], ["src/b.js"])

    def test_the_run_line_says_how_much_was_read_again(self):
        f = lambda name: str(self.ws / "src" / name)
        events = [call("Read", None, file_path=f("auth.js")), spawn("t1", "senior-dev"),
                  call("Read", "t1", file_path=f("auth.js"))]
        res = run.Result(sc=run.Scenario(id="x", category="c", prompt="p"),
                         reply=run.Reply(text="ok", events=events))
        res.spawned = run.delegation_tree(events, self.ws)
        line = run.delegation_summary([res])
        self.assertIn("read again 1 file(s) their caller had already read", line)
        self.assertIn("1 of them they did not go on to edit", line)


class EverySample(unittest.TestCase):
    """A scenario does not have to declare `delegate:` for the delegation to
    be recorded: on 2026-11-10 five samples delegated and the run saw none."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "fixtures" / "fx").mkdir(parents=True)
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        self.sc = run.Scenario(id="x", category="c", prompt="p", agent="ux-ui",
                               workspace="fixtures/fx")
        self.patch = mock.patch.object(run, "ROOT", self.tmp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def sample(self, events):
        reply = run.Reply(text="done", events=events)
        with mock.patch.object(run, "ask", return_value=reply), \
                mock.patch.object(run, "make_workspace", return_value=self.ws):
            return run.run_one(self.sc)

    def test_a_sample_that_delegated_says_so_in_its_record(self):
        self.assertFalse(self.sc.delegate)
        res = self.sample([spawn("t1", "senior-dev", description="build the empty state")])
        rec = run.trial_record(res)
        self.assertEqual(rec["delegated_to"]["t1"]["agent"], "senior-dev")
        self.assertEqual(rec["delegated_to"]["t1"]["kind"], "agent")
        self.assertEqual(rec["delegated_to"]["t1"]["depth"], 1)

    def test_a_sample_cut_by_its_budget_still_says_whom_it_called(self):
        """Measured on 2026-11-10: the ceiling counts the called agent's spend,
        so the cut lands while it works — and the record came back empty."""
        reply = run.Reply(text="", cost=0.2, events=[spawn("t1", "senior-dev"),
                                                     call("Bash", "t1", command="ls")],
                          error="budget: the sample hit its --max-budget-usd ceiling ($0.20 spent)")
        with mock.patch.object(run, "ask", return_value=reply), \
                mock.patch.object(run, "make_workspace", return_value=self.ws):
            res = run.run_one(self.sc)
        self.assertEqual(res.status, "ERROR")
        self.assertEqual(run.trial_record(res)["delegated_to"]["t1"]["agent"], "senior-dev")
        self.assertEqual(res.spawned["t1"]["events"], 1)

    def test_a_sample_that_did_not_delegate_records_nothing(self):
        self.assertIsNone(run.trial_record(self.sample([]))["delegated_to"])

    def test_the_run_says_in_one_line_what_was_delegated(self):
        a = self.sample([spawn("t1", "senior-dev"), spawn("t2", "senior-dev", parent="t1")])
        b = self.sample([spawn("t3", "fork")])
        c = self.sample([])
        line = run.delegation_summary([a, b, c])
        self.assertIn("2 of 3 sample(s) handed work to another agent", line)
        self.assertIn("senior-dev ×2", line)
        self.assertIn("fork ×1", line)
        self.assertIn("deepest level 2", line)
        self.assertEqual(run.delegation_summary([c]), "")


class Fingerprint(unittest.TestCase):

    def prints(self, **env):
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH", "CLAUDE_CODE_FORK_SUBAGENT")}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True), \
                mock.patch.object(run, "catalog_skill_names", return_value=[]):
            return run.host_fingerprints([])["subagents"]

    def test_the_depth_and_the_fork_setting_the_cli_saw_are_in_the_stamp(self):
        self.assertEqual(self.prints(), {"max_depth": "default", "fork": "default"})
        self.assertEqual(self.prints(CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH="1",
                                     CLAUDE_CODE_FORK_SUBAGENT="0"),
                         {"max_depth": "1", "fork": "0"})

    def test_a_run_stamped_before_the_key_existed_can_still_be_resumed(self):
        stamp = {"catalog_commit": "a" * 40, "catalog_dirty": False, "installed_at": "t"}
        meta = {"catalog": stamp, "budget": {"capped": True},
                "fingerprints": {"agents": {"qa": "x"}, "scenarios": {"a": "f"}}}
        now = {"agents": {"qa": "x"}, "scenarios": {"a": "f"},
               "subagents": {"max_depth": "default", "fork": "default"}}
        self.assertEqual(run.resume_refusal(meta, now, stamp), "")
        meta["fingerprints"]["subagents"] = {"max_depth": "1", "fork": "default"}
        self.assertIn("subagents", run.resume_refusal(meta, now, stamp))


if __name__ == "__main__":
    unittest.main()
