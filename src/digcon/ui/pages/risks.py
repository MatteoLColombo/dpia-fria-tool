"""Section 3.2: case risk register — RSEL-01 selection from the catalogue, four dimensions per risk, calibrated by the engine."""

from __future__ import annotations

import streamlit as st

from digcon.domain.enums import Probability, Reversibility, RuleEffect, Scale, Scope, label
from digcon.domain.models import ConfigBundle
from digcon.engine import EngineResult

from .. import api_mode, state

DIMENSIONS = (("scale", Scale), ("scope", Scope), ("reversibility", Reversibility), ("probability", Probability))


def _sync(rid: str) -> None:
    ss = st.session_state
    if not ss.get(f"w.risk.{rid}.include"):
        state.set_or_remove("risks", rid, None)
        return
    data = {"risk_id": rid}
    for prefix in ("", "residual_"):
        for dim, _ in DIMENSIONS:
            v = ss.get(f"w.risk.{rid}.{prefix}{dim}")
            if v is not None:
                data[f"{prefix}{dim}"] = v
    refs = [r.strip() for r in (ss.get(f"w.risk.{rid}.refs") or "").splitlines() if r.strip()]
    if refs:
        data["evidence_refs"] = refs
    state.set_or_remove("risks", rid, data)


def _dims(rid: str, prefix: str, stored: dict) -> None:
    cols = st.columns(4)
    for col, (dim, enum) in zip(cols, DIMENSIONS):
        key = f"w.risk.{rid}.{prefix}{dim}"
        state.seed(key, stored.get(f"{prefix}{dim}"))
        with col:
            st.selectbox(dim.capitalize(), [m.value for m in enum], key=key, placeholder="—",
                         format_func=lambda c, e=enum: label(e[c]), on_change=_sync, args=(rid,))


def suggestions(cfg: ConfigBundle, result: EngineResult) -> dict[str, list[str]]:
    """RSEL-01 (AS-032): risks whose source questions (sheet 04) were read by a rule that identified a harm.

    A suggestion only: the selection stays human and never goes outside the 11-risk catalogue.
    """
    triggers = {
        rid: set(rr.input_ids)
        for rid, rr in result.rules.items()
        if rr.fired and RuleEffect.RISK_INPUT in rr.effects and rid != "RSEL-01"
    }
    d04 = (state.store()["answers"].get("D04") or {}).get("value") or []
    out: dict[str, list[str]] = {}
    for spec in cfg.risks.risks:
        sources = set(spec.core_questions + spec.provider_questions + spec.deployer_questions)
        why = [f"{rid} ({', '.join(sorted(qs & sources))})" for rid, qs in triggers.items() if qs & sources]
        if spec.id in d04:
            why.insert(0, "selected in D04")
        if why:
            out[spec.id] = why
    return out


_RELEVANCE_TEXT = {"RELEVANT": "Relevant to this case", "NOT_RELEVANT": "Not relevant to this case",
                   "UNCERTAIN": "Unclear from the answers"}


def _api_box(rid: str) -> None:
    """The API's suggestion for this risk (3.2), with what a person did with it."""
    sug = state.store().get("api_risk_suggestions", {}).get(rid)
    if not sug:
        return
    decision = sug.get("decision")
    ratings = " · ".join(f"{dim.capitalize()} {label(enum[sug[dim]])}" for dim, enum in DIMENSIONS if sug.get(dim))
    cited = ", ".join(r.removeprefix("answer:") for r in sug.get("evidence_refs", [])) or "none"
    if decision != "PENDING":
        note = "you used it" if decision == "ACCEPTED" else "you dismissed it"
        st.caption(f":gray[The API suggested: {_RELEVANCE_TEXT[sug['relevance']]}"
                   f"{' (' + ratings + ')' if ratings else ''}; {note}.]")
        return
    with st.container(border=True):
        st.markdown(f":violet-badge[Suggested by API] **{_RELEVANCE_TEXT[sug['relevance']]}**"
                    + (f"  \nInitial: {ratings}" if ratings else ""))
        st.caption(f"{sug.get('rationale') or ''} Cited: {cited}. Not in the register until you use it; "
                   "check each rating against your evidence.")
        with st.container(horizontal=True, gap="small"):
            if sug["relevance"] == "RELEVANT":
                st.button("Use", key=f"api.risk.use.{rid}", icon=":material/check:", on_click=api_mode.use_risk,
                          args=(rid,), help="Include this risk with the suggested initial ratings; they become yours.")
            st.button("Dismiss", key=f"api.risk.dismiss.{rid}", icon=":material/close:",
                      on_click=api_mode.dismiss_risk, args=(rid,),
                      help="Set the suggestion aside; this risk will not be suggested again.")


