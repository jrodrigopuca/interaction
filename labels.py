#!/usr/bin/env python3
"""labels.py — calibrate the judge against a human (B-039).

Every verdict in this harness rests on an LLM judge, and nothing had ever
compared it with a person. This builds that comparison without running a
single agent again: the samples already exist in runs/, with the criterion
they were judged against and the event stream the reply is rebuilt from.

  ./labels.py pick                  # choose the candidates, fix the holdout
  ./labels.py page                  # labels/label.html: label them, judge hidden
  ./labels.py import labels.json    # merge what the page exported
  ./labels.py rejudge --judge-model opus --max-cost-usd 1
  ./labels.py report                # TPR / TNR, dev and holdout apart

The holdout is drawn once, at `pick`, with a recorded seed. Disagreements on
the dev split are for fixing criteria; TPR and TNR are reported on the holdout
only, so a criterion is never tuned against the very samples that score it.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run   # noqa: E402

LABELS = ROOT / "labels"
CANDIDATES = LABELS / "candidates.jsonl"   # what the labeller sees: no verdicts
VERDICTS = LABELS / "judge-at-pick.jsonl"  # the original verdicts, kept apart
HUMAN = LABELS / "labels.jsonl"            # one human label per candidate
PAGE = LABELS / "label.html"
HOLDOUT_SHARE = 0.4
CHOICES = ("PASS", "FAIL", "AMBIGUA")


def key_of(run_name: str, sid: str) -> str:
    return f"{run_name}/{sid}"


def read_jsonl(path: Path) -> list:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def judged_samples(runs_dir: Path) -> list:
    """Every lead sample that was judged and kept its event stream: the reply
    the judge read is rebuilt exactly as Reply.transcript was built."""
    out = []
    for trace in sorted(runs_dir.glob("*/trace.jsonl")):
        try:
            meta = json.loads((trace.parent / "run.json").read_text())
        except (OSError, ValueError):
            meta = {}
        for line in trace.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            criterion = (rec.get("assert") or {}).get("judge")
            verdict = (rec.get("judge") or {}).get("verdict")
            if not criterion or not rec.get("events") or verdict is None:
                continue
            graded = run.transcript_of(rec["events"], rec.get("reply") or "") or rec.get("reply", "")
            out.append({
                "key": key_of(trace.parent.name, rec["id"]),
                "run": trace.parent.name, "id": rec["id"],
                "category": rec.get("category", ""), "agent": rec.get("agent", ""),
                "prompt": rec.get("prompt", ""), "criterion": criterion,
                "criterion_sha": run.criterion_sha(criterion), "graded": graded,
                "old_version": bool(meta.get("experiment")),
                "_verdict": "PASS" if verdict else "FAIL",
                "_why": (rec.get("judge") or {}).get("why", ""),
            })
    return out


def pick(samples: list, n: int, seed: int) -> list:
    """All judge-FAILs (they are rare and most likely to hold real failures),
    the rest judge-PASSes drawn at random with experiment runs — earlier agent
    versions measured on purpose — first in line. One sample per identical
    (scenario, reply), and the holdout drawn per original verdict so both
    splits hold both kinds."""
    rng = random.Random(seed)
    seen, uniq = set(), []
    for s in samples:
        sig = (s["id"], hashlib.sha256(s["graded"].encode()).hexdigest())
        if sig not in seen:
            seen.add(sig)
            uniq.append(s)
    fails = [s for s in uniq if s["_verdict"] == "FAIL"]
    passes = [s for s in uniq if s["_verdict"] == "PASS"]
    rng.shuffle(fails)
    rng.shuffle(passes)
    old = [s for s in passes if s["old_version"]]
    new = [s for s in passes if not s["old_version"]]
    want_pass = max(0, n - len(fails))
    chosen_pass = old[: want_pass // 3] + new
    chosen_pass = chosen_pass[:want_pass]
    chosen = fails[:n] + chosen_pass
    for group in (fails[:n], chosen_pass):
        k = round(len(group) * HOLDOUT_SHARE)
        held = set(id(s) for s in rng.sample(group, k)) if group else set()
        for s in group:
            s["split"] = "holdout" if id(s) in held else "dev"
    rng.shuffle(chosen)            # the labeller must not meet all FAILs first
    return chosen


def public(s: dict) -> dict:
    """What the labeller may see: never the judge's verdict or its reason."""
    return {k: v for k, v in s.items() if not k.startswith("_")}


