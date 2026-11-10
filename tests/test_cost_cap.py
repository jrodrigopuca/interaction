"""A run never spends past what was approved for it (B-044): a gate before
every launch, a ceiling per sample, and the subscription's five-hour window.
No model call — the runner is a fake with a fixed cost, and the streams are
recorded shapes.

    python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402
import viz   # noqa: E402


def fake_runner(cost=1.0, quotas=None, delay=0.0):
    """A runner whose every sample costs `cost`; the n-th reports quotas[n]."""
    launched = []
    lock = threading.Lock()

    def go(task):
        with lock:
            n = len(launched)
            launched.append(task)
        time.sleep(delay)
        q = {"five_hour": quotas[n]} if quotas and n < len(quotas) else None
        return SimpleNamespace(task=task, cost=cost, quota=q)
    return go, launched


class Gate(unittest.TestCase):

    def test_no_sample_starts_once_the_budget_is_reached(self):
        go, launched = fake_runner(cost=1.0)
        gate = run.Gate(2.5)
        out = run.dispatch(list(range(10)), 1, gate, go)
        self.assertEqual(len(launched), 3)          # 0, 1, 2 → spent 3.0 ≥ 2.5
        self.assertEqual(gate.stopped, "budget")
        self.assertEqual([r.task for r in out], [0, 1, 2])

    def test_overshoot_is_bounded_by_the_samples_in_flight(self):
        go, launched = fake_runner(cost=1.0, delay=0.02)
        gate = run.Gate(2.5)
        run.dispatch(list(range(20)), 4, gate, go)
        self.assertLessEqual(gate.spent - gate.max_cost, 4 * 1.0)
        self.assertLess(len(launched), 20)

    def test_samples_in_flight_finish_and_are_kept(self):
        go, launched = fake_runner(cost=1.0, delay=0.02)
        out = run.dispatch(list(range(20)), 4, run.Gate(2.5), go)
        self.assertEqual(len(out), len(launched))    # nothing launched is dropped
        self.assertEqual([r.task for r in out], sorted(r.task for r in out))

    def test_without_reaching_the_budget_everything_runs(self):
        go, launched = fake_runner(cost=0.1)
        gate = run.Gate(100.0)
        out = run.dispatch(list(range(12)), 3, gate, go)
        self.assertEqual(len(out), 12)
        self.assertEqual(gate.stopped, "")

    def test_the_five_hour_window_stops_launches(self):
        go, launched = fake_runner(cost=0.01, quotas=[0.85, 0.91, 0.92])
        gate = run.Gate(100.0)
        run.dispatch(list(range(10)), 1, gate, go)
        self.assertEqual(len(launched), 2)
        self.assertEqual(gate.stopped, "quota")

    def test_the_record_says_capped_only_when_samples_were_left(self):
        gate = run.Gate(2.5)
        gate.record(3.1, {"five_hour": 0.4, "seven_day": 0.2})
        gate.allows()
        rec = run.budget_record(gate, planned=10, ran=3, repeat=1)
        self.assertTrue(rec["capped"])
        self.assertEqual(rec["stopped_by"], "budget")
        self.assertAlmostEqual(rec["overshoot_usd"], 0.6)
        self.assertEqual(rec["five_hour"], 0.4)
        whole = run.budget_record(run.Gate(5.0), planned=3, ran=3, repeat=1)
        self.assertFalse(whole["capped"])
        self.assertIsNone(whole["stopped_by"])


def stream(*events) -> str:
    return "\n".join(json.dumps(e) for e in events)


RATE = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": {
    "five_hour": {"utilization": 0.11, "resetsAt": 1791955800},
    "seven_day": {"utilization": 0.22, "resetsAt": 1792386000}}}}


class Stream(unittest.TestCase):

    def test_a_sample_cut_by_its_ceiling_keeps_its_cost_and_is_not_a_fail(self):
        r = run.parse_stream(stream(RATE, {"type": "result", "subtype": "error_max_budget_usd",
                                           "total_cost_usd": 1.02, "result": ""}), 1, "")
        self.assertTrue(r.error.startswith("budget"))
        self.assertAlmostEqual(r.cost, 1.02)
        sc = SimpleNamespace(assertions={}, floor="")
        self.assertEqual(run.Result(sc, r).verdict, "ERROR")

    def test_a_failed_call_still_counts_what_it_spent(self):
        r = run.parse_stream(stream({"type": "result", "subtype": "error_during_execution",
                                     "total_cost_usd": 0.3}), 1, "boom")
        self.assertTrue(r.error.startswith("exit 1"))
        self.assertAlmostEqual(r.cost, 0.3)

    def test_the_quota_windows_are_read_from_the_stream(self):
        r = run.parse_stream(stream(RATE, {"type": "result", "subtype": "success",
                                           "total_cost_usd": 0.1, "result": "ok"}))
        self.assertEqual(r.quota["five_hour"], 0.11)
        self.assertEqual(r.quota["seven_day"], 0.22)
        self.assertIsNone(run.quota_of([{"type": "result"}]))

    def test_the_sample_ceiling_follows_the_kind_of_scenario(self):
        single = run.Scenario(id="a", category="judgment", prompt="p")
        heavy = run.Scenario(id="b", category="build-quality", prompt="p", delegate=True)
        self.assertEqual(single.sample_budget, run.SAMPLE_BUDGET_SINGLE)
        self.assertEqual(heavy.sample_budget, run.SAMPLE_BUDGET_HEAVY)
        self.assertEqual(run.estimate([single, heavy], 2), 2 * (run.EST_SINGLE + run.EST_HEAVY))


STAMP = {"catalog_commit": "a" * 40, "catalog_dirty": False,
         "catalog_path": "/somewhere", "installed_at": "2026-10-13T10:00:00-03:00"}


class Capped(unittest.TestCase):

    def test_a_capped_run_is_never_a_baseline(self):
        meta = {"fingerprints": {"isolation": " ".join(run.NEUTRAL_SESSION)},
                "budget": {"capped": True, "max_cost_usd": 5.0, "stopped_by": "budget"}}
        self.assertFalse(viz.is_neutral(meta))
        meta["budget"]["capped"] = False
        self.assertTrue(viz.is_neutral(meta))

    def test_applicability_skips_scenarios_a_capped_run_left_short(self):
        """--repeat 3 cut in its second pass: the scenario with 1 sample is not
        a verdict; the older run's stays the latest."""
        sc = run.load_scenarios()[0]
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            for name, verdict, meta, repeat in (
                    ("20261013-100000", "PASS", {}, 1),
                    ("20261013-110000", "FAIL",
                     {"budget": {"capped": True, "repeat": 3}}, 1)):
                d = runs / name
                d.mkdir()
                (d / "run.json").write_text(json.dumps({"catalog": STAMP, **meta}))
                (d / "trace.jsonl").write_text(
                    json.dumps({"id": sc.id, "status": verdict, "repeat": repeat}) + "\n")
            with mock.patch.object(run, "RUNS", runs), \
                    mock.patch.object(run, "catalog_skill_names", return_value=[]):
                row = run.applicability_data([sc], run.AGENT_MODEL)[0]
        self.assertEqual(row["run"], "20261013-100000")


