#!/usr/bin/env python3
"""viz.py — render harness runs as self-contained HTML reports.

`run.py` asserts whether an agent honoured its contract. It cannot show you the
WORK: which tools the agent reached for, what it read, where it stalled, what it
retried. A green scenario can still hide two wasted calls hunting for a file.
And a verdict alone does not say whether it still describes what is installed
today — so the home page answers that first.

Usage:
  ./viz.py runs/20260804-083423                 # one run
  ./viz.py --index                              # every run, plus runs/index.html
  ./viz.py runs/A runs/B --compare              # same scenarios across two runs
  ./viz.py runs/latest -o report.html           # choose the output path

Writes HTML with no external resources — open it, no server needed. Rendering
reads files and hashes; it never calls a model.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent / "runs"
SMOKE_DIR = RUNS_DIR.parent / "runs-smoke"

# run.py owns the scenario model, the fingerprints and the applicability rules;
# the report reuses them instead of keeping a second copy that drifts. It needs
# PyYAML — without it the pages still render, minus everything that compares a
# run against today's scenarios and install.
try:
    import run as harness
except (ImportError, SystemExit):
    harness = None

TOOL_ICON = {"Bash": "▸", "Read": "◇", "Write": "✎", "Edit": "✎", "Glob": "⌕",
             "Grep": "⌕", "Skill": "◈", "Task": "⑂", "Agent": "⑂", "WebFetch": "⤓",
             "WebSearch": "⌕", "TodoWrite": "☰"}


# --------------------------------------------------------------------------- #
# Normalising the event stream
# --------------------------------------------------------------------------- #
def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def steps_from(events: list, spawns: set = frozenset()) -> list:
    """Flatten Claude's event stream into a readable sequence.

    Only `assistant` and `user` events carry timestamps; the `system` ones that
    report thinking carry a token delta instead. So ordering comes from the
    stream itself and time is used, where present, to show the gaps — never the
    other way round, or the thinking steps would collapse onto their neighbours.

    `parent_tool_use_id` becomes the lane: null is the agent you invoked, any
    other value is a subagent it spawned. Today's harness traces are single-lane;
    the same rendering shows a delegation tree the moment one isn't."""
    steps, prev_ts = [], None

    def push(step):
        # Consecutive thinking in one lane is one pause, not twenty. Twenty bars
        # in a row is a wall that buries the conversation running through it.
        if (step["kind"] == "think" and steps and steps[-1]["kind"] == "think"
                and steps[-1]["lane"] == step["lane"]):
            steps[-1]["weight"] += step["weight"]
            steps[-1]["detail"] = f'{steps[-1]["weight"]} tokens'
            return
        steps.append(step)

    for ev in events:
        kind = ev.get("type")
        lane = ev.get("parent_tool_use_id") or "main"
        ts = parse_ts(ev.get("timestamp"))
        gap = int((ts - prev_ts).total_seconds() * 1000) if (ts and prev_ts) else 0
        if ts:
            prev_ts = ts

        if kind == "system" and ev.get("subtype") == "thinking_tokens":
            delta = ev.get("estimated_tokens_delta") or 0
            if delta:
                push({"kind": "think", "lane": lane, "label": "thinking",
                      "detail": f"{delta} tokens", "weight": delta, "ms": 0})
            continue

        if kind == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    name = block.get("name", "tool")
                    # Spawning is already shown as "⑂ X joined"; drawing the
                    # tool call too says the same thing twice.
                    if name in ("Task", "Agent"):
                        continue
                    arg = block.get("input", {})
                    hint = (arg.get("command") or arg.get("file_path")
                            or arg.get("pattern") or arg.get("description")
                            or arg.get("skill") or "")
                    push({"kind": "tool", "lane": lane, "name": name,
                                  "label": f"{name}", "detail": str(hint),
                          "full": json.dumps(arg, ensure_ascii=False, indent=2),
                          "ms": gap})
                elif block.get("type") == "text" and block.get("text", "").strip():
                    text = block["text"].strip()
                    push({"kind": "text", "lane": lane,
                          "label": text.split("\n")[0][:90],
                          "detail": text, "ms": gap})

        elif kind == "user":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    # A subagent's return IS the message it just posted in its
                    # own lane. Rendering both makes every specialist speak
                    # twice — once as itself, once as data handed to the parent.
                    if block.get("tool_use_id") in spawns:
                        continue
                    body = block.get("content")
                    if isinstance(body, list):
                        body = " ".join(b.get("text", "") for b in body
                                        if isinstance(b, dict))
                    body = str(body or "")
                    push({"kind": "result", "lane": lane,
                          "label": "result",
                          "detail": body[:4000],
                          "error": bool(block.get("is_error")),
                          "ms": gap})
    return steps


def load_run(path: Path) -> dict:
    trace = path / "trace.jsonl"
    if not trace.exists():
        sys.exit(f"no trace.jsonl in {path}")
    scenarios = []
    for line in trace.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        events = rec.pop("events", [])
        rec["steps"] = steps_from(events, set(rec.get("delegated_to") or {}))
        # A lane id means nothing on screen. project.py records which subagent
        # each spawn id belongs to, so relabel the lanes with agent names.
        names = {k: v.get("agent", "?") for k, v in (rec.get("delegated_to") or {}).items()}
        for s in rec["steps"]:
            s["laneName"] = "main" if s["lane"] == "main" else names.get(s["lane"], s["lane"][-6:])
        scenarios.append(rec)
    return {"name": path.name, "scenarios": scenarios, "meta": read_meta(path)}


def read_meta(path: Path) -> dict:
    """run.json, written by run.py since 2026-09; older runs have none."""
    try:
        return json.loads((path / "run.json").read_text())
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------- #
# Provenance: what a run can be compared with
# --------------------------------------------------------------------------- #
def git(path, *args) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def nice_time(name: str, with_year: bool = True) -> str:
    """20261011-220947 → '11 Oct 2026, 22:09'. Run names ARE their start time."""
    try:
        t = datetime.strptime(name[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return name
    return t.strftime(f"%-d %b{' %Y' if with_year else ''}, %H:%M")


def short(commit, dirty=False) -> str:
    c = (commit or "")[:7]
    return c + ("*" if c and dirty else "")


def run_warnings(meta: dict) -> list:
    """What makes this run unlike a neutral default session, as short labels.

    An experiment is NOT one of these: it is declared (`--experiment`), and
    shown as its own tag. A user session predates that flag and keeps its own
    warning — it is what it is, whatever its author meant by it."""
    fp = meta.get("fingerprints")
    if not fp:
        return []
    out = []
    iso = fp.get("isolation")
    if not iso:
        out.append("Isolation not recorded")
    elif iso.startswith("USER SESSION"):
        out.append("User session · not neutral")
    styles = [s for s in (meta.get("effective") or {}).get("output_styles") or []
              if s != "default"]
    if styles and not (iso or "").startswith("USER SESSION"):
        out.append("Output style " + ", ".join(styles))
    return out


def is_neutral(meta: dict) -> bool:
    return bool(meta.get("fingerprints")) and not run_warnings(meta) \
        and not meta.get("experiment")


def model_matches(asked, got: list) -> bool | None:
    """Did the alias asked for resolve to the model that answered? None when
    either side is unknown — an old run, or a run on the CLI default."""
    if not asked or asked.startswith("(") or not got:
        return None
    return all(asked.lower() in g.lower() for g in got)


def denied_count(sc: dict) -> int:
    return sum(1 for t in trials_of(sc) if t.get("permission_denials"))


def trials_of(sc: dict) -> list:
    """Every sample. Traces from before --repeat (2026-08) have none: the
    scenario itself is its only sample."""
    return sc.get("trials") or [{
        "status": sc.get("status"), "failures": sc.get("failures") or [],
        "judge": sc.get("judge"), "cost_usd": sc.get("cost_usd", 0),
        "duration_ms": sc.get("duration_ms", 0), "reply": sc.get("reply"),
        "error": sc.get("error"), "score": sc.get("score"),
        "delegated_to": sc.get("delegated_to")}]


def lead_index(sc: dict) -> int:
    """Which sample the trace kept the events of — run.py's Aggregate.lead:
    the first that did not pass, else the first."""
    ts = trials_of(sc)
    return next((i for i, t in enumerate(ts) if t.get("status") != "PASS"), 0)


def summarize(d: Path) -> dict | None:
    """A run without its event streams: enough for the home page."""
    trace = d / "trace.jsonl"
    if not trace.exists():
        return None
    scs = []
    for line in trace.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            rec.pop("events", None)
            scs.append(rec)
    return {"name": d.name, "dir": d, "meta": read_meta(d), "scenarios": scs,
            "ids": [s["id"] for s in scs],
            "cost": sum(s.get("cost_usd") or 0 for s in scs),
            "samples": sum(s.get("repeat") or 1 for s in scs)}


# --------------------------------------------------------------------------- #
# What the report knows about TODAY: scenarios, install, every run's summary
# --------------------------------------------------------------------------- #
def context(runs_dir: Path = RUNS_DIR) -> dict:
    """Everything both pages compare a run against, loaded once.

    `full` is computed, never recorded: run.py does not write which filters a
    run used. A run counts as the full suite when it covered every default
    scenario that had appeared in any earlier run — a scenario added after it
    does not make it partial in hindsight — and at least half of today's."""
    scen = {s.id: s for s in harness.load_scenarios()} if harness else {}
    suite = [s for s in scen.values() if not s.manual and not s.experiment]
    suite_ids = {s.id for s in suite}
    model = harness.AGENT_MODEL if harness else ""
    appl = {r["id"]: r for r in harness.applicability_data(suite, model)} if harness else {}
    runs = [r for r in (summarize(d) for d in sorted(runs_dir.iterdir())
                        if d.is_dir()) if r] if runs_dir.exists() else []
    seen = set()
    for r in runs:
        ids = set(r["ids"])
        r["full"] = bool(suite_ids) and ids >= (suite_ids & seen) \
            and len(ids & suite_ids) >= len(suite_ids) / 2
        seen |= ids
    runs.reverse()   # newest first, from here on
    baseline = next((r for r in runs if r["full"] and is_neutral(r["meta"])), None)
    try:
        installed = json.loads((Path.home() / ".claude" / ".local-agents.json").read_text())
    except (OSError, ValueError):
        installed = {}
    return {"scen": scen, "suite": suite_ids, "manual": len(scen) - len(suite_ids),
            "model": model, "appl": appl, "runs": runs, "baseline": baseline,
            "by_name": {r["name"]: r for r in runs}, "installed": installed,
            "estimate": cost_estimate(runs)}


def cost_estimate(runs: list, window: int = 10) -> dict | None:
    """Average cost of one scenario sample over the latest runs that recorded
    costs. A guide for deciding, not a quote: scenarios differ several-fold."""
    paid = [r for r in runs if r["cost"] > 0][:window]
    samples = sum(r["samples"] for r in paid)
    if not samples:
        return None
    return {"per": sum(r["cost"] for r in paid) / samples, "runs": len(paid),
            "samples": samples}


def estimate_label(est) -> str:
    if not est:
        return "no past run recorded a cost to estimate from"
    return (f"estimated from past runs: ${est['per']:.3f} per scenario sample, the "
            f"average over the last {est['runs']} run(s) that recorded costs "
            f"({est['samples']} samples)")


def money(n: int, est) -> str:
    return f"≈ ${n * est['per']:.2f}" if est else "cost unknown"


# --------------------------------------------------------------------------- #
# Per-check results
# --------------------------------------------------------------------------- #
# How a trace from before per-check results (2026-10-12) still says which check
# failed: by the failure message each one writes. run.py's ACTION_CHECKS holds
# the action-side prefixes; the reply-side ones live in check().
REPLY_PREFIX = {"matches": "does not match /", "contains": "missing `",
                "not_contains": "must not mention `", "max_words": None,
                "min_score": "suite "}
NOTE_PASS = {"unchanged_files": "No fixture file was modified or deleted.",
             "forbid_text": "Not in any reply, nor in any file the agent created or modified."}


def failed_by(key: str, fails: list) -> list:
    if key == "max_words":
        return [f for f in fails if re.match(r"\d+ words, limit", f)]
    prefix = REPLY_PREFIX.get(key) or (harness.ACTION_CHECKS.get(key) if harness else None)
    return [f for f in fails if prefix and f.startswith(prefix)] if prefix else []


def shown_value(key: str, val) -> str:
    if isinstance(val, list):
        return "  ".join(f"/{v}/" if key in ("forbid_commands",) else str(v) for v in val)
    if key == "matches":
        return f"/{val}/"
    return json.dumps(val, ensure_ascii=False) if isinstance(val, dict) else str(val)


def check_rows(sc: dict, asserts: dict, expect: str) -> list:
    """One row per deterministic assertion, across every sample: how many held,
    and whether "held" was ever tested. From the trial's own `checks` when the
    trace has them; derived from its failure messages when it does not."""
    ts = trials_of(sc)
    n = len(ts)
    keys = [k for k in asserts if k != "judge"]
    rows = []
    if expect:
        keys = ["routing"] + keys
    for key in keys:
        val = expect if key == "routing" else asserts.get(key)
        recorded = [next((c for c in (t.get("checks") or []) if c.get("check") == key), None)
                    for t in ts]
        if all(recorded):
            results = [c["result"] for c in recorded]
            details = [c.get("detail") for c in recorded if c.get("detail")]
            derived = False
        else:
            results, details = [], []
            for t in ts:
                fails = t.get("failures") or []
                if key == "routing":
                    bad = [f for f in fails if f.startswith("routed to")]
                else:
                    bad = failed_by(key, fails)
                tools = t.get("tools_used", "missing")
                if bad:
                    results.append("fail")
                    details += bad
                elif key == "forbid_commands" and tools != "missing" \
                        and "Bash" not in (tools or []):
                    results.append("vacuous")
                elif key not in REPLY_PREFIX and key != "routing" and not (
                        harness and key in harness.ACTION_CHECKS):
                    results.append("unrecorded")
                else:
                    results.append("pass")
            derived = True
        held = sum(1 for r in results if r in ("pass", "vacuous"))
        vac = results.count("vacuous")
        if "unrecorded" in results:
            st, why = "NA", ("", "No result was recorded for this check.")
        else:
            st = "PASS" if held == n else "FAIL" if held == 0 else "FLAKY"
            if details:
                uniq = list(dict.fromkeys(details))
                why = ("", " · ".join(uniq[:3]) + (f" · +{len(uniq) - 3} more" if len(uniq) > 3 else ""))
            elif vac == n:
                why = ("Not exercised:", "no Bash command was attempted in any sample, "
                       "so this held without being tested.")
            elif vac:
                why = ("Not exercised", f"in {vac} of {n} samples (no Bash command there).")
            elif key == "forbid_commands" and "missing" not in [t.get("tools_used", "missing") for t in ts]:
                bash = sum(1 for t in ts if "Bash" in (t.get("tools_used") or []))
                why = ("Exercised:", f"Bash used in {bash} of {n} samples; no command matched.")
            else:
                why = ("", NOTE_PASS.get(key, "Held in every sample."))
        rows.append({"k": key, "v": shown_value(key, val), "st": st, "held": f"{held}/{n}",
                     "note": why[0], "why": why[1], "derived": derived})
    return rows


def scenario_spec(sc: dict, meta: dict, ctx: dict) -> dict:
    """What this scenario was measured against, and how sure we are of it.

    Since 2026-10-12 the trace carries the assertions verbatim; before that the
    only source is today's YAML, which is right only while the scenario's
    fingerprint is unchanged — so the page says when it is not."""
    cur = ctx["scen"].get(sc["id"])
    then = ((meta.get("fingerprints") or {}).get("scenarios") or {}).get(sc["id"])
    changed = bool(cur and then and then != cur.fingerprint)
    if "assert" in sc:
        asserts, src = sc.get("assert") or {}, "run"
    elif cur:
        asserts, src = cur.assertions, "today"
    else:
        asserts, src = {}, "none"
    expect = cur.expect if (cur and cur.is_routing) else ""
    # A YAML block keeps the author's line wrapping; only blank lines are meant.
    judge = re.sub(r"(?<!\n)\n(?!\n)", " ", (asserts.get("judge") or "").strip())
    out = {"checks": check_rows(sc, asserts, expect), "judge": judge,
           "src": src, "changed": None, "workspace": cur.workspace if cur else "",
           "defined": bool(cur), "unknown": src == "today" and not then}
    if changed:
        a = ctx["appl"].get(sc["id"]) or {}
        out["changed"] = {"then": then[:8], "now": cur.fingerprint[:8], "latest": {
            "st": a.get("status"), "n": f"{a.get('passes', 0)}/{a.get('repeat', 1)}",
            "run": a.get("run"), "at": nice_time(a.get("run") or "", False),
            "trust": a.get("class")} if a.get("run") else None}
    return out


# --------------------------------------------------------------------------- #
# HTML — shared
# --------------------------------------------------------------------------- #
# Two independent channels, everywhere: HUE is the verdict (pass, fail, flaky,
# error), FILL is the trust (solid current, striped partial, hollow historic).
# Neither borrows the other's, so a green-but-stale verdict reads as both.
# Dark only: one palette to keep legible, and the reports are read at a desk.
CSS = """
:root{
  color-scheme:dark;
  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px;
  --space-5:24px; --space-6:32px; --space-7:48px; --space-8:64px;
  --text-xs:12px; --text-sm:14px; --text-md:16px; --text-lg:20px; --text-xl:24px; --text-2xl:32px;
  --weight-regular:400; --weight-strong:600;
  --radius-sm:4px; --radius-md:8px; --radius-pill:999px;
  --font-sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  --font-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  --page-max:1120px;
  --bg:#141413; --surface:#1c1c1a; --surface-sunk:#232320;
  --border:#30302c; --border-strong:#4a4a44;
  --text:#ecece7; --text-muted:#a8a8a1;
  --accent:#8fb2f0; --accent-soft:#1e293b;
  --pass:#6cc596; --pass-soft:#15281d;
  --fail:#f0897d; --fail-soft:#311a17;
  --flaky:#b9a1f2; --flaky-soft:#251d35;
  --error:#e6a656; --error-soft:#2d2213;
  --warn:#ecbb52; --warn-soft:#2b2411; --warn-line:#a67c10;
  --trust:#d6d6cf;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);
  font:var(--weight-regular) var(--text-sm)/1.5 var(--font-sans)}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
code,.mono{font-family:var(--font-mono);font-size:var(--text-xs)}
code{background:var(--surface-sunk);padding:1px var(--space-1);border-radius:var(--radius-sm);word-break:break-all}
button{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:var(--radius-sm)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.wrap{max-width:var(--page-max);margin:0 auto;padding:0 var(--space-4)}
.muted{color:var(--text-muted)}
.top{border-bottom:1px solid var(--border);background:var(--surface)}
.top .wrap{display:flex;align-items:center;gap:var(--space-4);min-height:48px;flex-wrap:wrap}
.brand{font-weight:var(--weight-strong);font-size:var(--text-sm)}
.brand span{color:var(--text-muted);font-weight:var(--weight-regular)}
.nav{display:flex;gap:var(--space-1);flex-wrap:wrap}
.nav a{color:var(--text-muted);padding:var(--space-3) var(--space-2);font-size:var(--text-sm)}
.nav a[aria-current]{color:var(--text);box-shadow:inset 0 -2px 0 var(--text)}
.head{padding:var(--space-6) 0 var(--space-5)}
.head h1{font-size:var(--text-xl);margin:0 0 var(--space-1);letter-spacing:-.01em}
.head p{margin:0;color:var(--text-muted);max-width:75ch}
.facts{display:flex;flex-wrap:wrap;gap:var(--space-1) var(--space-4);margin-top:var(--space-3);
  font-size:var(--text-xs);color:var(--text-muted)}
.facts b{color:var(--text);font-weight:var(--weight-strong)}
section{margin:0 0 var(--space-7)}
.sec-h{display:flex;align-items:baseline;gap:var(--space-3);flex-wrap:wrap;margin:0 0 var(--space-3)}
.sec-h h2{font-size:var(--text-md);margin:0}
.sec-h .q{color:var(--text-muted);font-size:var(--text-sm)}
.sec-h .end{margin-left:auto;font-size:var(--text-xs);color:var(--text-muted)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md)}
.label{font-size:var(--text-xs);font-weight:var(--weight-strong);letter-spacing:.06em;
  text-transform:uppercase;color:var(--text-muted);margin:0 0 var(--space-2)}
.empty-card{padding:var(--space-5);font-size:var(--text-sm)}
.empty-card p{margin:0 0 var(--space-2)} .empty-card p:last-child{margin:0}
.st{display:inline-flex;align-items:center;gap:var(--space-1);font:var(--weight-strong) var(--text-xs)/1 var(--font-sans);
  letter-spacing:.04em;padding:3px var(--space-2);border-radius:var(--radius-pill);white-space:nowrap}
.st::before{font-size:11px}
.st.PASS{color:var(--pass);background:var(--pass-soft)} .st.PASS::before{content:"✓"}
.st.FAIL{color:var(--fail);background:var(--fail-soft)} .st.FAIL::before{content:"✕"}
.st.FLAKY{color:var(--flaky);background:var(--flaky-soft)} .st.FLAKY::before{content:"≈"}
.st.ERROR{color:var(--error);background:var(--error-soft)} .st.ERROR::before{content:"!"}
.st.NA,.st.SKIP{color:var(--text-muted);background:transparent;font-weight:var(--weight-regular)}
.st.dim{opacity:.55}
.tr{display:inline-flex;align-items:center;gap:var(--space-1);font-size:var(--text-xs);white-space:nowrap;color:var(--text)}
.tr i{display:inline-block;width:10px;height:10px;border-radius:50%;border:1.5px solid var(--trust);flex:none}
.tr.current i{background:var(--trust)}
.tr.partial i{background:linear-gradient(90deg,var(--trust) 50%,transparent 50%)}
.tr.historic i,.tr.never i{background:transparent}
.tr.never i{border-style:dotted}
.tag{display:inline-flex;align-items:center;gap:var(--space-1);font:var(--weight-strong) 11px/1 var(--font-sans);
  letter-spacing:.05em;text-transform:uppercase;padding:4px var(--space-2);border-radius:var(--radius-sm);
  border:1px solid var(--border-strong);color:var(--text-muted);white-space:nowrap}
.tag.full{background:var(--text);color:var(--surface);border-color:var(--text)}
.tag.exp{border-style:dashed;color:var(--text)}
.tag.warn{color:var(--warn);border-color:var(--warn-line);
  background:repeating-linear-gradient(135deg,var(--warn-soft) 0 5px,transparent 5px 10px)}
.tag.warn::before{content:"⚠";font-size:11px}
.tag.plain{text-transform:none;letter-spacing:0;font-weight:var(--weight-regular);font-family:var(--font-mono)}
.chip{border:1px solid var(--border);background:var(--surface);border-radius:var(--radius-pill);
  padding:var(--space-1) var(--space-3);font-size:var(--text-xs);cursor:pointer;min-height:32px;color:var(--text-muted)}
.chip[aria-pressed="true"]{background:var(--text);color:var(--surface);border-color:var(--text)}
.chip .n{font-variant-numeric:tabular-nums;opacity:.8;margin-left:var(--space-1)}
.btn{border:1px solid var(--border-strong);background:var(--surface);border-radius:var(--radius-sm);
  padding:var(--space-2) var(--space-3);cursor:pointer;min-height:36px;font-size:var(--text-xs);color:var(--text)}
.kv dt{font-size:var(--text-xs);color:var(--text-muted)}
.kv dd{margin:0;font-size:var(--text-sm);overflow-wrap:anywhere}
.kv dd small{display:block;color:var(--text-muted);font-size:var(--text-xs)}
.score{font-size:var(--text-2xl);font-weight:var(--weight-strong);letter-spacing:-.02em;line-height:1;
  font-variant-numeric:tabular-nums}
.score small{font-size:var(--text-sm);color:var(--text-muted);font-weight:var(--weight-regular);letter-spacing:0}
details.more summary{cursor:pointer;color:var(--accent);font-size:var(--text-xs);margin-top:var(--space-2);
  list-style:none;min-height:24px;display:inline-flex;align-items:center}
details.more summary::-webkit-details-marker{display:none}
details.more summary::before{content:"▸ "} details.more[open] summary::before{content:"▾ "}
.idlist{margin:var(--space-2) 0 0;padding:0;list-style:none;font:11px/1.7 var(--font-mono);color:var(--text-muted);
  columns:2 220px;column-gap:var(--space-4)}
.idlist li{break-inside:avoid;display:flex;gap:var(--space-2);align-items:center}
.idlist a{color:var(--text-muted)}
footer{padding:var(--space-6) 0 var(--space-8);color:var(--text-muted);font-size:var(--text-xs)}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

HOME_CSS = """
.fresh{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr)}
.fresh > div{padding:var(--space-5)}
.fresh > div + div{border-left:1px solid var(--border)}
.big{font-size:var(--text-lg);line-height:1.35;margin:0 0 var(--space-2);max-width:40ch}
.big b{font-size:var(--text-2xl);font-weight:var(--weight-strong);letter-spacing:-.02em}
.bar{display:flex;height:16px;border-radius:var(--radius-sm);overflow:hidden;border:1px solid var(--trust);
  margin:var(--space-4) 0 var(--space-2)}
.bar span{display:block;height:100%}
.bar .c{background:var(--trust)}
.bar .p{background:repeating-linear-gradient(135deg,var(--trust) 0 1.5px,transparent 1.5px 6px)}
.bar .h{background:transparent}
.bar .h + .x{border-left:1px dotted var(--trust)}
.legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:var(--space-3) var(--space-4);
  margin:var(--space-4) 0 0;padding:0;list-style:none}
