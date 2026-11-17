"""Sections 3.3 (rules and scrutiny: reviewer checks, legal reviews) and 3.5 (hard stop gate, HS01–HS10)."""

from __future__ import annotations

import streamlit as st

from digcon.domain.enums import ElementSource, RuleElementState
from digcon.domain.models import ConfigBundle
from digcon.engine import EngineResult

from .. import renderer, state
from ..labels import workbook_text
from digcon.domain.action_plan import title
from digcon.domain.review_progress import stop_progress
from ..review_language import PROBLEMS, FACTS


def render_hard_stops(cfg: ConfigBundle, result: EngineResult) -> None:
    recorded_gates = set(state.store()["human_gates"])
    st.markdown(
        "Review each question against the evidence. A stop condition is confirmed only when all its "
        "required facts are established and a reasoned legal review is recorded. Uncertainty is not confirmation. "
        "A mitigation plan cannot remove a confirmed stop condition: changed facts require a new legal determination."
    )
    st.caption("Colours concern individual checks, not permission to proceed. Blue identifies a neutral fact; "
               "green means only that the particular problem was not identified.")
    from digcon import argument as ra
    current = state.assessment()
    positions = ra.read(current, cfg, result)
    referred = [i for i in positions.system + [x for p in positions.rights.values() for x in p.items]
                if i.position in (ra.STOP_PENDING, ra.STOP_CONFIRMED, ra.STOP_EXCLUDED) and i.scope != "WORKBOOK"]
    if referred:
        with st.container(border=True):
            st.markdown("**Raised by the argument (3.4–3.5)**")
            for i in referred:
                where = "the use as a whole" if i.scope == "SYSTEM" else cfg.argument.right(i.scope).title
                st.caption(f"• {where} — {i.text}")
    raised = ra.referred_stops(current, cfg)
    pending = sum(stop_progress(hs)[1] or (h in raised and hs.gate.value != "COMPLETED") for h, hs in result.hard_stops.items())
    st.caption(f"{pending} stop checks need attention")
    show_all = st.checkbox("Show completed and unopened checks", key="w.hs.show_all")
    ordered = sorted(result.hard_stops.items(), key=lambda pair: not stop_progress(pair[1])[1])
    for hs_id, hs in ordered:
        spec = cfg.rule(hs_id)
        status, needs_attention = stop_progress(hs)
        if hs_id in raised and hs.gate.value != "COMPLETED":
            status, needs_attention = "🟡 Raised by the argument — reviewer decision needed", True
        if not needs_attention and not show_all:
            continue
        with st.expander(f"{title(hs_id)} · {status}", expanded=needs_attention):
            if hs.state is RuleElementState.UNCERTAIN:
                uncertain = [eid for eid, value in hs.elements.items() if value is RuleElementState.UNCERTAIN]
                if uncertain:
                    st.markdown("**Information to establish:**")
                    for eid in uncertain:
                        st.write("• " + PROBLEMS.get(eid, FACTS.get(eid, eid)))
                if hs.gate.value != "COMPLETED":
                    st.caption("Next: assess the facts and record the reasoned reviewer decision below.")
                else:
                    st.caption("The review is recorded, but the facts above remain uncertain. Update their evidence before concluding.")
            with st.expander("Technical rule details"):
                st.caption(f"{hs_id}: {workbook_text(hs_id, 'trigger_text', spec.trigger_text)}")
                st.caption(f"Remediability: {spec.remediability}")
            for el in spec.encoding.elements:
                renderer.element(el, hs.elements[el.id].value)
            if hs.opened or hs_id in recorded_gates or hs_id in raised:
                renderer.legal_gate(hs_id)
            if hs.awaiting_legal_review:
                st.warning("All required facts are established. A reasoned legal decision is still needed to confirm this stop condition.")


def render_rules(cfg: ConfigBundle, result: EngineResult) -> None:
    recorded_gates = set(state.store()["human_gates"])
    st.subheader("Reviewer checks")
    st.caption("Suitability, necessity, safeguards and balancing are no longer checked here: they are steps of the "
               "argument per right (3.4–3.6).")
    st.caption("Red: this problem is present. Green: this particular problem is not identified. "
               "Yellow: more information is needed. Blue: a neutral fact is confirmed. "
               "These colours record your judgement; they do not certify compliance or evidence adequacy.")
    st.caption(
        "Qualitative judgements the tool cannot draw from your answers: record them here. "
        "A check left as 'Not evaluated' is listed as to be verified and does not change the outcome."
    )
    suggested = [
        eid for eid, rec in state.store()["elements"].items()
        if rec.get("source") == "API" and cfg.rule(eid.split(".", 1)[0]).family not in ("HS", "PROP")
    ]
    if suggested:
        with st.container(border=True):
            st.markdown(f"**{len(suggested)} checks were filled automatically.** Each one must be checked: "
                        "confirm or clear it below (its reason is shown under it).")
    to_verify = {f.rule_id for f in result.verification_requests}
    for spec in cfg.rules.rules:
        manual = [e for e in spec.encoding.elements if e.source is ElementSource.MANUAL]
        if spec.family in ("HS", "PROP") or not manual:  # PROP-*: absorbed by the argument (3.4-3.6)
            continue
        mark = " · to be verified" if spec.id in to_verify else ""
        by_api = any(e.id in suggested for e in manual)
        with st.expander(f"{title(spec.id)}{mark}" + (" :blue-badge[Set by API]" if by_api else ""), expanded=by_api):
            with st.expander("Technical rule details"):
                st.caption(f"{spec.id}: {workbook_text(spec.id, 'trigger_text', spec.trigger_text)}")
            for el in manual:
                renderer.element(el)

    st.subheader("Legal reviews")
    pending = [f.rule_id for f in result.pending_reviews if cfg.rule(f.rule_id).family not in ("HS", "PROP")]
    done = [r for r in recorded_gates if cfg.rule(r).family not in ("HS", "PROP") and r not in pending]
    if not pending and not done:
        st.caption("No legal review pending outside the stop conditions (3.8).")
    for rid in pending + done:
        st.markdown(f"**{title(rid)}**")
        with st.expander("Technical rule details"):
            st.caption(f"{rid}: {workbook_text(rid, 'trigger_text', cfg.rule(rid).trigger_text)}")
        renderer.legal_gate(rid)

    scrutiny = sorted(r for r, rr in result.rules.items() if rr.fired and any(e.value == "SCRUTINY" for e in rr.effects))
    st.subheader("Scrutiny")
    if scrutiny:
        st.markdown("Higher scrutiny raised by: **" + "; ".join(title(r) for r in scrutiny) + "**. Scrutiny never produces an outcome by itself.")
    else:
        st.caption("No rule raises scrutiny.")
