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
  ./run.py --repeat 5               # five samples each; disagreement is a result
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
import shutil
import subprocess
import sys
import tempfile
import threading
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

# A hung call must not wedge a worker for the rest of the run — but a ceiling
# that fires is PURE LOSS. On a subscription the currency is tokens, and a
# killed call has already spent every token it consumed while returning
# nothing. Measured, in one run: the fastest `reviewed` sample took 59s and
# cost $2.31; the slowest took 519s and cost $1.54. Nine times the wall clock,
# a third less money. Time is not the budget — so a tight timeout buys nothing
# and can destroy work already paid for.
#
# Hence two ceilings, not one. A routing reply that takes five minutes is
# wedged and should die fast; an orchestrator at fifteen minutes is working.
# Measured durations reach 798s under contention, and the process outlives what
# `duration_ms` reports, so the delegating ceiling carries real headroom.
TIMEOUT = 300            # single-agent scenarios (--timeout)
DELEGATE_TIMEOUT = 1800  # scenarios with delegate: true (--delegate-timeout)

WS_ROOT = Path(tempfile.gettempdir())   # set to <run>/workspaces in main()
COST_PER_CALL = 0.10    # --dry-run estimates only. Recalibrated 2026-09-04 with the
                        # sonnet agent / safe-mode opus judge defaults: a cold agent
                        # call ~$0.17, a judge ~$0.02-0.03, tool-heavy agents more.

# Two independent model choices, because they answer different questions.
#
# The agent under test runs on Sonnet: a model the user works with daily, and
# at the current price ladder (Sonnet 5 under half of Opus 5 per token) the
# single largest lever on a run's cost. It also makes the suite a robustness
# test — an agent file that steers Sonnet steers the stronger models too. When
# a scenario fails here and you suspect capability rather than the prompt,
# re-run that one with `--model opus` (or the model you actually talk to)
# before touching the agent.
#
# The judge runs on Opus: it is what decides PASS/FAIL, and a lenient judge
# turns every run green — the failure mode this harness exists to avoid. The
# judge's prompt is short, so the stronger model costs far less here than it
# would on the agent side. On a subscription the currency is rate-limit
# budget rather than dollars.
AGENT_MODEL = "sonnet"  # --model
JUDGE_MODEL = "opus"    # --judge-model


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
    delegate: bool = False   # record the subagent tree (costs nothing extra)
    execute: dict = field(default_factory=dict)   # {suite, symbol} → real tests
    timeout: int = 0         # per-scenario override; 0 → the ceiling below
    manual: bool = False     # excluded from a bare run; see load_scenarios
    workspace: str = ""      # fixture dir seeded into a fresh cwd per sample
    allow: str = ""          # --allowedTools, comma-separated
    deny: str = ""           # --disallowedTools, comma-separated

    @property
    def is_routing(self) -> bool:
        return self.category == "routing"

    @property
    def limit(self) -> int:
        """Seconds this scenario gets before it is abandoned."""
        return self.timeout or (DELEGATE_TIMEOUT if self.delegate else TIMEOUT)


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
                delegate=bool(raw.get("delegate", False)),
                execute=raw.get("exec", {}) or {},
                timeout=int(raw.get("timeout", 0)),
                manual=bool(raw.get("manual", False)),
                workspace=raw.get("workspace", ""),
                allow=raw.get("allow", ""),
                deny=raw.get("deny", ""),
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


