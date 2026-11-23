"""API risk suggestions in 3.2 (ui/api_mode.py, interpret/risk_suggestions.py). Fake client, no network."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from digcon.config import load_config
from digcon.domain.action_plan import fingerprint
from digcon.domain.models import AssessmentState
from digcon.interpret.openai_interpreter import OpenAIInterpreter
from digcon.interpret.risk_suggestions import RiskSuggester
from digcon.ui import api_mode
from digcon.ui import state as ui_state
from digcon.ui.app import NAV
from digcon.ui.labels import RISKS_TITLE
from engine_support import build_state

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
CODE = "prof-link-code"
SECRETS = {"DIGCON_API_ENABLED": True, "DIGCON_API_LINK_CODE": CODE, "OPENAI_API_KEY": "sk-test",
           "OPENAI_MODEL": "test-model"}
PERSON_RATED = "RISK-21"  # rated by a person in build_state(): never sent


def _risk_answer(req, relevance="RELEVANT", **dims):
    refs = [e["id"] for e in req["evidence"] if e["answer"] != "NOT ANSWERED"][:1]
    base = {"scale": "HIGH", "scope": "WIDE", "reversibility": "UNCERTAIN", "probability": "LIKELY"}
    return {"risk_id": req["risk_id"], "relevance": relevance, **base, **dims,
            "evidence_refs": refs, "rationale": "fake risk reasoning"}


class FakeResponses:
    """Risk calls: RELEVANT with HIGH / WIDE / (uncertain) / LIKELY. Rule calls: NOT_MET."""

    def __init__(self, answer=_risk_answer):
        self.risk_calls: list[str] = []
        self.rule_calls = 0
        self.answer = answer

    def create(self, **kwargs):
        req = json.loads(kwargs["input"])
        if "risk_id" in req:
            self.risk_calls.append(req["risk_id"])
            out = self.answer(req)
        else:
            self.rule_calls += 1
            refs = [e["id"] for e in req["evidence"]][:1]
            out = {"rule_id": req["rule_id"], "elements": [
                {"element_id": e["element_id"], "state": "NOT_MET", "evidence_refs": refs, "rationale": "x"}
                for e in req["elements"]]}
        return SimpleNamespace(output_text=json.dumps(out), usage=None, status="completed")


@pytest.fixture
def fake(monkeypatch):
    api_mode._counter.clear()
    responses = FakeResponses()
    monkeypatch.setattr(api_mode, "make_client", lambda: SimpleNamespace(responses=responses))
    return responses


def app(secrets=SECRETS, link=CODE) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state[ui_state.STORE] = build_state().model_dump(mode="json")
    at.session_state[NAV] = RISKS_TITLE
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    if link is not None:
        at.query_params["api"] = link
    return at.run()


def store(at):
    return at.session_state[ui_state.STORE]


def test_without_the_private_link_no_risk_is_sent(fake):
    at = app(link=None)
    assert not at.exception, [e.message for e in at.exception]
    assert fake.risk_calls == []
    assert store(at)["api_risk_suggestions"] == {}


def test_opening_3_2_suggests_risks_without_touching_the_register(fake):
    at = app()
    assert not at.exception, [e.message for e in at.exception]
    assert fake.risk_calls and PERSON_RATED not in fake.risk_calls
    assert fake.rule_calls == 0  # reviewer checks are read in 3.3 / 4.1, not here
    sugs = store(at)["api_risk_suggestions"]
    assert set(sugs) == set(fake.risk_calls)
    first = sugs[fake.risk_calls[0]]
    assert first["relevance"] == "RELEVANT" and first["decision"] == "PENDING"
    assert first["scale"] == "HIGH" and first["reversibility"] is None  # UNCERTAIN leaves it empty
    assert list(store(at)["risks"]) == [PERSON_RATED]  # nothing enters the register by itself
    assert "API risk suggestion" in " ".join(m.value for m in at.markdown)


def test_unchanged_answers_are_not_sent_again(fake):
    at = app()
    sent = len(fake.risk_calls)
    at.run()
    assert len(fake.risk_calls) == sent


def test_use_copies_the_ratings_into_the_register(fake):
    at = app()
    rid = fake.risk_calls[0]
    at.button(key=f"api.risk.use.{rid}").click().run()
    assert not at.exception, [e.message for e in at.exception]
    entry = store(at)["risks"][rid]
    assert (entry["scale"], entry["scope"], entry["probability"]) == ("HIGH", "WIDE", "LIKELY")
    assert entry.get("reversibility") is None  # left for the person
    assert store(at)["api_risk_suggestions"][rid]["decision"] == "ACCEPTED"
    assert at.checkbox(key=f"w.risk.{rid}.include").value is True


def test_dismiss_keeps_the_record_and_is_not_suggested_again(fake):
    at = app()
    rid = fake.risk_calls[0]
    at.button(key=f"api.risk.dismiss.{rid}").click().run()
    assert store(at)["api_risk_suggestions"][rid]["decision"] == "DISMISSED"
    assert rid not in store(at)["risks"]
    data = store(at)
    at2 = AppTest.from_file(APP, default_timeout=60)  # a fresh session with the saved file
    at2.session_state[ui_state.STORE] = data
    at2.session_state[NAV] = RISKS_TITLE
    for k, v in SECRETS.items():
        at2.secrets[k] = v
    at2.query_params["api"] = CODE
    before = len(fake.risk_calls)
    at2.run()
    assert rid not in fake.risk_calls[before:]


def test_suggestions_do_not_change_the_outcome_or_the_action_plan_signatures(fake):
    cfg = load_config()
    plain = build_state()
    at = app()
    with_sugs = AssessmentState.model_validate(store(at))
    assert with_sugs.api_risk_suggestions
    from digcon.engine import RunContext, run_engine
    from datetime import datetime, timezone
    ctx = RunContext(run_id="t", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert run_engine(cfg, plain, ctx).outcome == run_engine(cfg, with_sugs, ctx).outcome
    for rule_id in ("PROP-02", "RMS-01"):
        assert fingerprint(plain, rule_id) == fingerprint(with_sugs.model_copy(update={"elements": plain.elements}), rule_id)


@pytest.mark.parametrize("bad", [
    {"scale": "EXTREME"},  # outside the workbook enum
    {"evidence_refs": ["Z99"]},  # cites something that was not sent
    {"relevance": "MAYBE"},
])
def test_invalid_output_is_rejected(bad):
    cfg = load_config()
    responses = FakeResponses(lambda req: {**_risk_answer(req), **bad})
    suggester = RiskSuggester(OpenAIInterpreter(cfg, SimpleNamespace(responses=responses), "m"))
    state = build_state()
    out = suggester.suggest(state, ["RISK-01"], None)
    assert out == []
    assert suggester.calls[0].rejected or suggester.calls[0].error


def test_not_relevant_keeps_no_ratings_and_needs_a_citation():
    cfg = load_config()
    responses = FakeResponses(lambda req: _risk_answer(req, relevance="NOT_RELEVANT"))
    suggester = RiskSuggester(OpenAIInterpreter(cfg, SimpleNamespace(responses=responses), "m"))
    [sug] = suggester.suggest(build_state(), ["RISK-01"], None)
    assert sug.scale is None and sug.probability is None
    responses.answer = lambda req: {**_risk_answer(req, relevance="NOT_RELEVANT"), "evidence_refs": []}
    assert suggester.suggest(build_state(), ["RISK-01"], None) == []


def test_the_request_carries_only_the_risk_s_own_answers_and_the_context():
    cfg = load_config()
    suggester = RiskSuggester(OpenAIInterpreter(cfg, SimpleNamespace(responses=None), "m"))
    spec = cfg.risk("RISK-01")
    req = suggester.request_for(build_state(), spec, None)
    sources = set(spec.core_questions + spec.provider_questions + spec.deployer_questions)
    assert {e["id"] for e in req["evidence"]} == sources
    schema = suggester.schema_for(req)
    assert "RESIDUAL" not in json.dumps(schema).upper()
    assert schema["properties"]["scale"]["enum"] == ["LOW", "MEDIUM", "HIGH", "VERY_HIGH", "UNCERTAIN"]


def test_a_failed_call_shows_its_reason(monkeypatch):
    api_mode._counter.clear()

    class Broken:
        def create(self, **kwargs):
            raise RuntimeError("Error code: 401 - expired_secret_key")

    monkeypatch.setattr(api_mode, "make_client", lambda: SimpleNamespace(responses=Broken()))
    at = app()
    captions = " ".join(c.value for c in at.caption)
    assert "First reason: RuntimeError: Error code: 401 - expired_secret_key" in captions
