"""The committed config/ loads, matches the workbook in numbers and passes cross-reference validation."""

from collections import Counter
from pathlib import Path

import pytest
import yaml

from digcon.config import default_config
from digcon.domain.enums import ORDINAL, Probability, Reversibility, RiskLevel, Scale, Scope, Severity
from digcon.domain.validation import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT.parent / "spec" / "DIGCON_T17_DECISION_ENGINE.xlsx"


@pytest.fixture(scope="module")
def cfg():
    return default_config()


def known_findings():
    with open(ROOT / "tools" / "encodings" / "known_anomalies.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_version(cfg):
    assert cfg.version == "T17-v1.0.1"


def test_workbook_in_numbers(cfg):
    phases = Counter(q.phase.value for q in cfg.questions.questions)
    assert phases == {"INTRO": 7, "WHAT": 7, "HOW": 14, "WHY": 25, "PROVIDER": 10, "DEPLOYER": 11}
    assert len(cfg.rules.rules) == 79 + 1  # 79 of the workbook (ANOMALIE A9) + HS10 (extension RA-1)
    assert len(cfg.risks.risks) == 11
    assert len(cfg.mitigations.mitigations) == 50
    assert len(cfg.sep.fields) == 15  # SEP00–SEP13 + SEP04A
    assert [g.id for g in cfg.questions.governance_fields] == ["G01", "G02", "G03", "G04", "G05"]


def test_no_unregistered_errors(cfg):
    known = known_findings()

    def is_known(f):
        return any(k["code"] == f.code and k["subject"] == f.subject and k.get("contains", "") in f.message for k in known)

    errors = [f for f in validate_bundle(cfg) if f.level == "ERROR" and not is_known(f)]
    assert errors == []


def test_only_hard_stops_and_out05_can_produce_o5(cfg):
    o5 = {r.id for r in cfg.rules.rules if r.can_produce_o5}
    assert o5 == {f"HS{i:02d}" for i in range(1, 11)} | {"OUT-05"}  # HS10 from extension RA-1
    assert all(r.encoding.outcome != "O5" for r in cfg.rules.rules if r.id != "OUT-05")
    assert not any(r.can_produce_o5 for r in cfg.rules.rules if r.family == "PROP")


def test_outcome_precedence(cfg):
    assert cfg.rules.outcome_precedence == ["O5", "O4", "O3", "O2", "O1"]
    assert [r.encoding.outcome for r in cfg.rules.rules if r.family == "OUT"] == ["O5", "O4", "O3", "O2", "O1"]


def test_hard_stops_have_required_gate_and_non_remediability(cfg):
    for i in range(1, 10):
        hs = cfg.rule(f"HS0{i}")
        assert hs.human_gate.value == "REQUIRED"
        assert hs.encoding.elements, hs.id
        assert [e.id for e in hs.encoding.elements] == [f"{hs.id}.E{n}" for n in range(1, len(hs.encoding.elements) + 1)]
        assert any(e.non_remediability for e in hs.encoding.elements), hs.id
        assert " AND ".join(e.text for e in hs.encoding.elements) == hs.trigger_text.replace("  ", " ")


def test_prepopulated_mitigations_are_inactive_candidates_without_residual(cfg):
    for m in cfg.mitigations.mitigations:
        assert m.candidate_status == "NOT ACTIVATED — CANDIDATE"
        assert m.actual_residual is None
    assert {m.responsible_role for m in cfg.mitigations.mitigations} == {"Provider", "Deployer", "Joint"}


EXPECTED_MATRIX = {
    "LOW": ["VERY_LOW", "LOW", "MODERATE", "MODERATE"],
    "MEDIUM": ["LOW", "MODERATE", "MODERATE", "HIGH"],
    "HIGH": ["MODERATE", "HIGH", "HIGH", "VERY_HIGH"],
    "VERY_HIGH": ["HIGH", "HIGH", "VERY_HIGH", "VERY_HIGH"],
}


def test_calibration_matrix_matches_spec(cfg):
    m = cfg.risks.calibration.matrix
    for sev, row in EXPECTED_MATRIX.items():
        assert [m[Severity[sev]][p].value for p in Probability] == row


@pytest.mark.parametrize(
    ("fixture", "scale", "scope", "rev", "prob", "expected"),
    [
        ("CAL-01", "LOW", "LIMITED", "REVERSIBLE", "RARE", "VERY_LOW"),
        ("CAL-02", "MEDIUM", "MODERATE", "PARTLY_REVERSIBLE", "POSSIBLE", "MODERATE"),
        ("CAL-03", "HIGH", "MODERATE", "PARTLY_REVERSIBLE", "POSSIBLE", "HIGH"),
        ("CAL-04", "HIGH", "SYSTEMIC", "PARTLY_REVERSIBLE", "POSSIBLE", "HIGH"),
        ("CAL-05", "HIGH", "SYSTEMIC", "DIFFICULT_TO_REVERSE", "LIKELY", "VERY_HIGH"),
    ],
)
def test_exported_matrix_reproduces_calibration_fixtures(cfg, fixture, scale, scope, rev, prob, expected):
    # Config-integrity check only; the engine's calibration function gets its own tests in step 2.
    sev_by_ordinal = {ORDINAL[s]: s for s in Severity}
    sev = sev_by_ordinal[max(ORDINAL[Scale[scale]], ORDINAL[Scope[scope]], ORDINAL[Reversibility[rev]])]
    assert cfg.risks.calibration.matrix[sev][Probability[prob]] is RiskLevel[expected]


@pytest.mark.skipif(not WORKBOOK.exists(), reason="spec/ workbook not available")
def test_config_is_up_to_date_with_workbook(capsys):
    from tools.export_workbook import main

    assert main(["--check"]) == 0, capsys.readouterr().out


# --- the validator catches what it should --------------------------------------


def _with_rule(cfg, rule_id, **changes):
    rules = [r.model_copy(update=changes) if r.id == rule_id else r for r in cfg.rules.rules]
    return cfg.model_copy(update={"rules": cfg.rules.model_copy(update={"rules": rules})})


def _codes(bundle):
    return {(f.code, f.subject) for f in validate_bundle(bundle) if f.level == "ERROR"}


def test_validator_flags_prop_rule_producing_o5(cfg):
    assert ("INVARIANT-O5", "PROP-09") in _codes(_with_rule(cfg, "PROP-09", can_produce_o5=True))


def test_validator_flags_hard_stop_without_required_gate(cfg):
    assert ("INVARIANT-HS", "HS03") in _codes(_with_rule(cfg, "HS03", human_gate="POSSIBLE"))


def test_validator_flags_dangling_references(cfg):
    assert ("REF-QUESTION", "SCR-01") in _codes(_with_rule(cfg, "SCR-01", link_ids=["C99"]))
    assert ("REF-RISK", "SCR-01") in _codes(_with_rule(cfg, "SCR-01", link_ids=["RISK-99"]))
    enc = cfg.rule("SCR-01").encoding.model_copy(update={"inputs": ["C46", "Q99"]})
    assert ("REF-QUESTION", "SCR-01") in _codes(_with_rule(cfg, "SCR-01", encoding=enc))


def test_validator_flags_value_outside_question_states(cfg):
    from digcon.domain.models import RuleCase

    enc = cfg.rule("SCR-01").encoding
    bad = enc.model_copy(update={"cases": [RuleCase.model_validate({"when": {"q": "C46", "is": ["MAYBE"]}})]})
    assert ("ENUM", "SCR-01") in _codes(_with_rule(cfg, "SCR-01", encoding=bad))


def test_validator_flags_unregistered_assumption(cfg):
    findings = validate_bundle(cfg, registered_assumptions={"AS-001"})
    assert any(f.code == "ASSUMPTION" and f.subject == "AS-013" and f.level == "ERROR" for f in findings)
