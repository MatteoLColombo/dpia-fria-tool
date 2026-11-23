"""API mode: the OpenAI interpreter fills the reviewer checks (3.3) and suggests risks (3.2), for invited sessions only.

A session is in API mode only when all of these hold:
  * the master switch DIGCON_API_ENABLED is true in the Streamlit secrets;
  * OPENAI_API_KEY, OPENAI_MODEL and DIGCON_API_LINK_CODE are set there;
  * the app was opened with the private link ``?api=<DIGCON_API_LINK_CODE>``.
Everyone else uses the deterministic tool and sees nothing about the API.

In API mode the interpreter runs when 3.3 or 4.1 is opened, only for reviewer-check rules (never hard
stops) whose answers changed since the API last saw them. A value a person sets always wins, and a value
a person clears is not filled again in that session. DIGCON_API_DAILY_CALLS caps the calls of all
sessions together (default 300 a day), to protect the credit.

In 3.2 the API suggests, for each catalogue risk not yet rated by a person, whether it applies and a first
rating of its four initial dimensions. A suggestion stays outside the register until a person uses it;
a dismissed suggestion is not made again for that assessment.
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
RISK_TRIED = "api_risk_tried"  # risk id -> input digest already sent in this session
RISK_STATUS = "api_risk_status"  # last 3.2 run summary
# What the API saw, and what a person cleared, belongs to one assessment: a load or a discard starts
# over, otherwise reloading the same file would never be sent again. ACTIVE (the private link) stays.
state.PER_ASSESSMENT_KEYS.update({DISMISSED, TRIED, STATUS, RISK_TRIED, RISK_STATUS})
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
        if rule.id == "PROP-03" and current.alternatives_review is not None:
            continue  # the new alternatives determination belongs to the human reviewer
        if rule.family == "HS":
            continue  # hard-stop elements stay human-only until benchmarked
        if rule.family == "PROP":
            continue  # RA-1: proportionality is argued by a person, step by step, in 3.4-3.6
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


def _first_problem(calls) -> str | None:
    """The first error or rejection of a run, short, for the note in 3.2 / 3.3 (no secrets: OpenAI masks keys)."""
    for c in calls:
        text = c.error or (c.rejected[0] if c.rejected else None)
        if text:
            return text if len(text) <= 240 else text[:237] + "…"
    return None


def refresh(cfg: ConfigBundle) -> bool:
    """Fill the reviewer checks whose answers changed. Call before the engine runs.

    Returns True when element values changed (the caller reruns, so the autosave picks them up).
    """
    if not active():
        return False
    try:
        return _refresh(cfg)
    except Exception as exc:  # invalid assessment, missing package, network: the deterministic tool carries on
        st.session_state[STATUS] = {"limit": False, "set": 0, "failed": 1, "rules": 0, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
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
    updated = apply_evaluations(current, evaluations).model_dump(mode="json")
    state.store()["elements"] = updated["elements"]
    state.store()["api_suggestions"] = updated["api_suggestions"]
    for ev in evaluations:
        st.session_state.pop(f"w.{ev.element_id}", None)  # the widget reseeds from the store
    failed = sum(1 for c in interp.calls if c.error)
    st.session_state[STATUS] = {"limit": granted < wanted, "set": len(evaluations), "failed": failed,
                                "detail": _first_problem(interp.calls),
                                "rules": len(todo)}
    return bool(evaluations)


def confirm(element_id: str) -> None:
    """A person accepts the API's value: it becomes theirs; the suggestion stays on record for the audit."""
    rec = state.store()["elements"].get(element_id)
    if not rec or rec.get("source") != ElementSource.API.value:
        return
    state.store()["elements"][element_id] = {"element_id": element_id, "state": rec["state"]}
    note_person_change(element_id)


def clear(element_id: str) -> None:
    """A person discards the API's value: back to not evaluated, and the API does not fill it again
    (the kept suggestion marks it as cleared, also after the file is saved and loaded again)."""
    state.store()["elements"].pop(element_id, None)
    st.session_state.pop(f"w.{element_id}", None)
    note_person_change(element_id)


def note_person_change(element_id: str) -> None:
    """A person set or cleared this check: the API does not fill it again in this session."""
    st.session_state.setdefault(DISMISSED, set()).add(element_id)


def pending_review() -> list[str]:
    """Checks holding an API value that no person has confirmed or changed yet (they do not count: AS-040)."""
    return sorted(e for e, v in state.store()["elements"].items() if v.get("source") == ElementSource.API.value)


def notice() -> None:
    """On 3.3 / 4.1: how many API suggestions await a person, and a short note when the API could not do its job."""
    from .labels import RULES_TITLE

    waiting = pending_review()
    if waiting:  # shown on any link: a saved file can carry unreviewed suggestions
        n = len(waiting)
        st.markdown(f":orange-badge[{n} API suggestion{'s' if n != 1 else ''} to review] "
                    ":gray[They do not count in the outcome until you confirm or change them.]")
        if st.session_state.get(state.NAV) != RULES_TITLE:
            st.button("Review them in 3.3", key="api.review", icon=":material/fact_check:",
                      on_click=state.go, args=(RULES_TITLE,))
    if not active():
        return
    status = st.session_state.get(STATUS) or {}
    if status.get("error"):
        st.caption(f"Some checks could not be read automatically ({status['error']}): they stay to be verified.")
    elif status.get("limit"):
        st.caption("The daily limit for automatic checks is reached: the remaining checks stay to be verified.")
    elif status.get("failed"):
        st.caption(f"{status['failed']} automatic checks failed: those checks stay to be verified."
                   + (f" First reason: {status['detail']}" if status.get("detail") else ""))


