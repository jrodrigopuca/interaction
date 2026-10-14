#!/usr/bin/env python3
"""project.py — give the agents a real task and record how they work on it.

`run.py` asserts contracts on one agent at a time. This does the other thing:
hands a genuine, multi-specialty piece of work to an orchestrator and captures
the whole tree — who got spawned, what each one did, what it cost.

  ./project.py "Necesito un checkout con pagos" --max-cost-usd 10
  ./project.py "..." --agent stark --max-cost-usd 10
  ./project.py "..." --delegate --max-cost-usd 10   # ask explicitly for delegation

--max-cost-usd is required (B-060): one task with delegation cost up to $6.86
when measured, and it is handed to the call as `claude -p --max-budget-usd`.
A call stopped by it, or failed in any other way, is still recorded with what
it spent.

The `--delegate` flag exists because it separates two different questions, and
conflating them would hide the answer to both:

  without it   does the orchestrator delegate ON ITS OWN?
  with it      CAN it delegate when told to?

The catalog's agents are advisory by design — `validate.py` forbids them from
assuming they can invoke another agent, since not every host can. So a flat
tree from the first form is a finding, not a bug.

Output is a `runs/<timestamp>/trace.jsonl` in the same shape `run.py` writes,
so `viz.py` renders it with no changes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import run as harness   # ask(), and the trace conventions

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"

DELEGATION_NUDGE = (
    "\n\nCoordiná este trabajo: delegá cada parte al especialista que "
    "corresponda usando la herramienta Task, en paralelo cuando se pueda, y "
    "después integrá lo que devuelvan en una respuesta sola."
)



def build_record(reply, agent: str, task: str, stamp: str, tree: dict) -> dict:
    """The trace line, also for a failed call: its cost was spent all the same."""
    return {
        "id": f"project-{stamp}",
        "category": "project",
        "agent": agent,
        "prompt": task,
        # Nothing is asserted here; this is observation. A call that failed —
        # its budget, a timeout — is the one thing that is not.
        "status": "ERROR" if reply.error else "PASS",
        "failures": [],
        "judge": None,
        "cost_usd": round(reply.cost, 4),
        "duration_ms": reply.ms,
        "reply": reply.text,
        "error": reply.error,
        "delegated_to": tree,
        "events": reply.events,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("task", help="what you want done, in your own words")
    ap.add_argument("--agent", default="eng-manager",
                    help="who receives it (default: eng-manager, the router)")
    ap.add_argument("--delegate", action="store_true",
                    help="explicitly ask for Task delegation instead of observing "
                         "whether it happens unprompted")
    ap.add_argument("--model", default="", help="model for the run")
    ap.add_argument("--max-cost-usd", type=float, metavar="USD", required=True,
                    help="the most this task may spend, approved beforehand; passed to "
                         "the call as --max-budget-usd")
    args = ap.parse_args()
    if args.max_cost_usd <= 0:
        sys.exit("--max-cost-usd must be above zero")

    prompt = args.task + (DELEGATION_NUDGE if args.delegate else "")
    mode = "asked to delegate" if args.delegate else "observing"
    print(f"→ {args.agent} · {mode}\n  {args.task[:90]}\n")

    t0 = time.time()
    reply = harness.ask(prompt, agent=args.agent, model=args.model,
                        forward_subagents=True, max_budget=args.max_cost_usd)
    elapsed = time.time() - t0

    tree = harness.delegation_tree(reply.events)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = RUNS / stamp
    outdir.mkdir(parents=True, exist_ok=True)
    record = build_record(reply, args.agent, args.task, stamp, tree)
    (outdir / "trace.jsonl").write_text(json.dumps(record, ensure_ascii=False) + "\n")
    (outdir / f"project-{stamp}.md").write_text(
        f"# {args.task}\n\n- agent: `{args.agent}`\n- mode: {mode}\n"
        f"- cost: ${reply.cost:.3f} · {reply.ms} ms\n\n## Reply\n\n{reply.text}\n")

    if reply.error:
        print(f"  failed: {reply.error}\n  ${reply.cost:.2f} spent · {elapsed:.0f}s → {outdir}")
        return 2 if reply.error.startswith("budget") else 1

    if tree:
        print(f"  delegated to {len(tree)} subagent(s):")
        for info in tree.values():
            print(f"    ⑂ {info['agent']:16} {info['events']:3} events  "
                  f"{info['task']}")
    else:
        print("  no delegation: it answered alone.")
        if not args.delegate:
            print("  (that may be correct — these agents name owners rather than\n"
                  "   invoking them. Re-run with --delegate to see if it can.)")

    print(f"\n  ${reply.cost:.2f} · {elapsed:.0f}s → {outdir}")
    print(f"  ./viz.py {outdir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
