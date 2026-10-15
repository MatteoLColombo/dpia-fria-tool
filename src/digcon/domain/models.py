"""Pydantic v2 models of the T17 decision engine.

Three groups:

* ``Condition`` — the small condition language used in ``config/*.yaml`` for
  triggers, evidence-gap conditions and visibility. Rules are data, not code.
* Spec models — the workbook as exported by ``tools/export_workbook.py``.
* Runtime models — the state of one assessment and its audit events.

All models reject unknown fields and out-of-enum values.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .enums import (
    UNRESOLVED_STATES,
    AnswerKind,
    AnswerState,
    DecisionEffect,
    ElementSource,
    EncodingKind,
    EngineFlag,
    HumanGate,
    HumanGateRequirement,
    MitigationAllowed,
    MitigationHierarchy,
    MitigationRequirement,
    MitigationStatus,
    MitigationTiming,
    Module,
    Phase,
    Probability,
    PropStatus,
    Reversibility,
    RiskLevel,
    Role,
    RuleEffect,
    RuleElementState,
    RuleSeverity,
    Scale,
    Scope,
    SepDecision,
    SepEffect,
    SepVulnerability,
    Severity,
)

# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------

QUESTION_ID_RE = re.compile(r"^(?:C\d{2}B?|N\d{2}|W\d{2}|Q\d{2}|FOLLOW|P\d{2}|D\d{2})$")
RULE_ID_RE = re.compile(r"^(?:HS0[1-9]|RMS-9[A-Z]|FRIA-27[A-Z]|[A-Z]+-\d{2})$")
RISK_ID_RE = re.compile(r"^RISK-\d{2}$")
MITIGATION_ID_RE = re.compile(r"^MIT-\d{3}$")
SEP_FIELD_ID_RE = re.compile(r"^SEP\d{2}A?$")
GOVERNANCE_ID_RE = re.compile(r"^G\d{2}$")
ELEMENT_ID_RE = re.compile(r"^(?:HS0[1-9]|RMS-9[A-Z]|FRIA-27[A-Z]|[A-Z]+-\d{2})\.E\d+$")

QuestionId = Annotated[str, StringConstraints(pattern=QUESTION_ID_RE.pattern)]
RuleId = Annotated[str, StringConstraints(pattern=RULE_ID_RE.pattern)]
RiskId = Annotated[str, StringConstraints(pattern=RISK_ID_RE.pattern)]
MitigationId = Annotated[str, StringConstraints(pattern=MITIGATION_ID_RE.pattern)]
SepFieldId = Annotated[str, StringConstraints(pattern=SEP_FIELD_ID_RE.pattern)]
ElementId = Annotated[str, StringConstraints(pattern=ELEMENT_ID_RE.pattern)]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class _Spec(BaseModel):
    """Immutable config model."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class _State(BaseModel):
    """Runtime model: mutable, re-validated on assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Condition language
# ---------------------------------------------------------------------------


class AllOf(_Spec):
    all: list[Condition] = Field(min_length=1)


class AnyOf(_Spec):
    any: list[Condition] = Field(min_length=1)


class NotOf(_Spec):
    not_: Condition = Field(alias="not")


# Answer conditions only look at *visible* questions: a hidden question is never
# YES, never provided and never unresolved (it is simply not asked).


class AnswerIs(_Spec):
    """Answer state (or enum value for ROLE / RISK_RATING / SINGLE / NOTIFICATION / EFFECTIVENESS) is one of ``is``."""

    q: QuestionId
    is_: list[str] = Field(alias="is", min_length=1)


class AnswerUnresolved(_Spec):
    """Visible answer missing, UNKNOWN or NOT_OWNED. Never equivalent to NO.

    N_A is not matched: it only produces a verification request (EG-01 review, AS-013).
    """

    q: QuestionId
    unresolved: Literal[True]


class AnswerProvided(_Spec):
    """Visible answer has a substantive value (text, options, enum value or YES/NO)."""

    q: QuestionId
    provided: Literal[True]


class ElementIs(_Spec):
    """Element evaluated with one of ``is``. A not-yet-evaluated element matches nothing."""

    element: ElementId
    is_: list[str] = Field(alias="is", min_length=1)


class ElementUnresolved(_Spec):
    """Element not evaluated yet, or UNCERTAIN."""

    element: ElementId
    unresolved: Literal[True]


class HardStopIs(_Spec):
    """Resolved HS state: MET only with all elements MET and the human gate COMPLETED (AS-006)."""

    hs: RuleId
    is_: list[RuleElementState] = Field(alias="is", min_length=1)


class RuleFired(_Spec):
    """At least one case of the rule matched."""

    rule: RuleId
    fired: Literal[True]


class FlagSet(_Spec):
    flag: EngineFlag


class RiskMatch(_Spec):
    """At least one risk in the case register matches *all* given filters.

    ``residual`` is the level calibrated from post-control dimensions after a verified
    reassessment; it is missing until then (never 0, never assumed lower).
    """

    risk: Literal["ANY"] | RiskId
    initial_at_least: RiskLevel | None = None
    residual_at_least: RiskLevel | None = None
    residual_missing: Literal[True] | None = None

    @model_validator(mode="after")
    def _has_filter(self) -> RiskMatch:
        if not (self.initial_at_least or self.residual_at_least or self.residual_missing):
            raise ValueError("risk condition without filters")
        return self


class MitigationMatch(_Spec):
    """At least one *activated* mitigation matches all given filters."""

    mitigation: Literal["ANY_ACTIVATED"]
    decision_effect: list[DecisionEffect] | None = None
    status_in: list[MitigationStatus] | None = None
    status_not_in: list[MitigationStatus] | None = None
    without_evidence: Literal[True] | None = None


class PropIs(_Spec):
    prop: Literal["ANY"] | RuleId
    is_: list[PropStatus] = Field(alias="is", min_length=1)


class SepIs(_Spec):
    sep: SepFieldId
    is_: list[str] = Field(alias="is", min_length=1)


Condition = Union[
    AllOf,
    AnyOf,
    NotOf,
    AnswerIs,
    AnswerUnresolved,
    AnswerProvided,
    ElementIs,
    ElementUnresolved,
    HardStopIs,
    RuleFired,
    FlagSet,
    RiskMatch,
    MitigationMatch,
    PropIs,
    SepIs,
]

for _m in (AllOf, AnyOf, NotOf):
    _m.model_rebuild()


def iter_conditions(cond: Condition | None):
    """Depth-first walk over a condition tree."""
    if cond is None:
        return
    yield cond
    if isinstance(cond, AllOf):
        for c in cond.all:
            yield from iter_conditions(c)
    elif isinstance(cond, AnyOf):
        for c in cond.any:
            yield from iter_conditions(c)
    elif isinstance(cond, NotOf):
        yield from iter_conditions(cond.not_)


# ---------------------------------------------------------------------------
# Spec models (config/*.yaml)
# ---------------------------------------------------------------------------


class ConfigMeta(_Spec):
    workbook_version: NonEmpty
    workbook_file: NonEmpty
    workbook_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    generated_by: NonEmpty


class Option(_Spec):
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9_]+$")]
    label: NonEmpty


class OptionSet(_Spec):
    id: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9_]+$")]
    source: NonEmpty
    options: list[Option] = Field(min_length=1)
    assumptions: list[str] = []


class QuestionSpec(_Spec):
    id: QuestionId
    sheet: NonEmpty
    order: int
    phase: Phase
    subsection: NonEmpty
    text: NonEmpty
    response_model: NonEmpty
    kind: AnswerKind
    states: list[AnswerState]
    option_set: str | None = None
    visibility_text: NonEmpty
    visibility: Condition | None = None  # None = always visible
    if_positive: str
    if_negative: str
    if_unresolved: str
    rule_refs_text: NonEmpty
    rule_refs: list[str]
    ra_status: NonEmpty
    assumptions: list[str] = []


class GovernanceField(_Spec):
    id: Annotated[str, StringConstraints(pattern=GOVERNANCE_ID_RE.pattern)]
    field: NonEmpty
    purpose: NonEmpty


class ElementBinding(_Spec):
    """Element state read from an answer. Anything not listed is UNCERTAIN."""

    q: QuestionId
    met_when: list[str] = Field(min_length=1)
    not_met_when: list[str] = []


class RuleElementSpec(_Spec):
    id: ElementId
    text: NonEmpty
    source: ElementSource
    state_enum: Literal["RuleElementState", "PropStatus"] = "RuleElementState"
    legal_judgement: bool = False
    non_remediability: bool = False
    binding: ElementBinding | None = None
    requires_verified_mitigation: bool = False

    @model_validator(mode="after")
    def _binding_matches_source(self) -> RuleElementSpec:
        if (self.source is ElementSource.ANSWER) != (self.binding is not None):
            raise ValueError(f"{self.id}: binding is required for ANSWER elements and forbidden otherwise")
        return self


class RuleCase(_Spec):
    """One branch of a rule. Cases are tried in order; the first match wins."""

    when: Condition
    effects: list[RuleEffect] = []
    status: PropStatus | None = None  # PROP-* rules only


class RuleEncoding(_Spec):
    """Hand-coded structure of a prose trigger (tools/encodings/rules.yaml).

    The rule *fires* when one of ``cases`` matches. ``gap`` is evaluated on its own
    and carries the missing/unknown treatment of the workbook. ``review`` flags manual
    checks still to do: a non-blocking verification request (AS-013).
    """

    kind: EncodingKind
    inputs: list[QuestionId] = []
    cases: list[RuleCase] = []
    gap: Condition | None = None
    gap_effects: list[RuleEffect] = []
    review: Condition | None = None
    elements: list[RuleElementSpec] = []
    hs_referral: RuleId | None = None
    routes_to: list[RuleId] = []
    outcome: Literal["O1", "O2", "O3", "O4", "O5"] | None = None
    assumptions: list[str] = []
    note: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> RuleEncoding:
        if self.kind is EncodingKind.SYSTEM and (self.cases or self.gap or self.review):
            raise ValueError("SYSTEM rules have no cases or gap")
        if self.kind is not EncodingKind.SYSTEM and not self.cases:
            raise ValueError("non-SYSTEM rules need at least one case")
        if (self.gap is None) != (not self.gap_effects):
            raise ValueError("gap and gap_effects go together")
        return self


class RuleSpec(_Spec):
    id: RuleId
    family: NonEmpty
    order: int
    source: NonEmpty
    links_text: NonEmpty
    link_ids: list[str]
    actor: NonEmpty
    trigger_text: NonEmpty
    missing_treatment: NonEmpty
    consequence_class: NonEmpty
    severity: RuleSeverity
    severity_text: NonEmpty
    flow_effect: NonEmpty
    can_produce_o5: bool
    human_gate: HumanGateRequirement
    human_gate_text: NonEmpty
    ra_note: NonEmpty
    sep_implication: NonEmpty
    mitigation_allowed: MitigationAllowed
    mitigation_allowed_text: NonEmpty
    mitigation_action: NonEmpty
    remediability: NonEmpty
    related_text: str | None = None
    related_ids: list[str] = []
    encoding: RuleEncoding


class LegacyProfile(_Spec):
    """RA reference profile of 04 — kept for traceability, never an engine input."""

    text: NonEmpty
    scale: Scale
    scope: Scope
    reversibility: Reversibility
    probability: Probability
    reference_risk: RiskLevel
    provisional_residual_text: str | None = None


class RiskSpec(_Spec):
    id: RiskId
    label: str | None = None
    order: int
    source_text: NonEmpty
    core_questions: list[QuestionId]
    provider_questions: list[QuestionId]
    deployer_questions: list[QuestionId]
    actor: NonEmpty
    right: NonEmpty
    groups: NonEmpty
    harm_scenarios: list[NonEmpty] = Field(min_length=1)
    safeguards_to_verify: NonEmpty
    candidate_mitigation_text: NonEmpty
    rule_links_text: NonEmpty
    rule_links: list[str]
    human_review_text: NonEmpty
    template_status: NonEmpty
    sep_relevance: NonEmpty
    mitigation_ids: list[MitigationId]
    prop_rules: list[RuleId]
    legacy: LegacyProfile


class CalibrationSpec(_Spec):
    """04_RISK_ANALYSIS: severity = MAX(scale, scope, reversibility); level = matrix[severity][probability]."""

    rule_text: NonEmpty
    control_effect_text: NonEmpty
    scale: list[Scale] = Field(min_length=4, max_length=4)
    scope: list[Scope] = Field(min_length=4, max_length=4)
    reversibility: list[Reversibility] = Field(min_length=4, max_length=4)
    probability: list[Probability] = Field(min_length=4, max_length=4)
    matrix: dict[Severity, dict[Probability, RiskLevel]]

    @model_validator(mode="after")
    def _complete(self) -> CalibrationSpec:
        if set(self.matrix) != set(Severity):
            raise ValueError("calibration matrix must have one row per severity")
        for sev, row in self.matrix.items():
            if set(row) != set(Probability):
                raise ValueError(f"calibration row {sev.value} must have one column per probability")
        return self


class MitigationSpec(_Spec):
    id: MitigationId
    order: int
    source_type: NonEmpty
    source_ids_text: NonEmpty
    risk_id: RiskId
    source_rule: RuleId
    sep_ref: str | None = None
    harm: NonEmpty
    rights: NonEmpty
    trigger: NonEmpty
    measure: NonEmpty
    hierarchy: MitigationHierarchy
    measure_type: NonEmpty
    responsible_role: Literal["Provider", "Deployer", "Joint"]
    owner: NonEmpty
    timing: MitigationTiming
    timing_text: NonEmpty
    requirement: MitigationRequirement
    decision_effect: DecisionEffect
    decision_effect_text: NonEmpty
    evidence_of_implementation: NonEmpty
    verification_method: NonEmpty
    closure_criterion: NonEmpty
    candidate_status: Literal["NOT ACTIVATED — CANDIDATE"]  # 05A: inactive until triggered (AS-022)
    risk_before: RiskLevel | None = None
    expected_residual_text: NonEmpty
    actual_residual: RiskLevel | None = None  # must stay empty until verified reassessment
    adequacy_text: NonEmpty
    residual_acceptable_text: NonEmpty
    review_trigger: NonEmpty
    review_date: str | None = None
    notes: NonEmpty
    expected_effect: NonEmpty
    reassessment_text: NonEmpty
    human_legal_review_text: NonEmpty
    unresolved_text: NonEmpty


class SepFieldSpec(_Spec):
    id: SepFieldId
    order: int
    field: NonEmpty
    question: NonEmpty
    response_model: NonEmpty
    activation: NonEmpty
    output: NonEmpty
    risk_link: str | None = None
    rule_refs_text: str | None = None
    rule_refs: list[RuleId] = []
    mitigation_link: str | None = None
    human_review: HumanGateRequirement
    human_review_text: NonEmpty
    status: NonEmpty


class SepTrigger(_Spec):
    trigger: NonEmpty
    default_consequence: NonEmpty
    automatic: bool
    notes: NonEmpty


class QuestionsFile(_Spec):
    meta: ConfigMeta
    option_sets: list[OptionSet]
    questions: list[QuestionSpec]
    governance_fields: list[GovernanceField]


class RulesFile(_Spec):
    meta: ConfigMeta
    outcome_precedence: list[Literal["O1", "O2", "O3", "O4", "O5"]]
    rules: list[RuleSpec]


class RisksFile(_Spec):
    meta: ConfigMeta
    calibration: CalibrationSpec
    risks: list[RiskSpec]


class MitigationsFile(_Spec):
    meta: ConfigMeta
    mitigations: list[MitigationSpec]


class SepFile(_Spec):
    meta: ConfigMeta
    purpose: NonEmpty
    fields: list[SepFieldSpec]
    triggers: list[SepTrigger]


class ConfigBundle(_Spec):
    """Everything the runtime reads from ``config/``."""

    version: NonEmpty
    questions: QuestionsFile
    rules: RulesFile
    risks: RisksFile
    mitigations: MitigationsFile
    sep: SepFile

    def question(self, qid: str) -> QuestionSpec:
        return _by_id(self.questions.questions, qid)

    def rule(self, rid: str) -> RuleSpec:
        return _by_id(self.rules.rules, rid)

    def risk(self, rid: str) -> RiskSpec:
        return _by_id(self.risks.risks, rid)

    def mitigation(self, mid: str) -> MitigationSpec:
        return _by_id(self.mitigations.mitigations, mid)


def _by_id(items, item_id: str):
    for item in items:
        if item.id == item_id:
            return item
    raise KeyError(item_id)


# ---------------------------------------------------------------------------
# Runtime models (one assessment)
# ---------------------------------------------------------------------------


class Answer(_State):
    """One answer. A question with no ``Answer`` is *missing*, which is never NO.

    * closed questions: ``state`` (YES / NO / UNKNOWN / N_A / NOT_OWNED);
    * text, options, enum-valued questions: ``value``, or an unresolved ``state``.
    """

    question_id: QuestionId
    state: AnswerState | None = None
    value: str | list[str] | None = None
    detail: str | None = None  # basis / rationale / reference accompanying the answer
    evidence_refs: list[NonEmpty] = []

    @model_validator(mode="after")
    def _consistent(self) -> Answer:
        has_value = bool(self.value.strip()) if isinstance(self.value, str) else bool(self.value)
        if self.state is None and not has_value:
            raise ValueError(f"{self.question_id}: an answer needs a state or a value")
        if self.state in UNRESOLVED_STATES and has_value:
            raise ValueError(f"{self.question_id}: {self.state.value} cannot carry a value")
        return self


class ElementEvaluation(_State):
    """State of one rule element, set by a person now and by the API later."""

    element_id: ElementId
    state: RuleElementState | PropStatus
    source: ElementSource = ElementSource.MANUAL
    evidence_refs: list[NonEmpty] = []
    rationale: str | None = None
    provenance: str | None = None  # source API only: provider, model, prompt and schema versions


class HumanGateRecord(_State):
    rule_id: RuleId
    gate: HumanGate
    decision: str | None = None
    decided_by: str | None = None
    reference: str | None = None

    @model_validator(mode="after")
    def _completed_has_decision(self) -> HumanGateRecord:
        if self.gate is HumanGate.COMPLETED and not (self.decision and self.decided_by):
            raise ValueError(f"{self.rule_id}: a COMPLETED gate needs decision and decided_by")
        return self


class RiskAssessment(_State):
    """Case-specific variables of one RISK-*. Residual dimensions only after verification."""

    risk_id: RiskId
    scale: Scale | None = None
    scope: Scope | None = None
    reversibility: Reversibility | None = None
    probability: Probability | None = None
    residual_scale: Scale | None = None
    residual_scope: Scope | None = None
    residual_reversibility: Reversibility | None = None
    residual_probability: Probability | None = None
    evidence_refs: list[NonEmpty] = []
    notes: str | None = None


class MitigationRecord(_State):
    mitigation_id: MitigationId
    activated: bool = False
    status: MitigationStatus = MitigationStatus.PROPOSED
    owner: str | None = None
    decision_effect: DecisionEffect | None = None  # None = as in the plan
    linked_risk_ids: list[RiskId] = []
    linked_rule_ids: list[RuleId] = []
    evidence_refs: list[NonEmpty] = []
    verification_ref: str | None = None
    notes: str | None = None


class SepRecord(_State):
    decision: SepDecision | None = None  # SEP00
    vulnerability: SepVulnerability | None = None  # SEP03
    effect: SepEffect | None = None  # SEP09
    effect_risk_ids: list[RiskId] = []
    new_risk: AnswerState | None = None  # SEP10
    new_mitigation: AnswerState | None = None  # SEP11
    texts: dict[Annotated[str, StringConstraints(pattern=SEP_FIELD_ID_RE.pattern)], str] = {}
    evidence_refs: list[NonEmpty] = []


class GovernanceRecord(_State):
    """G01–G05: filled by a person, never by the engine."""

    g01_decision: str | None = None
    g02_decision_maker: str | None = None
    g03_review_date: str | None = None
    g04_conditions: str | None = None
    g05_reasoning: str | None = None


class AssessmentState(_State):
    assessment_id: NonEmpty
    workbook_version: NonEmpty
    answers: dict[QuestionId, Answer] = {}
    elements: dict[ElementId, ElementEvaluation] = {}
    human_gates: dict[RuleId, HumanGateRecord] = {}
    risks: dict[RiskId, RiskAssessment] = {}
    mitigations: dict[MitigationId, MitigationRecord] = {}
    sep: SepRecord = SepRecord()
    governance: GovernanceRecord = GovernanceRecord()

    @model_validator(mode="after")
    def _keys_match(self) -> AssessmentState:
        for key, item, attr in (
            *((k, v, "question_id") for k, v in self.answers.items()),
            *((k, v, "element_id") for k, v in self.elements.items()),
            *((k, v, "rule_id") for k, v in self.human_gates.items()),
            *((k, v, "risk_id") for k, v in self.risks.items()),
            *((k, v, "mitigation_id") for k, v in self.mitigations.items()),
        ):
            if getattr(item, attr) != key:
                raise ValueError(f"key {key!r} does not match {attr}={getattr(item, attr)!r}")
        return self


class HsState(_Spec):
    hs_id: RuleId
    state: RuleElementState
    elements: dict[ElementId, RuleElementState]


class AuditEvent(_Spec):
    """Minimum audit event (06_API, audit trail contract). Missing required fields → rejected."""

    event_id: NonEmpty
    assessment_id: NonEmpty
    run_id: NonEmpty
    workbook_version: NonEmpty
    timestamp: AwareDatetime
    module: Module
    input_ids: list[NonEmpty] = []
    evidence_refs: list[NonEmpty] = []
    rule_id: RuleId | None = None
    api_evaluation: dict | None = None
    human_gate: HumanGate | None = None
    human_decision: str | None = None
    linked_risk_ids: list[RiskId] = []
    linked_mitigation_ids: list[MitigationId] = []
    hs_state: HsState | None = None
    engine_output: str | None = None
    parent_event_id: str | None = None

    def audit_defects(self) -> list[str]:
        """Defects that make a rule event non-closing (fixture AUD-T01)."""
        defects: list[str] = []
        if self.rule_id is not None and not self.evidence_refs:
            defects.append("rule event without evidence_refs")
        if self.module is Module.OUTCOME and not self.engine_output:
            defects.append("terminal event without engine_output")
        if self.human_gate is HumanGate.COMPLETED and not self.human_decision:
            defects.append("completed human gate without human_decision")
        return defects
