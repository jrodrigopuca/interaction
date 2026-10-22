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


    def test_every_sample_of_a_repeat_run_with_its_own_key(self):
        trials = [{"judge": {"verdict": True}, "graded": "lead"},
                  {"judge": {"verdict": False, "why": "no"}, "graded": "second"},
                  {"judge": {"verdict": None}, "graded": "unjudged"}]
        with tempfile.TemporaryDirectory() as tmp:
            write_run(Path(tmp), "20261001-000000", [
                {"id": "a", "assert": {"judge": "PASS if X"}, "judge": {"verdict": True},
                 "events": EVENTS, "reply": "done", "trials": trials}])
            got = labels.judged_samples(Path(tmp))
        self.assertEqual([s["key"] for s in got], ["20261001-000000/a", "20261001-000000/a#2"])
        self.assertEqual((got[1]["graded"], got[1]["_verdict"]), ("second", "FAIL"))


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

    def test_a_scenario_never_sits_on_both_sides(self):
        pool = [dict(sample(i, "FAIL" if i % 4 == 0 else "PASS"), id=f"sc{i % 7}") for i in range(40)]
        sides = {}
        for s in labels.pick(pool, 40, seed=3):
            sides.setdefault(s["id"], set()).add(s["split"])
        self.assertTrue(all(len(v) == 1 for v in sides.values()))
        self.assertIn({"holdout"}, sides.values())

    def test_identical_replies_count_once(self):
        dup = [sample(1, "PASS"), dict(sample(1, "PASS"), key="r2/1")]
        self.assertEqual(len(labels.pick(dup, 10, seed=1)), 1)

    def test_pick_refuses_to_redraw_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            cand = Path(tmp) / "candidates.jsonl"
            cand.write_text("{}\n")
            with mock.patch.object(labels, "CANDIDATES", cand), self.assertRaises(SystemExit):
                labels.cmd_pick(SimpleNamespace(force=False, runs=Path(tmp), n=1, seed=1))


class Resplit(unittest.TestCase):

    def run_in(self, tmp, cands, human, verdicts, **kw):
        t = Path(tmp)
        patches = [mock.patch.object(labels, n, t / f) for n, f in
                   (("CANDIDATES", "c.jsonl"), ("HUMAN", "h.jsonl"),
                    ("VERDICTS", "v.jsonl"), ("PICK", "pick.json"))]
        for pt in patches:
            pt.start()
        try:
            labels.write_jsonl(t / "c.jsonl", cands)
            labels.write_jsonl(t / "h.jsonl", human)
            labels.write_jsonl(t / "v.jsonl", verdicts)
            with mock.patch("builtins.print"):
                labels.cmd_resplit(SimpleNamespace(seed=1, why="", **kw))
            return (labels.read_jsonl(t / "c.jsonl"), labels.read_jsonl(t / "h.jsonl"),
                    json.loads((t / "pick.json").read_text()))
        finally:
            for pt in patches:
                pt.stop()

    def data(self):
        cands = [dict(labels.public(sample(i, "PASS")), id=f"sc{i % 10}", key=f"r/sc{i % 10}-{i}",
                      split="dev") for i in range(30)]
        for c in cands:
            c["key"] = f"r{c['key'][2:].split('-')[1]}/{c['id']}"
        human = [{"key": c["key"], "label": "FAIL" if c["id"] in ("sc1", "sc2") else "PASS",
                  "split": "dev"} for c in cands]
        verdicts = [{"key": c["key"], "verdict": "PASS"} for c in cands]
        return cands, human, verdicts

    def test_pinned_scenarios_go_to_dev_and_labels_follow_their_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            cands, human, meta = self.run_in(tmp, *self.data(), pin_dev=["sc0", "sc3"])
        side = {c["key"]: c["split"] for c in cands}
        self.assertEqual({c["split"] for c in cands if c["id"] in ("sc0", "sc3")}, {"dev"})
        self.assertTrue(all(h["split"] == side[h["key"]] for h in human))
        self.assertEqual(len(human), 30)                         # no label lost
        self.assertEqual(meta["pinned_dev"], ["sc0", "sc3"])

    def test_a_human_failure_counts_for_the_holdout_draw(self):
        real = labels.split_scenarios
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(labels, "split_scenarios", side_effect=real) as spy:
            self.run_in(tmp, *self.data(), pin_dev=[])
        has_fail = spy.call_args.args[0]
        self.assertEqual({k for k, f in has_fail.items() if f}, {"sc1", "sc2"})

    def test_an_unknown_pin_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit):
            self.run_in(tmp, *self.data(), pin_dev=["nope"])


