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

The holdout is drawn by SCENARIO, never by sample: fixing a criterion on dev
changes every sample of that scenario, so a scenario with samples on both
sides would leak the fix into the score. Each scenario's side is fixed once
and recorded in labels/pick.json; a scenario whose disagreements were already
read goes to dev (`resplit --pin-dev`), since it is no longer blind.
Disagreements on dev are for fixing criteria; TPR and TNR are reported on the
holdout only, so a criterion is never tuned against the samples that score it.

  ./labels.py resplit --pin-dev ID ...   # move to by-scenario splits, keep labels
  ./labels.py add --n 20                 # more candidates, likely failures first
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run   # noqa: E402

LABELS = ROOT / "labels"
CANDIDATES = LABELS / "candidates.jsonl"   # what the labeller sees: no verdicts
VERDICTS = LABELS / "judge-at-pick.jsonl"  # the original verdicts, kept apart
HUMAN = LABELS / "labels.jsonl"            # one human label per candidate
PICK = LABELS / "pick.json"                # seed, and each scenario's split
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
            lead = {
                "key": key_of(trace.parent.name, rec["id"]),
                "run": trace.parent.name, "id": rec["id"],
                "category": rec.get("category", ""), "agent": rec.get("agent", ""),
                "prompt": rec.get("prompt", ""), "criterion": criterion,
                "criterion_sha": run.criterion_sha(criterion), "graded": graded,
                "old_version": bool(meta.get("experiment")),
                "_verdict": "PASS" if verdict else "FAIL",
                "_why": (rec.get("judge") or {}).get("why", ""),
            }
            out.append(lead)
            # The other samples of a --repeat run: the trace keeps each one's
            # graded text and verdict, against the same criterion. Keyed
            # "run/id#k" so the lead keeps the key every earlier label uses.
            for k, t in enumerate(rec.get("trials") or [], start=1):
                tv = (t.get("judge") or {}).get("verdict")
                if k == 1 or tv is None or not t.get("graded"):
                    continue
                out.append(dict(lead, key=f"{lead['key']}#{k}", graded=t["graded"],
                                _verdict="PASS" if tv else "FAIL",
                                _why=(t.get("judge") or {}).get("why", "")))
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
    has_fail = {}
    for s in chosen:
        has_fail[s["id"]] = has_fail.get(s["id"], False) or s["_verdict"] == "FAIL"
    splits = split_scenarios(has_fail, rng, set())
    for s in chosen:
        s["split"] = splits[s["id"]]
    rng.shuffle(chosen)            # the labeller must not meet all FAILs first
    return chosen


def split_scenarios(has_fail: dict, rng: random.Random, pinned: set) -> dict:
    """Scenario id -> "dev" | "holdout". Pinned ids go to dev; the rest are
    drawn per group (holds a failure or not) so the holdout gets both kinds."""
    out = {sid: "dev" for sid in has_fail if sid in pinned}
    for group in (True, False):
        ids = sorted(sid for sid, f in has_fail.items() if f is group and sid not in pinned)
        held = set(rng.sample(ids, round(len(ids) * HOLDOUT_SHARE)))
        out.update({sid: "holdout" if sid in held else "dev" for sid in ids})
    return out