.legend li{font-size:var(--text-xs);color:var(--text-muted)}
.legend b{display:flex;align-items:center;gap:var(--space-2);font-size:var(--text-sm);color:var(--text)}
.legend b .n{font-variant-numeric:tabular-nums}
.verdicts{margin-top:var(--space-4);padding-top:var(--space-4);border-top:1px dashed var(--border);
  font-size:var(--text-sm);display:flex;gap:var(--space-2);align-items:center;flex-wrap:wrap}
.reasons{list-style:none;margin:0 0 var(--space-5);padding:0;display:grid;gap:var(--space-2)}
.reasons li{display:grid;grid-template-columns:170px minmax(0,1fr) 28px;gap:var(--space-2);align-items:center;font-size:var(--text-xs)}
.reasons .rb{height:8px;border-radius:2px;background:var(--surface-sunk);overflow:hidden}
.reasons .rb span{display:block;height:100%;background:var(--text-muted)}
.reasons li.key .rb span{background:var(--text)}
.reasons li.key{font-weight:var(--weight-strong)}
.reasons .n{text-align:right;font-variant-numeric:tabular-nums}
.next{border:1px solid var(--border-strong);border-radius:var(--radius-md);padding:var(--space-4)}
.next h3{font-size:var(--text-sm);margin:0 0 var(--space-1)}
.next p{margin:0 0 var(--space-3);font-size:var(--text-xs);color:var(--text-muted)}
.opts{display:grid;gap:var(--space-2)}
.opt{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:var(--space-1) var(--space-3);
  padding:var(--space-3);background:var(--surface-sunk);border-radius:var(--radius-sm)}
.opt b{font-size:var(--text-sm)}
.opt .cost{font-variant-numeric:tabular-nums;font-weight:var(--weight-strong);text-align:right;white-space:nowrap}
.opt .sub{grid-column:1/-1;font-size:var(--text-xs);color:var(--text-muted)}
.opt code{grid-column:1/-1;display:block;padding:var(--space-2);background:var(--surface);font-size:11px;line-height:1.5}
.est{font-style:italic}
.base-h{display:flex;flex-wrap:wrap;gap:var(--space-3) var(--space-5);align-items:flex-start;
  padding:var(--space-5);border-bottom:1px solid var(--border)}
.prov{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:var(--space-2) var(--space-5);flex:1;min-width:260px;margin:0}
.tbl{width:100%;border-collapse:collapse;font-size:var(--text-sm)}
.tbl th{font-size:var(--text-xs);color:var(--text-muted);font-weight:var(--weight-strong);text-align:left;
  padding:var(--space-2) var(--space-4);border-bottom:1px solid var(--border);white-space:nowrap}
.tbl td{padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--border);vertical-align:top}
.tbl tr:last-child td{border-bottom:0}
.tbl .id{font-family:var(--font-mono);font-size:var(--text-xs);overflow-wrap:anywhere}
.tbl .sub{display:block;font-size:var(--text-xs);color:var(--text-muted);margin-top:2px}
.arrow{color:var(--text-muted)}
.base-foot{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:var(--space-4);
  padding:var(--space-4) var(--space-5);border-top:1px solid var(--border);background:var(--surface-sunk);
  border-radius:0 0 var(--radius-md) var(--radius-md);font-size:var(--text-xs);color:var(--text-muted)}
.base-foot b{color:var(--text)}
.allpass{padding:var(--space-4) var(--space-5);color:var(--text-muted);font-size:var(--text-sm)}
.matrix{width:100%;border-collapse:collapse}
.matrix th,.matrix td{padding:var(--space-3);border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
.matrix thead th{font-size:var(--text-xs);color:var(--text-muted);font-weight:var(--weight-strong);white-space:nowrap}
.matrix tbody th{font-weight:var(--weight-strong)}
.matrix tbody th small{display:block;font:var(--weight-regular) var(--text-xs)/1.4 var(--font-mono);color:var(--text-muted)}
.matrix td .d{display:block;font-size:11px;color:var(--text-muted);margin-top:var(--space-1);max-width:24ch;line-height:1.35;overflow-wrap:anywhere}
.matrix tr:last-child th,.matrix tr:last-child td{border-bottom:0}
.hist-note{font-size:var(--text-xs);color:var(--text-muted);padding:var(--space-3) var(--space-4);
  border-top:1px solid var(--border);background:var(--surface-sunk);border-radius:0 0 var(--radius-md) var(--radius-md)}
.hist-note ul{margin:var(--space-1) 0 0;padding-left:var(--space-4)}
.filters{display:flex;flex-wrap:wrap;gap:var(--space-2);margin:0 0 var(--space-3)}
.runs{list-style:none;margin:0;padding:0}
.day{display:flex;gap:var(--space-3);align-items:baseline;padding:var(--space-5) var(--space-4) var(--space-2);
  font-size:var(--text-xs);color:var(--text-muted);border-bottom:1px solid var(--border)}
.day b{color:var(--text);font-size:var(--text-sm)}
.run{display:grid;grid-template-columns:64px 112px minmax(0,1fr) 150px 120px 64px;gap:var(--space-3);
  align-items:start;padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--border);
  color:inherit;text-decoration:none}
.run:hover{background:var(--surface-sunk);text-decoration:none}
.run .t{font:var(--text-xs)/1.9 var(--font-mono);color:var(--text-muted)}
.res{display:grid;gap:var(--space-1)}
.res .frac{font-weight:var(--weight-strong);font-variant-numeric:tabular-nums}
.res .frac small{font-weight:var(--weight-regular);color:var(--text-muted);font-size:var(--text-xs)}
.mini{display:flex;height:4px;border-radius:2px;overflow:hidden;background:var(--surface-sunk);width:96px}
.mini .p{background:var(--pass)} .mini .f{background:var(--fail)} .mini .k{background:var(--flaky)} .mini .e{background:var(--error)}
.what .line{display:flex;flex-wrap:wrap;gap:var(--space-2);align-items:center}
.what .sum{font-size:var(--text-sm)}
.what .ids{display:block;font:11px/1.5 var(--font-mono);color:var(--text-muted);margin-top:var(--space-1);overflow-wrap:anywhere}
.what .xp{display:block;font-size:var(--text-xs);color:var(--text-muted);margin-top:var(--space-1)}
.cfg,.cat{font:var(--text-xs)/1.6 var(--font-mono);color:var(--text-muted);overflow-wrap:anywhere}
.cfg b,.cat b{color:var(--text);font-weight:var(--weight-regular)}
.cfg b.diff{font-weight:var(--weight-strong)}
.cost{font:var(--text-xs)/1.9 var(--font-mono);text-align:right;font-variant-numeric:tabular-nums}
.run.is-baseline{box-shadow:inset 3px 0 0 var(--text)}
.run.is-warn{box-shadow:inset 3px 0 0 var(--warn-line)}
.runs-head{display:grid;grid-template-columns:64px 112px minmax(0,1fr) 150px 120px 64px;gap:var(--space-3);
  padding:var(--space-2) var(--space-4);font-size:var(--text-xs);font-weight:var(--weight-strong);color:var(--text-muted);
  border-bottom:1px solid var(--border)}
.runs-head span:last-child{text-align:right}
.runs li.old{display:none} .runs.show-old li.old{display:block}
.older{display:flex;justify-content:space-between;gap:var(--space-3);flex-wrap:wrap;align-items:center;
  padding:var(--space-4);font-size:var(--text-xs);color:var(--text-muted)}
.empty{padding:var(--space-6) var(--space-4);text-align:center;color:var(--text-muted);display:none}
@media (max-width:900px){
  .fresh{grid-template-columns:1fr}
  .fresh > div + div{border-left:0;border-top:1px solid var(--border)}
  .runs-head{display:none}
  .run{grid-template-columns:56px minmax(0,1fr) auto;grid-template-areas:"t res cost" "t what what" "t cfg cat"}
  .run .t{grid-area:t} .run .res{grid-area:res} .run .what{grid-area:what}
  .run .cfg{grid-area:cfg} .run .cat{grid-area:cat} .run .cost{grid-area:cost}
  .res{grid-auto-flow:column;justify-content:start;align-items:center;gap:var(--space-2)}
}
@media (max-width:640px){
  .fresh > div,.base-h{padding:var(--space-4)}
  .big b{font-size:var(--text-xl)}
  .reasons li{grid-template-columns:130px minmax(0,1fr) 24px}
  .run{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"t cost" "res res" "what what" "cfg cfg" "cat cat"}
  .matrix thead{display:none}
  .matrix,.matrix tbody,.matrix tr,.matrix th,.matrix td{display:block;width:100%}
  .matrix tr{padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--border)}
  .matrix tr:last-child{border-bottom:0}
  .matrix tbody th,.matrix td{border:0;padding:var(--space-1) 0}
  .matrix td{display:flex;gap:var(--space-2);align-items:baseline;flex-wrap:wrap}
  .matrix td::before{content:attr(data-k);min-width:84px;font-size:var(--text-xs);color:var(--text-muted)}
  .matrix td .d{max-width:none;margin:0}
  .tbl.stack thead{display:none}
  .tbl.stack,.tbl.stack tbody,.tbl.stack tr,.tbl.stack td{display:block;width:100%}
  .tbl.stack tr{padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--border)}
  .tbl.stack td{border:0;padding:var(--space-1) 0}
}
"""


def esc(s):
    return html.escape(str(s if s is not None else ""))


def top_bar(home: str, current: str) -> str:
    links = [("evidence", "Health"), ("baseline", "Baseline"), ("hosts", "Hosts"),
             ("history", "Runs")]
    cur = ' aria-current="page"'
    nav = "".join(f'<a href="{home}#{k}"{cur if k == current else ""}>{v}</a>' for k, v in links)
    return (f'<header class="top"><div class="wrap"><div class="brand">interaction '
            f'<span>· agent harness</span></div><nav class="nav" aria-label="Sections">{nav}'
            f'</nav></div></header>')


def page(title: str, css: str, body: str, script: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}{css}</style></head><body>
{body}
{f"<script>{script}</script>" if script else ""}
</body></html>"""


