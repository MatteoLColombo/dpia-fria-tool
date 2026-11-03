"""Section 1.0: start a new assessment or resume a saved one."""

from __future__ import annotations

import streamlit as st

from digcon.domain.models import ConfigBundle
from digcon.engine import EngineResult

from .. import state


def _sync_id() -> None:
    value = (st.session_state.get("w.meta.id") or "").strip()
    if value:
        state.store()["assessment_id"] = value


def save_button(where: str, *, width="content") -> None:
    st.download_button(
        "Save progress (download JSON)",
        state.to_json(),
        file_name=f"{state.store()['assessment_id']}.json",
        mime="application/json",
        key=f"save.{where}",
        on_click=state.mark_saved,
        icon=":material/download:",
        width=width,
        help="Keep this file: upload it in section 1.0 to resume the assessment later.",
    )


def render(cfg: ConfigBundle, result: EngineResult) -> None:
    st.markdown(
        "Work through the four steps in the left menu, in order: first the **assessment framework**, then the "
        "**regulatory requirements** that apply, then the **rights assessment**, then the **findings and decision**."
    )
    with st.container(border=True):
        st.markdown(
            ":blue[:material/history:] Answers are **autosaved in this browser** as you go, so a reload or a closed "
            "tab loses nothing. Nothing is stored on a server. To continue on another browser or computer, or to "
            "keep a record, download the JSON file. On a shared computer, use *Discard answers and start over* "
            "when you finish."
        )
    col_new, col_resume = st.columns(2, gap="medium")
    with col_new, st.container(border=True):
        st.subheader("New assessment")
        state.seed("w.meta.id", state.store()["assessment_id"])
        st.text_input("Assessment name", key="w.meta.id", on_change=_sync_id,
                      help="Used as the file name when you save progress.")
        if st.button("Discard answers and start over", icon=":material/restart_alt:",
                     help="Removes every answer, including the copy autosaved in this browser. Download a file first if you may need them."):
            state.replace(state.empty_store(cfg))
            st.rerun()
    with col_resume, st.container(border=True):
        st.subheader("Resume an assessment")
        upload = st.file_uploader("Saved assessment (JSON)", type=["json"])
        if upload is not None and st.button("Load this assessment", type="primary", icon=":material/upload_file:",
                                            help="Replaces the answers in this session."):
            try:
                state.replace(state.parse_upload(upload.getvalue()))
                st.session_state[state.LANDING] = True  # first unanswered section, or the findings if complete
                st.rerun()
            except ValueError as exc:
                st.error("This file could not be loaded. Choose a JSON file saved from this tool with "
                         "“Save progress”, unchanged.")
                with st.expander("Technical details"):
                    st.code(str(exc), language=None)
