#!/usr/bin/env python3
"""run.py — behavioural harness for the local-agents catalog.

The catalog's own checks (validate.py) prove the FILES are well formed. Nothing
proved the agents BEHAVE as those files promise. This runs scenarios against the
installed agents and asserts the contracts they claim: hard rules, handoffs,
inherited reasoning, language register, and routing.

Usage:
  ./run.py                          # every scenario
  ./run.py --category hard-rule     # one category
  ./run.py --only qa-no-product     # one scenario (substring match)
  ./run.py --list                   # show scenarios without running
  ./run.py --dry-run                # show what would run, and the cost estimate

Each scenario costs a real API call (~$0.10-0.20, because every `claude -p`
opens a fresh session and pays cache creation on the agent's whole prompt), so
filters are not a convenience — they are how you avoid burning money debugging
one failing case.

Requires PyYAML and the `claude` CLI on PATH.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("run.py needs PyYAML — run: pip install pyyaml")

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "scenarios"
RUNS = ROOT / "runs"
INSTALLED_AGENTS = Path.home() / ".claude" / "agents"

TIMEOUT = 300           # a hung call must not wedge the whole run
COST_PER_CALL = 0.20    # calibrated from observed runs; --dry-run estimates only

# Two independent model choices, because they answer different questions.
#
# The agent under test should run on the model you ACTUALLY use — testing qa on
# Sonnet while you work with Opus measures an agent you never talk to. Default
# is empty: inherit whatever the CLI is configured with.
#
# The judge is a PASS/FAIL classifier over a short reply. Opus there is waste,
# so it defaults to a cheaper model. On a subscription the currency is
# rate-limit budget rather than dollars, and the judge is roughly half the
# calls in a full run.
AGENT_MODEL = ""        # --model
JUDGE_MODEL = "sonnet"  # --judge-model


# --------------------------------------------------------------------------- #
# Scenario model
# --------------------------------------------------------------------------- #
@dataclass
class Scenario:
    id: str
    category: str
    prompt: str
    agent: str = ""          # empty for routing scenarios: that IS the question
    expect: str = ""         # routing: the agent that should own this
    assertions: dict = field(default_factory=dict)

    @property
    def is_routing(self) -> bool:
        return self.category == "routing"


def load_scenarios() -> list:
    out = []
    for path in sorted(SCENARIOS.glob("*.yaml")):
        for raw in yaml.safe_load(path.read_text()) or []:
            out.append(Scenario(
                id=raw["id"],
                category=raw.get("category", path.stem),
                prompt=raw["prompt"].strip(),
                agent=raw.get("agent", ""),
                expect=raw.get("expect", ""),
                assertions=raw.get("assert", {}) or {},
            ))
    ids = [s.id for s in out]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        sys.exit(f"duplicate scenario ids: {sorted(dupes)}")
    return out


# --------------------------------------------------------------------------- #
# Talking to Claude
# --------------------------------------------------------------------------- #
@dataclass
class Reply:
    text: str
    cost: float = 0.0
    ms: int = 0
    events: list = field(default_factory=list)
    error: str = ""


def ask(prompt: str, agent: str = "", model: str = "") -> Reply:
    """One `claude -p` call. Returns the final text plus the raw event stream.

    The stream is kept whole, not just the answer: `parent_tool_use_id` and the
    timestamps in it are what a later visualiser needs to reconstruct who
    delegated to whom. Assertions only need `.text`; the rest is for the trace."""
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    if agent:
        cmd += ["--agent", agent]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return Reply(text="", error=f"timed out after {TIMEOUT}s")
    if proc.returncode != 0:
        return Reply(text="", error=f"exit {proc.returncode}: {proc.stderr.strip()[:200]}")

    events, text, cost, ms = [], "", 0.0, 0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        events.append(ev)
        if ev.get("type") == "result":
            text = ev.get("result", "") or text
            cost = ev.get("total_cost_usd", 0.0)
            ms = ev.get("duration_ms", 0)
    if not text:
        return Reply(text="", events=events, error="no result event in stream")
    return Reply(text=text.strip(), cost=cost, ms=ms, events=events)


def roster_prompt(task: str) -> str:
    """Build the routing question from the INSTALLED agent descriptions.

    Routing is the one thing that can't be tested by invoking an agent — the
    question is which one should be invoked. What decides that in every host is
    the description, so that is what gets tested, and it is read from what is
    installed rather than from the catalog: the installed copy is what runs."""
    lines = []
    for path in sorted(INSTALLED_AGENTS.glob("*.md")):
        m = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.DOTALL)
        if not m:
            continue
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except Exception:
            continue
        desc = re.sub(r"<example>.*?</example>", "", str(meta.get("description", "")),
                      flags=re.DOTALL)
        desc = " ".join(desc.split())
        if desc:
            lines.append(f"- {path.stem}: {desc}")
    return (
        "These agents are available:\n\n" + "\n".join(lines) +
        f"\n\nA user brings this task:\n\n  \"{task}\"\n\n"
        "Which ONE agent should handle it? Reply with the agent name only, "
        "nothing else."
    )


JUDGE_PREAMBLE = (
    "You are grading whether an AI agent's reply honours a stated contract.\n"
    "Judge ONLY the criterion given. Be strict but fair: a reply that satisfies "
    "the criterion in substance passes even if worded unexpectedly.\n\n"
)


def judge(criterion: str, reply: str) -> tuple:
    """Neutral LLM judge. Returns (passed, why, cost).

    Deliberately invoked WITHOUT --agent: grading the catalog with an agent from
    the same catalog would measure it against itself. An unparseable verdict is
    an ERROR, never a pass — a harness that fails toward green is worse than no
    harness."""
    prompt = (JUDGE_PREAMBLE +
              f"CRITERION:\n{criterion}\n\nREPLY TO GRADE:\n---\n{reply}\n---\n\n"
              "Answer with exactly PASS or FAIL on the first line, then one "
              "sentence explaining why.")
    r = ask(prompt, model=JUDGE_MODEL)
    if r.error:
        return None, f"judge call failed: {r.error}", r.cost
    head = r.text.strip().splitlines()[0].strip().upper() if r.text.strip() else ""
    why = " ".join(r.text.strip().splitlines()[1:]).strip() or r.text.strip()
    if head.startswith("PASS"):
        return True, why, r.cost
    if head.startswith("FAIL"):
        return False, why, r.cost
    return None, f"judge gave no verdict: {r.text[:120]}", r.cost


# --------------------------------------------------------------------------- #
# Assertions
# --------------------------------------------------------------------------- #
def check(sc: Scenario, reply: str) -> list:
    """Deterministic assertions. Returns a list of failure strings."""
    fails = []
    a = sc.assertions

    if sc.is_routing:
        picked = reply.strip().strip(".`").split()[0].lower() if reply.strip() else ""
        if picked != sc.expect:
            fails.append(f"routed to `{picked or '?'}`, expected `{sc.expect}`")
        return fails

    if "matches" in a and not re.search(a["matches"], reply, re.M):
        fails.append(f"does not match /{a['matches']}/")
    for needle in a.get("contains", []):
        if needle.lower() not in reply.lower():
            fails.append(f"missing `{needle}`")
    for needle in a.get("not_contains", []):
        if needle.lower() in reply.lower():
            fails.append(f"must not mention `{needle}`")
    if "max_words" in a:
        n = len(reply.split())
        if n > a["max_words"]:
            fails.append(f"{n} words, limit {a['max_words']}")
    return fails


@dataclass
class Result:
    sc: Scenario
    reply: Reply
    fails: list = field(default_factory=list)
    judged: object = None      # True / False / None(error) / "skipped"
    judge_why: str = ""
    judge_cost: float = 0.0

    @property
    def status(self) -> str:
        if self.reply.error:
            return "ERROR"
        if self.fails:
            return "FAIL"
        if self.judged is None and "judge" in self.sc.assertions:
            return "ERROR"
        if self.judged is False:
            return "FAIL"
        return "PASS"

    @property
    def cost(self) -> float:
        return self.reply.cost + self.judge_cost


def run_one(sc: Scenario) -> Result:
    prompt = roster_prompt(sc.prompt) if sc.is_routing else sc.prompt
    reply = ask(prompt, "" if sc.is_routing else sc.agent, AGENT_MODEL)
    if reply.error:
        return Result(sc, reply)

    res = Result(sc, reply, fails=check(sc, reply.text))
    criterion = sc.assertions.get("judge")
    if criterion:
        # Judge even when a deterministic assertion already failed: two
        # independent signals on one run are cheaper than a second run later.
        ok, why, cost = judge(criterion, reply.text)
        res.judged, res.judge_why, res.judge_cost = ok, why, cost
    return res


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def persist(results: list, started: str):
    """Write the run to disk: a JSONL trace plus one file per scenario.

    The trace is the contract with everything downstream — a visualiser reads
    this, not the terminal output."""
    outdir = RUNS / started
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / "trace.jsonl").open("w") as fh:
        for r in results:
            fh.write(json.dumps({
                "id": r.sc.id,
                "category": r.sc.category,
                "agent": r.sc.agent or "(routing)",
                "prompt": r.sc.prompt,
                "status": r.status,
                "failures": r.fails,
                "judge": {"verdict": r.judged, "why": r.judge_why}
                         if "judge" in r.sc.assertions else None,
                "cost_usd": round(r.cost, 4),
                "duration_ms": r.reply.ms,
                "reply": r.reply.text,
                "error": r.reply.error,
                "events": r.reply.events,
            }, ensure_ascii=False) + "\n")
        # Per-scenario markdown, for reading a failure without jq.
    for r in results:
        body = [f"# {r.sc.id}  ({r.status})", "",
                f"- agent: `{r.sc.agent or '(routing)'}`",
                f"- category: {r.sc.category}",
                f"- cost: ${r.cost:.4f} · {r.reply.ms} ms", "",
                "## Prompt", "", r.sc.prompt, "", "## Reply", "",
                r.reply.text or f"*(error: {r.reply.error})*"]
        if r.fails:
            body += ["", "## Failed assertions", ""] + [f"- {f}" for f in r.fails]
        if r.judge_why:
            body += ["", "## Judge", "", f"verdict: {r.judged}", "", r.judge_why]
        (outdir / f"{r.sc.id}.md").write_text("\n".join(body) + "\n")
    return outdir


MARK = {"PASS": " ok ", "FAIL": "FAIL", "ERROR": "ERR "}


def report(results: list, outdir: Path, elapsed: float):
    print()
    for r in sorted(results, key=lambda x: (x.sc.category, x.sc.id)):
        print(f"{MARK[r.status]}  {r.sc.category:12} {r.sc.id:28} "
              f"${r.cost:.3f}")
        for f in r.fails:
            print(f"          {f}")
        if r.reply.error:
            print(f"          {r.reply.error}")
        if r.judged is False or (r.judged is None and "judge" in r.sc.assertions):
            print(f"          judge: {r.judge_why[:150]}")

    bad = [r for r in results if r.status != "PASS"]
    total = sum(r.cost for r in results)
    print(f"\n{len(results) - len(bad)}/{len(results)} passed · "
          f"${total:.2f} · {elapsed:.0f}s")
    print(f"run saved to {outdir}")
    if bad:
        print("\nread the full reply before believing a failure — a judge FAIL "
              "can be the judge's mistake, not the agent's.")
    return 1 if bad else 0


def main():
    global AGENT_MODEL, JUDGE_MODEL
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--category", help="run only this category")
    ap.add_argument("--only", help="run scenarios whose id contains this")
    ap.add_argument("--list", action="store_true", help="list scenarios and exit")
    ap.add_argument("--dry-run", action="store_true", help="show what would run")
    ap.add_argument("--jobs", type=int, default=4, help="parallel calls (default 4)")
    ap.add_argument("--model", default=AGENT_MODEL,
                    help="model for the agent under test (default: the CLI's own). "
                         "Use the model you actually work with, or the test measures "
                         "an agent you never talk to")
    ap.add_argument("--judge-model", default=JUDGE_MODEL,
                    help=f"model for the PASS/FAIL judge (default {JUDGE_MODEL})")
    args = ap.parse_args()

    AGENT_MODEL, JUDGE_MODEL = args.model, args.judge_model

    scenarios = load_scenarios()
    if args.category:
        scenarios = [s for s in scenarios if s.category == args.category]
    if args.only:
        scenarios = [s for s in scenarios if args.only in s.id]
    if not scenarios:
        sys.exit("no scenarios matched")

    if args.list or args.dry_run:
        for s in scenarios:
            judged = " +judge" if "judge" in s.assertions else ""
            print(f"  {s.category:12} {s.id:28} agent={s.agent or '(routing)'}{judged}")
        calls = len(scenarios) + sum(1 for s in scenarios if "judge" in s.assertions)
        print(f"\n{len(scenarios)} scenarios · ~{calls} calls · "
              f"~${calls * COST_PER_CALL:.2f}")
        return 0

    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"running {len(scenarios)} scenarios with {args.jobs} parallel calls…")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(run_one, scenarios))
    outdir = persist(results, started)
    return report(results, outdir, time.time() - t0)


if __name__ == "__main__":
    sys.exit(main())