def st_chip(status, text=None) -> str:
    status = status or "NA"
    return f'<span class="st {esc(status)}">{esc(text if text is not None else status)}</span>'


def trust_chip(cls: str, label: str = None) -> str:
    c = "never" if cls == "never run" else cls
    return f'<span class="tr {esc(c)}"><i></i>{esc(cls if label is None else label)}</span>'


def frac(passes, repeat) -> str:
    return f"{passes}/{repeat}"


# --------------------------------------------------------------------------- #
# HTML — home (runs/index.html)
# --------------------------------------------------------------------------- #
REASONS = [("agent changed", "agent changed"), ("skills changed", "skills changed"),
           ("permissions changed", "permissions changed"),
           ("session isolation changed", "session isolation changed"),
           ("model ", "model changed")]


def only_flag(ids: list, ctx: dict) -> tuple:
    """`--only` for exactly these ids, and how many scenarios it really picks:
    run.py matches by substring, so an id inside a longer one drags it in."""
    picked = [s for s in ctx["scen"] if any(i in s for i in ids)]
    return f"./run.py --only {','.join(ids)}", len(picked)


def home_freshness(ctx: dict) -> str:
    rows = list(ctx["appl"].values())
    if not rows:
        return ('<div class="card empty-card"><p><b>Freshness unavailable.</b></p>'
                '<p class="muted">The report could not load run.py (it needs PyYAML), so no '
                'verdict can be checked against today\'s install.</p></div>')
    est = ctx["estimate"]
    by = {k: [r for r in rows if r["class"] == k] for k in ("current", "partial", "historic", "never run")}
    total = len(rows)
    n_cur, n_par, n_his, n_nev = (len(by[k]) for k in ("current", "partial", "historic", "never run"))
    if not n_cur and not n_par:
        # Nothing checkable at all: say so plainly, with what fixes it.
        return (f'<div class="card empty-card"><p><b>No verdict can be checked against '
                f"today's install.</b></p><p class=\"muted\">{n_his} of {total} latest verdicts "
                f'are historic and {n_nev} scenario(s) never ran. One full run '
                f'(<code>./run.py</code>, {money(total, est)}, {esc(estimate_label(est))}) '
                f'records the fingerprints that make them comparable.</p>'
                f'<div class="bar" role="img" aria-label="{n_his} historic, {n_nev} never run">'
                f'<span class="h" style="width:100%"></span></div></div>')
    pct = lambda n: f"{100 * n / total:.2f}%"
    lead = ("All" if n_cur == total else "Only" if n_cur < total / 2 else "")
    sub = []
    if n_par:
        sub.append(f"{n_par} were reached before something around them changed.")
    if n_his:
        sub.append(f"{n_his} are historic: the scenario changed or the run predates fingerprints.")
    else:
        sub.append("None is historic: every scenario still has a verdict for its current definition.")
    if n_nev:
        sub.append(f"{n_nev} never ran.")
    st_tally = {}
    for r in rows:
        if r["run"]:
            st_tally[r["status"]] = st_tally.get(r["status"], 0) + 1
    verdicts = "".join(
        f'<span class="st {k}{"" if st_tally.get(k) else " dim"}">{st_tally.get(k, 0)} {k}</span>'
        for k in ("PASS", "FLAKY", "FAIL", "ERROR") if st_tally.get(k) or k in ("PASS", "FAIL"))
    bad = [r for r in rows if r["run"] and r["status"] != "PASS"]
    if bad and len(bad) <= 4:
        verdicts += ('<span class="muted">· not passing: ' + ", ".join(
            f'<a class="mono" href="{esc(r["run"])}/report.html#{esc(r["id"])}">{esc(r["id"])}</a> '
            f'{esc(frac(r["passes"], r["repeat"]))}, {esc(r["class"])}' for r in bad) + '</span>')

    def idlist(rs, verdict=True):
        return '<ul class="idlist">' + "".join(
            f'<li>{st_chip(r["status"], frac(r["passes"], r["repeat"])) if verdict and r["run"] else ""}'
            f'<a href="{esc(r["run"])}/report.html#{esc(r["id"])}">{esc(r["id"])}</a></li>'
            if r["run"] else f'<li>{esc(r["id"])}</li>' for r in rs) + "</ul>"

    left = (f'<p class="big">{lead} <b>{n_cur}</b> of {total} latest verdicts describe what is '
            f'installed today.</p><p class="muted" style="margin:0;max-width:60ch">{" ".join(sub)}</p>'
            f'<div class="bar" role="img" aria-label="{n_cur} current, {n_par} partial, {n_his} historic, {n_nev} never run">'
            + (f'<span class="c" style="width:{pct(n_cur)}"></span>' if n_cur else "")
            + (f'<span class="p" style="width:{pct(n_par)}"></span>' if n_par else "")
            + (f'<span class="h" style="width:{pct(n_his + n_nev)}"></span>' if n_his + n_nev else "")
            + '</div><ul class="legend">'
            f'<li><b>{trust_chip("current", "")}<span class="n">{n_cur}</span> current</b>'
            'Same scenario, agent, skills, model, session isolation and permissions.</li>'
            f'<li><b>{trust_chip("partial", "")}<span class="n">{n_par}</span> partial</b>'
            'Same scenario; the agent, skills, model, isolation or permissions changed.</li>'
            f'<li><b>{trust_chip("historic", "")}<span class="n">{n_his}</span> historic</b>'
            'The scenario changed, or the run predates fingerprints.</li>'
            f'<li><b>{trust_chip("never run", "")}<span class="n">{n_nev}</span>&nbsp;never run</b>'
            'Defined, but no run has ever covered it.</li></ul>'
            f'<div class="verdicts"><span class="muted">Latest verdicts:</span>{verdicts}</div>'
            + (f'<details class="more"><summary>The {n_cur} current verdicts</summary>{idlist(by["current"])}</details>'
               if n_cur else ""))

    # Why the partial ones are partial, and what a rerun would buy.
    right = ""
    if n_par:
        counts = [(label, sum(1 for r in by["partial"] if any(w.startswith(p) for w in r["why"])))
                  for p, label in REASONS]
        right += f'<p class="label">Why {n_par} are partial</p><ul class="reasons">' + "".join(
            f'<li class="{"key" if label == "agent changed" else ""}"><span>{esc(label)}</span>'
            f'<span class="rb"><span style="width:{100 * n / n_par:.0f}%"></span></span>'
            f'<span class="n">{n}</span></li>' for label, n in counts) + "</ul>"
    if n_his:
        hc = {}
        for r in by["historic"]:
            for w in r["why"]:
                hc[w] = hc.get(w, 0) + 1
        right += f'<p class="label">Why {n_his} are historic</p><ul class="reasons">' + "".join(
            f'<li><span>{esc(w)}</span><span class="rb"><span style="width:{100 * n / n_his:.0f}%"></span>'
            f'</span><span class="n">{n}</span></li>' for w, n in sorted(hc.items(), key=lambda x: -x[1])) + "</ul>"
    opts = []
    agent_changed = [r for r in by["partial"] if "agent changed" in r["why"]]
    if agent_changed:
        ids = [r["id"] for r in agent_changed]
        per = {}
        for r in agent_changed:
            a = ctx["scen"][r["id"]].agent or "(routing)"
            per[a] = per.get(a, 0) + 1
        cmd, picked = only_flag(ids, ctx)
        rest = n_par - len(agent_changed)
        opts.append(
            f'<div class="opt"><b>Rerun the {len(ids)} whose agent changed</b>'
            f'<span class="cost">{money(picked, est)}</span><span class="sub">'
            + esc(" · ".join(f"{a} {n}" for a, n in sorted(per.items(), key=lambda x: -x[1])))
            + (f". The other {rest} stay partial (skills, isolation or permissions)." if rest else ".")
            + (f" The filter matches {picked} scenarios by substring." if picked != len(ids) else "")
            + f'</span><code>{esc(cmd)}</code>'
            f'<details class="more" style="grid-column:1/-1"><summary>The {len(ids)} scenarios</summary>'
            f'{idlist(agent_changed, False)}</details></div>')
    stale = by["historic"] + by["never run"]
    if stale:
        cmd, picked = only_flag([r["id"] for r in stale], ctx)
        opts.append(
            f'<div class="opt"><b>Run the {len(stale)} historic or never-run</b>'
            f'<span class="cost">{money(picked, est)}</span><span class="sub">Gives each a verdict '
            f'against its current definition.</span><code>{esc(cmd)}</code></div>')
    base = ctx["baseline"]
    missing = sorted(ctx["suite"] - set(base["ids"])) if base else []
    opts.append(
        f'<div class="opt"><b>New full baseline</b><span class="cost">{money(total, est)}</span>'
        f'<span class="sub">All {total} current'
        + (f", and the first baseline that includes the {len(missing)} scenario(s) added since." if missing else ".")
        + '</span><code>./run.py</code></div>')
    right += ('<div class="next"><h3>What would make it current — your call</h3>'
              f'<p>Costs are an estimate, not a quote — <span class="est">{esc(estimate_label(est))}</span>, '
              'at one sample each. Nothing runs from this page.</p>'
              f'<div class="opts">{"".join(opts)}</div></div>')
    return f'<div class="card fresh"><div>{left}</div><div>{right}</div></div>'


def history_of(sid: str, ctx: dict, after: str) -> list:
    """Every verdict on one scenario in runs after `after`, oldest first."""
    out = []
    for r in reversed(ctx["runs"]):
        if r["name"] <= after:
            continue
        sc = next((s for s in r["scenarios"] if s["id"] == sid), None)
        if sc:
            out.append((r["name"], sc))
    return out


def comparability(a: dict, b: dict) -> list:
    """Why two runs' verdicts cannot be set side by side, as short reasons."""
    out = []
    for key, what in (("judge_model", "judge"), ("model", "agent model")):
        if a.get(key) != b.get(key):
            out.append(f'{what} was <span class="mono">{esc(b.get(key) or "?")}</span>, '
                       f'now <span class="mono">{esc(a.get(key) or "?")}</span>')
    if not b.get("fingerprints"):
        out.append("the run has no fingerprints")
    return out


def home_baseline(ctx: dict) -> tuple:
    base = ctx["baseline"]
    est = ctx["estimate"]
    full = [r for r in ctx["runs"] if r["full"]]
    if not base:
        latest = full[0] if full else None
        why = ""
        if latest:
            p = sum(1 for s in latest["scenarios"] if s["status"] == "PASS")
            why = (f'The latest full run ({nice_time(latest["name"], False)}, {p}/{len(latest["ids"])}) '
                   + ("has no provenance" if not latest["meta"].get("fingerprints") else "was not neutral")
                   + ", so it is shown in the history, not here. ")
        return "", (f'<div class="card empty-card"><p><b>No full baseline yet.</b></p>'
                    f'<p class="muted">{why}<code>./run.py</code> {money(len(ctx["suite"]), est)}.</p></div>')
    meta = base["meta"]
    scs = base["scenarios"]
    passed = sum(1 for s in scs if s["status"] == "PASS")
    cat = meta.get("catalog") or {}
    fp = meta.get("fingerprints") or {}
    eff = meta.get("effective") or {}
    inst = ctx["installed"]
    behind = ""
    if cat.get("catalog_commit") and inst.get("catalog_commit") \
            and cat["catalog_commit"] != inst["catalog_commit"]:
        n = git(inst.get("catalog_path", ""), "rev-list", "--count",
                f'{cat["catalog_commit"]}..{inst["catalog_commit"]}')
        behind = (f'<small>{esc(n + " commits" if n else "older")} before installed '
                  f'<span class="mono">{esc(short(inst["catalog_commit"]))}</span></small>')
    elif cat.get("catalog_commit"):
        behind = "<small>same as installed</small>"
    harn = fp.get("harness") or {}
    rep = max((s.get("repeat") or 1) for s in scs)
    prov = (f'<dl class="prov kv">'
            f'<div><dt>Ran</dt><dd>{esc(nice_time(base["name"]))}</dd></div>'
            f'<div><dt>Catalog</dt><dd><span class="mono">{esc(short(cat.get("catalog_commit")))}</span> '
            f'{"dirty" if cat.get("catalog_dirty") else "clean"}{behind}</dd></div>'
            f'<div><dt>Agent / judge</dt><dd>{esc(", ".join(eff.get("agent_models") or [meta.get("model", "?")]))} / '
            f'{esc(", ".join(eff.get("judge_models") or [meta.get("judge_model", "?")]))}</dd></div>'
            f'<div><dt>Harness · CLI</dt><dd><span class="mono">{esc(short(harn.get("commit")))}</span> '
            f'{"dirty" if harn.get("dirty") else "clean"} · {esc(fp.get("cli") or "?")}</dd></div>'
            f'<div><dt>Cost</dt><dd>${base["cost"]:.2f} · {rep} sample{"s" if rep > 1 else ""} each</dd></div></dl>')
    rows = []
    for s in sorted((s for s in scs if s["status"] != "PASS"),
                    key=lambda s: (ctx["appl"].get(s["id"], {}).get("class") != "current", s["id"])):
        later = history_of(s["id"], ctx, base["name"])
        a = ctx["appl"].get(s["id"])
        if later:
            name, last = later[-1]
            before = [frac(x.get("passes", 0), x.get("repeat") or 1) for _, x in later[:-1]]
            sub = nice_time(name, False) + (f" · after {', '.join(before)}" if before else "")
            if (last.get("repeat") or 1) == 1:
                sub += " · one sample only"
            since = (f'{st_chip(s["status"])} <span class="arrow">→</span> '
                     f'{st_chip(last["status"], frac(last.get("passes", 0), last.get("repeat") or 1))}'
                     f'<span class="sub">{esc(sub)}</span>')
        else:
            since = f'{st_chip(s["status"])} <span class="sub">no run since</span>'
        if a:
            short_why = ", ".join(w.replace(" changed", "") for w in a["why"])
            trust = trust_chip(a["class"]) + (
                f'<span class="sub">{esc(short_why + (" changed" if a["class"] == "partial" else ""))}</span>'
                if a["why"] else "")
        else:
            trust = '<span class="muted">no longer defined</span>'
        rows.append(f'<tr><td class="id"><a href="{esc(base["name"])}/report.html#{esc(s["id"])}">'
                    f'{esc(s["id"])}</a></td><td>{esc(s.get("agent"))}</td><td>{since}</td><td>{trust}</td></tr>')
    table = (f'<table class="tbl stack"><caption class="sr">Scenarios that did not pass in the '
             f'baseline, and their latest verdict</caption><thead><tr><th>Did not pass in the baseline</th>'
             f'<th>Agent</th><th>Since then</th><th>Trust now</th></tr></thead><tbody>{"".join(rows)}'
             f'</tbody></table>') if rows else '<p class="allpass">Every scenario passed in this baseline.</p>'
    foot = []
    added = sorted(ctx["suite"] - set(base["ids"]))
    if added:
        foot.append(f'<div><b>Not in this baseline — {len(added)} added later.</b> '
                    f'{esc(", ".join(added))}. Their only evidence is targeted runs.</div>')
    prev = next((r for r in full if r["name"] < base["name"]), None)
    if prev:
        pp = sum(1 for s in prev["scenarios"] if s["status"] == "PASS")
        why = comparability(meta, prev["meta"])
        foot.append(f'<div><b>Previous full suite: {esc(nice_time(prev["name"], False))}, {pp}/{len(prev["ids"])}.</b> '
                    + (f'Not comparable — {"; ".join(why)}. A change in score is not a regression '
                       f'until both run under the same conditions.' if why else
                       'Same models, both with provenance: the scores compare.') + '</div>')
    tags = '<span class="tag full">Full suite</span><span class="tag">neutral</span>'
    body = (f'<div class="card"><div class="base-h"><div><div class="score">{passed}'
            f'<small>/{len(scs)} passed</small></div><div style="margin-top:var(--space-2);display:flex;'
            f'gap:var(--space-2);flex-wrap:wrap">{tags}</div></div>{prov}</div>{table}'
            + (f'<div class="base-foot">{"".join(foot)}</div>' if foot else "") + '</div>')
    return f'<a class="end" href="{esc(base["name"])}/report.html">Open run {esc(base["name"])} →</a>', body


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def home_hosts(smoke_dir: Path) -> tuple:
    """Latest smoke result per host. A later report replaces an earlier one for
    the same host — a rerun after an auth error is the answer, not noise — and
    what it replaced is listed underneath, so the error is not erased."""
    reports = []
    for f in sorted(smoke_dir.glob("*/report.json")) if smoke_dir.exists() else []:
        try:
            reports.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    if not reports:
        return "", ('<div class="card empty-card"><p><b>No smoke results in runs-smoke/.</b></p>'
                    '<p class="muted">Nothing has checked whether the catalog installs and behaves '
                    'in each host. <code>./smoke.py --free-only</code> does it without calling a '
                    'model.</p></div>')
    latest, older = {}, {}
    for rep in reports:
        for host, entry in (rep.get("hosts") or {}).items():
            if host in latest:
                older.setdefault(host, []).append(latest[host])
            latest[host] = (rep, entry)
    commits = [rep.get("catalog_commit") for rep, _ in latest.values()]
    usual = max(set(commits), key=commits.count)
    harnesses = [rep.get("harness_commit") for rep, _ in latest.values()]
    cols = []
    for rep, entry in latest.values():
        for name in entry.get("checks") or {}:
            if name not in cols:
                cols.append(name)
    rows = []
    for host, (rep, entry) in latest.items():
        checks = entry.get("checks") or {}
        cells = []
        for c in cols:
            if c in checks:
                d = ANSI.sub("", checks[c].get("detail") or "")
                cells.append(f'<td data-k="{esc(c)}">{st_chip(checks[c].get("status"))}'
                             f'<span class="d">{esc(d[:140])}</span></td>')
            else:
                cells.append(f'<td data-k="{esc(c)}"><span class="st NA" title="not in this host\'s '
                             f'latest report">— n/a</span></td>')
        # Only what sets this host apart: a rerun that replaced a failure, a
        # catalog other than the one most hosts were checked against.
        note = []
        if any(st in ("FAIL", "ERROR") for _, e in older.get(host, [])
               for st in (c.get("status") for c in (e.get("checks") or {}).values())):
            note.append("rerun")
        if rep.get("catalog_commit") != usual:
            note.append(f'catalog {rep.get("catalog_commit")}')
        if rep.get("free_only"):
            note.append("free checks only")
        model = entry.get("model")
        rows.append(f'<tr><th>{esc(host)}<small>{esc(entry.get("version") or "?")}</small></th>'
                    f'<td data-k="model">{esc(model) if model else "<span class=muted>not recorded</span>"}</td>'
                    + "".join(cells) +
                    f'<td data-k="ran" class="mono">{esc(nice_time(rep.get("started", ""), False))}'
                    + (f'<span class="d" style="font-family:var(--font-sans)">{esc(" · ".join(note))}</span>' if note else "")
                    + '</td></tr>')
    sup = []
    for host, olds in older.items():
        for rep, entry in olds:
            bad = {k: v for k, v in (entry.get("checks") or {}).items()
                   if v.get("status") in ("FAIL", "ERROR")}
            if not bad:
                continue
            details = list(dict.fromkeys(ANSI.sub("", v.get("detail") or "").strip() for v in bad.values()))
            sup.append(f'<li>{esc(host)} at {esc(nice_time(rep.get("started", ""), False))} — '
                       + " ".join(st_chip(v.get("status")) for v in {v["status"]: v for v in bad.values()}.values())
                       + f' {esc(", ".join(bad))}: <span class="mono">{esc("; ".join(d[:120] for d in details))}</span></li>')
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = (f'<div class="card"><table class="matrix"><thead><tr><th>Host</th><th>Model</th>{head}'
            f'<th>Ran</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            + (f'<div class="hist-note"><b>Superseded by a later report for the same host:</b>'
               f'<ul>{"".join(sup)}</ul></div>' if sup else "") + '</div>')
    end = (f'catalog <span class="mono">{esc(usual)}</span> · harness '
           f'<span class="mono">{esc(max(set(harnesses), key=harnesses.count))}</span>')
    return f'<span class="end">{end}</span>', body


