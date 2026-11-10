"""--resume finishes a capped run paying only the samples it still owes, and
merges them into the same run folder (B-044, part b). No model call: the
samples are built by hand and `run_one` is a fake.

    python3 -m unittest discover -s tests
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402

STAMP = {"catalog_commit": "a" * 40, "catalog_dirty": False,
         "installed_at": "2026-11-10T10:00:00-03:00"}
PRINTS = {"harness": {"commit": "h1"}, "agents": {"qa": "x"}, "skills": "s",
          "isolation": "neutral", "permissions": "p",
          "scenarios": {"a": "fa", "b": "fb"}}


def sample(sc, text="ok", fails=(), cost=0.10):
    return run.Result(sc=sc, reply=run.Reply(text=text, cost=cost, model="claude-sonnet-5-5"),
                      fails=list(fails))


def capped_meta(**over):
    meta = {"model": "sonnet", "judge_model": "sonnet", "branch": "with",
            "catalog": dict(STAMP), "fingerprints": json.loads(json.dumps(PRINTS)),
            "budget": {"max_cost_usd": 0.25, "cost_usd": 0.30, "overshoot_usd": 0.05,
                       "capped": True, "stopped_by": "budget", "samples_planned": 6,
                       "samples_run": 3, "repeat": 3, "five_hour": 0.2, "seven_day": 0.1}}
    meta.update(over)
    return meta


class Refusal(unittest.TestCase):

    def test_a_capped_run_on_the_same_install_can_be_resumed(self):
        self.assertEqual(run.resume_refusal(capped_meta(), PRINTS, STAMP), "")

    def test_the_harness_commit_alone_does_not_block(self):
        now = dict(PRINTS, harness={"commit": "h2", "dirty": True})
        self.assertEqual(run.resume_refusal(capped_meta(), now, STAMP), "")

    def test_a_complete_run_has_nothing_to_resume(self):
        meta = capped_meta()
        meta["budget"]["capped"] = False
        self.assertIn("not capped", run.resume_refusal(meta, PRINTS, STAMP))
        self.assertIn("no budget record", run.resume_refusal({"catalog": STAMP}, PRINTS, STAMP))

    def test_a_reinstall_since_blocks(self):
        later = dict(STAMP, installed_at="2026-11-10T12:00:00-03:00")
        self.assertIn("reinstalled since", run.resume_refusal(capped_meta(), PRINTS, later))
        self.assertIn("while it ran",
                      run.resume_refusal(capped_meta(catalog_changed=True), PRINTS, STAMP))

    def test_a_changed_scenario_agent_or_permission_blocks_and_is_named(self):
        for key, value in (("scenarios", {"a": "fa", "b": "CHANGED"}),
                           ("agents", {"qa": "y"}), ("permissions", "q")):
            why = run.resume_refusal(capped_meta(), dict(PRINTS, **{key: value}), STAMP)
            self.assertIn(key, why)


class Merge(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "20261110-100000"
        self.a = run.Scenario(id="a", category="judgment", prompt="pa", agent="qa")
        self.b = run.Scenario(id="b", category="judgment", prompt="pb", agent="qa")
        # The capped run: three samples of `a` (all green), none of `b`.
        run.persist([run.Aggregate(self.a, [sample(self.a) for _ in range(3)])], self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_the_samples_still_owed_are_planned_in_whole_passes(self):
        owed = run.missing_samples([self.a, self.b], run.read_records(self.out), 3)
        self.assertEqual([s.id for s in owed], ["b", "b", "b"])
        (self.out / "trace.jsonl").write_text(json.dumps(
            {"id": "a", "trials": [{"status": "PASS"}]}) + "\n")
        owed = run.missing_samples([self.a, self.b], run.read_records(self.out), 3)
        self.assertEqual([s.id for s in owed], ["b", "a", "b", "a", "b"])

    def test_new_samples_join_the_stored_ones_and_the_status_is_recomputed(self):
        old = run.scenario_record(run.Aggregate(self.a, [sample(self.a)]))
        new = run.scenario_record(run.Aggregate(self.a, [
            sample(self.a), sample(self.a, text="bad", fails=["did not match"])]))
        rec = run.merge_record(old, new)
        self.assertEqual((rec["status"], rec["passes"], rec["repeat"]), ("FLAKY", 2, 3))
        self.assertEqual(rec["tally"], {"PASS": 2, "FAIL": 1})
        self.assertAlmostEqual(rec["cost_usd"], 0.30)
        # the stored lead was green: the first failure takes its place
        self.assertEqual((rec["reply"], rec["failures"]), ("bad", ["did not match"]))

    def test_a_stored_failing_lead_is_kept(self):
        old = run.scenario_record(run.Aggregate(self.a, [sample(self.a, "first", ["x"])]))
        new = run.scenario_record(run.Aggregate(self.a, [sample(self.a, "second", ["y"])]))
        rec = run.merge_record(old, new)
        self.assertEqual((rec["status"], rec["reply"]), ("FAIL", "first"))

    def test_the_run_folder_ends_up_whole(self):
        (self.out / "trace.jsonl").write_text(json.dumps(run.scenario_record(
            run.Aggregate(self.a, [sample(self.a)]))) + "\n")
        (self.out / "a.md").write_text(run.scenario_markdown(
            run.Aggregate(self.a, [sample(self.a)])))
        aggs = [run.Aggregate(self.a, [sample(self.a), sample(self.a, "bad", ["nope"])]),
                run.Aggregate(self.b, [sample(self.b) for _ in range(3)])]
        merged = run.merge_into(self.out, [self.a, self.b], aggs, "20261110-120000")
        self.assertEqual({k: (v["status"], v["repeat"]) for k, v in merged.items()},
                         {"a": ("FLAKY", 3), "b": ("PASS", 3)})
        self.assertEqual(run.read_records(self.out).keys(), merged.keys())
        md = (self.out / "a.md").read_text()
        self.assertTrue(md.startswith("# a  (FLAKY  2/3)"))
        self.assertIn("- cost: $0.3000", md)
        self.assertIn("## Resumed 20261110-120000: samples 2 to 3 of 3", md)
        self.assertIn("## Sample 3/3 — FAIL", md)
        self.assertTrue((self.out / "b.md").read_text().startswith("# b  (PASS  3/3)"))

    def test_the_budget_adds_up_and_stops_being_capped_when_complete(self):
        old = capped_meta()["budget"]
        gate = run.Gate(1.00)
        gate.record(0.30, {"five_hour": 0.4})
        done = run.merged_budget(old, gate, ran=3)
        self.assertEqual((done["capped"], done["stopped_by"], done["samples_run"]),
                         (False, None, 6))
        self.assertAlmostEqual(done["cost_usd"], 0.60)
        self.assertAlmostEqual(done["max_cost_usd"], 1.25)
        self.assertEqual((done["overshoot_usd"], done["five_hour"], done["seven_day"]),
                         (0.0, 0.4, 0.1))
        gate.stopped = "budget"
        short = run.merged_budget(old, gate, ran=2)
        self.assertEqual((short["capped"], short["stopped_by"]), (True, "budget"))


class EndToEnd(unittest.TestCase):
    """main() with --resume: the selection and the models come from the run,
    only the missing samples are taken, and the run folder is completed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmp.name) / "runs"
        self.out = self.runs / "20261110-100000"
        self.a = run.Scenario(id="a", category="judgment", prompt="pa", agent="qa")
        self.b = run.Scenario(id="b", category="judgment", prompt="pb", agent="qa")
        run.persist([run.Aggregate(self.a, [sample(self.a) for _ in range(3)])], self.out)
        self.prints = dict(PRINTS, scenarios={"a": self.a.fingerprint, "b": self.b.fingerprint})
        (self.out / "run.json").write_text(json.dumps(capped_meta(fingerprints=self.prints)))
        self.manifest = Path(self.tmp.name) / "home" / ".local-agents.json"
        self.manifest.parent.mkdir()
        self.manifest.write_text(json.dumps(STAMP))
        self.taken = []

    def tearDown(self):
        self.tmp.cleanup()

    def main(self, *argv, stamp=None):
        if stamp:
            self.manifest.write_text(json.dumps(stamp))

        def fake(sc):
            self.taken.append(sc.id)
            return sample(sc)
        patches = [
            mock.patch.object(run, "RUNS", self.runs),
            mock.patch.object(run, "INSTALLED_AGENTS", self.manifest.parent / "agents"),
            mock.patch.object(run, "load_scenarios", return_value=[self.a, self.b]),
            mock.patch.object(run, "host_fingerprints", return_value=self.prints),
            mock.patch.object(run, "expired_experiments", return_value=[]),
            mock.patch.object(run, "run_one", side_effect=fake),
            mock.patch.object(sys, "argv", ["run.py", *argv]),
        ]
        out = io.StringIO()
        for p in patches:
            p.start()
        try:
            with redirect_stdout(out):
                try:
                    code = run.main()
                except SystemExit as e:
                    code = e.code
        finally:
            for p in reversed(patches):
                p.stop()
        return code, out.getvalue()

    def test_it_takes_only_what_is_owed_and_the_run_stops_being_capped(self):
        code, out = self.main("--resume", "20261110-100000", "--max-cost-usd", "2")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.taken, ["b", "b", "b"])
        meta = json.loads((self.out / "run.json").read_text())
        self.assertFalse(meta["budget"]["capped"])
        self.assertEqual(meta["budget"]["samples_run"], 6)
        self.assertEqual(meta["resumed"][0]["samples_run"], 3)
        self.assertEqual(meta["catalog"], STAMP)
        records = run.read_records(self.out)
        self.assertEqual({k: v["repeat"] for k, v in records.items()}, {"a": 3, "b": 3})
        self.assertFalse((self.out / "partial.jsonl").exists())
        self.assertEqual([p.name for p in self.runs.iterdir()], ["20261110-100000"])

    def test_a_reinstall_since_refuses_before_any_sample(self):
        later = dict(STAMP, installed_at="2026-11-10T12:00:00-03:00")
        code, _ = self.main("--resume", "20261110-100000", "--max-cost-usd", "2", stamp=later)
        self.assertIn("reinstalled since", str(code))
        self.assertEqual(self.taken, [])
        self.assertTrue(json.loads((self.out / "run.json").read_text())["budget"]["capped"])

    def test_the_dry_run_says_what_is_owed_and_spends_nothing(self):
        code, out = self.main("--resume", "20261110-100000", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("3 sample(s) still owed", out)
        self.assertEqual(self.taken, [])


if __name__ == "__main__":
    unittest.main()
