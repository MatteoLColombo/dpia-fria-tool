"""Saved assessments: files from earlier versions still load, and a save/reload changes nothing."""

import json
from pathlib import Path

from digcon.config import default_config
from digcon.domain.enums import Outcome
from digcon.domain.models import AssessmentState
from digcon.engine import run_engine
from digcon.ui import state as ui_state
from engine_support import CTX, build_state
from test_engine import APPROVED_ACTION
from test_ui import app, no_errors, outcome

LEGACY = Path(__file__).resolve().parent / "fixtures" / "legacy"


APPROVED_PATCH = {
    "answers": {"C46": "NO"},
    "elements": {"HS05.E1": "MET", "HS05.E2": "NOT_MET", "HS05.E3": "NOT_MET"},
    "human_gates": {"HS05": "COMPLETED"},
    "mitigations": {
        "MIT-002": {"activated": True, "status": "VERIFIED_EFFECTIVE", "linked_rule_ids": ["SCR-01"], "evidence_refs": ["doc:x"]},
        "MIT-009": {"activated": True, "status": "VERIFIED_EFFECTIVE", "evidence_refs": ["doc:mit-009-test-report"]},
    },
    "risks": {"RISK-07": {"scale": "MEDIUM", "scope": "MODERATE", "reversibility": "PARTLY_REVERSIBLE", "probability": "POSSIBLE",
                          "residual_scale": "LOW", "residual_scope": "LIMITED", "residual_reversibility": "REVERSIBLE",
                          "residual_probability": "RARE"}},
    "action_plan": {"SCR-01": APPROVED_ACTION},
    "residual_reviews": {"RISK-07": {"reviewer": "Risk owner", "review_date": "2026-10-12", "rationale": "Test report",
                                     "evidence_refs": ["doc:mit-009-test-report"], "mitigation_ids": ["MIT-009"],
                                     "reviewed_fingerprint": "AUTO"}},
}


def _reload(state: AssessmentState) -> AssessmentState:
    """Save progress, then Resume an assessment: the same path as the UI."""
    return AssessmentState.model_validate(ui_state.parse_upload(state.model_dump_json().encode("utf-8")))


def test_files_saved_before_the_action_plan_still_load():
    """12 Oct 2026 format: no action_plan, no residual_reviews."""
    raw = (LEGACY / "role-joint-O1-2026-10-12.json").read_bytes()
    assert b"action_plan" not in raw and b"residual_reviews" not in raw
    loaded = AssessmentState.model_validate(ui_state.parse_upload(raw))
    assert loaded.action_plan == {} and loaded.residual_reviews == {}
    assert run_engine(default_config(), loaded, CTX).outcome is Outcome.O1


def test_legacy_file_loaded_in_the_app():
    at = app()
    at.session_state[ui_state.STORE] = ui_state.parse_upload((LEGACY / "role-joint-O1-2026-10-12.json").read_bytes())
    at.run()
    no_errors(at)
    # O1 under the workbook alone; a file from before the rights argument (RA-1) has no argument yet.
    assert outcome(at) == "O4"


def test_reload_keeps_an_approved_action_and_a_residual_review():
    before = run_engine(default_config(), build_state(APPROVED_PATCH), CTX)
    after = run_engine(default_config(), _reload(build_state(APPROVED_PATCH)), CTX)
    assert before.outcome is Outcome.O2 and not before.open_remediations
    assert before.risks["RISK-07"].residual is not None
    assert after.outcome is before.outcome
    assert after.open_remediations == before.open_remediations
    assert after.risks["RISK-07"].residual == before.risks["RISK-07"].residual


def test_reload_is_lossless_for_every_sample():
    for path in sorted((Path(__file__).resolve().parents[1] / "samples").glob("*.json")):
        state = AssessmentState.model_validate(json.loads(path.read_text(encoding="utf-8")))
        assert _reload(state) == state, path.name


def test_visiting_every_page_keeps_approvals_valid():
    """The UI must not rewrite the state on render: any change would silently void every approval."""
    from digcon.domain.action_plan import approved, residual_approved
    from test_ui import ALL_TITLES, goto

    state = build_state(APPROVED_PATCH)
    at = app()
    at.session_state[ui_state.STORE] = state.model_dump(mode="json")
    at.run()
    for title in ALL_TITLES:
        goto(at, title)
    no_errors(at)
    shown = AssessmentState.model_validate(at.session_state[ui_state.STORE])
    assert shown == state
    assert approved(shown, "SCR-01") and residual_approved(shown, "RISK-07")
    assert outcome(at) == "O2"
