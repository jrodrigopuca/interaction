#!/usr/bin/env python3
"""smoke.py — does what the catalog installs still work on each host?

run.py asks whether the agents BEHAVE as their files promise, on Claude Code,
with a judge. This asks something narrower and deterministic, on every host the
catalog installs into: after a project install,

  1. load       the agents are discovered where the installer put them
  2. skill      a catalog skill is visible to the agent
  3. read tier  `visionary` (access: read) cannot write a file, and can load skills
  4. full tier  `senior-dev` (access: full) can

Answered from the disk and the host's own listings, never from a judge. Every
host fact it relies on was measured by hand on 2026-10-11 and is pinned to a
host version that changes under us — so each run records those versions.

Usage:
  ./smoke.py                       # every host, free checks and paid ones
  ./smoke.py --host kiro           # one host (repeatable)
  ./smoke.py --free-only           # only checks that call no model
  ./smoke.py --free-only --strict  # as CI runs it: ERROR and SKIP fail too

Each paid check is one short call on the user's own subscription for that host.
An error that is not the catalog's — no login, no quota, a refused permission,
a timeout — is reported as such, with the host's own message, and never counted
as a failure of the catalog.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs-smoke"
READ_AGENT, FULL_AGENT, SKILL = "visionary", "senior-dev", "lh-tradeoffs"
TIMEOUT = 240
# Per-host model override, set from the command line. None → the host's own
# default. Recorded in the report: a different model is a different measurement.
MODELS = {}

# key: (install.py --tool, binary)
HOSTS = {
    "claude": ("claude", "claude"),
    "opencode": ("opencode", "opencode"),
    "kiro": ("kiro", "kiro-cli"),
    "codex": ("codex", "codex"),
    "antigravity": ("antigravity", "agy"),
}

# Same neutral Claude session run.py uses (see its NEUTRAL_SESSION comment).
CLAUDE_NEUTRAL = ["--setting-sources", "project,local", "--settings",
                  json.dumps({"permissions": {"allow": ["Read", "Edit", "Write"]}})]

# Errors that are not the catalog's. Order matters: first match wins.
ERROR_KINDS = [
    ("auth", r"401|unauthori[sz]ed|log ?in again|not logged in|sign in|authenticat"
             r"|token could not be refreshed|oauth|credentials"),
    ("subscription", r"subscription|free tier|quota|insufficient credit|out of credits|rate.?limit"
                     r"|\b429\b|billing|upgrade your plan|usage limit"),
    ("permission", r"requires approval|permission denied|not permitted"
                   r"|can.t be checked before it runs"),
    ("not installed", r"command not found|no such file or directory"),
]


def classify(text: str) -> str:
    low = (text or "").lower()
    for kind, pattern in ERROR_KINDS:
        if re.search(pattern, low):
            return kind
    return "unknown"


def sh(cmd: list, cwd: Path, timeout: int = TIMEOUT, env: dict = None) -> dict:
    """Run one host command with stdin closed — `codex exec` waits on stdin
    forever otherwise (measured) — and a hard timeout.

    PWD is set to the workspace too, not only the process cwd: opencode takes
    its directory from PWD (measured on 1.19.0 — it wrote the test file into
    the directory smoke.py was launched from, not the workspace)."""
    env = dict(env or os.environ, PWD=str(cwd))
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL, env=env)
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr, "timeout": False}
    except subprocess.TimeoutExpired as e:
        return {"rc": None, "out": (e.stdout or b"").decode(errors="replace")
                if isinstance(e.stdout, bytes) else (e.stdout or ""),
                "err": "", "timeout": True}
    except FileNotFoundError:
        return {"rc": 127, "out": "", "err": f"{cmd[0]}: command not found", "timeout": False}


def result(status: str, detail: str = "") -> dict:
    return {"status": status, "detail": detail}


def error_of(r: dict) -> dict:
    if r["timeout"]:
        return result("ERROR", f"timeout after {TIMEOUT}s")
    text = re.sub(r"\x1b\[[0-9;]*m", "", (r["err"] or "") + "\n" + (r["out"] or ""))
    tail = " ".join(text.strip().split())[-220:]
    return result("ERROR", f"{classify(text)}: {tail}")


# --------------------------------------------------------------------------- #
# Free checks — host listings, no model call
# --------------------------------------------------------------------------- #
def claude_init(ws: Path, agent: str) -> dict:
    """The init event of `claude -p --agent X` lists the session's tools and
    skills before any model call; the process is stopped right after it."""
    proc = subprocess.Popen(["claude", "-p", "reply OK", "--agent", agent,
                             "--output-format", "stream-json", "--verbose",
                             "--max-turns", "1", *CLAUDE_NEUTRAL],
                            cwd=str(ws), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("subtype") == "init":
                return ev
        return {}
    finally:
        proc.kill()


def free_checks(host: str, ws: Path) -> dict:
    out = {}
    if host == "claude":
        ev = claude_init(ws, READ_AGENT)
        if not ev:
            return {"load": result("ERROR", "no init event")}
        tools = set(ev.get("tools", []))
        out["load"] = result("PASS", f"{READ_AGENT} session started")
        out["skill"] = result("PASS" if SKILL in ev.get("skills", []) else "FAIL",
                              f"{len(ev.get('skills', []))} skills visible")
        leak = sorted(tools & {"Edit", "Write", "NotebookEdit", "Bash"})
        out["read floor"] = result("FAIL" if leak else "PASS",
                                   f"write tools available: {leak}" if leak
                                   else "no write tool in the allowlist")
        # Read-only is not skill-less: without `Skill` in the allowlist the
        # agent cannot load its own skills (harness run 20261014-003338: 0 of 8).
        out["read skill"] = result("PASS" if "Skill" in tools else "FAIL",
                                   "Skill in the read-tier allowlist" if "Skill" in tools
                                   else "no Skill tool: the read tier cannot load skills")
    elif host == "opencode":
        r = sh(["opencode", "agent", "list"], ws, 120)
        if r["rc"] != 0:
            return {"load": error_of(r)}
        names = set(re.findall(r"^([a-z][a-z0-9-]*) \(", r["out"], re.M))
        out["load"] = result("PASS" if {READ_AGENT, FULL_AGENT} <= names else "FAIL",
                             f"{len(names)} agents listed")
        tmp = ws / ".smoke-skills.json"
        with tmp.open("w") as fh:   # piped JSON gets cut short: write to a file
            subprocess.run(["opencode", "debug", "skill"], cwd=str(ws), stdout=fh,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=120,
                           env=dict(os.environ, PWD=str(ws)))
        raw = tmp.read_text()
        tmp.unlink()
        try:
            skills = json.loads(raw[raw.index("["):])
            hit = [s["location"] for s in skills if s.get("name") == SKILL]
            # opencode keeps ONE copy per name and which one varies by run
            # (measured): a global copy here is not a failure of the project
            # install, so say which copy it picked.
            where = ("project copy" if hit and hit[0].startswith(str(ws.resolve()))
                     or hit and hit[0].startswith(str(ws)) else "a global copy")
            out["skill"] = result("PASS" if hit else "FAIL",
                                  f"{where}: {hit[0]}" if hit else "not listed")
        except ValueError:
            out["skill"] = result("ERROR", "could not parse `opencode debug skill`")
    elif host == "kiro":
        r = sh(["kiro-cli", "agent", "list"], ws, 120)
        # Without a login kiro-cli refuses even to list agents (measured on
        # 2.29.1): the host's error, not an empty catalog.
        if r["rc"] != 0:
            return {"load": error_of(r)}
        # kiro-cli prints the listing on STDERR (measured on 2.29.1), after a
        # warning per agent that also exists globally ("Using workspace version").
        text = re.sub(r"\x1b\[[0-9;]*m", "", (r["out"] or "") + (r["err"] or ""))
        names = set(re.findall(r"^\s*\*?\s*([a-z][a-z0-9-]*)\s+Workspace", text, re.M))
        out["load"] = result("PASS" if {READ_AGENT, FULL_AGENT} <= names else "FAIL",
                             f"{len(names)} workspace agents listed")
    return out


# --------------------------------------------------------------------------- #
# Paid checks — one call per agent
# --------------------------------------------------------------------------- #
def prompt_for(agent: str) -> str:
    return (f"Create a file named smoke-{agent}.txt in the current directory "
            f"containing the word done. Do it yourself with your own tools; do not "
            f"delegate it to anyone. Then end your reply with exactly two lines: "
            f"'AGENT: <your agent name>' and 'SKILL: yes' or 'SKILL: no' — whether a "
            f"skill named {SKILL} is available to you.")


def ask(host: str, ws: Path, agent: str) -> dict:
    p = prompt_for(agent)
    if host == "claude":
        env = dict(os.environ, CLAUDE_CODE_SHELL="/bin/bash")
        return sh(["claude", "-p", "--agent", agent, "--model", "sonnet", "--max-turns", "6",
                   *CLAUDE_NEUTRAL, "--", p], ws, env=env)
    if host == "opencode":
        model = ["-m", MODELS["opencode"]] if MODELS.get("opencode") else []
        return sh(["opencode", "run", "--dir", str(ws), "--agent", agent, "--auto",
                   *model, p], ws)
    if host == "kiro":
        return sh(["kiro-cli", "chat", "--agent", agent, "--no-interactive",
                   "--trust-all-tools", p], ws)
    if host == "antigravity":
        return sh(["agy", "--agent", agent, "--mode", "accept-edits",
                   "--print-timeout", f"{TIMEOUT - 20}s", "-p", p], ws)
    if host == "codex":
        # Custom agents are spawned by the main agent. The session's sandbox
        # comes from config (-c), never from --sandbox: the flag overrides every
        # agent file, read-only included (measured on 0.144.5).
        spawn = (f"Spawn the custom agent named {agent} and give it this task "
                 f"verbatim: \"{p}\" Do NOT create any file yourself. Relay its "
                 f"reply verbatim, including its AGENT and SKILL lines.")
        return sh(["codex", "exec", "--skip-git-repo-check",
                   "-c", 'sandbox_mode="workspace-write"', spawn], ws)
    raise ValueError(host)


def paid_checks(host: str, ws: Path, out: dict) -> dict:
    replies = {}
    for agent in (READ_AGENT, FULL_AGENT):
        r = ask(host, ws, agent)
        reply = re.sub(r"\x1b\[[0-9;]*m", "", r["out"] or "")
        (ws / f".smoke-{agent}.log").write_text(
            f"rc={r['rc']} timeout={r['timeout']}\n--- stdout\n{reply}\n--- stderr\n{r['err']}")
        bad = r["timeout"] or r["rc"] not in (0,) or not reply.strip()
        replies[agent] = None if bad else reply
        if bad:
            out[f"{agent} call"] = error_of(r)

    written = lambda a: (ws / f"smoke-{a}.txt").is_file()
    # A host that resolves its directory from somewhere else writes the file
    # there: look in the places it could have gone, and say so.
    for a in (READ_AGENT, FULL_AGENT):
        for elsewhere in {Path.cwd(), ROOT, Path.home()}:
            stray = elsewhere / f"smoke-{a}.txt"
            if stray.is_file():
                stray.unlink()
                out[f"{a} wrote elsewhere"] = result(
                    "FAIL", f"wrote {stray} instead of the workspace (removed)")
    if replies[READ_AGENT] is not None:
        out["read tier"] = (result("FAIL", f"smoke-{READ_AGENT}.txt was written")
                            if written(READ_AGENT) else
                            result("PASS", "no file written"))
    if replies[FULL_AGENT] is not None:
        out["full tier"] = (result("PASS", "file written") if written(FULL_AGENT)
                            else result("FAIL", f"smoke-{FULL_AGENT}.txt missing"))
    if "load" not in out:
        named = [a for a, rep in replies.items()
                 if rep and re.search(rf"AGENT:\s*`?{re.escape(a)}", rep, re.I)]
        seen = [a for a, rep in replies.items() if rep]
        if seen:
            out["load"] = result("PASS" if len(named) == len(seen) else "FAIL",
                                 f"named itself: {named or 'none'} of {seen}")
    # Both agents are asked; the read tier's answer used to be paid for and
    # dropped, which is how a read tier with no skill access went unseen.
    for key, agent in (("skill", FULL_AGENT), ("read skill", READ_AGENT)):
        if key not in out and replies[agent]:
            yes = re.search(r"SKILL:\s*`?yes", replies[agent], re.I)
            out[key] = result("PASS" if yes else "FAIL",
                              f"{agent} reports the skill "
                              f"{'available' if yes else 'missing'}")
    return out


# --------------------------------------------------------------------------- #
def catalog_path() -> Path:
    manifest = Path.home() / ".claude" / ".local-agents.json"
    try:
        return Path(json.loads(manifest.read_text())["catalog_path"])
    except (OSError, ValueError, KeyError):
        return ROOT.parent / "local-agents"


def version(binary: str) -> str:
    r = sh([binary, "--version"], Path.cwd(), 60)
    return " ".join((r["out"] or r["err"]).split())[:80] or "?"


def git_head(path: Path) -> str:
    r = sh(["git", "rev-parse", "--short", "HEAD"], path, 10)
    dirty = sh(["git", "status", "--porcelain"], path, 10)["out"].strip()
    return (r["out"].strip() or "?") + (" (dirty)" if dirty else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", action="append", choices=sorted(HOSTS),
                    help="host to check (repeatable; default: all)")
    ap.add_argument("--free-only", action="store_true",
                    help="only the checks that call no model")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero on ERROR and SKIP too, not only FAIL (for CI, "
                         "where a host that did not answer must not pass as green)")
    ap.add_argument("--catalog", type=Path, default=None)
    ap.add_argument("--opencode-model", metavar="PROVIDER/MODEL",
                    help="model for opencode (e.g. opencode/big-pickle, free); "
                         "default: opencode's own configured model")
    args = ap.parse_args()
    hosts = args.host or list(HOSTS)
    if args.opencode_model:
        MODELS["opencode"] = args.opencode_model
    catalog = (args.catalog or catalog_path()).resolve()
    if not (catalog / "install.py").is_file():
        sys.exit(f"no install.py in {catalog}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = RUNS / stamp
    outdir.mkdir(parents=True, exist_ok=True)
    report = {"started": stamp, "catalog": str(catalog), "catalog_commit": git_head(catalog),
              "harness_commit": git_head(ROOT), "free_only": args.free_only, "hosts": {}}
    print(f"catalog {report['catalog_commit']} · harness {report['harness_commit']}"
          f"{' · free checks only' if args.free_only else ''}\n")

    for host in hosts:
        tool, binary = HOSTS[host]
        entry = {"version": version(binary), "model": MODELS.get(host) or "host default",
                 "checks": {}}
        report["hosts"][host] = entry
        if shutil.which(binary) is None:
            entry["checks"]["host"] = result("SKIP", f"{binary} not installed")
        else:
            # Outside this repo, and its own git root: a workspace inside the
            # harness let an agent climb to the repo with `git rev-parse`.
            ws = Path(tempfile.mkdtemp(prefix=f"smoke-{host}-"))
            sh(["git", "init", "-q"], ws, 30)
            inst = sh([sys.executable, str(catalog / "install.py"), "--all", "--tool", tool,
                       "--project", str(ws), "--on-conflict", "overwrite"], catalog, 300)
            if inst["rc"] != 0:
                entry["checks"]["install"] = error_of(inst)
            else:
                checks = free_checks(host, ws)
                if not args.free_only:
                    checks = paid_checks(host, ws, checks)
                entry["checks"] = checks
            entry["workspace"] = str(ws)
            logs = outdir / host
            logs.mkdir(exist_ok=True)
            for f in ws.glob(".smoke-*.log"):
                shutil.copy(f, logs / f.name[1:])
        print(f"{host:12} {entry['version']} · model: {entry['model']}")
        for name, c in entry["checks"].items():
            print(f"   {c['status']:5} {name:16} {c['detail'][:150]}")
        print()

    (outdir / "report.json").write_text(json.dumps(report, indent=2))
    statuses = [c["status"] for h in report["hosts"].values() for c in h["checks"].values()]
    print(" · ".join(f"{statuses.count(s)} {s}" for s in ("PASS", "FAIL", "ERROR", "SKIP")
                     if s in statuses) + f"  → {outdir}")
    bad = {"FAIL", "ERROR", "SKIP"} if args.strict else {"FAIL"}
    return 1 if bad & set(statuses) else 0


if __name__ == "__main__":
    sys.exit(main())
