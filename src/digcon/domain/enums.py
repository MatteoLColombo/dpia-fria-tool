"""Closed enums of the T17 decision engine.

Code uses UPPER_SNAKE members only. Workbook / interface labels such as
``NOT DEMONSTRATED`` or ``IMPLEMENTED — UNVERIFIED`` are mapped in exactly one
place (``_LABELS`` below). Any value outside an enum is rejected, never coerced.
"""

from __future__ import annotations

from enum import Enum
from typing import TypeVar


class _Closed(Enum):
    """Enum whose JSON/YAML value is the canonical UPPER_SNAKE code.

    Deliberately not a ``str`` subclass: ``Scale.LOW`` must not equal ``Severity.LOW``
    or the plain string ``"LOW"``.
    """

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Canonical enums (06_API "normalized state contract")
# ---------------------------------------------------------------------------


class AnswerState(_Closed):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"
    N_A = "N_A"
    NOT_OWNED = "NOT_OWNED"


#: States that never mean NO: they produce an evidence gap (UNKNOWN, NOT_OWNED) or a
#: verification request (N_A) — AS-013.
UNRESOLVED_STATES: frozenset[AnswerState] = frozenset(
    {AnswerState.UNKNOWN, AnswerState.N_A, AnswerState.NOT_OWNED}
)


class Role(_Closed):
    PROVIDER = "PROVIDER"
    DEPLOYER = "DEPLOYER"
    JOINT = "JOINT"
    UNKNOWN = "UNKNOWN"


class RuleElementState(_Closed):
    MET = "MET"
    NOT_MET = "NOT_MET"
    UNCERTAIN = "UNCERTAIN"


class PropStatus(_Closed):
    SUPPORTED = "SUPPORTED"
    NOT_DEMONSTRATED = "NOT_DEMONSTRATED"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    REMEDIATION_REQUIRED = "REMEDIATION_REQUIRED"
    HUMAN_LEGAL_REVIEW = "HUMAN_LEGAL_REVIEW"


class MitigationStatus(_Closed):
    PROPOSED = "PROPOSED"
    PLANNED = "PLANNED"
    IN_IMPLEMENTATION = "IN_IMPLEMENTATION"
    IMPLEMENTED_UNVERIFIED = "IMPLEMENTED_UNVERIFIED"
    VERIFIED_EFFECTIVE = "VERIFIED_EFFECTIVE"
    VERIFIED_INEFFECTIVE = "VERIFIED_INEFFECTIVE"
    CLOSED = "CLOSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SepEffect(_Closed):
    CONFIRM = "CONFIRM"
    MODIFY = "MODIFY"
    CONTRADICT = "CONTRADICT"
    NEW_ISSUE = "NEW_ISSUE"


class Outcome(_Closed):
    O1 = "O1"
    O2 = "O2"
    O3 = "O3"
    O4 = "O4"
    O5 = "O5"


class RiskLevel(_Closed):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class Scale(_Closed):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class Scope(_Closed):
    LIMITED = "LIMITED"
    MODERATE = "MODERATE"
    WIDE = "WIDE"
    SYSTEMIC = "SYSTEMIC"


class Reversibility(_Closed):
    REVERSIBLE = "REVERSIBLE"
    PARTLY_REVERSIBLE = "PARTLY_REVERSIBLE"
    DIFFICULT_TO_REVERSE = "DIFFICULT_TO_REVERSE"
    IRREVERSIBLE = "IRREVERSIBLE"


class Probability(_Closed):
    RARE = "RARE"
    POSSIBLE = "POSSIBLE"
    LIKELY = "LIKELY"
    VERY_LIKELY = "VERY_LIKELY"