class More(unittest.TestCase):

    def test_earlier_versions_then_failed_scenarios_then_the_rest(self):
        chosen = [dict(sample(1, "PASS"), id="hurt")]
        human = [{"key": "r/hurt", "label": "FAIL"}]
        pool = ([dict(sample(10 + i, "PASS"), id="other") for i in range(5)] +
                [dict(sample(20 + i, "PASS"), id="hurt") for i in range(2)] +
                [dict(sample(30 + i, "PASS", old=True), id="any") for i in range(2)])
        got = labels.more(pool, chosen, human, 5, labels.random.Random(1))
        self.assertEqual([s["id"] for s in got[:4]], ["any", "any", "hurt", "hurt"])
        self.assertEqual(len(got), 5)

    def test_never_adds_a_chosen_sample_or_a_duplicate_reply(self):
        chosen = [sample(1, "PASS")]
        pool = [sample(1, "PASS"), dict(sample(1, "PASS"), key="r2/1"), sample(2, "PASS")]
        got = labels.more(pool, chosen, [], 10, labels.random.Random(1))
        self.assertEqual([s["key"] for s in got], ["r/2"])


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
                labels.cmd_rejudge(SimpleNamespace(judge_cli="claude", judge_model="opus", max_cost_usd=1.0,
                                                   ambiguous=False, all=False, resume=None))
                out = labels.read_jsonl(next(t.glob("rejudge-opus-*.jsonl")))
        self.assertEqual(judge.call_count, 2)         # 0.5 + 0.5 reaches 1.0
        self.assertEqual(out[0]["criterion_sha"], cands[0]["criterion_sha"])
        self.assertEqual(out[0]["judge"], "PASS")


def codex_out(*events, rc=0):
    return SimpleNamespace(returncode=rc, stderr="",
                           stdout="".join(json.dumps(e) + "\n" for e in events))


MSG = lambda t: {"type": "item.completed", "item": {"type": "agent_message", "text": t}}
DONE = {"type": "turn.completed", "usage": {"input_tokens": 900, "output_tokens": 40}}