def more(pool: list, chosen: list, human: list, n: int, rng: random.Random) -> list:
    """Up to n samples not chosen yet, likeliest failures first: runs of an
    earlier agent version, then scenarios a human has already failed, then the
    rest. Every judge-FAIL is already in at `pick`, so these are judge-PASSes —
    exactly where a lenient judge would hide."""
    taken = {c["key"] for c in chosen}
    seen = {(c["id"], hashlib.sha256(c["graded"].encode()).hexdigest()) for c in chosen}
    failed = {h["key"].split("/", 1)[1].split("#")[0] for h in human if h["label"] == "FAIL"}
    tiers = ([], [], [])
    for s in pool:
        sig = (s["id"], hashlib.sha256(s["graded"].encode()).hexdigest())
        if s["key"] in taken or sig in seen:
            continue
        seen.add(sig)
        tiers[0 if s["old_version"] else 1 if s["id"] in failed else 2].append(s)
    out = []
    for t in tiers:
        rng.shuffle(t)
        out += t
    return out[:n]


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
.stale{border:1px solid var(--amb);color:var(--amb);border-radius:8px;padding:8px 12px;margin:10px 0}
</style></head><body><main>
<header><h1>Etiquetar al juez</h1><span class="muted" id="progress"></span><span class="grow"></span>
<button id="export">Exportar etiquetas</button></header>
<p class="muted">Leé la respuesta completa y decidí si cumple el <b>criterio</b>, como lo haría el juez. No ves su veredicto a propósito. <b>AMBIGUA</b> es para cuando con esta respuesta ni vos podés decidir. Todo se guarda en este navegador; al terminar, exportá.</p>
<header><span class="tag" id="id"></span><span class="tag" id="agent"></span><span class="tag" id="cat"></span><span class="muted" id="run"></span></header>
<section><h2>Pedido al agente</h2><pre id="prompt"></pre></section>
<p id="stale" class="stale" hidden>El criterio cambió desde tu etiqueta. Volvé a decidir con este texto: tu etiqueta anterior queda marcada.</p>
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
// labels.jsonl wins when it is newer: a label corrected outside the page
// (or on another browser) must not be reverted by an older local copy.
for (const [k, v] of Object.entries(__PRIOR__))
  if (!labels[k] || (v.at && (!labels[k].at || Date.parse(v.at) > Date.parse(labels[k].at)))) labels[k] = v;
