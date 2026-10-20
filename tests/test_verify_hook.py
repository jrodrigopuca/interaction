"""B-084: `verify:` puts the catalog's verify hook in the sample's session.
No model call: the CLI is a fake and the catalog is a temp dir.

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
import run   # noqa: E402


class VerifyHooks(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.catalog = Path(self._tmp.name)
        (self.catalog / "scripts").mkdir()
        self.script = self.catalog / "scripts" / "verify_before_stop.py"
        self.script.write_text("# verify\n")
        self.guard = self.catalog / "scripts" / "shell_write_guard.py"
        self.guard.write_text("# guard\n")

    def test_the_check_goes_on_argv_under_both_stop_events(self):
        with mock.patch.object(run, "catalog_root", return_value=self.catalog):
            hooks = run.verify_hooks("npm test -- --silent")
        self.assertEqual(set(hooks), {"Stop", "SubagentStop"})
        for event in ("Stop", "SubagentStop"):
            entry = hooks[event][0]
            self.assertNotIn("matcher", entry)
            self.assertEqual(entry["hooks"][0]["command"],
                             f'python3 "{self.script}" \'npm test -- --silent\'')

    def test_a_missing_script_stops_the_run(self):
        self.script.unlink()
        with mock.patch.object(run, "catalog_root", return_value=self.catalog):
            with self.assertRaises(SystemExit):
                run.verify_hooks("npm test")

    def test_guard_and_verify_share_one_settings_block(self):
        sc = run.Scenario(id="x", category="c", prompt="p", guard="shell-writes", verify="npm test")
        with mock.patch.object(run, "catalog_root", return_value=self.catalog):
            hooks = run.session_hooks(sc)
        self.assertEqual(set(hooks), {"PreToolUse", "Stop", "SubagentStop"})
        self.assertIsNone(run.session_hooks(run.Scenario(id="y", category="c", prompt="p")))

    def test_the_scripts_hash_is_fingerprinted_under_verify(self):
        sc = [run.Scenario(id="v", category="c", prompt="p", verify="npm test"),
              run.Scenario(id="n", category="c", prompt="p")]
        with mock.patch.object(run, "catalog_root", return_value=self.catalog), \
                mock.patch.object(run, "catalog_skill_names", return_value=[]):
            a = run.host_fingerprints(sc)["guards"]
            self.script.write_text("# verify, edited\n")
            b = run.host_fingerprints(sc)["guards"]
        self.assertEqual(set(a), {"verify"})
        self.assertNotEqual(a, b)

    def test_ask_sends_the_hooks_in_the_single_settings(self):
        fake = SimpleNamespace(stdout="", returncode=0, stderr="")
        with mock.patch.object(run, "catalog_root", return_value=self.catalog), \
                mock.patch.object(run.subprocess, "run", return_value=fake) as sp:
            run.ask("p", hooks=run.verify_hooks("npm test"), neutral=True)
        cmd = sp.call_args.args[0]
        self.assertEqual(cmd.count("--settings"), 1)
        settings = json.loads(cmd[cmd.index("--settings") + 1])
        self.assertIn("Stop", settings["hooks"])
        self.assertIn("permissions", settings)

    def test_verify_needs_the_neutral_session(self):
        with mock.patch.object(run.subprocess, "run") as sp:
            reply = run.ask("p", hooks={"Stop": []}, neutral=False)
        self.assertIn("neutral", reply.error)
        sp.assert_not_called()


class Loader(unittest.TestCase):

    def load(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text("- id: x\n  category: c\n  prompt: p\n" + extra)
            with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                return run.load_scenarios()

    def test_verify_loads_as_a_string(self):
        self.assertEqual(self.load("  verify: npm test\n")[0].verify, "npm test")
        self.assertEqual(self.load("")[0].verify, "")

    def test_a_list_is_refused(self):
        with self.assertRaises(SystemExit):
            self.load("  verify: [npm, test]\n")

    def test_the_twin_differs_from_its_base_only_in_id_manual_and_verify(self):
        sc = {s.id: s for s in run.load_scenarios()}
        a, b = sc["senior-dev-slug-change-suite-red"], sc["senior-dev-slug-change-verify"]
        self.assertEqual((a.verify, b.verify), ("", "npm test"))
        self.assertTrue(b.manual)
        for f in ("agent", "prompt", "assertions", "allow", "deny", "refuse",
                  "workspace", "permission_mode", "budget", "execute", "guard"):
            self.assertEqual(getattr(a, f), getattr(b, f), f)
        ids = [s.id for s in run.load_scenarios()]
        self.assertEqual([i for i in ids if a.id in i], [a.id])

    def test_the_fixture_suite_is_green_before_the_change(self):
        import subprocess
        proc = subprocess.run(["npm", "test"], cwd=ROOT / "fixtures" / "verify-stop",
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout[-500:] + proc.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
