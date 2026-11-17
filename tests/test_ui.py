"""The Streamlit app, driven through its widgets (streamlit.testing.AppTest)."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from digcon.domain.enums import Phase
from digcon.domain.models import AssessmentState
from digcon.ui import state as ui_state
from digcon.ui.app import NAV, _steps
from digcon.ui.labels import (
    GOVERNANCE_TITLE, NAV_LABELS, PHASE_TITLES, RESULT_TITLE, REVIEW_TITLE, ROUTING_TITLE, RULES_TITLE, STEP_ADDONS,
)
from engine_support import build_state

TIMEOUT = 60
APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


def app(patch=None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    if patch is not None:
        at.session_state[ui_state.STORE] = build_state(patch).model_dump(mode="json")
    return at.run()


ALL_TITLES = [t for items in _steps().values() for t, _ in items]


def menu_button(at: AppTest, title):
    return at.sidebar.button(key=f"nav.{title}")


def goto(at: AppTest, title) -> AppTest:
    """Click the section in the left menu, as a user does."""
    title = PHASE_TITLES[title] if isinstance(title, Phase) else title
    return menu_button(at, title).click().run()


def outcome(at: AppTest) -> str:
    goto(at, RESULT_TITLE)
    line = next(m.value for m in at.markdown if "Export code: O" in m.value)  # RA-1: derived from the overall position
    return line.split("Export code: ", 1)[1][:2]


def rerecord(at: AppTest, right: str, step: str) -> AppTest:
    """The assessor reviews a step of the argument on the changed facts and records it again (3.5)."""
    from digcon.ui.labels import ARGUMENT_TITLE
    goto(at, ARGUMENT_TITLE)
    at.selectbox(key="w.arg.selected").set_value(right).run()
    return at.button(key=f"arg.record.{right}.{step}").click().run()


def page_text(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)


def no_errors(at: AppTest) -> None:
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_empty_app_renders_with_header_and_disclaimer():
    at = app()
    no_errors(at)
    assert at.title[0].value == "Fundamental Rights Assessment"
    assert "Research prototype" in page_text(at)
    assert not at.info  # no coloured info boxes
    page = page_text(at)
    assert any("By Federica Paolucci, Eleonora Silva and Matteo Colombo" in c.value for c in at.caption[:3])
    assert outcome(at) == "O4"  # nothing answered yet: evidence gaps


def test_every_section_renders():
    at = app({})
    for title in ALL_TITLES:
        goto(at, title)
        no_errors(at)
        assert at.header[0].value == title
        assert menu_button(at, title).proto.type == "primary"  # current section highlighted
        assert not at.info


def test_menu_lists_all_four_steps_core_first():
    at = app({})
    keys = [b.key for b in at.sidebar.button if b.key and b.key.startswith("nav.") and b.key not in ("nav.prev", "nav.next")]
    assert keys == [f"nav.{t}" for t in ALL_TITLES]
    assert list(_steps())[0].startswith("Step 1") and list(_steps())[1] == STEP_ADDONS
    assert ALL_TITLES[1:5] == [PHASE_TITLES[p] for p in (Phase.INTRO, Phase.WHAT, Phase.HOW, Phase.WHY)]
    # The pager crosses from the last core section into step 2.
    goto(at, Phase.WHY)
    at.button(key="nav.next").click().run()
    assert at.header[0].value == ROUTING_TITLE
    assert at.session_state[NAV] == ROUTING_TITLE


def test_closed_add_ons_are_marked_in_the_menu():
    at = goto(app({}), ROUTING_TITLE)  # baseline: not high-risk
    assert "closed" in menu_button(at, PHASE_TITLES[Phase.PROVIDER]).label.lower()
    assert "Not high-risk" in page_text(at)
    at = goto(app({"answers": {"FOLLOW": "YES", "C05": "PROVIDER"}}), ROUTING_TITLE)
    label = menu_button(at, PHASE_TITLES[Phase.PROVIDER]).label
    assert label.startswith(NAV_LABELS[PHASE_TITLES[Phase.PROVIDER]]) and "0 / 10" in label


def test_deployer_role_explains_what_is_missing():
    at = goto(app({"answers": {"C05": "DEPLOYER", "FOLLOW": "NO"}}), Phase.DEPLOYER)
    assert "HIGH RISK = YES" in page_text(at)
    at = goto(app({"answers": {"C05": "DEPLOYER", "FOLLOW": "YES"}}), Phase.DEPLOYER)
    assert "D00 = YES" in page_text(at)
    at.button_group(key="w.D00").set_value("YES").run()
    assert at.text_area(key="w.D01.value") is not None


def test_baseline_assessment_shows_o1():
    at = app({})
    no_errors(at)
    assert outcome(at) == "O1"


def test_widget_answer_updates_outcome_and_opens_hard_stop():
    at = goto(app({}), Phase.HOW)
    at.button_group(key="w.C46").set_value("NO").run()
    no_errors(at)
    assert at.session_state[ui_state.STORE]["answers"]["C46"]["state"] == "NO"
    assert outcome(at) == "O4"  # HS05 opened by the signal, not evaluated yet
    # The lawyer excludes HS05 from the UI.
    goto(at, REVIEW_TITLE)
    at.button_group(key="w.HS05.E1").set_value("MET").run()
    at.button_group(key="w.HS05.E2").set_value("NOT_MET").run()
    at.checkbox(key="w.gate.HS05").check().run()
    at.text_input(key="w.gate.HS05.decision").input("Oversight can be introduced").run()
    at.text_input(key="w.gate.HS05.by").input("F. Paolucci").run()
    no_errors(at)
    # RA-1 revision loop: the oversight answer changed, so the guarantees step of each engaged right is out of date.
    assert outcome(at) == "O4"
    for right in ("CFR-21", "CFR-08"):
        rerecord(at, right, "B5")
    assert outcome(at) == "O3"  # SCR-01 remediation still open


def test_unknown_status_on_text_question_is_a_gap_not_a_no():
    at = goto(app({}), Phase.WHAT)
    at.button_group(key="w.C11.status").set_value("UNKNOWN").run()
    no_errors(at)
    assert at.session_state[ui_state.STORE]["answers"]["C11"]["state"] == "UNKNOWN"
    assert outcome(at) == "O4"


def test_hidden_answers_survive_in_the_store():
    at = goto(app({"answers": {"FOLLOW": "YES", "C05": "PROVIDER", "P01": "YES"}}), Phase.WHAT)
    at.button_group(key="w.FOLLOW").set_value("NO").run()  # provider add-on closes
    goto(at, Phase.PROVIDER)
    goto(at, Phase.WHAT)
    at.button_group(key="w.FOLLOW").set_value("YES").run()  # and reopens
    goto(at, Phase.PROVIDER)
    no_errors(at)
    assert at.session_state[ui_state.STORE]["answers"]["P01"]["state"] == "YES"
    assert at.button_group(key="w.P01").value == "YES"


@pytest.mark.parametrize(
    ("role", "extra"),
    [
        ("PROVIDER", {}),
        ("DEPLOYER", {"D00": "YES"}),
        ("JOINT", {"D00": "YES"}),
    ],
)
def test_complete_assessment_per_role_from_the_ui(role, extra):
    """Acceptance check: one full assessment per role reaches an outcome with an audit trail."""
    at = goto(app({"answers": {"FOLLOW": "YES", **extra}}), Phase.INTRO)
    at.selectbox(key="w.C05").set_value(role).run()
    if role in ("PROVIDER", "JOINT"):
        goto(at, Phase.PROVIDER)
        for q, v in {"P01": "YES", "P02": "NO", "P03": "YES", "P04": "YES", "P05": "NO",
                     "P06": "YES", "P07": "YES", "P08": "YES", "P09": "YES", "P10": "YES"}.items():
            at.button_group(key=f"w.{q}").set_value(v).run()
        goto(at, RULES_TITLE)
        at.checkbox(key="w.gate.RMS-9I").check().run()
        at.text_input(key="w.gate.RMS-9I.decision").input("Residual risk acceptable").run()
        at.text_input(key="w.gate.RMS-9I.by").input("Provider governance board").run()
    if role in ("DEPLOYER", "JOINT"):
        goto(at, Phase.DEPLOYER)
        texts = {
            "D01": "Recruiters use the ranking when shortlisting",
            "D02": "12-month pilot, daily use",
            "D05": "Every list reviewed by a recruiter",
            "D06": "Complaint channel, HR lead owner",
            "D09": "DPIA-2026-04",
        }
        for q, v in texts.items():
            at.text_area(key=f"w.{q}.value").input(v).run()
        at.button_group(key="w.D03.value").set_value(["WORKERS_CANDIDATES"]).run()
        at.button_group(key="w.D04.value").set_value(["RISK-21"]).run()
        at.button_group(key="w.D07").set_value("NO").run()
        at.button_group(key="w.D08").set_value("NO").run()
        at.selectbox(key="w.D10").set_value("DONE").run()
        goto(at, RULES_TITLE)
        for el in ("FRIA-27A.E1", "FRIA-27D.E1", "FRIA-27E.E1", "FRIA-27F.E1", "FRIA-27I.E1"):
            at.button_group(key=f"w.{el}").set_value("NOT_MET").run()
    if role in ("DEPLOYER", "JOINT"):
        # RA-1: the deployer module named the affected groups; the interference step is recorded again on them.
        for right in ("CFR-21", "CFR-08"):
            rerecord(at, right, "B2")
    no_errors(at)
    assert outcome(at) == "O1"
    audit = [e for e in at.expander if e.label.startswith("Audit trail")]
    assert audit and "(0 events)" not in audit[0].label


def test_state_json_roundtrip():
    at = app({"answers": {"C46": "NO"}})
    exported = json.loads(ui_state.AssessmentState.model_validate(at.session_state[ui_state.STORE]).model_dump_json())
    again = AssessmentState.model_validate(exported)
    assert again.answers["C46"].state.value == "NO"
    assert ui_state.parse_upload(json.dumps(exported).encode("utf-8")) == again.model_dump(mode="json")


def test_control_effectiveness_is_a_closed_choice():
    at = goto(app({}), Phase.WHY)
    assert "NOT_VERIFIED" in at.selectbox(key="w.C43").options or "NOT VERIFIED" in at.selectbox(key="w.C43").options
    at.selectbox(key="w.C43").set_value("INEFFECTIVE").run()
    no_errors(at)
    assert at.session_state[ui_state.STORE]["answers"]["C43"]["value"] == "INEFFECTIVE"
    assert outcome(at) == "O3"


def test_governance_decision_is_its_own_section():
    at = goto(app({}), GOVERNANCE_TITLE)
    no_errors(at)
    at.text_input(key="w.gov.G01").input("Approved for a 6-month pilot").run()
    assert at.session_state[ui_state.STORE]["governance"]["g01_decision"] == "Approved for a 6-month pilot"
    assert outcome(at) == "O1"  # the recorded decision never changes the recommended outcome


def test_unsent_text_drafts_are_laid_over_the_browser_copy():
    from digcon.config import default_config
    from digcon.ui import bridge
    from digcon.ui.pages import result as result_page, sep as sep_page

    cfg = default_config()
    data = ui_state.AssessmentState(assessment_id="x", workbook_version=cfg.version).model_dump(mode="json")
    data["answers"]["C11"] = {"question_id": "C11", "state": "UNKNOWN"}
    drafts = {
        "w-C01-value": "  Typed before reload ",  # text question: becomes the answer
        "w-C11-value": "ignored",  # marked UNKNOWN: its text box is disabled
        "w-gov-G01": "Approved",
        "w-sep-SEP01": "Trigger text",
        "w-sep-SEP00": "YES",  # enum field: not a text draft
        "w-meta-id": "my-case",
        "w-NOPE-value": "unknown question",
    }
    bridge.apply_drafts(cfg, data, drafts, result_page.GOVERNANCE_FIELDS, set(sep_page.ENUM_FIELDS))
    state = ui_state.AssessmentState.model_validate(data)
    assert state.answers["C01"].value == "Typed before reload"
    assert state.answers["C11"].state.value == "UNKNOWN"
    assert state.governance.g01_decision == "Approved"
    assert state.sep.texts == {"SEP01": "Trigger text"}
    assert state.assessment_id == "my-case"
    assert "NOPE" not in state.answers


def test_guided_plan_preserves_work_across_stages_and_json_export():
    from digcon.ui.labels import MITIGATION_TITLE
    from digcon.ui.pages.action_plan import STAGES

    at = goto(app({'elements': {'QUAL-01.E1': 'MET'}}), MITIGATION_TITLE)
    at.radio(key='plan.stage.QUAL-01').set_value(STAGES[1]).run()
    at.text_area(key='w.plan.QUAL-01.action').input('Document the actual workflow').run()
    at.text_input(key='w.plan.QUAL-01.owner').input('Operations team').run()
    at.radio(key='plan.stage.QUAL-01').set_value(STAGES[2]).run()
    at.text_area(key='w.plan.QUAL-01.implementation').input('Workflow documented and approved').run()
    at.text_area(key='w.plan.QUAL-01.evidence_refs').input('procedure:v2').run()
    at.radio(key='plan.stage.QUAL-01').set_value(STAGES[3]).run()
    at.button(key='plan.resolve.QUAL-01').click().run()
    assert at.warning  # incomplete verification must not close the finding
    at.radio(key='plan.stage.QUAL-01').set_value(STAGES[1]).run()
    no_errors(at)
    assert at.text_area(key='w.plan.QUAL-01.action').value == 'Document the actual workflow'
    saved = AssessmentState.model_validate(at.session_state[ui_state.STORE])
    restored = AssessmentState.model_validate_json(saved.model_dump_json())
    item = restored.action_plan['QUAL-01']
    assert item.owner == 'Operations team'
    assert item.evidence_refs == ['procedure:v2']
    assert item.decision != 'RESOLVED'


def test_config_cache_rebuilds_when_code_or_config_changes(tmp_path, monkeypatch):
    """Fast reruns, yet never config objects built by the previous code after a deploy."""
    import os

    from digcon.ui import app as ui_app

    (tmp_path / "rules.yaml").write_text("a", encoding="utf-8")
    monkeypatch.setattr(ui_app, "_SOURCES", (tmp_path,))
    before = ui_app._code_version()
    assert ui_app._code_version() == before  # nothing changed: same cache key
    target = tmp_path / "rules.yaml"
    target.write_text("ab", encoding="utf-8")
    os.utime(target, ns=(1, 1))
    assert ui_app._code_version() != before


def _loaded(patch) -> AppTest:
    """What "Load this assessment" leaves behind: the new store and the landing flag."""
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state[ui_state.STORE] = build_state(patch).model_dump(mode="json")
    at.session_state[ui_state.LANDING] = True
    return at.run()


def test_a_half_done_assessment_opens_where_the_answers_stop():
    at = _loaded({"remove_answers": ["C38", "C39"]})  # two HOW questions left unanswered
    no_errors(at)
    assert at.header[0].value == PHASE_TITLES[Phase.HOW]
    assert ui_state.LANDING not in at.session_state


def test_a_complete_assessment_opens_on_the_findings():
    at = _loaded({})
    no_errors(at)
    assert at.header[0].value == RESULT_TITLE


def test_completed_stop_review_is_hidden_until_requested():
    at = goto(app({'elements': {'HS06.E2': 'NOT_MET'}, 'human_gates': {'HS06': 'COMPLETED'}}), REVIEW_TITLE)
    no_errors(at)
    assert not any('Review completed' in e.label for e in at.expander)
    at.checkbox(key='w.hs.show_all').check().run()
    no_errors(at)
    assert any('Review completed — stop not established' in e.label for e in at.expander)
    assert not any('Review in progress' in e.label for e in at.expander)


def test_pure_information_gap_links_to_source_without_a_new_action_form():
    from digcon.ui.labels import MITIGATION_TITLE
    at = goto(app({'answers': {'C43': 'NOT_VERIFIED'}}), MITIGATION_TITLE)
    no_errors(at)
    assert any(b.key and b.key.startswith('gap.source.') and b.key.endswith('.C43') for b in at.button)
    assert not any(t.key == 'w.plan.DQ-01.action' for t in at.text_area)


def test_shared_action_can_be_edited_once_and_preserves_separate_reviews():
    from digcon.domain.action_plan import share_action
    from digcon.ui.labels import MITIGATION_TITLE
    from digcon.ui.pages.action_plan import STAGES
    saved = build_state({'elements': {'QUAL-01.E1': 'MET', 'DATA-01.E1': 'MET'}})
    share_action(saved, ['QUAL-01', 'DATA-01'], dict(action='Restrict use', owner='Team',
                 due_date='2026-12-01', implementation='', evidence_refs=[]), 'shared-1')
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state[ui_state.STORE] = saved.model_dump(mode='json')
    at.session_state[ui_state.NAV] = MITIGATION_TITLE
    at.session_state['plan_focus'] = 'QUAL-01'
    at.run()
    no_errors(at)
    at.radio(key='plan.stage.QUAL-01').set_value(STAGES[1]).run()
    at.text_input(key='w.plan.QUAL-01.owner').input('Revised team').run()
    no_errors(at)
    records = at.session_state[ui_state.STORE]['action_plan']
    assert records['QUAL-01']['owner'] == records['DATA-01']['owner'] == 'Revised team'
    assert records['QUAL-01']['decision'] == records['DATA-01']['decision'] == 'PENDING'