class Severity(_Closed):
    """Impact severity on the 1–4 scale (04_RISK_ANALYSIS calibration rows)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class HumanGate(_Closed):
    """Human-gate *event* state recorded in the audit trail."""

    NO = "NO"
    REQUIRED = "REQUIRED"
    COMPLETED = "COMPLETED"


# ---------------------------------------------------------------------------
# Enums needed to represent the workbook as config
# ---------------------------------------------------------------------------


class HumanGateRequirement(_Closed):
    """Normalised 'Human gate' column of 05 / 'Human review?' of 04A (AS-005)."""

    NO = "NO"
    POSSIBLE = "POSSIBLE"
    REQUIRED = "REQUIRED"


class RuleSeverity(_Closed):
    """'Severity' column of 05_REGOLE_HS."""

    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    HARD_STOP = "HARD_STOP"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BY_RISK = "BY_RISK"
    BY_SOURCE_RULE = "BY_SOURCE_RULE"


class MitigationAllowed(_Closed):
    YES = "YES"
    NO = "NO"
    CONDITIONAL = "CONDITIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BEFORE_HS_ONLY = "BEFORE_HS_ONLY"


class Phase(_Closed):
    INTRO = "INTRO"
    WHAT = "WHAT"
    HOW = "HOW"
    WHY = "WHY"
    PROVIDER = "PROVIDER"
    DEPLOYER = "DEPLOYER"


class Module(_Closed):
    """Audit-trail module (06_API, closed enum)."""

    CORE = "CORE"
    ART9 = "ART9"
    FRIA = "FRIA"
    SEP = "SEP"
    RISK = "RISK"
    RULE = "RULE"
    MIT = "MIT"
    OUTCOME = "OUTCOME"


class AnswerKind(_Closed):
    """How a question is answered. Derived from the 'Modello risposta' column."""

    STATE = "STATE"  # YES / NO / UNKNOWN / N_A / NOT_OWNED (subset per question)
    TEXT = "TEXT"  # free or structured text + evidence references
    REFERENCE = "REFERENCE"  # document reference + evidence references
    SINGLE = "SINGLE"  # one option from a closed option set
    MULTI = "MULTI"  # options from a closed option set
    ROLE = "ROLE"  # Role enum
    RISK_RATING = "RISK_RATING"  # RiskLevel
    RISK_ROWS = "RISK_ROWS"  # one or more concrete RISK-* ids selected via RSEL-01 (D04)
    NOTIFICATION = "NOTIFICATION"  # NotificationStatus (D10)
    EFFECTIVENESS = "EFFECTIVENESS"  # ControlEffectiveness + evidence (C43, C48)


class NotificationStatus(_Closed):
    """D10, Art. 27(3): notification of the FRIA results to the market surveillance authority."""

    TO_DO = "TO_DO"
    DONE = "DONE"
    EXEMPT_ART46_1 = "EXEMPT_ART46_1"


class ControlEffectiveness(_Closed):
    """Effectiveness status of a control against the harm scenario(s) (C43, C48). UNKNOWN is the answer state."""

    VERIFIED_EFFECTIVE = "VERIFIED_EFFECTIVE"
    INEFFECTIVE = "INEFFECTIVE"
    NOT_VERIFIED = "NOT_VERIFIED"


class SepDecision(_Closed):
    YES = "YES"
    NO = "NO"
    TO_ASSESS = "TO_ASSESS"


class SepVulnerability(_Closed):
    YES = "YES"
    NO = "NO"
    UNCERTAIN = "UNCERTAIN"


class MitigationHierarchy(_Closed):
    AVOID = "AVOID"
    MITIGATE = "MITIGATE"
    RESTORE = "RESTORE"
    COMPENSATE = "COMPENSATE"


class MitigationTiming(_Closed):
    BEFORE_DEPLOYMENT = "BEFORE_DEPLOYMENT"
    BEFORE_PILOT_AND_ON_REVIEW = "BEFORE_PILOT_AND_ON_REVIEW"
    DURING_DEPLOYMENT_CONTINUOUS = "DURING_DEPLOYMENT_CONTINUOUS"


class MitigationRequirement(_Closed):
    CONDITIONAL = "CONDITIONAL"
    HUMAN_DETERMINATION = "HUMAN_DETERMINATION"


class DecisionEffect(_Closed):
    """'Decision effect' column of 05A — drives O2/O3 in the aggregation."""

    CONTINUOUS_CONDITION = "CONTINUOUS_CONDITION"
    REQUIRED_BEFORE_DEPLOYMENT = "REQUIRED_BEFORE_DEPLOYMENT"
    HUMAN_DECISION_BEFORE_ACTIVATION = "HUMAN_DECISION_BEFORE_ACTIVATION"
    NONE_UNTIL_EVIDENCE_GAP_RESOLVED = "NONE_UNTIL_EVIDENCE_GAP_RESOLVED"


class EncodingKind(_Closed):
    """How a workbook rule trigger was turned into data (assumption register)."""

    STRUCTURED = "STRUCTURED"  # condition on answers, read directly from the workbook
    MANUAL = "MANUAL"  # needs element-level human/API evaluation (closed enum)
    DERIVED = "DERIVED"  # condition on other rule outputs / engine state
    SYSTEM = "SYSTEM"  # architectural constraint, no trigger of its own


class RuleEffect(_Closed):
    EVIDENCE_GAP = "EVIDENCE_GAP"
    VERIFICATION_REQUEST = "VERIFICATION_REQUEST"
    REMEDIATION_REQUIRED = "REMEDIATION_REQUIRED"
    SCRUTINY = "SCRUTINY"
    HUMAN_LEGAL_REVIEW = "HUMAN_LEGAL_REVIEW"
    ROUTE_TO_HS = "ROUTE_TO_HS"
    SUSPEND_ROUTING = "SUSPEND_ROUTING"
    ACTIVATE_MODULE = "ACTIVATE_MODULE"
    CLOSE_MODULE = "CLOSE_MODULE"
    RISK_INPUT = "RISK_INPUT"
    MITIGATION_REQUIRED = "MITIGATION_REQUIRED"
    SEP_ASSESSMENT = "SEP_ASSESSMENT"
    RECORD = "RECORD"
    PROP_STATUS = "PROP_STATUS"
    OUTCOME = "OUTCOME"


class ElementSource(_Closed):
    """Where a rule element's state comes from."""

    ANSWER = "ANSWER"  # bound to a question answer
    MANUAL = "MANUAL"  # filled by a person
    API = "API"  # filled by the text interpreter (interpret/ slot); a person can still override it