# -- 3.2: risk suggestions ----------------------------------------------------------------

RISK_DIMENSIONS = ("scale", "scope", "reversibility", "probability")


def _rated_by_person(entry) -> bool:
    return entry is not None and all(getattr(entry, d) is not None for d in RISK_DIMENSIONS)


def _risk_todo(cfg: ConfigBundle, current, suggester, visible) -> list[str]:
    """Catalogue risks to send: not rated by a person, not dismissed, some linked answer given, inputs changed."""
    from digcon.domain.enums import ApiRiskDecision

    tried = st.session_state.setdefault(RISK_TRIED, {})
    out = []
    for spec in cfg.risks.risks:
        previous = current.api_risk_suggestions.get(spec.id)
        if previous is not None and previous.decision is ApiRiskDecision.DISMISSED:
            continue
        if _rated_by_person(current.risks.get(spec.id)):
            continue
        request = suggester.request_for(current, spec, visible)
        if not suggester.worth_sending(request):
            continue
        digest = suggester.digest(request)
        if previous is not None and previous.provenance.endswith(f"input {digest}"):
            continue
        if tried.get(spec.id) != digest:
            out.append(spec.id)
            tried[spec.id] = digest
    return out


def refresh_risks(cfg: ConfigBundle) -> bool:
    """Suggest risks whose linked answers changed (3.2). Returns True when a suggestion was added or replaced."""
    if not active():
        return False
    try:
        return _refresh_risks(cfg)
    except Exception as exc:  # the deterministic tool carries on
        st.session_state[RISK_STATUS] = {"limit": False, "set": 0, "failed": 1, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        return False


def _refresh_risks(cfg: ConfigBundle) -> bool:
    from digcon.interpret.risk_suggestions import RiskSuggester

    current = state.assessment()
    suggester = RiskSuggester(_interpreter(cfg))
    visible = suggester.interp.visible_questions(current)
    todo = _risk_todo(cfg, current, suggester, visible)
    if not todo:
        return False
    wanted = len(todo)
    granted = _reserve(wanted)
    if granted < wanted:  # the ones not sent may go next time the cap allows
        for rid in todo[granted:]:
            st.session_state[RISK_TRIED].pop(rid, None)
    todo = todo[:granted]
    if not todo:
        st.session_state[RISK_STATUS] = {"limit": True, "set": 0, "failed": 0}
        return False
    with st.spinner(f"Reading {len(todo)} catalogue risks with the API…"):
        suggestions = suggester.suggest(current, todo, visible)
    bucket = state.store().setdefault("api_risk_suggestions", {})
    for sug in suggestions:
        bucket[sug.risk_id] = sug.model_dump(mode="json")
    failed = sum(1 for c in suggester.calls if c.error or c.rejected)
    st.session_state[RISK_STATUS] = {"limit": granted < wanted, "set": len(suggestions), "failed": failed,
                                     "detail": _first_problem(suggester.calls)}
    return bool(suggestions)


def use_risk(risk_id: str) -> None:
    """A person takes the API's suggestion: the risk enters the register with the suggested initial ratings,
    which are theirs from then on (a dimension the API left open stays as it was)."""
    sug = state.store().get("api_risk_suggestions", {}).get(risk_id)
    if not sug or sug.get("relevance") != "RELEVANT":
        return
    entry = dict(state.store()["risks"].get(risk_id) or {"risk_id": risk_id})
    for dim in RISK_DIMENSIONS:
        if sug.get(dim) is not None:
            entry[dim] = sug[dim]
    state.store()["risks"][risk_id] = entry
    sug["decision"] = "ACCEPTED"
    for key in [k for k in st.session_state if str(k).startswith(f"w.risk.{risk_id}.")]:
        del st.session_state[key]  # the widgets reseed from the register


def dismiss_risk(risk_id: str) -> None:
    """A person sets the suggestion aside: it stays on record, and this risk is not suggested again."""
    sug = state.store().get("api_risk_suggestions", {}).get(risk_id)
    if sug:
        sug["decision"] = "DISMISSED"


def pending_risks() -> list[str]:
    """Relevant risks the API suggested that no person has used or dismissed yet."""
    return sorted(r for r, s in state.store().get("api_risk_suggestions", {}).items()
                  if s.get("relevance") == "RELEVANT" and s.get("decision") == "PENDING")


def risk_notice() -> None:
    """On 3.2: suggestions to review, and a short note when the API could not do its job."""
    waiting = pending_risks()
    if waiting:
        n = len(waiting)
        st.markdown(f":violet-badge[{n} API risk suggestion{'s' if n != 1 else ''} to review] "
                    ":gray[Not in the register until you use them: " + ", ".join(waiting) + ".]")
    if not active():
        return
    status = st.session_state.get(RISK_STATUS) or {}
    if status.get("error"):
        st.caption(f"Some risks could not be read automatically ({status['error']}).")
    elif status.get("limit"):
        st.caption("The daily limit for automatic checks is reached: some risks were not read.")
    elif status.get("failed"):
        st.caption(f"{status['failed']} automatic risk readings failed or were rejected."
                   + (f" First reason: {status['detail']}" if status.get("detail") else ""))
