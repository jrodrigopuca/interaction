"""A run during which the catalog was reinstalled is invalid (B-052): its
samples straddle two catalog versions and describe neither. These tests make
no model call — they fake the install stamp and the run folders.

    python3 -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run   # noqa: E402
import viz   # noqa: E402

STAMP = {"catalog_commit": "a" * 40, "catalog_dirty": False,
         "catalog_path": "/somewhere", "installed_at": "2026-10-13T10:00:00-03:00"}


class CatalogChanged(unittest.TestCase):

    def test_the_same_install_is_unchanged(self):
        self.assertFalse(run.catalog_changed(STAMP, dict(STAMP)))
        self.assertFalse(run.catalog_changed(None, None))

    def test_a_new_commit_a_reinstall_or_a_first_install_is_a_change(self):
        self.assertTrue(run.catalog_changed(STAMP, {**STAMP, "catalog_commit": "b" * 40}))
        # Same commit, installed again: the files were rewritten mid-run.
        self.assertTrue(run.catalog_changed(STAMP, {**STAMP, "installed_at": "2026-10-13T10:05:00-03:00"}))
        self.assertTrue(run.catalog_changed(STAMP, {**STAMP, "catalog_dirty": True}))
        self.assertTrue(run.catalog_changed(None, STAMP))
        self.assertTrue(run.catalog_changed(STAMP, None))

    def test_close_stamp_records_both_stamps_only_when_it_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / ".local-agents.json"
            manifest.write_text(json.dumps(STAMP))
            same = {"catalog": dict(STAMP)}
            self.assertFalse(run.close_stamp(same, manifest))
            self.assertNotIn("catalog_changed", same)

            moved = {"catalog": dict(STAMP)}
            later = {**STAMP, "catalog_commit": "b" * 40}
            manifest.write_text(json.dumps(later))
            self.assertTrue(run.close_stamp(moved, manifest))
            self.assertTrue(moved["catalog_changed"])
            self.assertEqual(moved["catalog_end"], later)
            self.assertEqual(moved["catalog"], STAMP, "the starting stamp must survive")


class NeverBaselineNeverCurrent(unittest.TestCase):

    def test_viz_never_takes_it_for_a_baseline(self):
        neutral = {"fingerprints": {"isolation": "neutral"}, "catalog": STAMP}
        self.assertTrue(viz.is_neutral(neutral))
        self.assertFalse(viz.is_neutral({**neutral, "catalog_changed": True}))
        self.assertIn("Catalog changed during the run · invalid",
                      viz.run_warnings({**neutral, "catalog_changed": True}))

    def test_applicability_skips_its_verdicts(self):
        """A newer run that saw the catalog change must not become a
        scenario's latest verdict; the older valid run stays it."""
        sc = run.load_scenarios()[0]
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            for name, verdict, extra in (("20261013-100000", "PASS", {}),
                                         ("20261013-110000", "FAIL", {"catalog_changed": True})):
                d = runs / name
                d.mkdir()
                (d / "run.json").write_text(json.dumps({"catalog": STAMP, **extra}))
                (d / "trace.jsonl").write_text(json.dumps({"id": sc.id, "status": verdict}) + "\n")
            # The host fingerprint reads the machine's install stamp; which
            # run is picked does not depend on it, and a clean CI runner has none.
            with mock.patch.object(run, "RUNS", runs), \
                    mock.patch.object(run, "catalog_skill_names", return_value=[]):
                row = run.applicability_data([sc], run.AGENT_MODEL)[0]
        self.assertEqual(row["run"], "20261013-100000")


if __name__ == "__main__":
    unittest.main()
