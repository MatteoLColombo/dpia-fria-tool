"""Display-only wording. Stored states and decision conditions are unchanged.

Every T17 element is explicitly classified: a confirmed neutral fact must not
be coloured as a failure, and an unknown future element gets neutral labels.
"""

PROBLEMS = {
    'QUAL-01.E1': 'Is the submitted explanation of the operational and organisational context insufficient?',
    'QUAL-01.E2': 'Is the submitted explanation of the legal basis insufficient?',
    'QUAL-01.E3': 'Is the submitted explanation of purpose limitation or compatibility insufficient?',
    'QUAL-01.E4': 'Is the submitted explanation of data minimisation insufficient?',
    'QUAL-01.E5': 'Is the submitted explanation of retention periods insufficient?',
    'QUAL-01.E6': 'Is the submitted explanation of necessity insufficient?',
    'FRIA-27A.E1': 'Does the actual use process conflict with the intended purpose?',
    'FRIA-27D.E1': 'Were the specific risks assessed without the provider information required under Article 13?',
    'FRIA-27E.E1': 'Is human oversight insufficient when compared with the instructions for use?',
    'FRIA-27F.E1': 'Are the measures, governance arrangements or complaints mechanisms for risks that materialise absent or inadequate?',
    'HS01.E1': 'Is the purpose manifestly unlawful?',
    'HS01.E3': 'Is it impossible to redefine the purpose in a lawful form?',
    'HS02.E1': 'Does the assessment record that there is no legal basis for the processing?',
    'HS02.E2': 'Has the review of documented alternatives established that no valid alternative legal basis exists?',
    'HS02.E3': 'Is a lawful redesign impossible?',
    'HS03.E2': 'Has incompatibility of the data reuse been established?',
    'HS03.E3': 'Is reconfiguration impossible, including restricting the purpose or collecting new data?',
    'HS04.E1': 'Does the assessment record that the actual use is outside the intended purpose?',
    'HS04.E2': 'Does that use present a grave risk to fundamental rights?',
    'HS04.E3': 'Is it impossible to reconfigure that use?',
    'HS05.E2': 'Is essential human oversight structurally impossible in this use?',
    'HS05.E3': 'Is it impossible to remedy that inability to provide human oversight?',
    'HS06.E2': 'Is effective contestability structurally impossible in this use?',
    'HS06.E3': 'Is it impossible to remedy that inability to contest the decision?',
    'HS07.E1': 'Is this use expressly prohibited by the applicable law?',
    'HS08.E1': 'Has grave harm to fundamental rights been established?',
    'HS08.E2': 'Have the assessed mitigations proved insufficient?',
    'HS08.E3': 'Is it impossible to reduce the remaining risk to an acceptable level?',
    'HS09.E2': 'Has grave harm specific to the vulnerable group been established?',
    'HS09.E3': 'Is that group-specific harm incapable of being mitigated?',
    'HS10.E1': 'Does the use limit a right that admits no limitation, or affect the essence of a Charter right?',
    'HS10.E2': 'Is it impossible to redesign the use so that the right, or its essence, remains intact?',
    'LEGAL-01.E1': 'Is the reasoning on the legal basis or purpose limitation inadequate, or inconsistent with the recorded answers?',
    'DATA-01.E1': 'Is control over the data categories or sources inadequate for the purpose?',
    'DQ-01.E1': 'Are the data quality measures inadequate?',
    'BIAS-01.E1': 'Has a disproportionate impact on protected groups been detected?',
    'TRANS-01.E1': 'Is operational support for data subject rights inadequate?',
    'REM-01.E1': 'Are the measures enabling people to contest decisions inadequate?',
    'PROP-02.E1': 'Is the connection between the actual use and its stated purpose insufficiently demonstrated?',
    'PROP-03.E1': 'Was a reasonably practicable, less intrusive alternative capable of achieving the purpose excluded without sufficient justification?',
    'PROP-04.E1': 'Do the data, frequency, population, duration, access or scope exceed what the purpose requires?',
    'PROP-05.E1': 'Does the necessity reasoning merely assert a conclusion without examining harm, purpose, alternatives, safeguards and residual impact?',
    'PROP-05.E2': 'Does the proportionality reasoning merely assert a conclusion without examining harm, purpose, alternatives, safeguards and residual impact?',
    'PROP-06.E1': 'Is evidence missing of the operational effectiveness of safeguards relied on to reduce risk?',
    'PROP-06.E2': 'Is a declared safeguard not operational, relevant, specific, verifiable or capable of reducing likelihood or severity?',
    'PROP-07.E1': 'Does a material interference with fundamental rights remain after verified safeguards?',
    'PROP-09.E1': 'Is grave interference or harm sufficiently established?',
    'PROP-09.E4': 'Does the residual impact remain high?',
    'PROP-09.E5': 'Is further reasonable mitigation incapable of reducing the impact to an acceptable level?',
    'PROP-10.E2': 'Is the impact or residual risk more intense or concentrated on the vulnerable group?',
    'PROP-10.E3': 'Is grave group-specific harm established and apparently incapable of being mitigated?',
    'FRIA-27G.E1': 'Is the previous impact assessment unreferenced or insufficiently comparable to this context?',
    'FRIA-27I.E1': 'Is the DPIA reference missing or inadequate to verify the Article 27 element it is intended to cover?',
}

FACTS = {
    'HS01.E2': 'Has a reasoned legal determination been made about the unlawfulness of the purpose?',
    'HS03.E1': 'Are data being reused?',
    'HS05.E1': 'Is human oversight essential in this use context?',
    'HS06.E1': 'Is the ability to contest the decision essential in this use context?',
    'HS09.E1': 'Has a vulnerable group been identified?',
    'PROP-09.E2': 'Have the relevant safeguards been considered?',
    'PROP-09.E3': 'Have the relevant mitigations been considered?',
    'PROP-10.E1': 'Is a vulnerable group, or people in a situation of particular vulnerability, affected?',
}


def element_question(element_id, fallback):
    return PROBLEMS.get(element_id, FACTS.get(element_id, fallback))


def element_label(element_id, value):
    if value is None:
        return '⚪ Not yet assessed'
    if value == 'UNCERTAIN':
        return '🟡 Uncertain — more information needed'
    if element_id in PROBLEMS:
        return {'MET': '🔴 Yes — this problem is present',
                'NOT_MET': '🟢 No — this problem is not identified'}.get(value, '⚪ Not yet assessed')
    return {'MET': '🔵 Yes — confirmed', 'NOT_MET': '⚪ No — not established'}.get(value, '⚪ Not yet assessed')
