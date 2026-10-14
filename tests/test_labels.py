"""labels.py calibrates the judge against a human (B-039). The tests pin the
parts whose failure would quietly spoil the measurement: the labeller never
sees the judge, the holdout is fixed and holds both kinds, labels are tied to
the criterion text, and TPR/TNR count what they claim. No model call.

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
import labels   # noqa: E402
import run      # noqa: E402


def sample(i, verdict, old=False, cat="judgment"):
    return {"key": f"r/{i}", "run": "r", "id": f"s{i}", "category": cat, "agent": "a",
            "prompt": "p", "criterion": "PASS if X", "criterion_sha": run.criterion_sha("PASS if X"),
            "graded": f"reply {i}", "old_version": old, "_verdict": verdict, "_why": "because"}


def write_run(root: Path, name: str, records: list, meta: dict = None):
    d = root / name
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps(meta or {}))
    (d / "trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))


EVENTS = [{"type": "assistant", "parent_tool_use_id": None,
           "message": {"role": "assistant", "content": [{"type": "text", "text": "first I checked"}]}}]


class Samples(unittest.TestCase):

    def test_only_judged_samples_with_events_and_a_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_run(Path(tmp), "20261001-000000", [
                {"id": "a", "assert": {"judge": "PASS if X"}, "judge": {"verdict": True},
                 "events": EVENTS, "reply": "done"},
                {"id": "b", "assert": {"judge": "PASS if X"}, "judge": {"verdict": None},
                 "events": EVENTS, "reply": "x"},                      # no verdict
                {"id": "c", "assert": {"contains": ["y"]}, "events": EVENTS},  # not judged
                {"id": "d", "assert": {"judge": "PASS if X"}, "judge": {"verdict": False},
                 "reply": "no events"}], {"experiment": "old agent"})
            got = labels.judged_samples(Path(tmp))
        self.assertEqual([s["id"] for s in got], ["a"])
        self.assertIn("first I checked", got[0]["graded"])        # the whole transcript
        self.assertTrue(got[0]["old_version"])


class Pick(unittest.TestCase):

    def pool(self):
        return [sample(i, "FAIL", old=i % 2 == 0) for i in range(10)] + \
               [sample(100 + i, "PASS", old=i < 30) for i in range(200)]

    def test_takes_every_fail_and_fills_with_passes(self):
        got = labels.pick(self.pool(), 60, seed=1)
        self.assertEqual(len(got), 60)
        self.assertEqual(sum(s["_verdict"] == "FAIL" for s in got), 10)

    def test_is_reproducible_from_its_seed(self):
        a = [s["key"] for s in labels.pick(self.pool(), 60, seed=7)]
        b = [s["key"] for s in labels.pick(self.pool(), 60, seed=7)]
        self.assertEqual(a, b)

    def test_the_holdout_holds_both_kinds_at_the_set_share(self):
        got = labels.pick(self.pool(), 60, seed=1)
        for v in ("PASS", "FAIL"):
            group = [s for s in got if s["_verdict"] == v]
            held = sum(s["split"] == "holdout" for s in group)
            self.assertEqual(held, round(len(group) * labels.HOLDOUT_SHARE))

    def test_identical_replies_count_once(self):
        dup = [sample(1, "PASS"), dict(sample(1, "PASS"), key="r2/1")]
        self.assertEqual(len(labels.pick(dup, 10, seed=1)), 1)

    def test_pick_refuses_to_redraw_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            cand = Path(tmp) / "candidates.jsonl"
            cand.write_text("{}\n")
            with mock.patch.object(labels, "CANDIDATES", cand), self.assertRaises(SystemExit):
                labels.cmd_pick(SimpleNamespace(force=False, runs=Path(tmp), n=1, seed=1))


class Hidden(unittest.TestCase):

    def test_the_labeller_never_sees_the_judge(self):
        page = labels.build_page([labels.public(sample(1, "FAIL"))], {})
        self.assertNotIn("_verdict", page)
        self.assertNotIn("because", page)            # the judge's reason
        self.assertNotIn("_why", page)

    def test_a_reply_cannot_close_the_script_tag(self):
        s = labels.public(dict(sample(1, "PASS"), graded="ok </script><b>x"))
        page = labels.build_page([s], {})
        self.assertEqual(page.count("</script>"), 1)


class Merge(unittest.TestCase):

    def cands(self):
        return [dict(labels.public(sample(i, "PASS")), split="dev") for i in range(3)]

    def test_a_label_is_tied_to_its_criterion_and_split(self):
        rows = labels.merge([], [{"key": "r/1", "label": "FAIL", "note": "n"}], self.cands())
        self.assertEqual(rows[0]["criterion_sha"], run.criterion_sha("PASS if X"))
        self.assertEqual(rows[0]["split"], "dev")

    def test_a_newer_label_replaces_the_older(self):
        old = labels.merge([], [{"key": "r/1", "label": "FAIL"}], self.cands())
        new = labels.merge(old, [{"key": "r/1", "label": "PASS"}], self.cands())
        self.assertEqual([r["label"] for r in new], ["PASS"])

    def test_unknown_keys_and_values_are_refused(self):
        with self.assertRaises(SystemExit):
            labels.merge([], [{"key": "nope", "label": "PASS"}], self.cands())
        with self.assertRaises(SystemExit):
            labels.merge([], [{"key": "r/1", "label": "MAYBE"}], self.cands())


class Rates(unittest.TestCase):

    def test_tpr_and_tnr_and_what_is_left_out(self):
        rows = ([{"label": "PASS", "judge": "PASS"}] * 8 + [{"label": "PASS", "judge": "FAIL"}] * 2 +
                [{"label": "FAIL", "judge": "FAIL"}] * 9 + [{"label": "FAIL", "judge": "PASS"}] * 1 +
                [{"label": "AMBIGUA", "judge": "PASS"}] + [{"label": "FAIL", "judge": "ERROR"}])
        r = labels.rates(rows)
        self.assertAlmostEqual(r["tpr"], 0.8)
        self.assertAlmostEqual(r["tnr"], 0.9)
        self.assertEqual((r["ambiguous"], r["no_verdict"]), (1, 1))

    def test_no_failures_means_no_tnr_not_a_perfect_one(self):
        self.assertIsNone(labels.rates([{"label": "PASS", "judge": "PASS"}])["tnr"])


class Rejudge(unittest.TestCase):

    def test_stops_at_its_budget_and_keeps_the_criterion_hash(self):
        cands = [dict(labels.public(sample(i, "PASS")), split="dev") for i in range(5)]
        human = [{"key": c["key"], "label": "PASS"} for c in cands]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            with mock.patch.object(labels, "LABELS", t), \
                    mock.patch.object(labels, "CANDIDATES", t / "c.jsonl"), \
                    mock.patch.object(labels, "HUMAN", t / "h.jsonl"), \
                    mock.patch.object(run, "judge", return_value=(True, "ok", 0.5)) as judge, \
                    mock.patch("builtins.print"):
                labels.write_jsonl(t / "c.jsonl", cands)
                labels.write_jsonl(t / "h.jsonl", human)
                labels.cmd_rejudge(SimpleNamespace(judge_model="opus", max_cost_usd=1.0, all=False))
                out = labels.read_jsonl(next(t.glob("rejudge-opus-*.jsonl")))
        self.assertEqual(judge.call_count, 2)         # 0.5 + 0.5 reaches 1.0
        self.assertEqual(out[0]["criterion_sha"], cands[0]["criterion_sha"])
        self.assertEqual(out[0]["judge"], "PASS")


if __name__ == "__main__":
    unittest.main()
