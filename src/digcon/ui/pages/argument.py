"""Step 3 sections 3.4–3.6: the rights argument (RA-1).

3.4 screening of every right of the register, and the steps that concern the use as a whole (A1–A3);
3.5 the argument for each engaged right (B1–B6, open points);
3.6 the steps across rights (C1–C2) and the positions at a glance.

Each step is a determination with reasons, sources, evidence, an optional dissent, and the name and
date of the person who records it. Recording stores what the determination relied on: a later change
to those facts marks it out of date. The tool never weighs and never concludes 'proportionate'.
"""
from __future__ import annotations

import streamlit as st

from digcon import argument as ra
from digcon.domain.enums import MitigationHierarchy, label
from digcon.domain.models import Determination

from .. import state
from ..labels import ARGUMENT_TITLE, CROSS_TITLE, MITIGATION_TITLE, REVIEW_TITLE, RISKS_TITLE, SCREENING_TITLE

EXTRA = {  # step -> [(field, label, help)]
    "B1": [("holders", "Whose right: the holders in this use", "Applicants, claimants, pupils, patients: name them concretely.")],
    "B2": [("persons", "Persons affected and their position towards the deployer",
            "Dependency, no way to opt out, power asymmetry. Link to the groups identified in 1.3.")],
    "B5": [("conditions", "Measures that must stay in place during use",
            "Required when the guarantees are adequate only with conditions. Each becomes a condition of the position.")],
}
FUNCTION = {
    MitigationHierarchy.AVOID: "necessity — avoids or narrows the interference",
    MitigationHierarchy.MITIGATE: "safeguard — reduces likelihood or severity",
    MitigationHierarchy.RESTORE: "remedy — restores the position of the persons affected",
    MitigationHierarchy.COMPENSATE: "remedy — compensates; does not reduce the interference",
}
BADGE = {ra.NOT_ENGAGED: "gray", ra.CLEAR: "green", ra.CONDITIONS: "blue", ra.INCOMPLETE: "violet",
         ra.STOP_EXCLUDED: "violet", ra.REVISION: "orange", ra.STOP_PENDING: "red", ra.STOP_CONFIRMED: "red"}
LIST_FIELDS = ("sources", "evidence")


def badge(position: str) -> str:
    return f":{BADGE[position]}-badge[{ra.LABELS[position]}]"


# -- storage -------------------------------------------------------------------------------


def _bucket(scope: str, create: bool = False) -> dict | None:
    arg = state.store().setdefault("argument", {"schema_version": 1, "system": {}, "rights": {}, "cross": {}})
    if scope == "SYSTEM":
        return arg.setdefault("system", {})
    if scope == "CROSS":
        return arg.setdefault("cross", {})
    rights = arg.setdefault("rights", {})
    if scope not in rights:
        if not create:
            return None
        rights[scope] = {"steps": {}, "open_points": ""}
    return rights[scope].setdefault("steps", {})


def _stored(scope: str, step: str) -> dict:
    bucket = _bucket(scope)
    return dict((bucket or {}).get(step) or {})


def _key(scope, step, field):
    return f"w.arg.{scope}.{step}.{field}"


def _sync(scope: str, step: str) -> None:
    data = _stored(scope, step)
    ss = st.session_state
    for field in ("code", "reasons", *LIST_FIELDS, "dissent", "dissent_by", "author", "date"):
        k = _key(scope, step, field)
        if k not in ss:
            continue
        value = ss[k] or ""
        data[field] = [v.strip() for v in value.splitlines() if v.strip()] if field in LIST_FIELDS else value
    extra = dict(data.get("extra") or {})
    for field, *_ in EXTRA.get(step, []):
        k = _key(scope, step, f"extra.{field}")
        if k in ss:
            extra[field] = ss[k] or ""
    data["extra"] = {k: v for k, v in extra.items() if v}
    record = Determination.model_validate(data).model_dump(mode="json")
    if record == Determination().model_dump(mode="json"):
        (_bucket(scope) or {}).pop(step, None)
        return
    _bucket(scope, create=True)[step] = record


