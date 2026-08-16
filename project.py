#!/usr/bin/env python3
"""project.py — give the agents a real task and record how they work on it.

`run.py` asserts contracts on one agent at a time. This does the other thing:
hands a genuine, multi-specialty piece of work to an orchestrator and captures
the whole tree — who got spawned, what each one did, what it cost.

  ./project.py "Necesito un checkout con pagos"
  ./project.py "..." --agent stark
  ./project.py "..." --delegate           # ask explicitly for delegation

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




def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("task", help="what you want done, in your own words")
    ap.add_argument("--agent", default="eng-manager",
                    help="who receives it (default: eng-manager, the router)")
    ap.add_argument("--delegate", action="store_true",
                    help="explicitly ask for Task delegation instead of observing "
                         "whether it happens unprompted")
    ap.add_argument("--model", default="", help="model for the run")
    args = ap.parse_args()

    prompt = args.task + (DELEGATION_NUDGE if args.delegate else "")
    mode = "asked to delegate" if args.delegate else "observing"
    print(f"→ {args.agent} · {mode}\n  {args.task[:90]}\n")

    t0 = time.time()
    reply = harness.ask(prompt, agent=args.agent, model=args.model,
                        forward_subagents=True)
    elapsed = time.time() - t0

    if reply.error:
        sys.exit(f"failed: {reply.error}")

    tree = harness.delegation_tree(reply.events)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = RUNS / stamp
    outdir.mkdir(parents=True, exist_ok=True)
    record = {
        "id": f"project-{stamp}",
        "category": "project",
        "agent": args.agent,
        "prompt": args.task,
        "status": "PASS",          # nothing is asserted here; this is observation
        "failures": [],
        "judge": None,
        "cost_usd": round(reply.cost, 4),
        "duration_ms": reply.ms,
        "reply": reply.text,
        "error": "",
        "delegated_to": tree,
        "events": reply.events,
    }
    (outdir / "trace.jsonl").write_text(json.dumps(record, ensure_ascii=False) + "\n")
    (outdir / f"project-{stamp}.md").write_text(
        f"# {args.task}\n\n- agent: `{args.agent}`\n- mode: {mode}\n"
        f"- cost: ${reply.cost:.3f} · {reply.ms} ms\n\n## Reply\n\n{reply.text}\n")

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