def run_row(r: dict, ctx: dict, old: bool) -> tuple:
    """One run in the history, and the filter keys it answers to."""
    meta, scs = r["meta"], r["scenarios"]
    n = len(scs)
    tally = {}
    for s in scs:
        tally[s["status"]] = tally.get(s["status"], 0) + 1
    passed = tally.get("PASS", 0)
    small = " · ".join(f"{tally[k]} {k.lower()}" for k in ("FAIL", "FLAKY", "ERROR") if tally.get(k))
    mini = "".join(f'<span class="{c}" style="width:{100 * tally.get(k, 0) / n:.1f}%"></span>'
                   for k, c in (("PASS", "p"), ("FLAKY", "k"), ("FAIL", "f"), ("ERROR", "e"))
                   if tally.get(k)) if n else ""
    cats = sorted({s.get("category", "?") for s in scs})
    ids = r["ids"]
    if any(i.startswith("project-") for i in ids):
        summ = f"project — {n} scenario{'s' if n != 1 else ''}"
    elif r["full"]:
        summ = f"{n} scenarios · {len(cats)} categories"
    else:
        summ = f"{n} scenario{'s' if n != 1 else ''} · " + (", ".join(cats) if len(cats) <= 3 else f"{len(cats)} categories")
    tags, keys = [], ["full" if r["full"] else "partial"]
    if r["full"]:
        tags.append('<span class="tag full">Full suite</span>')
    if ctx["baseline"] is r:
        tags.append('<span class="tag">latest baseline</span>')
    if meta.get("experiment"):
        tags.append(f'<span class="tag exp" title="{esc(meta["experiment"])}">Experiment</span>')
        keys.append("exp")
    rep = max((s.get("repeat") or 1) for s in scs) if scs else 1
    if rep > 1:
        tags.append(f'<span class="tag">×{rep}</span>')
    warns = run_warnings(meta)
    denied = sum(1 for s in scs if denied_count(s))
    if denied:
        warns.append(f"permission denied · {denied}")
    tags += [f'<span class="tag warn">{esc(w)}</span>' for w in warns]
    if warns:
        keys.append("warn")
    if not meta.get("fingerprints"):
        tags.append('<span class="tag">no provenance</span>')
    gone = [i for i in ids if ctx["scen"] and i not in ctx["scen"] and not i.startswith("project-")]
    if gone:
        tags.append(f'<span class="tag" title="{esc(", ".join(gone))}">{len(gone)} no longer defined</span>')
    idline = f'<span class="ids">{esc(", ".join(ids))}</span>' if not r["full"] and n <= 8 else ""
    xp = f'<span class="xp">Experiment: {esc(meta["experiment"])}</span>' if meta.get("experiment") else ""
    bm = (ctx["baseline"] or {}).get("meta", {})
    mdl, jdg = meta.get("model"), meta.get("judge_model")
    cfg = ""
    if meta:
        cfg = (f'<b class="{"diff" if bm and mdl != bm.get("model") else ""}">{esc(mdl or "?")}</b> / '
               f'<b class="{"diff" if bm and jdg != bm.get("judge_model") else ""}">{esc(jdg or "?")}</b>')
        styles = [s for s in (meta.get("effective") or {}).get("output_styles") or [] if s != "default"]
        if styles:
            cfg += f'<br>style <b>{esc(", ".join(styles))}</b>'
    else:
        cfg = '<span class="muted">not recorded</span>'
    cat = meta.get("catalog") or {}
    harn = (meta.get("fingerprints") or {}).get("harness") or {}
    catl = f'<b>{esc(short(cat.get("catalog_commit"), cat.get("catalog_dirty")))}</b>' if cat.get("catalog_commit") else ""
    if harn.get("commit"):
        catl += f' · {esc(short(harn["commit"], harn.get("dirty")))}'
    cls = "run" + (" is-baseline" if ctx["baseline"] is r else "") + (" is-warn" if warns else "")
    li = (f'<li data-k="{" ".join(keys)}"{" class=old" if old else ""}><a class="{cls}" href="{esc(r["name"])}/report.html">'
          f'<span class="t">{esc(r["name"][9:11] + ":" + r["name"][11:13])}</span>'
          f'<span class="res"><span class="frac">{passed}/{n}{f" <small>{small}</small>" if small else ""}</span>'
          f'<span class="mini">{mini}</span></span>'
          f'<span class="what"><span class="line"><span class="sum">{esc(summ)}</span>{"".join(tags)}</span>{xp}{idline}</span>'
          f'<span class="cfg">{cfg}</span><span class="cat">{catl or "<span class=muted>—</span>"}</span>'
          f'<span class="cost">${r["cost"]:.2f}</span></a></li>')
    return li, keys


def home_history(ctx: dict) -> tuple:
    runs = ctx["runs"]
    est = ctx["estimate"]
    if not runs:
        n = sum(1 for s in ctx["scen"].values() if s.category == "routing")
        return "", ('<div class="card empty-card"><p><b>No runs yet.</b></p><p class="muted">Start small: '
                    f'<code>./run.py --category routing</code> ({n} scenarios, {money(n, est)}).</p></div>')
    # Recent days in full, the rest folded: enough to see this week's work
    # without scrolling past a month of history to reach the filters' answer.
    shown, cut_day = 0, None
    for r in runs:
        if shown >= 20 and r["name"][:8] != runs[shown - 1]["name"][:8]:
            cut_day = r["name"][:8]
            break
        shown += 1
    items, counts, day = [], {"all": 0, "full": 0, "partial": 0, "exp": 0, "warn": 0}, None
    for i, r in enumerate(runs):
        old = i >= shown
        if r["name"][:8] != day:
            day = r["name"][:8]
            same = [x for x in runs if x["name"][:8] == day]
            items.append(f'<li class="day{" old" if old else ""}"><b>{esc(nice_time(day + "-000000").split(",")[0])}</b>'
                         f'<span>{len(same)} run{"s" if len(same) != 1 else ""} · ${sum(x["cost"] for x in same):.2f}</span></li>')
        li, keys = run_row(r, ctx, old)
        items.append(li)
        counts["all"] += 1
        for k in keys:
            counts[k] += 1
    older = runs[shown:]
    fold = ""
    if older:
        withp = sum(1 for r in older if r["meta"].get("fingerprints"))
        fold = (f'<div class="older" id="older"><span>{len(older)} older runs · '
                f'{esc(nice_time(older[0]["name"]).split(",")[0])} → {esc(nice_time(older[-1]["name"]).split(",")[0])} · '
                f'${sum(r["cost"] for r in older):.2f} · {"none" if not withp else withp} with provenance</span>'
                f'<button class="btn" type="button" id="show-old">Show older runs</button></div>')
    chips = "".join(f'<button class="chip" type="button" data-f="{k}" aria-pressed="{str(k == "all").lower()}">'
                    f'{label}<span class="n">{counts[k]}</span></button>'
                    for k, label in (("all", "All"), ("full", "Full suites"), ("partial", "Partial"),
                                     ("exp", "Experiments"), ("warn", "With warnings")))
    total = sum(r["cost"] for r in runs)
    bm = (ctx["baseline"] or {}).get("meta", {})
    body = (f'<div class="filters" role="group" aria-label="Filter runs">{chips}</div><div class="card">'
            '<div class="runs-head" aria-hidden="true"><span>Time</span><span>Result</span><span>What ran</span>'
            '<span>Agent / judge</span><span>Catalog · harness</span><span>Cost</span></div>'
            f'<ul class="runs" id="runs">{"".join(items)}</ul>'
            '<p class="empty" id="runs-empty">No runs match this filter.</p>'
            f'{fold}</div><p class="muted" style="font-size:var(--text-xs);margin:var(--space-3) 0 0;max-width:80ch">'
            '<code>*</code> after a commit means that tree was dirty. '
            + (f'Bold model names differ from the latest baseline\'s (<span class="mono">'
               f'{esc(bm.get("model"))} / {esc(bm.get("judge_model"))}</span>). ' if bm else "")
            + '<b>Experiment</b> = declared with <code>--experiment</code> when the run was created; '
            'hover the tag, or open the run, for what it tests. A <b>⚠</b> tag marks a run that was '
            'not a neutral default session, or where the host refused a command.</p>')
    return f'<span class="end">{len(runs)} runs · ${total:.2f} total</span>', body


HOME_JS = """
(function(){
  const list=document.getElementById('runs'); if(!list) return;
  const chips=[...document.querySelectorAll('.chip')], empty=document.getElementById('runs-empty');
  const older=document.getElementById('older'), more=document.getElementById('show-old');
  let f='all';
  // One filter at a time; a filter searches every run, folded ones included,
  // and day headers hide when nothing under them is left.
  const apply=()=>{
    const all = f==='all', open = list.classList.contains('show-old');
    let shown=0, day=null, dayCount=0;
    const flush=()=>{ if(day) day.style.display=dayCount?'':'none'; };
    [...list.children].forEach(li=>{
      const hidden = li.classList.contains('old') && all && !open;
      if(li.classList.contains('day')){ flush(); day=li; dayCount=0; li.style.display=hidden?'none':''; return; }
      const ok = !hidden && (all || (li.dataset.k||'').split(' ').includes(f));
      li.style.display=ok?'block':'none'; if(ok){shown++;dayCount++;}
    });
    flush(); empty.style.display=shown?'none':'block';
    if(older) older.style.display = all && !open ? '' : 'none';
  };
  chips.forEach(c=>c.onclick=()=>{ f=c.dataset.f; chips.forEach(x=>x.setAttribute('aria-pressed',x===c)); apply(); });
  if(more) more.onclick=()=>{ list.classList.add('show-old'); apply(); };
  apply();
})();
"""


def build_index(runs_dir: Path, ctx: dict = None) -> str:
    """The home page: what state the catalog is in, and how much of that
    evidence still describes today's install — before what ran when.

    It also regenerates every run's own report, so the index is never a set of
    links to files that don't exist yet."""
    ctx = ctx or context(runs_dir)
    for r in ctx["runs"]:
        (r["dir"] / "report.html").write_text(build_run(load_run(r["dir"]), ctx))
    inst = ctx["installed"]
    subject = git(inst.get("catalog_path", ""), "log", "-1", "--format=%s",
                  inst.get("catalog_commit", "")) if inst.get("catalog_commit") else ""
    facts = [f'<span>Generated <b>{esc(datetime.now().strftime("%-d %b %Y, %H:%M"))}</b></span>']
    if inst.get("catalog_commit"):
        facts.append(f'<span>Installed catalog <b class="mono">{esc(short(inst["catalog_commit"], inst.get("catalog_dirty")))}</b> '
                     f'{esc(subject)}</span>')
    if ctx["model"]:
        facts.append(f'<span>Compared on model <b class="mono">{esc(ctx["model"])}</b></span>')
    if ctx["suite"]:
        facts.append(f'<span>Default suite <b>{len(ctx["suite"])}</b> scenarios'
                     + (f' <span class="muted">(+{ctx["manual"]} manual)</span>' if ctx["manual"] else "") + '</span>')
    b_end, b_body = home_baseline(ctx)
    h_end, h_body = home_hosts(SMOKE_DIR if runs_dir == RUNS_DIR else runs_dir.parent / "runs-smoke")
    r_end, r_body = home_history(ctx)
    body = (top_bar("#", "evidence") + '<main class="wrap"><div class="head"><h1>Catalog health</h1>'
            '<p>What state is the catalog in, and how much of that evidence can you trust? Each scenario '
            'counts once, by its latest verdict, checked against what is installed now.</p>'
            f'<div class="facts">{"".join(facts)}</div></div>'
            '<section id="evidence" aria-labelledby="ev-h"><div class="sec-h"><h2 id="ev-h">Evidence freshness</h2>'
            '<span class="q">Does each latest verdict still describe today\'s install?</span>'
            f'<span class="end">from <code>run.py --applicability --model {esc(ctx["model"])}</code> · no model calls</span></div>'
            f'{home_freshness(ctx)}</section>'
            '<section id="baseline" aria-labelledby="bl-h"><div class="sec-h"><h2 id="bl-h">Latest full baseline</h2>'
            f'<span class="q">The last time every scenario ran together, in a neutral session.</span>{b_end}</div>'
            f'{b_body}</section>'
            '<section id="hosts" aria-labelledby="h-h"><div class="sec-h"><h2 id="h-h">Hosts</h2>'
            f'<span class="q">Does the catalog install and behave in each tool? Latest smoke result per host.</span>{h_end}</div>'
            f'{h_body}</section>'
            '<section id="history" aria-labelledby="hi-h"><div class="sec-h"><h2 id="hi-h">Runs</h2>'
            f'<span class="q">Every recorded run, newest first.</span>{r_end}</div>{r_body}</section>'
            '</main><div class="wrap"><footer>Generated by <code>viz.py --index</code> from runs/, runs-smoke/ '
            'and the scenarios in scenarios/. Rendering calls no model.</footer></div>')
    return page("Catalog health", HOME_CSS, body, HOME_JS)


