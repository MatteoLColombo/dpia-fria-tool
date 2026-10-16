"""Config-driven widgets. A new question in questions.yaml appears here with no code change."""

from __future__ import annotations

from typing import Any

import streamlit as st

from digcon.domain.enums import AnswerKind, ControlEffectiveness, NotificationStatus, RiskLevel, Role, RuleElementState, label
from digcon.domain.models import ConfigBundle, QuestionSpec, RuleElementSpec

from . import api_mode, state
from .labels import QUESTION_NOTES
from .style import RULE, question_title

ELEMENT_STATES = [s.value for s in RuleElementState]


def _label(code: str, names: dict[str, str]) -> str:
    return names.get(code, code)


def _option_names(cfg: ConfigBundle, q: QuestionSpec) -> dict[str, str]:
    names = {s.value: label(s) for s in q.states}
    if q.kind is AnswerKind.ROLE:
        names |= {r.value: label(r) for r in Role if r is not Role.UNKNOWN}
    elif q.kind is AnswerKind.RISK_RATING:
        names |= {r.value: label(r) for r in RiskLevel}
    elif q.kind is AnswerKind.NOTIFICATION:
        names |= {n.value: label(n) for n in NotificationStatus}
    elif q.kind is AnswerKind.EFFECTIVENESS:
        names |= {e.value: label(e) for e in ControlEffectiveness}
    elif q.kind in (AnswerKind.SINGLE, AnswerKind.MULTI) and q.option_set:
        names |= {o.code: o.label for os_ in cfg.questions.option_sets if os_.id == q.option_set for o in os_.options}
    elif q.kind is AnswerKind.RISK_ROWS:
        names |= {r.id: f"{r.id} — {r.label or r.right.split(';')[0][:60]}" for r in cfg.risks.risks}
    return names


def _value_codes(cfg: ConfigBundle, q: QuestionSpec) -> list[str]:
    states = {s.value for s in q.states}
    return [c for c in _option_names(cfg, q) if c not in states]


def _sync(cfg: ConfigBundle, q: QuestionSpec) -> None:
    ss = st.session_state
    k = f"w.{q.id}"
    states = [s.value for s in q.states]
    answer: dict[str, Any] | None
    if q.kind is AnswerKind.STATE:
        v = ss.get(k)
        answer = None if v is None else {"question_id": q.id, "state": v}
        detail = (ss.get(f"{k}.detail") or "").strip()
        if answer and detail:
            answer["detail"] = detail
    elif q.kind in (AnswerKind.TEXT, AnswerKind.REFERENCE, AnswerKind.MULTI, AnswerKind.RISK_ROWS):
        status = ss.get(f"{k}.status")  # None = a value is given
        value = ss.get(f"{k}.value")
        if status:
            answer = {"question_id": q.id, "state": status}
        elif isinstance(value, str) and value.strip():
            answer = {"question_id": q.id, "value": value.strip()}
        elif isinstance(value, list) and value:
            answer = {"question_id": q.id, "value": list(value)}
        else:
            answer = None
    else:
        v = ss.get(k)
        if v is None:
            answer = None
        elif v in states:
            answer = {"question_id": q.id, "state": v}
        else:
            answer = {"question_id": q.id, "value": v}
        detail = (ss.get(f"{k}.detail") or "").strip()
        if answer and detail:
            answer["detail"] = detail
    state.set_or_remove("answers", q.id, answer)


UNRESOLVED_NOTE = {
    "UNKNOWN": ":violet-badge[:material/help: Unknown] :gray[May create an evidence gap. Never read as NO.]",
    "NOT_OWNED": ":violet-badge[:material/person_off: Not owned] :gray[May create an evidence gap. Never read as NO.]",
    "N_A": ":gray-badge[:material/block: N/A] :gray[May be sent for verification. Never read as NO.]",
}


def question(cfg: ConfigBundle, q: QuestionSpec) -> None:
    st.markdown(question_title(q.text, q.id), unsafe_allow_html=True, help=f"Rules: {q.rule_refs_text}")
    _question(cfg, q)
    answer = state.store()["answers"].get(q.id) or {}
    if answer.get("state") in UNRESOLVED_NOTE:
        st.markdown(UNRESOLVED_NOTE[answer["state"]])
    if q.id in QUESTION_NOTES:
        st.caption(QUESTION_NOTES[q.id])
    st.markdown(RULE, unsafe_allow_html=True)


