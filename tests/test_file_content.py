"""`expect_file_content`: the deliverable is a file, so its content is checked
on disk, not in the reply the judge reads (B-080)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run   # noqa: E402

RULE = {"docs/**/*.md": ["(?i)revisit", "(?i)rounding|redondeo"]}


class ExpectFileContent(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        fixture = self.tmp / "fixtures" / "fx"
        fixture.mkdir(parents=True)
        (fixture / "README.md").write_text("seeded: revisit if rounding\n")
        self.ws = self.tmp / "ws"
        shutil.copytree(fixture, self.ws)
        self.sc = run.Scenario(id="x", category="c", prompt="p", agent="g",
                               workspace="fixtures/fx")
        self.patch = mock.patch.object(run, "ROOT", self.tmp)
        self.patch.start()
        self.reply = run.Reply(text="done", events=[])

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def fails(self):
        return [f for f in run.action_failures({"expect_file_content": RULE},
                                               self.sc, self.reply, self.ws)
                if f.startswith("no written file matching")]

    def write_adr(self, text):
        (self.ws / "docs" / "adr").mkdir(parents=True, exist_ok=True)
        (self.ws / "docs" / "adr" / "0001-x.md").write_text(text)

    def test_a_written_file_with_every_pattern_passes(self):
        self.write_adr("## Context\nRounding bug.\n## Revisit if\nWe move to decimals.\n")
        self.assertEqual(self.fails(), [])

    def test_a_missing_pattern_fails_naming_it(self):
        self.write_adr("## Context\nRounding bug.\n")
        out = self.fails()
        self.assertEqual(len(out), 1)
        self.assertIn("revisit", out[0])

    def test_nothing_written_fails_and_says_so(self):
        out = self.fails()
        self.assertEqual(len(out), 2)
        self.assertTrue(all("(none was written)" in f for f in out))

    def test_a_seeded_file_outside_the_glob_never_counts(self):
        (self.ws / "README.md").write_text("edited: revisit if rounding\n")
        self.assertEqual(len(self.fails()), 2)

    def test_its_result_is_recorded_not_unrecorded(self):
        self.assertIn("expect_file_content", run.ACTION_CHECKS)


if __name__ == "__main__":
    unittest.main()
