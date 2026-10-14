"""project.py spends only what was approved for it (B-060), and a call that
was cut or failed is still recorded with its cost. No model call: `ask` is
replaced by a fake that returns a recorded reply.

    python3 -m unittest discover -s tests
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import project   # noqa: E402
import run       # noqa: E402


def call(argv, reply):
    """Run project.main() with `argv` and a fake ask(); return (code, ask mock, trace)."""
    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(project, "RUNS", Path(tmp) / "runs"), \
            mock.patch.object(project, "ROOT", Path(tmp)), \
            mock.patch.object(project.harness, "ask", return_value=reply) as ask, \
            mock.patch.object(sys, "argv", ["project.py", *argv]), \
            redirect_stdout(io.StringIO()):
        code = project.main()
        traces = list(Path(tmp).glob("runs/*/trace.jsonl"))
        trace = json.loads(traces[0].read_text()) if traces else None
    return code, ask, trace


class ProjectBudget(unittest.TestCase):

    def test_it_does_not_start_without_a_budget(self):
        with mock.patch.object(project.harness, "ask") as ask, \
                mock.patch.object(sys, "argv", ["project.py", "a task"]), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            project.main()
        ask.assert_not_called()

    def test_the_budget_reaches_the_call(self):
        ok = run.Reply(text="done", cost=1.2, ms=10)
        code, ask, trace = call(["a task", "--max-cost-usd", "5"], ok)
        self.assertEqual(ask.call_args.kwargs["max_budget"], 5.0)
        self.assertEqual(code, 0)
        self.assertEqual(trace["status"], "PASS")

    def test_a_call_cut_by_its_budget_is_recorded_with_its_cost(self):
        cut = run.Reply(text="", cost=5.03, error="budget: the sample hit its "
                        "--max-budget-usd ceiling ($5.03 spent)")
        code, _, trace = call(["a task", "--max-cost-usd", "5"], cut)
        self.assertEqual(code, 2)
        self.assertEqual(trace["status"], "ERROR")
        self.assertAlmostEqual(trace["cost_usd"], 5.03)
        self.assertTrue(trace["error"].startswith("budget"))

    def test_any_other_failure_is_recorded_too(self):
        failed = run.Reply(text="", cost=0.4, error="timed out after 300s")
        code, _, trace = call(["a task", "--max-cost-usd", "5"], failed)
        self.assertEqual(code, 1)
        self.assertEqual(trace["status"], "ERROR")
        self.assertAlmostEqual(trace["cost_usd"], 0.4)


if __name__ == "__main__":
    unittest.main()
