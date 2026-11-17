"""Cross-reference and invariant checks over a ConfigBundle.

Pure: takes the bundle (and optionally the set of registered assumption IDs),
returns findings. Used by tools/export_workbook.py before writing config/ and by
the tests on the committed config.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from .enums import (
    ORDINAL,
    AnswerKind,
    ControlEffectiveness,
    DecisionEffect,
    MitigationTiming,
    EncodingKind,
    HumanGateRequirement,
    NotificationStatus,
    Phase,
    PropStatus,
    RiskLevel,
    Role,
    RuleEffect,
    RuleElementState,
    RuleSeverity,
    SepDecision,
    SepEffect,
    SepVulnerability,
    Severity,
)
from .models import (
    GOVERNANCE_ID_RE,
    MITIGATION_ID_RE,
    QUESTION_ID_RE,
    RISK_ID_RE,
    RULE_ID_RE,
    AnswerIs,
    AnswerProvided,
    ArgumentIs,
    AnswerUnresolved,
    ConfigBundle,
    ElementIs,
    ElementUnresolved,
    HardStopIs,
    PropIs,
    QuestionSpec,
    RiskMatch,
    RuleFired,
    SepIs,
    iter_conditions,
)

Level = Literal["ERROR", "WARN", "INFO"]

# Workbook v1.0.1 in numbers. A mismatch means the export read the wrong rows.
EXPECTED_PHASES = {Phase.INTRO: 7, Phase.WHAT: 7, Phase.HOW: 14, Phase.WHY: 25, Phase.PROVIDER: 10, Phase.DEPLOYER: 11}
EXPECTED_RULE_FAMILIES = {
    "PROP": 12, "RMS": 10, "FRIA": 10, "HS": 9, "FLOW": 5, "OUT": 5, "SEP": 4, "MIT": 4, "SCR": 3,
    "SYS": 3, "CROSS": 2, "EG": 1, "QUAL": 1, "ROLE": 1, "SCOPE": 1, "LEGAL": 1, "DATA": 1,
    "DQ": 1, "BIAS": 1, "TRANS": 1, "REM": 1, "RSEL": 1, "RACT": 1,
}  # fmt: skip
# Rules added by config/extension.yaml (RA-1): HS10.
EXTENSION_RULE_FAMILIES = {"HS": 1}
EXPECTED_RISKS = 11
EXPECTED_MITIGATIONS = 50
EXPECTED_SEP_FIELDS = 15
HARD_STOPS = [f"HS{i:02d}" for i in range(1, 11)]  # HS10 from the RA-1 extension
# PROP rules that return a PropStatus (PROP-11). PROP-00/-08/-11 are system / loop rules.
PROP_WITH_STATUS = ["PROP-01", "PROP-02", "PROP-03", "PROP-04", "PROP-05", "PROP-06", "PROP-07", "PROP-09", "PROP-10"]
# SEP fields that conditions may test, with their closed values (04A response models).
SEP_VALUES: dict[str, set[str]] = {
    "SEP00": set(SepDecision.__members__),
    "SEP03": set(SepVulnerability.__members__),
    "SEP09": set(SepEffect.__members__),
    "SEP10": {"YES", "NO"},
    "SEP11": {"YES", "NO"},
}

WILDCARD_RE = re.compile(r"^(RISK|MIT|SEP|PROP|EG|FRIA|RMS)-\*$|^HS\*$")


@dataclass(frozen=True)
class Finding:
    level: Level
    code: str
    subject: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.code} {self.subject}: {self.message}"


def validate_bundle(bundle: ConfigBundle, registered_assumptions: set[str] | None = None) -> list[Finding]:
    v = _Validator(bundle, registered_assumptions)
    v.run()
    return v.findings


class _Validator:
    def __init__(self, bundle: ConfigBundle, registered: set[str] | None) -> None:
        self.b = bundle
        self.registered = registered
        self.findings: list[Finding] = []
        self.questions = {q.id: q for q in bundle.questions.questions}
        self.rules = {r.id: r for r in bundle.rules.rules}
        self.risks = {r.id: r for r in bundle.risks.risks}
        self.mitigations = {m.id: m for m in bundle.mitigations.mitigations}
        self.sep_fields = {f.id: f for f in bundle.sep.fields}
        self.governance = {g.id for g in bundle.questions.governance_fields}
        self.option_sets = {o.id: o for o in bundle.questions.option_sets}
        self.elements = {e.id: (r.id, e) for r in bundle.rules.rules for e in r.encoding.elements}
        self.used_assumptions: set[str] = set()

    def add(self, level: Level, code: str, subject: str, message: str) -> None:
        self.findings.append(Finding(level, code, subject, message))

    def run(self) -> None:
        self.check_duplicates()
        self.check_counts()
        self.check_questions()
        self.check_rules()
        self.check_risks()
        self.check_mitigations()
        self.check_sep()
        self.check_calibration()
        self.check_rule_cycles()
        self.check_assumptions()

    # -- generic reference resolution ------------------------------------------------

    def ref(self, token: str, subject: str, where: str) -> None:
        """Resolve one ID-shaped token of any family."""
        if WILDCARD_RE.match(token):
            prefix = token.rstrip("*")
            pool = [*self.rules, *self.risks, *self.mitigations]
            if not any(i.startswith(prefix) for i in pool):
                self.add("ERROR", "REF-WILDCARD", subject, f"{where}: {token} matches nothing")
        elif GOVERNANCE_ID_RE.match(token):
            if token not in self.governance:
                self.add("ERROR", "REF-GOVERNANCE", subject, f"{where}: governance field {token} does not exist")
        elif QUESTION_ID_RE.match(token):
            if token not in self.questions:
                self.add("ERROR", "REF-QUESTION", subject, f"{where}: question {token} does not exist")
        elif RISK_ID_RE.match(token):
            if token not in self.risks:
                self.add("ERROR", "REF-RISK", subject, f"{where}: risk {token} does not exist")
        elif MITIGATION_ID_RE.match(token):
            if token not in self.mitigations:
                self.add("ERROR", "REF-MITIGATION", subject, f"{where}: mitigation {token} does not exist")
        elif RULE_ID_RE.match(token):
            if token not in self.rules:
                self.add("ERROR", "REF-RULE", subject, f"{where}: rule {token} does not exist")
        else:
            self.add("ERROR", "REF-UNPARSED", subject, f"{where}: {token!r} is not an ID")

    # -- checks ------------------------------------------------------------------------

    def check_duplicates(self) -> None:
        for name, items in (
            ("question", self.b.questions.questions),
            ("rule", self.b.rules.rules),
            ("risk", self.b.risks.risks),
            ("mitigation", self.b.mitigations.mitigations),
            ("sep field", self.b.sep.fields),
            ("option set", self.b.questions.option_sets),
        ):
            for item_id, n in Counter(i.id for i in items).items():
                if n > 1:
                    self.add("ERROR", "DUPLICATE-ID", item_id, f"{name} defined {n} times")
        for os_ in self.b.questions.option_sets:
            for code, n in Counter(o.code for o in os_.options).items():
                if n > 1:
                    self.add("ERROR", "DUPLICATE-ID", os_.id, f"option {code} defined {n} times")
        for el_id, n in Counter(e.id for r in self.b.rules.rules for e in r.encoding.elements).items():
            if n > 1:
                self.add("ERROR", "DUPLICATE-ID", el_id, f"element defined {n} times")

    def check_counts(self) -> None:
        phases = Counter(q.phase for q in self.b.questions.questions)
        for phase, n in EXPECTED_PHASES.items():
            if phases.get(phase, 0) != n:
                self.add("ERROR", "COUNT", f"phase {phase.value}", f"{phases.get(phase, 0)} questions, expected {n}")
        families = Counter(r.family for r in self.b.rules.rules)
        expected = Counter(EXPECTED_RULE_FAMILIES)
        if self.b.extension is not None:
            expected.update(EXTENSION_RULE_FAMILIES)
        if families != expected:
            self.add("ERROR", "COUNT", "rules", f"families {dict(families)} != {dict(expected)}")
        for what, n, exp in (
            ("risks", len(self.risks), EXPECTED_RISKS),
            ("mitigations", len(self.mitigations), EXPECTED_MITIGATIONS),
            ("sep fields", len(self.sep_fields), EXPECTED_SEP_FIELDS),
        ):
            if n != exp:
                self.add("ERROR", "COUNT", what, f"{n}, expected {exp}")

    def check_questions(self) -> None:
        for q in self.b.questions.questions:
            for tok in q.rule_refs:
                self.ref(tok, q.id, "rule refs")
            if q.option_set is not None and q.option_set in self.option_sets:
                self.used_assumptions.update(self.option_sets[q.option_set].assumptions)
            if q.kind in (AnswerKind.SINGLE, AnswerKind.MULTI):
                if q.option_set is None:
                    self.add("ERROR", "OPTIONS-MISSING", q.id, f"{q.kind.value} question without option set")
                elif q.option_set not in self.option_sets:
                    self.add("ERROR", "REF-OPTIONS", q.id, f"option set {q.option_set} does not exist")
            elif q.option_set is not None:
                self.add("ERROR", "OPTIONS-UNEXPECTED", q.id, f"{q.kind.value} question with an option set")
            self.check_condition(q.visibility, q.id, "visibility")
            self.used_assumptions.update(q.assumptions)
        # Bidirectional question <-> rule citation.
        cited_by_questions = {tok for q in self.b.questions.questions for tok in q.rule_refs}
        for r in self.b.rules.rules:
            q_sources = [t for t in r.link_ids if QUESTION_ID_RE.match(t)]
            for qid in q_sources:
                q = self.questions.get(qid)
                if q is not None and r.id not in q.rule_refs:
                    lvl: Level = "WARN" if r.family == "HS" else "INFO"
                    self.add(lvl, "CITE-ONE-WAY", r.id, f"lists {qid} as source, but {qid} does not cite {r.id}")
            if r.id not in cited_by_questions and r.encoding.kind is not EncodingKind.SYSTEM:
                level: Level = "WARN" if r.family == "HS" else "INFO"
                self.add(level, "NOT-CITED", r.id, "no question cites this rule")

    def check_rules(self) -> None:
        for r in self.b.rules.rules:
            enc = r.encoding
            for tok in (*r.link_ids, *r.related_ids):
                self.ref(tok, r.id, "workbook links")
            for qid in enc.inputs:
                self.ref(qid, r.id, "encoding inputs")
            for i, case in enumerate(enc.cases, 1):
                self.check_condition(case.when, r.id, f"case {i}")
                if case.status is not None and r.family != "PROP":
                    self.add("ERROR", "ENCODING", r.id, f"case {i}: PropStatus outside PROP-*")
                if r.id in PROP_WITH_STATUS and case.status is None:
                    self.add("ERROR", "ENCODING", r.id, f"case {i}: PROP rule case without status")
            self.check_condition(enc.gap, r.id, "gap")
            self.check_condition(enc.review, r.id, "review")
            effects = {e for c in enc.cases for e in c.effects}
            for target in (*enc.routes_to, *([enc.hs_referral] if enc.hs_referral else [])):
                self.ref(target, r.id, "routing")
            for el in enc.elements:
                if not el.id.startswith(r.id + "."):
                    self.add("ERROR", "ELEMENT-ID", el.id, f"element of {r.id} must be named {r.id}.E<n>")
                if el.binding is not None:
                    self.check_values(el.binding.q, [*el.binding.met_when, *el.binding.not_met_when], el.id)
                if el.state_enum == "PropStatus" and r.family != "PROP":
                    self.add("ERROR", "ELEMENT-ENUM", el.id, "PropStatus elements only in PROP-* rules")
            self.used_assumptions.update(enc.assumptions)

            # Invariants (05_REGOLE_HS / 06_API).
            is_hs = r.id in HARD_STOPS
            if r.can_produce_o5 and not (is_hs or r.id == "OUT-05"):
                self.add("ERROR", "INVARIANT-O5", r.id, "only HS01–HS10 and OUT-05 may produce O5")
            if is_hs:
                if r.severity is not RuleSeverity.HARD_STOP:
                    self.add("ERROR", "INVARIANT-HS", r.id, "hard stop without severity HARD STOP")
                if r.human_gate is not HumanGateRequirement.REQUIRED:
                    self.add("ERROR", "INVARIANT-HS", r.id, "hard stop without REQUIRED human gate (AS-005)")
                if not enc.elements:
                    self.add("ERROR", "INVARIANT-HS", r.id, "hard stop without constituent elements")
                if not any(e.non_remediability for e in enc.elements):
                    self.add("ERROR", "INVARIANT-HS", r.id, "hard stop without a non-remediability element")
            elif r.severity is RuleSeverity.HARD_STOP:
                self.add("ERROR", "INVARIANT-HS", r.id, "severity HARD STOP outside HS01–HS10")
            if RuleEffect.OUTCOME in effects and r.family != "OUT":
                self.add("ERROR", "INVARIANT-OUTCOME", r.id, "only OUT-* rules emit an outcome")
            if r.family == "OUT" and enc.outcome is None:
                self.add("ERROR", "INVARIANT-OUTCOME", r.id, "OUT rule without outcome")
            if enc.outcome == "O5" and r.id != "OUT-05":
                self.add("ERROR", "INVARIANT-O5", r.id, "O5 only through OUT-05")
            if r.family == "PROP" and (r.can_produce_o5 or enc.outcome):
                self.add("ERROR", "INVARIANT-PROP", r.id, "PROP-* rules never produce O5")
            if enc.hs_referral and enc.hs_referral not in HARD_STOPS:
                self.add("ERROR", "INVARIANT-HS", r.id, f"hs_referral {enc.hs_referral} is not a hard stop")
            if enc.kind is EncodingKind.MANUAL and not enc.elements:
                self.add("ERROR", "ENCODING", r.id, "MANUAL encoding without manual elements")

        out_order = self.b.rules.outcome_precedence
        if out_order != ["O5", "O4", "O3", "O2", "O1"]:
            self.add("ERROR", "INVARIANT-OUTCOME", "outcome_precedence", f"{out_order} != O5→O4→O3→O2→O1")
        ordered_out = [r.encoding.outcome for r in self.b.rules.rules if r.family == "OUT"]
        if ordered_out != out_order:
            self.add("ERROR", "INVARIANT-OUTCOME", "OUT-*", f"OUT rules in order {ordered_out}")

    def check_condition(self, cond, subject: str, where: str) -> None:
        for node in iter_conditions(cond):
            if isinstance(node, (AnswerIs, AnswerUnresolved, AnswerProvided)):
                self.ref(node.q, subject, where)
                if isinstance(node, AnswerIs):
                    self.check_values(node.q, node.is_, subject)
            elif isinstance(node, (ElementIs, ElementUnresolved)):
                found = self.elements.get(node.element)
                if found is None:
                    self.add("ERROR", "REF-ELEMENT", subject, f"{where}: element {node.element} does not exist")
                    continue
                if isinstance(node, ElementIs):
                    enum = PropStatus if found[1].state_enum == "PropStatus" else RuleElementState
                    bad = [x for x in node.is_ if x not in enum.__members__]
                    if bad:
                        self.add("ERROR", "ENUM", subject, f"{where}: {bad} not in {enum.__name__}")
            elif isinstance(node, SepIs):
                if node.sep not in self.sep_fields:
                    self.add("ERROR", "REF-SEP", subject, f"{where}: SEP field {node.sep} does not exist")
                elif node.sep not in SEP_VALUES:
                    self.add("ERROR", "ENUM", subject, f"{where}: {node.sep} has no closed values")
                elif set(node.is_) - SEP_VALUES[node.sep]:
                    self.add("ERROR", "ENUM", subject, f"{where}: {node.sep} cannot take {sorted(set(node.is_) - SEP_VALUES[node.sep])}")
            elif isinstance(node, ArgumentIs):
                if self.b.argument is None:
                    self.add("ERROR", "REF-ARGUMENT", subject, f"{where}: no config/argument.yaml")
                    continue
                ids = {s.id for s in self.b.argument.steps}
                for step in node.steps:
                    if step not in ids:
                        self.add("ERROR", "REF-ARGUMENT", subject, f"{where}: step {step} does not exist")
                        continue
                    codes = {o.code for o in self.b.argument.step(step).options}
                    if not set(node.is_) & codes:
                        self.add("ERROR", "ENUM", subject, f"{where}: {step} takes none of {node.is_}")
            elif isinstance(node, HardStopIs):
                if node.hs not in HARD_STOPS:
                    self.add("ERROR", "REF-RULE", subject, f"{where}: {node.hs} is not a hard stop")
            elif isinstance(node, (RuleFired,)):
                self.ref(node.rule, subject, where)
            elif isinstance(node, PropIs):
                if node.prop != "ANY":
                    self.ref(node.prop, subject, where)
            elif isinstance(node, RiskMatch):
                if node.risk != "ANY":
                    self.ref(node.risk, subject, where)

    def allowed_values(self, q: QuestionSpec) -> set[str]:
        allowed = {s.value for s in q.states}
        if q.kind is AnswerKind.ROLE:
            allowed |= set(Role.__members__) - {Role.UNKNOWN.value}  # UNKNOWN is the answer state
        elif q.kind is AnswerKind.RISK_RATING:
            allowed |= set(RiskLevel.__members__)
        elif q.kind is AnswerKind.NOTIFICATION:
            allowed |= set(NotificationStatus.__members__)
        elif q.kind is AnswerKind.EFFECTIVENESS:
            allowed |= set(ControlEffectiveness.__members__)
        elif q.kind in (AnswerKind.SINGLE, AnswerKind.MULTI) and q.option_set in self.option_sets:
            allowed |= {o.code for o in self.option_sets[q.option_set].options}
        return allowed

    def check_values(self, qid: str, values: list[str], subject: str) -> None:
        q = self.questions.get(qid)
        if q is None:
            return
        bad = sorted(set(values) - self.allowed_values(q))
        if bad:
            self.add("ERROR", "ENUM", subject, f"{qid} cannot take {bad} (kind {q.kind.value})")

    def check_risks(self) -> None:
        owner: dict[str, str] = {}
        for risk in self.b.risks.risks:
            for qid in risk.core_questions + risk.provider_questions + risk.deployer_questions:
                self.ref(qid, risk.id, "source questions")
            for qid in risk.provider_questions:
                if not qid.startswith("P"):
                    self.add("ERROR", "RISK-SOURCES", risk.id, f"{qid} listed under Provider")
            for qid in risk.deployer_questions:
                if not qid.startswith("D"):
                    self.add("ERROR", "RISK-SOURCES", risk.id, f"{qid} listed under Deployer")
            for qid in risk.core_questions:
                if self.questions.get(qid) and self.questions[qid].phase in (Phase.PROVIDER, Phase.DEPLOYER):
                    self.add("ERROR", "RISK-SOURCES", risk.id, f"{qid} listed under Core")
            for tok in (*risk.rule_links, *risk.prop_rules):
                self.ref(tok, risk.id, "rule links")
            for mid in risk.mitigation_ids:
                self.ref(mid, risk.id, "mitigation ids")
                m = self.mitigations.get(mid)
                if m is not None and m.risk_id != risk.id:
                    self.add("ERROR", "RISK-MIT-LINK", risk.id, f"{mid} belongs to {m.risk_id}")
                if mid in owner:
                    self.add("ERROR", "RISK-MIT-LINK", mid, f"listed under {owner[mid]} and {risk.id}")
                owner[mid] = risk.id
        for m in self.b.mitigations.mitigations:
            if m.id not in owner:
                self.add("ERROR", "RISK-MIT-LINK", m.id, f"not listed by its risk {m.risk_id}")

    def check_mitigations(self) -> None:
        for m in self.b.mitigations.mitigations:
            self.ref(m.risk_id, m.id, "risk id")
            self.ref(m.source_rule, m.id, "source rule")
            if m.actual_residual is not None:
                self.add("ERROR", "INVARIANT-MIT", m.id, "actual residual risk set before verified reassessment")
            if m.timing is MitigationTiming.DURING_DEPLOYMENT_CONTINUOUS and m.decision_effect is DecisionEffect.REQUIRED_BEFORE_DEPLOYMENT:
                self.add("WARN", "MIT-TIMING", m.id, "timing 'during pilot/deployment' but decision effect 'required before pilot/deployment'")

    def check_sep(self) -> None:
        for f in self.b.sep.fields:
            for rid in f.rule_refs:
                self.ref(rid, f.id, "rule link")
            if f.rule_refs_text and not f.rule_refs:
                self.add("ERROR", "REF-UNPARSED", f.id, f"rule link {f.rule_refs_text!r} not parsed")

    def check_calibration(self) -> None:
        cal = self.b.risks.calibration
        sev_by_ordinal = {ORDINAL[s]: s for s in Severity}
        for risk in self.b.risks.risks:
            lp = risk.legacy
            sev = sev_by_ordinal[max(ORDINAL[lp.scale], ORDINAL[lp.scope], ORDINAL[lp.reversibility])]
            computed = cal.matrix[sev][lp.probability]
            if computed is not lp.reference_risk:
                self.add(
                    "ERROR",
                    "CALIBRATION",
                    risk.id,
                    f"RA reference profile gives {computed.value} with the matrix, workbook says {lp.reference_risk.value}",
                )

    def check_rule_cycles(self) -> None:
        """Rule-to-rule references must form a DAG (a HS gap may read its own HS)."""
        deps: dict[str, set[str]] = {}
        for r in self.b.rules.rules:
            refs: set[str] = set()
            conds = [c.when for c in r.encoding.cases] + [r.encoding.gap, r.encoding.review]
            for node in (n for c in conds for n in iter_conditions(c)):
                if isinstance(node, RuleFired):
                    refs.add(node.rule)
                elif isinstance(node, HardStopIs):
                    refs.add(node.hs)
                elif isinstance(node, PropIs) and node.prop != "ANY":
                    refs.add(node.prop)
            refs.discard(r.id)
            deps[r.id] = refs
        state: dict[str, int] = {}

        def visit(rid: str, path: list[str]) -> None:
            if state.get(rid) == 2:
                return
            if state.get(rid) == 1:
                self.add("ERROR", "RULE-CYCLE", rid, " -> ".join([*path[path.index(rid):], rid]))
                return
            state[rid] = 1
            for dep in sorted(deps.get(rid, ())):
                visit(dep, [*path, rid])
            state[rid] = 2

        for rid in deps:
            visit(rid, [])

    def check_assumptions(self) -> None:
        if self.registered is None:
            return
        for as_id in sorted(self.used_assumptions - self.registered):
            self.add("ERROR", "ASSUMPTION", as_id, "used in config but not registered in ANOMALIE.md")
        for as_id in sorted(self.registered - self.used_assumptions):
            self.add("INFO", "ASSUMPTION", as_id, "registered, not referenced by config (engine/UI level)")
