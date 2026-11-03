# Fundamental Rights Assessment

Assessing fundamental rights risks, safeguards and governance decisions. The DPIA is the
methodological reference for the assessment framework; AI Act obligations for providers
(Art. 9) and deployers (Art. 27) are covered by the modules that apply to the case.

Developed by Federica Paolucci, Eleonora Silva and Matteo Colombo, for the DIGCON — FIS-funded
project, Baffi Centre, Bocconi University, PI Oreste Pollicino.

**Open the tool: https://fundamental-rights-assessment.streamlit.app/**

The logic is deterministic and follows the DIGCON T17 decision engine, workbook version
`T17-v1.0.1`. With the public link no answers leave the browser session: there is no database
and no external API call. A private link, for the research team only, lets an OpenAI model
(EU data residency) suggest the interpretive reviewer checks in section 3.3; a person confirms,
changes or clears each one. A suggestion counts in the outcome only once a person has reviewed
it, and the audit trail records both.

> Research prototype for research and evaluation purposes only. This tool does not certify
> legal compliance or replace legally required assessments or human decision-making. Do not
> enter personal data, confidential DPIAs, trade secrets or sensitive organisational information.

## Using it

The assessment runs in four steps, shown in the left rail:

1. **Assessment framework**: assessment workspace, assessment scope, WHAT, HOW, WHY.
2. **Regulatory requirements**: applicable assessment requirements, then provider obligations
   (Art. 9) and the deployer FRIA (Art. 27), which open only when the step 1 answers call for them.
3. **Rights assessment**: stakeholder involvement, fundamental rights risks, legal and procedural
   review, safeguards and mitigation, legal constraints and stop conditions.
4. **Findings and decision**: assessment findings (the recommended outcome), then the governance
   decision, which a person records.

Answers are autosaved in the browser. To keep an assessment or move it to another computer,
use **Save progress** to download a JSON file, and load it again from **Assessment workspace →
Resume an assessment**.

### Sample assessments

`samples/` holds ready-made assessments to load instead of typing one in:

| File | Outcome |
|---|---|
| `role-provider-O1.json`, `role-deployer-O1.json`, `role-joint-O1.json` | one complete assessment per role, O1 |
| `outcome-O1-proceed.json` … `outcome-O5-hard-stop-HS07.json` | one per outcome, O1 to O5 |
| `hard-stop-unknown-not-O5.json` | an unknown hard stop element gives an evidence gap (O4), never O5 |

## Running it on your own machine

Python 3.11 or newer.

```
git clone https://github.com/MatteoLColombo/dpia-fria-tool.git
cd dpia-fria-tool
python -m venv .venv
.venv\Scripts\activate          # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The app opens at http://localhost:8501.

## For developers

```
pip install -r requirements-dev.txt
python -m pytest                       # engine, test fixtures, UI and samples
python tools/make_samples.py           # rebuild samples/ after an engine or config change
```

- `config/` holds the questions, rules, risks, mitigations and stakeholder engagement fields
  as YAML, exported from the frozen workbook. The rules are data: the engine has no rule IDs
  written into its code.
- `src/digcon/engine/` is the decision engine (pure functions), `src/digcon/ui/` the Streamlit
  interface.
- `tests/fixtures/` translates the workbook's test fixtures into concrete assessment states;
  the expected outcomes come from the workbook and are never changed to make a test pass.
- `DESIGN.md` describes the visual system.
