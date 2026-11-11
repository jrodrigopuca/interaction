"""The ACP client drives an agent it did not write: it opens a session,
switches to a named agent, sends one prompt and answers every permission
request by its own policy (B-103). No model: the agent is a script.

    python3 -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import acp   # noqa: E402

FAKE = [sys.executable, str(ROOT / "tests" / "fake_acp_agent.py")]


class Session(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = Path(self._tmp.name)

    def run_turn(self, text="hacé el cambio", **kw):
        return acp.run_prompt(FAKE, self.cwd, text, timeout=kw.pop("timeout", 20), **kw)

    def test_opening_a_session_says_what_the_agent_offers_and_spends_nothing(self):
        turn = self.run_turn(mode="ux-ui", send=False)
        self.assertEqual(turn.session["mode"], "ux-ui")
        self.assertEqual(turn.session["modes"], ["agent_default", "ux-ui", "senior-dev"])
        self.assertEqual(turn.session["model"], "auto")
        self.assertEqual((turn.text, turn.stop_reason, turn.tool_calls), ("", "", []))

    def test_a_mode_the_agent_does_not_offer_is_an_error_not_the_default_agent(self):
        with self.assertRaises(acp.AcpError) as ctx:
            self.run_turn(mode="visionary")
        self.assertIn("no mode `visionary`", str(ctx.exception))
        self.assertIn("ux-ui", str(ctx.exception))

    def test_a_turn_collects_the_text_the_tool_calls_and_the_stop_reason(self):
        turn = self.run_turn(mode="senior-dev")
        self.assertTrue(turn.text.startswith("Leo el archivo. "))
        self.assertEqual(turn.stop_reason, "end_turn")
        self.assertEqual([(c["title"], c["kind"]) for c in turn.tool_calls],
                         [("Reading a.txt", "read"), ("Creating b.tsx", "edit")])
        self.assertEqual(turn.tool_calls[0]["status"], "completed")
        self.assertEqual(turn.session["sessionId"], "sess-1")

    def test_with_no_policy_every_permission_request_is_refused_once(self):
        turn = self.run_turn()
        self.assertEqual(turn.permissions, [{"title": "Creating b.tsx", "kind": "edit",
                                             "approved": False, "answered": "opt-reject_once"}])
        self.assertIn("Decisión: opt-reject_once.", turn.text)
        self.assertEqual(turn.tool_calls[1]["status"], "failed")

    def test_the_policy_decides_by_kind_of_tool_and_never_picks_an_always_option(self):
        turn = self.run_turn(policy=acp.allow_kinds("read", "edit"))
        self.assertEqual(turn.permissions[0]["answered"], "opt-allow_once")
        self.assertTrue(turn.permissions[0]["approved"])
        self.assertEqual(turn.tool_calls[1]["status"], "completed")
        refused = self.run_turn(policy=acp.allow_kinds("read"))
        self.assertEqual(refused.permissions[0]["answered"], "opt-reject_once")

    def test_a_request_that_omits_the_kind_is_judged_by_the_kind_the_call_announced(self):
        """kiro-cli 3.2.0 sends the kind in the `tool_call` update and not in
        the permission request: an edit must not be judged as `other`."""
        turn = self.run_turn("no-kind", policy=acp.allow_kinds("edit"))
        self.assertEqual(turn.permissions[0]["kind"], "edit")
        self.assertTrue(turn.permissions[0]["approved"])
        refused = self.run_turn("no-kind", policy=acp.allow_kinds("other", "read"))
        self.assertEqual((refused.permissions[0]["kind"], refused.permissions[0]["approved"]),
                         ("edit", False))

    def test_without_an_option_that_says_it_once_the_request_is_cancelled(self):
        """Approving with `allow_always` would hand the decision back to the
        agent for the rest of the session."""
        turn = self.run_turn("no-once", policy=acp.allow_kinds("edit"))
        self.assertEqual(turn.permissions[0], {"title": "Creating b.tsx", "kind": "edit",
                                               "approved": False, "answered": None})
        self.assertIn("Decisión: cancelled.", turn.text)

    def test_a_request_for_a_capability_the_client_does_not_offer_is_refused(self):
        turn = self.run_turn("ask-fs")
        self.assertIn(f"fs:{acp.METHOD_NOT_FOUND}", turn.text)
        self.assertEqual(turn.stop_reason, "end_turn")

    def test_host_notifications_outside_the_spec_are_kept_apart(self):
        turn = self.run_turn()
        self.assertEqual([e["method"] for e in turn.extensions], ["_fake/extension"])
        self.assertEqual(turn.record()["extensions"], ["_fake/extension"])

    def test_an_agent_that_goes_silent_or_dies_is_an_error_with_its_reason(self):
        with self.assertRaises(acp.AcpError) as ctx:
            self.run_turn("hang", timeout=2)
        self.assertIn("no answer in 2s", str(ctx.exception))
        with self.assertRaises(acp.AcpError) as ctx:
            self.run_turn("die")
        self.assertIn("exited before answering", str(ctx.exception))


class Policy(unittest.TestCase):

    def test_a_request_with_no_kind_counts_as_other(self):
        self.assertFalse(acp.allow_kinds("read")({"toolCall": {}}))
        self.assertTrue(acp.allow_kinds("other")({"toolCall": {}}))
        self.assertFalse(acp.deny_all({"toolCall": {"kind": "read"}}))

    def test_the_option_chosen_is_the_one_time_one(self):
        options = [{"optionId": "a", "kind": "allow_always"}, {"optionId": "b", "kind": "allow_once"},
                   {"optionId": "c", "kind": "reject_once"}]
        self.assertEqual(acp.choose_option(options, True), "b")
        self.assertEqual(acp.choose_option(options, False), "c")
        self.assertIsNone(acp.choose_option(options[:1], True))
        self.assertIsNone(acp.choose_option(None, False))


if __name__ == "__main__":
    unittest.main()