class MeasuredEstimate(unittest.TestCase):
    """B-044 (b): the estimate is the last measured cost of each scenario as
    it is now, on the same models; the flat rate only where nothing matches."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmp.name)
        self.a = run.Scenario(id="a", category="routing", prompt="p")
        self.b = run.Scenario(id="b", category="judgment", prompt="q")
        self.patch = mock.patch.object(run, "RUNS", self.runs)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def record(self, name, sc, costs, model="sonnet", judge="sonnet", fp=None,
               statuses=None, **meta):
        d = self.runs / name
        d.mkdir()
        (d / "run.json").write_text(json.dumps({
            "model": model, "judge_model": judge, "branch": "with",
            "fingerprints": {"isolation": " ".join(run.NEUTRAL_SESSION),
                             "scenarios": {sc.id: fp or sc.fingerprint}}, **meta}))
        statuses = statuses or ["PASS"] * len(costs)
        (d / "trace.jsonl").write_text(json.dumps({"id": sc.id, "trials": [
            {"status": s, "cost_usd": c} for s, c in zip(statuses, costs)]}) + "\n")

    def costs(self, *scs, model="sonnet", judge="sonnet"):
        return run.measured_costs(list(scs), model, judge)

    def test_a_measured_scenario_is_estimated_at_what_it_cost(self):
        self.record("20261110-100000", self.a, [0.07, 0.08, 0.09])
        m = self.costs(self.a, self.b)
        self.assertAlmostEqual(m["a"], 0.08)
        self.assertNotIn("b", m)
        self.assertAlmostEqual(run.estimate([self.a, self.b], 3, m),
                               3 * (0.08 + run.EST_SINGLE))

    def test_the_latest_matching_run_wins(self):
        self.record("20261110-100000", self.a, [0.50])
        self.record("20261110-110000", self.a, [0.10])
        self.assertAlmostEqual(self.costs(self.a)["a"], 0.10)

    def test_another_model_or_judge_is_not_this_scenarios_cost(self):
        self.record("20261110-100000", self.a, [0.02], model="haiku")
        self.record("20261110-110000", self.a, [0.30], judge="opus")
        self.assertEqual(self.costs(self.a), {})
        self.assertAlmostEqual(self.costs(self.a, model="haiku")["a"], 0.02)

    def test_a_scenario_that_changed_since_is_not_measured(self):
        self.record("20261110-100000", self.a, [0.07], fp="an-older-fingerprint")
        self.assertEqual(self.costs(self.a), {})

    def test_the_other_branch_an_override_and_an_experiment_do_not_count(self):
        self.record("20261110-100000", self.a, [0.07], branch="without")
        self.record("20261110-110000", self.a, [0.07], agent_override="qa")
        self.record("20261110-120000", self.a, [0.07], experiment="a probe")
        self.assertEqual(self.costs(self.a), {})

    def test_a_sample_that_errored_is_left_out_of_the_mean(self):
        self.record("20261110-100000", self.a, [0.10, 1.00], statuses=["PASS", "ERROR"])
        self.assertAlmostEqual(self.costs(self.a)["a"], 0.10)
        self.record("20261110-110000", self.b, [1.00], statuses=["ERROR"])
        self.assertNotIn("b", self.costs(self.b))

    def test_the_note_says_how_much_is_measured(self):
        both = [self.a, self.b]
        self.assertIn("not calibrated for opus", run.estimate_note(both, {}, "opus"))
        note = run.estimate_note(both, {"a": 0.08}, "sonnet")
        self.assertIn("1 measured on sonnet, 1 not yet", note)
        self.assertIn("b", note)
        self.assertEqual(run.estimate_note(both, {"a": 0.08, "b": 0.2}, "sonnet"),
                         "every scenario measured on sonnet")


if __name__ == "__main__":
    unittest.main()
