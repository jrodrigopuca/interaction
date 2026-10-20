"""B-083: `permission_mode:`, `guard:` and the `no_landed_shell_writes`
assertion. No model call: the CLI is a fake and events are hand-built.

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

REDIRECT = r"cat\s*>"


def bash(i, cmd, result="ok", error=False):
    return [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": i, "name": "Bash", "input": {"command": cmd}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": i, "content": result, "is_error": error}]}},
    ]


def landed(events, rxs=(REDIRECT,)):
    sc = run.Scenario(id="x", category="c", prompt="p")
    return run.action_failures({"no_landed_shell_writes": list(rxs)}, sc,
                               run.Reply(text="", events=events), None)


class NoLandedShellWrites(unittest.TestCase):

    def test_a_write_that_ran_fails(self):
        got = landed(bash("a", "cat > a.txt <<'EOF'\nx\nEOF"))
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].startswith(run.ACTION_CHECKS["no_landed_shell_writes"]))

    def test_a_refused_write_did_not_land(self):
        # The guard's deny, and the host's own refusal, both come back as errors.
        refused = "Refused by the local-agents shell-write guard (heredoc redirected to a file)"
        self.assertEqual(landed(bash("a", "cat > a.txt <<'EOF'\nx\nEOF", refused, error=True)), [])

    def test_attempts_are_forbid_commands_business_not_this_one(self):
        ev = bash("a", "cat > a.txt", "requires approval", error=True)
        sc = run.Scenario(id="x", category="c", prompt="p")
        reply = run.Reply(text="", events=ev)
        self.assertEqual(len(run.action_failures({"forbid_commands": [REDIRECT]}, sc, reply, None)), 1)
        self.assertEqual(landed(ev), [])

    def test_commands_that_do_not_match_pass(self):
        self.assertEqual(landed(bash("a", "node --test")), [])

    def test_no_command_at_all_is_vacuous_not_pass(self):
        sc = run.Scenario(id="x", category="c", prompt="p",
                          assertions={"no_landed_shell_writes": [REDIRECT]})
        got = run.check_results(sc, run.Reply(text="", events=[]), [])
        self.assertEqual([(c["check"], c["result"]) for c in got],
                         [("no_landed_shell_writes", "vacuous")])

    def test_the_scenarios_use_the_wide_detour_list(self):
        sc = {s.id: s for s in run.load_scenarios()}
        wide = sc["architect-denied-tool-no-workaround"].assertions["forbid_commands"]
        for sid in ("senior-dev-shell-writes-bare", "senior-dev-shell-writes-guard"):
            self.assertEqual(sc[sid].assertions["no_landed_shell_writes"], wide)


def settings_of(cmd):
    return json.loads(cmd[cmd.index("--settings") + 1])


class Ask(unittest.TestCase):

    def call(self, **kw):
        fake = SimpleNamespace(stdout="", returncode=0, stderr="")
        with mock.patch.object(run.subprocess, "run", return_value=fake) as sp:
            reply = run.ask("p", **kw)
        return reply, sp

    def test_permission_mode_reaches_the_cli(self):
        _, sp = self.call(permission_mode="auto", neutral=True)
        cmd = sp.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "auto")
        self.assertLess(cmd.index("--permission-mode"), cmd.index("--"))

    def test_no_mode_means_no_flag(self):
        _, sp = self.call(neutral=True)
        self.assertNotIn("--permission-mode", sp.call_args.args[0])

    def test_hooks_go_in_the_single_settings_with_the_permissions(self):
        hooks = {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
                                                                "command": "python3 g.py"}]}]}
        _, sp = self.call(hooks=hooks, neutral=True)
        cmd = sp.call_args.args[0]
        self.assertEqual(cmd.count("--settings"), 1)
        s = settings_of(cmd)
        self.assertEqual(s["hooks"], hooks)
        self.assertIn("permissions", s)

    def test_a_guard_needs_the_neutral_session(self):
        reply, sp = self.call(hooks={"PreToolUse": []}, neutral=False)
        self.assertIn("neutral", reply.error)
        sp.assert_not_called()


class Guards(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.catalog = Path(self._tmp.name)
        (self.catalog / "scripts").mkdir()
        self.script = self.catalog / "scripts" / "shell_write_guard.py"
        self.script.write_text("# guard\n")

    def test_the_hook_runs_the_catalogs_script(self):
        with mock.patch.object(run, "catalog_root", return_value=self.catalog):
            hooks = run.guard_hooks("shell-writes")
        entry = hooks["PreToolUse"][0]
        self.assertEqual(entry["matcher"], "Bash")
        self.assertEqual(entry["hooks"][0]["command"], f'python3 "{self.script}"')

    def test_a_missing_script_stops_the_run(self):
        self.script.unlink()
        with mock.patch.object(run, "catalog_root", return_value=self.catalog):
            with self.assertRaises(SystemExit):
                run.guard_hooks("shell-writes")

    def test_the_scripts_hash_is_fingerprinted(self):
        sc = [run.Scenario(id="g", category="c", prompt="p", guard="shell-writes"),
              run.Scenario(id="n", category="c", prompt="p")]
        with mock.patch.object(run, "catalog_root", return_value=self.catalog), \
                mock.patch.object(run, "catalog_skill_names", return_value=[]):
            a = run.host_fingerprints(sc)["guards"]
            self.script.write_text("# guard, edited\n")
            b = run.host_fingerprints(sc)["guards"]
        self.assertEqual(set(a), {"shell-writes"})
        self.assertNotEqual(a, b)

    def test_no_guarded_scenario_records_none(self):
        sc = [run.Scenario(id="n", category="c", prompt="p")]
        with mock.patch.object(run, "catalog_skill_names", return_value=[]):
            self.assertIsNone(run.host_fingerprints(sc)["guards"])


class Loader(unittest.TestCase):

    def load(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.yaml").write_text("- id: x\n  category: c\n  prompt: p\n" + extra)
            with mock.patch.object(run, "SCENARIOS", Path(tmp)):
                return run.load_scenarios()

    def test_known_values_load(self):
        s = self.load("  permission_mode: acceptEdits\n  guard: shell-writes\n")[0]
        self.assertEqual((s.permission_mode, s.guard), ("acceptEdits", "shell-writes"))

    def test_an_unknown_mode_or_guard_stops_the_load(self):
        for bad in ("  permission_mode: yolo\n", "  permission_mode: default\n",
                    "  guard: everything\n"):
            with self.assertRaises(SystemExit, msg=bad):
                self.load(bad)

    TWINS = {"architect-denied-tool-no-workaround": "architect-denied-tool-guard",
             "senior-dev-denied-tool-no-workaround": "senior-dev-denied-tool-guard",
             "generalist-denied-tool-no-workaround": "generalist-denied-tool-guard",
             "architect-runs-repo-generator": "architect-repo-generator-guard",
             "senior-dev-runs-repo-generator": "senior-dev-repo-generator-guard",
             "senior-dev-no-edit-tool-announces-and-leaves-diff": "senior-dev-no-edit-tool-guard",
             "senior-dev-shell-writes-bare": "senior-dev-shell-writes-guard"}

    def test_the_guarded_twins_differ_only_in_id_and_guard(self):
        sc = {s.id: s for s in run.load_scenarios()}
        for base, twin in self.TWINS.items():
            a, b = sc[base], sc[twin]
            self.assertEqual((a.guard, b.guard), ("", "shell-writes"), base)
            self.assertTrue(b.manual, base)
            for f in ("agent", "prompt", "assertions", "allow", "deny", "refuse",
                      "workspace", "permission_mode", "budget", "execute"):
                self.assertEqual(getattr(a, f), getattr(b, f), f"{base}: {f}")

    def test_a_base_id_never_selects_its_twin(self):
        # `--only` matches substrings: a twin containing its base's id would
        # run, and be paid for, whenever the base is asked for by name.
        ids = [s.id for s in run.load_scenarios()]
        for base in self.TWINS:
            self.assertEqual([i for i in ids if base in i], [base], base)

    def test_the_guard_selector_takes_every_guarded_scenario_and_nothing_else(self):
        wanted = ("shell-writes-guard", "-tool-guard", "-generator-guard")
        picked = {s.id for s in run.load_scenarios() if any(o in s.id for o in wanted)}
        guarded = {s.id for s in run.load_scenarios() if s.guard}
        self.assertEqual(picked, guarded)


if __name__ == "__main__":
    unittest.main()
