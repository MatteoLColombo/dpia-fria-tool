"""Operational work records and per-finding approval; no external inference."""
import hashlib
import json

TITLES = {
    'EG-01': 'Complete the information needed for the assessment',
    'QUAL-01': 'Explain and substantiate the assessment reasoning',
    'LEGAL-01': 'Clarify the legal basis and purpose of the processing',
    'DATA-01': 'Review the collection, use and retention of data',
    'DQ-01': 'Verify data quality in the actual use context',
    'BIAS-01': 'Investigate unequal effects and discrimination risks',
    'TRANS-01': 'Provide understandable information to affected people',
    'REM-01': 'Enable affected people to challenge the outcome',
    'SCR-01': 'Establish meaningful human oversight',
    'SCR-02': 'Review the justification for the interference with rights',
    'SCR-03': 'Review the remaining risk to fundamental rights',
    'CROSS-01': 'Define the intended purpose',
    'CROSS-02': 'Check the actual use against the intended purpose',
    'FRIA-27A': 'Align the use process with the intended purpose',
    'FRIA-27B': 'Specify how long and how often the system is used',
    'FRIA-27C': 'Identify affected people and groups',
    'FRIA-27D': 'Assess harm using the relevant provider information',
    'FRIA-27E': 'Specify how human oversight will work',
    'FRIA-27F': 'Define the response to harm and the complaints procedure',
    'FRIA-27G': 'Check whether the previous assessment fits this use',
    'FRIA-27H': 'Update the assessment after changes',
    'FRIA-27I': 'Identify which findings are supported by the existing DPIA',
    'FRIA-27J': 'Document notification of the FRIA results or the applicable exemption',
    'HS01': 'Legal review of the purpose and possible lawful redesign',
    'HS02': 'Legal review of the legal basis and possible alternatives',
    'HS03': 'Legal review of data reuse and possible reconfiguration',
    'HS04': 'Legal review of use outside the intended purpose',
    'HS05': 'Legal review of whether essential human oversight can be provided',
    'HS06': 'Legal review of whether effective contestability can be provided',
    'HS07': 'Legal review of a potentially prohibited use',
    'HS08': 'Legal review of serious harm remaining after safeguards',
    'HS09': 'Legal review of serious harm to a vulnerable group',
    'PROP-00': 'Review the proportionality reasoning',
    'PROP-01': 'Complete the factual basis for the proportionality review',
    'PROP-02': 'Explain how the actual use serves the stated purpose',
    'PROP-03': 'Assess less intrusive alternatives',
    'PROP-04': 'Limit the processing and use to what is necessary',
    'PROP-05': 'Substantiate the necessity and proportionality reasoning',
    'PROP-06': 'Verify the safeguards relied on in the assessment',
    'PROP-07': 'Review remaining interference with fundamental rights',
    'PROP-08': 'Address the shortcomings identified in the proportionality review',
    'PROP-09': 'Review whether serious remaining harm can be reduced',
    'PROP-10': 'Assess concentrated effects on vulnerable groups',
    'PROP-11': 'Record the proportionality review',
    'MIT-01': 'Turn the assessment findings into concrete actions',
    'MIT-02': 'Complete and verify measures required before use',
    'MIT-03': 'Obtain evidence of effectiveness and remaining risk',
    'MIT-04': 'Reassess stop conditions using the relevant evidence',
    'RSEL-01': 'Include and assess the relevant fundamental rights risks',
    'RACT-01': 'Reassess the risks included in this assessment',
    'ROLE-01': 'Confirm the organisation’s role',
    'SCOPE-01': 'Complete the assessment scope',
    'FLOW-01': 'Review a potentially prohibited practice',
    'FLOW-02': 'Confirm the high-risk classification',
    'FLOW-03': 'Confirm the applicable provider requirements',
    'FLOW-04': 'Assess the need for stakeholder involvement',
    'FLOW-05': 'Confirm whether the FRIA requirements apply',
    'SEP-01': 'Identify the need to involve affected people',
    'SEP-02': 'Decide and explain the approach to consultation',
    'SEP-03': 'Reassess assumptions using stakeholder evidence',
    'SEP-04': 'Respond to safeguards and remedies requested by stakeholders',
}
for suffix, title in zip('ABCDEFGHIJ', [
    'Maintain an iterative risk management process', 'Assess health and safety risks',
    'Assess fundamental rights risks', 'Assess risks from the intended use',
    'Assess risks from foreseeable misuse', 'Document foreseeable misuse',
    'Feed monitoring findings into risk review', 'Adopt targeted risk management measures',
    'Assess and justify the remaining risk', 'Test against defined criteria and thresholds']):
    TITLES['RMS-9' + suffix] = title

