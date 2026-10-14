"""`expect_skills` and `forbid_skills` (B-041) read which skill the agent
itself loaded. No model call: the events are recorded shapes.

    python3 -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402


def loads(*names, parent=None):
    """An assistant turn that calls the Skill tool once per name."""
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": n}} for n in names]}}


class SkillAssertions(unittest.TestCase):

    def test_an_expected_skill_that_loaded_passes(self):
        self.assertEqual(run.skill_failures({"expect_skills": ["lh-migrations"]},
                                            [loads("lh-migrations")]), [])

    def test_an_expected_skill_that_did_not_load_fails_and_says_what_did(self):
        out = run.skill_failures({"expect_skills": ["lh-migrations"]}, [loads("lh-data-modeling")])
        self.assertEqual(len(out), 1)
        self.assertIn("lh-migrations", out[0])
        self.assertIn("loaded: lh-data-modeling", out[0])

    def test_a_forbidden_skill_that_loaded_fails(self):
        out = run.skill_failures({"forbid_skills": ["lh-migrations"]}, [loads("lh-migrations")])
        self.assertTrue(out and out[0].startswith("loaded forbidden skill"))

    def test_a_near_miss_that_loaded_another_skill_passes(self):
        self.assertEqual(run.skill_failures({"forbid_skills": ["lh-migrations"]},
                                            [loads("lh-data-modeling")]), [])

    def test_a_subagent_loading_it_does_not_count(self):
        """The agent under test is the main lane; a specialist it delegated to
        loading the skill says nothing about this agent's description."""
        out = run.skill_failures({"expect_skills": ["lh-migrations"]},
                                 [loads("lh-migrations", parent="toolu_1")])
        self.assertTrue(out)

    def test_a_namespaced_name_is_matched_by_its_bare_name(self):
        self.assertEqual(run.skill_failures({"expect_skills": ["lh-migrations"]},
                                            [loads("local-agents:lh-migrations")]), [])

    def test_each_assertion_has_a_result_mapping(self):
        sc = run.Scenario(id="x", category="skill-trigger", prompt="p",
                          assertions={"expect_skills": ["a"], "forbid_skills": ["b"]})
        reply = run.Reply(text="ok")
        res = run.check_results(sc, reply, ["did not load skill(s): a"])
        self.assertEqual({c["check"]: c["result"] for c in res},
                         {"expect_skills": "fail", "forbid_skills": "pass"})


    def test_run_one_applies_them(self):
        """Wired where the sample is graded, not only defined: a fake ask()
        whose agent loaded the wrong skill makes the sample FAIL."""
        import tempfile
        from unittest import mock
        sc = run.Scenario(id="x", category="skill-trigger", prompt="p", agent="dba",
                          assertions={"expect_skills": ["lh-migrations"]})
        reply = run.Reply(text="ok", events=[loads("lh-data-modeling")])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "ask", return_value=reply), \
                mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
            res = run.run_one(sc)
        self.assertEqual(res.verdict, "FAIL")
        self.assertTrue(res.fails[0].startswith("did not load skill"))


if __name__ == "__main__":
    unittest.main()