# --------------------------------------------------------------------------- #
# HTML — one run (runs/<ts>/report.html)
# --------------------------------------------------------------------------- #
RUN_CSS = """
.crumb{font-size:var(--text-xs);color:var(--text-muted);padding-top:var(--space-5)}
.run-title{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--space-2) var(--space-3);margin:var(--space-2) 0 var(--space-4)}
.run-title h1{font:var(--weight-strong) var(--text-xl)/1.3 var(--font-mono);margin:0;letter-spacing:-.01em}
.run-title .when{color:var(--text-muted)}
.prov-card{margin-bottom:var(--space-6)}
.cmp{display:flex;flex-wrap:wrap;gap:var(--space-2) var(--space-5);padding:var(--space-4) var(--space-5);
  border-bottom:1px solid var(--border);list-style:none;margin:0}
.cmp li{display:flex;gap:var(--space-2);align-items:baseline;font-size:var(--text-sm)}
.cmp .ok{color:var(--pass);font-weight:var(--weight-strong)}
.cmp .wn{color:var(--warn);font-weight:var(--weight-strong)}
.cmp .no{color:var(--fail);font-weight:var(--weight-strong)}
.cmp-verdict{padding:var(--space-4) var(--space-5) 0;margin:0;font-size:var(--text-md);font-weight:var(--weight-strong)}
.cmp-verdict span{font-weight:var(--weight-regular);color:var(--text-muted);font-size:var(--text-sm)}
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--space-4) var(--space-5);
  padding:var(--space-4) var(--space-5);margin:0}
.vs{padding:var(--space-3) var(--space-5);border-top:1px solid var(--border);background:var(--surface-sunk);
  font-size:var(--text-xs);color:var(--text-muted);border-radius:0 0 var(--radius-md) var(--radius-md)}
.vs b{color:var(--text)}
.vs details summary{cursor:pointer;color:var(--accent);min-height:24px;display:inline-flex;align-items:center}
.hashes{margin:var(--space-2) 0 0;columns:3 180px;font:11px/1.7 var(--font-mono);list-style:none;padding:0}
.hashes .hit{color:var(--text);font-weight:var(--weight-strong)}
.banner{display:flex;gap:var(--space-3);align-items:flex-start;padding:var(--space-4) var(--space-5);
  border-bottom:1px solid var(--warn-line);color:var(--text);
  background:repeating-linear-gradient(135deg,var(--warn-soft) 0 8px,transparent 8px 16px);
  border-radius:var(--radius-md) var(--radius-md) 0 0}
.banner .ic{color:var(--warn);font-size:var(--text-lg);line-height:1}
.banner b{display:block;font-size:var(--text-md);color:var(--warn)}
.banner.neutral{background:var(--surface-sunk);border-bottom-color:var(--border)}
.banner.neutral .ic,.banner.neutral b{color:var(--text-muted)}
.banner.exp{background:var(--surface-sunk);border-bottom:1px dashed var(--border-strong)}
.banner.exp .ic,.banner.exp b{color:var(--text)}
.sumline{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-2) var(--space-4);margin:0 0 var(--space-4)}
.sumline .score{font-size:var(--text-xl)}
.sumline .meta{font-size:var(--text-xs);color:var(--text-muted)}
.fbar{display:flex;flex-wrap:wrap;gap:var(--space-3) var(--space-5);align-items:center;padding:var(--space-3) 0;
  border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin:0 0 var(--space-4);
  position:sticky;top:0;background:var(--bg);z-index:2}
.fgroup{display:flex;flex-wrap:wrap;gap:var(--space-2);align-items:center}
.fgroup > span{font-size:var(--text-xs);color:var(--text-muted);margin-right:var(--space-1)}
.fixed{font-size:var(--text-xs)}
.scns{display:grid;gap:var(--space-3)}
.scn{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md);scroll-margin-top:72px}
.scn > summary{list-style:none;cursor:pointer;display:grid;
  grid-template-columns:110px minmax(0,1fr) auto auto;gap:var(--space-2) var(--space-4);align-items:center;
  padding:var(--space-3) var(--space-4);min-height:56px}
.scn > summary::-webkit-details-marker{display:none}
.scn[open] > summary{border-bottom:1px solid var(--border)}
.scn .sid{font:var(--weight-strong) var(--text-sm)/1.4 var(--font-mono);overflow-wrap:anywhere}
.scn .smeta{display:block;font:var(--text-xs)/1.5 var(--font-sans);color:var(--text-muted);font-weight:var(--weight-regular)}
.scn .flags{display:flex;flex-wrap:wrap;gap:var(--space-1);justify-content:flex-end}
.scn .c{font:var(--text-xs) var(--font-mono);color:var(--text-muted);text-align:right;min-width:56px}
.scn .c::after{content:" ▸"} .scn[open] .c::after{content:" ▾"}
.dots{display:inline-flex;gap:3px;margin-left:var(--space-1)}
.dots i{width:7px;height:7px;border-radius:50%;display:inline-block}
.dots i.PASS{background:var(--pass)} .dots i.FAIL{background:var(--fail)} .dots i.ERROR{background:var(--error)}
.body{padding:var(--space-4) var(--space-5) var(--space-5)}
.h3{font-size:var(--text-xs);font-weight:var(--weight-strong);letter-spacing:.06em;text-transform:uppercase;
  color:var(--text-muted);margin:var(--space-5) 0 var(--space-3)}
.h3:first-child{margin-top:0}
.alert{display:grid;grid-template-columns:auto minmax(0,1fr);gap:var(--space-1) var(--space-3);
  padding:var(--space-3) var(--space-4);border-radius:var(--radius-sm);margin:0 0 var(--space-3);
  border:1px solid var(--warn-line);border-left-width:4px;background:var(--warn-soft);font-size:var(--text-sm)}
.alert .ic{color:var(--warn);font-weight:var(--weight-strong)}
.alert b{color:var(--text)}
.alert p{margin:var(--space-1) 0 0;color:var(--text-muted);font-size:var(--text-xs)}
.alert.hist{border-color:var(--border-strong);background:var(--surface-sunk)}
.alert.hist .ic{color:var(--text-muted)}
.spec{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--space-5)}
.prompt{border:1px dashed var(--border-strong);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4);
  white-space:pre-wrap;font-size:var(--text-sm);overflow-wrap:anywhere}
.prompt-who{font-size:var(--text-xs);color:var(--text-muted);margin:0 0 var(--space-1)}
.checks{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-2)}
.check{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:var(--space-1) var(--space-3);align-items:baseline;
  padding:var(--space-2) var(--space-3);border:1px solid var(--border);border-radius:var(--radius-sm)}
.check .k{font:var(--weight-strong) var(--text-xs) var(--font-mono)}
.check .v{font:11px/1.5 var(--font-mono);color:var(--text-muted);overflow-wrap:anywhere}
.check .why{grid-column:2/-1;font-size:var(--text-xs);color:var(--text-muted);overflow-wrap:anywhere}
.check .why em{font-style:normal;color:var(--warn);font-weight:var(--weight-strong)}
.kind{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:1px var(--space-1)}
.crit{font-size:var(--text-sm);line-height:1.55;margin:var(--space-2) 0 0;padding:var(--space-3) var(--space-4);
  background:var(--surface-sunk);border-radius:var(--radius-sm);white-space:pre-wrap}
.crit-note{font-size:var(--text-xs);color:var(--warn);margin:var(--space-2) 0 0;font-weight:var(--weight-strong)}
.cnote{font-size:var(--text-xs);color:var(--text-muted);margin:var(--space-2) 0 0}
.samples{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:var(--space-3)}
.sample{border:1px solid var(--border);border-top:3px solid var(--border-strong);border-radius:var(--radius-sm);
  display:flex;flex-direction:column;min-width:0}
.sample.PASS{border-top-color:var(--pass)} .sample.FAIL{border-top-color:var(--fail)} .sample.ERROR{border-top-color:var(--error)}
.sample .sh{display:flex;flex-wrap:wrap;gap:var(--space-2);align-items:center;padding:var(--space-2) var(--space-3);
  font-size:var(--text-xs);color:var(--text-muted)}
.sample .sh b{color:var(--text)}
.sample .rep{font-size:var(--text-xs);color:var(--accent)}
.sample dl{margin:0;padding:0 var(--space-3) var(--space-2);display:grid;grid-template-columns:auto minmax(0,1fr);
  gap:2px var(--space-2);font-size:var(--text-xs)}
.sample dt{color:var(--text-muted)} .sample dd{margin:0;font-family:var(--font-mono);font-size:11px;overflow-wrap:anywhere}
.sample dd.deny{color:var(--warn);font-family:var(--font-sans);font-weight:var(--weight-strong)}
.sample dd.bad{color:var(--fail);font-family:var(--font-sans)}
.judge{margin:0;padding:var(--space-2) var(--space-3);font-size:var(--text-xs);line-height:1.5;
  border-top:1px solid var(--border);background:var(--surface-sunk)}
.judge b{display:block;font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);margin-bottom:2px}
.reply{position:relative;margin:0;padding:var(--space-3);font-size:var(--text-xs);line-height:1.55;white-space:pre-wrap;
  overflow-wrap:anywhere;max-height:14em;overflow:hidden;border-top:1px solid var(--border);flex:1}
.reply::after{content:"";position:absolute;inset:auto 0 0 0;height:3em;background:linear-gradient(transparent,var(--surface))}
.reply.open{max-height:none} .reply.open::after{display:none}
.more-btn{border:0;background:transparent;color:var(--accent);font-size:var(--text-xs);cursor:pointer;
  padding:var(--space-2) var(--space-3);text-align:left;min-height:32px}
.ctl{display:flex;gap:var(--space-2);align-items:center;flex-wrap:wrap;margin:0 0 var(--space-3)}
.ctl .note{font-size:var(--text-xs);color:var(--text-muted)}
.tl{border-left:2px solid var(--border);padding-left:var(--space-4);margin-left:var(--space-1)}
.step{transition:opacity .2s} .tl.playing .step:not(.on){opacity:0}
.who{font:var(--weight-strong) var(--text-xs)/1.4 var(--font-mono);margin:var(--space-3) 0 var(--space-1);
  display:flex;gap:var(--space-2);align-items:center;color:var(--text-muted)}
.who .ans{font:var(--weight-strong) 10px/1 var(--font-sans);letter-spacing:.06em;text-transform:uppercase;color:var(--pass);
  border:1px solid currentColor;border-radius:var(--radius-pill);padding:2px var(--space-2)}
.bub{border:1px solid var(--border);border-radius:var(--radius-sm) var(--radius-md) var(--radius-md) var(--radius-md);
  padding:var(--space-3) var(--space-4);white-space:pre-wrap;overflow-wrap:anywhere;font-size:var(--text-sm);background:var(--surface)}
.bub.me{border-style:dashed;background:transparent}
.act{display:grid;grid-template-columns:18px auto minmax(0,1fr) auto;gap:var(--space-2);align-items:baseline;
  font:var(--text-xs)/1.6 var(--font-mono);color:var(--text-muted);padding:2px 0}
.act .i{text-align:center;color:var(--accent)} .act b{color:var(--text);font-weight:var(--weight-strong)}
.act .arg{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}
.act .arg.open{white-space:pre-wrap;overflow-wrap:anywhere}
.act .t{font-size:11px}
.act.res .i{color:var(--text-muted)}
.act.err .i,.act.err b{color:var(--fail)}
.act.denied{background:var(--warn-soft);border-radius:var(--radius-sm);padding:2px var(--space-2);margin:2px 0 2px calc(-1 * var(--space-2))}
.act.denied .i,.act.denied b{color:var(--warn)}
.think{height:3px;border-radius:2px;background:var(--border-strong);margin:var(--space-1) 0 var(--space-1) 26px}
.join{margin:var(--space-4) 0 var(--space-1);font:var(--text-xs) var(--font-mono);color:var(--text-muted);
  border-top:1px dashed var(--border);padding-top:var(--space-2)}
.join b{color:var(--text)}
.sub-lane{margin-left:var(--space-5);border-left:2px solid var(--border);padding-left:var(--space-3)}
.final{margin-top:var(--space-3)}
.final-reply{border-left:2px solid var(--border);padding-left:var(--space-4);white-space:pre-wrap;font-size:var(--text-sm);overflow-wrap:anywhere}
@media (max-width:900px){
  .spec{grid-template-columns:1fr}
  .samples{grid-template-columns:1fr}
  .scn > summary{grid-template-columns:auto minmax(0,1fr) auto;grid-template-areas:"st id c" "fl fl fl"}
  .scn > summary .st{grid-area:st} .scn > summary .sidw{grid-area:id} .scn > summary .flags{grid-area:fl;justify-content:flex-start}
  .scn > summary .c{grid-area:c}
}
@media (max-width:640px){
  .cmp,.fields,.vs,.banner,.cmp-verdict{padding-left:var(--space-4);padding-right:var(--space-4)}
  .body{padding:var(--space-3) var(--space-4) var(--space-4)}
  .fbar{position:static}
  .act{grid-template-columns:18px auto minmax(0,1fr)} .act .t{display:none}
  .sub-lane{margin-left:var(--space-2)}
}
@media (prefers-reduced-motion:reduce){.tl.playing .step:not(.on){opacity:1}}
"""

