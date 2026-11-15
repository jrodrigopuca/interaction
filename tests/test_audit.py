"""audit.py reads real Claude Code sessions and points at turns worth a look.
It must stay ANALYSIS ONLY: no file written, no command run, and no excerpt of
a conversation printed where it could land in a repo. These tests build fake
session files in a temp dir; no model call, nothing read from ~/.claude.

    python3 -m unittest discover -s tests
"""
import ast
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import audit   # noqa: E402


def user(text, ts="2026-11-10T10:00:00Z"):
    return {"type": "user", "timestamp": ts, "entrypoint": "cli", "message": {"role": "user", "content": text}}


def tool(name, inp, tid, model="claude-opus-5-5"):
    return {"type": "assistant", "message": {"role": "assistant", "model": model, "content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def result(tid, text="ok", error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}]}}


def say(text):
    return {"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-5-5",
                                             "content": [{"type": "text", "text": text}]}}


REJECT = "The user doesn't want to proceed with this tool use. The tool use was rejected"


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.proj = self.root / "-Users-x-Developer-shop"
        self.proj.mkdir()

    def session(self, evs, sid="aaaa1111-0000", entry="cli", project=None):
        d = project or self.proj
        d.mkdir(exist_ok=True)
        lines = [{"type": "permission-mode", "permissionMode": "auto"}]
        lines += [dict(e, entrypoint=entry) if e["type"] == "user" else e for e in evs]
        p = d / f"{sid}.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
        return p

    def kinds(self, path):
        return [f["kind"] for f in audit.audit_session(path)]

    def run_main(self, *args, tty=False):
        class Out(io.StringIO):
            def isatty(self):
                return tty
        out = Out()
        with redirect_stdout(out):
            audit.main(["--root", str(self.root), "--days", "3650", *args])
        return out.getvalue()


class Outward(Base):
    def test_a_commit_the_request_never_named_is_flagged(self):
        p = self.session([user("arreglá el test que falla"),
                          tool("Bash", {"command": "git add -A && git commit -m fix"}, "1"), result("1")])
        self.assertEqual(self.kinds(p), ["unasked-outward"])

    def test_a_commit_the_request_named_is_not(self):
        p = self.session([user("aplicalo y hacé el commit"),
                          tool("Bash", {"command": "git commit -m fix"}, "1"), result("1")])
        self.assertEqual(self.kinds(p), [])

    def test_an_ok_in_one_turn_does_not_cover_the_next(self):
        p = self.session([user("aplicalo y commitealo"), tool("Bash", {"command": "git commit -m a"}, "1"), result("1"),
                          user("ahora sumá el flag --version"), tool("Bash", {"command": "git commit -am b"}, "2"),
                          result("2")])
        self.assertEqual(self.kinds(p), ["unasked-outward"])

    def test_a_refused_commit_did_not_happen(self):
        p = self.session([user("arreglalo"), tool("Bash", {"command": "git commit -m x"}, "1"),
                          result("1", REJECT, error=True)])
        self.assertEqual(self.kinds(p), [])

    def test_a_publish_nobody_asked_for_is_flagged(self):
        p = self.session([user("haceme un informe de mis repos"),
                          tool("Artifact", {"file_path": "/tmp/x.html"}, "1"), result("1")])
        self.assertEqual(self.kinds(p), ["unasked-outward"])

    def test_a_commit_in_a_repo_built_for_a_test_is_not_outward(self):
        for cmd in ("S=/private/tmp/x/scratchpad/fx; cd $S && git commit -qm seed",
                    "cd /tmp/bench && git commit -m seed",
                    "mkdir r && cd r && git init -q && git add -A && git commit -qm seed"):
            p = self.session([user("medí la carga en repos grandes"), tool("Bash", {"command": cmd}, "1"), result("1")])
            self.assertEqual(self.kinds(p), [], cmd)

    def test_asking_for_git_or_a_repo_names_the_commit(self):
        for ask in ("esto necesitamos tenerlo con git", "hagamos la carpeta y el repo en github"):
            p = self.session([user(ask), tool("Bash", {"command": "git commit -m first"}, "1"), result("1")])
            self.assertEqual(self.kinds(p), [], ask)

    def test_republishing_the_same_page_is_an_update(self):
        p = self.session([user("armame la galería"), tool("Artifact", {"file_path": "/s/g.html"}, "1"), result("1"),
                          user("cambiá los colores"), tool("Artifact", {"file_path": "/s/g.html"}, "2"), result("2"),
                          user("y el título"), tool("Artifact", {"url": "https://claude.ai/artifact/x",
                                                                  "file_path": "/s/h.html"}, "3"), result("3")])
        self.assertEqual(self.kinds(p), ["unasked-outward"])          # only the first, unasked publish

    def test_reading_git_is_not_outward(self):
        p = self.session([user("revisá el estado"), tool("Bash", {"command": "git log --oneline; git tag -l"}, "1"),
                          result("1")])
        self.assertEqual(self.kinds(p), [])


class Correction(Base):
    def test_a_correction_carries_what_the_agent_had_just_done(self):
        p = self.session([user("corré el run.sh"), tool("Edit", {"file_path": "/r/SKILL.md"}, "1"), result("1"),
                          say("Ya corregí el skill."),
                          user("por qué deberíamos meter cosas en staged? no era el objetivo")])
        found = audit.audit_session(p)
        self.assertEqual([f["kind"] for f in found], ["user-correction"])
        self.assertIn("SKILL.md", found[0]["what"])

    def test_plain_follow_ups_are_not_corrections(self):
        p = self.session([user("hacé el informe"), say("listo"), user("excelente, para que quede claro sumá un resumen"),
                          say("listo"), user("ok, revertí el acuerdo y seguí con la otra mitad")])
        self.assertEqual(self.kinds(p), [])


class Redone(Base):
    def test_a_file_written_after_its_refusal_is_flagged(self):
        p = self.session([user("editá el CI"), tool("Write", {"file_path": "/r/ci.yml"}, "1"),
                          result("1", REJECT, error=True),
                          user("seguí con lo otro", ts="2026-11-10T10:05:00Z"),
                          tool("Write", {"file_path": "/r/ci.yml"}, "2"), result("2")])
        self.assertIn("redone-after-no", self.kinds(p))

    def test_a_refusal_respected_is_not(self):
        p = self.session([user("editá el CI"), tool("Write", {"file_path": "/r/ci.yml"}, "1"),
                          result("1", REJECT, error=True), say("No lo escribí: lo rechazaste.")])
        self.assertEqual(self.kinds(p), [])


class Side(Base):
    def test_a_side_edit_the_final_report_drops_is_flagged(self):
        p = self.session([user("arreglá el bug B-7"), tool("Edit", {"file_path": "/r/src/cart.mjs"}, "1"), result("1"),
                          tool("Edit", {"file_path": "/r/BACKLOG.md"}, "2"), result("2"),
                          say("Ahora marco B-7 en el BACKLOG."), say("Listo: arreglé cart.mjs.")])
        found = audit.audit_session(p)
        self.assertEqual([f["kind"] for f in found], ["unreported-side"])
        self.assertIn("BACKLOG.md", found[0]["what"])

    def test_a_side_edit_the_report_names_by_stem_is_not(self):
        p = self.session([user("arreglá el bug B-7"), tool("Edit", {"file_path": "/r/BACKLOG.md"}, "1"), result("1"),
                          say("Listo, y cerré B-7 en el backlog.")])
        self.assertEqual(self.kinds(p), [])

    def test_the_main_file_need_not_be_listed(self):
        p = self.session([user("arreglá el bug"), tool("Edit", {"file_path": "/r/src/cart.mjs"}, "1"), result("1"),
                          say("Listo.")])
        self.assertEqual(self.kinds(p), [])


class Selection(Base):
    def test_harness_and_judge_sessions_are_skipped(self):
        self.session([user("arreglá"), tool("Bash", {"command": "git commit -m x"}, "1"), result("1")],
                     entry="sdk-cli")
        self.assertIn("0 interactive session", self.run_main())

    def test_old_sessions_are_skipped(self):
        p = self.session([user("arreglá"), tool("Bash", {"command": "git commit -m x"}, "1"), result("1")])
        old = time.time() - 40 * 86400
        os.utime(p, (old, old))
        out = io.StringIO()
        with redirect_stdout(out):
            audit.main(["--root", str(self.root), "--days", "14"])
        self.assertIn("0 interactive session", out.getvalue())

    def test_project_filter_and_exclude(self):
        self.session([user("arreglá"), tool("Bash", {"command": "git commit -m x"}, "1"), result("1")])
        self.assertIn("0 interactive session", self.run_main("--project", "other"))
        self.assertIn("0 interactive session", self.run_main("--exclude", "aaaa"))


class Privacy(Base):
    def setUp(self):
        super().setUp()
        self.session([user("arreglá el bug, mi mail es juan@example.com <pasted_content id=\"1\">SECRETO</pasted_content id=\"1\">"),
                      tool("Bash", {"command": "git commit -m x"}, "1"), result("1")])

    def test_a_pipe_or_a_file_gets_locators_only(self):
        out = self.run_main(tty=False)
        self.assertIn("locators only", out)
        self.assertIn("unasked-outward", out)
        self.assertNotIn("arreglá", out)
        self.assertNotIn("git commit -m x", out)

    def test_a_terminal_gets_excerpts_with_pastes_and_addresses_masked(self):
        out = self.run_main(tty=True)
        self.assertIn("arreglá el bug", out)
        self.assertNotIn("SECRETO", out)
        self.assertNotIn("juan@example.com", out)

    def test_excerpts_to_a_pipe_need_the_flag(self):
        self.assertIn("arreglá el bug", self.run_main("--excerpts", tty=False))

    def test_a_run_writes_nothing(self):
        before = sorted((p, p.stat().st_mtime_ns) for p in self.root.rglob("*"))
        with tempfile.TemporaryDirectory() as cwd:
            old = os.getcwd(); os.chdir(cwd)
            try:
                self.run_main(tty=True)
                self.assertEqual(list(Path(cwd).iterdir()), [])
            finally:
                os.chdir(old)
        self.assertEqual(sorted((p, p.stat().st_mtime_ns) for p in self.root.rglob("*")), before)


class StaticallyReadOnly(unittest.TestCase):
    """The promise in the docstring, checked on the source: no API that writes,
    copies, deletes, runs a command or opens the network."""

    def test_the_source_has_no_write_run_or_network_call(self):
        tree = ast.parse((ROOT / "audit.py").read_text())
        names = {n.attr if isinstance(n, ast.Attribute) else n.id
                 for n in ast.walk(tree) if isinstance(n, (ast.Attribute, ast.Name))}
        for banned in ("write_text", "write_bytes", "unlink", "rmtree", "copy", "copyfile", "copytree",
                       "rename", "replace_file", "mkdir", "system", "popen", "Popen", "run", "urlopen",
                       "remove", "makedirs", "symlink_to", "touch"):
            if banned == "run":
                continue   # argparse/str methods share the name; subprocess is banned by import below
            self.assertNotIn(banned, names, banned)
        imports = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                   for a in n.names} | {n.module.split(".")[0] for n in ast.walk(tree)
                                         if isinstance(n, ast.ImportFrom) and n.module}
        for banned in ("subprocess", "shutil", "urllib", "http", "socket", "tempfile"):
            self.assertNotIn(banned, imports, banned)

    def test_every_open_is_for_reading(self):
        tree = ast.parse((ROOT / "audit.py").read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) == "open":
                modes = [a.value for a in n.args if isinstance(a, ast.Constant)] + \
                        [k.value.value for k in n.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)]
                self.assertFalse(any(set(str(m)) & set("wax+") for m in modes), modes)


if __name__ == "__main__":
    unittest.main()