def _record(cfg, scope: str, step: str) -> None:
    _sync(scope, step)
    current = state.assessment()
    rec = ra._record(current, scope, step)
    missing = ra.missing_fields(cfg, step, rec)
    if missing:
        st.session_state[f"arg.msg.{scope}.{step}"] = "Still to complete: " + ", ".join(missing) + "."
        return
    signature = ra.fingerprint(current, cfg, scope, step)
    data = _bucket(scope)[step]
    snapshot = {k: v for k, v in rec.model_dump(mode="json").items() if k != "history"}
    snapshot["fingerprint"] = signature
    data["history"] = [*data.get("history", []), snapshot]
    data["fingerprint"] = signature


# -- one determination ---------------------------------------------------------------------


def status_line(cfg, scope: str, step: str) -> str:
    r = ra.read_step(state.assessment(), cfg, scope, step)
    stored = _stored(scope, step)
    if r.status == ra.CURRENT:
        return ":green-badge[:material/check: Recorded]"
    if r.status == ra.STALE:
        return ":orange-badge[Out of date — the facts changed since it was recorded]"
    if stored.get("fingerprint"):
        return ":orange-badge[Edited — record it again]"
    return ":gray-badge[Not recorded]"


def step_box(cfg, scope: str, step: str) -> None:
    """One step in a collapsible box: open while it needs work, closed once recorded and current."""
    spec = cfg.argument.step(step)
    reading = ra.read_step(state.assessment(), cfg, scope, step)
    opt = spec.option(reading.code) if reading.code else None
    summary = opt.label if (opt and reading.status == ra.CURRENT) else {
        ra.STALE: "out of date", ra.MISSING: "to determine"}.get(reading.status, "")
    mark = "✓" if reading.status == ra.CURRENT else "●"
    with st.expander(f"{mark} {spec.title} — {summary}", expanded=reading.status != ra.CURRENT):
        determination(cfg, scope, step)


def determination(cfg, scope: str, step: str, *, compact: bool = False) -> None:
    spec = cfg.argument.step(step)
    stored = _stored(scope, step)
    st.markdown(f"**{spec.question}**  {status_line(cfg, scope, step)}")
    with st.expander("Guidance for this step"):
        st.markdown(spec.note)
        st.caption(f"Common mistake: {spec.mistake}")
        st.caption(f"Example: {spec.example}")
    codes = [""] + [o.code for o in spec.options]
    names = {"": "Not yet determined", **{o.code: o.label for o in spec.options}}
    state.seed(_key(scope, step, "code"), stored.get("code") or "")
    for field in ("reasons", "dissent", "dissent_by", "author", "date"):
        state.seed(_key(scope, step, field), stored.get(field) or "")
    for field in LIST_FIELDS:
        state.seed(_key(scope, step, field), "\n".join(stored.get(field) or []))
    for field, *_ in EXTRA.get(step, []):
        state.seed(_key(scope, step, f"extra.{field}"), (stored.get("extra") or {}).get(field, ""))
    st.selectbox("Determination", codes, key=_key(scope, step, "code"), format_func=names.get,
                 on_change=_sync, args=(scope, step))
    st.text_area("Reasons", key=_key(scope, step, "reasons"), on_change=_sync, args=(scope, step), height=80,
                 help="Why this determination, in your words. A conclusion without reasons does not complete the step.")
    for field, name, help_ in EXTRA.get(step, []):
        if field == "conditions" and st.session_state[_key(scope, step, "code")] != "ADEQUATE_WITH_CONDITIONS":
            continue
        st.text_area(name, key=_key(scope, step, f"extra.{field}"), help=help_, on_change=_sync, args=(scope, step), height=68)
    if not compact:
        c1, c2 = st.columns(2)
        c1.text_area("Sources — one per line", key=_key(scope, step, "sources"), on_change=_sync, args=(scope, step),
                     height=68, help="Provisions, Charter Explanations, case law, guidance.")
        c2.text_area("Evidence — one per line", key=_key(scope, step, "evidence"), on_change=_sync, args=(scope, step),
                     height=68, help="Documents, tests, stakeholder input, answers in this assessment.")
        with st.expander("Dissent (optional)", expanded=bool(stored.get("dissent"))):
            st.caption("A different view within the team stays on record and is shown in the report. It does not change the position.")
            st.text_area("Dissenting view", key=_key(scope, step, "dissent"), on_change=_sync, args=(scope, step), height=68)
            st.text_input("Author of the dissent", key=_key(scope, step, "dissent_by"), on_change=_sync, args=(scope, step))
    c1, c2, c3 = st.columns([2, 2, 2], vertical_alignment="bottom")
    c1.text_input("Recorded by", key=_key(scope, step, "author"), on_change=_sync, args=(scope, step))
    c2.text_input("Date (YYYY-MM-DD)", key=_key(scope, step, "date"), on_change=_sync, args=(scope, step))
    c3.button("Record this determination", key=f"arg.record.{scope}.{step}", on_click=_record, args=(cfg, scope, step))
    msg = st.session_state.pop(f"arg.msg.{scope}.{step}", None)
    if msg:
        st.warning(msg)
    if stored.get("history"):
        with st.expander(f"Earlier determinations ({len(stored['history'])})"):
            for h in reversed(stored["history"]):
                st.caption(f"{h.get('date')} · {h.get('author')} · {names.get(h.get('code'), h.get('code'))} — {h.get('reasons')}")