RUN_JS = """
const D = DATA;
const ORDER = {FAIL:0, ERROR:1, FLAKY:2, PASS:3};
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const secs = ms => (ms/1000).toFixed(1)+"s";
const tally = arr => arr.reduce((m,x)=>(m[x]=(m[x]||0)+1,m),{});
const denied = sc => sc.trials.filter(t => t.deny && t.deny.length).length;
const money = n => "$" + (n||0).toFixed(3);

function flags(sc){
  let h = "";
  const d = denied(sc);
  if(d) h += `<span class="tag warn">Permission denied ${d}/${sc.n}</span>`;
  if(sc.spec.changed) h += `<span class="tag">Definition changed since</span>`;
  if(!sc.spec.defined) h += `<span class="tag">No longer defined</span>`;
  if(sc.subs) h += `<span class="tag plain">⑂ ${sc.subs}</span>`;
  const sk = [...new Set(sc.trials.flatMap(t=>Array.isArray(t.skills)?t.skills:[]))];
  if(sk.length) h += `<span class="tag plain">◈ ${esc(sk.join(", "))}</span>`;
  return h;
}

function alerts(sc){
  const sp = sc.spec; let h = "";
  const d = sc.trials.filter(t=>t.deny&&t.deny.length);
  if(d.length){
    const msg = [...new Set(d.flatMap(t=>t.deny))];
    h += `<div class="alert" role="note"><span class="ic">⚠</span><div>
      <b>The host refused a command in ${d.length} of ${sc.n} sample${sc.n>1?"s":""} — the verdict may hide a tool the agent needed.</b>
      <p>${msg.map(m=>"“"+esc(m)+"”").join(" · ")}. The denied step is marked in the conversation below.</p></div></div>`;
  }
  if(sp.changed){
    const L = sp.changed.latest;
    h += `<div class="alert hist" role="note"><span class="ic">○</span><div>
      <b>This verdict is historic: the scenario's definition changed after this run.</b>
      <p>Fingerprint ${esc(sp.changed.then)} then, ${esc(sp.changed.now)} now. ${L ? `Latest verdict:
      <span class="st ${esc(L.st)}">${esc(L.n)}</span> in <a href="${esc(D.up)}${esc(L.run)}/report.html#${esc(sc.id)}">${esc(L.run)}</a>
      (${esc(L.at)}) · <span class="tr ${esc(L.trust)}"><i></i>${esc(L.trust)}</span>` : "No verdict for today's definition yet."}</p></div></div>`;
  }
  if(!sp.defined){
    h += `<div class="alert hist" role="note"><span class="ic">○</span><div>
      <b>This scenario is no longer defined in scenarios/*.yaml.</b>
      <p>The verdict below stands as history; nothing today measures the same thing.</p></div></div>`;
  }
  return h;
}

function checks(sc){
  const sp = sc.spec;
  let h = `<ul class="checks">`;
  sp.checks.forEach(c=>{
    h += `<li class="check"><span class="st ${c.st}">${c.st==="NA"?"—":c.held}</span>
      <span><span class="k">${esc(c.k)}</span> <span class="v">${esc(c.v)}</span></span>
      <span class="kind">deterministic</span>
      <span class="why">${c.note?`<em>${esc(c.note)}</em> `:""}${esc(c.why)}</span></li>`;
  });
  if(sp.judge){
    const v = sc.trials.map(t=>t.jv);
    const jPass = v.filter(x=>x===true).length;
    const js = jPass===sc.n ? "PASS" : jPass===0 ? (v.every(x=>x===null||x===undefined)?"ERROR":"FAIL") : "FLAKY";
    h += `<li class="check"><span class="st ${js}">${jPass}/${sc.n}</span>
      <span><span class="k">judge</span> <span class="v">${esc(D.judge)} reads the reply against the criterion</span></span>
      <span class="kind">model</span>
      <span class="why">Its reasoning for each sample is under Samples.</span></li>`;
  }
  if(!sp.checks.length && !sp.judge) h += `<li class="check"><span class="st NA">—</span><span class="v">No assertions ${sp.src==="none"?"known":"declared"}.</span></li>`;
  h += `</ul>`;
  if(sp.checks.some(c=>c.derived))
    h += `<p class="cnote">Per-check results derived from the failures this trace recorded — it predates per-check results.</p>`;
  return h;
}

function samples(sc){
  let h = `<div class="samples" style="--n:${Math.min(sc.n,3)}">`;
  sc.trials.forEach((t,i)=>{
    // A list, null (recorded: none) or "missing" (the trace predates the field).
    const tools = Array.isArray(t.tools) ? Object.entries(tally(t.tools)).map(([k,v])=>v>1?`${k} ×${v}`:k).join(", ") : (t.tools==="missing" ? "not recorded" : "none");
    const skills = Array.isArray(t.skills) ? t.skills.join(", ") : (t.skills==="missing" ? "not recorded" : "none loaded");
    const id = `r-${sc.id}-${i}`;
    h += `<article class="sample ${t.st}">
      <div class="sh"><span class="st ${t.st}">${t.st}</span><b>Sample ${i+1}</b>
        <span>${money(t.cost)}${t.ms?` · ${secs(t.ms)}`:""}</span>${i===sc.lead && sc.steps.length?'<span class="rep">▶ replayed below</span>':''}</div>
      <dl><dt>tools</dt><dd>${esc(tools)}</dd>
          <dt>skills</dt><dd>${esc(skills)}</dd>
          ${t.model?`<dt>model</dt><dd>${esc(t.model)}${t.style&&t.style!=="default"?` · style ${esc(t.style)}`:""}</dd>`:""}
          ${t.subs?`<dt>subagents</dt><dd>${esc(t.subs)}</dd>`:""}
          ${t.score?`<dt>suite</dt><dd>${esc(t.score)}</dd>`:""}
          ${t.deny?`<dt>denied</dt><dd class="deny">⚠ ${esc(t.deny.join(" · "))}</dd>`:""}
          ${t.fails&&t.fails.length?`<dt>failed</dt><dd class="bad">${esc(t.fails.join(" · "))}</dd>`:""}
          ${t.error?`<dt>error</dt><dd class="bad">${esc(t.error)}</dd>`:""}</dl>
      ${t.why?`<p class="judge"><b>Judge</b>${esc(t.why)}</p>`:""}
      <div class="reply" id="${esc(id)}">${esc(t.reply || "(no reply)")}</div>
      <button class="more-btn" type="button" data-for="${esc(id)}">Show full reply</button>
    </article>`;
  });
  return h + `</div>`;
}

function timeline(sc){
  if(!sc.steps.length) return `<p class="cnote">This trace kept no event stream for this scenario.</p>`;
  const t = sc.trials[sc.lead] || {};
  const denies = new Set((t.deny||[]).map(x=>x.trim()));
  const lastText = [...sc.steps].reverse().find(s=>s.kind==="text" && s.lane==="main");
  const seen = new Set(["main"]);
  let h = `<div class="ctl"><button class="btn" type="button" data-play>▶ Play</button>
    <button class="btn" type="button" data-all>Show all</button>
    <span class="note">${sc.n>1?`Sample ${sc.lead+1} of ${sc.n} — the trace keeps one conversation per scenario · `:""}<span data-pos></span></span></div>
    <div class="tl">
    <div class="step on"><div class="who">you</div><div class="bub me">${esc((sc.prompt||"").trim())}</div></div>`;
  sc.steps.forEach(s=>{
    const sub = s.lane!=="main", name = sub ? s.laneName : sc.agent;
    const wrap = x => sub ? `<div class="sub-lane">${x}</div>` : x;
    const tm = s.ms>1500 ? secs(s.ms) : (s.ms ? s.ms+"ms" : "");
    let pre = "";
    if(!seen.has(s.lane)){
      seen.add(s.lane);
      const task = sc.delegated_to?.[s.lane]?.task || "";
      pre = `<div class="step join">⑂ <b>${esc(name)}</b> joined${task?" — "+esc(task):""}</div>`;
    }
    if(s.kind==="think"){ h += pre + wrap(`<div class="step think" style="width:${Math.min(180,(s.weight||0)/4)}px" title="thinking · ${esc(s.detail)}"></div>`); return; }
    if(s.kind==="text"){
      const fin = s===lastText;
      h += pre + wrap(`<div class="step"><div class="who">${esc(name)}${fin?'<span class="ans">answer</span>':''}<span>${tm}</span></div>
            <div class="bub">${esc(s.detail)}</div></div>`); return;
    }
    if(s.kind==="tool"){
      h += pre + wrap(`<div class="step act"><span class="i">${D.icons[s.name]||"▸"}</span><b>${esc(s.name)}</b><span class="arg" title="click to expand">${esc(s.detail)}</span><span class="t">${tm}</span></div>`); return;
    }
    const isDeny = s.error && denies.has((s.detail||"").trim());
    const cls = isDeny ? "denied" : s.error ? "err" : "res";
    const lbl = isDeny ? "denied by host" : s.error ? "error" : "result";
    h += pre + wrap(`<div class="step act ${cls}"><span class="i">${isDeny?"⚠":"↩"}</span><b>${lbl}</b><span class="arg" title="click to expand">${esc(s.detail)}</span><span class="t">${tm}</span></div>`);
  });
  h += `</div>`;
  // Only when it is NOT already the last bubble — otherwise it is the same
  // text printed twice, which reads as if the agent repeated itself.
  if(sc.reply && sc.reply.trim() !== (lastText?.detail||"").trim())
    h += `<div class="final"><h3 class="h3">Final reply</h3><div class="final-reply">${esc(sc.reply)}</div></div>`;
  return h;
}

function body(sc){
  const sp = sc.spec;
  const critHead = sp.src==="run" ? "Criterion — as judged in this run" : sp.src==="today" && (sp.changed||sp.unknown) ? "Criterion — today's version" : "Criterion";
  let crit = sp.judge ? `<div class="crit">${esc(sp.judge)}</div>` : `<p class="cnote">No judge criterion: the verdict rests on the deterministic checks.</p>`;
  if(sp.changed && sp.src==="today") crit += `<p class="crit-note">This run was judged against an earlier definition that the trace did not keep.</p>`;
  else if(sp.unknown) crit += `<p class="crit-note">This run predates fingerprints: today's definition is shown, and it may not be the one this run was judged against.</p>`;
  return `${alerts(sc)}
    <div class="spec">
      <div><h3 class="h3">The task</h3>
        <p class="prompt-who">Prompt${sp.workspace?`, in a fresh copy of <code>${esc(sp.workspace)}</code>`:""}</p>
        <div class="prompt">${esc((sc.prompt||"").trim())}</div>
        <h3 class="h3">${critHead}</h3>${crit}
      </div>
      <div><h3 class="h3">Checks</h3>${checks(sc)}</div>
    </div>
    <h3 class="h3">${sc.n>1?`Samples — ${sc.n}, side by side`:"Sample"}</h3>
    ${samples(sc)}
    <h3 class="h3">Conversation</h3>
    <div data-tl>${timeline(sc)}</div>`;
}

function render(){
  const list = [...D.scenarios].sort((a,b)=>(ORDER[a.status]??9)-(ORDER[b.status]??9) || a.id.localeCompare(b.id));
  document.getElementById("scns").innerHTML = list.map(sc=>{
    const dots = sc.n>1 ? sc.trials.map(t=>`<i class="${esc(t.st)}" title="sample: ${esc(t.st)}"></i>`).join("") : "";
    return `<details class="scn" id="${esc(sc.id)}" data-status="${esc(sc.status)}" data-agent="${esc(sc.agent)}" data-cat="${esc(sc.cat)}"
        data-deny="${denied(sc)?1:0}" data-changed="${sc.spec.changed?1:0}">
      <summary>
        <span class="st ${esc(sc.status)}">${esc(sc.status)}${sc.n>1?` ${sc.passes}/${sc.n}`:""}</span>
        <span class="sidw"><span class="sid">${esc(sc.id)}</span>
          <span class="smeta">${esc(sc.agent)} · ${esc(sc.cat)} <span class="dots" aria-hidden="true">${dots}</span></span></span>
        <span class="flags">${flags(sc)}</span>
        <span class="c">$${(sc.cost||0).toFixed(2)}</span>
      </summary>
      <div class="body"></div></details>`;
  }).join("");
  // Bodies are built when a row opens: a full suite is sixty-odd conversations
  // and nobody reads them all on one visit.
  document.querySelectorAll(".scn").forEach(el=>{
    const sc = D.scenarios.find(s=>s.id===el.id);
    const fill = ()=>{ if(el.dataset.done) return; el.dataset.done=1;
      el.querySelector(".body").innerHTML = body(sc); wire(el); };
    el.addEventListener("toggle", ()=>{ if(el.open) fill(); });
    if(sc.status!=="PASS" || denied(sc) || location.hash.slice(1)===sc.id){ el.open = true; fill(); }
  });
  const target = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if(target) target.scrollIntoView();
}

const F = {status:"all", agent:"all", cat:"all", flag:"none"};
function chipGroup(id, key, opts){
  const g = document.getElementById(id); if(!g) return;
  opts.forEach(([val,label,n])=>{
    const b = document.createElement("button");
    b.type="button"; b.className="chip"; b.dataset.v=val;
    b.setAttribute("aria-pressed", String(F[key]===val));
    b.innerHTML = `${esc(label)}${n!=null?`<span class="n">${n}</span>`:""}`;
    b.onclick = ()=>{ F[key] = (F[key]===val && key==="flag") ? "none" : val;
      g.querySelectorAll(".chip").forEach(c=>c.setAttribute("aria-pressed", String(c.dataset.v===F[key]))); apply(); };
    g.appendChild(b);
  });
}
function apply(){
  let shown=0;
  document.querySelectorAll(".scn").forEach(el=>{
    const ok = (F.status==="all"||el.dataset.status===F.status)
            && (F.agent==="all"||el.dataset.agent===F.agent)
            && (F.cat==="all"||el.dataset.cat===F.cat)
            && (F.flag==="none"||el.dataset[F.flag]==="1");
    el.style.display = ok?"":"none"; if(ok) shown++;
  });
  document.getElementById("scn-empty").style.display = shown?"none":"block";
}

let timer=null;
function wire(root){
  root.querySelectorAll(".more-btn").forEach(b=>b.onclick=()=>{
    const r=document.getElementById(b.dataset.for); const o=r.classList.toggle("open");
    b.textContent=o?"Collapse reply":"Show full reply"; });
  root.querySelectorAll(".act .arg").forEach(a=>a.onclick=()=>a.classList.toggle("open"));
  root.querySelectorAll("[data-tl]").forEach(box=>{
    const tl=box.querySelector(".tl"); if(!tl) return;
    const steps=[...tl.querySelectorAll(".step")], pos=box.querySelector("[data-pos]");
    const all=()=>{clearInterval(timer);tl.classList.remove("playing");steps.forEach(s=>s.classList.add("on"));pos.textContent=`${steps.length} steps`;};
    box.querySelector("[data-all]").onclick=all;
    box.querySelector("[data-play]").onclick=()=>{
      if(matchMedia("(prefers-reduced-motion: reduce)").matches){all();return;}
      clearInterval(timer); tl.classList.add("playing"); steps.forEach((s,i)=>s.classList.toggle("on",i===0));
      let i=1; timer=setInterval(()=>{ if(i>=steps.length){clearInterval(timer);tl.classList.remove("playing");return;}
        steps[i].classList.add("on"); steps[i].scrollIntoView({block:"nearest",behavior:"smooth"});
        pos.textContent=`${i+1}/${steps.length}`; i++; },300);
    };
    all();
  });
}

render();
const st = tally(D.scenarios.map(s=>s.status)), ag = tally(D.scenarios.map(s=>s.agent)), ct = tally(D.scenarios.map(s=>s.cat));
chipGroup("f-status","status",[["all","All",D.scenarios.length], ...["FAIL","FLAKY","ERROR","PASS"].filter(k=>st[k]).map(k=>[k,k,st[k]])]);
chipGroup("f-agent","agent",[["all","All",null], ...Object.entries(ag).sort().map(([k,v])=>[k,k,v])]);
chipGroup("f-cat","cat",[["all","All",null], ...Object.entries(ct).sort().map(([k,v])=>[k,k,v])]);
const nd = D.scenarios.filter(s=>denied(s)).length, nc = D.scenarios.filter(s=>s.spec.changed).length;
chipGroup("f-flag","flag",[["deny","Permission denied",nd],["changed","Definition changed",nc]]);
"""


def scenario_data(sc: dict, meta: dict, ctx: dict) -> dict:
    """One scenario, shaped for the page's script: every sample, the lead's
    conversation, and what it was measured against."""
    ts = trials_of(sc)
    trials = []
    for t in ts:
        j = t.get("judge") or {}
        score = t.get("score") or {}
        subs = t.get("delegated_to") or {}
        trials.append({
            "st": t.get("status"), "cost": t.get("cost_usd") or 0, "ms": t.get("duration_ms") or 0,
            "ac": t.get("agent_cost_usd"), "jc": t.get("judge_cost_usd"),
            "model": t.get("model"), "style": t.get("output_style"),
            "deny": t.get("permission_denials"),
            # Absent key = the trace predates the field ("missing"); present
            # and null = recorded, and there were none.
            "tools": t["tools_used"] if "tools_used" in t else "missing",
            "skills": t["skills_loaded"] if "skills_loaded" in t else "missing",
            "why": j.get("why") or "", "jv": j.get("verdict") if j else None,
            "reply": t.get("reply") or "", "error": t.get("error") or "",
            "fails": t.get("failures") or [],
            "score": (f'{score.get("passed", "?")}/{score.get("total", "?")} passed'
                      if score and "total" in score else score.get("error", "") if score else ""),
            "subs": ", ".join(sorted({v.get("agent", "?") for v in subs.values()})) if subs else "",
        })
    return {"id": sc["id"], "cat": sc.get("category", "?"), "agent": sc.get("agent", "?"),
            "status": sc.get("status"), "passes": sc.get("passes", 1 if sc.get("status") == "PASS" else 0),
            "n": len(ts), "cost": sc.get("cost_usd") or 0, "prompt": sc.get("prompt", ""),
            "lead": lead_index(sc), "trials": trials, "steps": sc.get("steps", []),
            "reply": sc.get("reply") or "", "delegated_to": sc.get("delegated_to"),
            "subs": len(sc.get("delegated_to") or {}),
            "spec": scenario_spec(sc, meta, ctx)}


def provenance_card(run: dict, ctx: dict) -> str:
    """Before any verdict: can this run be compared with anything?"""
    meta, name = run["meta"], run["name"]
    fp = meta.get("fingerprints") or {}
    cat = meta.get("catalog") or {}
    eff = meta.get("effective") or {}
    if not fp:
        asked = (f'{esc(meta.get("model") or "?")} / {esc(meta.get("judge_model") or "?")}'
                 '<small>asked for; the model actually used was not recorded</small>') if meta else \
            '<span class="muted">not recorded</span>'
        return ('<section class="card prov-card" aria-labelledby="pv-h"><h2 id="pv-h" class="sr">Provenance</h2>'
                '<div class="banner neutral" style="border-radius:var(--radius-md) var(--radius-md) 0 0"><span class="ic">○</span><div><b>No provenance recorded</b>'
                'This run predates fingerprints. Its verdicts are historic: they cannot be checked against '
                'what is installed today.</div></div><dl class="fields">'
                + (f'<div class="kv"><dt>Catalog</dt><dd><span class="mono">{esc(short(cat.get("catalog_commit")))}</span> '
                   f'{"dirty" if cat.get("catalog_dirty") else "clean"}'
                   f'{" · installed " + esc(nice_iso(cat.get("installed_at"))) if cat.get("installed_at") else ""}</dd></div>'
                   if cat.get("catalog_commit") else '<div class="kv"><dt>Catalog</dt><dd class="muted">not recorded</dd></div>')
                + f'<div class="kv"><dt>Agent / judge</dt><dd>{asked}</dd></div>'
                '<div class="kv"><dt>Harness · CLI · isolation</dt><dd class="muted">not recorded</dd></div>'
                '</dl></section>')
    iso = fp.get("isolation") or ""
    user = iso.startswith("USER SESSION")
    styles = eff.get("output_styles") or []
    harn = fp.get("harness") or {}
    am = model_matches(meta.get("model"), eff.get("agent_models"))
    jm = model_matches(meta.get("judge_model"), eff.get("judge_models"))
    mark = lambda ok: '<span class="ok">✓</span>' if ok else '<span class="no">✕</span>'
    cmp = [f'<li>{mark(iso and not user)} {"Neutral session" if iso and not user else "User session" if user else "Isolation not recorded"}</li>']
    if styles:
        cmp.append(f'<li>{mark(styles == ["default"])} Output style <span class="mono">{esc(", ".join(styles))}</span></li>')
    else:
        cmp.append('<li><span class="wn">⚠</span> Output style not recorded</li>')
    if am is None or jm is None:
        cmp.append('<li><span class="wn">⚠</span> Models: could not confirm the ones asked for</li>')
    else:
        cmp.append(f'<li>{mark(am and jm)} Models {"as requested" if am and jm else "differ from the ones asked for"}</li>')
    cmp.append(f'<li>{"<span class=wn>⚠</span> Catalog tree dirty" if cat.get("catalog_dirty") else "<span class=ok>✓</span> Catalog tree clean"}</li>')
    cmp.append(f'<li>{"<span class=wn>⚠</span> Harness tree dirty — uncommitted harness code ran" if harn.get("dirty") else "<span class=ok>✓</span> Harness tree clean"}</li>')
    banner, verdict = "", ""
    if meta.get("experiment"):
        banner += (f'<div class="banner exp"><span class="ic">⚗</span><div><b>Experiment: {esc(meta["experiment"])}</b>'
                   'Declared with <code>--experiment</code> when the run was created. Read it against its own '
                   'question; it is not a baseline.</div></div>')
    if user:
        banner += ('<div class="banner"><span class="ic">⚠</span><div><b>Not neutral — run with --user-session</b>'
                   "The agents ran with the user's own settings, CLAUDE.md, output style and shell. "
                   'Read it as an experiment: never a baseline.</div></div>')
    elif not iso:
        banner += ('<div class="banner"><span class="ic">⚠</span><div><b>Isolation not recorded</b>'
                   'This run has fingerprints but no session isolation: it may have run with the user\'s own '
                   'settings. Never a baseline.</div></div>')
    if not banner:
        clean = (styles == ["default"]) and am and jm
        verdict = (f'<p class="cmp-verdict">{"Comparable" if clean else "Comparable, with caveats"} '
                   f'<span>— neutral session'
                   + (", default output style" if styles == ["default"] else "")
                   + (", the models that were asked for" if am and jm else "") + '.</span></p>')
    inst = ctx["installed"]
    csub = git(cat.get("catalog_path") or inst.get("catalog_path", ""), "log", "-1", "--format=%s",
               cat.get("catalog_commit", "")) if cat.get("catalog_commit") else ""
    hsub = git(RUNS_DIR.parent, "log", "-1", "--format=%s", harn["commit"]) if harn.get("commit") else ""
    perm, skills = fp.get("permissions") or "", fp.get("skills") or ""
    fields = (
        f'<div class="kv"><dt>Catalog</dt><dd><span class="mono">{esc(short(cat.get("catalog_commit")))}</span> '
        f'{"dirty" if cat.get("catalog_dirty") else "clean"}<small>{esc(csub)}'
        f'{" · installed " + esc(nice_iso(cat.get("installed_at"))) if cat.get("installed_at") else ""}</small></dd></div>'
        f'<div class="kv"><dt>Harness</dt><dd><span class="mono">{esc(short(harn.get("commit")))}</span> '
        + ('<span class="tag warn" style="vertical-align:1px">dirty</span>' if harn.get("dirty") else "clean")
        + f'<small>{esc(hsub)}</small></dd></div>'
        f'<div class="kv"><dt>CLI</dt><dd>{esc(fp.get("cli") or "not recorded")}</dd></div>'
        f'<div class="kv"><dt>Agent model</dt><dd>{esc(", ".join(eff.get("agent_models") or []) or "not recorded")}'
        f'<small>asked for: {esc(meta.get("model"))}</small></dd></div>'
        f'<div class="kv"><dt>Judge model</dt><dd>{esc(", ".join(eff.get("judge_models") or []) or "not recorded")}'
        f'<small>asked for: {esc(meta.get("judge_model"))}</small></dd></div>'
        f'<div class="kv"><dt>Output style</dt><dd>{esc(", ".join(styles) or "not recorded")}</dd></div>'
        f'<div class="kv"><dt>Isolation</dt><dd class="mono">{esc(iso or "not recorded")}</dd></div>'
        f'<div class="kv"><dt>Permissions · skills</dt><dd class="mono">{esc(perm[:8])} · {esc(skills[:8])}</dd></div>')
    return ('<section class="card prov-card" aria-labelledby="pv-h"><h2 id="pv-h" class="sr">Provenance</h2>'
            f'{banner}{verdict}<ul class="cmp">{"".join(cmp)}</ul><dl class="fields">{fields}</dl>'
            f'{versus_baseline(run, ctx)}</section>')