def ask(prompt: str, agent: str = "", model: str = "",
        forward_subagents: bool = False, timeout: int = 0,
        cwd: Path = None, allow: str = "", deny: str = "",
        safe_mode: bool = False, system: str = "", tools: str = None) -> Reply:
    """One `claude -p` call. Returns the final text plus the raw event stream.

    The stream is kept whole, not just the answer: `parent_tool_use_id` and the
    timestamps in it are what a later visualiser needs to reconstruct who
    delegated to whom. Assertions only need `.text`; the rest is for the trace."""
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    if agent:
        cmd += ["--agent", agent]
    if model:
        cmd += ["--model", model]
    if forward_subagents:
        # Makes a spawned subagent's messages appear in the stream with
        # parent_tool_use_id set, instead of being collapsed into one tool
        # result. Without it there is no delegation tree to see.
        cmd.append("--forward-subagent-text")
    if allow:
        cmd += ["--allowedTools", allow]
    if deny:
        cmd += ["--disallowedTools", deny]
    if safe_mode:
        # Every customization off: CLAUDE.md, output styles, skills, hooks,
        # agents. A grader must not inherit the user's persona — measured: with
        # the default session the judge answered YES to "do your instructions
        # mention Senior Architect or Rioplatense?"; with --safe-mode, NO.
        # (`--bare` would do the same but skips keychain reads, so a
        # subscription session is not logged in.)
        cmd.append("--safe-mode")
    if system:
        # REPLACES Claude Code's default system prompt (~37k tokens, paid as a
        # cache write on every fresh session). The judge needs a paragraph.
        cmd += ["--system-prompt", system]
    if tools is not None:
        # "" disables every built-in tool. Variadic like the tool flags above,
        # so it must sit right before the `--` that ends flag parsing.
        cmd += ["--tools", tools]
    # `--` before the prompt, always. Both tool flags are variadic and swallow
    # every following argument until the next flag — comma-joined values do not
    # help. A trailing prompt becomes a tool name and the CLI exits with
    # "Input must be provided…", which arrives as an empty reply costing $0.00:
    # indistinguishable, at a glance, from an agent that ran and said nothing.
    cmd += ["--", prompt]
    limit = timeout or TIMEOUT
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=limit,
                              cwd=str(cwd) if cwd else None, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return Reply(text="", error=f"timed out after {limit}s")
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


def delegation_tree(events: list) -> dict:
    """Who spawned whom, from the raw stream.

    A `Task`/`Agent` tool_use in the parent's output names the subagent and
    carries the id its messages will be tagged with; every later event whose
    parent_tool_use_id matches belongs to that child.

    Lives here rather than in project.py because project.py already imports
    this module — putting it there and importing back would be a cycle."""
    spawned, activity = {}, {}
    for ev in events:
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                # Both names appear depending on the CLI version; looking for
                # only one of them reported "no delegation" on a run that had
                # spawned seven subagents.
                if block.get("type") == "tool_use" and block.get("name") in ("Task", "Agent"):
                    arg = block.get("input", {})
                    spawned[block.get("id", "?")] = {
                        "agent": arg.get("subagent_type", "?"),
                        "task": (arg.get("description") or "")[:70],
                    }
        pid = ev.get("parent_tool_use_id")
        if pid:
            activity[pid] = activity.get(pid, 0) + 1
    for tid, info in spawned.items():
        info["events"] = activity.get(tid, 0)
    return spawned


# --------------------------------------------------------------------------- #
# Running what the agent produced
# --------------------------------------------------------------------------- #
CODE_BLOCK = re.compile(r"```(?:js|javascript|jsx|ts|typescript|mjs)?[^\n]*\n(.*?)```",
                        re.DOTALL)


def extract_impl(reply: str, symbol: str) -> str:
    """The last fenced block that defines `symbol`.

    Agents commonly show a first cut and then the corrected version; the LAST
    block that actually defines the export is the deliverable. Picking the
    largest block instead would sometimes pick a worked example or a test file
    with more lines than the implementation."""
    blocks = [b for b in CODE_BLOCK.findall(reply)
              if re.search(rf"\b{re.escape(symbol)}\b", b)
              and re.search(rf"(function|const|let|var|class)\s+{re.escape(symbol)}\b", b)]
    return blocks[-1] if blocks else ""


def deliverable(sc: "Scenario", reply: str, ws: Path) -> tuple:
    """The code to grade, and where it came from.

    Two sources, because two kinds of task. When the agent works in a seeded
    workspace the deliverable is the FILE it edited — that is the artifact a
    colleague would pull, and reading it back also catches an agent that
    narrated a change it never wrote. Otherwise it is the fenced block."""
    src = sc.execute.get("from_file")
    if src and ws:
        path = ws / src
        if not path.exists():
            return "", f"missing {src} in the workspace"
        return path.read_text(), src
    return extract_impl(reply, sc.execute["symbol"]), "the reply"