# -- 3.4 screening and the use as a whole --------------------------------------------------


def render_screening(cfg, result) -> None:
    st.markdown(
        "Step 3 builds an argument for each right, as a third party could follow and contest it. Start here: decide "
        "which rights of the register the use engages, and determine the three steps that concern the use as a whole. "
        f"The engaged rights are argued in {ARGUMENT_TITLE}."
    )
    st.caption(cfg.argument.meta.disclaimer)
    current = state.assessment()
    positions = ra.read(current, cfg, result)
    st.subheader("Screening of rights")
    st.caption("Every right of the register is screened. A right marked not engaged needs reasons: this is where an "
               "assessment can hide what it does not examine.")
    for card in cfg.argument.rights:
        r = ra.read_step(current, cfg, card.id, "S0")
        code = ra.current_code(current, cfg, card.id, "S0")
        mark = {"ENGAGED": "Engaged", "NOT_ENGAGED": "Not engaged", "UNDETERMINED": "Undetermined"}.get(code, "To screen")
        hint = " · in the risk register" if card.risk_id and card.risk_id in current.risks else ""
        with st.expander(f"{card.title} · {mark}{hint}", expanded=r.status != ra.CURRENT and bool(hint)):
            st.caption(card.protects)
            determination(cfg, card.id, "S0", compact=True)
    st.subheader("The use as a whole")
    st.caption("These steps are determined once. Each right's argument relies on them (B6 weighs the aim as achieved).")
    for step in ra.SYSTEM_STEPS:
        step_box(cfg, "SYSTEM", step)
    engaged = ra.engaged(current, cfg)
    if engaged:
        st.button(f"Continue with the argument for {len(engaged)} engaged right(s)", key="arg.to.rights",
                  on_click=state.go, args=(ARGUMENT_TITLE,), type="primary")
    st.caption("Position of the use as a whole: " + badge(max([i.position for i in positions.system if i.scope == "SYSTEM"],
                                                              key=ra.RANK.get, default=ra.CLEAR)))


# -- 3.5 argument per right ----------------------------------------------------------------


def _card(card) -> None:
    status = ":green-badge[Verified]" if card.status == "VERIFIED" else ":orange-badge[Draft — not yet verified by the research team]"
    with st.expander("About this right " + ("(verified)" if card.status == "VERIFIED" else "(draft guidance)")):
        st.markdown(status)
        st.markdown(f"**What it protects.** {card.protects}")
        st.markdown(f"**Corresponding ECHR provision.** {card.echr}")
        st.markdown(f"**Limitation regime.** {card.regime}")
        st.markdown(f"**Essence.** {card.essence}")
        st.markdown("**Typical interferences in AI uses**\n" + "\n".join(f"- {x}" for x in card.interferences))
        st.markdown("**Questions to ask**\n" + "\n".join(f"- {x}" for x in card.questions))
        st.markdown("**Sources**\n" + "\n".join(f"- {x}" for x in card.sources))
        if card.source_check:
            st.caption(f"Source check: {card.source_check}")
        if card.verified_by:
            st.caption(f"Verified by {card.verified_by} on {card.verified_on}.")