def nice_iso(value) -> str:
    t = parse_ts(value)
    return t.strftime("%-d %b %H:%M") if t else str(value or "")


def versus_baseline(run: dict, ctx: dict) -> str:
    """The question a reader has next: does this run line up with the latest
    full baseline, and on which of the things a verdict depends on?"""
    base = ctx["baseline"]
    fp = run["meta"].get("fingerprints") or {}
    agents = fp.get("agents") or {}
    under = sorted({s.get("agent") for s in run["scenarios"]} & set(agents))
    if any(s.get("agent") == "(routing)" for s in run["scenarios"]):
        under = sorted(agents)
    hashes = ('<details><summary>All ' + str(len(agents)) + ' agent fingerprints</summary><ul class="hashes">'
              + "".join(f'<li class="{"hit" if a in under else ""}">{esc(a)} {esc(h[:8])}</li>'
                        for a, h in sorted(agents.items())) + '</ul></details>') if agents else ""
    if not base:
        return f'<div class="vs"><b>No full baseline to compare against yet.</b>{hashes}</div>'
    if base["name"] == run["name"]:
        return f'<div class="vs"><b>This run is the latest full baseline.</b>{hashes}</div>'
    bfp = base["meta"].get("fingerprints") or {}
    bag = bfp.get("agents") or {}
    same = [a for a in under if bag.get(a) == agents.get(a)]
    diff = [a for a in under if bag.get(a) != agents.get(a)]
    parts = []
    if same and not diff:
        parts.append("the agents under test are unchanged — " + ", ".join(
            f'{esc(a)} <span class="mono">{esc(agents[a][:8])}</span>' for a in same) + ".")
    elif diff:
        parts.append("the agents under test differ — " + ", ".join(
            f'{esc(a)} <span class="mono">{esc((bag.get(a) or "absent")[:8])} → {esc(agents[a][:8])}</span>'
            for a in diff) + (f"; unchanged: {esc(', '.join(same))}." if same else "."))
    other = [k for k, label in (("skills", "skills"), ("isolation", "isolation"), ("permissions", "permissions"))
             if bfp.get(k) != fp.get(k)]
    if other:
        parts.append(f'{", ".join(other).capitalize()} differ, so verdicts on the same scenario are '
                     f'<i>partial</i> matches.')
    else:
        parts.append("Skills, isolation and permissions match.")
    if run["meta"].get("model") != base["meta"].get("model"):
        parts.append(f'Agent model {esc(base["meta"].get("model"))} there, {esc(run["meta"].get("model"))} here.')
    inb = sum(1 for s in run["scenarios"] if s["id"] in set(base["ids"]))
    n = len(run["scenarios"])
    parts.append(f"{'None' if not inb else 'All' if inb == n else inb} of these {n} scenario"
                 f"{'s' if n != 1 else ''} {'is' if inb == 1 else 'are'} in that baseline.")
    return (f'<div class="vs"><b>Against the latest baseline ({esc(nice_time(base["name"], False))}):</b> '
            + " ".join(parts) + hashes + '</div>')


def build_run(run: dict, ctx: dict, home: str = "../index.html") -> str:
    meta, scs, name = run["meta"], run["scenarios"], run["name"]
    summ = ctx["by_name"].get(name) or {"full": False}
    cats = sorted({s.get("category", "?") for s in scs})
    rep = max((s.get("repeat") or 1) for s in scs) if scs else 1
    when = (f'{nice_time(name)} · {len(scs)} scenario{"s" if len(scs) != 1 else ""} · '
            + (", ".join(cats) if len(cats) <= 3 else f"{len(cats)} categories")
            + (f" · {rep} samples each" if rep > 1 else ""))
    tags = ('<span class="tag full">Full suite</span>' if summ.get("full") else '<span class="tag">Partial</span>')
    if meta.get("experiment"):
        tags += f'<span class="tag exp" title="{esc(meta["experiment"])}">Experiment</span>'
    tags += "".join(f'<span class="tag warn">{esc(w)}</span>' for w in run_warnings(meta))
    tally = {}
    for s in scs:
        tally[s["status"]] = tally.get(s["status"], 0) + 1
    ts = [t for s in scs for t in trials_of(s)]
    ac = sum(t.get("agent_cost_usd") or 0 for t in ts)
    jc = sum(t.get("judge_cost_usd") or 0 for t in ts)
    cost = sum(s.get("cost_usd") or 0 for s in scs)
    denied = sum(1 for s in scs if denied_count(s))
    split = f" (agent ${ac:.2f} · judge ${jc:.2f})" if ac or jc else ""
    sumline = (f'<span class="score">{tally.get("PASS", 0)}<small>/{len(scs)} passed</small></span>'
               + "".join(st_chip(k, f"{tally[k]} {k}") for k in ("FAIL", "ERROR", "FLAKY", "PASS") if tally.get(k))
               + (f'<span class="tag warn">Permission denied in {denied} scenario{"s" if denied != 1 else ""}</span>' if denied else "")
               + f'<span class="meta">${cost:.2f}{split} · {len(ts)} sample{"s" if len(ts) != 1 else ""}</span>')
    cat_group = (f'<div class="fgroup"><span>Category</span><span class="fixed mono">{esc(cats[0])} (only one)</span></div>'
                 if len(cats) == 1 else '<div class="fgroup" id="f-cat"><span>Category</span></div>')
    up = os.path.dirname(home)
    data = {"run": name, "icons": TOOL_ICON, "up": up + "/" if up else "",
            "judge": ", ".join((meta.get("effective") or {}).get("judge_models") or [])
                     or meta.get("judge_model") or "the judge",
            "scenarios": [scenario_data(s, meta, ctx) for s in scs]}
    # A reply containing "</script>" would end the tag early and break the page.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    body = (top_bar(home, "history") + '<main class="wrap">'
            f'<div class="crumb"><a href="{home}#history">Runs</a> / {esc(nice_time(name).split(",")[0])}</div>'
            f'<div class="run-title"><h1>{esc(name)}</h1><span class="when">{esc(when)}</span>{tags}</div>'
            + provenance_card(run, ctx) +
            '<section aria-labelledby="rs-h"><h2 id="rs-h" class="sr">Results</h2>'
            f'<div class="sumline">{sumline}</div>'
            '<div class="fbar" role="group" aria-label="Filter scenarios">'
            '<div class="fgroup" id="f-status"><span>Status</span></div>'
            '<div class="fgroup" id="f-agent"><span>Agent</span></div>'
            f'{cat_group}<div class="fgroup" id="f-flag"><span>Show only</span></div></div>'
            '<div class="scns" id="scns"></div>'
            '<p class="empty" id="scn-empty" style="display:none;padding:var(--space-5);text-align:center;'
            'color:var(--text-muted)">No scenario matches these filters.</p></section></main>'
            f'<div class="wrap"><footer>Generated by <code>viz.py</code> from runs/{esc(name)}. '
            'Rendering calls no model.</footer></div>')
    return page(f"Run {name}", RUN_CSS, body, f"const DATA={payload};{RUN_JS}")


# --------------------------------------------------------------------------- #
# HTML — compare (--compare): the previous report, kept as it was
# --------------------------------------------------------------------------- #
LEGACY_CSS = """
*{box-sizing:border-box}
:root{
  --bg:#fbfbfa; --fg:#1a1a19; --dim:#6b6b68; --line:#e4e4e1; --card:#fff;
  --pass:#2e7d4f; --fail:#c0392b; --err:#b7791f; --flaky:#7c5cbf;
  --tool:#4a6fa5; --text:#5a4a7a; --think:#8a8a86; --result:#3d7a6c;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#161615; --fg:#e8e8e5; --dim:#9a9a95; --line:#2e2e2c; --card:#1e1e1d;
  --pass:#5cb87f; --fail:#e07a6c; --err:#d9a441; --flaky:#a98ae0;
  --tool:#7fa3d8; --text:#a690cf; --think:#7a7a76; --result:#6cbfa8;
}}
:root[data-theme=dark]{
  --bg:#161615; --fg:#e8e8e5; --dim:#9a9a95; --line:#2e2e2c; --card:#1e1e1d;
  --pass:#5cb87f; --fail:#e07a6c; --err:#d9a441; --flaky:#a98ae0;
  --tool:#7fa3d8; --text:#a690cf; --think:#7a7a76; --result:#6cbfa8;
}
:root[data-theme=light]{
  --bg:#fbfbfa; --fg:#1a1a19; --dim:#6b6b68; --line:#e4e4e1; --card:#fff;
  --pass:#2e7d4f; --fail:#c0392b; --err:#b7791f; --flaky:#7c5cbf;
  --tool:#4a6fa5; --text:#5a4a7a; --think:#8a8a86; --result:#3d7a6c;
}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.55 ui-sans-serif,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:20px;margin:0 0 4px} .sub{color:var(--dim);margin:0 0 28px}
.grid{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;
  padding:12px 14px;cursor:pointer;transition:.12s}
.card:hover{border-color:var(--dim);transform:translateY(-1px)}
.card h3{margin:0 0 6px;font-size:13px;font-weight:600;font-family:ui-monospace,monospace}
.meta{color:var(--dim);font-size:12px;display:flex;gap:10px;flex-wrap:wrap}
.badge{font-size:11px;font-weight:700;letter-spacing:.04em;padding:1px 7px;
  border-radius:99px;border:1px solid currentColor}
.PASS{color:var(--pass)} .FAIL{color:var(--fail)} .ERROR{color:var(--err)}
.FLAKY{color:var(--flaky)}
/* Samples of one scenario, when --repeat took more than one. */
.samples{margin:10px 0 0;display:flex;flex-direction:column;gap:6px}
.sample{border:1px solid var(--line);border-left:3px solid currentColor;
  border-radius:4px;padding:8px 12px;font-size:13px}
.sample .who{font:600 11px/1.4 ui-monospace,monospace;margin-bottom:4px;
  display:flex;gap:8px;align-items:center}
.sample .txt{color:var(--fg);white-space:pre-wrap;word-break:break-word;
  max-height:9em;overflow:hidden;cursor:pointer}
.sample .txt.open{max-height:none}
.catrow{display:flex;align-items:baseline;gap:10px;margin:26px 0 10px}
.catrow h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;
  color:var(--dim);margin:0;font-weight:600}
.catrow .rule{flex:1;height:1px;background:var(--line)}
dialog{border:1px solid var(--line);border-radius:10px;background:var(--card);
  color:var(--fg);max-width:min(940px,94vw);width:100%;padding:0}
dialog::backdrop{background:#0009}
.dhead{padding:16px 20px;border-bottom:1px solid var(--line);
  display:flex;align-items:center;gap:12px;position:sticky;top:0;background:var(--card)}
.dhead h2{margin:0;font-size:15px;font-family:ui-monospace,monospace;flex:1}
.dbody{padding:16px 20px;max-height:70vh;overflow:auto}
button{font:inherit;background:transparent;color:var(--fg);border:1px solid var(--line);
  border-radius:6px;padding:4px 12px;cursor:pointer}
button:hover{border-color:var(--dim)}
/* Chat view: a run reads as a conversation, because that is what it is. */
.step{opacity:0;transition:opacity .2s} .step.on{opacity:1}
.msg{margin:14px 0 4px}
.msg .who{font:600 12px/1.4 ui-monospace,monospace;margin-bottom:4px;
  display:flex;align-items:center;gap:8px}
.msg .who .t{font-weight:400;color:var(--dim);font-size:11px}
.bub{background:var(--card);border:1px solid var(--line);border-radius:4px 12px 12px 12px;
  padding:10px 14px;white-space:pre-wrap;word-break:break-word;font-size:13.5px;
  max-height:15em;overflow:hidden;cursor:pointer;position:relative}
.bub.open{max-height:none}
.bub.clip::after{content:'';position:absolute;inset:auto 0 0 0;height:2.6em;
  background:linear-gradient(transparent,var(--card))}
.bub.open::after{display:none}
.me .bub{border-radius:12px 4px 12px 12px;background:transparent;border-style:dashed}
/* One colour per speaker, stable across runs: in a group chat you track who
   is talking by colour before you read the name. */
.msg .who{color:var(--spk)}
.bub{border-left:3px solid var(--spk)}
.act .ic,.act b{color:var(--spk)}
.join b{color:var(--spk)}
.final .bub{border-color:var(--pass);max-height:none}
.final .bub::after{display:none}
.tag{font-size:10px;font-weight:700;letter-spacing:.05em;color:var(--pass);
  border:1px solid currentColor;border-radius:99px;padding:0 6px}
.act{display:flex;gap:8px;align-items:baseline;padding:2px 0 2px 2px;
  font:12px/1.5 ui-monospace,monospace;color:var(--dim)}
.act .ic{width:14px;text-align:center;color:var(--tool)}
.act.err .ic,.act.err b{color:var(--fail)}
.act b{font-weight:600;color:var(--tool)}
.act .arg{color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  max-width:62ch;cursor:pointer}
.act .arg.open{white-space:pre-wrap;max-width:none}
.act .t{margin-left:auto;font-size:11px;opacity:.7;flex:none}
.join{margin:16px 0 6px;font:12px ui-monospace,monospace;color:var(--dim);
  border-top:1px dashed var(--line);padding-top:10px}
.join b{color:var(--fg)}
.think{height:3px;background:var(--think);border-radius:2px;opacity:.4;margin:3px 0 3px 22px}
.lane-0{margin-left:0} .lane-1{margin-left:26px;border-left:2px solid var(--line);
  padding-left:14px}
.prompt{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--text);
  border-radius:6px;padding:12px 14px;white-space:pre-wrap;font-size:13.5px;margin:4px 0 8px}
.ctl{display:flex;gap:8px;align-items:center;margin:4px 0 14px}
.reply{border-left:2px solid var(--line);padding-left:14px;white-space:pre-wrap;
  color:var(--fg);font-size:13px;margin-top:6px}
.note{color:var(--dim);font-size:12px;margin:6px 0 0}
/* Per-scenario structure: charge sheet → verdict → samples → conversation. */
h3.sec{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--dim);margin:22px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--line,#ddd)}
.q{color:var(--dim);font-style:italic;font-size:13px}
.catrow .q{margin-left:12px}
.spec{background:var(--card);border-radius:8px;padding:12px 14px}
.spec .q{margin-bottom:8px}
.checks{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.chk{font-family:ui-monospace,monospace;font-size:12px;padding:2px 8px;border-radius:999px;
  border:1px solid var(--line,#ddd)}
.crit{white-space:pre-wrap;font-size:13px;line-height:1.45}
.verdict{border-left:3px solid var(--dim);padding:8px 14px;border-radius:0 8px 8px 0;background:var(--card)}
.verdict.PASS{border-color:var(--pass)} .verdict.FAIL{border-color:var(--fail)}
.verdict.ERROR{border-color:var(--err)} .verdict.FLAKY{border-color:var(--flaky)}
.verdict .jw{margin:6px 0 0;font-size:13px;line-height:1.45}
.card .looks{font-size:12px;color:var(--dim);margin-top:6px;line-height:1.35;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.fails{color:var(--fail);font-size:12.5px;margin:8px 0 0}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600;font-size:12px}
.chg{font-family:ui-monospace,monospace}
"""