def run_suite(code: str, suite: Path, symbol: str) -> dict:
    """Run the agent's code against a suite it never saw. Ground truth.

    This is the point of the whole mechanism: whether an implementation is
    correct is a fact, and asking an LLM judge to eyeball arbitrary code for
    bugs replaces that fact with an opinion. The suite only asserts behaviour
    the prompt explicitly specified — a hidden test for unstated behaviour
    would measure mind-reading."""
    if not code:
        return {"error": f"no code defining `{symbol}`"}
    shimmed = "export" not in code
    if shimmed:
        # The task was "write this function", not "pick a module system".
        # Failing here would score syntax compliance instead of correctness.
        code += f"\nexport {{ {symbol} }};\n"
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "candidate.mjs").write_text(code)
        (d / "suite.mjs").write_text(suite.read_text())
        try:
            p = subprocess.run(["node", str(d / "suite.mjs")],
                               capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return {"error": "suite timed out — infinite loop in the candidate?"}
        try:
            out = json.loads(p.stdout.strip() or "{}")
        except ValueError:
            return {"error": f"suite produced no verdict: "
                             f"{(p.stderr or p.stdout).strip()[:200]}"}
    out["shimmed_export"] = shimmed
    return out


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
    prompt = (f"CRITERION:\n{criterion}\n\nREPLY TO GRADE:\n---\n{reply}\n---\n\n"
              "Answer with exactly PASS or FAIL on the first line, then one "
              "sentence explaining why.")
    # A grader is a one-shot classifier: no tools, no customizations, and its
    # own one-paragraph system prompt instead of Claude Code's. Measured on one
    # scenario: the default session made the Opus judge cost ~$0.40 (tool
    # schemas alone were ~30k tokens of cache write); with --safe-mode,
    # --system-prompt and --tools "" the same verdict costs ~$0.004.
    r = ask(prompt, model=JUDGE_MODEL, safe_mode=True, system=JUDGE_PREAMBLE, tools="")
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


def tool_names(events: list) -> set:
    """Names of the tools the agent itself invoked (subagents excluded)."""
    out = set()
    for ev in events:
        if ev.get("parent_tool_use_id"):
            continue
        msg = ev.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                out.add(str(c.get("name")))
    return out


def tool_uses(events: list) -> int:
    """tool_use blocks issued by the agent itself (subagents have their own
    parent_tool_use_id and are not the agent's investigation)."""
    n = 0
    for ev in events:
        if ev.get("parent_tool_use_id"):
            continue
        msg = ev.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):     # a plain-text message, or a result event
            continue
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                n += 1
    return n


def check_score(sc: Scenario, score: dict) -> list:
    """Assertions over the executed suite, not over the prose."""
    a = sc.assertions
    if score.get("error"):
        return [f"suite did not run: {score['error']}"]
    total = score.get("total", 0)
    if not total:
        return ["suite reported no cases"]
    ratio = score.get("passed", 0) / total
    floor = a.get("min_score", 1.0)
    if ratio < floor:
        missed = ", ".join(f["name"] for f in score.get("failures", [])[:4])
        return [f"suite {score['passed']}/{total} (floor {floor:.0%}) — {missed}"]
    return []


@dataclass
class Result:
    sc: Scenario
    reply: Reply
    fails: list = field(default_factory=list)
    judged: object = None      # True / False / None(error) / "skipped"
    judge_why: str = ""
    judge_cost: float = 0.0
    score: dict = field(default_factory=dict)     # executed suite, if any
    spawned: dict = field(default_factory=dict)   # subagent tree, if any
    workspace: str = ""                           # seeded dir, kept for inspection

    @property
    def score_line(self) -> str:
        if not self.score or self.score.get("error"):
            return ""
        return f"{self.score.get('passed', 0)}/{self.score.get('total', 0)}"

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


