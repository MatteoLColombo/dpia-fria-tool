"""Rights argument RA-1: positions per right, overall position, completeness, export code.

The workbook fixtures keep their expected outcomes (the engine is unchanged except HS10); these
cases cover the argument layer read on top of the engine.
"""

import pytest

from digcon import argument as ra
from digcon.config import default_config
from digcon.domain.enums import RuleElementState
from digcon.engine import run_engine
from engine_support import CTX, build_state, sign_argument
from test_engine import APPROVED_ACTION

CFG = default_config()


def read(patch=None, state=None):
    state = state or build_state(patch or {})
    result = run_engine(CFG, state, CTX)
    return ra.read(state, CFG, result), result


def right(code, **steps):
    return {"argument": {"rights": {code: {s: v for s, v in steps.items()}}}}


def test_baseline_is_clear_and_complete():
    p, r = read()
    assert (p.overall, p.complete, p.ocode) == (ra.CLEAR, True, "O1")
    assert p.rights["CFR-21"].position == ra.CLEAR
    assert p.rights["CFR-07"].position == ra.NOT_ENGAGED
    assert r.outcome.value == "O1"


def test_no_argument_leaves_the_assessment_incomplete_but_not_the_engine():
    state = build_state()
    state.argument = state.argument.model_copy(update={"system": {}, "rights": {}, "cross": {}})
    p, r = read(state=state)
    assert p.overall == ra.INCOMPLETE and not p.complete and p.ocode == "O4"
    assert r.outcome.value == "O1"  # the workbook's reading of steps 1-2 is unchanged


def test_every_right_of_the_register_must_be_screened():
    p, _ = read({"argument": {"drop": ["CFR-35.S0"]}})
    assert p.rights["CFR-35"].position == ra.INCOMPLETE
    assert any(i.scope == "CFR-35" and i.ref == "S0" for i in p.missing)


def test_a_missing_step_is_named():
    p, _ = read({"argument": {"drop": ["CFR-21.B6"]}})
    assert p.rights["CFR-21"].position == ra.INCOMPLETE
    assert [i.ref for i in p.missing] == ["B6"]


def test_reasons_author_and_date_are_required():
    for change in ({"reasons": ""}, {"author": " "}, {"date": "13/11/2026"}):
        state = build_state()
        det = state.argument.rights["CFR-21"].steps["B4"]
        state.argument.rights["CFR-21"].steps["B4"] = det.model_copy(update=change)
        p, _ = read(state=state)
        assert p.rights["CFR-21"].position == ra.INCOMPLETE, change


def test_dissent_needs_its_author_and_does_not_change_the_position():
    p, _ = read(right("CFR-21", B6={"code": "AIM_PREVAILS", "reasons": "Limited interference",
                                   "dissent": "The aim is served too little", "dissent_by": "Legal reviewer"}))
    assert p.rights["CFR-21"].position == ra.CLEAR
    p, _ = read(right("CFR-21", B6={"code": "AIM_PREVAILS", "reasons": "Limited interference",
                                   "dissent": "The aim is served too little"}))
    assert p.rights["CFR-21"].position == ra.INCOMPLETE


def test_a_change_to_the_risk_makes_the_argument_out_of_date():
    state = build_state()
    risk = state.risks["RISK-21"]
    state.risks["RISK-21"] = risk.model_copy(update={"scale": risk.scale.__class__.HIGH})
    p, _ = read(state=state)
    stale = {i.ref for i in p.missing if i.scope == "CFR-21"}
    assert {"B2", "B4", "B6"} <= stale
    assert all("out of date" in i.text for i in p.missing if i.scope == "CFR-21")


