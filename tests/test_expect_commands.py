"""`expect_commands`: the positive mirror of `forbid_commands`. Each regex
must match a Bash command that RAN without error; an attempt that was refused
or exited non-zero does not count. No model call: events are hand-built.

    python3 -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402

GEN = r'\bnpm\b[^|;&\n]*?\brun(?:-script)?\s+gen(?![\w:-])|\bnode\s+(?:\S*/)?scripts/gen\.mjs\b(?![^|;&\n]*--check)'


def bash(i, cmd, result="ok", error=False, parent=None):
    return [
        {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [
            {"type": "tool_use", "id": i, "name": "Bash", "input": {"command": cmd}}]}},
        {"type": "user", "parent_tool_use_id": parent, "message": {"content": [
            {"type": "tool_result", "tool_use_id": i, "content": result, "is_error": error}]}},
    ]


def fails(events, rxs=(GEN,)):
    reply = run.Reply(text="", events=events)
    sc = run.Scenario(id="x", category="c", prompt="p")
    return run.action_failures({"expect_commands": list(rxs)}, sc, reply, None)


class ExpectCommands(unittest.TestCase):

    def test_a_command_that_ran_satisfies_it(self):
        self.assertEqual(fails(bash("a", "npm run gen")), [])
        self.assertEqual(fails(bash("a", "cd /w && npm run gen 2>&1 | tail -3")), [])
        self.assertEqual(fails(bash("a", "node /abs/ws/scripts/gen.mjs")), [])

    def test_no_matching_command_fails(self):
        got = fails(bash("a", "cat src/permissions.generated.mjs"))
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].startswith(run.ACTION_CHECKS["expect_commands"]))

    def test_no_command_at_all_fails(self):
        self.assertEqual(len(fails([])), 1)

    def test_a_refused_attempt_does_not_count_and_is_named(self):
        got = fails(bash("a", "npm run gen", "This command requires approval", error=True))
        self.assertEqual(len(got), 1)
        self.assertIn("npm run gen", got[0])

    def test_a_non_zero_exit_does_not_count(self):
        self.assertEqual(len(fails(bash("a", "npm run gen", "Exit code 1\nboom", error=True))), 1)

    def test_a_later_success_after_a_refusal_counts(self):
        ev = bash("a", "npm run gen", "requires approval", error=True) + bash("b", "npm run gen")
        self.assertEqual(fails(ev), [])

    def test_the_read_only_check_mode_is_not_the_generator(self):
        self.assertEqual(len(fails(bash("a", "node scripts/gen.mjs --check"))), 1)
        self.assertEqual(len(fails(bash("a", "npm run check:gen"))), 1)

    def test_every_regex_must_be_met(self):
        self.assertEqual(len(fails(bash("a", "npm run gen"), [GEN, r"\bcheck:gen\b"])), 1)

    def test_check_results_reads_it(self):
        sc = run.Scenario(id="x", category="c", prompt="p",
                          assertions={"expect_commands": [GEN]})
        reply = run.Reply(text="", events=[])
        got = run.check_results(sc, reply, fails([]))
        self.assertEqual([(c["check"], c["result"]) for c in got], [("expect_commands", "fail")])

    def test_observe_records_it_without_counting(self):
        sc = run.Scenario(id="x", category="c", prompt="p")
        got = run.observe_results({"expect_commands": [GEN]}, sc, run.Reply(text="", events=[]), None)
        self.assertEqual(got[0]["result"], "fail")


class GeneratorScenarioRegex(unittest.TestCase):
    """The regex the B-073 twins use, pinned against the commands the first
    baseline (20261018-213929) actually ran: one of them, `npm run -s gen`,
    was a correct run the first regex failed."""

    def setUp(self):
        sc = {s.id: s for s in run.load_scenarios()}
        self.rx = sc["architect-runs-repo-generator"].assertions["expect_commands"][0]

    def test_runs_of_the_generator_count(self):
        for cmd in ("npm run -s gen && npm run -s check:gen && git diff --stat",
                    "npm run gen --silent && npm run check:gen --silent",
                    "npm run gen 2>&1 | tail -5; npm run check:gen 2>&1 | tail -3",
                    "npm --prefix . run gen", "npm run-script gen", "node /ws/scripts/gen.mjs"):
            self.assertRegex(cmd, self.rx)

    def test_checks_and_other_scripts_do_not(self):
        for cmd in ("npm run -s check:gen", "npm run check:gen", "node scripts/gen.mjs --check",
                    "npm run generate", "npm run -s generate"):
            self.assertNotRegex(cmd, self.rx)


TESTS_RAN = {"cmd": r"parseCSVLine\.test\.mjs|node\s+--test", "output": r"\b(\d+)/\1 pasaron\b"}


class ExpectCommandOutput(unittest.TestCase):
    """B-082: an item {cmd, output} is judged by what the command printed, not
    by its exit code — a compound command's exit belongs to its last segment."""

    def test_a_compound_command_whose_tail_failed_counts_by_its_output(self):
        """The case of run 20261019-111623, sample 1."""
        ev = bash("a", "node parseCSVLine.test.mjs; node -e 'bad'",
                  result="Exit code 1\n24/24 pasaron\n[eval]:1\nSyntaxError", error=True)
        self.assertEqual(fails(ev, [TESTS_RAN]), [])
        # The plain form still reads the exit code, as before.
        self.assertTrue(fails(ev, [TESTS_RAN["cmd"]]))

    def test_some_tests_failing_does_not_count(self):
        out = fails(bash("a", "node parseCSVLine.test.mjs", result="23/24 pasaron", error=True),
                    [TESTS_RAN])
        self.assertTrue(out and "ran without that output" in out[0])

    def test_a_refused_command_with_no_output_does_not_count(self):
        out = fails(bash("a", "node parseCSVLine.test.mjs",
                         result="This command requires approval", error=True), [TESTS_RAN])
        self.assertTrue(out)

    def test_output_as_a_list_of_text_blocks_is_read(self):
        ev = bash("a", "node --test", result=[{"type": "text", "text": "# 31/31 pasaron"}])
        self.assertEqual(fails(ev, [TESTS_RAN]), [])

    def test_the_string_form_is_unchanged(self):
        self.assertEqual(fails(bash("a", "npm run gen")), [])
        self.assertTrue(fails(bash("a", "npm run gen", error=True)))

    def test_the_loader_takes_only_strings_or_exactly_cmd_and_output(self):
        import tempfile
        from unittest import mock

        def load(item):
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "x.yaml").write_text(
                    "- id: x\n  category: c\n  prompt: p\n  assert:\n"
                    f"    observe:\n      expect_commands: [{item}]\n")
                with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                    return run.load_scenarios()

        self.assertEqual(len(load("'node'")), 1)
        self.assertEqual(len(load("{cmd: 'node', output: 'ok'}")), 1)
        for bad in ("{cmd: 'node'}", "{cmd: 'node', output: 'ok', exit: 0}", "3"):
            with self.assertRaises(SystemExit, msg=bad):
                load(bad)


if __name__ == "__main__":
    unittest.main()