def make_workspace(sc: Scenario) -> Path:
    """A fresh seeded directory for one sample, kept with the run.

    `cwd` is where the agent STARTS, not a wall it cannot cross — verified: an
    agent told explicitly not to self-limit wrote outside it with no error. So
    this buys isolation between samples and a record of what each one did, not
    containment. Real containment needs the OS (sandbox-exec, a container);
    `deny:` covers the commands worth refusing."""
    ws = Path(tempfile.mkdtemp(prefix=f"{sc.id}-", dir=WS_ROOT))
    if sc.workspace:
        shutil.copytree(ROOT / sc.workspace, ws, dirs_exist_ok=True)
    return ws


def run_one(sc: Scenario) -> Result:
    prompt = roster_prompt(sc.prompt) if sc.is_routing else sc.prompt
    # Every scenario gets its own EMPTY directory, not the harness repo. With
    # the harness as cwd, agents read scenarios/*.yaml and found their own test
    # ("precisamente para testear si eng-manager detecta bien…"), and every
    # conceptual question opened with a survey of a repo that isn't the user's.
    # An empty cwd is the honest stage: nothing to explore, nothing to leak.
    ws = make_workspace(sc)
    reply = ask(prompt, "" if sc.is_routing else sc.agent, AGENT_MODEL,
                forward_subagents=sc.delegate, timeout=sc.limit,
                cwd=ws, allow=sc.allow, deny=sc.deny)
    if reply.error:
        return Result(sc, reply, workspace=str(ws or ""))

    res = Result(sc, reply, fails=check(sc, reply.text), workspace=str(ws or ""))
    # `max_tools`: how much the agent INVESTIGATED, which no judge can see from
    # the reply. Counts tool_use blocks in the main lane of the event stream.
    # A conceptual question answered after a five-command survey of the repo
    # is a correct reply bought at the wrong price.
    if "max_tools" in sc.assertions:
        used = tool_uses(reply.events)
        if used > int(sc.assertions["max_tools"]):
            res.fails.append(f"used {used} tools, max {sc.assertions['max_tools']}")
    # `forbidden_tools`: names the agent must not have invoked at all. With an
    # access tier installed the host refuses them; without one this is the
    # only way to see that a read-only advisor quietly edited a file.
    if "forbidden_tools" in sc.assertions:
        hit = sorted(tool_names(reply.events) & set(sc.assertions["forbidden_tools"]))
        if hit:
            res.fails.append(f"invoked forbidden tool(s): {', '.join(hit)}")
    if sc.delegate:
        res.spawned = delegation_tree(reply.events)
    if sc.execute:
        code, origin = deliverable(sc, reply.text, ws)
        res.score = run_suite(code, ROOT / sc.execute["suite"],
                              sc.execute["symbol"])
        res.score["source"] = origin
        res.fails += check_score(sc, res.score)
    criterion = sc.assertions.get("judge")
    if criterion:
        # Judge even when a deterministic assertion already failed: two
        # independent signals on one run are cheaper than a second run later.
        ok, why, cost = judge(criterion, reply.text)
        res.judged, res.judge_why, res.judge_cost = ok, why, cost
    return res


@dataclass
class Aggregate:
    """One scenario and every sample taken of it. With --repeat 1 it is a
    passthrough, which is why nothing downstream had to learn two shapes."""
    sc: Scenario
    trials: list           # list[Result], len == --repeat

    @property
    def tally(self) -> dict:
        out = {}
        for r in self.trials:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    @property
    def status(self) -> str:
        """PASS or FAIL only when every sample agrees; FLAKY when they don't.

        A majority vote would call 3-of-5 green and throw away the two
        failures — which is precisely the evidence the extra samples were paid
        for. Disagreement is not a tie to break, it IS the finding: either the
        agent is inconsistent or the scenario is, and both are worth knowing.
        So FLAKY is not a pass. Asking for certainty and getting ambiguity
        means the answer is "we still don't know"."""
        seen = {r.status for r in self.trials}
        return seen.pop() if len(seen) == 1 else "FLAKY"

    @property
    def passes(self) -> int:
        return sum(1 for r in self.trials if r.status == "PASS")

    @property
    def lead(self) -> Result:
        """The sample to show when only one can be shown.

        A failing sample is the informative one: nobody opens a flaky scenario
        to read one of the runs that worked."""
        return next((r for r in self.trials if r.status != "PASS"), self.trials[0])

    @property
    def cost(self) -> float:
        return sum(r.cost for r in self.trials)


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def trial_record(r: Result) -> dict:
    """One sample, without its event stream — see persist() for why."""
    return {
        "status": r.status,
        "failures": r.fails,
        "judge": {"verdict": r.judged, "why": r.judge_why}
                 if "judge" in r.sc.assertions else None,
        "cost_usd": round(r.cost, 4),
        "agent_cost_usd": round(r.reply.cost, 4),
        "judge_cost_usd": round(r.judge_cost, 4),
        "duration_ms": r.reply.ms,
        "reply": r.reply.text,
        "error": r.reply.error,
        "score": r.score or None,
        "delegated_to": r.spawned or None,
    }


