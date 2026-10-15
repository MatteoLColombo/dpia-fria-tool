"""Audit trail (06_API contract): one event per calibrated risk, per applied rule and for the outcome."""

from __future__ import annotations

from digcon.domain.enums import Module
from digcon.domain.models import AuditEvent, HsState

from .result import HardStopResult, RiskResult, RuleResult, RunContext

MODULE_BY_FAMILY = {
    "RMS": Module.ART9,
    "FRIA": Module.FRIA,
    "SEP": Module.SEP,
    "MIT": Module.MIT,
    "OUT": Module.OUTCOME,
    "FLOW": Module.CORE,
    "ROLE": Module.CORE,
    "SCOPE": Module.CORE,
    "CROSS": Module.CORE,
}


def _output(r: RuleResult) -> str:
    parts = []
    if r.fired:
        parts.append(f"FIRED case {r.case}: {','.join(e.value for e in r.effects) or 'no effect'}")
    if r.status is not None:
        parts.append(f"status={r.status.value}")
    if r.gap:
        parts.append(f"GAP: {','.join(e.value for e in r.gap_effects)}")
    if r.review:
        parts.append("REVIEW: verification requested")
    return "; ".join(parts)


def build_trail(
    *,
    ctx: RunContext,
    assessment_id: str,
    workbook_version: str,
    families: dict[str, str],
    rules: dict[str, RuleResult],
    hard_stops: dict[str, HardStopResult],
    risks: dict[str, RiskResult],
    risk_evidence: dict[str, list[str]],
    api_evaluations: dict[str, dict] | None = None,
    human_decisions: dict[str, str],
    outcome_rule: str,
    outcome: str,
) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    by_rule: dict[str, str] = {}

    def add(**kw) -> AuditEvent:
        ev = AuditEvent(
            event_id=f"{ctx.run_id}-{len(events) + 1:03d}",
            assessment_id=assessment_id,
            run_id=ctx.run_id,
            workbook_version=workbook_version,
            timestamp=ctx.timestamp,
            **kw,
        )
        events.append(ev)
        return ev

    for rid, rr in risks.items():
        add(
            module=Module.RISK,
            input_ids=[rid],
            evidence_refs=sorted({f"risk:{rid}", *risk_evidence.get(rid, [])}),
            linked_risk_ids=[rid],
            engine_output=(
                f"severity={_v(rr.severity)} initial={_v(rr.initial)} residual={_v(rr.residual)}"
                + (" reassessment required (SEP)" if rr.to_reassess else "")
            ),
        )

    for rid, r in rules.items():
        if not r.applied or families[rid] == "OUT":
            continue
        hs = hard_stops.get(rid)
        ev = add(
            module=MODULE_BY_FAMILY.get(families[rid], Module.RULE),
            rule_id=rid,
            input_ids=r.input_ids,
            evidence_refs=r.evidence_refs,
            api_evaluation=(api_evaluations or {}).get(rid),
            human_gate=r.human_gate,
            human_decision=human_decisions.get(rid),
            linked_risk_ids=r.linked_risk_ids,
            linked_mitigation_ids=r.linked_mitigation_ids,
            hs_state=HsState(hs_id=rid, state=hs.state, elements=hs.elements) if hs else None,
            engine_output=_output(r),
        )
        by_rule[rid] = ev.event_id

    out = rules[outcome_rule]
    contributors = [ref.removeprefix("rule:") for ref in out.evidence_refs if ref.startswith("rule:")]
    parent = next((by_rule[c] for c in contributors if c in by_rule), None)
    add(
        module=Module.OUTCOME,
        rule_id=outcome_rule,
        input_ids=out.input_ids,
        evidence_refs=out.evidence_refs,
        linked_risk_ids=out.linked_risk_ids,
        linked_mitigation_ids=out.linked_mitigation_ids,
        engine_output=f"{outcome} (recommended outcome, not the governance decision)",
        parent_event_id=parent,
    )
    return events


def _v(x) -> str:
    return x.value if x is not None else "—"


def audit_defects(events: list[AuditEvent]) -> list[str]:
    return [f"{e.event_id} ({e.rule_id or e.module.value}): {d}" for e in events for d in e.audit_defects()]
