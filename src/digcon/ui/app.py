"""Streamlit app: header, step-by-step navigation (00_MAPPA_FLUSSO), live engine result.

Step 1 is the common core, step 2 the add-ons opened by the scoping answers, step 3 the
transversal modules, step 4 the recommended outcome and the governance decision. The
left rail lists every section of every step with its status, the current outcome and
whether the work is saved.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import streamlit as st

from digcon.config import default_config
from digcon.domain.enums import Phase
from digcon.engine import EngineResult, InvalidAssessment, RunContext, run_engine

from . import api_mode, bridge, state
from .labels import (
    APP_CAPTION,
    APP_TITLE,
    DISCLAIMER,
    FOOTER,
    GOVERNANCE_TITLE,
    METHODOLOGY,
    MITIGATION_TITLE,
    NAV_LABELS,
    OUTCOME_TITLES,
    PHASE_TITLES,
    RESULT_TITLE,
    REVIEW_TITLE,
    RISKS_TITLE,
    ROUTING_TITLE,
    RULES_TITLE,
    SEP_TITLE,
    START_TITLE,
    STEP_ADDONS,
    STEP_ANALYSIS,
    STEP_CORE,
    STEP_OUTCOME,
    STEP_TEXT,
)
from .pages import mitigation, questionnaire, result, review, risks, routing, sep, start
from .style import CSS, OUTCOME_COLOUR

NAV = state.NAV
RESTORED = "restored_from_browser"
SIDEBAR_WIDTH = 368  # px: section labels and their status on one line


@st.cache_resource
def _config():
    return default_config()


def _phase_page(phase: Phase):
    return lambda cfg, res: questionnaire.render(cfg, res, phase)


def _steps() -> dict[str, list[tuple[str, object]]]:
    """Step -> [(section title, render function)], in protocol order."""
    return {
        STEP_CORE: [(START_TITLE, start.render)]
        + [(PHASE_TITLES[p], _phase_page(p)) for p in (Phase.INTRO, Phase.WHAT, Phase.HOW, Phase.WHY)],
        STEP_ADDONS: [
            (ROUTING_TITLE, routing.render),
            (PHASE_TITLES[Phase.PROVIDER], _phase_page(Phase.PROVIDER)),
            (PHASE_TITLES[Phase.DEPLOYER], _phase_page(Phase.DEPLOYER)),
        ],
        STEP_ANALYSIS: [
            (SEP_TITLE, sep.render),
            (RISKS_TITLE, risks.render),
            (RULES_TITLE, review.render_rules),
            (MITIGATION_TITLE, mitigation.render),
            (REVIEW_TITLE, review.render_hard_stops),
        ],
        STEP_OUTCOME: [(RESULT_TITLE, result.render), (GOVERNANCE_TITLE, result.render_governance)],
    }


def step_of(title: str) -> str:
    return next(step for step, items in _steps().items() if title in [t for t, _ in items])


_go = state.go


def _progress(cfg, res: EngineResult | None) -> tuple[dict[str, str], dict[str, tuple[int, int]]]:
    """Per-section status mark (markdown) and per-step (answered, visible) question counts."""
    if res is None:
        return {}, {}
    answers = state.store()["answers"]
    visible = set(res.visible_questions)
    marks: dict[str, str] = {}
    counts: dict[str, tuple[int, int]] = {STEP_CORE: (0, 0), STEP_ADDONS: (0, 0)}
    for phase in Phase:
        ids = [q.id for q in cfg.questions.questions if q.phase is phase and q.id in visible]
        title = PHASE_TITLES[phase]
        locked = (phase is Phase.PROVIDER and not res.provider_module) or (phase is Phase.DEPLOYER and not ids)
        if locked:
            marks[title] = ":gray-badge[:material/lock: Closed]"
            continue
        done = sum(1 for q in ids if q in answers)
        marks[title] = ":green-badge[:material/check: Complete]" if done == len(ids) else f":gray-badge[{done} / {len(ids)}]"
        step = STEP_CORE if phase in (Phase.INTRO, Phase.WHAT, Phase.HOW, Phase.WHY) else STEP_ADDONS
        a, v = counts[step]
        counts[step] = (a + done, v + len(ids))
    store = state.store()
    marks[START_TITLE] = ":gray-badge[New]" if state.save_status(cfg) == "empty" else ":blue-badge[Started]"
    marks[ROUTING_TITLE] = (
        ":orange-badge[Suspended]" if res.routing_suspended
        else f":blue-badge[{res.role.title()}]" if res.role and res.high_risk == "YES"
        else ":gray-badge[Core only]" if res.high_risk == "NO" else ":gray-badge[No route yet]"
    )
    sep_filled = len(store["sep"].get("texts", {})) + sum(
        1 for a in ("decision", "vulnerability", "effect", "new_risk", "new_mitigation") if store["sep"].get(a))
    marks[SEP_TITLE] = f":gray-badge[{sep_filled} / {len(cfg.sep.fields)}]"
    marks[RISKS_TITLE] = f":gray-badge[{len(store['risks'])} in register]"
    marks[RULES_TITLE] = (f":gray-badge[{len(res.verification_requests)} to verify]" if res.verification_requests
                          else ":green-badge[:material/check: Nothing to verify]")
    marks[MITIGATION_TITLE] = f":gray-badge[{sum(1 for m in store['mitigations'].values() if m.get('activated'))} activated]"
    opened = sum(1 for h in res.hard_stops.values() if h.opened)
    marks[REVIEW_TITLE] = f":orange-badge[{opened} open]" if opened else ":gray-badge[None open]"
    marks[RESULT_TITLE] = f":{OUTCOME_COLOUR[res.outcome]}-badge[{res.outcome.value}]"
    marks[GOVERNANCE_TITLE] = ":green-badge[Recorded]" if store["governance"].get("g01_decision") else ":gray-badge[To record]"
    return {k: v for k, v in marks.items() if v}, counts


def _save_block(cfg) -> None:
    status = state.save_status(cfg)
    if status == "empty":
        st.markdown(":gray[:material/draft: **Nothing entered yet**]")
    else:
        file_note = ("Matches your last downloaded file." if status == "saved"
                     else "Download a file to keep a copy outside this browser.")
        st.markdown(f":green[:material/history: **Autosaved in this browser**]  \n:gray[{file_note}]")
    start.save_button("rail", width="stretch")


def _menu(cfg, steps: dict[str, list], res: EngineResult | None, marks: dict[str, str], counts) -> None:
    current = st.session_state[NAV]
    with st.sidebar:
        st.markdown('<p class="digcon-brand">DIGCON</p><p class="digcon-brand-sub">Fundamental Rights Assessment</p>',
                    unsafe_allow_html=True)
        if api_mode.active():
            st.markdown(":blue-badge[:material/smart_toy: API mode]")
        with st.container(border=True):
            if res is not None:
                st.markdown(f":{OUTCOME_COLOUR[res.outcome]}-badge[{OUTCOME_TITLES[res.outcome]}]")
                st.caption(
                    f"{len(res.evidence_gaps)} evidence gaps · {len(res.open_remediations)} remediations · "
                    f"{len(res.verification_requests)} to verify"
                )
            _save_block(cfg)
        for n, (step, items) in enumerate(steps.items(), 1):
            st.markdown(f'<div class="digcon-step">Step {n} · {step.split(" — ", 1)[1]}</div>', unsafe_allow_html=True)
            answered, total = counts.get(step, (0, 0))
            if total:
                st.progress(answered / total, text=f"{answered} of {total} questions answered")
            for title, _ in items:
                label = NAV_LABELS[title] + (f"  {marks[title]}" if title in marks else "")
                st.button(
                    label,
                    key=f"nav.{title}",
                    on_click=_go,
                    args=(title,),
                    type="primary" if title == current else "secondary",
                    width="stretch",
                )


def _restore(cfg, stored: dict) -> None:
    """First run after a reload: reopen the last section and bring back the browser copy plus unsent text."""
    if stored.get("nav") in {t for items in _steps().values() for t, _ in items}:
        st.session_state[NAV] = stored["nav"]
    if state.save_status(cfg) != "empty":
        return
    drafts = stored.get("drafts") if isinstance(stored.get("drafts"), dict) else {}
    if not stored.get("assessment") and not drafts:
        return
    try:
        data = state.parse_upload(stored["assessment"].encode("utf-8")) if stored.get("assessment") else state.empty_store(cfg)
        bridge.apply_drafts(cfg, data, drafts, result.GOVERNANCE_FIELDS, set(sep.ENUM_FIELDS))
        state.replace(data, from_file=False)
    except ValueError:
        return  # an unreadable browser copy is ignored; the next answer overwrites it
    st.session_state[RESTORED] = True
    st.rerun()


def _header() -> None:
    title_col, method_col = st.columns([5, 1], vertical_alignment="bottom")
    with title_col, st.container(key="apphead"):
        st.title(APP_TITLE)
        st.caption(APP_CAPTION)
    with method_col, st.popover("Methodology", icon=":material/menu_book:", width="stretch"):
        st.markdown(METHODOLOGY)
    with st.container(border=True, key="disclaimer"):
        st.markdown(DISCLAIMER)


def _pager(titles: list[str], current: str) -> None:
    i = titles.index(current)
    st.space("small")
    prev_col, _, next_col = st.columns([2, 3, 2])
    if i > 0:
        prev_col.button(NAV_LABELS[titles[i - 1]], on_click=_go, args=(titles[i - 1],), key="nav.prev", width="stretch",
                        icon=":material/arrow_back:")
    if i < len(titles) - 1:
        next_col.button(
            NAV_LABELS[titles[i + 1]], on_click=_go, args=(titles[i + 1],), key="nav.next", type="primary", width="stretch",
            icon=":material/arrow_forward:", icon_position="right",
        )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state=SIDEBAR_WIDTH)
    st.markdown(CSS, unsafe_allow_html=True)
    _header()

    cfg = _config()
    state.init(cfg)
    stored = bridge.sync(None if state.save_status(cfg) == "empty" else state.to_json(), st.session_state.get(NAV) or START_TITLE)
    if stored:
        _restore(cfg, stored)
    if st.session_state.pop(RESTORED, False):
        st.toast("Answers restored from this browser's autosave.", icon=":material/history:")
    api_mode.activate_from_link()
    if st.session_state.get(NAV) in (RULES_TITLE, RESULT_TITLE) and api_mode.refresh(cfg):
        st.rerun()  # the next run autosaves the values the API just set
    try:
        res = run_engine(
            cfg,
            state.assessment(),
            RunContext(run_id=uuid.uuid4().hex[:12], timestamp=datetime.now(timezone.utc)),
        )
    except InvalidAssessment as exc:
        res = None
        st.error(
            "The outcome cannot be calculated: this assessment contains values that are not allowed answers ("
            + "; ".join(exc.errors)
            + "). Load a different saved file or start a new assessment in section 1.0."
        )

    steps = _steps()
    sections = {title: render for items in steps.values() for title, render in items}
    titles = list(sections)
    if st.session_state.get(NAV) not in titles:
        st.session_state[NAV] = titles[0]
    marks, counts = _progress(cfg, res)
    _menu(cfg, steps, res, marks, counts)
    current = st.session_state[NAV]
    step = step_of(current)

    st.header(current)
    if current == steps[step][0][0]:
        st.markdown(STEP_TEXT[step])
    if current in (RULES_TITLE, RESULT_TITLE):
        api_mode.notice()
    if res is not None or current == START_TITLE:
        sections[current](cfg, res)
    _pager(titles, current)
    st.divider()
    st.caption(FOOTER)