_partial_lock = threading.Lock()


def log_partial(outdir: Path, sc: Scenario, r: Result):
    """Append one finished sample the moment it lands.

    Insurance, not the product. `persist()` writes the real trace only when the
    whole run completes, and a run that delegates takes tens of minutes — one
    that died at minute 35 took every paid result with it, because the results
    existed nowhere but in memory. The money is spent either way; losing the
    data on top of it is the avoidable half.

    Deleted on success, where trace.jsonl supersedes it entirely."""
    rec = trial_record(r)
    rec["id"] = sc.id
    with _partial_lock:
        with (outdir / "partial.jsonl").open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def persist(aggs: list, outdir: Path):
    """Write the run to disk: a JSONL trace plus one file per scenario.

    The trace is the contract with everything downstream — a visualiser reads
    this, not the terminal output. One line per SCENARIO, never one per sample:
    the top-level fields describe the lead trial so every existing consumer
    keeps working, and `trials` carries the rest.

    Only the lead trial keeps its `events`. Full streams are by far the largest
    thing in this file, and --repeat 5 would make it five times heavier to
    replay four conversations nobody opens. Each sample keeps its reply text,
    which is what you actually read when a scenario turns out flaky."""
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / "trace.jsonl").open("w") as fh:
        for a in aggs:
            lead = a.lead
            fh.write(json.dumps({
                "id": a.sc.id,
                "category": a.sc.category,
                "agent": a.sc.agent or "(routing)",
                "prompt": a.sc.prompt,
                "status": a.status,
                "repeat": len(a.trials),
                "passes": a.passes,
                "tally": a.tally,
                "failures": lead.fails,
                "judge": {"verdict": lead.judged, "why": lead.judge_why}
                         if "judge" in a.sc.assertions else None,
                "cost_usd": round(a.cost, 4),
                "duration_ms": lead.reply.ms,
                "reply": lead.reply.text,
                "error": lead.reply.error,
                "score": lead.score or None,
                "delegated_to": lead.spawned or None,
                "trials": [trial_record(t) for t in a.trials],
                "events": lead.reply.events,
            }, ensure_ascii=False) + "\n")
        # Per-scenario markdown, for reading a failure without jq.
    for a in aggs:
        n = len(a.trials)
        head = a.status + (f"  {a.passes}/{n}" if n > 1 else "")
        body = [f"# {a.sc.id}  ({head})", "",
                f"- agent: `{a.sc.agent or '(routing)'}`",
                f"- category: {a.sc.category}",
                f"- cost: ${a.cost:.4f}", "",
                "## Prompt", "", a.sc.prompt]
        for i, r in enumerate(a.trials, 1):
            label = "## Reply" if n == 1 else f"## Sample {i}/{n} — {r.status}"
            if r.score_line:
                label += f"  ·  suite {r.score_line}"
            body += ["", label, ""]
            if r.spawned:
                body += ["Subagents: " + ", ".join(
                    f"`{v.get('agent')}`" for v in r.spawned.values()), ""]
            for f in r.score.get("failures", [])[:20]:
                body += [f"- ✕ {f['name']} — `{f['input']!r}` → `{f['got']}` "
                         f"(expected `{f['expected']}`)"]
            if r.score.get("failures"):
                body += [""]
            body += [r.reply.text or f"*(error: {r.reply.error})*"]
            if r.fails:
                body += ["", "Failed assertions:"] + [f"- {f}" for f in r.fails]
            if r.judge_why:
                body += ["", f"Judge: {r.judged} — {r.judge_why}"]
        (outdir / f"{a.sc.id}.md").write_text("\n".join(body) + "\n")
    return outdir


