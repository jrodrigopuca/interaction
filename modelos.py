#!/usr/bin/env python3
"""modelos.py — the charts of MODELOS.md, computed from saved runs.

    ./modelos.py                 # writes img/modelos-totales.svg and img/modelos-agentes.svg

Each model is a list of runs: the branch with the catalog and the branch
without it (`--branch without`). Samples are pooled per branch with
viz.delta_rows, and only the scenarios that BOTH models ran are compared, so a
bar never sets one model's scenario against another's. When a new snapshot is
taken, add its runs to MODELS and run this again; the old charts are replaced,
the old numbers stay in MODELOS.md as text.

Standard library only (plus the harness's own viz.py and run.py).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import viz  # noqa: E402

# Snapshot of 2026-10-21. Sonnet: B-038 (catalog e2cca79). Haiku: B-088 (1c43523).
MODELS = {
    "Sonnet 5.5": ["20261020-193010", "20261020-193738", "20261020-200125", "20261020-200810",
                   "20261020-201059", "20261020-201340", "20261020-201530", "20261020-202121"],
    "Haiku 5.5": ["20261021-210614", "20261021-211510", "20261021-214451", "20261021-211653",
                  "20261021-212403", "20261021-212944", "20261021-213528", "20261021-213648",
                  "20261021-213825"],
}
# Criteria rewritten between the two snapshots (B-038, review before stark):
# their Sonnet verdicts were judged on the old wording, so they are not compared.
EXCLUDE = {"eng-manager-resolves-specialist-conflict",
           "senior-dev-fixes-unreproducible-bug-as-hypothesis",
           "eng-manager-handles-missing-agent"}
COLORS = {"Sonnet 5.5": "#3b6fd4", "Haiku 5.5": "#d4843b"}
INK, MUTED, GRID, BG = "#1f2328", "#59636e", "#d0d7de", "#ffffff"
FONT = "font-family='-apple-system,Segoe UI,Helvetica,Arial,sans-serif'"


def rows_of(runs: list) -> dict:
    d = viz.delta_rows([viz.load_run(ROOT / "runs" / r) for r in runs])
    return {r["id"]: r for r in d["rows"]
            if r["delta"] is not None and r["kept"] != "design-cell" and r["id"] not in EXCLUDE}


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def svg(width: int, height: int, body: str) -> str:
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
            f"viewBox='0 0 {width} {height}' {FONT}>"
            f"<rect width='100%' height='100%' fill='{BG}'/>{body}</svg>\n")


def legend(x: int, y: int) -> str:
    out = ""
    for i, (name, color) in enumerate(COLORS.items()):
        out += (f"<rect x='{x + i * 130}' y='{y - 10}' width='12' height='12' rx='2' fill='{color}'/>"
                f"<text x='{x + i * 130 + 18}' y='{y}' font-size='13' fill='{INK}'>{name}</text>")
    return out


def totals_chart(data: dict, n: int) -> str:
    """Pass rate with and without the catalog, one pair of bars per model."""
    w, h, left, top, plot_h = 560, 330, 60, 60, 210
    groups = [("Sin catálogo", "sin"), ("Con catálogo", "con")]
    body = (f"<text x='{left}' y='28' font-size='16' font-weight='600' fill='{INK}'>"
            f"Tasa de aciertos ({n} escenarios comunes)</text>{legend(left, 50)}")
    for pct in (0, 25, 50, 75, 100):
        y = top + plot_h - pct / 100 * plot_h
        body += (f"<line x1='{left}' y1='{y}' x2='{w - 20}' y2='{y}' stroke='{GRID}'/>"
                 f"<text x='{left - 8}' y='{y + 4}' font-size='11' fill='{MUTED}' text-anchor='end'>{pct}%</text>")
    slot = (w - 20 - left) / len(groups)
    for gi, (label, key) in enumerate(groups):
        gx = left + gi * slot
        for mi, (model, rows) in enumerate(data.items()):
            v = mean([r[key] for r in rows.values()])
            bw = 70
            x = gx + slot / 2 - bw - 4 + mi * (bw + 8)
            bh = v * plot_h
            body += (f"<rect x='{x:.1f}' y='{top + plot_h - bh:.1f}' width='{bw}' height='{bh:.1f}' rx='3' fill='{COLORS[model]}'/>"
                     f"<text x='{x + bw / 2:.1f}' y='{top + plot_h - bh - 6:.1f}' font-size='12' fill='{INK}' text-anchor='middle'>{v:.0%}</text>")
        body += f"<text x='{gx + slot / 2:.1f}' y='{top + plot_h + 22}' font-size='13' fill='{INK}' text-anchor='middle'>{label}</text>"
    return svg(w, h, body)


def agents_chart(data: dict) -> str:
    """Contribution of the catalog per agent, horizontal bars, one per model."""
    agents = {}
    for model, rows in data.items():
        for r in rows.values():
            agents.setdefault(r["agent"], {}).setdefault(model, []).append(r["delta"])
    order = sorted(agents, key=lambda a: (-mean(agents[a].get("Sonnet 5.5", [])), a))
    row_h, bar_h, left, top, plot_w = 34, 12, 150, 70, 380
    w, h = left + plot_w + 70, top + len(order) * row_h + 30
    body = (f"<text x='20' y='28' font-size='16' font-weight='600' fill='{INK}'>"
            f"Aporte del catálogo por agente (puntos de aciertos)</text>{legend(left, 52)}")
    for pct in (0, 25, 50, 75, 100):
        x = left + pct / 100 * plot_w
        body += (f"<line x1='{x}' y1='{top - 6}' x2='{x}' y2='{h - 26}' stroke='{GRID}'/>"
                 f"<text x='{x}' y='{h - 10}' font-size='11' fill='{MUTED}' text-anchor='middle'>+{pct}</text>")
    for i, a in enumerate(order):
        y = top + i * row_h
        n = max(len(v) for v in agents[a].values())
        body += (f"<text x='{left - 10}' y='{y + bar_h + 4}' font-size='13' fill='{INK}' text-anchor='end'>{a}</text>"
                 f"<text x='{left - 10}' y='{y + bar_h + 18}' font-size='10' fill='{MUTED}' text-anchor='end'>{n} esc.</text>")
        for mi, model in enumerate(data):
            v = max(0.0, mean(agents[a].get(model, [])))
            bw = v * plot_w
            by = y + mi * (bar_h + 3)
            body += (f"<rect x='{left}' y='{by}' width='{max(bw, 1.5):.1f}' height='{bar_h}' rx='2' fill='{COLORS[model]}'/>"
                     f"<text x='{left + bw + 6:.1f}' y='{by + bar_h - 2}' font-size='11' fill='{INK}'>+{v * 100:.0f}</text>")
    return svg(w, h, body)


def main() -> int:
    data = {m: rows_of(runs) for m, runs in MODELS.items()}
    common = set.intersection(*(set(r) for r in data.values()))
    data = {m: {i: r for i, r in rows.items() if i in common} for m, rows in data.items()}
    out = ROOT / "img"
    out.mkdir(exist_ok=True)
    (out / "modelos-totales.svg").write_text(totals_chart(data, len(common)))
    (out / "modelos-agentes.svg").write_text(agents_chart(data))
    for m, rows in data.items():
        con, sin = mean([r["con"] for r in rows.values()]), mean([r["sin"] for r in rows.values()])
        print(f"  {m}: {len(rows)} escenarios · con {con:.0%} · sin {sin:.0%} · aporte {con - sin:+.0%}")
    print(f"  → {out / 'modelos-totales.svg'}\n  → {out / 'modelos-agentes.svg'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