class CodexJudge(unittest.TestCase):
    """A judge from another family: same text, its own parse, and no tools."""

    def judge(self, *events, ambiguous=False, rc=0):
        with mock.patch.object(labels.subprocess, "run", return_value=codex_out(*events, rc=rc)) as sp:
            got = labels.codex_judge("PASS if X", "the reply", ["-m", "m"], ambiguous)
        return got, sp.call_args

    def test_reads_the_same_text_run_judge_sends(self):
        _, call = self.judge(MSG("ok\nVERDICT: PASS"), DONE)
        self.assertEqual(call.kwargs["input"], run.judge_prompt("PASS if X", "the reply"))
        self.assertEqual(call.args[0][:3], ["codex", "exec", "--json"])

    def test_pass_fail_and_ambiguous(self):
        self.assertEqual(self.judge(MSG("fine\n**VERDICT: PASS**"), DONE)[0], ("PASS", "fine", 940))
        self.assertEqual(self.judge(MSG("no\nVERDICT: FAIL"), DONE)[0][0], "FAIL")
        got, call = self.judge(MSG("cannot tell\nVERDICT: AMBIGUOUS"), DONE, ambiguous=True)
        self.assertEqual(got[0], "AMBIGUA")
        self.assertEqual(call.kwargs["input"], run.judge_prompt("PASS if X", "the reply", True))

    def test_a_judge_that_used_a_tool_gives_no_verdict(self):
        (v, why, _), _ = self.judge({"type": "item.completed", "item": {"type": "command_execution"}},
                                    MSG("looked it up\nVERDICT: PASS"), DONE)
        self.assertIsNone(v)
        self.assertIn("command_execution", why)

    def test_a_failed_call_or_an_unreadable_answer_is_no_verdict(self):
        self.assertIsNone(self.judge(MSG("VERDICT: PASS"), rc=1)[0][0])
        self.assertIsNone(self.judge({"type": "turn.failed", "error": "quota"})[0][0])
        self.assertIsNone(self.judge(MSG("I think it mostly works"), DONE)[0][0])

    def test_a_run_is_refused_when_the_judge_would_see_the_catalog(self):
        leaky = SimpleNamespace(returncode=0, stderr="", stdout='[{"text": "- lh-backlog: ..."}]')
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(labels, "LABELS", Path(tmp)), \
                mock.patch.object(labels, "CANDIDATES", Path(tmp) / "c.jsonl"), \
                mock.patch.object(labels, "HUMAN", Path(tmp) / "h.jsonl"), \
                mock.patch.object(labels.subprocess, "run", return_value=leaky) as sp, \
                self.assertRaises(SystemExit) as stop:
            labels.cmd_rejudge(SimpleNamespace(judge_cli="codex", judge_model="m", max_calls=5,
                                               max_cost_usd=None, effort="low", ambiguous=False, all=False, resume=None))
        self.assertIn("lh-backlog", str(stop.exception))
        self.assertEqual(sp.call_count, 1)            # the render, never an exec

    def test_the_isolation_flags_reach_the_render_and_the_exec(self):
        flags = labels.codex_flags("m", "low", Path("/p"))
        for f in ("skills.include_instructions=false", "--ephemeral", "read-only",
                  "features.shell_tool=false", "features.multi_agent=false"):
            self.assertIn(f, flags)
        with mock.patch.object(labels.subprocess, "run",
                               return_value=SimpleNamespace(returncode=0, stderr="", stdout="[]")) as sp:
            self.assertEqual(labels.codex_isolation(flags), [])
        self.assertIn("skills.include_instructions=false", sp.call_args.args[0])

    def test_a_codex_run_stops_at_its_call_cap(self):
        cands = [dict(labels.public(sample(i, "PASS")), split="dev") for i in range(5)]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            with mock.patch.object(labels, "LABELS", t), \
                    mock.patch.object(labels, "CANDIDATES", t / "c.jsonl"), \
                    mock.patch.object(labels, "HUMAN", t / "h.jsonl"), \
                    mock.patch.object(labels, "codex_isolation", return_value=[]), \
                    mock.patch.object(labels, "codex_judge", return_value=("AMBIGUA", "?", 10)) as j, \
                    mock.patch("builtins.print"):
                labels.write_jsonl(t / "c.jsonl", cands)
                labels.write_jsonl(t / "h.jsonl", [{"key": c["key"], "label": "PASS"} for c in cands])
                labels.cmd_rejudge(SimpleNamespace(judge_cli="codex", judge_model="m", max_calls=3,
                                                   max_cost_usd=None, effort="low", ambiguous=True,
                                                   all=False, resume=None))
                out = labels.read_jsonl(next(t.glob("rejudge-codex-m-amb-*.jsonl")))
        self.assertEqual(j.call_count, 3)
        self.assertEqual({r["judge"] for r in out}, {"AMBIGUA"})


class Verdicts(unittest.TestCase):

    def test_run_judge_still_reads_only_pass_or_fail(self):
        self.assertNotIn("AMBIGUOUS", run.judge_prompt("c", "r"))
        self.assertIn("AMBIGUOUS", run.judge_prompt("c", "r", ambiguous=True))
        self.assertEqual(run.parse_verdict("why\n<br>\nVERDICT: FAIL")[0], "FAIL")

    def test_an_abstaining_judge_is_counted_apart(self):
        rows = [{"label": "FAIL", "judge": "FAIL"}, {"label": "FAIL", "judge": "AMBIGUA"},
                {"label": "FAIL", "judge": "ERROR"}]
        r = labels.rates(rows)
        self.assertEqual((r["tnr"], r["abstained"], r["no_verdict"]), (1.0, 1, 1))


