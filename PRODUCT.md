# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are participants in the DIGCON Fundamental Rights Assessment Sandbox: teams at organisations that provide or deploy AI systems (compliance, DPO, legal), assessing one of their own systems. They usually fill in the assessment on their own at a desktop, often across several sittings, saving and reloading the assessment as JSON between sessions.

The DIGCON research team (the supervising professor plus the provider-side and deployer-side leads) owns the methodology and judges whether the tool applies it correctly. They are reviewers of the tool, not its main day-to-day users.

## Product Purpose

The tool supports a structured assessment of fundamental rights risks, safeguards and decision-making processes around an AI system. The DPIA is the methodological reference for the assessment framework; EU AI Act obligations for providers (Art. 9) and deployers (Art. 27) are covered by the modules that apply. It applies the T17 decision engine deterministically. Users answer a structured questionnaire, and the engine routes them, calibrates the risks, tracks mitigations and evidence, checks the hard-stop conditions and recommends one of five outcomes, O1 (can proceed) to O5 (cannot proceed). Every outcome comes with an audit trail and downloadable Markdown and JSON reports.

The assessment succeeds when a participant reaches a defensible recommended outcome. That means seeing exactly which evidence is missing, which mitigations are still open and which rules fired, and being able to hand the report to whoever makes the governance decision.

## Positioning

- The tool reaches its result through traceable rules, not a score or an LLM opinion. Each recommendation traces back to specific rule IDs in a versioned specification (the T17 workbook).
- Uncertainty is kept visible rather than resolved. "Unknown", "not applicable" and "not owned" are never treated as "no". They produce evidence gaps or verification requests.
- The tool only recommends an outcome. It never declares a system proportionate or disproportionate, and the final governance decision is recorded separately by a person.

## Operating Context

- A self-paced, step-by-step flow:
  1. Assessment framework (workspace, assessment scope, WHAT, HOW, WHY).
  2. Regulatory requirements, which apply according to the scope answers.
  3. Rights assessment: stakeholder involvement (SEP), fundamental rights risks, legal and procedural checks, the argument per right (RA-1: screening, use as a whole, each engaged right, across rights), safeguards and action plan, stop conditions.
  4. Findings and decision: completeness and position per right and overall, then the governance decision.
- Sessions are resumed by downloading and re-uploading the assessment JSON. There is no account and no database.
- Results leave the tool as Markdown, JSON and CSV exports, which then feed an organisation's own DPIA, FRIA and governance documents.
- It runs as a Streamlit app, probably published from the public `main` branch on Streamlit Community Cloud. Development happens on `rewrite/t17-engine`.

## Capabilities and Constraints

- **Stack:** Python with Streamlit, Pydantic v2 and PyYAML. Questions, rules, risks, mitigations and SEP fields are data in `config/`, generated from the frozen workbook (`T17-v1.0.1`). The UI is rendered from `questions.yaml`.
- **The engine is pure and deterministic.** Outcome precedence is O5 → O4 → O3 → O2 → O1. O5 can only come from hard stops whose constituent elements are fully MET. Only mitigations marked "verified effective" lower residual risk.
- **Every closed question offers Unknown, N/A and Not owned** wherever its answer model allows them.
- **Out of scope for now:** LLM/API interpretation (there is only a stub slot in `interpret/`), a database, a human-gate workflow (it is a manually filled field), and batch runs.
- **Delivery deadline:** 12 October 2026. The visual redesign was brought forward and ships before that delivery (decided 2026-10-09). Copy, credits and disclaimer stay.
- **Language:** code, identifiers and UI text are in English.
- **The repo is public.** Nothing from the private specification folder goes into it.

## Brand Commitments

- **Title:** "Fundamental Rights Assessment". **Subtitle:** "Assessing fundamental rights risks, safeguards and governance decisions." (renamed 2026-10-17: no "DPIA-based" in the title).
- **Credits:** byline under the subtitle, "By Federica Paolucci, Eleonora Silva and Matteo Colombo · DIGCON, Baffi Centre, Bocconi University" (added 2026-10-17, at the top so it is visible); footer "DIGCON — FIS-funded project, Baffi Centre, Bocconi University · All rights reserved".
- **Disclaimer:** "Research prototype for research and evaluation purposes only. This tool does not certify legal compliance or replace legally required assessments or human decision-making. Do not enter personal data, confidential DPIAs, trade secrets or sensitive organisational information." It must stay prominent.
- **Interface vocabulary:** no "sandbox" anywhere in the interface (it stays in internal research documentation), and no user-facing "routing", "add-on", "gate" or "workbook". Rule and question IDs stay visible for traceability.
- **Voice:** precise, legal-methodological and non-promotional. Never imply that the tool gives a legal conclusion.
- **Institutional branding:** no binding Bocconi or Baffi brand guidelines or logos have been given. Do not add institutional marks without confirmation.

## Evidence on Hand

- UI copy, labels, methodology text, credits and disclaimer are in `src/digcon/ui/labels.py`.
- The engine configuration is in `config/`. It holds 74 questions, 79 rules, 11 risks, 50 mitigation templates and 15 SEP fields.
- `tests/fixtures/` holds the 46 workbook test fixtures, which are concrete example assessment states.
- **Not available:** no real user testimonials, adoption figures, case studies or pilot results. Do not fabricate any.

## Product Principles

1. **Traceability over persuasion.** Every on-screen judgement must point back to the rule, input or evidence that produced it.
2. **Never collapse uncertainty.** Unknown, missing and not-owned answers stay visibly distinct from "no", and they stay visible all the way to the outcome.
3. **Recommend, don't decide.** Keep the engine's recommendation clearly separate from the human governance decision.
4. **Support long, interrupted work.** Users fill in a long questionnaire on their own, so progress, open items and the way to resume must always be obvious.
5. **Research-grade honesty.** The tool presents itself as a sandbox prototype, never as a compliance certification.
