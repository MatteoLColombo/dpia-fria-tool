"""Visual layer that the Streamlit theme (.streamlit/config.toml) cannot express: card surfaces,
sidebar navigation, question rows, the outcome banner and the severity × probability matrix."""

from __future__ import annotations

from html import escape

from digcon.domain.enums import Outcome, Probability, RiskLevel, Severity, label

# Outcome levels are recommendation levels, not pass/fail: one hue each, never red/green alone.
OUTCOME_COLOUR = {Outcome.O1: "green", Outcome.O2: "blue", Outcome.O3: "orange", Outcome.O4: "violet", Outcome.O5: "red"}
_OUTCOME_TINT = {  # banner ground, ink
    Outcome.O1: ("#E8F4EE", "#14532D"),
    Outcome.O2: ("#E8EFFC", "#173F95"),
    Outcome.O3: ("#FDF0E1", "#7C3A06"),
    Outcome.O4: ("#F1EBFB", "#4B2A8C"),
    Outcome.O5: ("#FCEBEA", "#7F1D16"),
}
# One sequential ramp for risk intensity (matrix cells), light to dark.
RISK_RAMP = {
    RiskLevel.VERY_LOW: ("#FFF7EC", "#5A3A12"),
    RiskLevel.LOW: ("#FEE7C8", "#5A3A12"),
    RiskLevel.MODERATE: ("#FBC98E", "#4A2A06"),
    RiskLevel.HIGH: ("#F08A3E", "#3B1A02"),
    RiskLevel.VERY_HIGH: ("#B5480F", "#FFFFFF"),
}

CSS = """
<style>
/* Browser surfaces */
::selection { background: #CFE0FF; color: #18202F; }
section[data-testid="stMain"] :is(button, input, textarea, [role="combobox"], a):focus-visible {
    outline: 2px solid #1F5EDB; outline-offset: 2px;
}
[data-testid="stMetricValue"], [data-testid="stDataFrame"], .digcon-count { font-variant-numeric: tabular-nums; }

/* Header: the app name is a quiet line, the section heading leads */
.st-key-disclaimer p, .st-key-apphead .stCaption p { font-size: 0.86rem; max-width: none !important; }

/* Canvas */
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1180px; }
h1, h2, h3 { letter-spacing: -0.01em; }
.stMarkdown p, .stCaption p { max-width: 78ch; }

/* Cards: every bordered container is a white surface on the canvas */
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"]) {
    background: #FFFFFF;
}
section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] { background: #16243F; }

/* Sidebar navigation */
section[data-testid="stSidebar"] .stButton button {
    justify-content: flex-start; text-align: left; min-height: 2.15rem; padding: 0.3rem 0.75rem;
    border: none; background: transparent; color: #D7DEEA;
}
section[data-testid="stSidebar"] .stButton button > div { justify-content: flex-start; }
section[data-testid="stSidebar"] .stButton button:hover { background: #1F3052; color: #FFFFFF; }
section[data-testid="stSidebar"] .stButton button[kind="primary"] { background: #24406F; color: #FFFFFF; }
section[data-testid="stSidebar"] .stButton button p { font-size: 0.92rem; }
section[data-testid="stSidebar"] .stButton button:focus-visible { outline: 2px solid #7FAEFF; outline-offset: 1px; }
section[data-testid="stSidebar"] [data-testid="stDownloadButton"] button {
    border: 1px solid #3A5383; background: #1F3052; color: #FFFFFF; justify-content: center;
}
.digcon-brand { font-weight: 700; font-size: 1.05rem; color: #FFFFFF; letter-spacing: 0.01em; margin: 0; }
.digcon-brand-sub { font-size: 0.8rem; color: #9AA7BD; margin: 0 0 0.6rem 0; }
.digcon-step { font-size: 0.72rem; font-weight: 650; letter-spacing: 0.07em; text-transform: uppercase;
               color: #9AA7BD; margin: 1.05rem 0 0.2rem 0.75rem; }

/* Question rows */
.digcon-q { font-weight: 600; font-size: 0.98rem; margin: 0.15rem 0 0.25rem 0; line-height: 1.4; }
.digcon-q code { font-weight: 500; font-size: 0.75rem; margin-left: 0.35rem; }
hr.digcon-rule { border: none; border-top: 1px solid #E4E9F0; margin: 0.9rem 0 0.7rem 0; }

/* Answer controls: the chosen answer reads at a glance */
[data-testid="stButtonGroup"] button[data-selected="true"]:not(:disabled) {
    background: #1F5EDB !important; border-color: #1F5EDB !important; color: #FFFFFF !important;
}
[data-testid="stButtonGroup"] button[data-selected="true"]:not(:disabled) p { color: #FFFFFF !important; }

/* 2.0: the case that applies */
.st-key-route_active { background: #E8EFFC; border: 1px solid #B9CCF5; border-radius: 8px; padding: 0.6rem 0.8rem; }

/* Confirm on a check set by the API: light green, same weight as the other buttons */
[class*="st-key-api-ok-"] button { background: #E8F4EE; color: #1F7A4D; border: 1px solid #B9DCC8; }
[class*="st-key-api-ok-"] button:hover { background: #D6ECDF; color: #14532D; border-color: #8FC6A6; }
[class*="st-key-api-ok-"] button p, [class*="st-key-api-ok-"] button span { color: inherit; }

/* Outcome banner */
.digcon-outcome { border-radius: 8px; padding: 1.1rem 1.25rem; margin: 0.2rem 0 0.6rem 0; }
.digcon-outcome .ttl { font-size: 1.45rem; font-weight: 650; margin: 0.15rem 0 0.35rem 0; }
.digcon-outcome .txt { font-size: 0.95rem; margin: 0; max-width: 80ch; }

/* Open-item counters */
.digcon-counters { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.5rem; margin: 0.4rem 0 0.9rem 0; }
.digcon-counters .cnt { background: #FFFFFF; border: 1px solid #D5DCE6; border-radius: 8px; padding: 0.55rem 0.8rem;
    font-size: 0.82rem; color: #3A4456; display: flex; align-items: baseline; gap: 0.5rem; }
.digcon-counters .cnt .digcon-count { font-size: 1.35rem; font-weight: 650; color: #18202F; }
.digcon-counters .cnt.zero, .digcon-counters .cnt.zero .digcon-count { color: #5B6576; font-weight: 400; }

/* Risk matrix */
table.digcon-matrix { border-collapse: separate; border-spacing: 4px; width: 100%; font-size: 0.85rem; }
div.digcon-matrix-wrap { overflow-x: auto; }
table.digcon-matrix { min-width: 560px; }
table.digcon-matrix th { font-weight: 600; color: #5B6576; text-align: center; padding: 0.3rem;
    border: none !important; background: transparent !important; }
table.digcon-matrix th.row { text-align: right; white-space: nowrap; }
table.digcon-matrix td { border: none !important; border-radius: 6px; padding: 0.45rem; vertical-align: top; height: 3.4rem; }
table.digcon-matrix td .lvl { font-size: 0.7rem; font-weight: 650; letter-spacing: 0.04em; }
table.digcon-matrix caption { caption-side: top; text-align: left; font-size: 0.8rem; color: #5B6576; padding-bottom: 0.2rem; }
table.digcon-matrix td .chip { display: inline-block; margin: 0.2rem 0.2rem 0 0; padding: 0.05rem 0.4rem;
    border-radius: 4px; background: #FFFFFF; color: #18202F; font-size: 0.75rem; font-weight: 600;
    border: 1px solid #18202F; }
table.digcon-matrix td .chip.res { border-style: dashed; background: transparent; }
table.digcon-matrix td.hi .chip.res { color: #FFFFFF; border-color: #FFFFFF; }
</style>
"""


