"""API mode in the app (ui/api_mode.py): private link, master switch, daily cap, person wins. Fake client, no network."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from digcon.ui import api_mode
from digcon.ui import state as ui_state
from digcon.ui.app import NAV
from digcon.ui.labels import RULES_TITLE
from engine_support import build_state

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
CODE = "prof-link-code"
SECRETS = {
    "DIGCON_API_ENABLED": True,
    "DIGCON_API_LINK_CODE": CODE,
    "OPENAI_API_KEY": "sk-test",
    "OPENAI_MODEL": "test-model",
}


class FakeResponses:
    """Answers every requested element NOT_MET, citing the first piece of evidence sent."""

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        req = json.loads(kwargs["input"])
        refs = [e["id"] for e in req["evidence"]][:1]
        out = {"rule_id": req["rule_id"], "elements": [
            {"element_id": e["element_id"], "state": "NOT_MET", "evidence_refs": refs, "rationale": "fake reasoning"}
            for e in req["elements"]
        ]}
        return SimpleNamespace(output_text=json.dumps(out), usage=None, status="completed")


@pytest.fixture
def fake(monkeypatch):
    api_mode._counter.clear()  # the daily cap is shared by sessions: start each test from zero
    responses = FakeResponses()
    monkeypatch.setattr(api_mode, "make_client", lambda: SimpleNamespace(responses=responses))
    return responses


def app(secrets=None, link=None) -> AppTest:
    """Answered assessment with no reviewer check filled in yet."""
    at = AppTest.from_file(APP, default_timeout=60)
    data = build_state().model_dump(mode="json")
    data["elements"] = {}
    at.session_state[ui_state.STORE] = data
    at.session_state[NAV] = RULES_TITLE
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    if link is not None:
        at.query_params["api"] = link
    return at.run()


def api_elements(at):
    return {e: v for e, v in at.session_state[ui_state.STORE]["elements"].items() if v.get("source") == "API"}


def page_text(at) -> str:
    return " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)


@pytest.mark.parametrize(
    ("secrets", "link"),
    [
        (SECRETS, None),  # normal link (students)
        (SECRETS, "wrong-code"),  # wrong code
        ({**SECRETS, "DIGCON_API_ENABLED": False}, CODE),  # master switch off
        ({k: v for k, v in SECRETS.items() if k != "OPENAI_API_KEY"}, CODE),  # no key configured
        (None, CODE),  # no secrets at all
    ],
)
def test_without_the_private_link_and_the_switch_the_tool_stays_deterministic(fake, secrets, link):
    at = app(secrets, link)
    assert not at.exception, [e.message for e in at.exception]
    assert fake.calls == 0
    assert not api_elements(at)
    assert "API mode" not in page_text(at)


def test_the_private_link_fills_reviewer_checks_and_tags_them(fake):
    at = app(SECRETS, CODE)
    assert not at.exception, [e.message for e in at.exception]
    filled = api_elements(at)
    assert fake.calls > 0 and filled
    assert not any(e.startswith("HS") for e in filled)  # hard stops stay human-only
    assert all("input " in v["provenance"] for v in filled.values())
    text = page_text(at)
    assert "API mode" in text and "Set by API" in text and "fake reasoning" in text


def test_unchanged_answers_are_not_sent_again(fake):
    at = app(SECRETS, CODE)
    first = fake.calls
    at.run()
    at.run()
    assert fake.calls == first


def test_a_person_s_value_wins_and_a_cleared_value_is_not_refilled(fake):
    at = app(SECRETS, CODE)
    eid = next(iter(api_elements(at)))
    at.button_group(key=f"w.{eid}").set_value("MET").run()
    stored = at.session_state[ui_state.STORE]["elements"][eid]
    assert stored["state"] == "MET" and stored.get("source", "MANUAL") == "MANUAL"
    at.button_group(key=f"w.{eid}").set_value(None).run()
    calls = fake.calls
    at.run()
    assert eid not in at.session_state[ui_state.STORE]["elements"]
    assert fake.calls == calls


def test_the_daily_cap_limits_calls(fake):
    at = app({**SECRETS, "DIGCON_API_DAILY_CALLS": 2}, CODE)
    assert fake.calls == 2
    assert "Daily API limit reached" in page_text(at)


def test_a_changed_answer_is_sent_again(fake):
    from digcon.domain.enums import Phase
    from digcon.ui.labels import PHASE_TITLES

    at = app(SECRETS, CODE)
    before = fake.calls
    at.sidebar.button(key=f"nav.{PHASE_TITLES[Phase.WHAT]}").click().run()  # C12 is in 1.2
    at.text_area(key="w.C12.value").input("Used internally.").run()
    at.sidebar.button(key=f"nav.{RULES_TITLE}").click().run()
    assert fake.calls > before  # QUAL-01 reads C12: its checks are refreshed
    assert fake.calls - before < before  # but only the rules that read C12, not everything again
