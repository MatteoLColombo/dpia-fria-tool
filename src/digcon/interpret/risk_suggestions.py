"""API suggestions for the risk register (3.2): which catalogue risks apply, and a first initial rating.

Same contract as the rule interpreter (openai_interpreter.py), on the risk catalogue (sheet 04):
  * one call per catalogue risk, carrying only that risk's source questions and the assessment context;
  * closed output schema: relevance and the four initial dimensions are the workbook enums (or UNCERTAIN),
    evidence IDs are a closed enum of what was sent;
  * everything is validated again before it is kept; a rejected suggestion is simply not there.

A suggestion never enters the register by itself and never reaches the engine: a person copies it in
(or not) in 3.2. Residual dimensions are never suggested (they need a VERIFIED EFFECTIVE measure), no
risk outside the 11 of the catalogue can be proposed (RSEL-01), and the API never picks an outcome.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from digcon.domain.enums import Probability, Reversibility, RiskRelevance, Scale, Scope
from digcon.domain.models import ApiRiskSuggestion, AssessmentState, RiskSpec

from .openai_interpreter import CONTEXT_IDS, CallRecord, OpenAIInterpreter, _answer_text

RISK_PROMPT_VERSION = "r1"
RISK_SCHEMA_VERSION = "rs1"
UNCERTAIN = "UNCERTAIN"
DIMENSIONS: tuple[tuple[str, type], ...] = (
    ("scale", Scale), ("scope", Scope), ("reversibility", Reversibility), ("probability", Probability),
)
RELEVANCE = [r.value for r in RiskRelevance]

INSTRUCTIONS_R1 = """\
You assist DIGCON, a deterministic decision engine for fundamental-rights impact assessments of AI systems.
You do one narrow job: for one risk from the DIGCON risk catalogue, say whether the answers about the assessed
system show that this risk is relevant to the case and, if it is, propose a first rating of its initial
dimensions. A person reviews every suggestion; nothing you return counts until they accept it.

You receive:
- risk: the fundamental right concerned, the groups exposed, the harm scenarios and the safeguards to verify.
- context: what the assessed system is and does (role, object, intended purpose, scope, documentation).
- evidence: the answers the catalogue links to this risk.

relevance:
- RELEVANT: the context and evidence show that this use of the system could plausibly produce one of the harm
  scenarios, or a closely related harm to the same right for the groups described.
- NOT_RELEVANT: the evidence shows that the harm cannot arise in this use (for example the right or the group
  is not touched by what the system does).
- UNCERTAIN: the evidence needed to decide is missing, too vague to judge, or contradicts itself.

Initial dimensions, rated before any safeguard or mitigation (give them only when relevance is RELEVANT;
otherwise answer UNCERTAIN for each):
- scale: how serious the harm is for a person affected: LOW, MEDIUM, HIGH, VERY_HIGH.
- scope: how many people or how wide the harm reaches: LIMITED, MODERATE, WIDE, SYSTEMIC.
- reversibility: how far the harm can be undone: REVERSIBLE, PARTLY_REVERSIBLE, DIFFICULT_TO_REVERSE, IRREVERSIBLE.
- probability: how likely the harm is to occur without further safeguards: RARE, POSSIBLE, LIKELY, VERY_LIKELY.
Answer UNCERTAIN for a dimension the evidence does not let you rate. Safeguards that are planned, claimed or not
yet verified do not lower an initial rating. Never rate residual risk.

Rules:
- An answer that is missing, UNKNOWN, N/A or NOT OWNED is never the same as NO.
- Do not reach RELEVANT or a rating from your own assumptions about facts that are not written in the context
  or evidence.
- In evidence_refs cite only the context or evidence IDs supplied that support your suggestion. Never invent IDs.
  RELEVANT and NOT_RELEVANT must cite at least one evidence or context ID.
- Do not decide the outcome of the assessment, do not conclude whether the processing is proportionate or
  disproportionate, and do not propose risks other than the one you were given.
- rationale: two to four sentences: why the risk is or is not relevant, then a short reason for each rating,
  quoting the evidence where possible.