class Resume(unittest.TestCase):
    """A run cut by its cap continues where it stopped, in the same file."""

    def go(self, prior, **kw):
        cands = [dict(labels.public(sample(i, "PASS")), split="dev") for i in range(5)]
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            f = t / "rejudge-opus-20261015-000000.jsonl"
            with mock.patch.object(labels, "LABELS", t), \
                    mock.patch.object(labels, "CANDIDATES", t / "c.jsonl"), \
                    mock.patch.object(labels, "HUMAN", t / "h.jsonl"), \
                    mock.patch.object(run, "judge", return_value=(False, "no", 0.1)) as judge, \
                    mock.patch("builtins.print"):
                labels.write_jsonl(t / "c.jsonl", cands)
                labels.write_jsonl(t / "h.jsonl", [{"key": c["key"], "label": "PASS"} for c in cands])
                labels.write_jsonl(f, prior(cands))
                args = dict(judge_cli="claude", judge_model="opus", max_cost_usd=5.0,
                            ambiguous=False, all=False, resume=str(f))
                args.update(kw)
                labels.cmd_rejudge(SimpleNamespace(**args))
                return judge, labels.read_jsonl(f), sorted(t.glob("rejudge-*"))

    def test_keeps_what_was_judged_and_judges_only_the_rest(self):
        prior = lambda cs: [{"key": c["key"], "judge": "PASS", "why": "", "criterion_sha": c["criterion_sha"]}
                            for c in cs[:3]]
        judge, out, files = self.go(prior)
        self.assertEqual(judge.call_count, 2)
        self.assertEqual([r["judge"] for r in out], ["PASS"] * 3 + ["FAIL"] * 2)
        self.assertEqual(len(files), 1)                       # the same file, not a second run

    def test_an_error_or_a_changed_criterion_is_judged_again(self):
        prior = lambda cs: [{"key": cs[0]["key"], "judge": "ERROR", "why": "", "criterion_sha": cs[0]["criterion_sha"]},
                            {"key": cs[1]["key"], "judge": "PASS", "why": "", "criterion_sha": "old"}]
        judge, out, _ = self.go(prior)
        self.assertEqual(judge.call_count, 5)
        self.assertEqual(len(out), 5)

    def test_refuses_a_file_from_another_judge(self):
        with self.assertRaises(SystemExit):
            self.go(lambda cs: [], judge_model="sonnet")


class Refresh(unittest.TestCase):
    """A criterion fixed in scenarios/ reaches the candidates; the labels made
    against the old text stay marked until the human looks again."""

    def test_takes_the_current_criterion_and_moves_its_hash(self):
        c = dict(labels.public(sample(1, "PASS")), split="dev", id="sc")
        scs = {"sc": run.Scenario(id="sc", category="c", prompt="p", assertions={"judge": "PASS if Y"})}
        got = labels.refreshed([c], scs)[0]
        self.assertEqual((got["criterion"], got["criterion_sha"]), ("PASS if Y", run.criterion_sha("PASS if Y")))
        self.assertEqual(got["graded"], c["graded"])
        self.assertEqual(labels.refreshed([c], {})[0], c)          # a scenario gone: left as is

    def test_an_imported_label_keeps_the_text_it_was_made_against(self):
        cands = [dict(labels.public(sample(1, "PASS")), split="dev")]
        rows = labels.merge([], [{"key": "r/1", "label": "PASS", "criterion_sha": "old"}], cands)
        self.assertEqual(rows[0]["criterion_sha"], "old")

    def test_the_page_lets_a_newer_label_win_and_shows_stale_ones(self):
        page = labels.build_page([labels.public(sample(1, "PASS"))], {})
        self.assertIn("Date.parse(v.at) > Date.parse(labels[k].at)", page)
        self.assertIn('id="stale"', page)


