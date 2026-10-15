"""Text interpreter on the OpenAI Responses API with Structured Outputs (06_API).

The interpreter fills the same slots a person fills by hand: the MET / NOT_MET / UNCERTAIN state
of MANUAL rule elements, with the evidence it relied on. It never picks an outcome, never creates
rules, never invents enum values and never decides "proportionate / disproportionate"; the engine
does everything else, deterministically, on the states it returns.

One call per rule, carrying only that rule's elements and the answers the rule reads (its
encoding inputs), never the whole questionnaire. The output schema is built per call: element
IDs and evidence IDs are closed enums of what was sent, so the model cannot cite anything else.
Everything the model returns is validated again before it reaches the engine; rejected items are
recorded in the call log and the element simply stays not evaluated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from digcon.domain.enums import AnswerKind, ElementSource, RuleElementState, label
from digcon.domain.models import AssessmentState, ConfigBundle, ElementEvaluation, QuestionSpec, RuleElementSpec

PROMPT_VERSION = "p1"
SCHEMA_VERSION = "s1"
STATES = [s.value for s in RuleElementState]

INSTRUCTIONS = """\
You assist DIGCON, a deterministic decision engine for fundamental-rights impact assessments of AI systems.
You do one narrow job: evaluate the rule elements you are given against the evidence you are given.

For each element return a state:
- MET: the evidence establishes that the statement in the element is true.
- NOT_MET: the evidence establishes that the statement in the element is not true.
- UNCERTAIN: the evidence is missing, insufficient, contradictory or ambiguous for deciding.
Elements usually describe a deficiency or a condition: MET means the deficiency or condition is present.

Rules:
- Use only the evidence supplied. Do not assume facts that are not written there.
- An answer that is missing, UNKNOWN, N/A or NOT OWNED is never the same as NO.
- In evidence_refs cite only the evidence IDs supplied that support your evaluation. Never invent IDs.
  A MET or NOT_MET evaluation must cite at least one evidence ID.
- Do not decide the outcome of the assessment, do not conclude whether the processing is proportionate or
  disproportionate, and do not evaluate anything you were not asked about.
