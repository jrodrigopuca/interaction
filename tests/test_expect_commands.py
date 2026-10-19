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


if __name__ == "__main__":
    unittest.main()
