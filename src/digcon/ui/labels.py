"""Interface texts that the workbook does not provide. Enum labels come from digcon.domain.enums.label."""

from __future__ import annotations

from digcon.domain.enums import Outcome, Phase

APP_TITLE = "Fundamental Rights Assessment"
APP_CAPTION = "Assessing fundamental rights risks, safeguards and governance decisions."
FOOTER = "DIGCON — FIS-funded project, Baffi Centre, Bocconi University · All rights reserved"
CREDITS = "Developed by Federica Paolucci, Eleonora Silva and Matteo Colombo."
BYLINE = "By Federica Paolucci, Eleonora Silva and Matteo Colombo · DIGCON, Baffi Centre, Bocconi University"
DISCLAIMER = (
    "**Research prototype** for research and evaluation purposes only. This tool does not certify legal compliance "
    "or replace legally required assessments or human decision-making. Do not enter personal data, confidential "
    "DPIAs, trade secrets or sensitive organisational information."
)

METHODOLOGY = """
**What this assessment does**

DIGCON examines how a concrete AI use can affect people and fundamental rights, what safeguards are available,
who is responsible, and whether the evidence supports the proposed decision. The DPIA provides a methodological
reference. The research framework can be used beyond the statutory scope of an individual assessment obligation.

**How to work through it**

1. Describe the system, its actual use, the people affected and the organisation’s responsibilities.
2. Explain which legal requirements apply. The provider risk management module and deployer FRIA have separate scopes.
3. Assess harm as evidence, then argue each right engaged: legality, aim and suitability once for the use; then,
   for each right, the interference, whether the right admits limitation or its essence is affected, necessity,
   guarantees and remedies, and the balancing in the strict sense (Article 52(1) of the Charter).
4. Address findings in the action plan, verify the evidence, record new determinations, and record the
   organisation’s reasoned decision.

**Law and DIGCON method**

[Article 9 AI Act](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-9) concerns the risk management system
for high-risk AI systems. [Article 27 AI Act](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-27) concerns
FRIAs by the deployers and for the uses within its scope. High-risk status or a joint role alone does not establish
that Article 27 applies. Each module explains the relevant paragraphs next to the questions.
The tool uses recorded applicability answers; it does not independently validate the legal classification or applicable dates.

The four risk dimensions, outcome categories, action records and review workflow are DIGCON methodological choices.
They are not statutory scoring rules. Use existing documentation where relevant, identifying the section and explaining
what it establishes in this context. A document reference is not, by itself, evidence of adequacy.

**From a finding to action**

Distinguish missing information, an established shortcoming, a risk of harm and a legal determination still needed.
Adding a missing document is an assessment task; changing a process to reduce harm is a mitigation measure.
Both may require action, but they serve different purposes.

Follow the four steps: understand the problem; plan the action; record implementation; verify and decide.
Explain why each measure addresses the particular problem. Identify the implementer, the effectiveness verifier
and the person deciding on that finding, including provider and deployer contributions where needed.
A proposed measure does not establish implementation; implementation does not establish effectiveness;
effectiveness does not automatically close a finding. Closure requires a specific reasoned human decision.

Reassess scale, scope, reversibility and probability separately, linking each proposed change to verified controls
and supporting evidence. Unverified residual values do not replace the initial risk. A confirmed legal stop condition
requires a new reasoned legal determination based on changed facts or safeguards; an action plan cannot override it.

**Reading the result**

Unknown, not applicable and information held by another actor are distinct from a negative answer.
Colours describe individual checks, not general permission to proceed. A valid audit trail means the recorded
reasoning can be traced; it does not establish completeness, adequacy or legality.
The tool’s outcome is a recommendation. The organisation records its governance decision and reasons separately.
"""

# The four steps of 00_MAPPA_FLUSSO: common core, add-ons opened after scoping, transversal modules, convergence.
STEP_CORE = "Step 1 — Assessment framework"
STEP_ADDONS = "Step 2 — Regulatory requirements"
STEP_ANALYSIS = "Step 3 — Rights assessment"
STEP_OUTCOME = "Step 4 — Findings and decision"
STEP_TEXT = {
    STEP_CORE: "Common to providers and deployers: the assessment scope, then WHAT → HOW → WHY. "
               "No later step replaces these questions.",
    STEP_ADDONS: "The AI Act requirements that apply once the scope is set: Article 9 for providers, Article 27 (FRIA) "
                 "for deployers within its scope. A joint role requires a separate check of each obligation. These modules "
                 "do not cover every potentially applicable legal requirement.",
    STEP_ANALYSIS: "Built on steps 1 and 2: stakeholder involvement and the risk register as evidence, the legal and "
                   "procedural checks, then an argument for each right engaged — legality, aim and suitability once, "
                   "then for each right its interference, threshold, necessity, guarantees and balancing — the steps "
                   "across rights, the action plan and the stop conditions.",
    STEP_OUTCOME: "The findings show whether the assessment is complete and the position for each right. They are the "
                  "tool's reading of your determinations: the final decision belongs to the organisation and is "
                  "recorded in 4.2.",
}

