"""Reports (step 4): Markdown, JSON and CSV built from one engine run, on every sample and in the app."""

import csv
import io
import json

import pytest

from digcon.config import default_config
from digcon.domain.models import AssessmentState
from digcon.engine import run_engine
from digcon.reporting import csv_tables, json_report, markdown
from digcon.ui import state as ui_state
from digcon.ui.labels import GOVERNANCE_TITLE, OUTCOME_TITLES, RESULT_TITLE
from engine_support import CTX, build_state
from test_ui import app, goto, no_errors
from tools import make_samples

CFG = default_config()
SAMPLES = sorted(make_samples.SAMPLES.glob("*.json"))


def _sample(path) -> AssessmentState:
    return AssessmentState.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_markdown_report_covers_outcome_answers_and_audit(path):
    state = _sample(path)
    result = run_engine(CFG, state, CTX)
    md = markdown.build(CFG, state, result)
    from digcon import argument as ra
    positions = ra.read(state, CFG, result)
    assert OUTCOME_TITLES[result.outcome] in md  # the workbook's reading stays on record
    assert positions.label() in md and f"export code {positions.ocode}" in md
    assert state.assessment_id in md and result.workbook_version in md
    assert "not a decision" in md and "## 7. Rights argument" in md
    for qid in result.visible_questions:
        assert f"| {qid} |" in md, qid
    for event in result.audit_trail:
        assert f"| {event.event_id} |" in md
    assert "None" not in md
    assert markdown.build(CFG, state, result) == md  # same run, same report


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_json_report_holds_the_assessment_and_full_audit_trail(path):
    state = _sample(path)
    result = run_engine(CFG, state, CTX)
    data = json.loads(json_report.dumps(state, result))
    assert data["format"] == json_report.FORMAT
    assert data["workbook_outcome"] == result.outcome.value
    assert data["recommended_outcome"] in ("O1", "O2", "O3", "O4", "O5")
    assert data["workbook_version"] == result.workbook_version
    assert len(data["result"]["audit_trail"]) == len(result.audit_trail)
    assert AssessmentState.model_validate(data["assessment"]) == state


def test_a_json_report_can_be_loaded_to_resume():
    state = _sample(SAMPLES[0])
    raw = json_report.dumps(state, run_engine(CFG, state, CTX)).encode("utf-8")
    assert ui_state.parse_upload(raw) == state.model_dump(mode="json")


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_csv_tables_have_one_row_per_item(path):
    state = _sample(path)
    result = run_engine(CFG, state, CTX)

    def rows(text):
        assert text.startswith(csv_tables.BOM)
        return list(csv.reader(io.StringIO(text.removeprefix(csv_tables.BOM))))

    assert len(rows(csv_tables.audit_trail(result))) == len(result.audit_trail) + 1
    assert len(rows(csv_tables.risk_register(CFG, state, result))) == len(result.risks) + 1
    assert len(rows(csv_tables.mitigation_plan(CFG, state))) == sum(m.activated for m in state.mitigations.values()) + 1


def test_reviewer_checks_show_who_set_them():
    state = build_state()
    data = state.model_dump(mode="json")
    api = {"source": "API", "rationale": "Reason given", "evidence_refs": ["answer:C33"], "provenance": "openai:m"}
    data["elements"] = {
        "PROP-05.E1": {"element_id": "PROP-05.E1", "state": "MET", **api},
        "PROP-05.E2": {"element_id": "PROP-05.E2", "state": "NOT_MET"},
        "PROP-03.E1": {"element_id": "PROP-03.E1", "state": "MET"},
        "QUAL-01.E1": {"element_id": "QUAL-01.E1", "state": "UNCERTAIN"},
    }
    sug = {"rationale": "Reason given", "evidence_refs": ["answer:C33"], "provenance": "openai:m"}
    data["api_suggestions"] = {
        eid: {"element_id": eid, "state": s, **sug}
        for eid, s in (("PROP-05.E1", "MET"), ("PROP-05.E2", "NOT_MET"), ("PROP-03.E1", "NOT_MET"),
                       ("PROP-06.E1", "UNCERTAIN"))
    }
    state = AssessmentState.model_validate(data)
    md = markdown.build(CFG, state, run_engine(CFG, state, CTX))
    assert "| PROP-05.E1 | MET | API (not yet reviewed) | MET | Reason given | C33 |" in md
    assert "| PROP-05.E2 | NOT MET | Person, confirmed the API | NOT MET |" in md
    assert "| PROP-03.E1 | MET | Person, changed the API's value | NOT MET |" in md
    assert "| PROP-06.E1 | Not evaluated | Person, cleared the API's value | UNCERTAIN |" in md
    assert "| QUAL-01.E1 | UNCERTAIN | Person | — |" in md


def test_free_text_cannot_break_a_table():
    data = build_state().model_dump(mode="json")
    data["answers"]["C01"] = {"question_id": "C01", "value": "a | b\nsecond line"}
    state = AssessmentState.model_validate(data)
    md = markdown.build(CFG, state, run_engine(CFG, state, CTX))
    assert "a \\| b<br>second line" in md


@pytest.mark.parametrize("title", [RESULT_TITLE, GOVERNANCE_TITLE])
def test_report_downloads_in_the_app(title):
    at = app({})
    goto(at, title)
    no_errors(at)
    assert any(s.value == "Download the report" for s in at.subheader)


def test_findings_page_says_the_outcome_is_a_recommendation():
    from digcon.ui.labels import RECOMMENDATION_NOTE

    at = app({})
    goto(at, RESULT_TITLE)
    assert any(RECOMMENDATION_NOTE in m.value for m in at.markdown)


def test_every_hard_stop_element_is_shown_in_english():
    from digcon.ui.labels import HS_ELEMENTS

    for rule in CFG.rules.rules:
        if rule.family == "HS":
            assert len(HS_ELEMENTS[rule.id]) == len(rule.encoding.elements), rule.id
