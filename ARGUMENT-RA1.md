# Rights argument RA-1 (draft)

Status: draft for methodological validation. It changes step 3 and the way the result is read. It
should be taken into the workbook, with a new version number, before it is presented as part of T17.
Background: the comparative note on the Commission's draft FRIA template (16–17 November 2026),
decisions 1–3.

## What changes

Step 3 is now an argument per right, which a third party can follow and contest:

| Section | Content |
|---|---|
| 3.1–3.2 | Stakeholder involvement; the risk register, now evidence of the intensity of an interference |
| 3.3 Legal and procedural checks | The workbook's reviewer checks, without the PROP-* checks |
| 3.4 Rights screening, use as a whole | Every right of the register screened (engaged / not engaged with reasons); A1 legality, A2 legitimate aim, A3 suitability |
| 3.5 Argument per right | B1 right in context, B2 interference, B3 threshold (regime, essence), B4 necessity, B5 guarantees and remedies, B6 balancing in the strict sense, open points, revision plan |
| 3.6 Across rights | C1 cumulative interference, C2 conflicts between rights; positions at a glance |
| 3.7 Safeguards and action plan | Unchanged; measures carry their role (necessity, safeguard, remedy) |
| 3.8 Stop conditions | HS01–HS10, with the stops raised by the argument |

Each step is a **determination**: an option stated positively, reasons, sources, evidence, an optional
dissent with its author, and the name and date of the person who records it. Recording stores what
the determination relied on. A later change to those facts (the risk, the verified measures, the
purpose, the groups, an earlier step) marks it out of date.

## Positions

4.1 shows two things: whether the assessment is complete, and a position for each right.

| Position | When |
|---|---|
| Not engaged | Screened out with reasons, or no interference found (B2) |
| Incomplete | A step missing, undetermined or out of date |
| No unjustified interference found | B3 passed, B4 and B5 adequate, B6 in favour of the aim |
| Justified subject to conditions | B5 adequate while stated measures stay in place, or a continuous workbook measure |
| Revision required | B4, B5, B6 adverse (B6 adds a legal review), A1 quality deficient, A3 does not serve, C1 changes a conclusion, or a workbook remediation |
| Stop: legal review pending | A1 no basis (HS02), A2 aim not legitimate (HS01), B3 no limitation or essence affected (HS10), or a workbook stop opened |
| Stop: confirmed | The legal review establishes every element |
| Stop: excluded by legal review | The legal review finds an element not established; the step is revised and the argument resumes |

The overall position is the most serious one. O1–O5 appear only in exports and the audit trail:
stop confirmed → O5; incomplete or pending → O4; revision → O3; conditions → O2; otherwise O1. The
workbook's own outcome for steps 1–2 stays on record next to it.

**Revision loop.** For a right in revision, the assessor plans the action and links catalogue
measures (3.5). A measure verified effective in 3.7 marks the guarantees and the balancing out of
date; the assessor records them again on the changed facts. A confirmed stop is lifted only by a
redesign, which opens a new version. An action-plan approval never changes a determination.

**Governance (4.2).** The decision states whether it follows the overall position. A departure needs
reasons; the report shows it next to the position.

## Guidance on rights

`config/argument.yaml` holds the wording of every step (question, note, common mistake, example) and
a card for each right of the register: what it protects, the corresponding ECHR provision, the
limitation regime, the essence, typical interferences in AI uses, questions, sources. **All cards
are drafts until a member of the research team verifies them**; the interface and the report say so.
The other Charter rights follow in a second phase.

## Engine

The workbook engine is unchanged except for HS10 (`config/extension.yaml`), raised by B3. The
argument is read outside the engine (`src/digcon/argument`), on top of its result. PROP-* rules still
run but no longer set the position or appear in 3.3; API suggestions skip them.

## Effect on existing assessments

Files saved before RA-1 load unchanged and show "incomplete": they have no argument. The workbook
fixtures keep their expected outcomes; the test baseline gained a full argument (`argument:` in
`tests/fixtures/baseline.yaml`). `tests/test_argument.py` covers positions, the revision loop and the
stop paths, including a loop driven through the widgets.

## Open questions for the research team

1. HS04 (use outside the intended purpose) is read from A3. It could be read from A1.
2. PROP-05 (assertive reasoning) has no successor beyond required reasons and QUAL-01.
3. A dissent never changes the position. Should a dissent by the legal reviewer?
4. C1 and C2 go out of date whenever a B6 changes. This is strict; the team may prefer a narrower rule.
5. The cards must be verified, starting with the statements on the essence (Articles 7, 8, 11, 47).