def _evidence(cfg, result, current, card) -> None:
    risk = result.risks.get(card.risk_id) if card.risk_id else None
    if risk:
        initial = label(risk.initial) if risk.initial else "not calibrated"
        residual = label(risk.residual) if risk.residual else "not verified"
        st.caption(f"Evidence from {RISKS_TITLE} ({card.risk_id}): initial risk {initial} · residual {residual}. "
                   "Ratings show the intensity of the interference; they do not decide its justification.")
    elif card.risk_id:
        st.caption(f"{card.risk_id} is not included in {RISKS_TITLE}: no rating is available as evidence.")
    linked = ra.linked_mitigations(current, cfg, card.risk_id)
    if linked:
        st.caption("Measures bearing on this right: " + "; ".join(
            f"{m.mitigation_id} ({FUNCTION[cfg.mitigation(m.mitigation_id).hierarchy]}, {label(m.status)})" for m in linked))


def _open_points_sync(right: str) -> None:
    rights = state.store().setdefault("argument", {}).setdefault("rights", {})
    rights.setdefault(right, {"steps": {}, "open_points": ""})["open_points"] = st.session_state.get(f"w.arg.{right}.open_points") or ""


def render_rights(cfg, result) -> None:
    current = state.assessment()
    positions = ra.read(current, cfg, result)
    engaged = ra.engaged(current, cfg)
    st.markdown(
        "For each engaged right, in a fixed order: the right in context, the interference, the threshold "
        "(a right admitting no limitation, or its essence), necessity, guarantees and remedies, and the balancing "
        "in the strict sense. A step that raises a stop condition ends the argument until the legal review in "
        f"{REVIEW_TITLE} decides it."
    )
    if not engaged:
        st.info(f"No right is engaged yet. Screen the rights in {SCREENING_TITLE}.", icon=":material/info:")
        st.button("Go to the screening", key="arg.to.screening", on_click=state.go, args=(SCREENING_TITLE,))
        return
    names = {c.id: c.title for c in cfg.argument.rights}
    state.seed("w.arg.selected", engaged[0])
    if st.session_state["w.arg.selected"] not in engaged:
        st.session_state["w.arg.selected"] = engaged[0]
    right = st.selectbox("Right", engaged, key="w.arg.selected",
                         format_func=lambda r: f"{names[r]} — {ra.LABELS[positions.rights[r].position]}")
    card = cfg.argument.right(right)
    pos = positions.rights[right]
    st.markdown(f"Position: {badge(pos.position)}")
    for item in pos.items:
        st.caption(f"• {item.text}")
    _card(card)
    _evidence(cfg, result, current, card)
    for step in ("B1", "B2", "B3R", "B3E", "B4", "B5", "B6"):
        if step not in pos.required:
            continue
        step_box(cfg, right, step)
    hidden = [s for s in ("B4", "B5", "B6") if s not in pos.required]
    if hidden and any(i.ref in ("B3R", "B3E") for i in pos.items):
        st.caption("Necessity, guarantees and balancing are not asked while a limit is at issue: no balancing can "
                   f"justify it. If the legal review in {REVIEW_TITLE} excludes the stop, the argument resumes here.")
    revision_plan(cfg, current, right, pos.position)
    with st.container(border=True):
        st.markdown("**Open points.** What could not be determined, conflicting evidence, disagreement in the team.")
        key = f"w.arg.{right}.open_points"
        state.seed(key, (state.store().get("argument", {}).get("rights", {}).get(right) or {}).get("open_points", ""))
        st.text_area("Open points (optional)", key=key, on_change=_open_points_sync, args=(right,), height=80)
    st.caption(f"Measures and the action plan are in {MITIGATION_TITLE}. A verified measure marks the guarantees and "
               "the balancing out of date: record them again on the changed facts.")


# -- 3.6 across rights ---------------------------------------------------------------------


def render_cross(cfg, result) -> None:
    current = state.assessment()
    positions = ra.read(current, cfg, result)
    engaged = ra.engaged(current, cfg)
    st.markdown("Two questions that the argument for one right cannot answer alone. Then the positions at a glance.")
    if len(engaged) >= 2:
        step_box(cfg, "CROSS", "C1")
    else:
        st.caption("Cumulative interference (C1) is asked when two or more rights are engaged.")
    if engaged:
        step_box(cfg, "CROSS", "C2")
    st.subheader("Positions at a glance")
    rows = []
    for card in cfg.argument.rights:
        p = positions.rights[card.id]
        rows.append(f"| {card.title} | {badge(p.position)} | {'; '.join(i.text for i in p.items) or '—'} |")
    st.markdown("| Right | Position | What sets it |\n|---|---|---|\n" + "\n".join(rows))