"""


class RiskSuggester:
    """Risk suggestions on the client, model and settings of an ``OpenAIInterpreter``. ``calls`` keeps one record per call."""

    def __init__(self, interp: OpenAIInterpreter):
        self.interp = interp
        self.cfg = interp.cfg
        self.calls: list[CallRecord] = []

    @property
    def provenance(self) -> str:
        i = self.interp
        effort = f"; effort {i.reasoning_effort}" if i.reasoning_effort else ""
        return f"openai:{i.model}{effort}; prompt {RISK_PROMPT_VERSION}; schema {RISK_SCHEMA_VERSION}"

    # -- request ------------------------------------------------------------------------

    def request_for(self, state: AssessmentState, spec: RiskSpec, visible: set[str] | None = None) -> dict[str, Any]:
        def item(qid: str) -> dict[str, str]:
            q = self.cfg.question(qid)
            return {"id": qid, "question": q.text,
                    "answer": _answer_text(self.cfg, q, state.answers.get(qid), self.interp._labels)}

        sources = list(dict.fromkeys(spec.core_questions + spec.provider_questions + spec.deployer_questions))
        inputs = [q for q in sources if visible is None or q in visible]
        return {
            "risk_id": spec.id,
            "risk": {"label": spec.label or spec.id, "right": spec.right, "groups": spec.groups,
                     "harm_scenarios": list(spec.harm_scenarios), "safeguards_to_verify": spec.safeguards_to_verify},
            "context": [item(q) for q in CONTEXT_IDS if q not in inputs and (visible is None or q in visible)],
            "evidence": [item(q) for q in inputs],
        }

    @staticmethod
    def worth_sending(request: dict[str, Any]) -> bool:
        """At least one linked answer was given: otherwise there is nothing to read."""
        return any(e["answer"] != "NOT ANSWERED" for e in request["evidence"])

    @staticmethod
    def digest(request: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _citable(request: dict[str, Any]) -> list[str]:
        return [e["id"] for e in request["context"]] + [e["id"] for e in request["evidence"]]

    @staticmethod
    def schema_for(request: dict[str, Any]) -> dict[str, Any]:
        props: dict[str, Any] = {
            "risk_id": {"type": "string", "enum": [request["risk_id"]]},
            "relevance": {"type": "string", "enum": RELEVANCE},
        }
        for dim, enum in DIMENSIONS:
            props[dim] = {"type": "string", "enum": [m.value for m in enum] + [UNCERTAIN]}
        props["evidence_refs"] = {"type": "array", "items": {"type": "string", "enum": RiskSuggester._citable(request)}}
        props["rationale"] = {"type": "string"}
        return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}

    # -- calls ---------------------------------------------------------------------------

    def suggest(self, state: AssessmentState, risk_ids: list[str], visible: set[str] | None = None) -> list[ApiRiskSuggestion]:
        """One call per risk, several at once; results keep the catalogue order. Failed calls return nothing."""
        specs = [s for s in self.cfg.risks.risks if s.id in set(risk_ids)]
        with ThreadPoolExecutor(max_workers=self.interp.max_parallel) as pool:
            results = list(pool.map(lambda s: self._suggest_one(state, s, visible), specs))
        return [r for r in results if r is not None]

    def _suggest_one(self, state: AssessmentState, spec: RiskSpec, visible: set[str] | None) -> ApiRiskSuggestion | None:
        i = self.interp
        request = self.request_for(state, spec, visible)
        record = CallRecord(rule_id=spec.id, model=i.model, reasoning_effort=i.reasoning_effort,
                            prompt_version=RISK_PROMPT_VERSION, schema_version=RISK_SCHEMA_VERSION,
                            timestamp=datetime.now(timezone.utc).isoformat(), request=request)
        self.calls.append(record)
        if not self.worth_sending(request):
            record.error = "none of the risk's linked answers is given: nothing to read"
            return None
        extra = {"reasoning": {"effort": i.reasoning_effort}} if i.reasoning_effort else {}
        try:
            response = i.client.responses.create(
                **extra,
                model=i.model,
                instructions=INSTRUCTIONS_R1,
                input=json.dumps(request, ensure_ascii=False, indent=2),
                text={"format": {"type": "json_schema", "name": "risk_suggestion",
                                 "schema": self.schema_for(request), "strict": True}},
                max_output_tokens=i.max_output_tokens,
                store=False,
            )
        except Exception as exc:  # network, auth, quota: no suggestion
            record.error = f"{type(exc).__name__}: {exc}"
            return None
        record.raw_output = getattr(response, "output_text", None)
        if getattr(response, "status", None) == "incomplete":
            details = getattr(response, "incomplete_details", None)
            record.error = f"response incomplete: {getattr(details, 'reason', details)}"
            return None
        usage = getattr(response, "usage", None)
        record.usage = usage.model_dump() if hasattr(usage, "model_dump") else None
        return self._validate(record, request)

    def _validate(self, record: CallRecord, request: dict[str, Any]) -> ApiRiskSuggestion | None:
        def reject(why: str) -> None:
            record.rejected.append(f"{request['risk_id']}: {why}")

        try:
            payload = json.loads(record.raw_output or "")
        except ValueError:
            record.error = "output is not JSON"
            return None
        if not isinstance(payload, dict) or payload.get("risk_id") != request["risk_id"]:
            record.error = f"wrong or missing risk_id: {payload.get('risk_id') if isinstance(payload, dict) else payload!r}"
            return None
        relevance = payload.get("relevance")
        if relevance not in RELEVANCE:
            reject(f"relevance {relevance!r} outside {RELEVANCE}")
            return None
        refs = payload.get("evidence_refs") or []
        if not isinstance(refs, list) or not set(refs) <= set(self._citable(request)):
            reject(f"cites evidence that was not supplied {refs!r}")
            return None
        if relevance != RiskRelevance.UNCERTAIN.value and not refs:
            reject(f"{relevance} without evidence references")
            return None
        dims: dict[str, Any] = {}
        for dim, enum in DIMENSIONS:
            value = payload.get(dim)
            if value == UNCERTAIN or relevance != RiskRelevance.RELEVANT.value:
                continue  # only a relevant risk gets ratings; UNCERTAIN leaves the dimension empty
            try:
                dims[dim] = enum(value)
            except ValueError:
                reject(f"{dim} {value!r} outside {[m.value for m in enum]}")
                return None
        suggestion = ApiRiskSuggestion(
            risk_id=request["risk_id"], relevance=RiskRelevance(relevance), **dims,
            evidence_refs=[f"answer:{r}" for r in refs],
            rationale=(payload.get("rationale") or "").strip() or None,
            provenance=f"{self.provenance}; input {self.digest(request)}",
        )
        record.applied.append(suggestion.model_dump(mode="json"))
        return suggestion
