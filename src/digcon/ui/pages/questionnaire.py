from __future__ import annotations

import streamlit as st

from digcon.domain.enums import Phase
from digcon.domain.models import ConfigBundle
from digcon.engine import EngineResult

from .. import renderer, state
from ..labels import PHASE_TITLES, REVIEW_TITLE, subsection
from ..legal_guidance import ARTICLE_9, ARTICLE_27, PROVIDER_INTRO, PROVIDER_DETAIL, DEPLOYER_INTRO, DEPLOYER_DETAIL

PROVIDER = PHASE_TITLES[Phase.PROVIDER].split(" ", 1)[0]
DEPLOYER = PHASE_TITLES[Phase.DEPLOYER].split(" ", 1)[0]


def routing_box(result: EngineResult) -> None:
    """Which step 2 requirements apply now, and what is missing for the others (routing, 00_MAPPA_FLUSSO)."""
    answers = state.store()["answers"]
    role = result.role
    high_risk = result.high_risk
    lines = [f"High-risk classification: **{high_risk or 'not answered'}** · Organisation’s role: **{role or 'not answered'}**"]
    if result.routing_suspended:
        lines.append(f"**Step 2 requirements on hold.** C03 = YES: they stay closed until the legal review of HS07 "
                     f"excludes the prohibition ({REVIEW_TITLE}).")
    else:
        if result.provider_module:
            lines.append(f"**Article 9 provider module: open on your recorded answers** ({PROVIDER}).")
        elif role in ("PROVIDER", "JOINT"):
            lines.append(f"Article 9 provider obligations ({PROVIDER}): need **HIGH RISK = YES**.")
        if result.deployer_module:
            lines.append(f"**Article 27 FRIA module: open on your recorded answers** ({DEPLOYER}).")
        elif role in ("DEPLOYER", "JOINT"):
            if high_risk != "YES":
                lines.append(f"Article 27 deployer FRIA ({DEPLOYER}): needs **HIGH RISK = YES**, then **D00 = YES** in section {DEPLOYER}.")
            elif (answers.get("D00") or {}).get("state") != "YES":
                lines.append(f"Article 27 deployer FRIA ({DEPLOYER}): answer **D00 = YES** (first question of section {DEPLOYER}) to open D01–D10.")
        if high_risk == "NO":
            lines.append("Not high-risk according to your answer: these two modules remain closed. Continue the fundamental rights "
                         "assessment; other legal obligations may still apply.")
    with st.container(border=True):
        st.markdown("**Applicable requirements**")
        st.markdown("\n\n".join(lines))


def render(cfg: ConfigBundle, result: EngineResult, phase: Phase) -> None:
    visible = set(result.visible_questions)
    if phase in (Phase.PROVIDER, Phase.DEPLOYER):
        provider = phase is Phase.PROVIDER
        st.markdown(PROVIDER_INTRO if provider else DEPLOYER_INTRO)
        with st.expander("Legal scope and how to use this module"):
            st.markdown(PROVIDER_DETAIL if provider else DEPLOYER_DETAIL)
            url = ARTICLE_9 if provider else ARTICLE_27
            st.markdown(f"[Read the provision — European Commission]({url})")
            st.caption("Guidance checked on 21 October 2026. Examples are completion aids, not prescribed statutory forms.")
        routing_box(result)
        if phase is Phase.PROVIDER and not result.provider_module:
            return
        if phase is Phase.DEPLOYER and "D00" not in visible:
            return

    shown = [q for q in cfg.questions.questions if q.phase is phase and q.id in visible]
    answered = sum(1 for q in shown if q.id in state.store()["answers"] or (q.id == "C31" and state.store().get("alternatives_review") is not None))
    st.progress(answered / len(shown) if shown else 0.0, text=f"{answered} of {len(shown)} questions answered")
    st.caption("UNKNOWN, N/A and NOT OWNED are answers too: never treated as NO.")
    target = st.session_state.get('finding_source')
    focused = next((q for q in shown if q.id == target), None)
    if focused:
        with st.container(border=True):
            st.subheader('Answer linked to your selected issue')
            st.caption('Review or edit this answer, then use “Back to this issue” above to continue your work.')
            renderer.question(cfg, focused)
        shown = [q for q in shown if q.id != target]
    elif target:
        st.caption('The selected answer is not currently visible in this section. Your scope or role may have changed. Use the return buttons above to review the issue.')
    groups: dict[str, list] = {}
    for q in shown:
        groups.setdefault(q.subsection, []).append(q)
    for name, questions in groups.items():
        with st.container(border=True):
            st.subheader(subsection(name))
            for q in questions:
                renderer.question(cfg, q)

    if phase in (Phase.INTRO, Phase.WHAT):
        st.divider()
        routing_box(result)