def outcome_banner(outcome: Outcome, title: str, text: str) -> str:
    ground, ink = _OUTCOME_TINT[outcome]
    return (
        f'<div class="digcon-outcome" style="background:{ground};color:{ink}">'
        f'<div class="ttl">Recommended outcome: {escape(title)}</div><p class="txt">{escape(text)}</p></div>'
    )


def position_banner(ocode: str, title: str, text: str) -> str:
    """Overall position of the assessment (RA-1), tinted as the export code it maps to."""
    ground, ink = _OUTCOME_TINT[Outcome(ocode)]
    return (
        f'<div class="digcon-outcome" style="background:{ground};color:{ink}">'
        f'<div class="ttl">Overall position: {escape(title)}</div><p class="txt">{escape(text)}</p></div>'
    )


def counters(items: list[tuple[str, int]]) -> str:
    """One row of open-item counts; zeros recede so the open count leads."""
    cells = "".join(
        f'<div class="cnt{" zero" if n == 0 else ""}"><span class="digcon-count">{n}</span>{escape(name)}</div>'
        for name, n in items
    )
    return f'<div class="digcon-counters">{cells}</div>'


def question_title(text: str, qid: str) -> str:
    code = f"<code>{escape(qid)}</code>" if qid else ""
    return f'<p class="digcon-q">{escape(text)}{code}</p>'


RULE = '<hr class="digcon-rule">'


def risk_matrix(points: dict[str, tuple[Severity | None, Probability | None, Severity | None, Probability | None]],
                matrix: dict[Severity, dict[Probability, RiskLevel]]) -> str:
    """Severity rows (high at the top) × probability columns. Solid chip = initial, dashed = residual."""
    probs = list(Probability)
    head = "".join(f"<th>{escape(label(p))}</th>" for p in probs)
    rows = []
    for sev in reversed(list(Severity)):
        cells = []
        for p in probs:
            lvl = matrix[sev][p]
            ground, ink = RISK_RAMP[lvl]
            chips = "".join(
                f'<span class="chip">{escape(r)}</span>' for r, (s, pr, _, _) in points.items() if s is sev and pr is p
            ) + "".join(
                f'<span class="chip res" title="residual">{escape(r)} res.</span>'
                for r, (_, _, rs, rp) in points.items() if rs is sev and rp is p
            )
            hi = ' class="hi"' if lvl is RiskLevel.VERY_HIGH else ""
            cells.append(f'<td{hi} style="background:{ground};color:{ink}"><div class="lvl">{escape(label(lvl))}</div>{chips}</td>')
        rows.append(f'<tr><th class="row">{escape(label(sev))}</th>{"".join(cells)}</tr>')
    return (
        f'<div class="digcon-matrix-wrap"><table class="digcon-matrix"><caption>Rows: severity · Columns: probability</caption>'
        f'<thead><tr><th class="row">Severity</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )
