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

RUNS_DIR = Path(__file__).resolve().parent / "runs"

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
    return {"name": path.name, "scenarios": scenarios}


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
CSS = """
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
.idx td.n{font-family:ui-monospace,monospace}
.idx tr{cursor:pointer} .idx tr:hover td{background:var(--card)}
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
  let h = `<div class="meta" style="margin-bottom:10px">
    <span class="badge ${sc.status}">${sc.status}</span>
    ${n>1?`<span><b>${sc.passes}/${n}</b> samples passed</span>`:''}
    <span>agent <b>${esc(sc.agent)}</b></span>
    <span>$${(sc.cost_usd??0).toFixed(3)}</span>
    <span>${sc.duration_ms||0} ms</span>
    <span>${sc.steps.length} steps</span></div>`;
  if(sc.failures?.length) h += `<div class="fails">✕ ${sc.failures.map(esc).join('<br>✕ ')}</div>`;
  if(sc.judge) h += `<p class="note"><b>judge:</b> ${sc.judge.verdict===true?'PASS':sc.judge.verdict===false?'FAIL':'no verdict'} — ${esc(sc.judge.why)}</p>`;

  // Every sample, not just the one whose conversation is replayed below. The
  // trace keeps one event stream to stay small, but all the REPLIES — and on a
  // flaky scenario, reading them side by side is the whole point of --repeat.
  if(n>1){
    h += `<h3 style="font-size:13px;margin:18px 0 0">${n} samples</h3>
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

  h += `<div class="ctl"><button id="play">▶ play</button>
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
    h += `<h3 style="font-size:13px;margin:22px 0 0">Final reply</h3>
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
                    + (f'<span>{sc.get("passes", 0)}/{sc["repeat"]}</span>'
                       if sc.get("repeat", 1) > 1 else '') +
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


def current_scenario_ids(root: Path) -> set:
    """Scenario ids defined right now, so historical runs can be labelled."""
    try:
        import yaml
    except ImportError:
        return set()
    out = set()
    for f in sorted((root / "scenarios").glob("*.yaml")):
        for s in yaml.safe_load(f.read_text()) or []:
            out.add(s["id"])
    return out


def build_index(runs_dir: Path) -> str:
    """One page listing every run, so you never have to guess which to open.

    Each row also regenerates that run's own report, so the index is never a
    set of links to files that don't exist yet."""
    current = current_scenario_ids(runs_dir.parent)
    rows, total, historical = [], 0.0, 0
    for d in sorted(runs_dir.iterdir(), reverse=True):
        if not (d / "trace.jsonl").exists():
            continue
        run = load_run(d)
        (d / "report.html").write_text(build([run], False))
        scs = run["scenarios"]
        cost = sum(s.get("cost_usd", 0) for s in scs)
        total += cost
        bad = [s for s in scs if s["status"] != "PASS"]
        cats = sorted({s.get("category", "?") for s in scs})
        subs = sum(len(s.get("delegated_to") or {}) for s in scs)
        # A run whose only blemish is instability is not the same as one that
        # failed outright — colouring both red hides which kind of bad it was.
        state = ("PASS" if not bad
                 else "FLAKY" if all(s["status"] == "FLAKY" for s in bad)
                 else "FAIL")
        # A run judged against scenarios that no longer exist is history, not a
        # baseline: comparing a future run to it reads a verdict from criteria
        # nobody kept. Say so rather than deleting the evidence.
        stale = current and [s for s in scs
                             if s["id"] not in current
                             and not s["id"].startswith("project-")]
        if stale:
            historical += 1
        rows.append(
            f'<tr onclick="location.href=\'{d.name}/report.html\'">'
            f'<td class="n">{esc(d.name)}</td>'
            f'<td><span class="badge {state}">{len(scs) - len(bad)}/{len(scs)}</span></td>'
            f'<td>{esc(", ".join(cats))}'
            + (f'<br><span class="note">historical — {len(stale)} scenario(s) '
               f'no longer defined</span>' if stale else '') +
            f'</td>'
            f'<td class="n">{"⑂ " + str(subs) if subs else ""}</td>'
            f'<td class="n">${cost:.2f}</td></tr>')
    if not rows:
        rows = ['<tr><td colspan="5">no runs yet — try <code>./run.py '
                '--category routing</code></td></tr>']
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>agent runs</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Agent runs</h1>
<p class="sub">Every recorded run, newest first. Click one to watch it as a
conversation. ${total:.2f} spent across {len(rows)} run(s){
f" · {historical} historical (scenarios since changed — kept as evidence, not as a baseline)" if historical else ""}.</p>
<table class="idx"><tr><th>run</th><th>result</th><th>categories</th>
<th>subagents</th><th>cost</th></tr>{"".join(rows)}</table>
</div></body></html>"""


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
    out.write_text(build(runs, args.compare))
    n = sum(len(r["scenarios"]) for r in runs)
    print(f"  {n} scenarios from {len(runs)} run(s) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