def test_a_verified_measure_reopens_the_guarantees_and_the_balancing():
    """The revision loop: a new verified measure asks for new determinations, it does not change them."""
    state = build_state({"mitigations": {"MIT-038": {"activated": True, "status": "VERIFIED_EFFECTIVE",
                                                     "evidence_refs": ["doc:bias-audit"]}}})
    state.mitigations["MIT-038"] = state.mitigations["MIT-038"].model_copy(update={"evidence_refs": ["doc:bias-audit-v2"]})
    p, _ = read(state=state)
    assert {i.ref for i in p.missing if i.scope == "CFR-21"} == {"B5", "B6"}
    p, _ = read(state=sign_argument(state.model_copy(update={"argument": _unsigned(state.argument, "CFR-21", "B5", "B6")})))
    assert p.rights["CFR-21"].position == ra.CLEAR


def _unsigned(arg, right_id, *steps):
    arg = arg.model_copy(deep=True)
    for s in steps:
        arg.rights[right_id].steps[s].fingerprint = ""
    return arg


@pytest.mark.parametrize("step,code,ocode", [("B4", "LESS_INTRUSIVE_EXISTS", "O3"), ("B5", "INADEQUATE", "O3"),
                                             ("B6", "INTERFERENCE_PREVAILS", "O3")])
def test_adverse_steps_require_revision(step, code, ocode):
    p, _ = read(right("CFR-21", **{step: {"code": code, "reasons": "Shown by the evidence"}}))
    assert p.rights["CFR-21"].position == ra.REVISION and p.ocode == ocode and p.complete


def test_a_negative_balance_asks_for_legal_review():
    p, _ = read(right("CFR-21", B6={"code": "INTERFERENCE_PREVAILS", "reasons": "Shown by the evidence"}))
    assert "legal review" in p.rights["CFR-21"].items[0].text


def test_conditions_need_to_be_stated():
    p, _ = read(right("CFR-21", B5={"code": "ADEQUATE_WITH_CONDITIONS", "reasons": "Human review"}))
    assert p.rights["CFR-21"].position == ra.INCOMPLETE
    p, _ = read(right("CFR-21", B5={"code": "ADEQUATE_WITH_CONDITIONS", "reasons": "Human review",
                                   "extra": {"conditions": "Recruiter review of every list stays in place"}}))
    assert p.rights["CFR-21"].position == ra.CONDITIONS and p.ocode == "O2"


def test_undetermined_is_a_gap_not_a_negative_finding():
    p, _ = read(right("CFR-21", B3E={"code": "UNDETERMINED", "reasons": "Legal advice requested"}))
    assert p.rights["CFR-21"].position == ra.INCOMPLETE and p.ocode == "O4"


ESSENCE = right("CFR-21", B3E={"code": "AFFECTED", "reasons": "No applicant can obtain a human decision"})


def test_affected_essence_opens_hs10_and_stops_the_argument():
    p, r = read(ESSENCE)
    assert r.hard_stops["HS10"].opened
    assert p.rights["CFR-21"].position == ra.STOP_PENDING and p.ocode == "O4"
    assert "B4" not in p.rights["CFR-21"].required  # no balancing past an affected essence


def test_hs10_confirmed_by_the_legal_review():
    p, r = read({**ESSENCE, "elements": {"HS10.E1": "MET", "HS10.E2": "MET"}, "human_gates": {"HS10": "COMPLETED"}})
    assert r.hard_stops["HS10"].state is RuleElementState.MET
    assert p.rights["CFR-21"].position == ra.STOP_CONFIRMED and p.ocode == "O5" and r.outcome.value == "O5"


def test_hs10_excluded_by_the_legal_review_sends_the_right_back_to_the_argument():
    p, r = read({**ESSENCE, "elements": {"HS10.E1": "NOT_MET", "HS10.E2": "NOT_MET"}, "human_gates": {"HS10": "COMPLETED"}})
    assert p.rights["CFR-21"].position == ra.STOP_EXCLUDED and not p.complete
    assert {"B4", "B5", "B6"} <= set(p.rights["CFR-21"].required)
    # The assessor revises the essence step; the argument resumes and the stop stays on record.
    p, _ = read({**right("CFR-21", B3E={"code": "INTACT", "reasons": "Legal review: the recruiter decides"}),
                 "elements": {"HS10.E1": "NOT_MET", "HS10.E2": "NOT_MET"}, "human_gates": {"HS10": "COMPLETED"}})
    assert p.rights["CFR-21"].position == ra.CLEAR and p.complete