# -- revision plan for one right (the revision loop) ---------------------------------------


def _plan_sync(cfg, right: str) -> None:
    ss = st.session_state
    rights = state.store().setdefault("argument", {}).setdefault("rights", {})
    entry = rights.setdefault(right, {"steps": {}, "open_points": ""})
    plan = dict(entry.get("plan") or {})
    for field in ("action", "owner", "due_date", "status"):
        k = f"w.arg.{right}.plan.{field}"
        if k in ss:
            plan[field] = ss[k] or ("PLANNED" if field == "status" else "")
    k = f"w.arg.{right}.plan.measures"
    if k in ss:
        plan["measures"] = list(ss[k] or [])
    entry["plan"] = plan
    # A measure chosen here is activated and linked to this right's risk; it is verified in 3.7.
    from digcon.domain.models import MitigationRecord
    risk_id = cfg.argument.right(right).risk_id
    for mid in plan.get("measures", []):
        stored = state.store()["mitigations"].get(mid, {"mitigation_id": mid})
        record = MitigationRecord.model_validate(stored).model_dump(mode="json")
        record["activated"] = True
        if risk_id:
            record["linked_risk_ids"] = sorted(set(record["linked_risk_ids"]) | {risk_id})
        state.store()["mitigations"][mid] = record
        st.session_state.pop(f"w.mit.{mid}.on", None)


PLAN_STATUS = {"PLANNED": "Planned", "IN_PROGRESS": "In progress", "DONE": "Implemented — verify in 3.7"}


def revision_plan(cfg, current, right: str, position: str) -> None:
    stored = ((state.store().get("argument") or {}).get("rights", {}).get(right) or {}).get("plan") or {}
    if position not in (ra.REVISION, ra.CONDITIONS) and not stored:
        return
    card = cfg.argument.right(right)
    with st.container(border=True):
        st.markdown("**What will change for this right.** Plan the action, link the measures, then verify them in "
                    f"{MITIGATION_TITLE}. A measure verified effective marks the guarantees and the balancing out of "
                    "date: record them again on the changed facts. The position changes only through new determinations.")
        for field in ("action", "owner", "due_date"):
            state.seed(f"w.arg.{right}.plan.{field}", stored.get(field) or "")
        state.seed(f"w.arg.{right}.plan.status", stored.get("status") or "PLANNED")
        state.seed(f"w.arg.{right}.plan.measures", list(stored.get("measures") or []))
        st.text_area("What will be done", key=f"w.arg.{right}.plan.action", on_change=_plan_sync, args=(cfg, right), height=68,
                     help="A concrete change to the use: narrower scope, fewer data, a human review route, a redesign.")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Owner", key=f"w.arg.{right}.plan.owner", on_change=_plan_sync, args=(cfg, right))
        c2.text_input("Target date (YYYY-MM-DD)", key=f"w.arg.{right}.plan.due_date", on_change=_plan_sync, args=(cfg, right))
        c3.selectbox("Progress", list(PLAN_STATUS), key=f"w.arg.{right}.plan.status", format_func=PLAN_STATUS.get,
                     on_change=_plan_sync, args=(cfg, right))
        own = [m.id for m in cfg.mitigations.mitigations if m.risk_id == card.risk_id]
        others = [m.id for m in cfg.mitigations.mitigations if m.risk_id != card.risk_id]
        names = {m.id: f"{m.id} · {FUNCTION[m.hierarchy].split(' — ')[0]} · {m.measure[:70]}" for m in cfg.mitigations.mitigations}
        st.multiselect("Catalogue measures for this action", own + others, key=f"w.arg.{right}.plan.measures",
                       format_func=names.get, on_change=_plan_sync, args=(cfg, right),
                       help="Measures for this right's risk are listed first. Choosing one activates it and links it to this right.")
        for mid in stored.get("measures") or []:
            rec = current.mitigations.get(mid)
            st.caption(f"{mid}: {label(rec.status) if rec else 'not activated'}")
        st.button(f"Verify the measures in {MITIGATION_TITLE}", key=f"arg.plan.go.{right}", on_click=state.go,
                  args=(MITIGATION_TITLE,))
