"""A scenario that does real work can raise its per-sample ceiling, a sample
cut by that ceiling still says which skills it loaded, `expect_files` counts
only what the agent wrote, and `observe:` records behaviour without counting
it. No model call: `ask` is a fake and the workspaces are temp dirs.

    python3 -m unittest discover -s tests
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402


def loads(*names):
    return {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": n}} for n in names]}}


CUT = "budget: the sample hit its --max-budget-usd ceiling ($1.00 spent)"


class SampleBudget(unittest.TestCase):

    def test_a_scenario_can_raise_its_ceiling_up_to_the_heavy_one(self):
        sc = run.Scenario(id="a", category="c", prompt="p", budget=3.0)
        self.assertEqual(sc.sample_budget, 3.0)
        sc.budget = 50.0
        self.assertEqual(sc.sample_budget, run.SAMPLE_BUDGET_HEAVY)
        self.assertEqual(run.Scenario(id="b", category="c", prompt="p").sample_budget,
                         run.SAMPLE_BUDGET_SINGLE)

    def test_a_declared_budget_moves_the_estimate(self):
        sc = run.Scenario(id="a", category="c", prompt="p", budget=6.0)
        self.assertEqual(sc.estimate, 3.0)
        self.assertEqual(run.Scenario(id="b", category="c", prompt="p").estimate, run.EST_SINGLE)

    def test_the_loader_reads_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text(
                "- id: x\n  category: c\n  prompt: p\n  budget: 3\n")
            with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                sc = run.load_scenarios()[0]
        self.assertEqual(sc.budget, 3.0)


class CutVerdict(unittest.TestCase):

    def test_an_expected_skill_loaded_before_the_cut_is_a_pass(self):
        self.assertEqual(run.cut_skill_verdict({"expect_skills": ["lh-x"]}, [loads("lh-x")]), "PASS")

    def test_one_not_loaded_yet_is_unknown_never_a_fail(self):
        self.assertEqual(run.cut_skill_verdict({"expect_skills": ["lh-x"]}, []), "")

    def test_a_forbidden_skill_already_loaded_is_a_fail(self):
        self.assertEqual(run.cut_skill_verdict({"forbid_skills": ["lh-x"]}, [loads("lh-x")]), "FAIL")

    def test_a_forbidden_skill_not_loaded_yet_is_unknown(self):
        self.assertEqual(run.cut_skill_verdict({"forbid_skills": ["lh-x"]}, []), "")

    def test_a_scenario_that_needs_the_reply_stays_unknown(self):
        a = {"expect_skills": ["lh-x"], "judge": "did it do Y?"}
        self.assertEqual(run.cut_skill_verdict(a, [loads("lh-x")]), "")

    def test_run_one_uses_it(self):
        sc = run.Scenario(id="x", category="skill-trigger", prompt="p", agent="g",
                          assertions={"expect_skills": ["lh-x"]})
        for events, want in (([loads("lh-x")], "PASS"), ([], "ERROR")):
            reply = run.Reply(text="", cost=1.0, error=CUT, events=events)
            with tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(run, "ask", return_value=reply), \
                    mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
                self.assertEqual(run.run_one(sc).verdict, want)


class FixtureWorkspace(unittest.TestCase):
    """A seeded fixture with a README, as the skill-trigger fixtures have."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fixture = self.tmp / "fixtures" / "fx"
        (self.fixture / "src").mkdir(parents=True)
        (self.fixture / "README.md").write_text("seeded\n")
        (self.fixture / "src" / "a.mjs").write_text("export const a = 1\n")
        self.ws = self.tmp / "ws"
        shutil.copytree(self.fixture, self.ws)
        self.sc = run.Scenario(id="x", category="c", prompt="p", agent="g",
                               workspace="fixtures/fx")
        self.patch = mock.patch.object(run, "ROOT", self.tmp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def test_a_seeded_file_the_agent_left_alone_does_not_count(self):
        self.assertEqual(run.written_files(self.ws, ["**/*.md"], self.sc), [])

    def test_a_file_the_agent_created_counts_at_any_depth(self):
        (self.ws / "NOTES.md").write_text("state\n")
        (self.ws / "docs").mkdir()
        (self.ws / "docs" / "plan.md").write_text("plan\n")
        self.assertEqual(run.written_files(self.ws, ["**/*.md"], self.sc),
                         ["NOTES.md", "docs/plan.md"])

    def test_a_seeded_file_the_agent_edited_counts(self):
        (self.ws / "README.md").write_text("seeded\nplus the agent's notes\n")
        self.assertEqual(run.written_files(self.ws, ["**/*.md"], self.sc), ["README.md"])

    def test_observe_records_behaviour_without_changing_the_verdict(self):
        (self.ws / "src" / "a.mjs").write_text("export const a = 2\n")   # the agent edited it
        sc = self.sc
        sc.assertions = {"expect_skills": ["lh-x"],
                         "observe": {"unchanged_files": ["src/a.mjs"],
                                     "expect_files": ["**/*.md"]}}
        reply = run.Reply(text="done", events=[loads("lh-x")])
        with mock.patch.object(run, "ask", return_value=reply), \
                mock.patch.object(run, "make_workspace", return_value=self.ws):
            res = run.run_one(sc)
        self.assertEqual(res.verdict, "PASS")
        self.assertEqual({o["check"]: o["result"] for o in res.observed},
                         {"unchanged_files": "fail", "expect_files": "fail"})
        self.assertNotIn("observe", {c["check"] for c in res.checks
                                     if c["result"] == "unrecorded"})
        self.assertIn("observed", run.trial_record(res))


if __name__ == "__main__":
    unittest.main()
