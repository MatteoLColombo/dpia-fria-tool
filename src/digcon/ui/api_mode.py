"""API mode: the OpenAI interpreter fills the reviewer checks (3.3), for invited sessions only.

A session is in API mode only when all of these hold:
  * the master switch DIGCON_API_ENABLED is true in the Streamlit secrets;
  * OPENAI_API_KEY, OPENAI_MODEL and DIGCON_API_LINK_CODE are set there;
  * the app was opened with the private link ``?api=<DIGCON_API_LINK_CODE>``.
Everyone else uses the deterministic tool and sees nothing about the API.

In API mode the interpreter runs when 3.3 or 4.1 is opened, only for reviewer-check rules (never hard
stops) whose answers changed since the API last saw them. A value a person sets always wins, and a value
a person clears is not filled again in that session. DIGCON_API_DAILY_CALLS caps the calls of all
sessions together (default 300 a day), to protect the credit.
"""

from __future__ import annotations

import hmac
import threading
from datetime import date
from typing import Any

import streamlit as st

from digcon.domain.enums import ElementSource
from digcon.domain.models import ConfigBundle

from . import state

ACTIVE = "api_mode"
DISMISSED = "api_dismissed"  # element ids a person has set or cleared: the API leaves them alone
TRIED = "api_tried"  # rule id -> input digest already sent in this session (no retry loops)
STATUS = "api_status"  # last run summary, shown in 3.3 / 4.1
DEFAULT_DAILY_CALLS = 300


def _secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:  # no secrets file at all: the API is simply off
        return default


def _true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def enabled() -> bool:
    """Master switch on and fully configured (key, model, link code)."""
    return _true(_secret("DIGCON_API_ENABLED", False)) and all(
        _secret(k) for k in ("OPENAI_API_KEY", "OPENAI_MODEL", "DIGCON_API_LINK_CODE")
    )


def activate_from_link() -> None:
    """Turn API mode on for this browser session if it was opened with the private link."""
    if st.session_state.get(ACTIVE) or not enabled():
        return
    code = st.query_params.get("api")
    if code and hmac.compare_digest(str(code), str(_secret("DIGCON_API_LINK_CODE"))):
        st.session_state[ACTIVE] = True


def active() -> bool:
    """API mode for this session (the master switch can still turn it off at any time)."""
    return bool(st.session_state.get(ACTIVE)) and enabled()


# -- shared daily cap ---------------------------------------------------------------------

@st.cache_resource
def _counter() -> dict[str, Any]:
    return {"day": None, "calls": 0, "lock": threading.Lock()}


def _limit() -> int:
    try:
        return int(_secret("DIGCON_API_DAILY_CALLS", DEFAULT_DAILY_CALLS))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_CALLS


def remaining_today() -> int:
    c = _counter()
    with c["lock"]:
        if c["day"] != date.today():
            return _limit()
        return max(0, _limit() - c["calls"])


def _reserve(n: int) -> int:
    c = _counter()
    with c["lock"]:
        if c["day"] != date.today():
            c["day"], c["calls"] = date.today(), 0
        granted = max(0, min(n, _limit() - c["calls"]))
        c["calls"] += granted
        return granted


# -- running the interpreter --------------------------------------------------------------

def make_client():
    """OpenAI client from the secrets (tests replace this function)."""
    from openai import OpenAI

    base_url = _secret("OPENAI_BASE_URL")
    key = _secret("OPENAI_API_KEY")
    return OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)


def _interpreter(cfg: ConfigBundle):
    from digcon.interpret.openai_interpreter import OpenAIInterpreter

    return OpenAIInterpreter(cfg, make_client(), _secret("OPENAI_MODEL"),
                             reasoning_effort=_secret("OPENAI_REASONING_EFFORT"))


