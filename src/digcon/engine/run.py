"""run_engine: one deterministic pass from (config, assessment state, run context) to EngineResult."""

from __future__ import annotations

from digcon.domain.enums import (
    ElementSource,
    EngineFlag,
    HumanGate,
    HumanGateRequirement,
    Outcome,
    RuleEffect,
    RuleElementState,
    SepDecision,
)
from digcon.domain.models import AssessmentState, ConfigBundle

from .audit import audit_defects, build_trail
from .evaluator import HARD_STOPS, AnswerStatus, Evaluator
from .inputs import InvalidAssessment, check_state
from .result import EngineResult, Finding, HardStopResult, RuleResult, RunContext

_PREFIXES = ("answer:", "question:", "risk:", "mitigation:", "sep:")


def _api_evaluations(state: AssessmentState) -> dict[str, dict]:
    """Element states set by the interpreter, grouped by rule, for the audit trail (06_API: api_evaluation)."""
    out: dict[str, dict] = {}
    for eid, ev in state.elements.items():
        if ev.source is ElementSource.API:
            out.setdefault(eid.split(".", 1)[0], {})[eid] = {
                "state": ev.state.value,
                "evidence_refs": list(ev.evidence_refs),
                "rationale": ev.rationale,
                "provenance": ev.provenance,
            }
    return out


def run_engine(cfg: ConfigBundle, state: AssessmentState, ctx: RunContext) -> EngineResult:
    errors = check_state(cfg, state)
    if errors:
        raise InvalidAssessment(errors)
    ev = Evaluator(cfg, state)
    families = {r.id: r.family for r in cfg.rules.rules}

    # Outcome: OUT rules in precedence order O5 → O4 → O3 → O2 → O1; the first that fires wins.
    out_rules = sorted(
        (r for r in cfg.rules.rules if r.family == "OUT"),
        key=lambda r: cfg.rules.outcome_precedence.index(r.encoding.outcome),
    )
    outcome_rule = next((r for r in out_rules if ev.rule(r.id).fired), None)
    if outcome_rule is None:  # OUT-01 is the complement of the others: unreachable with a valid config
        raise RuntimeError("no outcome rule fired")

    rules: dict[str, RuleResult] = {}
    for spec in cfg.rules.rules:
        e = ev.rule(spec.id)
        refs = sorted(e.refs)
        rules[spec.id] = RuleResult(
            rule_id=spec.id,
            fired=e.fired,
            case=e.case,
            effects=list(e.effects),
            status=e.status,
            gap=e.gap,
            gap_effects=list(e.gap_effects),
            review=e.review,
            human_gate=_gate(ev, spec, e),
            input_ids=sorted({r.split(":", 1)[1] for r in refs if r.startswith(_PREFIXES)}),
            evidence_refs=refs,
            linked_risk_ids=sorted(e.risks),
            linked_mitigation_ids=sorted(
                e.mitigations | {m.mitigation_id for m in ev.activated() if spec.id in m.linked_rule_ids}
            ),
        )

    hard_stops = {}
    for hs in HARD_STOPS:
        elements = ev.hs_elements(hs)
        gate = ev.gate(hs)
        opened = rules[hs].fired
        all_met = all(s is RuleElementState.MET for s in elements.values())
        hard_stops[hs] = HardStopResult(
            hs_id=hs,
            opened=opened,
            state=ev.hs_state(hs),
            elements=elements,
            gate=gate or (HumanGate.REQUIRED if opened else HumanGate.NO),
            awaiting_legal_review=all_met and gate is not HumanGate.COMPLETED,
        )

    findings = _findings(ev, cfg, rules, hard_stops)
    trail = build_trail(
        ctx=ctx,
        assessment_id=state.assessment_id,
        workbook_version=cfg.version,
        families=families,
        rules=rules,
        hard_stops=hard_stops,
        risks=ev.risks,
        risk_evidence={rid: ra.evidence_refs for rid, ra in state.risks.items()},
        api_evaluations=_api_evaluations(state),
        human_decisions={
            rid: f"{g.decision} — {g.decided_by}" + (f" ({g.reference})" if g.reference else "")
            for rid, g in state.human_gates.items()
            if g.gate is HumanGate.COMPLETED
        },
        outcome_rule=outcome_rule.id,
        outcome=outcome_rule.encoding.outcome,
    )

    role_ans = state.answers.get("C05")
    follow = state.answers.get("FOLLOW")
    hs07_open = ev.hs_state("HS07") is not RuleElementState.NOT_MET
    sep_needed = any(RuleEffect.SEP_ASSESSMENT in rules[r].effects for r in rules)
    return EngineResult(
        assessment_id=state.assessment_id,
        run_id=ctx.run_id,
        workbook_version=cfg.version,
        timestamp=ctx.timestamp,
        outcome=Outcome(outcome_rule.encoding.outcome),
        outcome_rule=outcome_rule.id,
        high_risk=follow.state.value if follow and follow.state else None,
        role=(role_ans.value or role_ans.state.value) if role_ans else None,
        routing_suspended=rules["FLOW-01"].fired and hs07_open,
        provider_module=rules["FLOW-03"].fired,
        deployer_module=rules["FLOW-05"].fired,
        visible_questions=[q.id for q in cfg.questions.questions if ev.visible(q.id)],
        flags={f: ev.flag(f)[0] for f in EngineFlag},
        rules=rules,
        hard_stops=hard_stops,
        prop_statuses={r: rules[r].status for r in rules if rules[r].status is not None},
        risks=ev.risks,
        sep_status=state.sep.decision or (SepDecision.TO_ASSESS if sep_needed else None),
        warnings=list(ev.warnings),
        audit_trail=trail,
        audit_defects=audit_defects(trail),
        **findings,
    )


