"""`--permission-mode`: one mode for every sample of a run, over each
scenario's own — the suite runs in the default mode, the user works in auto."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run   # noqa: E402


class Override(unittest.TestCase):
    def mode_sent(self, override, own=""):
        sc = run.Scenario(id="x", category="c", prompt="p", agent="a", permission_mode=own)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "PERMISSION_OVERRIDE", override), \
                mock.patch.object(run, "ask", return_value=run.Reply(text="ok")) as ask, \
                mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
            run.run_one(sc)
        return ask.call_args.kwargs["permission_mode"]

    def test_unset_each_scenario_keeps_its_own(self):
        self.assertEqual(self.mode_sent("", own="acceptEdits"), "acceptEdits")
        self.assertEqual(self.mode_sent(""), "")

    def test_set_it_wins_over_the_scenario(self):
        self.assertEqual(self.mode_sent("auto"), "auto")
        self.assertEqual(self.mode_sent("auto", own="acceptEdits"), "auto")

    def test_it_enters_the_fingerprints_only_when_set(self):
        with mock.patch.object(run, "PERMISSION_OVERRIDE", ""):
            self.assertNotIn("permission_mode", run.host_fingerprints([]))
        with mock.patch.object(run, "PERMISSION_OVERRIDE", "auto"):
            self.assertEqual(run.host_fingerprints([])["permission_mode"], "auto")

    def test_a_resume_in_another_mode_is_refused(self):
        meta = {"budget": {"capped": True}, "fingerprints": {"permission_mode": "auto"}}
        self.assertIn("permission_mode", run.resume_refusal(meta, {}, None))


if __name__ == "__main__":
    unittest.main()
