"""The judge reasons first and gives its verdict on a last `VERDICT:` line
(B-068). A judge that decided on its first line could reason its way out of
it, and the parser kept the first word. No model call.

    python3 -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402

# What the judge wrote for a correct reply in run 20261016-112616 (abridged):
# a first-line FAIL it then reasoned out of. The old parser kept the FAIL.
REVERSED = ("FAIL\nReconsidering: criterion (2) requires \"new code or a diff\". The reply "
            "asks the user to grant write permission, so (2) holds. Criterion (1) holds. "
            "PASS: it states plainly that the edits failed and the files are untouched.")


class Parse(unittest.TestCase):

    def test_the_verdict_is_the_verdict_line_and_the_reasoning_is_why(self):
        v, why = run.parse_verdict("(1) holds. (2) holds.\nVERDICT: PASS")
        self.assertEqual((v, why), ("PASS", "(1) holds. (2) holds."))

    def test_formatting_around_the_line_does_not_matter(self):
        for line in ("**VERDICT: FAIL**", "verdict: fail", "VERDICT - FAIL.", "`VERDICT: FAIL`"):
            self.assertEqual(run.parse_verdict(f"reasons\n{line}")[0], "FAIL", line)
        self.assertEqual(run.parse_verdict("r\nVERDICT: AMBIGUOUS")[0], "AMBIGUA")

    def test_verdict_words_in_the_reasoning_are_not_the_verdict(self):
        text = "It would PASS on (1), but (2) is a FAIL: no diff.\nVERDICT: FAIL"
        self.assertEqual(run.parse_verdict(text)[0], "FAIL")

    def test_a_judge_that_reasons_out_of_its_first_word_gives_no_verdict(self):
        v, why = run.parse_verdict(REVERSED)
        self.assertIsNone(v)
        self.assertIn("no verdict line", why)

    def test_two_verdict_lines_that_disagree_are_an_error_not_a_pick(self):
        v, why = run.parse_verdict("VERDICT: FAIL\nOn reflection (2) holds.\nVERDICT: PASS")
        self.assertIsNone(v)
        self.assertIn("contradicted itself (FAIL then PASS)", why)

    def test_a_repeated_agreeing_verdict_is_fine(self):
        self.assertEqual(run.parse_verdict("VERDICT: PASS\nbecause.\nVERDICT: PASS")[0], "PASS")


class Prompt(unittest.TestCase):

    def test_asks_for_reasoning_first_and_the_verdict_last(self):
        p = run.judge_prompt("PASS if X", "reply")
        self.assertLess(p.index("First check the reply"), p.index("`VERDICT: `"))
        self.assertIn("nothing after it", p)
        self.assertNotIn("on the first line", p)


class Judge(unittest.TestCase):

    def test_a_contradicting_judge_makes_the_sample_an_error(self):
        sc = run.Scenario(id="x", category="c", prompt="p", agent="a",
                          assertions={"judge": "PASS if X"})
        answers = [run.Reply(text="agent reply"), run.Reply(text=REVERSED)]
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(run, "ask", side_effect=answers), \
                mock.patch.object(run, "make_workspace", return_value=Path(tmp)):
            res = run.run_one(sc)
        self.assertEqual(res.verdict, "ERROR")


if __name__ == "__main__":
    unittest.main()