PHASE_TITLES = {
    Phase.INTRO: "1.1 Assessment scope",
    Phase.WHAT: "1.2 WHAT — System and context",
    Phase.HOW: "1.3 HOW — Governance and oversight",
    Phase.WHY: "1.4 WHY — Legal justification",
    Phase.PROVIDER: "2.1 Systemic risk management",
    Phase.DEPLOYER: "2.2 Fundamental rights impact assessment (FRIA)",
}

SUBSECTIONS = {"Scoping e ruoli": "Scope and roles"}

OUTCOME_TITLES = {
    Outcome.O1: "O1 — Proceed",
    Outcome.O2: "O2 — Proceed subject to conditions",
    Outcome.O3: "O3 — Revision required",
    Outcome.O4: "O4 — Assessment incomplete — evidence gaps",
    Outcome.O5: "O5 — Cannot proceed under current conditions",
}
OUTCOME_TEXT = {
    Outcome.O1: "No stop condition, material evidence gap, open remediation or restrictive condition. Ordinary monitoring and review may remain.",
    Outcome.O2: "Only explicit pilot, deployment or continuous conditions remain. Proceed subject to those conditions.",
    Outcome.O3: "At least one required remediation is still open, failed or not verified. Revise before proceeding.",
    Outcome.O4: "Material information needed for a required conclusion is missing or unknown. Complete the assessment.",
    Outcome.O5: "At least one stop condition (HS01–HS10) is fully established and confirmed by legal review. A mitigation plan cannot override it.",
}
RECOMMENDATION_NOTE = (
    "This is the tool's reading of your determinations, not a decision: the final decision belongs to the "
    "organisation and is recorded in 4.2 Governance decision."
)
POSITION_TEXT = {
    "CLEAR": "Every engaged right has a complete argument, and no step found an unjustified interference. This is the "
             "assessors' finding on the record; the tool does not call the use proportionate.",
    "CONDITIONS": "The argument supports the use while stated measures stay in place during use.",
    "INCOMPLETE": "Steps are missing, cannot yet be determined, or are out of date. Complete them before relying on a position.",
    "STOP_EXCLUDED": "A legal review excluded a stop condition; the step that raised it must be revised and the argument continued.",
    "REVISION": "At least one step requires the use to change. Plan the action, verify it, and record new determinations.",
    "STOP_PENDING": "A stop condition is raised and awaits the legal review. No balancing or action plan can replace it.",
    "STOP_CONFIRMED": "A stop condition is confirmed by legal review. The use cannot proceed as designed; a redesign opens a new version.",
}


START_TITLE = "1.0 Assessment workspace"
ROUTING_TITLE = "2.0 Applicable assessment requirements"
SEP_TITLE = "3.1 Stakeholder involvement"
RISKS_TITLE = "3.2 Fundamental rights risks"
RULES_TITLE = "3.3 Legal and procedural checks"
SCREENING_TITLE = "3.4 Rights screening and the use as a whole"
ARGUMENT_TITLE = "3.5 Argument per right"
CROSS_TITLE = "3.6 Across rights"
MITIGATION_TITLE = "3.7 Safeguards and action plan"
REVIEW_TITLE = "3.8 Legal constraints and stop conditions"
RESULT_TITLE = "4.1 Assessment findings"
GOVERNANCE_TITLE = "4.2 Governance decision"

# Notes shown under specific questions. Interface guidance only: they change no logic.
QUESTION_NOTES = {
    "C05": "For high-risk systems, the selected role determines which requirements apply: provider risk management under Article 9, deployer FRIA under Article 27 where applicable, or both for joint roles.",
    "C06": "This answer is recorded for context. The organisation’s selected role determines the applicable modules.",
    "FOLLOW": "A high-risk classification opens the regulatory requirements for the organisation’s selected role.",
    "D00": "Confirming applicability opens the FRIA questions under Article 27.",
    "C43": "Record evidence of effectiveness here. A lower residual risk requires a separate documented and verified reassessment in Fundamental rights risks.",
    "C48": "Record evidence of effectiveness here. A lower residual risk requires a separate documented and verified reassessment in Fundamental rights risks.",
    "C34": "Record the initial risk from a prior assessment. It does not replace this tool’s risk assessment. Choose Not applicable if there is no prior assessment.",
    "C35": "Record the residual risk from a prior assessment. It does not replace the separate reassessment here. Choose Not applicable if there is no prior assessment.",
    "D04": "Select the concrete risks relevant to this use, then assess them in Fundamental rights risks.",
}



