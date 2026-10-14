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


if __name__ == "__main__":
    unittest.main()
