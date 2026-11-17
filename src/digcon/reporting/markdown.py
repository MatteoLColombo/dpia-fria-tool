"""Markdown report of one engine run: outcome, what to do next, answers, registers, governance, audit trail."""

from __future__ import annotations

from digcon.domain.enums import ApiReview, label
from digcon.domain.models import AssessmentState, ConfigBundle
from digcon.engine import EngineResult
from digcon.ui.labels import (
    APP_TITLE,
    CREDITS,
    DISCLAIMER,
    FOOTER,
    OUTCOME_TEXT,
    OUTCOME_TITLES,
    PHASE_TITLES,
    RECOMMENDATION_NOTE,
)

from .text import answer_text

# What stands between the case and a better outcome, in precedence order (as on 4.1).
NEXT = (
    ("evidence_gaps", "Evidence gaps", "Keep the outcome at O4 until resolved."),
    ("open_remediations", "Open remediations", "Keep the outcome at O3 until resolved."),
    ("open_conditions", "Conditions", "Remain attached to an O2 outcome."),
    ("pending_reviews", "Legal reviews pending", "Do not change the outcome by themselves."),
    ("verification_requests", "To be verified", "Do not change the outcome."),
)
GOVERNANCE = (
    ("G01", "g01_decision"), ("G02", "g02_decision_maker"), ("G03", "g03_review_date"),
    ("G04", "g04_conditions"), ("G05", "g05_reasoning"),
)
SEP_ATTRS = {"SEP00": "decision", "SEP03": "vulnerability", "SEP09": "effect", "SEP10": "new_risk", "SEP11": "new_mitigation"}


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>") or "—"


def _table(head: list[str], rows: list[list[object]]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|" + "|".join("---" for _ in head) + "|",
        *("| " + " | ".join(_cell(v) for v in row) + " |" for row in rows),
        "",
    ]


def _v(member) -> str:
    return label(member) if member is not None else "—"


SET_BY = {
    None: "Person",
    ApiReview.PENDING: "API (not yet reviewed)",
    ApiReview.CONFIRMED: "Person, confirmed the API",
    ApiReview.CHANGED: "Person, changed the API's value",
    ApiReview.CLEARED: "Person, cleared the API's value",
}


def element_origin(state: AssessmentState, element_id: str) -> str:
    """Who set a reviewer check, and what a person did with the API's suggestion."""
    return SET_BY[state.api_review(element_id)]


def _argument(cfg: ConfigBundle, state: AssessmentState, positions) -> list[str]:
    """RA-1: every determination of the argument, with its reasons, sources, evidence and any dissent."""
    from digcon import argument as ra

    out = ["## 7. Rights argument", "", cfg.argument.meta.disclaimer, ""]

    def det(scope: str, step: str) -> None:
        spec = cfg.argument.step(step)
        rec = ra._record(state, scope, step)
        reading = ra.read_step(state, cfg, scope, step)
        if rec is None or not rec.code:
            out.append(f"- **{spec.title}:** not determined")
            return
        opt = spec.option(rec.code)
        status = {ra.CURRENT: "", ra.STALE: " _(out of date)_", ra.MISSING: " _(not recorded)_"}[reading.status]
        out.append(f"- **{spec.title}:** {opt.label if opt else rec.code}{status} — {rec.reasons or 'no reasons'}"
                   + (f" ({rec.author}, {rec.date})" if rec.author else ""))
        for name, values in (("Sources", rec.sources), ("Evidence", rec.evidence)):
            if values:
                out.append(f"    - {name}: " + "; ".join(values))
        for key, value in rec.extra.items():
            out.append(f"    - {key.capitalize()}: {value}")
        if rec.dissent.strip():
            out.append(f"    - Dissent ({rec.dissent_by or 'author not stated'}): {rec.dissent}")

    out += ["### The use as a whole", ""]
    for step in ra.SYSTEM_STEPS:
        det("SYSTEM", step)
    out.append("")
    out += ["### Screening", ""]
    for card in cfg.argument.rights:
        rec = ra._record(state, card.id, "S0")
        code = rec.code if rec and rec.code else "not screened"
        out.append(f"- {card.title}: {code.replace('_', ' ').lower()}" + (f" — {rec.reasons}" if rec and rec.reasons else ""))
    out.append("")
    for right in ra.engaged(state, cfg):
        card = cfg.argument.right(right)
        p = positions.rights[right]
        out += [f"### {card.title} — {ra.LABELS[p.position]}", ""]
        if card.status != "VERIFIED":
            out.append("_Guidance on this right is a draft not yet verified by the research team._")
            out.append("")
        for step in ra.RIGHT_STEPS[1:]:
            if step in p.required:
                det(right, step)
        arg = state.argument.rights.get(right)
        if arg and arg.open_points.strip():
            out.append(f"- **Open points:** {arg.open_points}")
        if arg and arg.plan and arg.plan.action.strip():
            plan = arg.plan
            out.append(f"- **Revision plan:** {plan.action} (owner {plan.owner or 'not named'}, target "
                       f"{plan.due_date or 'not set'}, {plan.status.lower().replace('_', ' ')})"
                       + (f"; measures {', '.join(plan.measures)}" if plan.measures else ""))
        out.append("")
    if ra.engaged(state, cfg):
        out += ["### Across rights", ""]
        for step in ra.CROSS_STEPS:
            det("CROSS", step)
        out.append("")
    out.append("The positions record whether each step was determined, reasoned, signed and current. They are not "
               "a finding by the tool that the use is proportionate.")
    out.append("")
    return out