MARK = {"PASS": " ok ", "FAIL": "FAIL", "ERROR": "ERR ", "FLAKY": "FLKY"}


def report(aggs: list, outdir: Path, elapsed: float):
    print()
    repeated = any(len(a.trials) > 1 for a in aggs)
    for a in sorted(aggs, key=lambda x: (x.sc.category, x.sc.id)):
        share = f"{a.passes}/{len(a.trials)}  " if repeated else ""
        # Mean suite score across samples: one run of arbitrary generated code
        # says less than the average, and this column is the whole point of the
        # execution scenarios.
        scored = [t.score for t in a.trials if t.score and not t.score.get("error")]
        suite = ""
        if scored:
            mean = sum(s["passed"] / s["total"] for s in scored) / len(scored)
            suite = f"suite {mean:.0%}  "
        print(f"{MARK[a.status]}  {a.sc.category:12} {a.sc.id:28} "
              f"{share}{suite}${a.cost:.3f}")
        r = a.lead
        for f in r.fails:
            print(f"          {f}")
        if r.reply.error:
            print(f"          {r.reply.error}")
        if r.judged is False or (r.judged is None and "judge" in a.sc.assertions):
            print(f"          judge: {r.judge_why[:150]}")

    bad = [a for a in aggs if a.status != "PASS"]
    flaky = [a for a in aggs if a.status == "FLAKY"]
    total = sum(a.cost for a in aggs)
    tail = f" · {len(flaky)} flaky" if flaky else ""
    print(f"\n{len(aggs) - len(bad)}/{len(aggs)} passed{tail} · "
          f"${total:.2f} · {elapsed:.0f}s")
    print(f"run saved to {outdir}")
    if flaky:
        print("\na flaky scenario was never passing — it was sampling. Read the "
              "samples: if they disagree on the same question, the scenario is "
              "asking something the agent answers differently each time.")
    if bad:
        print("\nread the full reply before believing a failure — a judge FAIL "
              "can be the judge's mistake, not the agent's.")
    return 1 if bad else 0