class EngineFlag(_Closed):
    """Aggregate engine states computed over all rule results (definitions: AS-013, AS-016, AS-022, AS-023, AS-032)."""

    VISIBLE_QUESTION_UNRESOLVED = "VISIBLE_QUESTION_UNRESOLVED"
    VISIBLE_QUESTION_NOT_APPLICABLE = "VISIBLE_QUESTION_NOT_APPLICABLE"
    REMEDIATION_TRIGGERED = "REMEDIATION_TRIGGERED"
    RISK_INPUT_TRIGGERED = "RISK_INPUT_TRIGGERED"
    HS_MET = "HS_MET"
    MATERIAL_EVIDENCE_GAP = "MATERIAL_EVIDENCE_GAP"
    OPEN_REQUIRED_REMEDIATION = "OPEN_REQUIRED_REMEDIATION"
    OPEN_CONDITION = "OPEN_CONDITION"


# ---------------------------------------------------------------------------
# Labels: the single mapping between canonical codes and workbook/UI text
# ---------------------------------------------------------------------------

_LABELS: dict[Enum, str] = {
    AnswerState.YES: "YES",
    AnswerState.NO: "NO",
    AnswerState.UNKNOWN: "UNKNOWN",
    AnswerState.N_A: "N/A",
    AnswerState.NOT_OWNED: "NOT OWNED",
    PropStatus.SUPPORTED: "SUPPORTED",
    PropStatus.NOT_DEMONSTRATED: "NOT DEMONSTRATED",
    PropStatus.EVIDENCE_GAP: "EVIDENCE GAP",
    PropStatus.REMEDIATION_REQUIRED: "REMEDIATION REQUIRED",
    PropStatus.HUMAN_LEGAL_REVIEW: "HUMAN LEGAL REVIEW",
    MitigationStatus.PROPOSED: "PROPOSED",
    MitigationStatus.PLANNED: "PLANNED",
    MitigationStatus.IN_IMPLEMENTATION: "IN IMPLEMENTATION",
    MitigationStatus.IMPLEMENTED_UNVERIFIED: "IMPLEMENTED — UNVERIFIED",
    MitigationStatus.VERIFIED_EFFECTIVE: "VERIFIED EFFECTIVE",
    MitigationStatus.VERIFIED_INEFFECTIVE: "VERIFIED INEFFECTIVE",
    MitigationStatus.CLOSED: "CLOSED",
    MitigationStatus.NOT_APPLICABLE: "NOT APPLICABLE",
    SepEffect.NEW_ISSUE: "NEW ISSUE",
    RiskLevel.VERY_LOW: "VERY LOW",
    RiskLevel.VERY_HIGH: "VERY HIGH",
    Scale.VERY_HIGH: "VERY HIGH",
    Severity.VERY_HIGH: "VERY HIGH",
    Reversibility.PARTLY_REVERSIBLE: "PARTLY REVERSIBLE",
    Reversibility.DIFFICULT_TO_REVERSE: "DIFFICULT TO REVERSE",
    Probability.VERY_LIKELY: "VERY LIKELY",
    SepDecision.TO_ASSESS: "TO ASSESS",
    NotificationStatus.TO_DO: "TO DO",
    NotificationStatus.EXEMPT_ART46_1: "EXEMPT (Art. 46(1))",
    ControlEffectiveness.VERIFIED_EFFECTIVE: "VERIFIED EFFECTIVE",
    ControlEffectiveness.NOT_VERIFIED: "NOT VERIFIED",
    RuleSeverity.HARD_STOP: "HARD STOP",
}

E = TypeVar("E", bound=Enum)


def label(member: Enum) -> str:
    """Interface/workbook label of an enum member."""
    return _LABELS.get(member, str(member.value).replace("_", " "))


def parse(enum_cls: type[E], text: str) -> E:
    """Parse a canonical code or its exact workbook label. Anything else raises ValueError."""
    if not isinstance(text, str):
        raise ValueError(f"{enum_cls.__name__}: expected a string, got {text!r}")
    candidate = text.strip()
    for member in enum_cls:
        if candidate == member.value or candidate == label(member):
            return member
    allowed = ", ".join(m.value for m in enum_cls)
    raise ValueError(f"{enum_cls.__name__}: {text!r} is not one of {allowed}")


# 1–4 ordinal of the calibration dimensions (04_RISK_ANALYSIS "Permitted engine categories").
ORDINAL: dict[Enum, int] = {
    **{m: i for i, m in enumerate(Scale, 1)},
    **{m: i for i, m in enumerate(Scope, 1)},
    **{m: i for i, m in enumerate(Reversibility, 1)},
    **{m: i for i, m in enumerate(Probability, 1)},
    **{m: i for i, m in enumerate(Severity, 1)},
}

RISK_LEVEL_ORDER: dict[RiskLevel, int] = {m: i for i, m in enumerate(RiskLevel)}
