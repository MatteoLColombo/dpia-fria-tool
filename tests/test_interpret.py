"""OpenAI interpreter adapter (interpret/openai_interpreter.py), with a fake client: no network, no key."""

import json
from types import SimpleNamespace

import pytest

from digcon.config import default_config
from digcon.domain.enums import ElementSource, RuleElementState
from digcon.domain.models import ElementEvaluation
from digcon.interpret.openai_interpreter import OpenAIInterpreter, apply_evaluations, pending_elements
from engine_support import build_state, run

CFG = default_config()


class FakeResponses:
    def __init__(self, payload):
        self.payload = payload
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.payload, Exception):
            raise self.payload
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(output_text=text, usage=None)


def interpreter(payload):
    responses = FakeResponses(payload)
    return OpenAIInterpreter(CFG, SimpleNamespace(responses=responses), "test-model"), responses


def blank_state(*rule_ids):
    state = build_state()
    data = state.model_dump(mode="json")
    for rid in rule_ids:
        for el in CFG.rule(rid).encoding.elements:
            data["elements"].pop(el.id, None)
    return type(state).model_validate(data)


def element(eid, st, refs, why="because"):
    return {"element_id": eid, "state": st, "evidence_refs": refs, "rationale": why}


def test_request_carries_only_the_rule_and_its_inputs():
    interp, responses = interpreter({"rule_id": "PROP-05", "elements": []})
    state = blank_state("PROP-05")
    interp.evaluate(state, pending_elements(CFG, state, ["PROP-05"]))
    sent = json.loads(responses.kwargs["input"])
    assert sent["rule_id"] == "PROP-05"
    assert [e["id"] for e in sent["evidence"]] == ["C32", "C33"]
    assert {e["element_id"] for e in sent["elements"]} == {"PROP-05.E1", "PROP-05.E2"}
    assert responses.kwargs["store"] is False
    fmt = responses.kwargs["text"]["format"]
    assert fmt["strict"] is True
    item = fmt["schema"]["properties"]["elements"]["items"]["properties"]
    assert item["evidence_refs"]["items"]["enum"] == ["C32", "C33"]
    assert item["state"]["enum"] == ["MET", "NOT_MET", "UNCERTAIN"]


def test_valid_output_becomes_api_element_states_with_provenance():
    interp, _ = interpreter({"rule_id": "PROP-05", "elements": [
        element("PROP-05.E1", "NOT_MET", ["C32"]), element("PROP-05.E2", "MET", ["C33"]),
    ]})
    state = blank_state("PROP-05")
    evs = interp.evaluate(state, pending_elements(CFG, state, ["PROP-05"]))
    assert {e.element_id: e.state for e in evs} == {"PROP-05.E1": RuleElementState.NOT_MET, "PROP-05.E2": RuleElementState.MET}
    assert all(e.source is ElementSource.API and e.provenance.startswith("openai:test-model") for e in evs)
    assert evs[1].evidence_refs == ["answer:C33"]


@pytest.mark.parametrize(
    ("items", "reason"),
    [
        ([element("PROP-05.E1", "MET", ["C99"])], "not supplied"),
        ([element("PROP-05.E1", "MET", [])], "without evidence"),
        ([element("PROP-05.E1", "PROPORTIONATE", ["C32"])], "outside"),
        ([element("PROP-09.E1", "MET", ["C32"])], "not requested"),
        ([element("PROP-05.E1", "MET", ["C32"]), element("PROP-05.E1", "NOT_MET", ["C32"])], "duplicated"),
    ],
)
def test_invalid_items_are_rejected_not_coerced(items, reason):
    interp, _ = interpreter({"rule_id": "PROP-05", "elements": items})
    state = blank_state("PROP-05")
    evs = interp.evaluate(state, pending_elements(CFG, state, ["PROP-05"]))
    assert all(e.element_id != "PROP-05.E1" or reason == "duplicated" for e in evs)
    assert any(reason in r for r in interp.calls[0].rejected), interp.calls[0].rejected


def test_uncertain_without_evidence_is_allowed():
    interp, _ = interpreter({"rule_id": "PROP-05", "elements": [element("PROP-05.E1", "UNCERTAIN", [])]})
    state = blank_state("PROP-05")
    evs = interp.evaluate(state, pending_elements(CFG, state, ["PROP-05"]))
    assert [(e.element_id, e.state) for e in evs] == [("PROP-05.E1", RuleElementState.UNCERTAIN)]


@pytest.mark.parametrize("payload", ["not json", {"rule_id": "PROP-03", "elements": []}, RuntimeError("quota")])
def test_bad_or_failed_calls_change_nothing(payload):
    interp, _ = interpreter(payload)
    state = blank_state("PROP-05")
    assert interp.evaluate(state, pending_elements(CFG, state, ["PROP-05"])) == []
    assert interp.calls[0].error


def test_a_person_s_value_is_never_sent_nor_overwritten():
    state = blank_state("PROP-05")
    data = state.model_dump(mode="json")
    data["elements"]["PROP-05.E1"] = {"element_id": "PROP-05.E1", "state": "NOT_MET"}  # set by a person
    state = type(state).model_validate(data)
    assert [e.id for e in pending_elements(CFG, state, ["PROP-05"])] == ["PROP-05.E2"]
    api = ElementEvaluation(element_id="PROP-05.E1", state=RuleElementState.MET, source=ElementSource.API)
    assert apply_evaluations(state, [api]).elements["PROP-05.E1"].state is RuleElementState.NOT_MET


def test_api_values_reach_the_audit_trail():
    patch = {"elements": {"PROP-05.E2": "MET"}}
    state = build_state(patch)
    data = state.model_dump(mode="json")
    data["elements"]["PROP-05.E2"] = {"element_id": "PROP-05.E2", "state": "MET", "source": "API",
                                      "evidence_refs": ["answer:C33"], "rationale": "assertive", "provenance": "openai:m"}
    from datetime import datetime, timezone

    from digcon.engine import RunContext, run_engine

    r = run_engine(CFG, type(state).model_validate(data), RunContext(run_id="t", timestamp=datetime.now(timezone.utc)))
    ev = next(e for e in r.audit_trail if e.rule_id == "PROP-05")
    assert ev.api_evaluation["PROP-05.E2"]["state"] == "MET"
    assert ev.api_evaluation["PROP-05.E2"]["provenance"] == "openai:m"
    assert "answer:C33" in ev.evidence_refs
    assert r.closed
    assert run(patch).prop_statuses["PROP-05"] == r.prop_statuses["PROP-05"]  # same state, same engine result
