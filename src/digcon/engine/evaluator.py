"""Evaluation of config conditions over one assessment state.

Pure and deterministic: everything is derived from (ConfigBundle, AssessmentState),
memoised per run, iterated in config order. Rule cross-references are resolved lazily;
a cycle is a config error and raises EngineError.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from digcon.domain.enums import (
    RISK_LEVEL_ORDER,
    AnswerState,
    DecisionEffect,
    ElementSource,
    EncodingKind,
    EngineFlag,
    HumanGate,
    MitigationStatus,
    PropStatus,
    RiskLevel,
    RuleEffect,
    RuleElementState,
    SepEffect,
)
from digcon.domain.models import (
    AllOf,
    AnswerIs,
    AnswerProvided,
    AnswerUnresolved,
    AnyOf,
    AssessmentState,
    ConfigBundle,
    ElementIs,
    ElementUnresolved,
    FlagSet,
    HardStopIs,
    MitigationMatch,
    MitigationRecord,
    NotOf,
    PropIs,
    RiskMatch,
    RuleFired,
    SepIs,
    iter_conditions,
)

from .calibration import risk_level
from .result import RiskResult

HARD_STOPS = tuple(f"HS0{i}" for i in range(1, 10))
VERIFIED = (MitigationStatus.VERIFIED_EFFECTIVE, MitigationStatus.VERIFIED_INEFFECTIVE)


class EngineError(RuntimeError):
    pass


class AnswerStatus(Enum):
    HIDDEN = "HIDDEN"
    MISSING = "MISSING"
    UNRESOLVED = "UNRESOLVED"  # UNKNOWN / NOT_OWNED
    NOT_APPLICABLE = "NOT_APPLICABLE"  # N_A
    PROVIDED = "PROVIDED"


@dataclass
class RuleEval:
    fired: bool = False
    case: int | None = None
    effects: tuple[RuleEffect, ...] = ()
    status: PropStatus | None = None
    gap: bool = False
    gap_effects: tuple[RuleEffect, ...] = ()
    review: bool = False
    refs: set[str] = field(default_factory=set)
    risks: set[str] = field(default_factory=set)
    mitigations: set[str] = field(default_factory=set)


@dataclass
class _Trace:
    refs: set[str] = field(default_factory=set)
    risks: set[str] = field(default_factory=set)
    mitigations: set[str] = field(default_factory=set)


class Evaluator:
    def __init__(self, cfg: ConfigBundle, state: AssessmentState, *, count_pending_api: bool = False) -> None:
        self.cfg = cfg
        self.state = state
        # An API value no person has confirmed or changed yet counts as not evaluated (AS-040), except
        # in the API benchmark, which measures what the model's values would do to the outcome.
        self.count_pending_api = count_pending_api
        self.questions = {q.id: q for q in cfg.questions.questions}
        self.rule_specs = {r.id: r for r in cfg.rules.rules}
        self.element_specs = {e.id: (r.id, e) for r in cfg.rules.rules for e in r.encoding.elements}
        self.mitigation_specs = {m.id: m for m in cfg.mitigations.mitigations}
        self.warnings: list[str] = []
        self._visible: dict[str, bool] = {}
        self._rules: dict[str, RuleEval] = {}
        self._partial: dict[str, bool] = {}
        self._flags: dict[EngineFlag, tuple[bool, list[str]]] = {}
        self._busy: set[str] = set()
        self._stack: list[_Trace | None] = []
        self._flag_readers = self._find_flag_readers()
        self.risks = self._calibrate_risks()

    # -- bookkeeping -------------------------------------------------------------------

    def _enter(self, key: str) -> None:
        if key in self._busy:
            raise EngineError(f"dependency cycle through {key}")
        self._busy.add(key)

    def _note(self, ref: str | None = None, risk: str | None = None, mitigation: str | None = None, extra=()) -> None:
        trace = self._stack[-1] if self._stack else None
        if trace is None:
            return
        if ref:
            trace.refs.add(ref)
        trace.refs.update(extra)
        if risk:
            trace.risks.add(risk)
        if mitigation:
            trace.mitigations.add(mitigation)

    def _warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)

    def _find_flag_readers(self) -> dict[EngineFlag, set[str]]:
        readers: dict[EngineFlag, set[str]] = {f: set() for f in EngineFlag}
        for r in self.cfg.rules.rules:
            enc = r.encoding
            for cond in [c.when for c in enc.cases] + [enc.gap, enc.review]:
                for node in iter_conditions(cond):
                    if isinstance(node, FlagSet):
                        readers[node.flag].add(r.id)
        return readers

    # -- answers -----------------------------------------------------------------------

    def visible(self, qid: str) -> bool:
        if qid not in self._visible:
            q = self.questions[qid]
            self._enter(f"visible:{qid}")
            self._stack.append(None)  # visibility reads are not evidence of the calling rule
            try:
                self._visible[qid] = q.visibility is None or self.cond(q.visibility)
            finally:
                self._stack.pop()
                self._busy.discard(f"visible:{qid}")
        return self._visible[qid]

    def answer_status(self, qid: str) -> AnswerStatus:
        if not self.visible(qid):
            return AnswerStatus.HIDDEN
        if qid == 'C31' and self.state.alternatives_review is not None:
            from digcon.domain.alternatives import decision
            return AnswerStatus.UNRESOLVED if decision(self.state) == 'MISSING_EVIDENCE' else AnswerStatus.PROVIDED
        ans = self.state.answers.get(qid)
        if ans is None:
            return AnswerStatus.MISSING
        if ans.state in (AnswerState.UNKNOWN, AnswerState.NOT_OWNED):
            return AnswerStatus.UNRESOLVED
        if ans.state is AnswerState.N_A:
            return AnswerStatus.NOT_APPLICABLE
        return AnswerStatus.PROVIDED

    def answer_values(self, qid: str) -> set[str]:
        if qid == 'C31' and self.state.alternatives_review is not None:
            from digcon.domain.alternatives import decision
            return {'UNKNOWN'} if decision(self.state) == 'MISSING_EVIDENCE' else {'YES'}
        ans = self.state.answers.get(qid)
        if ans is None or not self.visible(qid):
            return set()
        if ans.state is not None:
            return {ans.state.value}
        if isinstance(ans.value, list):
            return set(ans.value)
        return {ans.value} if ans.value else set()

    def _note_answer(self, qid: str) -> None:
        if qid == 'C31' and self.state.alternatives_review is not None:
            self._note('alternatives_review:C31', extra=self.state.alternatives_review.evidence_refs)
        status = self.answer_status(qid)
        if status is AnswerStatus.HIDDEN:
            return
        ans = self.state.answers.get(qid)
        if ans is None:
            self._note(f"question:{qid}")
        else:
            self._note(f"answer:{qid}", extra=ans.evidence_refs)

    # -- elements and hard stops --------------------------------------------------------

    def element_state(self, eid: str) -> RuleElementState | PropStatus | None:
        """Effective state; None = not evaluated yet. ANSWER elements are read from their question."""
        if eid == 'PROP-03.E1' and self.state.alternatives_review is not None:
            from digcon.domain.alternatives import decision
            self._note('alternatives_review:C31', extra=self.state.alternatives_review.evidence_refs)
            return {'SUFFICIENT': RuleElementState.NOT_MET,
                    'UNJUSTIFIED_EXCLUSION': RuleElementState.MET}.get(decision(self.state), RuleElementState.UNCERTAIN)
        rule_id, spec = self.element_specs[eid]
        if spec.source is ElementSource.ANSWER:
            b = spec.binding
            values = self.answer_values(b.q) if self.answer_status(b.q) is AnswerStatus.PROVIDED else set()
            self._note_answer(b.q)
            if values & set(b.met_when):
                st: RuleElementState | PropStatus | None = RuleElementState.MET
            elif values & set(b.not_met_when):
                st = RuleElementState.NOT_MET
            else:
                st = RuleElementState.UNCERTAIN
        else:
            ev = self.state.elements.get(eid)
            if ev is not None and ev.source is ElementSource.API and not self.count_pending_api:
                ev = None  # awaiting a person: "to verify", like a check nobody has filled in
            st = ev.state if ev else None
            if ev:
                self._note(f"element:{eid}", extra=ev.evidence_refs)
        if st is RuleElementState.MET and spec.requires_verified_mitigation and not self.hs_has_verified_mitigation(rule_id):
            self._warn(f"{eid} recorded as MET but no activated mitigation linked to {rule_id} is verified: kept UNCERTAIN (AS-018)")
            st = RuleElementState.UNCERTAIN
        return st

    def gate(self, rule_id: str) -> HumanGate | None:
        rec = self.state.human_gates.get(rule_id)
        return rec.gate if rec else None

    def hs_elements(self, hs_id: str) -> dict[str, RuleElementState]:
        out = {}
        for el in self.rule_specs[hs_id].encoding.elements:
            st = self.element_state(el.id)
            out[el.id] = st if isinstance(st, RuleElementState) else RuleElementState.UNCERTAIN
        return out

    def hs_state(self, hs_id: str) -> RuleElementState:
        """MET / NOT_MET only once the legal gate is COMPLETED (AS-006, AS-029). UNCERTAIN is never MET."""
        states = list(self.hs_elements(hs_id).values())
        self._note(f"rule:{hs_id}")
        if self.gate(hs_id) is not HumanGate.COMPLETED:
            return RuleElementState.UNCERTAIN
        if all(s is RuleElementState.MET for s in states):
            return RuleElementState.MET
        if any(s is RuleElementState.NOT_MET for s in states):
            return RuleElementState.NOT_MET
        return RuleElementState.UNCERTAIN

    # -- mitigations ---------------------------------------------------------------------

    def activated(self) -> list[MitigationRecord]:
        return [m for m in self.state.mitigations.values() if m.activated]

    def decision_effect(self, rec: MitigationRecord) -> DecisionEffect:
        return rec.decision_effect or self.mitigation_specs[rec.mitigation_id].decision_effect

    def linked_risks(self, rec: MitigationRecord) -> set[str]:
        return {self.mitigation_specs[rec.mitigation_id].risk_id, *rec.linked_risk_ids}

    def hs_has_verified_mitigation(self, hs_id: str) -> bool:
        return any(hs_id in m.linked_rule_ids and m.status in VERIFIED for m in self.activated())

    def remediation_resolved(self, rule_id: str) -> bool:
        """AS-016 / AS-030: closed only by a linked, activated, VERIFIED_EFFECTIVE mitigation."""
        if rule_id == 'PROP-03' and self.state.alternatives_review is not None:
            from digcon.domain.alternatives import decision
            if decision(self.state) == 'UNJUSTIFIED_EXCLUSION':
                return False  # revise the substantive determination; a plan approval is insufficient
        from digcon.domain.action_plan import approved
        if not approved(self.state, rule_id):
            return False
        return any(
            rule_id in m.linked_rule_ids and m.status is MitigationStatus.VERIFIED_EFFECTIVE for m in self.activated()
        )

    # -- risks ---------------------------------------------------------------------------

    def _calibrate_risks(self) -> dict[str, RiskResult]:
        cal = self.cfg.risks.calibration
        sep = self.state.sep
        reassess = set(sep.effect_risk_ids) if sep.effect in (SepEffect.MODIFY, SepEffect.CONTRADICT, SepEffect.NEW_ISSUE) else set()
        out: dict[str, RiskResult] = {}
        for spec in self.cfg.risks.risks:
            ra = self.state.risks.get(spec.id)
            if ra is None:
                continue
            sev, initial = risk_level(cal, ra.scale, ra.scope, ra.reversibility, ra.probability)
            r_sev, residual = risk_level(
                cal, ra.residual_scale, ra.residual_scope, ra.residual_reversibility, ra.residual_probability
            )
            if residual is not None:
                from digcon.domain.action_plan import residual_approved
                review = self.state.residual_reviews.get(spec.id)
                verified = residual_approved(self.state, spec.id) and any(
                    m.mitigation_id in review.mitigation_ids and spec.id in self.linked_risks(m) and m.status is MitigationStatus.VERIFIED_EFFECTIVE
                    for m in self.activated()
                )
                if not verified:
                    self._warn(
                        f"{spec.id}: residual dimensions ignored — no current documented residual review with a linked "
                        "VERIFIED_EFFECTIVE measure (residual risk stays empty)"
                    )
                    r_sev, residual = None, None
            out[spec.id] = RiskResult(
                risk_id=spec.id,
                severity=sev,
                initial=initial,
                residual_severity=r_sev,
                residual=residual,
                to_reassess=spec.id in reassess,
            )
        return out

    # -- conditions ----------------------------------------------------------------------

    def cond(self, c) -> bool:
        if isinstance(c, AllOf):
            return all(self.cond(x) for x in c.all)
        if isinstance(c, AnyOf):
            return any(self.cond(x) for x in c.any)
        if isinstance(c, NotOf):
            return not self.cond(c.not_)
        if isinstance(c, AnswerIs):
            self._note_answer(c.q)
            return bool(self.answer_values(c.q) & set(c.is_))
        if isinstance(c, AnswerUnresolved):
            self._note_answer(c.q)
            return self.answer_status(c.q) in (AnswerStatus.MISSING, AnswerStatus.UNRESOLVED)
        if isinstance(c, AnswerProvided):
            self._note_answer(c.q)
            return self.answer_status(c.q) is AnswerStatus.PROVIDED
        if isinstance(c, ElementIs):
            st = self.element_state(c.element)
            return st is not None and st.value in c.is_
        if isinstance(c, ElementUnresolved):
            st = self.element_state(c.element)
            if st is None:
                self._note(f"element:{c.element}")
            return st is None or st is RuleElementState.UNCERTAIN
        if isinstance(c, HardStopIs):
            return self.hs_state(c.hs) in c.is_
        if isinstance(c, RuleFired):
            self._note(f"rule:{c.rule}")
            if c.rule in self._partial:
                return self._partial[c.rule]
            return self.rule(c.rule).fired
        if isinstance(c, FlagSet):
            value, contributors = self.flag(c.flag)
            self._note(f"flag:{c.flag.value}={'true' if value else 'false'}", extra=contributors)
            return value
        if isinstance(c, RiskMatch):
            return self._risk_match(c)
        if isinstance(c, MitigationMatch):
            return self._mitigation_match(c)
        if isinstance(c, PropIs):
            return self._prop_is(c)
        if isinstance(c, SepIs):
            return self._sep_is(c)
        raise EngineError(f"unknown condition {type(c).__name__}")

    def _risk_match(self, c: RiskMatch) -> bool:
        hit = False
        for rid, rr in self.risks.items():
            if c.risk != "ANY" and rid != c.risk:
                continue
            ok = True
            if c.initial_at_least is not None:
                ok &= rr.initial is not None and _ge(rr.initial, c.initial_at_least)
            if c.residual_at_least is not None:
                ok &= rr.residual is not None and _ge(rr.residual, c.residual_at_least)
            if c.residual_missing:
                ok &= rr.residual is None
            if ok:
                hit = True
                ra = self.state.risks[rid]
                self._note(f"risk:{rid}", risk=rid, extra=ra.evidence_refs)
        return hit

    def _mitigation_match(self, c: MitigationMatch) -> bool:
        hit = False
        for m in self.activated():
            if c.decision_effect is not None and self.decision_effect(m) not in c.decision_effect:
                continue
            if c.status_in is not None and m.status not in c.status_in:
                continue
            if c.status_not_in is not None and m.status in c.status_not_in:
                continue
            if c.without_evidence and m.evidence_refs:
                continue
            hit = True
            self._note(f"mitigation:{m.mitigation_id}", mitigation=m.mitigation_id, extra=m.evidence_refs)
        return hit

    def _prop_is(self, c: PropIs) -> bool:
        targets = (
            [r.id for r in self.cfg.rules.rules if any(case.status for case in r.encoding.cases)]
            if c.prop == "ANY"
            else [c.prop]
        )
        hit = False
        for rid in targets:
            status = self.rule(rid).status
            if status is not None and status in c.is_:
                hit = True
                self._note(f"rule:{rid}")
        return hit

    def _sep_is(self, c: SepIs) -> bool:
        sep = self.state.sep
        value = {
            "SEP00": sep.decision,
            "SEP03": sep.vulnerability,
            "SEP09": sep.effect,
            "SEP10": sep.new_risk,
            "SEP11": sep.new_mitigation,
        }.get(c.sep)
        if value is None:
            return False
        self._note(f"sep:{c.sep}", extra=sep.evidence_refs)
        return value.value in c.is_

    # -- rules ---------------------------------------------------------------------------

    def rule(self, rid: str) -> RuleEval:
        if rid in self._rules:
            return self._rules[rid]
        spec = self.rule_specs[rid]
        enc = spec.encoding
        self._enter(rid)
        trace = _Trace()
        self._stack.append(trace)
        try:
            ev = RuleEval()
            if enc.kind is not EncodingKind.SYSTEM:
                for i, case in enumerate(enc.cases, 1):
                    if self.cond(case.when):
                        ev.fired, ev.case, ev.effects, ev.status = True, i, tuple(case.effects), case.status
                        break
                self._partial[rid] = ev.fired
                if enc.gap is not None and self.cond(enc.gap):
                    ev.gap, ev.gap_effects = True, tuple(enc.gap_effects)
                if enc.review is not None and self.cond(enc.review):
                    ev.review = True
            ev.refs, ev.risks, ev.mitigations = trace.refs, trace.risks, trace.mitigations
        finally:
            self._stack.pop()
            self._busy.discard(rid)
            self._partial.pop(rid, None)
        self._rules[rid] = ev
        return ev

    def substantive_rules(self, reading: EngineFlag | None = None, producing: RuleEffect | None = None) -> list[str]:
        """Non-OUT rules, excluding those that read the flag being computed.

        With ``producing``, only rules that can emit that effect at all (from the config, before
        evaluation): a flag never evaluates rules that cannot contribute to it, so derived rules
        reading different flags do not depend on each other.
        """
        skip = self._flag_readers[reading] if reading else set()
        return [
            r.id
            for r in self.cfg.rules.rules
            if r.family != "OUT"
            and r.id not in skip
            and (producing is None or producing in {e for c in r.encoding.cases for e in c.effects} | set(r.encoding.gap_effects))
        ]

    def flag(self, f: EngineFlag) -> tuple[bool, list[str]]:
        if f in self._flags:
            return self._flags[f]
        self._enter(f"flag:{f.value}")
        self._stack.append(None)
        try:
            contributors = self._flag_contributors(f)
        finally:
            self._stack.pop()
            self._busy.discard(f"flag:{f.value}")
        self._flags[f] = (bool(contributors), contributors)
        return self._flags[f]

    def _flag_contributors(self, f: EngineFlag) -> list[str]:
        if f is EngineFlag.VISIBLE_QUESTION_UNRESOLVED:
            return [
                f"question:{q.id}"
                for q in self.cfg.questions.questions
                if self.answer_status(q.id) in (AnswerStatus.MISSING, AnswerStatus.UNRESOLVED)
            ]
        if f is EngineFlag.VISIBLE_QUESTION_NOT_APPLICABLE:
            return [
                f"question:{q.id}"
                for q in self.cfg.questions.questions
                if self.answer_status(q.id) is AnswerStatus.NOT_APPLICABLE
            ]
        if f is EngineFlag.HS_MET:
            return [f"rule:{hs}" for hs in HARD_STOPS if self.hs_state(hs) is RuleElementState.MET]
        if f is EngineFlag.OPEN_CONDITION:
            return [
                f"mitigation:{m.mitigation_id}"
                for m in self.activated()
                if self.decision_effect(m) is DecisionEffect.CONTINUOUS_CONDITION
                and m.status is not MitigationStatus.NOT_APPLICABLE
            ]
        if f is EngineFlag.REMEDIATION_TRIGGERED:
            rules = self.substantive_rules(f, RuleEffect.REMEDIATION_REQUIRED)
            return [f"rule:{r}" for r in rules if RuleEffect.REMEDIATION_REQUIRED in self.rule(r).effects]
        if f is EngineFlag.RISK_INPUT_TRIGGERED:
            rules = self.substantive_rules(f, RuleEffect.RISK_INPUT)
            return [f"rule:{r}" for r in rules if RuleEffect.RISK_INPUT in self.rule(r).effects]
        if f is EngineFlag.OPEN_REQUIRED_REMEDIATION:
            rules = self.substantive_rules(f, RuleEffect.REMEDIATION_REQUIRED)
            return [
                f"rule:{r}"
                for r in rules
                if RuleEffect.REMEDIATION_REQUIRED in self.rule(r).effects and not self.remediation_resolved(r)
            ]
        if f is EngineFlag.MATERIAL_EVIDENCE_GAP:
            rules = self.substantive_rules(f, RuleEffect.EVIDENCE_GAP)
            return [f"rule:{r}" for r in rules if self.is_material_gap(r)]
        raise EngineError(f"unknown flag {f}")

    def is_material_gap(self, rid: str) -> bool:
        ev = self.rule(rid)
        return (ev.fired and RuleEffect.EVIDENCE_GAP in ev.effects) or (
            ev.gap and RuleEffect.EVIDENCE_GAP in ev.gap_effects
        )


def _ge(a: RiskLevel, b: RiskLevel) -> bool:
    return RISK_LEVEL_ORDER[a] >= RISK_LEVEL_ORDER[b]