- rationale: one or two sentences explaining the evaluation, quoting the evidence where possible.
"""


class ResponsesClient(Protocol):
    """The part of ``openai.OpenAI`` the interpreter uses (lets tests pass a fake)."""

    responses: Any


@dataclass
class CallRecord:
    """One API call, for the audit log (06_API: prompt version, model, inputs, structured result)."""

    rule_id: str
    model: str
    reasoning_effort: str | None
    prompt_version: str
    schema_version: str
    timestamp: str
    request: dict[str, Any]
    raw_output: str | None = None
    usage: dict[str, Any] | None = None
    applied: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    error: str | None = None


def _option_labels(cfg: ConfigBundle) -> dict[tuple[str, str], str]:
    return {(s.id, o.code): o.label for s in cfg.questions.option_sets for o in s.options}


def _answer_text(cfg: ConfigBundle, q: QuestionSpec, answer, labels: dict[tuple[str, str], str]) -> str:
    if answer is None:
        return "NOT ANSWERED"
    if answer.state is not None:
        text = f"State: {label(answer.state)}"
    elif isinstance(answer.value, list):
        text = "; ".join(labels.get((q.option_set, v), v) for v in answer.value)
    else:
        text = labels.get((q.option_set, answer.value), answer.value) if q.kind is AnswerKind.SINGLE else answer.value
    if answer.detail:
        text += f"\nBasis / reference given: {answer.detail}"
    if answer.evidence_refs:
        text += f"\nEvidence references: {', '.join(answer.evidence_refs)}"
    return text


def pending_elements(cfg: ConfigBundle, state: AssessmentState, rule_ids: list[str] | None = None) -> list[RuleElementSpec]:
    """MANUAL elements the interpreter may fill: not set by a person (an earlier API value may be refreshed)."""
    out = []
    for rule in cfg.rules.rules:
        if rule_ids is not None and rule.id not in rule_ids:
            continue
        for el in rule.encoding.elements:
            ev = state.elements.get(el.id)
            if el.source is ElementSource.MANUAL and el.state_enum == "RuleElementState" and (
                ev is None or ev.source is ElementSource.API
            ):
                out.append(el)
    return out


def apply_evaluations(state: AssessmentState, evaluations: list[ElementEvaluation]) -> AssessmentState:
    """New state with the API evaluations laid in. A value a person set is never overwritten."""
    data = state.model_dump(mode="json")
    for ev in evaluations:
        current = state.elements.get(ev.element_id)
        if current is not None and current.source is not ElementSource.API:
            continue
        data["elements"][ev.element_id] = ev.model_dump(mode="json")
    return AssessmentState.model_validate(data)


class OpenAIInterpreter:
    """``Interpreter`` (interpret/base.py) backed by the Responses API. ``calls`` keeps one record per call."""

    def __init__(self, cfg: ConfigBundle, client: ResponsesClient, model: str, *,
                 reasoning_effort: str | None = None, max_output_tokens: int = 16000):
        # Reasoning tokens count towards max_output_tokens: keep it well above the size of the JSON.
        self.cfg = cfg
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.calls: list[CallRecord] = []
        self._labels = _option_labels(cfg)

    @property
    def provenance(self) -> str:
        effort = f"; effort {self.reasoning_effort}" if self.reasoning_effort else ""
        return f"openai:{self.model}{effort}; prompt {PROMPT_VERSION}; schema {SCHEMA_VERSION}"

    def evaluate(self, state: AssessmentState, elements: list[RuleElementSpec]) -> list[ElementEvaluation]:
        by_rule: dict[str, list[RuleElementSpec]] = {}
        for el in elements:
            by_rule.setdefault(el.id.split(".", 1)[0], []).append(el)
        out: list[ElementEvaluation] = []
        for rule_id, els in by_rule.items():
            out.extend(self._evaluate_rule(state, rule_id, els))
        return out

    # -- one rule ------------------------------------------------------------------------

    def request_for(self, state: AssessmentState, rule_id: str, elements: list[RuleElementSpec]) -> dict[str, Any]:
        rule = self.cfg.rule(rule_id)
        evidence = []
        for qid in rule.encoding.inputs:
            q = self.cfg.question(qid)
            evidence.append({"id": qid, "question": q.text, "answer": _answer_text(self.cfg, q, state.answers.get(qid), self._labels)})
        return {
            "rule_id": rule_id,
            "rule": rule.trigger_text,
            "elements": [{"element_id": el.id, "statement": el.text} for el in elements],
            "evidence": evidence,
        }

    @staticmethod
    def schema_for(request: dict[str, Any]) -> dict[str, Any]:
        refs = [e["id"] for e in request["evidence"]]
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["rule_id", "elements"],
            "properties": {
                "rule_id": {"type": "string", "enum": [request["rule_id"]]},
                "elements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["element_id", "state", "evidence_refs", "rationale"],
                        "properties": {
                            "element_id": {"type": "string", "enum": [e["element_id"] for e in request["elements"]]},
                            "state": {"type": "string", "enum": STATES},
                            "evidence_refs": {"type": "array", "items": {"type": "string", "enum": refs}},
                            "rationale": {"type": "string"},
                        },
                    },
                },
            },
        }

    def _evaluate_rule(self, state: AssessmentState, rule_id: str, elements: list[RuleElementSpec]) -> list[ElementEvaluation]:
        request = self.request_for(state, rule_id, elements)
        record = CallRecord(
            rule_id=rule_id,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            request=request,
        )
        self.calls.append(record)
        if not request["evidence"]:
            record.error = "rule has no encoded inputs: nothing to evaluate against"
            return []
        extra = {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort else {}
        try:
            response = self.client.responses.create(
                **extra,
                model=self.model,
                instructions=INSTRUCTIONS,
                input=json.dumps(request, ensure_ascii=False, indent=2),
                text={"format": {"type": "json_schema", "name": "rule_element_evaluation",
                                 "schema": self.schema_for(request), "strict": True}},
                max_output_tokens=self.max_output_tokens,
                store=False,
            )
        except Exception as exc:  # network, auth, quota: the element stays not evaluated
            record.error = f"{type(exc).__name__}: {exc}"
            return []
        record.raw_output = getattr(response, "output_text", None)
        if getattr(response, "status", None) == "incomplete":
            details = getattr(response, "incomplete_details", None)
            record.error = f"response incomplete: {getattr(details, 'reason', details)}"
            return []
        usage = getattr(response, "usage", None)
        record.usage = usage.model_dump() if hasattr(usage, "model_dump") else None
        return self._validate(record, request)

    def _validate(self, record: CallRecord, request: dict[str, Any]) -> list[ElementEvaluation]:
        try:
            payload = json.loads(record.raw_output or "")
        except ValueError:
            record.error = "output is not JSON"
            return []
        if not isinstance(payload, dict) or payload.get("rule_id") != request["rule_id"]:
            record.error = f"wrong or missing rule_id: {payload.get('rule_id') if isinstance(payload, dict) else payload!r}"
            return []
        asked = {e["element_id"] for e in request["elements"]}
        allowed_refs = {e["id"] for e in request["evidence"]}
        seen: set[str] = set()
        out = []
        for item in payload.get("elements", []):
            eid, st, refs = item.get("element_id"), item.get("state"), item.get("evidence_refs") or []
            if eid not in asked or eid in seen:
                record.rejected.append(f"{eid}: not requested or duplicated")
                continue
            seen.add(eid)
            if st not in STATES:
                record.rejected.append(f"{eid}: state {st!r} outside MET / NOT_MET / UNCERTAIN")
                continue
            if not set(refs) <= allowed_refs:
                record.rejected.append(f"{eid}: cites evidence that was not supplied {sorted(set(refs) - allowed_refs)}")
                continue
            if st != "UNCERTAIN" and not refs:
                record.rejected.append(f"{eid}: {st} without evidence references")
                continue
            ev = ElementEvaluation(
                element_id=eid,
                state=RuleElementState(st),
                source=ElementSource.API,
                evidence_refs=[f"answer:{r}" for r in refs],
                rationale=(item.get("rationale") or "").strip() or None,
                provenance=self.provenance,
            )
            record.applied.append(ev.model_dump(mode="json"))
            out.append(ev)
        for missing in sorted(asked - seen):
            record.rejected.append(f"{missing}: not returned")
        return out