def _question(cfg: ConfigBundle, q: QuestionSpec) -> None:
    stored = state.store()["answers"].get(q.id) or {}
    k = f"w.{q.id}"
    names = _option_names(cfg, q)
    title = q.text  # visible title is drawn above; the widget keeps it as its accessible name
    hidden = "collapsed"
    on_change = _sync
    args = (cfg, q)

    if q.kind is AnswerKind.STATE:
        state.seed(k, stored.get("state"))
        st.segmented_control(title, [s.value for s in q.states], key=k, label_visibility=hidden,
                             format_func=lambda c: _label(c, names), on_change=on_change, args=args)
        if "+" in q.response_model and st.session_state.get(k) is not None:
            state.seed(f"{k}.detail", stored.get("detail") or "")
            st.text_input("Basis or evidence reference (optional)", key=f"{k}.detail", on_change=on_change, args=args)
        return

    if q.kind in (AnswerKind.TEXT, AnswerKind.REFERENCE, AnswerKind.MULTI, AnswerKind.RISK_ROWS):
        state.seed(f"{k}.status", stored.get("state"))
        is_list = q.kind in (AnswerKind.MULTI, AnswerKind.RISK_ROWS)
        value = stored.get("value")
        state.seed(f"{k}.value", (value if isinstance(value, list) else []) if is_list else (value or ""))
        status = st.session_state[f"{k}.status"]
        disabled = status is not None
        locked = f"Marked as {label_of(status, names)}: click {label_of(status, names)} again to answer." if disabled else ""
        if is_list:
            st.pills(title, _value_codes(cfg, q), selection_mode="multi", key=f"{k}.value", disabled=disabled, wrap=True,
                     label_visibility=hidden, format_func=lambda c: _label(c, names), on_change=on_change, args=args)
        else:
            st.text_area(title, key=f"{k}.value", disabled=disabled, height=80, label_visibility=hidden,
                         placeholder=locked or "Type the answer, or mark it below", on_change=on_change, args=args)
        if disabled:
            st.caption(f":material/lock: {locked}")
        st.segmented_control("Or mark it as", [s.value for s in q.states], key=f"{k}.status",
                             format_func=lambda c: label_of(c, names), on_change=on_change, args=args)
        return

    # SINGLE / ROLE / RISK_RATING / NOTIFICATION / EFFECTIVENESS: one closed value or an unresolved state.
    state.seed(k, stored.get("value") or stored.get("state"))
    st.selectbox(title, [*_value_codes(cfg, q), *[s.value for s in q.states]], key=k, label_visibility=hidden,
                 placeholder="Select…", format_func=lambda c: _label(c, names), on_change=on_change, args=args)
    if q.kind in (AnswerKind.RISK_RATING, AnswerKind.NOTIFICATION, AnswerKind.EFFECTIVENESS) and st.session_state.get(k):
        state.seed(f"{k}.detail", stored.get("detail") or "")
        st.text_input("Evidence reference", key=f"{k}.detail", on_change=on_change, args=args)


def label_of(code: str, names: dict[str, str]) -> str:
    return names.get(code, code)


def _sync_element(eid: str) -> None:
    v = st.session_state.get(f"w.{eid}")
    api_mode.note_person_change(eid)
    # a value set here is the person's: it replaces an API value and the API never overwrites it
    state.set_or_remove("elements", eid, None if v is None else {"element_id": eid, "state": v})


def element(spec: RuleElementSpec, effective: str | None = None) -> None:
    """Element of a rule: MET / NOT_MET / UNCERTAIN, or not evaluated. ANSWER elements are read-only."""
    if spec.binding is not None:
        st.markdown(f"- `{spec.id}` {spec.text} — *read from {spec.binding.q}*: **{effective or 'UNCERTAIN'}**")
        return
    k = f"w.{spec.id}"
    stored = state.store()["elements"].get(spec.id)
    state.seed(k, stored["state"] if stored else None)
    tags = " · ".join(t for t, on in (("legal judgement", spec.legal_judgement), ("non-remediability", spec.non_remediability)) if on)
    st.segmented_control(
        f"`{spec.id}` {spec.text}" + (f"  _({tags})_" if tags else ""), ELEMENT_STATES, key=k,
        format_func=lambda c: c.replace("_", " "), on_change=_sync_element, args=(spec.id,),
        help="Not evaluated until you choose. Click the chosen state again to clear it.",
    )
    if stored and stored.get("source") == "API":
        cited = ", ".join(r.removeprefix("answer:") for r in stored.get("evidence_refs", [])) or "none"
        st.markdown(f":blue-badge[:material/smart_toy: Set by API] :gray[{stored.get('rationale') or ''}]")
        st.caption(f"Cited: {cited}. Choose a state yourself to replace it.")


def _sync_gate(rule_id: str) -> None:
    ss = st.session_state
    done = ss.get(f"w.gate.{rule_id}", False)
    decision = (ss.get(f"w.gate.{rule_id}.decision") or "").strip()
    by = (ss.get(f"w.gate.{rule_id}.by") or "").strip()
    value = (
        {"rule_id": rule_id, "gate": "COMPLETED", "decision": decision, "decided_by": by}
        if done and decision and by
        else None
    )
    state.set_or_remove("human_gates", rule_id, value)


def legal_gate(rule_id: str) -> None:
    stored = state.store()["human_gates"].get(rule_id) or {}
    k = f"w.gate.{rule_id}"
    state.seed(k, stored.get("gate") == "COMPLETED")
    state.seed(f"{k}.decision", stored.get("decision") or "")
    state.seed(f"{k}.by", stored.get("decided_by") or "")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        st.checkbox("Legal review completed", key=k, on_change=_sync_gate, args=(rule_id,))
    with c2:
        st.text_input("Decision and reasoning", key=f"{k}.decision", on_change=_sync_gate, args=(rule_id,))
    with c3:
        st.text_input("Reviewer", key=f"{k}.by", on_change=_sync_gate, args=(rule_id,))
    if st.session_state[k] and rule_id not in state.store()["human_gates"]:
        st.caption(":orange[Fill in decision and reviewer to record the review.]")