def test_no_legal_basis_refers_to_hs02():
    p, _ = read({"argument": {"system": {"A1": {"code": "NO_BASIS", "reasons": "No provision covers this use"}}}})
    stop = next(i for i in p.system if i.ref == "A1")
    assert stop.position == ra.STOP_PENDING and "HS02" in stop.text


def test_cumulative_step_is_required_with_two_engaged_rights():
    p, _ = read({"argument": {"drop": ["CROSS.C1"]}})
    assert [i.ref for i in p.missing] == ["C1"]


def test_workbook_remediations_still_count():
    p, r = read({"elements": {"QUAL-01.E1": "MET"}})
    assert r.outcome.value == "O3" and p.overall == ra.REVISION and p.ocode == "O3"


def test_proportionality_rules_of_the_workbook_are_absorbed():
    p, r = read({"elements": {"PROP-02.E1": "MET"}})
    assert r.outcome.value == "O3"  # the workbook still reads PROP-02
    assert p.overall == ra.CLEAR  # the argument replaces it (A3, B4-B6)


def test_an_approved_action_does_not_change_a_determination():
    p, _ = read({**right("CFR-21", B6={"code": "INTERFERENCE_PREVAILS", "reasons": "Shown by the evidence"}),
                 "action_plan": {"SCR-01": APPROVED_ACTION}})
    assert p.rights["CFR-21"].position == ra.REVISION


def test_revision_loop_through_the_widgets():
    """Revision required → plan with a measure → measure verified → steps out of date → new determinations."""
    from digcon.ui.labels import ARGUMENT_TITLE, CROSS_TITLE, MITIGATION_TITLE
    from test_ui import app, goto, no_errors, outcome

    at = app(right("CFR-21", B6={"code": "INTERFERENCE_PREVAILS", "reasons": "Proxies weigh heavily on women"}))
    assert outcome(at) == "O3"
    goto(at, ARGUMENT_TITLE)
    at.selectbox(key="w.arg.selected").set_value("CFR-21").run()
    no_errors(at)
    at.text_area(key="w.arg.CFR-21.plan.action").input("Remove career-break variables; add bias audit").run()
    at.multiselect(key="w.arg.CFR-21.plan.measures").set_value(["MIT-038"]).run()
    store = at.session_state["assessment"]
    assert store["mitigations"]["MIT-038"]["activated"] and "RISK-21" in store["mitigations"]["MIT-038"]["linked_risk_ids"]
    assert outcome(at) == "O3"  # planning changes nothing by itself
    goto(at, MITIGATION_TITLE)
    at.radio(key="w.plan_view").set_value("Catalogue measures").run()
    at.selectbox(key="w.mit.MIT-038.status").set_value("VERIFIED_EFFECTIVE").run()
    assert outcome(at) == "O4"  # B5 and B6 of Article 21 are now out of date
    goto(at, ARGUMENT_TITLE)
    at.selectbox(key="w.arg.selected").set_value("CFR-21").run()
    at.button(key="arg.record.CFR-21.B5").click().run()
    at.selectbox(key="w.arg.CFR-21.B6.code").set_value("AIM_PREVAILS").run()
    at.text_area(key="w.arg.CFR-21.B6.reasons").input("Proxies removed and audited; the remaining interference is limited").run()
    at.button(key="arg.record.CFR-21.B6").click().run()
    assert outcome(at) == "O4"  # the steps across rights relied on the earlier balancing
    goto(at, CROSS_TITLE)
    for step in ("C1", "C2"):
        at.button(key=f"arg.record.CROSS.{step}").click().run()
    no_errors(at)
    assert outcome(at) == "O1"
    history = at.session_state["assessment"]["argument"]["rights"]["CFR-21"]["steps"]["B6"]["history"]
    assert [h["code"] for h in history] == ["AIM_PREVAILS"]  # the earlier determination came from the fixture
