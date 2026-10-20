"""B-038: the branch WITHOUT the catalog. No model call: the CLI is faked, the
catalog is a temp dir and the run folders are hand-built.

    python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402
import viz   # noqa: E402


def sc(**kw):
    base = dict(id="x", category="judgment", prompt="p", agent="senior-dev")
    base.update(kw)
    return run.Scenario(**base)


class Skips(unittest.TestCase):

    def test_a_plain_scenario_runs(self):
        self.assertEqual(run.no_agent_reason(sc()), "")

    def test_categories_that_need_the_catalog_are_skipped_with_a_reason(self):
        for cat in ("routing", "handoff", "composition", "inheritance",
                    "skill-trigger", "skill-value", "build-quality"):
            self.assertTrue(run.no_agent_reason(sc(category=cat)), cat)

    def test_delegation_ablation_memory_and_skill_assertions_are_skipped(self):
        for kw in ({"delegate": True}, {"ablate": ("lh-code-audit",)}, {"memory": "off"},
                   {"assertions": {"memory_forbid_types": ["user"]}},
                   {"assertions": {"expect_skills": ["lh-x"]}},
                   {"assertions": {"forbid_skills": ["lh-x"]}}):
            self.assertTrue(run.no_agent_reason(sc(**kw)), kw)

    def test_a_skill_check_only_in_observe_does_not_skip(self):
        s = sc(assertions={"observe": {"expect_skills": ["lh-x"]}, "judge": "j"})
        self.assertEqual(run.no_agent_reason(s), "")

    def test_the_scenario_can_declare_its_own_reason(self):
        self.assertEqual(run.no_agent_reason(sc(no_agent="needs the roster")), "needs the roster")

    def test_every_roster_dependent_real_scenario_is_skipped(self):
        for s in run.load_scenarios():
            if s.category in ("routing", "handoff", "composition", "inheritance"):
                self.assertTrue(run.no_agent_reason(s), s.id)

    def test_the_recent_promises_do_run_without_the_catalog(self):
        by = {s.id: s for s in run.load_scenarios()}
        for sid in ("senior-dev-names-commit-point", "senior-dev-no-commit-talk-without-changes",
                    "senior-dev-shell-writes-bare", "senior-dev-slug-change-suite-red"):
            self.assertEqual(run.no_agent_reason(by[sid]), "", sid)


class Loader(unittest.TestCase):

    def load(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text("- id: x\n  category: c\n  prompt: p\n" + extra)
            with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                return run.load_scenarios()

    def test_no_agent_loads_as_the_reason(self):
        self.assertEqual(self.load("  no_agent: needs the roster\n")[0].no_agent, "needs the roster")
        self.assertEqual(self.load("")[0].no_agent, "")

    def test_a_non_string_reason_is_refused(self):
        with self.assertRaises(SystemExit):
            self.load("  no_agent: [a, b]\n")


class Protects(unittest.TestCase):

    def load(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text("- id: x\n  category: c\n  prompt: p\n" + extra)
            with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                return run.load_scenarios()[0]

    WHEN = '    revisit_if: "cuando se mida con otro modelo"\n'

    def test_a_kind_and_a_condition_load(self):
        s = self.load("  protects:\n    kind: model-floor\n" + self.WHEN)
        self.assertEqual(s.protects, ("model-floor", "", "cuando se mida con otro modelo"))
        self.assertEqual(self.load("").protects, ())

    def test_regression_of_needs_its_reference(self):
        ok = self.load("  protects:\n    kind: regression-of\n    ref: B-073\n" + self.WHEN)
        self.assertEqual(ok.protects[:2], ("regression-of", "B-073"))
        for extra in ("  protects:\n    kind: regression-of\n" + self.WHEN,
                      "  protects:\n    kind: by-design\n    ref: B-073\n" + self.WHEN):
            with self.assertRaises(SystemExit):
                self.load(extra)

    def test_a_free_text_reason_unknown_kind_or_missing_condition_is_refused(self):
        for extra in ("  protects: because it is nice\n",
                      "  protects:\n    kind: whatever\n" + self.WHEN,
                      "  protects:\n    kind: model-floor\n",
                      '  protects:\n    kind: model-floor\n    revisit_if: "later"\n'):
            with self.assertRaises(SystemExit, msg=extra):
                self.load(extra)

    def test_annotating_does_not_change_the_fingerprint(self):
        a = self.load("")
        b = self.load("  protects:\n    kind: model-floor\n" + self.WHEN)
        c = self.load('  no_agent: "needs the roster"\n')
        self.assertEqual({a.fingerprint}, {b.fingerprint, c.fingerprint})


class Workspace(unittest.TestCase):

    def make(self, branch):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "WS_ROOT", Path(tmp)), \
                mock.patch.object(run, "BRANCH", branch), \
                mock.patch.object(run, "git_root"), \
                mock.patch.object(run, "shadow_agents") as agents, \
                mock.patch.object(run, "shadow_skills") as skills:
            run.make_workspace(sc())
        return agents, skills

    def test_with_copies_the_catalog_into_the_workspace(self):
        agents, skills = self.make("with")
        agents.assert_called_once()
        skills.assert_called_once()

    def test_without_copies_neither_agents_nor_skills(self):
        agents, skills = self.make("without")
        agents.assert_not_called()
        skills.assert_not_called()


class Command(unittest.TestCase):

    def agent_arg(self, branch, s):
        seen = {}

        def fake_ask(prompt, agent="", *a, **kw):
            seen["agent"] = agent
            return run.Reply(text="", error="stop here")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "WS_ROOT", Path(tmp)), \
                mock.patch.object(run, "BRANCH", branch), \
                mock.patch.object(run, "git_root"), \
                mock.patch.object(run, "shadow_agents"), \
                mock.patch.object(run, "shadow_skills"), \
                mock.patch.object(run, "ask", side_effect=fake_ask):
            run.run_one(s)
        return seen["agent"]

    def test_with_names_the_agent(self):
        self.assertEqual(self.agent_arg("with", sc(agent="qa")), "qa")

    def test_without_names_no_agent(self):
        self.assertEqual(self.agent_arg("without", sc(agent="qa")), "")


class Leaks(unittest.TestCase):

    def check(self, events):
        with mock.patch.object(run, "catalog_skill_names", return_value={"lh-verification"}), \
                mock.patch.object(run, "catalog_agent_names", return_value={"senior-dev", "qa"}):
            return run.without_leaks(events)

    def init(self, skills=(), agents=()):
        return {"type": "system", "subtype": "init", "skills": list(skills), "agents": list(agents)}

    def tool(self, **inp):
        return {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "1", "name": "Bash", "input": inp}]}}

    def test_a_clean_session_has_no_leak(self):
        ev = [self.init(agents=["claude", "Explore", "general-purpose"]), self.tool(command="ls")]
        self.assertEqual(self.check(ev), [])

    def test_an_offered_catalog_skill_or_listed_agent_is_a_leak(self):
        got = self.check([self.init(skills=["lh-verification"], agents=["qa"])])
        self.assertEqual(len(got), 2)

    def test_reading_the_installed_copies_by_path_is_a_leak(self):
        for cmd in ("cat ~/.claude/agents/senior-dev.md", "ls ~/.claude/skills/lh-x",
                    "cat ~/Developer/local-agents/generalist/CORE.md"):
            self.assertEqual(len(self.check([self.tool(command=cmd)])), 1, cmd)

    def test_a_leak_turns_the_sample_into_an_error(self):
        events = [self.init(skills=["lh-verification"])]
        fake = run.Reply(text="answer", events=events)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "WS_ROOT", Path(tmp)), \
                mock.patch.object(run, "BRANCH", "without"), \
                mock.patch.object(run, "git_root"), \
                mock.patch.object(run, "ask", return_value=fake), \
                mock.patch.object(run, "catalog_skill_names", return_value={"lh-verification"}), \
                mock.patch.object(run, "catalog_agent_names", return_value=set()):
            res = run.run_one(sc())
        self.assertTrue(res.reply.error.startswith("without:"))


class NeverCurrent(unittest.TestCase):

    def test_applicability_ignores_the_branch_without(self):
        now = {"agents": {}, "skills": "S", "isolation": "I", "permissions": "P", "scenarios": {}}
        meta = {"model": "sonnet", "fingerprints": {**now, "scenarios": {"x": "fp"}}}
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            for name, extra, status in (("20261020-100000", {}, "PASS"),
                                        ("20261020-110000", {"branch": "without"}, "FAIL")):
                d = runs / name
                d.mkdir()
                (d / "run.json").write_text(json.dumps({**meta, **extra}))
                (d / "trace.jsonl").write_text(json.dumps(
                    {"id": "x", "status": status, "passes": int(status == "PASS"), "repeat": 1}) + "\n")
            with mock.patch.object(run, "RUNS", runs), \
                    mock.patch.object(run, "host_fingerprints", return_value=now):
                rows = run.applicability_data([sc(fingerprint="fp")], "sonnet")
        self.assertEqual((rows[0]["run"], rows[0]["status"]), ("20261020-100000", "PASS"))

    def test_the_viz_never_takes_it_as_a_baseline(self):
        meta = {"fingerprints": {"isolation": "neutral"}, "branch": "without"}
        self.assertFalse(viz.is_neutral(meta))
        self.assertTrue(any("not a baseline" in w for w in viz.run_warnings(meta)))
        self.assertTrue(viz.is_neutral({"fingerprints": {"isolation": "neutral"}}))

    def test_its_cost_does_not_pull_the_estimate_down(self):
        runs = [{"cost": 1.0, "samples": 10, "meta": {"branch": "without"}},
                {"cost": 10.0, "samples": 10, "meta": {}}]
        self.assertEqual(viz.cost_estimate(runs)["per"], 1.0)


def rec(sid, passes, repeat=3, agent="qa", category="judgment"):
    return {"id": sid, "agent": agent, "category": category, "passes": passes,
            "repeat": repeat, "status": "PASS" if passes == repeat else "FAIL"}


class Delta(unittest.TestCase):

    def runs(self):
        con = {"name": "with-run", "meta": {}, "scenarios": [
            rec("a", 3), rec("b", 3), rec("c", 3, agent="dba"), rec("only-with", 3)]}
        sin = {"name": "without-run", "meta": {"branch": "without"}, "scenarios": [
            rec("a", 0, 1), rec("b", 3, 3), rec("c", 1, 1, agent="dba"), rec("only-sin", 1, 1)]}
        return [con, sin]

    def test_delta_is_with_minus_without_per_scenario(self):
        rows = {r["id"]: r for r in viz.delta_rows(self.runs())["rows"]}
        self.assertEqual(rows["a"]["delta"], 1.0)
        self.assertEqual(rows["b"]["delta"], 0.0)
        self.assertEqual(rows["c"]["delta"], 0.0)
        self.assertIsNone(rows["only-sin"]["delta"])
        self.assertNotIn("only-with", rows)

    def test_rolled_up_by_agent_and_category_over_scenarios_with_both(self):
        d = viz.delta_rows(self.runs())
        qa = next(x for x in d["by_agent"] if x["agent"] == "qa")
        self.assertEqual((qa["n"], qa["delta"], qa["zero"]), (2, 0.5, 1))
        cat = d["by_category"][0]
        self.assertEqual((cat["category"], cat["n"]), ("judgment", 3))

    def test_a_design_cell_counts_in_no_average_and_a_kept_zero_is_not_flagged(self):
        d = viz.delta_rows(self.runs(), protects={"b": "design-cell", "c": "model-floor"})
        qa = next(x for x in d["by_agent"] if x["agent"] == "qa")
        self.assertEqual((qa["n"], qa["delta"]), (1, 1.0))      # "b" left out of the rollup
        by_id = {r["id"]: r for r in d["rows"]}
        self.assertEqual(by_id["b"]["kept"], "design-cell")
        self.assertEqual(by_id["a"]["kept"], "")
        html = viz.render_delta(self.runs())
        self.assertIn("kept as", html)

    def test_the_page_names_a_zero_delta_and_needs_a_run_without(self):
        html = viz.render_delta(self.runs())
        self.assertIn("What the catalog adds", html)
        self.assertIn("N/3 in both before concluding", html)
        self.assertEqual(viz.render_delta([self.runs()[0]]), "")


if __name__ == "__main__":
    unittest.main()
