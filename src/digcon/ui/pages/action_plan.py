"""Finding-led operational plan, persisted with the assessment."""
import streamlit as st
from digcon.domain.action_plan import ACTIONS, approved, approval_ready, findings, fingerprint, title
from digcon.domain.models import ActionPlanItem
from .. import state
from ..finding_navigation import open_source
from ..labels import PHASE_TITLES, REVIEW_TITLE

FIELDS = {
    'action': 'What will be done?', 'rationale': 'How does this action address this problem?',
    'owner': 'Responsible person or team', 'due_date': 'Target date (YYYY-MM-DD)',
    'implementation': 'What has been implemented?',
    'evidence_refs': 'Implementation evidence (one reference per line)',
    'verification_method': 'How was effectiveness checked?',
    'verification_result': 'What did the check establish for this problem?',
    'verification_evidence': 'Verification evidence (one reference per line)',
    'reviewer': 'Reviewer', 'review_date': 'Review date (YYYY-MM-DD)',
    'decision_reason': 'Reason for the review decision',
}


STAGES = ['🎯 1. Understand the problem', '🛠️ 2. Plan the action',
          '📎 3. Record implementation', '🔎 4. Verify and decide']
HELP = {
    'action': 'Describe a concrete change. Example: introduce a human review route for contested credit decisions.',
    'rationale': 'Explain how this change addresses this specific problem. A link to a measure is not enough.',
    'owner': 'Name the person or team responsible. Where provider and deployer must act, identify both contributions.',
    'due_date': 'When should the action be completed? Example: 2026-11-30.',
    'implementation': 'Describe what is now in operation, who implemented it and how. A planned action is not implementation.',
    'evidence_refs': 'Give traceable references, for example: complaints procedure v2, section 4; training record dated 2026-11-20.',
    'verification_method': 'Explain the test in the real use context. For a complaint route, test whether people can use it and obtain reconsideration.',
    'verification_result': 'Record what the test found for this problem, including failures and limitations. State who performed the check and when.',
    'verification_evidence': 'Reference the test report, reviewed cases or other evidence. The existence of a policy alone does not establish effectiveness.',
    'reviewer': 'Name the person deciding whether this specific problem is resolved. This role is distinct from implementing and testing the action.',
    'review_date': 'Date of the decision on this problem, in YYYY-MM-DD format.',
    'decision_reason': 'Explain why the evidence supports resolution or why the problem remains open. Refer to the implementation and verification evidence above.',
}


def _use_suggestion(rid):
    # Suggestions become editable text only after an explicit user action.
    if not state.store().get('action_plan', {}).get(rid, {}).get('action'):
        st.session_state[f'w.plan.{rid}.action'] = ACTIONS[rid][0]
        _sync(rid)


def _sync(rid):
    old = state.store().setdefault('action_plan', {}).get(rid, {})
    data = {'rule_id': rid, **old}
    for field in [*FIELDS, 'status']:
        key = f'w.plan.{rid}.{field}'
        if key not in st.session_state: continue
        value = st.session_state[key]
        data[field] = [x.strip() for x in value.splitlines() if x.strip()] if field.endswith('evidence') or field == 'evidence_refs' else value
    state.store()['action_plan'][rid] = ActionPlanItem.model_validate(data).model_dump(mode='json')


def _decide(rid, decision):
    _sync(rid)
    s = state.assessment()
    item = s.action_plan[rid]
    if decision == 'RESOLVED' and not approval_ready(item):
        st.session_state['plan_message'] = 'Complete the action, responsibility, implementation, verification, evidence and review fields first.'
        return
    data = state.store()['action_plan'][rid]
    history = list(data.get('review_history', []))
    current_fingerprint = fingerprint(s, rid)
    history.append({**{k: data.get(k) for k in ['reviewer','review_date','decision_reason']},
                    'decision': decision, 'reviewed_fingerprint': current_fingerprint})
    data.update(decision=decision, reviewed_fingerprint=current_fingerprint, review_history=history)


def _choose_measure(rid):
    st.session_state['plan_focus'] = rid
    st.session_state['w.plan_view'] = 'Catalogue measures'


def _field(rid, field, stored):
    value = stored.get(field, '')
    if isinstance(value, list): value = '\n'.join(value)
    key = f'w.plan.{rid}.{field}'
    state.seed(key, value)
    short = field in ('owner', 'due_date', 'reviewer', 'review_date')
    widget = st.text_input if short else st.text_area
    widget(FIELDS[field], key=key, on_change=_sync, args=(rid,), help=HELP[field])