let i = DATA.findIndex(d => !labels[d.key] || labels[d.key].criterion_sha !== d.criterion_sha); if (i < 0) i = 0;
const $ = id => document.getElementById(id);
function save() { try { localStorage.setItem(STORE, JSON.stringify(labels)); } catch (e) {} }
function show() {
  const d = DATA[i], l = labels[d.key] || {};
  $("id").textContent = d.id; $("agent").textContent = d.agent; $("cat").textContent = d.category;
  $("run").textContent = d.run; $("prompt").textContent = d.prompt; $("criterion").textContent = d.criterion;
  $("graded").textContent = d.graded; $("note").value = l.note || "";
  $("stale").hidden = !(l.label && l.criterion_sha && l.criterion_sha !== d.criterion_sha);
  document.querySelectorAll("[data-v]").forEach(b => b.classList.toggle("on", b.dataset.v === l.label));
  const done = DATA.filter(x => labels[x.key] && labels[x.key].label && labels[x.key].criterion_sha === x.criterion_sha).length;
  $("progress").textContent = `${i + 1} de ${DATA.length} · al día ${done}`;
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


def when(stamp: str) -> datetime:
    """An `at` as an aware instant. The page writes UTC with a Z; a stamp
    written by hand may be local and naive. Compared as text, "…T12:00"
    (local) and "…T14:00Z" order by accident, not by time."""
    d = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return d if d.tzinfo else d.astimezone()


def merge(existing: list, exported: list, candidates: list) -> list:
    """Exported labels win over earlier ones for the same key, unless the one
    on file is newer — a label revised outside the page must not be undone by
    an older export. What a review added to a row (`original_label`,
    `revised`, `excluded`) is kept. A label for a key that is not a candidate,
    or with an unknown value, is refused."""
    known = {c["key"]: c for c in candidates}
    by_key = {r["key"]: r for r in existing}
    for r in exported:
        if r.get("key") not in known:
            raise SystemExit(f"label for an unknown candidate: {r.get('key')}")
        if r.get("label") not in CHOICES:
            raise SystemExit(f"{r['key']}: label must be one of {CHOICES}, got {r.get('label')!r}")
        c = known[r["key"]]
        prior = by_key.get(r["key"], {})
        if prior.get("at") and r.get("at") and when(r["at"]) < when(prior["at"]):
            continue
        kept = {k: prior[k] for k in ("original_label", "revised", "excluded") if k in prior}
        by_key[r["key"]] = {**kept, "key": r["key"], "label": r["label"], "note": r.get("note", ""),
                            # the text the human read, not the one current now:
                            # a label made before `refresh` must stay stale
                            "criterion_sha": r.get("criterion_sha") or c["criterion_sha"],
                            "split": c["split"],
                            "at": r.get("at")}
    return [by_key[c["key"]] for c in candidates if c["key"] in by_key]


def rates(rows: list) -> dict:
    """TPR: of the samples the human passed, how many the judge passed.
    TNR: of those the human failed, how many the judge failed — the one that
    matters most, since a judge that passes failures paints the catalog green.
    AMBIGUA labels and missing verdicts are counted apart, never scored, and
    so is a judge that abstains: a judge that says AMBIGUA on everything hard
    would score a fine TNR on what is left, so `report` shows the abstentions
    next to it."""
    tp = sum(1 for r in rows if r["label"] == "PASS" and r["judge"] == "PASS")
    fn = sum(1 for r in rows if r["label"] == "PASS" and r["judge"] == "FAIL")
    tn = sum(1 for r in rows if r["label"] == "FAIL" and r["judge"] == "FAIL")
    fp = sum(1 for r in rows if r["label"] == "FAIL" and r["judge"] == "PASS")
    return {"tpr": tp / (tp + fn) if tp + fn else None, "tnr": tn / (tn + fp) if tn + fp else None,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp,
            "ambiguous": sum(1 for r in rows if r["label"] == "AMBIGUA"),
            "abstained": sum(1 for r in rows if r["label"] != "AMBIGUA" and r["judge"] == "AMBIGUA"),
            "no_verdict": sum(1 for r in rows if r["label"] != "AMBIGUA"
                              and r["judge"] not in ("PASS", "FAIL", "AMBIGUA"))}


def cmd_pick(args) -> int:
    if CANDIDATES.is_file() and not args.force:
        sys.exit(f"{CANDIDATES} exists: the holdout is fixed once. --force redraws it "
                 f"(and orphans every label made so far)")
    samples = judged_samples(args.runs)
    chosen = pick(samples, args.n, args.seed)
    write_jsonl(CANDIDATES, [public(c) for c in chosen])
    write_jsonl(VERDICTS, [{"key": c["key"], "verdict": c["_verdict"], "why": c["_why"]} for c in chosen])
    PICK.write_text(json.dumps({
        "seed": args.seed, "n": len(chosen), "holdout_share": HOLDOUT_SHARE,
        "picked_at": datetime.now().isoformat(timespec="seconds"),
        "pool": len(samples), "split_by": "scenario",
        "scenario_splits": {c["id"]: c["split"] for c in chosen}}, indent=2))
    cats = sorted({c["category"] for c in chosen})
    print(f"{len(chosen)} candidates from {len(samples)} judged samples · "
          f"{sum(c['split'] == 'holdout' for c in chosen)} held out · categories: {', '.join(cats)}")
    return 0


def cmd_resplit(args) -> int:
    """Re-draw dev/holdout by scenario over the candidates already chosen.
    Labels are kept (they belong to a sample, not to a side); only the side
    moves. A failure the human saw counts like one the judge saw."""
    candidates, human = read_jsonl(CANDIDATES), read_jsonl(HUMAN)
    if not candidates:
        sys.exit("no candidates: run `./labels.py pick` first")
    verdicts = {r["key"]: r["verdict"] for r in read_jsonl(VERDICTS)}
    failed = {h["key"] for h in human if h["label"] == "FAIL"}
    has_fail = {}
    for c in candidates:
        f = verdicts.get(c["key"]) == "FAIL" or c["key"] in failed
        has_fail[c["id"]] = has_fail.get(c["id"], False) or f
    unknown = set(args.pin_dev) - set(has_fail)
    if unknown:
        sys.exit(f"--pin-dev names no candidate scenario: {', '.join(sorted(unknown))}")
    splits = split_scenarios(has_fail, random.Random(args.seed), set(args.pin_dev))
    for c in candidates:
        c["split"] = splits[c["id"]]
    for h in human:
        h["split"] = splits[h["key"].split("/", 1)[1]]
    write_jsonl(CANDIDATES, candidates)
    write_jsonl(HUMAN, human)
    meta = json.loads(PICK.read_text()) if PICK.is_file() else {}
    meta.update({"split_by": "scenario", "resplit_seed": args.seed,
                 "resplit_at": datetime.now().isoformat(timespec="seconds"),
                 "pinned_dev": sorted(args.pin_dev), "pinned_why": args.why,
                 "scenario_splits": splits})
    PICK.write_text(json.dumps(meta, indent=2))
    summary(candidates, human)
    return 0


def cmd_add(args) -> int:
    candidates, human = read_jsonl(CANDIDATES), read_jsonl(HUMAN)
    meta = json.loads(PICK.read_text()) if PICK.is_file() else {}
    if meta.get("split_by") != "scenario":
        sys.exit("splits are still per sample: run `./labels.py resplit` first")
    rng = random.Random(args.seed)
    pool = judged_samples(args.runs)
    if getattr(args, "only", ""):
        ids = {i.strip() for i in args.only.split(",") if i.strip()}
        pool = [s for s in pool if s["id"] in ids]
    new = more(pool, candidates, human, args.n, rng)
    if not new:
        sys.exit("no judged sample left to add")
    splits = meta["scenario_splits"]
    fresh = {s["id"]: False for s in new if s["id"] not in splits}
    splits.update(split_scenarios(fresh, rng, set(fresh) if getattr(args, "dev", False) else set()))
    for s in new:
        s["split"] = splits[s["id"]]
    write_jsonl(CANDIDATES, candidates + [public(s) for s in new])
    write_jsonl(VERDICTS, read_jsonl(VERDICTS) +
                [{"key": s["key"], "verdict": s["_verdict"], "why": s["_why"]} for s in new])
    meta.setdefault("added", []).append({"n": len(new), "seed": args.seed,
                                         "at": datetime.now().isoformat(timespec="seconds")})
    meta["n"] = len(candidates) + len(new)
    PICK.write_text(json.dumps(meta, indent=2))
    print(f"added {len(new)} ({sum(s['old_version'] for s in new)} from earlier agent versions)")
    summary(candidates + new, human)
    return 0


def summary(candidates: list, human: list) -> None:
    labelled = {h["key"]: h["label"] for h in human if not h.get("excluded")}
    for split in ("dev", "holdout"):
        part = [c for c in candidates if c["split"] == split]
        got = [labelled[c["key"]] for c in part if c["key"] in labelled]
        print(f"  {split:8} {len({c['id'] for c in part}):3} scenarios · {len(part):3} samples · "
              f"labelled {len(got)} (FAIL {got.count('FAIL')}, PASS {got.count('PASS')}, "
              f"AMBIGUA {got.count('AMBIGUA')})")


def refreshed(candidates: list, scenarios: dict) -> list:
    """Candidates carrying the criterion each scenario has NOW. The reply is
    the same; what it is graded against moved. Labels keep the hash of the
    text the human read, so `report` and the page show which ones to review,
    and `rejudge --resume` judges only the samples whose text changed."""
    out = []
    for c in candidates:
        sc = scenarios.get(c["id"])
        now = (sc.assertions or {}).get("judge") if sc else None
        if now and now != c["criterion"]:
            c = dict(c, criterion=now, criterion_sha=run.criterion_sha(now))
        out.append(c)
    return out


def cmd_refresh(args) -> int:
    candidates = read_jsonl(CANDIDATES)
    new = refreshed(candidates, {s.id: s for s in run.load_scenarios()})
    moved = sorted({n["id"] for o, n in zip(candidates, new) if o["criterion_sha"] != n["criterion_sha"]})
    write_jsonl(CANDIDATES, new)
    human = {h["key"]: h for h in read_jsonl(HUMAN)}
    stale = [n["key"] for n in new if n["key"] in human and human[n["key"]]["criterion_sha"] != n["criterion_sha"]]
    print(f"{len(moved)} scenario(s) with a new criterion: {', '.join(moved) or '—'}")
    print(f"{len(stale)} label(s) made against an older text · `./labels.py page --only-stale` to review them")
    return 0


def cmd_page(args) -> int:
    candidates = read_jsonl(CANDIDATES)
    if not candidates:
        sys.exit("no candidates: run `./labels.py pick` first")
    prior = {r["key"]: {k: r[k] for k in ("label", "note", "criterion_sha", "at") if k in r}
             for r in read_jsonl(HUMAN)}
    if args.only_stale:
        candidates = [c for c in candidates
                      if c["key"] in prior and prior[c["key"]].get("criterion_sha") != c["criterion_sha"]]
        if not candidates:
            sys.exit("no label is stale: nothing to review")
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


# A judge from another model family (B-039): a Claude judge grading agents
# that run on Claude may share their blind spots. Codex has the catalog
# installed (48 lh-* skills in its skill roots), and a judge that can load
# them grades the catalog with the catalog — so every call drops the skill
# listing, the plugin/app/permission blocks and the environment, replaces the
# base instructions with the judge's own, runs in an empty directory with a
# read-only sandbox and no saved session, and any tool the judge still uses
# turns that verdict into an ERROR. `codex debug prompt-input` with the same
# flags shows what the model sees; codex_isolation() checks it before a run.
CODEX_FLAGS = [
    "--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check",
    "-s", "read-only",
    "-c", "skills.include_instructions=false",
    "-c", "include_permissions_instructions=false",
    "-c", "include_apps_instructions=false",
    "-c", "include_collaboration_mode_instructions=false",
    "-c", "include_environment_context=false",
    "-c", "features.plugins=false", "-c", "features.apps=false",
    "-c", "features.recommended_plugins=false",
    # A grader needs no tools. Turning them off is the stronger guarantee and
    # the cheaper call: measured on one sample, 12,953 input tokens -> 8,481,
    # same verdict. Codex still adds ~7.7k of its own around an ~800-token
    # prompt; what it is was not inspected (prompt-input shows no tools).
    "-c", "features.shell_tool=false", "-c", "features.unified_exec=false",
    "-c", "features.multi_agent=false", "-c", "features.view_image=false",
    "-c", "features.image_generation=false", "-c", "features.browser_use=false",
    "-c", "features.computer_use=false", "-c", "features.goals=false",
    "-c", "features.sleep_tool=false", "-c", "features.tool_suggest=false",
    "-c", "features.skill_search=false", "-c", 'web_search="disabled"',
]
CODEX_QUIET_ITEMS = {"agent_message", "reasoning"}   # anything else is a tool


def codex_flags(model: str, effort: str, preamble_file: Path) -> list:
    return CODEX_FLAGS + ["-m", model, "-c", f"model_reasoning_effort={effort}",
                          "-c", f"model_instructions_file={json.dumps(str(preamble_file))}"]


def codex_isolation(flags: list) -> list:
    """What the codex judge would see that it must not: catalog skill or agent
    names. Renders the prompt locally; no model call."""
    overrides = [x for i, f in enumerate(flags[:-1]) if f == "-c" for x in ("-c", flags[i + 1])]
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["codex", "debug", "prompt-input", *overrides, "probe"],
                           cwd=tmp, capture_output=True, text=True, timeout=60)
    if r.returncode:
        return [f"prompt-input failed: {r.stderr.strip()[:200]}"]
    leaks = sorted(set(re.findall(r"\blh-[a-z][a-z-]+", r.stdout)))
    leaks += [a for a in ("generalist", "eng-manager", "senior-dev") if a in r.stdout]
    return leaks


