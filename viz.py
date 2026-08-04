#!/usr/bin/env python3
"""viz.py — render a harness run as a self-contained HTML timeline.

`run.py` asserts whether an agent honoured its contract. It cannot show you the
WORK: which tools the agent reached for, what it read, where it stalled, what it
retried. A green scenario can still hide two wasted calls hunting for a file.

Usage:
  ./viz.py runs/20260804-083423                 # one run
  ./viz.py runs/A runs/B --compare              # same scenarios across two runs
  ./viz.py runs/latest -o report.html           # choose the output path

Writes one HTML file with no external resources — open it, no server needed.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

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


def steps_from(events: list) -> list:
    """Flatten Claude's event stream into a readable sequence.

    Only `assistant` and `user` events carry timestamps; the `system` ones that
    report thinking carry a token delta instead. So ordering comes from the
    stream itself and time is used, where present, to show the gaps — never the
    other way round, or the thinking steps would collapse onto their neighbours.

    `parent_tool_use_id` becomes the lane: null is the agent you invoked, any
    other value is a subagent it spawned. Today's harness traces are single-lane;
    the same rendering shows a delegation tree the moment one isn't."""
    steps, prev_ts = [], None
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
                steps.append({"kind": "think", "lane": lane, "label": "thinking",
                              "detail": f"{delta} tokens", "weight": delta, "ms": 0})
            continue

        if kind == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    name = block.get("name", "tool")
                    arg = block.get("input", {})
                    hint = (arg.get("command") or arg.get("file_path")
                            or arg.get("pattern") or arg.get("description")
                            or arg.get("skill") or "")
                    steps.append({"kind": "tool", "lane": lane, "name": name,
                                  "label": f"{name}", "detail": str(hint),
                                  "full": json.dumps(arg, ensure_ascii=False, indent=2),
                                  "ms": gap})
                elif block.get("type") == "text" and block.get("text", "").strip():
                    text = block["text"].strip()
                    steps.append({"kind": "text", "lane": lane,
                                  "label": text.split("\n")[0][:90],
                                  "detail": text, "ms": gap})

        elif kind == "user":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    body = block.get("content")
                    if isinstance(body, list):
                        body = " ".join(b.get("text", "") for b in body
                                        if isinstance(b, dict))
                    body = str(body or "")
                    steps.append({"kind": "result", "lane": lane,
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
        rec["steps"] = steps_from(events)
        # A lane id means nothing on screen. project.py records which subagent
        # each spawn id belongs to, so relabel the lanes with agent names.
        names = {k: v.get("agent", "?") for k, v in (rec.get("delegated_to") or {}).items()}
        for s in rec["steps"]:
            s["laneName"] = "main" if s["lane"] == "main" else names.get(s["lane"], s["lane"][-6:])
        scenarios.append(rec)
    return {"name": path.name, "scenarios": scenarios}


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
CSS = """
*{box-sizing:border-box}
:root{
  --bg:#fbfbfa; --fg:#1a1a19; --dim:#6b6b68; --line:#e4e4e1; --card:#fff;
  --pass:#2e7d4f; --fail:#c0392b; --err:#b7791f;
  --tool:#4a6fa5; --text:#5a4a7a; --think:#8a8a86; --result:#3d7a6c;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#161615; --fg:#e8e8e5; --dim:#9a9a95; --line:#2e2e2c; --card:#1e1e1d;
  --pass:#5cb87f; --fail:#e07a6c; --err:#d9a441;
  --tool:#7fa3d8; --text:#a690cf; --think:#7a7a76; --result:#6cbfa8;
}}
:root[data-theme=dark]{
  --bg:#161615; --fg:#e8e8e5; --dim:#9a9a95; --line:#2e2e2c; --card:#1e1e1d;
  --pass:#5cb87f; --fail:#e07a6c; --err:#d9a441;
  --tool:#7fa3d8; --text:#a690cf; --think:#7a7a76; --result:#6cbfa8;
}
:root[data-theme=light]{
  --bg:#fbfbfa; --fg:#1a1a19; --dim:#6b6b68; --line:#e4e4e1; --card:#fff;
  --pass:#2e7d4f; --fail:#c0392b; --err:#b7791f;
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
.step{display:grid;grid-template-columns:70px 22px 1fr;gap:10px;align-items:start;
  padding:5px 0;opacity:0;transition:opacity .18s}
.step.on{opacity:1}
.gap{font:11px/1.6 ui-monospace,monospace;color:var(--dim);text-align:right;padding-top:2px}
.dot{text-align:center;font-size:13px;padding-top:1px}
.k-tool .dot{color:var(--tool)} .k-text .dot{color:var(--text)}
.k-think .dot{color:var(--think)} .k-result .dot{color:var(--result)}
.lbl{font-family:ui-monospace,monospace;font-size:12.5px;word-break:break-word}
.k-tool .lbl b{color:var(--tool)} .k-result.err .lbl{color:var(--fail)}
.det{color:var(--dim);font-size:12px;white-space:pre-wrap;word-break:break-word;
  margin-top:2px;max-height:3.4em;overflow:hidden;cursor:pointer}
.det.open{max-height:none}
.lane{display:inline-block;font-size:10px;padding:0 5px;border-radius:4px;
  border:1px solid var(--line);color:var(--dim);margin-left:6px}
.bar{height:3px;background:var(--think);border-radius:2px;margin-top:4px;opacity:.45}
.ctl{display:flex;gap:8px;align-items:center;margin:4px 0 14px}
.reply{border-left:2px solid var(--line);padding-left:14px;white-space:pre-wrap;
  color:var(--fg);font-size:13px;margin-top:6px}
.note{color:var(--dim);font-size:12px;margin:6px 0 0}
.fails{color:var(--fail);font-size:12.5px;margin:8px 0 0}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600;font-size:12px}
.chg{font-family:ui-monospace,monospace}
"""

JS = """
const D = DATA;
const esc = s => (s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const dlg = document.getElementById('d');
let timer = null;

function openScenario(runIdx, id){
  const sc = D.runs[runIdx].scenarios.find(s=>s.id===id);
  document.getElementById('dt').textContent = sc.id;
  document.getElementById('db').innerHTML = render(sc);
  wire(sc);
  dlg.showModal();
}
function render(sc){
  let h = `<div class="meta" style="margin-bottom:10px">
    <span class="badge ${sc.status}">${sc.status}</span>
    <span>agent <b>${esc(sc.agent)}</b></span>
    <span>$${(sc.cost_usd??0).toFixed(3)}</span>
    <span>${sc.duration_ms||0} ms</span>
    <span>${sc.steps.length} steps</span></div>`;
  if(sc.failures?.length) h += `<div class="fails">✕ ${sc.failures.map(esc).join('<br>✕ ')}</div>`;
  if(sc.judge) h += `<p class="note"><b>judge:</b> ${sc.judge.verdict===true?'PASS':sc.judge.verdict===false?'FAIL':'no verdict'} — ${esc(sc.judge.why)}</p>`;
  if(sc.delegated_to && Object.keys(sc.delegated_to).length){
    const rows = Object.values(sc.delegated_to).map(d=>
      `<tr><td class="chg">⑂ ${esc(d.agent)}</td><td>${d.events} events</td><td>${esc(d.task)}</td></tr>`).join('');
    h += `<h3 style="font-size:13px;margin:16px 0 4px">Delegated to ${Object.keys(sc.delegated_to).length}</h3>
          <table>${rows}</table>`;
  }
  h += `<div class="ctl"><button id="play">▶ play</button>
        <button id="all">show all</button>
        <span class="note" id="pos"></span></div><div id="tl">`;
  sc.steps.forEach((s,i)=>{
    const gap = s.ms>1500 ? (s.ms/1000).toFixed(1)+'s' : (s.ms?s.ms+'ms':'');
    const dot = s.kind==='tool' ? (D.icons[s.name]||'▸')
              : s.kind==='text' ? '●' : s.kind==='result' ? '↩' : '·';
    const lane = s.lane!=='main' ? `<span class="lane">${esc(s.laneName||s.lane.slice(-6))}</span>` : '';
    const lbl = s.kind==='tool' ? `<b>${esc(s.name)}</b>${lane}` : esc(s.label)+lane;
    const bar = s.kind==='think' && s.weight ?
        `<div class="bar" style="width:${Math.min(100,s.weight/40)}%"></div>` : '';
    h += `<div class="step k-${s.kind}${s.error?' err':''}" data-i="${i}">
      <div class="gap">${gap}</div><div class="dot">${dot}</div>
      <div><div class="lbl">${lbl}</div>
      ${s.detail?`<div class="det">${esc(s.detail)}</div>`:''}${bar}</div></div>`;
  });
  h += `</div>`;
  if(sc.reply) h += `<h3 style="font-size:13px;margin:20px 0 0">Final reply</h3>
                     <div class="reply">${esc(sc.reply)}</div>`;
  return h;
}
function wire(sc){
  const steps = [...document.querySelectorAll('#tl .step')];
  const pos = document.getElementById('pos');
  document.querySelectorAll('.det').forEach(d=>d.onclick=()=>d.classList.toggle('open'));
  const showAll = ()=>{clearInterval(timer);steps.forEach(s=>s.classList.add('on'));
                       pos.textContent=`${steps.length}/${steps.length}`;};
  document.getElementById('all').onclick = showAll;
  document.getElementById('play').onclick = ()=>{
    clearInterval(timer);
    steps.forEach(s=>s.classList.remove('on'));
    let i=0;
    // Real gaps, compressed: a 40s run should still be watchable, but the
    // relative rhythm — where the agent stalled — has to survive.
    const tick = ()=>{
      if(i>=steps.length){clearInterval(timer);return;}
      steps[i].classList.add('on');
      steps[i].scrollIntoView({block:'nearest',behavior:'smooth'});
      pos.textContent=`${i+1}/${steps.length}`;
      i++;
    };
    tick(); timer = setInterval(tick, 260);
  };
  showAll();
}
dlg.addEventListener('close',()=>clearInterval(timer));
document.getElementById('x').onclick = ()=>dlg.close();
"""


def esc(s):
    return html.escape(str(s or ""))


def render_overview(runs: list) -> str:
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
            out.append(f'<div class="catrow"><h2>{esc(cat)}</h2><div class="rule"></div></div>')
            out.append('<div class="grid">')
            for sc in sorted(scs, key=lambda s: s["id"]):
                out.append(
                    f'<div class="card" onclick="openScenario({ri},\'{esc(sc["id"])}\')">'
                    f'<h3>{esc(sc["id"])}</h3>'
                    f'<div class="meta"><span class="badge {sc["status"]}">{sc["status"]}</span>'
                    f'<span>{esc(sc["agent"])}</span>'
                    f'<span>${sc.get("cost_usd", 0):.3f}</span>'
                    f'<span>{len(sc["steps"])} steps</span></div></div>')
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


def build(runs: list, compare: bool) -> str:
    data = {"runs": [{"name": r["name"], "scenarios": r["scenarios"]} for r in runs],
            "icons": TOOL_ICON}
    body = render_compare(runs) if compare else ""
    body += render_overview(runs)
    title = " vs ".join(r["name"] for r in runs) if compare else runs[0]["name"]
    # A reply containing "</script>" would end the tag early and break the page.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>agent run · {esc(title)}</title><style>{CSS}</style></head><body>
<div class="wrap">
<h1>Agent run · {esc(title)}</h1>
<p class="sub">Click a scenario to watch the agent work: every tool call, every
read, every pause. A green result can still hide wasted steps.</p>
{body}
</div>
<dialog id="d"><div class="dhead"><h2 id="dt"></h2><button id="x">close</button></div>
<div class="dbody" id="db"></div></dialog>
<script>const DATA={payload};{JS}</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+", type=Path, help="run directories")
    ap.add_argument("--compare", action="store_true",
                    help="add a per-scenario verdict table across the runs given")
    ap.add_argument("-o", "--out", type=Path, help="output path (default: inside the last run)")
    args = ap.parse_args()

    if args.compare and len(args.runs) < 2:
        sys.exit("--compare needs at least two run directories")

    runs = [load_run(p) for p in args.runs]
    out = args.out or (args.runs[-1] / "report.html")
    out.write_text(build(runs, args.compare))
    n = sum(len(r["scenarios"]) for r in runs)
    print(f"  {n} scenarios from {len(runs)} run(s) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
