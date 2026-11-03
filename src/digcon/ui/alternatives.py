"""Guided C31 with explicit human determination and legacy preservation."""
import streamlit as st
from digcon.domain.models import AlternativesReview
from digcon.domain.alternatives import decision, fingerprint, ready
from . import state

EXISTENCE = {'NOT_ASSESSED': 'Not yet assessed / not sure',
             'YES': 'Yes — a practicable, less intrusive alternative exists',
             'NO': 'No — none identified after examining the alternatives'}
DECISIONS = {'PENDING': 'Not yet reviewed', 'SUFFICIENT': 'Justification sufficient for this necessity check',
             'MISSING_EVIDENCE': 'More information is needed to reach a conclusion',
             'UNJUSTIFIED_EXCLUSION': 'A suitable, less intrusive alternative was excluded without sufficient justification'}
FIELDS = ('existence', 'comparison', 'evidence_refs', 'reviewer', 'review_date', 'review_reason', 'decision')


def begin():
    state.store()['alternatives_review'] = AlternativesReview().model_dump(mode='json')


def sync():
    data = dict(state.store().get('alternatives_review') or {})
    for field in FIELDS:
        key = 'w.alternatives.' + field
        if key in st.session_state:
            value = st.session_state[key]
            data[field] = [v.strip() for v in value.splitlines() if v.strip()] if field == 'evidence_refs' else value
    state.store()['alternatives_review'] = AlternativesReview.model_validate(data).model_dump(mode='json')


def approve():
    sync()
    current = state.assessment()
    record = current.alternatives_review
    if not ready(record):
        st.session_state['alternatives_message'] = ('Record the reviewer, date (YYYY-MM-DD) and reasons. A substantive conclusion also needs '
            'an assessed answer, comparison and evidence. Unjustified exclusion requires an identified alternative.')
        return
    data = state.store()['alternatives_review']
    signature = fingerprint(current)
    snapshot = {k: v for k, v in record.model_dump(mode='json').items() if k != 'history'}
    snapshot['reviewed_fingerprint'] = signature
    data['history'] = [*data.get('history', []), snapshot]
    data['reviewed_fingerprint'] = signature


def render():
    st.markdown('**Could the purpose be achieved through practicable alternatives with less interference with fundamental rights?**')
    record = state.store().get('alternatives_review')
    legacy = state.store()['answers'].get('C31')
    if record is None and legacy:
        st.caption('This assessment contains an earlier answer to “Have less intrusive alternatives been assessed?”. '
                   'It keeps its original meaning. It does not tell us whether alternatives exist.')
        st.write('Earlier answer: ' + str(legacy.get('state') or legacy.get('value')))
        if legacy.get('detail'):
            st.write(legacy['detail'])
        st.button('Start the new alternatives assessment', key='alternatives.begin', on_click=begin)
        st.caption('Starting the new assessment requires a fresh review. The earlier answer remains in the saved record.')
        return
    if 'alternatives_message' in st.session_state:
        st.warning(st.session_state.pop('alternatives_message'))
    data = record or AlternativesReview().model_dump(mode='json')
    for field in FIELDS:
        value = data[field]
        state.seed('w.alternatives.' + field, '\n'.join(value) if field == 'evidence_refs' else value)
    st.markdown('**1. Identify the alternatives**')
    st.selectbox('Do suitable, less intrusive alternatives exist?', list(EXISTENCE),
                 key='w.alternatives.existence', format_func=EXISTENCE.get, on_change=sync)
    st.caption('Consider a process without AI, narrower use, fewer data or a smaller affected population. '
               'Compare each option with the concrete purpose; a theoretical possibility is not enough.')
    st.markdown('**2. Explain the comparison and the proposed choice**')
    st.text_area('Which options were examined, how would they achieve the purpose, and why retain the proposed solution?',
                 key='w.alternatives.comparison', on_change=sync,
                 help='If none is suitable, explain why. If an alternative is suitable and less intrusive, explain why it was excluded.')
    st.text_area('Supporting evidence or addendum sections — one reference per line',
                 key='w.alternatives.evidence_refs', on_change=sync)
    with st.expander('3. Human review and conclusion', expanded=data['decision'] != 'PENDING'):
        st.selectbox('Reviewer’s conclusion', list(DECISIONS), key='w.alternatives.decision',
                     format_func=DECISIONS.get, on_change=sync)
        st.text_area('Reasons for this conclusion', key='w.alternatives.review_reason', on_change=sync)
        st.text_input('Reviewer', key='w.alternatives.reviewer', on_change=sync)
        st.text_input('Review date (YYYY-MM-DD)', key='w.alternatives.review_date', on_change=sync)
        st.button('Record the reasoned review', key='alternatives.approve', on_click=approve)
    effective = decision(state.assessment())
    if effective == 'SUFFICIENT':
        st.success('This necessity check is supported. The overall proportionality assessment remains separate.')
    elif effective == 'UNJUSTIFIED_EXCLUSION':
        st.error('Revision required: reconsider the choice or redesign the use. An action-plan approval alone cannot replace this review.')
    else:
        st.warning('Evidence gap: complete the comparison and record a current human review. A selected answer or document reference alone does not complete this check.')
    if record and record.get('reviewed_fingerprint') and record['reviewed_fingerprint'] != fingerprint(state.assessment()):
        st.caption('The supporting information or review fields have changed. Record a new review before relying on the earlier conclusion.')
    with st.expander('Previous review decisions and original answer'):
        if legacy:
            st.json(legacy)
        if data.get('history'):
            st.json(data['history'])
