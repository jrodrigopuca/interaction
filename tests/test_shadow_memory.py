"""`memory: off` on a scenario strips the `memory:` line from the shadow agent
(B-077): a host without a memory store, which is every host but Claude Code.
Without the field the shadow keeps `memory: local`, as it always did. No model
call: the agents dir is a temp dir with one fake agent.

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

AGENT = """---
name: qa
description: Finds bugs.
model: inherit
memory: user
tools: Read, Grep
---

# qa

Body that must survive untouched.
"""


class ShadowMemory(unittest.TestCase):

    def shadow(self, memory: str) -> str:
        with tempfile.TemporaryDirectory() as agents, tempfile.TemporaryDirectory() as ws:
            (Path(agents) / "qa.md").write_text(AGENT, encoding="utf-8")
            with mock.patch.object(run, "AGENTS_DIR", Path(agents)):
                run.shadow_agents(Path(ws), memory)
            return (Path(ws) / ".claude" / "agents" / "qa.md").read_text(encoding="utf-8")

    def test_default_rewrites_memory_to_local(self):
        got = self.shadow("")
        self.assertIn("\nmemory: local\n", got)
        self.assertNotIn("memory: user", got)
        self.assertIn("tools: Read, Grep\n", got)           # the rest of the frontmatter stays
        self.assertIn("Body that must survive untouched.", got)

    def test_off_removes_the_memory_line_and_nothing_else(self):
        got = self.shadow("off")
        self.assertNotIn("memory:", got)
        self.assertEqual(got, AGENT.replace("memory: user\n", ""))

    def test_off_on_an_agent_without_memory_is_a_no_op(self):
        bare = AGENT.replace("memory: user\n", "")
        with tempfile.TemporaryDirectory() as agents, tempfile.TemporaryDirectory() as ws:
            (Path(agents) / "qa.md").write_text(bare, encoding="utf-8")
            with mock.patch.object(run, "AGENTS_DIR", Path(agents)):
                run.shadow_agents(Path(ws), "off")
            got = (Path(ws) / ".claude" / "agents" / "qa.md").read_text(encoding="utf-8")
        self.assertEqual(got, bare)


class MemoryField(unittest.TestCase):

    def test_absent_means_the_usual_shadow(self):
        self.assertEqual(run.memory_mode(None, "x"), "")

    def test_off_is_accepted_in_any_case(self):
        self.assertEqual(run.memory_mode("off", "x"), "off")
        self.assertEqual(run.memory_mode(" OFF ", "x"), "off")

    def test_bare_off_arrives_as_yaml_false_and_is_off(self):
        # YAML 1.1: `memory: off` loads as the boolean False, not the string.
        self.assertEqual(run.memory_mode(False, "x"), "off")

    def test_anything_else_is_refused_not_ignored(self):
        for bad in ("on", "local", "user", "false", True, 1, 0):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                run.memory_mode(bad, "x")


if __name__ == "__main__":
    unittest.main()