def render(cfg: ConfigBundle, result: EngineResult) -> None:
    st.markdown(
        "Include the risks relevant to this case **from the DIGCON catalogue** and rate them; new risks cannot be "
        "added (RSEL-01). Severity = MAX(scale, scope, reversibility); level = severity × probability.\n\n"
        "Rate the **residual** dimensions only once a linked measure is VERIFIED EFFECTIVE (3.4). "
        "Until then the residual risk stays empty."
    )
    suggested = suggestions(cfg, result)
    rsel = result.rules.get("RSEL-01")
    in_register = set(state.store()["risks"])
    if rsel is not None and rsel.gap:
        st.warning("Your answers identify a harm (RSEL-01), but no risk is included and rated yet, so this is an "
                   "evidence gap. Include at least one risk below and rate its four initial dimensions.")
    missing = {r: why for r, why in suggested.items() if r not in in_register}
    if missing:
        with st.container(border=True):
            st.markdown(
                "**Suggested by RSEL-01** (not yet included)\n\n"
                + "\n".join(f"- **{r}** — from {'; '.join(why)}" for r, why in missing.items())
            )
    for spec in cfg.risks.risks:
        stored = state.store()["risks"].get(spec.id) or {}
        rr = result.risks.get(spec.id)
        level = (
            f" :orange-badge[Initial {label(rr.initial) if rr.initial else '—'}]"
            f" :gray-badge[Residual {label(rr.residual) if rr.residual else '—'}]" if rr else ""
        )
        hint = " :blue-badge[Suggested]" if spec.id in suggested and spec.id not in in_register else ""
        api_sug = state.store().get("api_risk_suggestions", {}).get(spec.id) or {}
        api_pending = api_sug.get("decision") == "PENDING" and api_sug.get("relevance") == "RELEVANT"
        if api_pending:
            hint += " :violet-badge[API: relevant]"
        title = f"{spec.id}{' (' + spec.label + ')' if spec.label else ''} — {spec.right.split(';')[0][:90]}{level}{hint}"
        with st.expander(title, expanded=bool(stored) or api_pending):
            _api_box(spec.id)
            key = f"w.risk.{spec.id}.include"
            state.seed(key, bool(stored))
            st.checkbox("Include in this assessment", key=key, on_change=_sync, args=(spec.id,))
            if rr and rr.to_reassess:
                st.warning("Stakeholder evidence modified or contradicted this risk (SEP09): review its ratings below.")
            with st.popover("Harm scenarios and safeguards to verify"):
                for h in spec.harm_scenarios:
                    st.markdown(f"- {h}")
                st.caption(spec.safeguards_to_verify)
            if not st.session_state[key]:
                continue
            with st.container(border=True):
                st.markdown("**Initial**")
                _dims(spec.id, "", stored)
                st.markdown("**Residual** :gray[after a linked measure is VERIFIED EFFECTIVE (3.4)]")
                _dims(spec.id, "residual_", stored)
            state.seed(f"w.risk.{spec.id}.refs", "\n".join(stored.get("evidence_refs", [])))
            st.text_area("Evidence references (one per line)", key=f"w.risk.{spec.id}.refs", height=68,
                         on_change=_sync, args=(spec.id,))
            _residual_review(cfg, spec.id)


def _save_review(rid):
    from digcon.domain.action_plan import fingerprint
    from digcon.domain.models import ResidualRiskReview
    def value(field): return st.session_state.get(f"w.resreview.{rid}.{field}", "")
    review = ResidualRiskReview(
        reviewer=value('reviewer'), review_date=value('date'), rationale=value('reason'),
        evidence_refs=[x.strip() for x in value('refs').splitlines() if x.strip()],
        mitigation_ids=value('measures') or [], reviewed_fingerprint=fingerprint(state.assessment(), rid))
    state.store().setdefault('residual_reviews', {})[rid] = review.model_dump(mode='json')


def _residual_review(cfg, rid):
    from digcon.domain.action_plan import residual_approved
    stored = state.store().get('residual_reviews', {}).get(rid, {})
    with st.expander('Verify the residual risk assessment'):
        st.caption('Justify scale, scope, reversibility and probability separately, including unchanged or increased dimensions. '
                   'Identify the verified measures and supporting evidence. Changes to assessment evidence require a new review.')
        for field, label_, attr in [('reviewer','Reviewer','reviewer'), ('date','Review date (YYYY-MM-DD)','review_date'),
                                    ('reason','Reasoning for each of the four dimensions','rationale'),
                                    ('refs','Verification evidence (one reference per line)','evidence_refs')]:
            value = stored.get(attr, '')
            if isinstance(value, list): value = '\n'.join(value)
            key = f'w.resreview.{rid}.{field}'; state.seed(key,value)
            st.text_area(label_,key=key)
        mids = [m.id for m in cfg.mitigations.mitigations]
        key=f'w.resreview.{rid}.measures';state.seed(key, stored.get('mitigation_ids', []))
        st.multiselect('Measures supporting this reassessment', mids, key=key,
                       format_func=lambda m: cfg.mitigation(m).measure)
        st.button('Record residual risk review',key=f'resreview.save.{rid}',on_click=_save_review,args=(rid,))
        if residual_approved(state.assessment(), rid):
            st.caption('Review recorded for the current evidence. The engine also checks the linked measures and their effectiveness status.')
        elif stored:
            st.warning('Review incomplete or supporting information changed; residual risk remains unverified.')