def _todo(cfg: ConfigBundle, current, interp) -> list[tuple[str, list, str]]:
    """Reviewer-check rules to send: pending elements, some answer to read, inputs changed since last seen."""
    from digcon.interpret.openai_interpreter import pending_elements

    dismissed = st.session_state.setdefault(DISMISSED, set())
    tried = st.session_state.setdefault(TRIED, {})
    visible = interp.visible_questions(current)
    out = []
    for rule in cfg.rules.rules:
        if rule.family == "HS":
            continue  # hard-stop elements stay human-only until benchmarked
        els = [e for e in pending_elements(cfg, current, [rule.id]) if e.id not in dismissed]
        if not els:
            continue
        request = interp.request_for(current, rule.id, els, visible)
        if not request["evidence"] or all(e["answer"] == "NOT ANSWERED" for e in request["evidence"]):
            continue
        digest = interp.digest(request)
        seen = all(
            (ev := current.elements.get(e.id)) is not None and ev.source is ElementSource.API
            and (ev.provenance or "").endswith(f"input {digest}")
            for e in els
        )
        if not seen and tried.get(rule.id) != digest:
            out.append((rule.id, els, digest))
    return out


def refresh(cfg: ConfigBundle) -> bool:
    """Fill the reviewer checks whose answers changed. Call before the engine runs.

    Returns True when element values changed (the caller reruns, so the autosave picks them up).
    """
    if not active():
        return False
    try:
        return _refresh(cfg)
    except Exception as exc:  # invalid assessment, missing package, network: the deterministic tool carries on
        st.session_state[STATUS] = {"limit": False, "set": 0, "failed": 1, "rules": 0, "error": f"{type(exc).__name__}"}
        return False


def _refresh(cfg: ConfigBundle) -> bool:
    from digcon.interpret.openai_interpreter import apply_evaluations

    current = state.assessment()
    interp = _interpreter(cfg)
    todo = _todo(cfg, current, interp)
    if not todo:
        return False
    wanted = len(todo)
    granted = _reserve(wanted)
    todo = todo[:granted]
    if not todo:
        st.session_state[STATUS] = {"limit": True, "set": 0, "failed": 0, "rules": 0}
        return False
    with st.spinner(f"Checking {len(todo)} reviewer checks with the API…"):
        evaluations = interp.evaluate(current, [e for _, els, _ in todo for e in els])
    tried = st.session_state.setdefault(TRIED, {})
    for rule_id, _, digest in todo:
        tried[rule_id] = digest
    updated = apply_evaluations(current, evaluations).model_dump(mode="json")["elements"]
    state.store()["elements"] = updated
    for ev in evaluations:
        st.session_state.pop(f"w.{ev.element_id}", None)  # the widget reseeds from the store
    failed = sum(1 for c in interp.calls if c.error)
    st.session_state[STATUS] = {"limit": granted < wanted, "set": len(evaluations), "failed": failed,
                                "rules": len(todo)}
    return bool(evaluations)


def note_person_change(element_id: str) -> None:
    """A person set or cleared this check: the API does not fill it again in this session."""
    st.session_state.setdefault(DISMISSED, set()).add(element_id)


def notice() -> None:
    """One line for 3.3 / 4.1 in API mode: what the API did, what is left today."""
    if not active():
        return
    status = st.session_state.get(STATUS)
    parts = [":blue-badge[:material/smart_toy: API mode] Reviewer checks are filled by the API (OpenAI, EU) "
             "when this page opens; any value you set yourself wins."]
    if status and status.get("error"):
        parts.append(f"The API could not be used ({status['error']}): the checks stay to be verified.")
    elif status:
        parts.append(f"Last check: {status['set']} values set on {status['rules']} rules"
                     + (f", {status['failed']} calls failed (those checks stay to be verified)" if status["failed"] else "")
                     + (". Daily API limit reached: the rest stays to be verified" if status["limit"] else "") + ".")
    parts.append(f"{remaining_today()} API calls left today.")
    st.caption(" ".join(parts))
