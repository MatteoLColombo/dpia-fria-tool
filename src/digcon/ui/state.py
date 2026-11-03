"""The assessment lives in one store in st.session_state, in AssessmentState JSON shape.

Widgets have keys ``w.<...>``; they are seeded from the store when missing and write back
through callbacks. Streamlit drops the state of widgets that are not rendered (hidden
questions, other add-ons): the store keeps the answers anyway.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

import streamlit as st

from digcon.domain.models import AssessmentState, ConfigBundle
from digcon.reporting.json_report import assessment_of

STORE = "assessment"
NAV = "nav"  # title of the section shown
SAVED = "saved_fingerprint"  # fingerprint of the assessment as last downloaded or loaded
WIDGET_PREFIX = "w."
# Session keys that describe the assessment on screen, not the browser session: dropped whenever a
# whole assessment is loaded or discarded. Other modules add their own (api_mode does).
PER_ASSESSMENT_KEYS: set[str] = {"plan_focus", "finding_source"}
LANDING = "land_after_load"  # set by "Load this assessment": the app picks where the loaded assessment opens


def empty_store(cfg: ConfigBundle) -> dict[str, Any]:
    return AssessmentState(assessment_id="new-assessment", workbook_version=cfg.version).model_dump(mode="json")


def store() -> dict[str, Any]:
    return st.session_state[STORE]


def init(cfg: ConfigBundle) -> None:
    if STORE not in st.session_state:
        st.session_state[STORE] = empty_store(cfg)


def assessment() -> AssessmentState:
    return AssessmentState.model_validate(store())


def seed(key: str, default: Any) -> None:
    """Give a widget its value from the store the first time it is rendered."""
    if key not in st.session_state:
        st.session_state[key] = default


def replace(data: dict[str, Any], *, from_file: bool = True) -> None:
    """Load a whole assessment (resume from JSON) and reset every widget.

    ``from_file``: the data matches a file the user holds (upload, or a fresh start), so it counts as saved.
    """
    st.session_state[STORE] = AssessmentState.model_validate(data).model_dump(mode="json")
    for key in PER_ASSESSMENT_KEYS:
        st.session_state.pop(key, None)
    for key in [k for k in st.session_state if str(k).startswith(WIDGET_PREFIX)]:
        del st.session_state[key]
    if from_file:
        mark_saved()
    else:
        st.session_state.pop(SAVED, None)


def to_json() -> str:
    return json.dumps(assessment().model_dump(mode="json"), ensure_ascii=False, indent=2)


def _fingerprint() -> str:
    return hashlib.sha256(json.dumps(store(), sort_keys=True, default=str).encode("utf-8")).hexdigest()


def mark_saved() -> None:
    st.session_state[SAVED] = _fingerprint()


def save_status(cfg: ConfigBundle) -> Literal["empty", "saved", "unsaved"]:
    """'empty' = nothing entered yet; 'saved' = matches the last downloaded or loaded file."""
    fresh = empty_store(cfg)
    fresh["assessment_id"] = store()["assessment_id"]
    if store() == fresh:
        return "empty"
    return "saved" if st.session_state.get(SAVED) == _fingerprint() else "unsaved"


def parse_upload(raw: bytes) -> dict[str, Any]:
    data = assessment_of(json.loads(raw.decode("utf-8")))  # a JSON report resumes too
    return AssessmentState.model_validate(data).model_dump(mode="json")


def set_or_remove(section: str, key: str, value: dict[str, Any] | None) -> None:
    bucket = store()[section]
    if value is None:
        bucket.pop(key, None)
    else:
        bucket[key] = value


def go(title: str) -> None:
    """Show another section (button callback)."""
    st.session_state[NAV] = title