def main():
    global AGENT_MODEL, JUDGE_MODEL, TIMEOUT, DELEGATE_TIMEOUT
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--category", help="run only this category")
    ap.add_argument("--only", help="run scenarios whose id contains this (comma-separated: any)")
    ap.add_argument("--list", action="store_true", help="list scenarios and exit")
    ap.add_argument("--dry-run", action="store_true", help="show what would run")
    ap.add_argument("--jobs", type=int, default=4, help="parallel calls (default 4)")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="take N samples of each scenario (default 1). A "
                         "single sample cannot tell a stable pass from a lucky "
                         "one; with N>1 a scenario whose samples disagree is "
                         "reported FLAKY instead of green. Costs N times as "
                         "much — use it when you changed something shared, or "
                         "on one scenario you don't trust")
    ap.add_argument("--model", default=AGENT_MODEL,
                    help="model for the agent under test (default sonnet: a model in "
                         "daily use, and the biggest lever on cost). Re-run a failure "
                         "that smells like capability with --model opus before "
                         "touching the agent")
    ap.add_argument("--judge-model", default=JUDGE_MODEL,
                    help=f"model for the PASS/FAIL judge (default {JUDGE_MODEL})")
    ap.add_argument("--timeout", type=int, default=TIMEOUT, metavar="S",
                    help=f"ceiling for a single-agent scenario (default {TIMEOUT})")
    ap.add_argument("--delegate-timeout", type=int, default=DELEGATE_TIMEOUT,
                    metavar="S",
                    help=f"ceiling for scenarios with delegate: true "
                         f"(default {DELEGATE_TIMEOUT}). A killed call has "
                         "already spent its tokens and returns nothing, so err "
                         "high — this catches hangs, it does not save money")
    args = ap.parse_args()

    AGENT_MODEL, JUDGE_MODEL = args.model, args.judge_model
    TIMEOUT, DELEGATE_TIMEOUT = args.timeout, args.delegate_timeout
    if args.repeat < 1:
        sys.exit("--repeat must be at least 1")

    scenarios = load_scenarios()
    if args.category:
        scenarios = [s for s in scenarios if s.category == args.category]
    if args.only:
        wanted = [o.strip() for o in args.only.split(",") if o.strip()]
        scenarios = [s for s in scenarios if any(o in s.id for o in wanted)]
    if not (args.category or args.only):
        # `manual` scenarios are opt-in. Some experiments are expensive and
        # already answered — the build-quality arms cost ~$12 and forty minutes
        # to re-confirm a result three separate runs agreed on. Deleting them
        # would throw away the scaffolding and the record; leaving them in the
        # default suite would tax every future run for no signal. Ask for them
        # by name when the question comes back.
        scenarios = [s for s in scenarios if not s.manual]
    if not scenarios:
        sys.exit("no scenarios matched")

    if args.list or args.dry_run:
        for s in scenarios:
            judged = " +judge" if "judge" in s.assertions else ""
            print(f"  {s.category:12} {s.id:28} agent={s.agent or '(routing)'}{judged}")
        calls = (len(scenarios) + sum(1 for s in scenarios if "judge" in s.assertions)
                 ) * args.repeat
        sampled = f" × {args.repeat} samples" if args.repeat > 1 else ""
        print(f"\n{len(scenarios)} scenarios{sampled} · ~{calls} calls · "
              f"~${calls * COST_PER_CALL:.2f}")
        return 0

    global WS_ROOT
    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = RUNS / started
    outdir.mkdir(parents=True, exist_ok=True)
    # Workspaces live with the run. What an agent DID — which files it wrote,
    # how many times it re-ran its own tests — is evidence the reply summarises
    # and sometimes omits. In the first build experiment it was found by
    # accident, in scratch directories left lying in the repo.
    WS_ROOT = outdir / "workspaces"
    WS_ROOT.mkdir(exist_ok=True)
    # Pin the run to the catalog version that was INSTALLED when it ran. The
    # installer stamps ~/.claude/.local-agents.json with the commit it copied;
    # without carrying it here a verdict cannot be tied to an agent version.
    manifest = INSTALLED_AGENTS.parent / ".local-agents.json"
    stamp = {"started": started, "model": args.model or "(cli default)",
             "judge_model": args.judge_model}
    try:
        stamp["catalog"] = json.loads(manifest.read_text())
    except (OSError, ValueError):
        stamp["catalog"] = None
    (outdir / "run.json").write_text(json.dumps(stamp, indent=2))
    cat = stamp["catalog"] or {}
    print(f"catalog {cat.get('catalog_commit', '?')[:7]}"
          f"{' (dirty)' if cat.get('catalog_dirty') else ''} installed {cat.get('installed_at', '?')}")
    sampled = f", {args.repeat} samples each" if args.repeat > 1 else ""
    print(f"running {len(scenarios)} scenarios{sampled} "
          f"with {args.jobs} parallel calls → {outdir.name}")
    t0 = time.time()
    # Whole-suite passes, not N back-to-back copies of each scenario. Samples of
    # the same prompt launched together all pay cache creation; separated by a
    # full pass, the later ones land on a warm prompt cache instead.
    tasks = [sc for _ in range(args.repeat) for sc in scenarios]

    def run_and_log(sc: Scenario) -> Result:
        r = run_one(sc)
        log_partial(outdir, sc, r)
        return r

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        flat = list(pool.map(run_and_log, tasks))
    by_id = {}
    for r in flat:
        by_id.setdefault(r.sc.id, []).append(r)
    aggs = [Aggregate(sc, by_id[sc.id]) for sc in scenarios]
    persist(aggs, outdir)
    (outdir / "partial.jsonl").unlink(missing_ok=True)
    return report(aggs, outdir, time.time() - t0)


if __name__ == "__main__":
    sys.exit(main())
