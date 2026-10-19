"""B-062: measuring a skill's value as the same task with and without it, and
recording the host's own skills beside ours. No model call: the events are
recorded shapes, the agents and skills dirs are temp dirs, ask() is mocked.

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

CATALOG = frozenset({"lh-pairing", "lh-code-audit", "lh-verification"})


def call(name, uid, parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [
        {"type": "tool_use", "id": uid, "name": "Skill", "input": {"skill": name}}]}}


def result(uid, error=False):
    return {"type": "user", "parent_tool_use_id": None, "message": {"content": [
        {"type": "tool_result", "tool_use_id": uid, "is_error": error, "content": "x"}]}}


def tool(name, uid, **inp):
    return {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
        {"type": "tool_use", "id": uid, "name": name, "input": inp}]}}


def init(*skills):
    return {"type": "system", "subtype": "init", "skills": list(skills)}


class FailedSkillCalls(unittest.TestCase):

    def test_a_call_that_errored_did_not_load(self):
        ev = [call("lh-code-audit", "t1"), result("t1", error=True)]
        self.assertEqual(run.loaded_skills(ev), set())
        out = run.skill_failures({"expect_skills": ["lh-code-audit"]}, ev)
        self.assertTrue(out and out[0].startswith("did not load"))

    def test_a_call_that_succeeded_loaded(self):
        ev = [call("lh-code-audit", "t1"), result("t1")]
        self.assertEqual(run.loaded_skills(ev), {"lh-code-audit"})

    def test_a_call_with_no_result_yet_still_counts(self):
        """A budget cut can land between the call and its result; that case
        kept its old meaning (cut_skill_verdict relies on it)."""
        self.assertEqual(run.loaded_skills([call("lh-code-audit", "t1")]), {"lh-code-audit"})

    def test_order_and_flags_are_kept(self):
        ev = [call("lh-x", "a"), result("a", error=True), call("plug:lh-y", "b"), result("b")]
        self.assertEqual(run.skill_calls(ev), [("lh-x", False), ("lh-y", True)])


class HostCells(unittest.TestCase):

    def setUp(self):
        p = mock.patch.object(run, "catalog_names_or_none", return_value=CATALOG)
        p.start()
        self.addCleanup(p.stop)

    def sc(self, expected=("lh-pairing",)):
        return run.Scenario(id="x", category="skill-trigger", prompt="p",
                            assertions={"expect_skills": list(expected)})

    def ev(self, *names):
        out = []
        for i, n in enumerate(names):
            out += [call(n, f"t{i}"), result(f"t{i}")]
        return out

    def test_the_four_cells(self):
        cases = {("lh-pairing", "code-review"): "ours+host", ("lh-pairing",): "ours",
                 ("code-review",): "host", (): "none"}
        for names, cell in cases.items():
            self.assertEqual(run.skill_cell(self.sc(), self.ev(*names)), cell, names)

    def test_ours_is_the_expected_skill_not_any_catalog_skill(self):
        """lh-verification + code-review in place of lh-pairing hides failure
        (c) if "ours" meant the catalog: it is the host cell."""
        self.assertEqual(run.skill_cell(self.sc(), self.ev("lh-verification", "code-review")),
                         "host")
        self.assertEqual(run.skill_cell(self.sc(), self.ev("lh-verification")), "none")

    def test_host_skills_are_whatever_is_not_the_catalog(self):
        self.assertEqual(run.host_skills(self.ev("lh-pairing", "simplify", "code-review")),
                         ["code-review", "simplify"])

    def test_no_cell_without_expect_skills(self):
        self.assertIsNone(run.skill_cell(self.sc(expected=()), self.ev("code-review")))

    def test_first_load_index_counts_only_loads(self):
        ev = [call("code-review", "a"), result("a", error=True)] + self.ev("simplify", "lh-pairing")
        self.assertEqual(run.first_load_index(ev, ["lh-pairing"]), 1)
        self.assertEqual(run.first_load_index(ev, ["code-review"]), None)
        self.assertEqual(run.first_load_index(ev, ["simplify"]), 0)

    def test_report_names_the_host_instead_of_ours(self):
        sc = self.sc()
        trials = [run.Result(sc, run.Reply(text="ok", events=self.ev(*names)))
                  for names in (("code-review",), ("lh-pairing",), ("lh-pairing", "simplify"))]
        agg = run.Aggregate(sc, trials)
        lines = run.skill_cell_lines([agg])
        self.assertIn("ours+host 1 · ours 1 · host instead of ours 1 · none 0", lines[0])
        self.assertIn("x (code-review)", lines[1])

    def test_trial_record_carries_them(self):
        sc = self.sc()
        rec = run.trial_record(run.Result(sc, run.Reply(
            text="ok", events=[call("lh-x", "z"), result("z", error=True)]
            + self.ev("code-review", "lh-pairing"))))
        self.assertEqual(rec["skills_loaded"], ["code-review", "lh-pairing"])
        self.assertEqual(rec["skills_refused"], ["lh-x"])
        self.assertEqual(rec["host_skills"], ["code-review"])
        self.assertEqual(rec["skill_cell"], "ours+host")
        self.assertEqual(rec["first_load"], {"expected": 1, "host": 0})

    def test_an_unreadable_catalog_records_unknown_not_empty(self):
        with mock.patch.object(run, "catalog_names_or_none", return_value=None):
            self.assertIsNone(run.host_skills(self.ev("code-review")))
            self.assertIsNone(run.skill_cell(self.sc(), self.ev("code-review")))


class Leaks(unittest.TestCase):

    def test_an_ablated_name_still_in_init_is_a_leak(self):
        out = run.ablation_leaks(["simplify"], [init("lh-pairing", "simplify")])
        self.assertEqual(out, ["`simplify` is still offered to the model (init skills)"])

    def test_reading_its_installed_copy_is_a_leak(self):
        for ev in (tool("Read", "r", file_path="/Users/u/.claude/skills/lh-code-audit/SKILL.md"),
                   tool("Bash", "b", command="cat ~/.claude/skills/lh-code-audit/SKILL.md")):
            self.assertEqual(run.ablation_leaks(["lh-code-audit"], [init("lh-pairing"), ev]),
                             ["`lh-code-audit` read by path (%s)" % ev["message"]["content"][0]["name"]])

    def test_a_skill_call_or_a_lookalike_name_is_not_a_leak(self):
        ev = [init("lh-pairing"), call("lh-code-audit", "t"), result("t", error=True),
              tool("Read", "r", file_path="src/lh-code-auditor/x.mjs"),
              tool("Bash", "b", command="grep -rn sqlIdent src")]
        self.assertEqual(run.ablation_leaks(["lh-code-audit"], ev), [])

    def test_run_one_turns_a_leak_into_an_error(self):
        sc = run.Scenario(id="x", category="skill-value", prompt="p", agent="security",
                          ablate=("simplify",))
        reply = run.Reply(text="ok", events=[init("simplify")])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "ask", return_value=reply) as ask, \
                mock.patch.object(run, "catalog_skill_names", return_value=set(CATALOG)), \
                mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
            res = run.run_one(sc)
        self.assertEqual(res.verdict, "ERROR")
        self.assertIn("ablate:", res.reply.error)
        self.assertEqual(ask.call_args.kwargs["skill_overrides"], {"simplify": "off"})


class Wiring(unittest.TestCase):

    def test_host_names_go_to_overrides_and_catalog_names_do_not(self):
        with mock.patch.object(run, "catalog_skill_names", return_value=set(CATALOG)):
            self.assertEqual(run.ablation_split(["lh-pairing", "simplify"]),
                             (("lh-pairing",), ("simplify",)))
            self.assertEqual(run.ablation_split(()), ((), ()))

    def test_one_settings_flag_carries_permissions_and_overrides(self):
        fake = SimpleNamespace(stdout="", returncode=0, stderr="")
        with mock.patch.object(run.subprocess, "run", return_value=fake) as sp:
            run.ask("p", refuse="Edit", neutral=True, skill_overrides={"simplify": "off"})
        cmd = sp.call_args.args[0]
        self.assertEqual(cmd.count("--settings"), 1)
        settings = json.loads(cmd[cmd.index("--settings") + 1])
        self.assertEqual(settings["skillOverrides"], {"simplify": "off"})
        self.assertNotIn("Edit", settings["permissions"]["allow"])

    def test_no_overrides_leaves_the_settings_as_before(self):
        fake = SimpleNamespace(stdout="", returncode=0, stderr="")
        with mock.patch.object(run.subprocess, "run", return_value=fake) as sp:
            run.ask("p", neutral=True)
        cmd = sp.call_args.args[0]
        self.assertEqual(json.loads(cmd[cmd.index("--settings") + 1]),
                         {"permissions": run.HARNESS_PERMISSIONS})

    def test_host_overrides_outside_the_neutral_session_are_an_error(self):
        with mock.patch.object(run.subprocess, "run") as sp:
            reply = run.ask("p", neutral=False, skill_overrides={"simplify": "off"})
        self.assertIn("neutral session", reply.error)
        sp.assert_not_called()

    def test_ablated_catalog_skill_is_not_copied_and_its_row_is_dropped(self):
        agent = ("---\nname: security\nmemory: user\n---\n\n## Skills\n\n| Skill | When |\n|---|---|\n"
                 "| `lh-threat-modeling` | Mapping |\n| `lh-code-audit` | Auditing |\n"
                 "| `lh-remediation` | Fixing |\n")
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as ws:
            agents, skills = Path(home) / "agents", Path(home) / "skills"
            agents.mkdir()
            (agents / "security.md").write_text(agent, encoding="utf-8")
            for n in ("lh-threat-modeling", "lh-code-audit"):
                (skills / n).mkdir(parents=True)
                (skills / n / "SKILL.md").write_text("x")
            with mock.patch.object(run, "AGENTS_DIR", agents), \
                    mock.patch.object(run, "INSTALLED_AGENTS", agents), \
                    mock.patch.object(run, "catalog_skill_names",
                                      return_value={"lh-threat-modeling", "lh-code-audit"}):
                run.shadow_agents(Path(ws), "", drop_skills=("lh-code-audit",))
                run.shadow_skills(Path(ws), skip=("lh-code-audit",))
            got = (Path(ws) / ".claude" / "agents" / "security.md").read_text(encoding="utf-8")
            copied = sorted(p.name for p in (Path(ws) / ".claude" / "skills").iterdir())
        self.assertNotIn("lh-code-audit", got)
        self.assertIn("| `lh-threat-modeling` | Mapping |\n| `lh-remediation` | Fixing |", got)
        self.assertEqual(copied, ["lh-threat-modeling"])


BASE = ("- id: with\n  category: skill-value\n  agent: security\n  prompt: p\n"
        "  assert:\n    judge: j\n")


class Loader(unittest.TestCase):

    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text(text)
            with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                return run.load_scenarios()

    def test_a_twin_with_the_same_entry_loads(self):
        got = self.load(BASE + BASE.replace("id: with", "id: without")
                        + "  ablate: [lh-code-audit]\n")
        self.assertEqual([s.ablate for s in got], [(), ("lh-code-audit",)])
        self.assertEqual(got[0].twin_key, got[1].twin_key)
        self.assertNotEqual(got[0].fingerprint, got[1].fingerprint)

    def test_a_yaml_merge_twin_loads(self):
        text = ("- &w\n  id: with\n  category: skill-value\n  agent: security\n  prompt: p\n"
                "  assert:\n    judge: j\n- <<: *w\n  id: without\n  ablate: [lh-code-audit]\n")
        self.assertEqual(len(self.load(text)), 2)

    def test_ablate_without_an_identical_twin_is_refused(self):
        without = BASE.replace("id: with", "id: without") + "  ablate: [lh-code-audit]\n"
        for twin in (BASE.replace("judge: j", "judge: other"),     # another criterion
                     BASE.replace("prompt: p", "prompt: q"),       # another prompt
                     ""):                                          # no twin at all
            with self.assertRaises(SystemExit):
                self.load(twin + without)

    def test_bad_ablate_values_are_refused(self):
        for value in ("[]", "[lh-a, lh-a]", "['has space']", "[1]", "{a: b}"):
            with self.assertRaises(SystemExit, msg=value):
                self.load(BASE + BASE.replace("id: with", "id: without")
                          + f"  ablate: {value}\n")

    def test_ablating_an_expected_skill_is_refused(self):
        text = ("- id: x\n  category: c\n  prompt: p\n  assert:\n    expect_skills: [lh-a]\n"
                "  ablate: [lh-a]\n")
        with self.assertRaises(SystemExit):
            self.load(text)


class StrictKeys(unittest.TestCase):

    def load(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text("- id: x\n  category: c\n  prompt: p\n" + extra)
            with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                return run.load_scenarios()

    def refused(self, extra, needle):
        with self.assertRaises(SystemExit) as ctx:
            self.load(extra)
        self.assertIn(needle, str(ctx.exception))

    def test_an_unknown_top_level_key_stops_the_load(self):
        self.refused("  ablation: [lh-a]\n", "unknown key `ablation`")

    def test_an_unknown_assert_key_stops_the_load(self):
        self.refused("  assert:\n    forbid_skill: [lh-a]\n", "`assert.forbid_skill`")

    def test_a_reply_check_in_observe_stops_the_load(self):
        """observe_results runs only action checks; `matches` there was ignored."""
        self.refused("  assert:\n    observe:\n      matches: x\n", "`assert.observe.matches`")

    def test_an_unknown_exec_key_stops_the_load(self):
        self.refused("  exec:\n    suite: s\n    symbl: f\n", "`exec.symbl`")

    def test_every_key_is_named_at_once(self):
        with self.assertRaises(SystemExit) as ctx:
            self.load("  foo: 1\n  assert:\n    bar: 2\n")
        self.assertIn("`foo`", str(ctx.exception))
        self.assertIn("`assert.bar`", str(ctx.exception))

    def test_known_keys_load(self):
        got = self.load("  agent: qa\n  manual: true\n  budget: 2\n  assert:\n"
                        "    expect_skills: [lh-a]\n    min_score: 0.5\n    judge: j\n"
                        "    observe:\n      expect_skills: [lh-b]\n      unchanged_files: [a]\n"
                        "  exec:\n    suite: s\n    symbol: f\n    from_file: g\n")
        self.assertEqual(got[0].id, "x")


if __name__ == "__main__":
    unittest.main()