def subsection(name: str) -> str:
    return SUBSECTIONS.get(name, name)


# English versions of the hard-stop elements (05_RULES has them in Italian only), AS-037: provisional,
# display only. The engine, the audit trail and config/ keep the workbook text.
HS_ELEMENTS = {
    "HS01": ("Purpose manifestly unlawful", "Reasoned legal determination",
             "Purpose cannot be redefined in a lawful form"),
    "HS02": ("C14 = No", "No valid alternative legal basis (alternatives documented)", "No lawful redesign possible"),
    "HS03": ("Reuse of data", "Incompatibility established",
             "Cannot be reconfigured (purpose restriction / new collection)"),
    "HS04": ("N02 = No", "Grave risk to rights", "Use cannot be reconfigured"),
    "HS05": ("Human oversight essential", "Structurally impossible", "Not remediable"),
    "HS06": ("Contestability essential", "Structurally impossible", "Not remediable"),
    "HS07": ("Use expressly prohibited by applicable law (closed list)",),
    "HS08": ("Grave harm to rights established", "Mitigations assessed and insufficient",
             "Risk cannot be reduced to an acceptable level"),
    "HS09": ("Vulnerable group identified", "Grave harm specific to the group", "Not mitigable"),
    "HS10": ("A right admitting no limitation is limited, or the essence of a right is affected",
             "No redesign leaves the right or its essence intact"),
}

# Workbook texts shown in the interface: English for the ones the workbook has in Italian (AS-037), reworded
# where they carry internal jargon. Meaning unchanged.
WORKBOOK_TEXT = {
    **{(f"{hs}.E{i}", "text"): t for hs, els in HS_ELEMENTS.items() for i, t in enumerate(els, 1)},
    **{(hs, "trigger_text"): " AND ".join(els) for hs, els in HS_ELEMENTS.items()},
    ("EG-01", "trigger_text"): "Necessary information missing or not sufficiently determined",
    ("FLOW-03", "trigger_text"): "High-risk = Yes AND role = Provider/Joint",
    ("CROSS-02", "trigger_text"): "Use case not consistent with the intended purpose",
    ("QUAL-01", "trigger_text"): "Reasoning field not empty but substantially insufficient",
    ("G01", "purpose"): "Final decision, distinct from the recommended outcome",
    ("G02", "purpose"): "Identifies the responsible person or body",
    ("G03", "purpose"): "Sets the review date",
    ("G04", "purpose"): "Records conditions and limitations",
    ("G05", "purpose"): "Records the reasoning of the decision",
    ("SEP00", "activation"): "Assess after affected persons/groups and material harm context are identified; "
                             "C55 is evidence, not a precondition.",
    ("RSEL-01", "trigger_text"): "A question, rule or evidence identifies a harm, affected right/area or material "
                                 "contextual risk that must be represented in the fundamental rights risks (3.2).",
}


def workbook_text(item_id: str, field: str, text: str) -> str:
    return WORKBOOK_TEXT.get((item_id, field), text)


# Names of the sections in the left menu.
NAV_LABELS = {
    START_TITLE: "1.0  Assessment workspace",
    PHASE_TITLES[Phase.INTRO]: "1.1  Assessment scope",
    PHASE_TITLES[Phase.WHAT]: "1.2  WHAT — System and context",
    PHASE_TITLES[Phase.HOW]: "1.3  HOW — Governance and oversight",
    PHASE_TITLES[Phase.WHY]: "1.4  WHY — Legal justification",
    ROUTING_TITLE: "2.0  Applicable requirements",
    PHASE_TITLES[Phase.PROVIDER]: "2.1  Provider obligations · Art. 9",
    PHASE_TITLES[Phase.DEPLOYER]: "2.2  Deployer FRIA · Art. 27",
    SEP_TITLE: "3.1  Stakeholder involvement",
    RISKS_TITLE: "3.2  Fundamental rights risks",
    RULES_TITLE: "3.3  Legal and procedural checks",
    SCREENING_TITLE: "3.4  Rights screening, use as a whole",
    ARGUMENT_TITLE: "3.5  Argument per right",
    CROSS_TITLE: "3.6  Across rights",
    MITIGATION_TITLE: "3.7  Safeguards and action plan",
    REVIEW_TITLE: "3.8  Stop conditions",
    RESULT_TITLE: "4.1  Assessment findings",
    GOVERNANCE_TITLE: "4.2  Governance decision",
}
