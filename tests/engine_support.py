"""Build AssessmentState objects from the YAML fixtures (baseline + patch)."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from digcon.config import default_config
from digcon.domain.action_plan import fingerprint
from digcon import argument as ra
from digcon.domain.enums import AnswerState
from digcon.domain.models import AssessmentState
from digcon.engine import RunContext, run_engine
from tools.export_workbook import StrictLoader

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CTX = RunContext(run_id="RUN-TEST", timestamp=datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc))
_STATES = set(AnswerState.__members__)


def load_yaml(name: str) -> Any:
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=StrictLoader)


def _answer(qid: str, raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return {"question_id": qid, **raw}
    if isinstance(raw, str) and raw in _STATES:
        return {"question_id": qid, "state": raw}
    return {"question_id": qid, "value": raw}


def _gate(rid: str, raw: Any) -> dict[str, Any]:
    if raw == "COMPLETED":
        return {"rule_id": rid, "gate": "COMPLETED", "decision": "Fixture legal determination", "decided_by": "Legal reviewer"}
    return {"rule_id": rid, **raw}


AUTO = "AUTO"  # reviewed_fingerprint placeholder: sign the review off against the final state


def _sign_reviews(state: AssessmentState) -> AssessmentState:
    """Fill reviewed_fingerprint = AUTO, as the reviewer does by approving in the UI.

    A fingerprint leaves out the whole action plan and every residual review, so the
    order in which reviews are signed does not matter.
    """
    plan = {
        rid: item.model_copy(update={"reviewed_fingerprint": fingerprint(state, rid)})
        if item.reviewed_fingerprint == AUTO else item
        for rid, item in state.action_plan.items()
    }
    reviews = {
        rid: review.model_copy(update={"reviewed_fingerprint": fingerprint(state, rid)})
        if review.reviewed_fingerprint == AUTO else review
        for rid, review in state.residual_reviews.items()
    }
    state = state.model_copy(update={"action_plan": plan, "residual_reviews": reviews})
    return sign_argument(state)


def sign_argument(state: AssessmentState) -> AssessmentState:
    """RA-1: record every argument determination against the final state, as the assessor does."""
    cfg = default_config()
    arg = state.argument.model_copy(deep=True)
    for scope, steps in [("SYSTEM", arg.system), ("CROSS", arg.cross),
                         *((r, a.steps) for r, a in arg.rights.items())]:
        for sid in steps:
            steps[sid] = steps[sid].model_copy(update={"author": steps[sid].author or "Fixture assessor",
                                                       "date": steps[sid].date or "2026-10-01"})
    state = state.model_copy(update={"argument": arg})
    for scope, steps in [("SYSTEM", arg.system), ("CROSS", arg.cross),
                         *((r, a.steps) for r, a in arg.rights.items())]:
        for sid, det in steps.items():
            if det.fingerprint in ("", AUTO):
                det.fingerprint = ra.fingerprint(state, cfg, scope, sid)
    return state


def build_state(patch: dict[str, Any] | None = None) -> AssessmentState:
    base = load_yaml("baseline.yaml")
    data = copy.deepcopy(base)
    patch = patch or {}
    for qid in patch.get("remove_answers", []):
        data["answers"].pop(qid)
    data["answers"].update(patch.get("answers", {}))
    data["elements"] = {**data.get("elements", {}), **patch.get("elements", {})}
    data["risks"] = {**data.get("risks", {}), **patch.get("risks", {})}
    argument = copy.deepcopy(data.get("argument", {}))
    for part in ("system", "cross"):
        argument.setdefault(part, {}).update(patch.get("argument", {}).get(part, {}))
    rights = argument.setdefault("rights", {})
    for right, steps in patch.get("argument", {}).get("rights", {}).items():
        rights.setdefault(right, {}).update(steps)
    for steps in patch.get("argument", {}).get("drop", []):  # e.g. "CFR-21.B6" or "SYSTEM.A1"
        scope, sid = steps.split(".")
        (argument["system"] if scope == "SYSTEM" else argument["cross"] if scope == "CROSS" else rights[scope]).pop(sid, None)
    return _sign_reviews(AssessmentState.model_validate(
        {
            "assessment_id": data["assessment_id"],
            "workbook_version": data["workbook_version"],
            "answers": {q: _answer(q, v) for q, v in data["answers"].items()},
            "elements": {e: {"element_id": e, "state": s} for e, s in data["elements"].items()},
            "human_gates": {r: _gate(r, g) for r, g in patch.get("human_gates", {}).items()},
            "risks": {r: {"risk_id": r, **v} for r, v in data["risks"].items()},
            "mitigations": {m: {"mitigation_id": m, **v} for m, v in patch.get("mitigations", {}).items()},
            "sep": patch.get("sep", {}),
            "action_plan": {r: {"rule_id": r, **v} for r, v in patch.get("action_plan", {}).items()},
            "residual_reviews": patch.get("residual_reviews", {}),
            "argument": {"system": argument.get("system", {}), "cross": argument.get("cross", {}),
                         "rights": {r: {"steps": s} for r, s in rights.items()}},
        }
    ))


def run(patch: dict[str, Any] | None = None, ctx: RunContext = CTX):
    return run_engine(default_config(), build_state(patch), ctx)


def expectation_failures(r, fx: dict[str, Any]) -> list[str]:
    """Every way an engine result misses a fixture's ``expect`` block (empty list = PASS).

    Shared by the fixture tests and the API test harness (tools/api_first_test.py).
    """
    exp = fx["expect"]
    out: list[str] = []

    def check(ok: bool, msg: str) -> None:
        if not ok:
            out.append(msg)

    if "outcome" in exp:
        check(r.outcome.value == exp["outcome"], f"outcome {r.outcome.value} != {exp['outcome']}")
    if "not_outcome" in exp:
        check(r.outcome.value != exp["not_outcome"], f"outcome must not be {exp['not_outcome']}")
    for hs, st in exp.get("hs", {}).items():
        check(r.hard_stops[hs].state.value == st, f"{hs} {r.hard_stops[hs].state.value} != {st}")
    if "hs_opened" in exp:
        opened = sorted(h for h, v in r.hard_stops.items() if v.opened)
        check(opened == sorted(exp["hs_opened"]), f"opened HS {opened} != {sorted(exp['hs_opened'])}")
    for rid, status in exp.get("prop", {}).items():
        got = r.prop_statuses.get(rid)
        check(got is not None and got.value == status, f"{rid} {got.value if got else None} != {status}")
    for rid, effects in exp.get("prop_effects", {}).items():
        got = {e.value for e in r.rules[rid].effects}
        check(got >= set(effects), f"{rid} effects {sorted(got)} lack {sorted(set(effects) - got)}")
    for rid, levels in exp.get("risk", {}).items():
        for stage, level in levels.items():
            got = getattr(r.risks[rid], stage)
            check((got.value if got else None) == level, f"{rid} {stage} {got.value if got else None} != {level}")
    for mid, status in exp.get("mitigation_status", {}).items():
        got = build_state(fx["patch"]).mitigations[mid].status.value
        check(got == status, f"{mid} {got} != {status}")
    for flag, value in exp.get("flags", {}).items():
        got = {f.value: v for f, v in r.flags.items()}[flag]
        check(got is value, f"flag {flag} {got} != {value}")
    if "sep_status" in exp:
        check(r.sep_status is not None and r.sep_status.value == exp["sep_status"], f"SEP status != {exp['sep_status']}")
    for rid in exp.get("fired", []):
        check(r.rules[rid].fired, f"{rid} did not fire")
    if "reassess" in exp:
        got = sorted(k for k, v in r.risks.items() if v.to_reassess)
        check(got == exp["reassess"], f"reassess {got} != {exp['reassess']}")
    if "routing_suspended" in exp:
        check(r.routing_suspended is exp["routing_suspended"], f"routing_suspended != {exp['routing_suspended']}")
    check(r.closed, f"audit not closed: {r.audit_defects}")
    return out