def build(cfg: ConfigBundle, state: AssessmentState, result: EngineResult) -> str:
    out: list[str] = []
    add = out.append

    add(f"# {APP_TITLE} — assessment report")
    add("")
    add(f"- Assessment: **{state.assessment_id}**")
    add(f"- Logic version: {cfg.logic_version}")
    add(f"- Run: {result.run_id}, {result.timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
    add("")
    add(f"> {DISCLAIMER}")
    add("")

    from digcon import argument as ra
    from digcon.ui.labels import POSITION_TEXT

    positions = ra.read(state, cfg, result)
    add("## 1. Assessment findings: overall position")
    add("")
    add(f"**{positions.label()}** — assessment {'complete' if positions.complete else 'incomplete'} · export code {positions.ocode}")
    add("")
    add(POSITION_TEXT[positions.overall])
    add("")
    out.extend(_table(["Right", "Position", "What sets it"], [
        [cfg.argument.right(r).title, ra.LABELS[p.position], "; ".join(i.text for i in p.items) or "—"]
        for r, p in positions.rights.items()
    ]))
    add(f"The export code is derived from the overall position. The workbook's own reading of steps 1–2 "
        f"(rule {result.outcome_rule}) gives {OUTCOME_TITLES[result.outcome]}.")
    add("")
    add(RECOMMENDATION_NOTE.replace("4.2 Governance decision", "section 10"))
    if not result.closed:
        add("")
        add("**Audit defects: this run is not a valid closure.** " + "; ".join(result.audit_defects))
    for w in result.warnings:
        add("")
        add(f"Warning: {w}")
    add("")

    add("## 2. What to do next")
    add("")
    every = positions.system + [i for p in positions.rights.values() for i in p.items]
    for pos in (ra.STOP_CONFIRMED, ra.STOP_PENDING, ra.REVISION, ra.STOP_EXCLUDED, ra.INCOMPLETE, ra.CONDITIONS):
        items = [i for i in every if i.position == pos]
        if not items:
            continue
        add(f"### {ra.LABELS[pos]} ({len(items)})")
        add("")
        for i in items:
            where = {"SYSTEM": "The use as a whole", "CROSS": "Across rights", "WORKBOOK": f"`{i.ref}`"}.get(
                i.scope) or cfg.argument.right(i.scope).title
            add(f"- {where}: {i.text}")
        add("")
    add("### Workbook findings in detail")
    add("")
    if not any(getattr(result, attr) for attr, *_ in NEXT):
        add("Nothing open: no gap, remediation, condition, pending review or verification request.")
        add("")
    for attr, title, effect in NEXT:
        findings = getattr(result, attr)
        if not findings:
            continue
        add(f"#### {title} ({len(findings)})")
        add("")
        add(f"_{effect} (workbook reading)_")
        add("")
        for f in findings:
            add(f"- `{f.rule_id}` {f.message}" + (f" ({', '.join(f.ids)})" if f.ids else ""))
        add("")

    add("## 3. Applicable assessment requirements")
    add("")
    add(f"- High-risk (FOLLOW): {result.high_risk or 'not answered'}")
    add(f"- Role (C05): {result.role or 'not answered'}")
    add(f"- Article 9 provider obligations: {'apply' if result.provider_module else 'do not apply'}")
    add(f"- Article 27 deployer FRIA: {'applies' if result.deployer_module else 'does not apply'}")
    if result.routing_suspended:
        add("- Step 2 requirements on hold (C03 = YES) until the legal review of HS07")
    add("")

    add("## 4. Answers")
    add("")
    visible = set(result.visible_questions)
    for phase, title in PHASE_TITLES.items():
        qs = [q for q in cfg.questions.questions if q.phase is phase and q.id in visible]
        if not qs:
            continue
        add(f"### {title}")
        add("")
        rows = []
        for q in qs:
            a = state.answers.get(q.id)
            rows.append([q.id, q.text, answer_text(cfg, q, a), a.detail if a else None])
        out.extend(_table(["ID", "Question", "Answer", "Basis or evidence"], rows))

    add("## 5. Stakeholder involvement (SEP)")
    add("")
    sep_rows = []
    for f in cfg.sep.fields:
        value = getattr(state.sep, SEP_ATTRS[f.id]) if f.id in SEP_ATTRS else state.sep.texts.get(f.id)
        if value is None or value == "":
            continue
        sep_rows.append([f.id, f.field, _v(value) if hasattr(value, "value") else value])
    if state.sep.effect_risk_ids:
        sep_rows.append(["SEP09", "Risks affected", ", ".join(state.sep.effect_risk_ids)])
    out.extend(_table(["ID", "Field", "Value"], sep_rows) if sep_rows else ["Nothing recorded.", ""])

    add("## 6. Fundamental rights risks")
    add("")
    if result.risks:
        rows = []
        for rid, r in result.risks.items():
            ra = state.risks.get(rid)
            rows.append([
                rid, cfg.risk(rid).right.split(";")[0],
                " / ".join(_v(getattr(ra, d, None)) for d in ("scale", "scope", "reversibility", "probability")),
                _v(r.severity), _v(r.initial), _v(r.residual) if r.residual else "— (not verified)",
                "Yes" if r.to_reassess else "—",
            ])
        out.extend(_table(["Risk", "Right", "Scale / scope / reversibility / probability", "Severity",
                           "Initial", "Residual", "Reassess (SEP)"], rows))
        add("Residual risk is recorded only after a linked mitigation is verified effective.")
        add("")
    else:
        add("No risk included.")
        add("")

    out.extend(_argument(cfg, state, positions))
    add("## 8. Legal and procedural checks")
    add("")
    add("### Reviewer checks")
    add("")
    checks = sorted(eid for eid in {*state.elements, *state.api_suggestions}
                    if cfg.rule(eid.split(".", 1)[0]).family != "HS")
    if checks:
        rows = []
        for eid in checks:
            ev, sug = state.elements.get(eid), state.api_suggestions.get(eid)
            reason = sug or ev
            rows.append([
                eid, ev.state.value.replace("_", " ") if ev else "Not evaluated", element_origin(state, eid),
                sug.state.value.replace("_", " ") if sug else None, reason.rationale,
                ", ".join(r.removeprefix("answer:") for r in reason.evidence_refs),
            ])
        out.extend(_table(["Check", "State", "Set by", "API suggested", "API reason", "Cited"], rows))
    else:
        add("No reviewer check recorded.")
        add("")
    gates = [g for g in state.human_gates.values() if cfg.rule(g.rule_id).family != "HS"]
    if gates:
        add("### Legal reviews")
        add("")
        out.extend(_table(["Rule", "Review", "Decision", "Reviewer"],
                          [[g.rule_id, g.gate.value, g.decision, g.decided_by] for g in gates]))
    scrutiny = sorted(r for r, rr in result.rules.items() if rr.fired and any(e.value == "SCRUTINY" for e in rr.effects))
    if scrutiny:
        add(f"Higher scrutiny raised by: {', '.join(scrutiny)}.")
        add("")

    add("## 9. Safeguards, mitigation and stop conditions")
    add("")
    add("### Safeguards and mitigation")
    add("")
    activated = [m for m in state.mitigations.values() if m.activated]
    if activated:
        out.extend(_table(["Mitigation", "Risk", "Measure", "Status", "Decision effect", "Owner"], [
            [m.mitigation_id, cfg.mitigation(m.mitigation_id).risk_id, cfg.mitigation(m.mitigation_id).measure,
             label(m.status), cfg.mitigation(m.mitigation_id).decision_effect_text, m.owner or "TO ASSIGN"]
            for m in activated
        ]))
    else:
        add("No measure activated.")
        add("")
    add("### Legal constraints and stop conditions")
    add("")
    opened = {h: v for h, v in result.hard_stops.items() if v.opened}
    if opened:
        out.extend(_table(["Stop condition", "State", "Legal review", "Elements"], [
            [h, v.state.value.replace("_", " "), v.gate.value,
             ", ".join(f"{k.split('.')[1]}={s.value}" for k, s in v.elements.items())]
            for h, v in opened.items()
        ]))
    else:
        add("No stop condition opened (HS01–HS10). High risk alone never produces O5.")
        add("")

    add("## 10. Governance decision")
    add("")
    fields = {g.id: g.field for g in cfg.questions.governance_fields}
    gov = [(gid, fields.get(gid, gid), getattr(state.governance, attr)) for gid, attr in GOVERNANCE]
    if any(v for *_, v in gov):
        out.extend(_table(["ID", "Field", "Value"], [[gid, field, v] for gid, field, v in gov]))
    else:
        add("Not recorded yet. It is filled by the responsible person or body, never by the tool.")
        add("")
    follows = state.governance.follows_position
    if follows == "DEPARTS":
        reasons = (state.governance.departure_reasons or "").strip()
        add(f"**The decision departs from the overall position ({positions.label()}).** "
            + (f"Reasons: {reasons}" if reasons else "No reasons recorded: the departure is unexplained."))
        add("")
    elif follows == "FOLLOWS":
        add(f"The decision follows the overall position ({positions.label()}).")
        add("")

    add("## 11. Audit trail")
    add("")
    add(f"{len(result.audit_trail)} events, run {result.run_id}, logic version {result.workbook_version}. "
        "The JSON report holds every field of every event.")
    add("")
    out.extend(_table(["Event", "Module", "Rule", "Output", "Inputs", "Evidence", "API", "Human review", "Parent"], [
        [e.event_id, e.module.value, e.rule_id, e.engine_output, ", ".join(e.input_ids), ", ".join(e.evidence_refs),
         ", ".join(f"{k}={v['state']}" for k, v in e.api_evaluation.items()) if e.api_evaluation else None,
         " — ".join(x for x in ((e.human_gate.value if e.human_gate else ""), e.human_decision or "") if x) or None,
         e.parent_event_id]
        for e in result.audit_trail
    ]))

    from digcon.domain.action_plan import title as action_title, approved
    add("## Action plan")
    for rid, item in state.action_plan.items():
        add(f"### {action_title(rid)}")
        add(f"- Progress: {item.status}; owner: {item.owner or 'Unassigned'}; target: {item.due_date or 'Not set'}")
        add(f"- Action: {item.action}")
        add(f"- Relevance: {item.rationale}")
        add(f"- Implementation: {item.implementation}")
        add(f"- Implementation evidence: {', '.join(item.evidence_refs)}")
        add(f"- Verification: {item.verification_method}; result: {item.verification_result}")
        add(f"- Verification evidence: {', '.join(item.verification_evidence)}")
        add(f"- Review: {item.decision}; reviewer: {item.reviewer}; date: {item.review_date}")
        add(f"- Reason: {item.decision_reason}")
        add(f"- Current documented resolution approval: {approved(state, rid)}")
        add("")
    add("---")
    add("")
    add(CREDITS)
    add("")
    add(FOOTER)
    add("")
    if state.alternatives_review is not None:
        from digcon.domain.alternatives import decision
        record = state.alternatives_review
        out += ['## Alternatives and necessity review', '',
                'The original C31 answer, if present, is retained above with its original meaning.', '',
                f'Effective review status: {decision(state)}', '',
                *_table(['Field', 'Recorded information'], [[k, v] for k, v in record.model_dump(mode='json').items()
                                                           if k not in ('history', 'reviewed_fingerprint')]),
                'Previous determinations: ' + str(len(record.history)), '']
    return "\n".join(out)