def codex_judge(criterion: str, reply: str, flags: list, ambiguous: bool) -> tuple:
    """(verdict | None, why, tokens). The same text run.judge sends, read by
    another family; the verdict comes from the last agent message."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r = subprocess.run(["codex", "exec", "--json", *flags, "-"], cwd=tmp,
                               input=run.judge_prompt(criterion, reply, ambiguous),
                               capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return None, "judge call failed: timeout", 0
    text, tools, tokens, errors = "", [], 0, []
    for line in r.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        item = ev.get("item") or {}
        if ev.get("type") == "item.completed":
            if item.get("type") == "agent_message":
                text = item.get("text", "")
            elif item.get("type") not in CODEX_QUIET_ITEMS:
                tools.append(item.get("type"))
        elif ev.get("type") == "turn.completed":
            u = ev.get("usage") or {}
            tokens += (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)
        elif ev.get("type") in ("error", "turn.failed"):
            errors.append(str(ev.get("message") or ev.get("error"))[:200])
    if tools:
        return None, f"judge used tools {sorted(set(tools))}: not a clean verdict", tokens
    if r.returncode or errors or not text:
        return None, f"judge call failed: {'; '.join(errors) or r.stderr.strip()[:200]}", tokens
    verdict, why = run.parse_verdict(text)
    return verdict, why, tokens


def cmd_rejudge(args) -> int:
    candidates = {c["key"]: c for c in read_jsonl(CANDIDATES)}
    keys = ([r["key"] for r in read_jsonl(HUMAN) if not r.get("excluded")] if not args.all
            else list(candidates))
    if getattr(args, "only", ""):
        ids = {i.strip() for i in args.only.split(",") if i.strip()}
        keys = [k for k in keys if k in candidates and candidates[k]["id"] in ids]
    if args.judge_cli == "claude":
        if args.max_cost_usd is None:
            sys.exit("--max-cost-usd is required for a claude judge")
        if args.ambiguous:
            sys.exit("--ambiguous is codex-only for now: run.judge reads PASS or FAIL")
        run.JUDGE_MODEL = args.judge_model
        cap = f"${args.max_cost_usd:.2f}"
    else:
        if not args.max_calls:
            sys.exit("--max-calls is required for a codex judge: the CLI reports tokens, not USD")
        if args.judge_model in ("opus", "sonnet", "haiku"):
            sys.exit("--judge-model names a codex model for --judge-cli codex (see `codex debug models`)")
        preamble = LABELS / ".judge-preamble.txt"
        preamble.write_text(run.JUDGE_PREAMBLE)
        flags = codex_flags(args.judge_model, args.effort, preamble)
        leaks = codex_isolation(flags)
        if leaks:
            sys.exit(f"the codex judge would see catalog content, refusing: {', '.join(leaks)}")
        cap = f"{args.max_calls} calls"
    name = args.judge_model if args.judge_cli == "claude" else f"codex-{args.judge_model}"
    stem = f"rejudge-{name}{'-amb' if args.ambiguous else ''}-"
    out = []
    if args.resume:
        path = Path(args.resume)
        if not path.name.startswith(stem):
            sys.exit(f"{path.name} is not a run of this judge ({stem}*): resume the same judge")
        # Kept: a verdict on the criterion text as it is now. An ERROR, or a
        # verdict on a criterion that has changed since, is judged again.
        out = [r for r in read_jsonl(path) if r["judge"] != "ERROR" and r["key"] in candidates
               and r["criterion_sha"] == candidates[r["key"]]["criterion_sha"]]
        done = {r["key"] for r in out}
        keys = [k for k in keys if k not in done]
        print(f"resuming {path.name}: {len(done)} kept, {len(keys)} to judge")
    else:
        path = LABELS / f"{stem}{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    spent, tokens, calls = 0.0, 0, 0
    for k in keys:
        if (args.judge_cli == "claude" and spent >= args.max_cost_usd) or \
                (args.judge_cli == "codex" and calls >= args.max_calls):
            print(f"cap reached ({cap}): {len(keys) - calls} left unjudged; "
                  f"--resume {path.name} continues")
            break
        c = candidates[k]
        calls += 1
        if args.judge_cli == "claude":
            ok, why, cost = run.judge(c["criterion"], c["graded"])
            spent += cost or 0.0
            verdict = {True: "PASS", False: "FAIL"}.get(ok, "ERROR")
        else:
            v, why, t = codex_judge(c["criterion"], c["graded"], flags, args.ambiguous)
            tokens += t
            verdict = v or "ERROR"
        out.append({"key": k, "judge": verdict, "why": why, "criterion_sha": c["criterion_sha"]})
        write_jsonl(path, out)                       # a cut run keeps what it paid for
        print(f"  {calls:3}/{len(keys)} {verdict:7} {k}", flush=True)
    write_jsonl(path, out)
    print(f"{path} · {len(out)} verdicts ({calls} new) · " +
          (f"${spent:.2f}" if args.judge_cli == "claude" else f"{tokens:,} tokens"))
    return 0


def cmd_report(args) -> int:
    side = {c["key"]: c["split"] for c in read_jsonl(CANDIDATES)}
    rows_h = read_jsonl(HUMAN)
    excluded = [r for r in rows_h if r.get("excluded")]
    human = {r["key"]: dict(r, split=side.get(r["key"], r.get("split"))) for r in rows_h
             if not r.get("excluded")}
    if excluded:
        print(f"{len(excluded)} label(s) excluded: " +
              "; ".join(f"{r['key']} ({r['excluded']})" for r in excluded))
    files = [Path(f) for f in args.rejudge] or sorted(LABELS.glob("rejudge-*.jsonl"))
    if not files:
        sys.exit("no rejudge file: run `./labels.py rejudge` first")
    for f in files:
        verdicts = {r["key"]: r for r in read_jsonl(f)}
        rows = [{"label": h["label"], "first": h.get("original_label", h["label"]),
                 "judge": verdicts[k]["judge"], "split": h["split"],
                 "stale": verdicts[k]["criterion_sha"] != h["criterion_sha"]}
                for k, h in human.items() if k in verdicts]
        print(f"\n{f.name}")
        for split in ("dev", "holdout", "all"):
            # "all" is honest only while no criterion was tuned on dev: the
            # stale count below says when that stopped being true.
            part = [r for r in rows if split == "all" or r["split"] == split]
            r = rates(part)
            fmt = lambda x: "—" if x is None else f"{x:.2f}"
            print(f"  {split:8} n={len(part):3}  TPR {fmt(r['tpr'])}  TNR {fmt(r['tnr'])}  "
                  f"(tp {r['tp']} fn {r['fn']} tn {r['tn']} fp {r['fp']}, "
                  f"ambiguous {r['ambiguous']}, judge abstained {r['abstained']}, "
                  f"no verdict {r['no_verdict']})")
        # A review that moved labels toward the judges would raise TNR by
        # construction; the first labels are the check on that.
        if any(r["first"] != r["label"] for r in rows):
            r = rates([dict(x, label=x["first"]) for x in rows])
            fmt = lambda x: "—" if x is None else f"{x:.2f}"
            print(f"  {'first':8} n={len(rows):3}  TPR {fmt(r['tpr'])}  TNR {fmt(r['tnr'])}  "
                  f"(all splits, labels as first given, before review)")
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
    p = sub.add_parser("resplit", help="dev/holdout by scenario, keeping every label")
    p.add_argument("--seed", type=int, default=39)
    p.add_argument("--pin-dev", nargs="*", default=[], metavar="ID",
                   help="scenarios whose disagreements were already read")
    p.add_argument("--why", default="", help="recorded next to the pins")
    p = sub.add_parser("add", help="more candidates, likeliest failures first")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--seed", type=int, default=40)
    p.add_argument("--runs", type=Path, default=run.RUNS)
    p.add_argument("--only", default="", metavar="IDS",
                   help="comma-separated scenario ids: add only their samples")
    p.add_argument("--dev", action="store_true",
                   help="new scenarios go to dev: their criterion is being fixed, not scored")
    sub.add_parser("refresh", help="take each scenario's current criterion from scenarios/")
    p = sub.add_parser("page", help="write labels/label.html")
    p.add_argument("--only-stale", action="store_true", help="only labels made against an older criterion")
    p = sub.add_parser("import", help="merge labels exported from the page")
    p.add_argument("file")
    p = sub.add_parser("rejudge", help="judge the labelled samples again (calls the model)")
    p.add_argument("--judge-cli", choices=("claude", "codex"), default="claude")
    p.add_argument("--judge-model", default=run.JUDGE_MODEL)
    p.add_argument("--max-cost-usd", type=float, help="the cap for a claude judge")
    p.add_argument("--max-calls", type=int, help="the cap for a codex judge")
    p.add_argument("--effort", default="medium", help="codex reasoning effort")
    p.add_argument("--ambiguous", action="store_true",
                   help="codex judge may answer AMBIGUOUS; report counts it as an abstention")
    p.add_argument("--all", action="store_true", help="every candidate, labelled or not")
    p.add_argument("--only", default="", metavar="IDS",
                   help="comma-separated scenario ids: judge only their samples")
    p.add_argument("--resume", metavar="FILE",
                   help="a cut run of the same judge: keep its verdicts, judge the rest")
    p = sub.add_parser("report", help="TPR and TNR per split")
    p.add_argument("rejudge", nargs="*")
    args = ap.parse_args()
    return {"pick": cmd_pick, "resplit": cmd_resplit, "add": cmd_add, "refresh": cmd_refresh, "page": cmd_page, "import": cmd_import,
            "rejudge": cmd_rejudge, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
