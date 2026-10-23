"""--only: substring by default, exact with a leading `=` (a twin's id extends
its base's, so a substring cannot pick the base alone)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run  # noqa: E402


class OnlyFilter(unittest.TestCase):

    def test_a_substring_matches_the_base_and_its_twin(self):
        self.assertTrue(run.only_matches("value-x-1", ["value-x-1"]))
        self.assertTrue(run.only_matches("value-x-1-without", ["value-x-1"]))

    def test_a_leading_equals_matches_only_that_id(self):
        self.assertTrue(run.only_matches("value-x-1", ["=value-x-1"]))
        self.assertFalse(run.only_matches("value-x-1-without", ["=value-x-1"]))

    def test_any_entry_is_enough(self):
        self.assertTrue(run.only_matches("b", ["=a", "b"]))
        self.assertFalse(run.only_matches("c", ["=a", "b"]))


if __name__ == "__main__":
    unittest.main()