LEGACY_JS = """
const D = DATA;
const esc = s => (s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const dlg = document.getElementById('d');
// One colour per speaker, assigned in the order they first appear. Hashing the
// name was stable across runs but collided WITHIN one — two specialists sharing
// a colour in the same conversation defeats the point of colouring at all.
const HUES=[210,145,275,25,330,190,95,55,255,165,300,120];
let SPK = new Map();
const spk = n => {
  if(!SPK.has(n)) SPK.set(n, HUES[SPK.size % HUES.length]);
  return `--spk:hsl(${SPK.get(n)} 55% 45%)`;
};
let timer = null;

function openScenario(runIdx, id){
  const sc = D.runs[runIdx].scenarios.find(s=>s.id===id);
  document.getElementById('dt').textContent = sc.id;
  document.getElementById('db').innerHTML = render(sc);
  wire(sc);
  dlg.showModal();
}
function render(sc){
  SPK = new Map();          // colours are per-conversation
  const n = sc.repeat || 1;
  const spec = D.specs[sc.id];
  const catq = D.catq[sc.category] || '';
  let h = `<div class="meta" style="margin-bottom:10px">
    <span class="badge ${sc.status}">${sc.status}</span>
    ${n>1?`<span><b>${sc.passes}/${n}</b> samples passed</span>`:''}
    <span>${esc(sc.category)}</span>
    <span>agent <b>${esc(sc.agent)}</b></span>
    <span>$${(sc.cost_usd??0).toFixed(3)}</span>
    <span>${sc.duration_ms||0} ms</span>
    <span>${sc.steps.length} steps</span></div>`;

  // 1. The charge sheet: what this test looks for, before any verdict. Read
  // from the YAML — the trace never carried it.
  h += `<h3 class="sec">What this test looks for</h3><div class="spec">`;
  if(catq) h += `<div class="q">${esc(sc.category)} — ${esc(catq)}</div>`;
  if(spec){
    if(spec.checks.length)
      h += `<div class="checks">${spec.checks.map(c=>`<span class="chk">✓ ${esc(c)}</span>`).join('')}</div>`;
    if(spec.judge) h += `<div class="crit">${esc(spec.judge)}</div>`;
    if(!spec.checks.length && !spec.judge) h += `<p class="note">no assertions declared</p>`;
    if(spec.workspace) h += `<p class="note">runs in a fresh copy of <code>${esc(spec.workspace)}</code></p>`;
  } else {
    h += `<p class="note">this scenario is no longer defined in scenarios/*.yaml — the verdict below was reached against a criterion nobody kept</p>`;
  }
  h += `</div>`;

  // 2. The verdict, with every reason it was reached.
  h += `<h3 class="sec">Verdict</h3><div class="verdict ${sc.status}">
        <div class="who"><span class="badge ${sc.status}">${sc.status}</span>
        ${n>1?`<span>${sc.passes}/${n} samples</span>`:''}</div>`;
  if(sc.failures?.length) h += `<div class="fails">✕ ${sc.failures.map(esc).join('<br>✕ ')}</div>`;
  if(sc.judge) h += `<p class="jw"><b>judge — ${sc.judge.verdict===true?'PASS':sc.judge.verdict===false?'FAIL':'no verdict'}:</b> ${esc(sc.judge.why)}</p>`;
  if(sc.error) h += `<div class="fails">error: ${esc(sc.error)}</div>`;
  if(!sc.failures?.length && !sc.judge && !sc.error) h += `<p class="note">deterministic checks passed</p>`;
  h += `</div>`;

  // Every sample, not just the one whose conversation is replayed below. The
  // trace keeps one event stream to stay small, but all the REPLIES — and on a
  // flaky scenario, reading them side by side is the whole point of --repeat.
  if(n>1){
    h += `<h3 class="sec">Samples — ${n}, side by side</h3>
          <div class="samples">`;
    sc.trials.forEach((t,i)=>{
      const jw = t.judge?.why ? ` — ${esc(t.judge.why)}` : '';
      h += `<div class="sample ${t.status}">
        <div class="who"><span class="badge ${t.status}">${t.status}</span>
          <span>sample ${i+1}</span><span>$${(t.cost_usd??0).toFixed(3)}</span></div>
        <div class="txt clip">${esc(t.reply || t.error)}</div>
        ${jw?`<p class="note" style="margin:6px 0 0">judge${jw}</p>`:''}</div>`;
    });
    h += `</div>`;
  }

  h += `<h3 class="sec">Conversation</h3>
        <div class="ctl"><button id="play">▶ play</button>
        <button id="all">show all</button>
        <span class="note" id="pos"></span></div>`;

  // The prompt is the first turn of the conversation, not metadata about it.
  h += `<div id="tl"><div class="step on msg me"><div class="who">you</div>
        <div class="prompt">${esc(sc.prompt)}</div></div>`;

  // Agents already seen, so a subagent's first appearance reads as joining.
  const seen = new Set(['main']);
  // The last text step IS the final reply — showing both duplicates it.
  const lastText = [...sc.steps].reverse().find(s=>s.kind==='text');
  sc.steps.forEach((s,i)=>{
    const name = s.laneName || (s.lane==='main' ? sc.agent : s.lane.slice(-6));
    const depth = s.lane==='main' ? 0 : 1;
    const t = s.ms>1500 ? (s.ms/1000).toFixed(1)+'s' : (s.ms?s.ms+'ms':'');
    let pre = '';
    if(!seen.has(s.lane)){
      seen.add(s.lane);
      const task = sc.delegated_to?.[s.lane]?.task || '';
      pre = `<div class="step join" data-i="${i}" style="${spk(name)}">⑂ <b>${esc(name)}</b> joined${task?' — '+esc(task):''}</div>`;
    }
    if(s.kind==='think'){
      h += pre + `<div class="step think lane-${depth}" data-i="${i}"
                   style="width:${Math.min(160,(s.weight||0)/3)}px"></div>`;
      return;
    }
    if(s.kind==='text'){
      const who = depth ? `${esc(name)}` : esc(sc.agent);
      const fin = s===lastText ? ' final' : '';
      h += pre + `<div class="step msg lane-${depth}${fin}" data-i="${i}" style="${spk(who)}">
        <div class="who">${who}${fin?'<span class="tag">answer</span>':''}${t?`<span class="t">${t}</span>`:''}</div>
        <div class="bub clip">${esc(s.detail)}</div></div>`;
      return;
    }
    // tools and their results are things that HAPPEN, not things anyone says
    const ic = s.kind==='result' ? '↩' : (D.icons[s.name]||'▸');
    const lbl = s.kind==='result' ? 'result' : `<b>${esc(s.name)}</b>`;
    h += pre + `<div class="step act lane-${depth}${s.error?' err':''}" data-i="${i}" style="${spk(name==='main'?sc.agent:name)}">
      <span class="ic">${ic}</span><span>${lbl}</span>
      <span class="arg">${esc(s.detail)}</span>
      ${t?`<span class="t">${t}</span>`:''}</div>`;
  });
  h += `</div>`;
  // Only when it is NOT already the last bubble — otherwise it is the same
  // text printed twice, which reads as if the agent repeated itself.
  if(sc.reply && sc.reply.trim() !== (lastText?.detail||'').trim())
    h += `<h3 class="sec">Final reply</h3>
          <div class="reply">${esc(sc.reply)}</div>`;
  return h;
}
function wire(sc){
  const steps = [...document.querySelectorAll('#tl .step:not(.me)')];
  const pos = document.getElementById('pos');
  document.querySelectorAll('.bub,.arg,.sample .txt').forEach(el=>el.onclick=()=>el.classList.toggle('open'));
  const showAll = ()=>{clearInterval(timer);steps.forEach(s=>s.classList.add('on'));
                       pos.textContent=`${steps.length}/${steps.length}`;};
  document.getElementById('all').onclick = showAll;
  document.getElementById('play').onclick = ()=>{
    clearInterval(timer);
    steps.forEach(s=>s.classList.remove('on'));
    let i=0;
    const tick = ()=>{
      if(i>=steps.length){clearInterval(timer);return;}
      steps[i].classList.add('on');
      steps[i].scrollIntoView({block:'nearest',behavior:'smooth'});
      pos.textContent=`${i+1}/${steps.length}`;
      i++;
    };
    tick(); timer = setInterval(tick, 300);
  };
  showAll();
}
dlg.addEventListener('close',()=>clearInterval(timer));
document.getElementById('x').onclick = ()=>dlg.close();
"""


def render_overview(runs: list, specs: dict = None) -> str:
    specs = specs or {}
    out = []
    for ri, run in enumerate(runs):
        cats = {}
        for sc in run["scenarios"]:
            cats.setdefault(sc.get("category", "?"), []).append(sc)
        total = sum(s.get("cost_usd", 0) for s in run["scenarios"])
        bad = sum(1 for s in run["scenarios"] if s["status"] != "PASS")
        out.append(f'<div class="catrow"><h2>{esc(run["name"])}</h2><div class="rule"></div>'
                   f'<span class="meta">{len(run["scenarios"]) - bad}/{len(run["scenarios"])}'
                   f' passed · ${total:.2f}</span></div>')
        for cat, scs in sorted(cats.items()):
            q = CATEGORY_QUESTION.get(cat, "")
            out.append(f'<div class="catrow"><h2>{esc(cat)}</h2><div class="rule"></div>'
                       + (f'<span class="q">{esc(q)}</span>' if q else '') + '</div>')
            out.append('<div class="grid">')
            for sc in sorted(scs, key=lambda s: s["id"]):
                spec = specs.get(sc["id"])
                out.append(
                    f'<div class="card" onclick="openScenario({ri},\'{esc(sc["id"])}\')">'
                    f'<h3>{esc(sc["id"])}</h3>'
                    f'<div class="meta"><span class="badge {sc["status"]}">{sc["status"]}</span>'
                    + (f'<span>{sc.get("passes", 0)}/{sc["repeat"]}</span>'
                       if sc.get("repeat", 1) > 1 else '') +
                    f'<span>{esc(sc["agent"])}</span>'
                    f'<span>${sc.get("cost_usd", 0):.3f}</span>'
                    f'<span>{len(sc["steps"])} steps</span></div>'
                    f'<div class="looks">{esc(looks_for(spec))}</div></div>')
            out.append("</div>")
    return "\n".join(out)


def render_compare(runs: list) -> str:
    """Same scenario across runs, so a lucky pass stops looking like a habit."""
    ids = sorted({s["id"] for r in runs for s in r["scenarios"]})
    head = "".join(f"<th>{esc(r['name'])}</th>" for r in runs)
    rows = []
    for sid in ids:
        cells, seen = [], []
        for r in runs:
            sc = next((s for s in r["scenarios"] if s["id"] == sid), None)
            st = sc["status"] if sc else "—"
            seen.append(st)
            cells.append(f'<td class="chg {st}">{st}</td>')
        # "—" means the scenario wasn't in that run, not that it changed:
        # counting absence as instability makes every partial run look broken.
        ran = {s for s in seen if s != "—"}
        flag = " ← unstable" if len(ran) > 1 else ""
        rows.append(f'<tr><td class="chg">{esc(sid)}{flag}</td>{"".join(cells)}</tr>')
    unstable = sum(1 for sid in ids
                   if len({s["status"] for r in runs
                           for s in r["scenarios"] if s["id"] == sid}) > 1)
    return (f'<div class="catrow"><h2>comparison</h2><div class="rule"></div>'
            f'<span class="meta">{unstable} scenario(s) changed verdict</span></div>'
            f'<table><tr><th>scenario</th>{head}</tr>{"".join(rows)}</table>'
            f'<p class="note">A scenario that flips between runs was never really '
            f'passing — it was sampling. That is the difference between an agent '
            f'that does the thing and one that sometimes does it.</p>')


# The question each category asks, from the README table. Shown above the
# cards so a reader knows what kind of promise is being checked before reading
# any single scenario.
CATEGORY_QUESTION = {
    "routing": "Given the roster, does the right agent get picked?",
    "composition": "Which SET of specialists does a piece of work need?",
    "hard-rule": "Do the non-negotiable lines hold under pressure?",
    "handoff": "Does the agent know where work goes when it stops being its own?",
    "inheritance": "Did the CORE that install.py inlines actually arrive?",
    "judgment": "Does the agent reason the way its judgment section says?",
    "self-verification": "Does an agent checking its own work find what an outsider finds?",
    "build-quality": "Solo vs reviewed vs team — measured by running the code.",
}


def load_specs(root: Path) -> dict:
    """id -> what the scenario looks for, read from scenarios/*.yaml.

    The trace records the verdict and the judge's reason, never the CRITERION:
    that lives in the YAML, and a report that shows a FAIL without what was
    being asked for is a verdict with no charge sheet."""
    try:
        import yaml
    except ImportError:
        return {}
    out = {}
    for f in sorted((root / "scenarios").glob("*.yaml")):
        for s in yaml.safe_load(f.read_text()) or []:
            a = s.get("assert") or {}
            checks = []
            if s.get("expect"):
                checks.append(f"routes to `{s['expect']}`")
            if a.get("matches"):
                checks.append(f"reply matches /{a['matches']}/")
            for n in a.get("contains") or []:
                checks.append(f"mentions `{n}`")
            for n in a.get("not_contains") or []:
                checks.append(f"never says `{n}`")
            ex = s.get("exec") or {}
            if ex:
                checks.append(f"code passes {ex.get('suite', '?')} "
                              f"(min {a.get('min_score', 1.0):.0%})")
            out[s["id"]] = {
                "category": s.get("category", f.stem),
                "agent": s.get("agent", ""),
                "checks": checks,
                "judge": (a.get("judge") or "").strip(),
                "workspace": s.get("workspace", ""),
                "manual": bool(s.get("manual")),
            }
    return out


def looks_for(spec: dict) -> str:
    """One line for a card: the deterministic checks, else the criterion's
    first sentence. Enough to know what the card is about without opening it."""
    if not spec:
        return "criterion no longer defined"
    crit = " ".join(spec["judge"].split())
    first = ""
    if crit:
        first = crit[:160] + ("…" if len(crit) > 160 else "")
        for sep in (". PASS", ". FAIL", ". "):
            i = crit.find(sep)
            if 0 < i < 180:
                first = crit[:i + 1]
                break
    # The judge's first sentence says what is wanted in words; a regex or a
    # substring says how it is checked. Words first, mechanics after.
    parts = [x for x in (first, "; ".join(spec["checks"])) if x]
    return " · ".join(parts)


def build_compare(runs: list) -> str:
    """--compare: the verdict table across runs, then the previous card view.
    Out of the redesign's scope; kept byte-for-byte in behaviour."""
    specs = load_specs(RUNS_DIR.parent)
    wanted = {s["id"] for r in runs for s in r["scenarios"]}
    data = {"runs": [{"name": r["name"], "scenarios": r["scenarios"]} for r in runs],
            "icons": TOOL_ICON,
            "specs": {k: v for k, v in specs.items() if k in wanted},
            "catq": CATEGORY_QUESTION}
    body = render_compare(runs) + render_overview(runs, specs)
    title = " vs ".join(r["name"] for r in runs)
    # A reply containing "</script>" would end the tag early and break the page.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>agent run · {esc(title)}</title><style>{LEGACY_CSS}</style></head><body>
<div class="wrap">
<h1>Agent run · {esc(title)}</h1>
<p class="sub">Each card says what its test looks for; click one to see the
criterion in full, the verdict, and the agent at work — every tool call, every
read, every pause. A green result can still hide wasted steps.</p>
{body}
</div>
<dialog id="d"><div class="dhead"><h2 id="dt"></h2><button id="x">close</button></div>
<div class="dbody" id="db"></div></dialog>
<script>const DATA={payload};{LEGACY_JS}</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="*", type=Path, help="run directories")
    ap.add_argument("--index", action="store_true",
                    help="regenerate every run's report plus an index page")
    ap.add_argument("--compare", action="store_true",
                    help="add a per-scenario verdict table across the runs given")
    ap.add_argument("-o", "--out", type=Path, help="output path (default: inside the last run)")
    args = ap.parse_args()

    if args.index:
        out = args.out or (RUNS_DIR / "index.html")
        out.write_text(build_index(RUNS_DIR))
        print(f"  index → {out}")
        return 0

    if not args.runs:
        sys.exit("give a run directory, or --index for all of them")
    if args.compare and len(args.runs) < 2:
        sys.exit("--compare needs at least two run directories")

    runs = [load_run(p) for p in args.runs]
    out = args.out or (args.runs[-1] / "report.html")
    if args.compare:
        out.write_text(build_compare(runs))
    else:
        # Every run given gets its own page; the last one goes to -o if set.
        ctx = context()
        for p, run in zip(args.runs, runs):
            dest = out if p is args.runs[-1] else p / "report.html"
            home = os.path.relpath(RUNS_DIR / "index.html", dest.resolve().parent)
            dest.write_text(build_run(run, ctx, home))
    n = sum(len(r["scenarios"]) for r in runs)
    print(f"  {n} scenarios from {len(runs)} run(s) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