PAGE_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Etiquetar al juez</title>
<style>
:root{--bg:#fafaf8;--fg:#1c1c1a;--muted:#6b6b66;--line:#deddd6;--card:#fff;--pass:#1f7a3a;--fail:#b3261e;--amb:#8a6100;--accent:#2d5bd7}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#a3a29b;--line:#34332f;--card:#1f1f1d;--pass:#5cc47a;--fail:#ff8a80;--amb:#e0b44c;--accent:#8aa8ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,sans-serif}
main{max-width:920px;margin:0 auto;padding:16px}
header{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;margin-bottom:12px}
h1{font-size:18px;margin:0}.muted{color:var(--muted)}.tag{font:12px ui-monospace,monospace;border:1px solid var(--line);border-radius:4px;padding:1px 6px}
section{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:10px 0}
section h2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
pre{white-space:pre-wrap;word-wrap:break-word;margin:0;font:13.5px/1.5 ui-monospace,SFMono-Regular,monospace}
.reply pre{font-family:system-ui,sans-serif;font-size:15px}
.bar{position:sticky;bottom:0;background:var(--bg);border-top:1px solid var(--line);padding:10px 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
button{font:inherit;padding:8px 14px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.pass{border-color:var(--pass);color:var(--pass)}button.fail{border-color:var(--fail);color:var(--fail)}button.amb{border-color:var(--amb);color:var(--amb)}
button.on{color:var(--card)}button.pass.on{background:var(--pass)}button.fail.on{background:var(--fail)}button.amb.on{background:var(--amb)}
textarea{width:100%;min-height:52px;font:inherit;padding:6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.grow{flex:1}a{color:var(--accent)}
</style></head><body><main>
<header><h1>Etiquetar al juez</h1><span class="muted" id="progress"></span><span class="grow"></span>
<button id="export">Exportar etiquetas</button></header>
<p class="muted">Leé la respuesta completa y decidí si cumple el <b>criterio</b>, como lo haría el juez. No ves su veredicto a propósito. <b>AMBIGUA</b> es para cuando con esta respuesta ni vos podés decidir. Todo se guarda en este navegador; al terminar, exportá.</p>
<header><span class="tag" id="id"></span><span class="tag" id="agent"></span><span class="tag" id="cat"></span><span class="muted" id="run"></span></header>
<section><h2>Pedido al agente</h2><pre id="prompt"></pre></section>
<section><h2>Criterio</h2><pre id="criterion"></pre></section>
<section class="reply"><h2>Respuesta (lo que lee el juez)</h2><pre id="graded"></pre></section>
<section><h2>Nota (opcional)</h2><textarea id="note" placeholder="Por qué, sobre todo si es FAIL o AMBIGUA"></textarea></section>
<div class="bar"><button id="prev">← Anterior</button>
<button class="pass" data-v="PASS">PASS</button><button class="fail" data-v="FAIL">FAIL</button><button class="amb" data-v="AMBIGUA">AMBIGUA</button>
<span class="grow"></span><button id="next">Siguiente →</button></div>
</main>
<script>
const DATA = __DATA__;
const STORE = "b039-labels";
let labels = {}; try { labels = JSON.parse(localStorage.getItem(STORE) || "{}"); } catch (e) {}
for (const [k, v] of Object.entries(__PRIOR__)) if (!labels[k]) labels[k] = v;
let i = Math.max(0, DATA.findIndex(d => !labels[d.key])); if (i < 0) i = 0;
const $ = id => document.getElementById(id);
function save() { try { localStorage.setItem(STORE, JSON.stringify(labels)); } catch (e) {} }
function show() {
  const d = DATA[i], l = labels[d.key] || {};
  $("id").textContent = d.id; $("agent").textContent = d.agent; $("cat").textContent = d.category;
  $("run").textContent = d.run; $("prompt").textContent = d.prompt; $("criterion").textContent = d.criterion;
  $("graded").textContent = d.graded; $("note").value = l.note || "";
  document.querySelectorAll("[data-v]").forEach(b => b.classList.toggle("on", b.dataset.v === l.label));
  const done = DATA.filter(x => labels[x.key] && labels[x.key].label).length;
  $("progress").textContent = `${i + 1} de ${DATA.length} · etiquetadas ${done}`;
  window.scrollTo(0, 0);
}
document.querySelectorAll("[data-v]").forEach(b => b.onclick = () => {
  const d = DATA[i]; labels[d.key] = {label: b.dataset.v, note: $("note").value, criterion_sha: d.criterion_sha,
    at: new Date().toISOString()}; save(); if (i < DATA.length - 1) { i++; } show();
});
$("note").oninput = () => { const d = DATA[i]; if (labels[d.key]) { labels[d.key].note = $("note").value; save(); } };
$("prev").onclick = () => { if (i > 0) { i--; show(); } };
$("next").onclick = () => { if (i < DATA.length - 1) { i++; show(); } };
$("export").onclick = () => {
  const out = DATA.filter(d => labels[d.key] && labels[d.key].label).map(d => ({key: d.key, ...labels[d.key]}));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: "application/json"}));
  a.download = "labels.json"; a.click();
};
show();
</script></body></html>
"""


def build_page(candidates: list, prior: dict) -> str:
    data = json.dumps([public(c) for c in candidates], ensure_ascii=False)
    # Inside a <script>, "</" could close the tag early; escape it.
    data = data.replace("</", "<\\/")
    return (PAGE_HTML.replace("__DATA__", data)
            .replace("__PRIOR__", json.dumps(prior, ensure_ascii=False).replace("</", "<\\/")))


def merge(existing: list, exported: list, candidates: list) -> list:
    """Exported labels win over earlier ones for the same key; a label for a
    key that is not a candidate, or with an unknown value, is refused."""
    known = {c["key"]: c for c in candidates}
    by_key = {r["key"]: r for r in existing}
    for r in exported:
        if r.get("key") not in known:
            raise SystemExit(f"label for an unknown candidate: {r.get('key')}")
        if r.get("label") not in CHOICES:
            raise SystemExit(f"{r['key']}: label must be one of {CHOICES}, got {r.get('label')!r}")
        c = known[r["key"]]
        by_key[r["key"]] = {"key": r["key"], "label": r["label"], "note": r.get("note", ""),
                            "criterion_sha": c["criterion_sha"], "split": c["split"],
                            "at": r.get("at")}
    return [by_key[c["key"]] for c in candidates if c["key"] in by_key]


def rates(rows: list) -> dict:
    """TPR: of the samples the human passed, how many the judge passed.
    TNR: of those the human failed, how many the judge failed — the one that
    matters most, since a judge that passes failures paints the catalog green.
    AMBIGUA labels and missing verdicts are counted apart, never scored."""
    tp = sum(1 for r in rows if r["label"] == "PASS" and r["judge"] == "PASS")
    fn = sum(1 for r in rows if r["label"] == "PASS" and r["judge"] == "FAIL")
    tn = sum(1 for r in rows if r["label"] == "FAIL" and r["judge"] == "FAIL")
    fp = sum(1 for r in rows if r["label"] == "FAIL" and r["judge"] == "PASS")
    return {"tpr": tp / (tp + fn) if tp + fn else None, "tnr": tn / (tn + fp) if tn + fp else None,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp,
            "ambiguous": sum(1 for r in rows if r["label"] == "AMBIGUA"),
            "no_verdict": sum(1 for r in rows if r["label"] != "AMBIGUA" and r["judge"] not in ("PASS", "FAIL"))}


def cmd_pick(args) -> int:
    if CANDIDATES.is_file() and not args.force:
        sys.exit(f"{CANDIDATES} exists: the holdout is fixed once. --force redraws it "
                 f"(and orphans every label made so far)")
    samples = judged_samples(args.runs)
    chosen = pick(samples, args.n, args.seed)
    write_jsonl(CANDIDATES, [public(c) for c in chosen])
    write_jsonl(VERDICTS, [{"key": c["key"], "verdict": c["_verdict"], "why": c["_why"]} for c in chosen])
    (LABELS / "pick.json").write_text(json.dumps({
        "seed": args.seed, "n": len(chosen), "holdout_share": HOLDOUT_SHARE,
        "picked_at": datetime.now().isoformat(timespec="seconds"),
        "pool": len(samples)}, indent=2))
    cats = sorted({c["category"] for c in chosen})
    print(f"{len(chosen)} candidates from {len(samples)} judged samples · "
          f"{sum(c['split'] == 'holdout' for c in chosen)} held out · categories: {', '.join(cats)}")
    return 0


def cmd_page(args) -> int:
    candidates = read_jsonl(CANDIDATES)
    if not candidates:
        sys.exit("no candidates: run `./labels.py pick` first")
    prior = {r["key"]: {k: r[k] for k in ("label", "note", "criterion_sha", "at") if k in r}
             for r in read_jsonl(HUMAN)}
    PAGE.write_text(build_page(candidates, prior))
    print(f"{PAGE} · {len(candidates)} candidates, {len(prior)} already labelled · open it in a browser")
    return 0


def cmd_import(args) -> int:
    exported = json.loads(Path(args.file).read_text())
    rows = merge(read_jsonl(HUMAN), exported, read_jsonl(CANDIDATES))
    write_jsonl(HUMAN, rows)
    counts = {v: sum(1 for r in rows if r["label"] == v) for v in CHOICES}
    print(f"{HUMAN}: {len(rows)} labels · {counts}")
    return 0


def cmd_rejudge(args) -> int:
    candidates = {c["key"]: c for c in read_jsonl(CANDIDATES)}
    keys = [r["key"] for r in read_jsonl(HUMAN)] if not args.all else list(candidates)
    run.JUDGE_MODEL = args.judge_model
    out, spent = [], 0.0
    for k in keys:
        if spent >= args.max_cost_usd:
            print(f"budget reached at ${spent:.2f}: {len(keys) - len(out)} left unjudged")
            break
        c = candidates[k]
        ok, why, cost = run.judge(c["criterion"], c["graded"])
        spent += cost or 0.0
        out.append({"key": k, "judge": {True: "PASS", False: "FAIL"}.get(ok, "ERROR"),
                    "why": why, "criterion_sha": c["criterion_sha"]})
    path = LABELS / f"rejudge-{args.judge_model}-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    write_jsonl(path, out)
    print(f"{path} · {len(out)} verdicts · ${spent:.2f}")
    return 0


def cmd_report(args) -> int:
    human = {r["key"]: r for r in read_jsonl(HUMAN)}
    files = [Path(f) for f in args.rejudge] or sorted(LABELS.glob("rejudge-*.jsonl"))
    if not files:
        sys.exit("no rejudge file: run `./labels.py rejudge` first")
    for f in files:
        verdicts = {r["key"]: r for r in read_jsonl(f)}
        rows = [{"label": h["label"], "judge": verdicts[k]["judge"], "split": h["split"],
                 "stale": verdicts[k]["criterion_sha"] != h["criterion_sha"]}
                for k, h in human.items() if k in verdicts]
        print(f"\n{f.name}")
        for split in ("dev", "holdout"):
            part = [r for r in rows if r["split"] == split]
            r = rates(part)
            fmt = lambda x: "—" if x is None else f"{x:.2f}"
            print(f"  {split:8} n={len(part):3}  TPR {fmt(r['tpr'])}  TNR {fmt(r['tnr'])}  "
                  f"(tp {r['tp']} fn {r['fn']} tn {r['tn']} fp {r['fp']}, "
                  f"ambiguous {r['ambiguous']}, no verdict {r['no_verdict']})")
        stale = sum(1 for r in rows if r["stale"])
        if stale:
            print(f"  {stale} label(s) were made against a different criterion text")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick", help="choose the candidates and fix the holdout")
    p.add_argument("--n", type=int, default=60)
    p.add_argument("--seed", type=int, default=39)
    p.add_argument("--runs", type=Path, default=run.RUNS)
    p.add_argument("--force", action="store_true")
    sub.add_parser("page", help="write labels/label.html")
    p = sub.add_parser("import", help="merge labels exported from the page")
    p.add_argument("file")
    p = sub.add_parser("rejudge", help="judge the labelled samples again (calls the model)")
    p.add_argument("--judge-model", default=run.JUDGE_MODEL)
    p.add_argument("--max-cost-usd", type=float, required=True)
    p.add_argument("--all", action="store_true", help="every candidate, labelled or not")
    p = sub.add_parser("report", help="TPR and TNR per split")
    p.add_argument("rejudge", nargs="*")
    args = ap.parse_args()
    return {"pick": cmd_pick, "page": cmd_page, "import": cmd_import,
            "rejudge": cmd_rejudge, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