def render(cfg, result):
    st.markdown('**Your action plan, in four steps.** Open a problem and choose the step you need. '
                'Saved work is included when you export the assessment and restored when you import it.')
    for col, heading, description in zip(st.columns(4), STAGES, [
        'Understand what needs attention.', 'Choose an action, an owner and a date.',
        'Record what was done and its evidence.', 'Check effectiveness and review this problem.'
    ]):
        with col:
            st.markdown('**' + heading + '**')
            st.caption(description)
    st.caption('A proposed or implemented action does not prove effectiveness. Verification does not automatically '
               'close the problem. Residual risk requires a separate documented reassessment in Fundamental rights risks.')
    if 'plan_message' in st.session_state: st.warning(st.session_state.pop('plan_message'))
    records = state.store().setdefault('action_plan', {})
    cards = findings(result, records)
    st.caption(f'{len(cards)} work items · {sum(v.get("status") == "IN_PROGRESS" for v in records.values())} in progress · '
               f'{sum(v.get("status") == "AWAITING_REVIEW" for v in records.values())} awaiting review')
    focus = st.session_state.get('plan_focus')
    if focus and focus not in cards:
        st.info('The issue you were working on is no longer listed among the current findings. Return to 4.1 to review the updated assessment; this is not a separate reviewer approval.')
    if not cards:
        st.success('No open finding currently needs an action.')
        return
    focus = st.session_state.get('plan_focus')
    for rid, info in sorted(cards.items(), key=lambda x: (x[0] != focus, not x[0].startswith('HS'), title(x[0]))):
        stored = records.get(rid, {})
        with st.expander(title(rid), expanded=rid == focus):
            st.caption(' · '.join(info['kinds']))
            if rid.startswith('HS'):
                steps = ('Read the facts and the grounds for the stop condition; identify what would need to change.',
                         'Document any changes and obtain a new reasoned legal determination. This action card cannot override the stop condition.')
            elif rid in ACTIONS:
                steps = ACTIONS[rid]
            else:
                steps = ('Review the source information below and specify the missing evidence or corrective action.',
                         'Record who will act, implement the action and submit the evidence for review.')
            stage = st.radio('Choose a step', STAGES, key=f'plan.stage.{rid}', horizontal=True)
            if stage == STAGES[0]:
                st.markdown('**First:** ' + steps[0] + '\n\n**Then:** ' + steps[1])
                qids = [q for q in result.rules[rid].input_ids if any(x.id == q for x in cfg.questions.questions)] if rid in result.rules else []
                with st.expander('Information used in this finding'):
                    for qid in qids:
                        q = cfg.question(qid); a = state.store()['answers'].get(qid, {})
                        if qid == 'C31' and state.store().get('alternatives_review') is not None:
                            from ..alternatives import EXISTENCE, DECISIONS
                            from digcon.domain.alternatives import decision
                            alt = state.store()['alternatives_review']
                            st.markdown('**Alternatives and justification of the choice**')
                            st.write(EXISTENCE[alt['existence']])
                            st.write(alt['comparison'] or 'Comparison not yet documented')
                            st.caption(DECISIONS[decision(state.assessment())])
                        else:
                            st.markdown('**' + q.text + '**')
                            st.write(a.get('value') or a.get('state') or 'Not answered')
                            if a.get('detail'): st.write(a['detail'])
                        st.button('Review this answer', key=f'plan.source.{rid}.{qid}', on_click=open_source, args=(rid, qid, PHASE_TITLES[q.phase]))
                    if not qids: st.caption('This finding requires review of the assessment evidence and judgement.')
            if stage == STAGES[1]:
                if rid in ACTIONS:
                    st.info('Suggested action: ' + ACTIONS[rid][0])
                    if not stored.get('action'):
                        st.button('Use this suggestion and edit it', key=f'plan.suggest.{rid}',
                                  on_click=_use_suggestion, args=(rid,))
                for f in ['action','rationale','owner','due_date']:
                    _field(rid, f, stored)
                key=f'w.plan.{rid}.status'; state.seed(key, stored.get('status', 'TODO'))
                st.selectbox('Work progress', ['TODO','IN_PROGRESS','AWAITING_REVIEW'], key=key,
                             format_func=lambda v: {'TODO':'Action proposed / implementation pending',
                                                   'IN_PROGRESS':'Implementation in progress',
                                                   'AWAITING_REVIEW':'Submitted for verification — effectiveness not yet established'}[v],
                             on_change=_sync,args=(rid,))
                linked = [m for m in state.assessment().mitigations.values() if rid in m.linked_rule_ids and m.activated]
                st.caption('Linked measures: ' + ('; '.join(cfg.mitigation(m.mitigation_id).measure for m in linked) or 'None yet'))
                st.button('Choose a measure for this problem', key=f'plan.measure.{rid}',
                          on_click=_choose_measure, args=(rid,))
                st.caption('Linking a measure alone never closes this problem.')
            if stage == STAGES[2]:
                st.info('Complete this step when the action has been carried out. Include who implemented it and what changed.')
                for f in ['implementation','evidence_refs']:
                    _field(rid,f,stored)
            if stage == STAGES[3]:
                st.caption('First record the effectiveness check, including the verifier and date. Then record the decision on this specific problem.')
                for f in ['verification_method','verification_result','verification_evidence']:
                    _field(rid,f,stored)
            if stage == STAGES[3]:
                for f in ['reviewer','review_date','decision_reason']: _field(rid,f,stored)
                if rid.startswith('HS'):
                    st.button('Reopen legal assessment', key=f'plan.hs.{rid}',on_click=state.go,args=(REVIEW_TITLE,))
                else:
                    st.button('Approve resolution for this finding',key=f'plan.resolve.{rid}',on_click=_decide,args=(rid,'RESOLVED'))
                    st.button('Keep this finding open',key=f'plan.open.{rid}',on_click=_decide,args=(rid,'OPEN'))
                current = state.assessment()
                if stored.get('decision') == 'RESOLVED':
                    if approved(current,rid): st.success('Resolution approved for the recorded evidence. The engine still checks all applicable conditions.')
                    else: st.warning('The approval is incomplete or its supporting information changed. Review again.')
                elif stored.get('decision') == 'OPEN': st.info('Reviewer decision: the finding remains open.')
                st.caption('Missing answers must be updated at source. An approval does not erase evidence gaps or legal stop conditions.')
            with st.expander('Technical details'):
                st.code(rid)
                st.write(info['ids'])
                if stored.get('review_history'): st.json(stored['review_history'])