def _gate(ev: Evaluator, spec, e) -> HumanGate:
    """Human-gate event of a rule: REQUIRED when the rule applies and reserves the judgement to a person."""
    if spec.family == "OUT" or not (e.fired or e.gap):
        return HumanGate.NO
    effects = set(e.effects) | set(e.gap_effects)
    needed = spec.human_gate is HumanGateRequirement.REQUIRED or (
        spec.human_gate is HumanGateRequirement.POSSIBLE and RuleEffect.HUMAN_LEGAL_REVIEW in effects
    )
    if spec.family == "HS":
        needed = e.fired
    if not needed:
        return HumanGate.NO
    return HumanGate.COMPLETED if ev.gate(spec.id) is HumanGate.COMPLETED else HumanGate.REQUIRED


def _findings(ev: Evaluator, cfg: ConfigBundle, rules: dict[str, RuleResult], hard_stops) -> dict[str, list[Finding]]:
    def questions(r: RuleResult, *statuses: AnswerStatus) -> list[str]:
        return [q for q in r.input_ids if q in ev.questions and ev.answer_status(q) in statuses]

    def open_elements(r: RuleResult) -> list[str]:
        return [
            ref.removeprefix("element:")
            for ref in r.evidence_refs
            if ref.startswith("element:")
            and ev.element_state(ref.removeprefix("element:")) in (None, RuleElementState.UNCERTAIN)
        ]

    gaps, reviews, remediations, pending = [], [], [], []
    for rid, r in rules.items():
        if cfg.rule(rid).family == "OUT":
            continue
        if (r.gap and RuleEffect.EVIDENCE_GAP in r.gap_effects) or (r.fired and RuleEffect.EVIDENCE_GAP in r.effects):
            ids = questions(r, AnswerStatus.MISSING, AnswerStatus.UNRESOLVED) or open_elements(r) or r.input_ids
            gaps.append(Finding(rule_id=rid, message="Evidence gap: material information missing or unknown", ids=ids))
        if r.review or RuleEffect.VERIFICATION_REQUEST in r.effects or RuleEffect.VERIFICATION_REQUEST in r.gap_effects:
            ids = questions(r, AnswerStatus.NOT_APPLICABLE) + open_elements(r)
            reviews.append(Finding(rule_id=rid, message="To be verified (does not block the outcome)", ids=ids))
        if r.fired and RuleEffect.REMEDIATION_REQUIRED in r.effects and not ev.remediation_resolved(rid):
            remediations.append(
                Finding(rule_id=rid, message="Remediation required before pilot/deployment", ids=r.linked_mitigation_ids)
            )
        if r.human_gate is HumanGate.REQUIRED:
            hs = hard_stops.get(rid)
            msg = (
                "Hard stop awaiting legal review"
                if hs and hs.awaiting_legal_review
                else "Hard stop open: legal evaluation of its elements required"
                if hs
                else "Human legal review pending (does not change the outcome)"
            )
            pending.append(Finding(rule_id=rid, message=msg, ids=[]))
    conditions = [
        Finding(rule_id="OUT-02", message="Condition remains (continuous mitigation)", ids=[c.removeprefix("mitigation:")])
        for c in ev.flag(EngineFlag.OPEN_CONDITION)[1]
    ]
    return {
        "evidence_gaps": gaps,
        "verification_requests": reviews,
        "open_remediations": remediations,
        "open_conditions": conditions,
        "pending_reviews": pending,
    }
