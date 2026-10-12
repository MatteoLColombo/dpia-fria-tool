# DPIA-based Fundamental Rights Assessment Tool

A research prototype that walks an AI system through a DPIA-based fundamental rights
assessment, with role-specific AI Act add-ons for providers (Art. 9) and deployers (Art. 27).
It ends with a recommended outcome, O1 (proceed) to O5 (do not proceed), and an audit trail
of every rule applied.

The logic is deterministic and follows the DIGCON T17 decision engine, workbook version
`T17-v1.0.1`. No answers leave the browser session: there is no database and no external
API call.

> Research prototype, for academic and sandbox testing only. Do not enter personal data,
> confidential DPIAs, trade secrets or sensitive organisational information.

## Using it

The assessment runs in four steps, shown in the left rail:

1. **Core**: start, introduction and scoping, what, how, why.
2. **Role-specific add-ons**: routing, then the provider (Art. 9) and deployer (Art. 27)
   sections, which open only when the core answers call for them.
3. **Risk analysis and safeguards**: stakeholder engagement, risk register, rules and scrutiny,
   mitigation plan, hard stop gate.
4. **Outcome**: recommended outcome, then the governance decision, which a person records.

Answers are autosaved in the browser. To keep an assessment or move it to another computer,
use **Save progress** to download a JSON file, and load it again from **Start → Resume an
assessment**.

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
git clone https://github.com/federicapaolucci-hash/dpia-fria-tool.git
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