ACTIONS = {
    'LEGAL-01': (
        'Identify and substantiate the legal basis and purpose for each relevant processing activity. '
        'Distinguish missing documentation from an established absence of a valid basis.',
        'If the review finds no valid basis, examine whether the processing or purpose can be lawfully redesigned. '
        'Record the determination and update the source answers; a proposed measure does not itself establish a basis.'),
    'FRIA-27A': ('Compare the intended purpose with what the system actually does in the workflow.',
                  'Document any mismatch, define the changes needed, and verify the revised workflow.'),
    'FRIA-27F': ('Define who responds when harm occurs and how affected people can submit a complaint.',
                  'Test the procedure on representative cases, including correction and reconsideration of outcomes.'),
    'DQ-01': ('Test data quality and output reliability for the types of records and people actually affected.',
              'Address the identified gaps and document the results of testing in the revised context.'),
    'DATA-01': ('Review which data are needed, where they come from, who can access them and how long they are kept.',
                'Implement the justified restrictions and verify that they work in practice.'),
    'PROP-04': ('Identify which data, population, frequency, duration or access exceeds the justified scope.',
                'Define narrower arrangements, document their implementation and assess their effects.'),
    'QUAL-01': ('Identify which explanations are unsupported or insufficient for the conclusion drawn.',
                'Add case-specific reasons and supporting evidence, then update the relevant answers.'),
    'FRIA-27J': ('Check and document the applicable notification requirement or exemption.',
                  'Record the notification reference and date, or the reasoned exemption basis, in the assessment.'),
}


def title(rule_id):
    return TITLES.get(rule_id, 'Review the assessment finding')


def findings(result, saved):
    """One work card per rule, preserving distinct finding kinds within the card."""
    grouped = {}
    for attr, kind in [('evidence_gaps', 'Information needed'), ('open_remediations', 'Corrective action needed'),
                       ('pending_reviews', 'Review needed'), ('verification_requests', 'Check needed'),
                       ('open_conditions', 'Ongoing condition')]:
        for f in getattr(result, attr):
            entry = grouped.setdefault(f.rule_id, {'kinds': [], 'ids': []})
            if kind not in entry['kinds']: entry['kinds'].append(kind)
            entry['ids'] = sorted(set(entry['ids']) | set(f.ids))
    for rid, hs in result.hard_stops.items():
        if hs.opened:
            grouped.setdefault(rid, {'kinds': [], 'ids': []})['kinds'].append('Stop condition: legal review')
    for rid in saved:
        grouped.setdefault(rid, {'kinds': ['Saved work — check current assessment'], 'ids': []})
    return grouped


def fingerprint(state, rule_id):
    """Conservative invalidation: changes in assessment evidence or this action require review."""
    data = state.model_dump(mode='json')
    if data.get('alternatives_review') is None:
        data.pop('alternatives_review', None)  # preserve signatures on legacy records
    item = data.pop('action_plan', {}).get(rule_id, {})
    for key in ['reviewed_fingerprint', 'decision', 'review_history']:
        item.pop(key, None)
    for key in ['governance', 'api_suggestions', 'assessment_id', 'residual_reviews']:
        data.pop(key, None)
    data['action'] = item
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def approval_ready(item):
    return bool(item and all(str(getattr(item, k)).strip() for k in (
        'action', 'rationale', 'owner', 'implementation', 'verification_method', 'verification_result',
        'reviewer', 'review_date', 'decision_reason')) and item.evidence_refs and item.verification_evidence)


def approved(state, rule_id):
    item = state.action_plan.get(rule_id)
    return bool(approval_ready(item) and item.decision == 'RESOLVED'
                and item.reviewed_fingerprint == fingerprint(state, rule_id))


def residual_approved(state, risk_id):
    review = state.residual_reviews.get(risk_id)
    if not review or not all([review.reviewer.strip(), review.review_date.strip(), review.rationale.strip(),
                              review.evidence_refs, review.mitigation_ids]):
        return False
    return review.reviewed_fingerprint == fingerprint(state, risk_id)