class Review(unittest.TestCase):
    """A label revised after review keeps its first value, survives an older
    export, and an excluded one is not scored."""

    def cands(self):
        return [dict(labels.public(sample(i, "PASS")), split="dev") for i in range(2)]

    def test_an_older_export_does_not_undo_a_revision(self):
        on_file = [{"key": "r/1", "label": "FAIL", "original_label": "PASS", "at": "2026-10-15T12:00:00",
                    "revised": {"why": "x"}, "criterion_sha": "s", "split": "dev"}]
        rows = labels.merge(on_file, [{"key": "r/1", "label": "PASS", "at": "2026-10-15T01:00:00Z"}],
                            self.cands())
        self.assertEqual(rows[0]["label"], "FAIL")

    def test_a_newer_export_wins_and_keeps_the_review_trail(self):
        on_file = [{"key": "r/1", "label": "FAIL", "original_label": "PASS", "at": "2026-10-15T12:00:00",
                    "excluded": "gone", "criterion_sha": "s", "split": "dev"}]
        rows = labels.merge(on_file, [{"key": "r/1", "label": "AMBIGUA", "at": "2026-10-16T00:00:00"}],
                            self.cands())
        self.assertEqual((rows[0]["label"], rows[0]["original_label"], rows[0]["excluded"]),
                         ("AMBIGUA", "PASS", "gone"))

    def test_report_skips_excluded_and_shows_first_labels(self):
        cands = self.cands()
        human = [dict(key=c["key"], label="FAIL", criterion_sha=c["criterion_sha"], split="dev") for c in cands]
        human[0]["excluded"] = "scenario rewritten"
        human[1]["original_label"] = "PASS"
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            with mock.patch.object(labels, "LABELS", t), \
                    mock.patch.object(labels, "CANDIDATES", t / "c.jsonl"), \
                    mock.patch.object(labels, "HUMAN", t / "h.jsonl"), \
                    mock.patch("builtins.print") as out:
                labels.write_jsonl(t / "c.jsonl", cands)
                labels.write_jsonl(t / "h.jsonl", human)
                labels.write_jsonl(t / "rejudge-x-1.jsonl",
                                   [{"key": c["key"], "judge": "FAIL", "criterion_sha": c["criterion_sha"]}
                                    for c in cands])
                labels.cmd_report(SimpleNamespace(rejudge=[]))
        text = "\n".join(str(c.args[0]) for c in out.call_args_list)
        self.assertIn("1 label(s) excluded", text)
        self.assertIn("all      n=  1", text)
        self.assertIn("first    n=  1  TPR 0.00", text)       # first label PASS, judge FAIL


class When(unittest.TestCase):

    def test_utc_and_local_stamps_compare_as_instants(self):
        local_noon = labels.datetime(2026, 10, 15, 12, 0).astimezone()
        later_utc = (local_noon + labels.timedelta(hours=1)).astimezone(labels.timezone.utc)
        self.assertLess(labels.when(local_noon.replace(tzinfo=None).isoformat()),
                        labels.when(later_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")))


class Excluded(unittest.TestCase):

    def test_rejudge_never_spends_on_an_excluded_label(self):
        cands = [dict(labels.public(sample(i, "PASS")), split="dev") for i in range(3)]
        human = [{"key": c["key"], "label": "PASS"} for c in cands]
        human[0]["excluded"] = "scenario rewritten"
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            with mock.patch.object(labels, "LABELS", t), \
                    mock.patch.object(labels, "CANDIDATES", t / "c.jsonl"), \
                    mock.patch.object(labels, "HUMAN", t / "h.jsonl"), \
                    mock.patch.object(run, "judge", return_value=(True, "ok", 0.01)) as judge, \
                    mock.patch("builtins.print"):
                labels.write_jsonl(t / "c.jsonl", cands)
                labels.write_jsonl(t / "h.jsonl", human)
                labels.cmd_rejudge(SimpleNamespace(judge_cli="claude", judge_model="opus", max_cost_usd=1.0,
                                                   ambiguous=False, all=False, resume=None))
        self.assertEqual([c.args[1] for c in judge.call_args_list], ["reply 1", "reply 2"])


if __name__ == "__main__":
    unittest.main()
