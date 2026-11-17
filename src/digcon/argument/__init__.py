"""Rights argument RA-1: reading the determinations of step 3 into positions.

Pure functions over (ConfigBundle, AssessmentState, EngineResult). The engine keeps computing the
workbook's findings for steps 1 and 2 and the stop conditions; this module reads the argument per
right and composes both into:

* the state of the assessment (complete or incomplete, with what is missing);
* a position for each right of the register, and one for the use as a whole;
* the overall position, and the O-code derived from it for exports and the audit trail.

It checks that each determination exists, is reasoned, is signed and is current. It never reads
its merits and never writes "proportionate".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date

from digcon.domain.enums import HumanGate, RuleElementState

# Positions, from the least to the most serious. The overall position is the most serious one.
NOT_ENGAGED = "NOT_ENGAGED"
CLEAR = "CLEAR"
CONDITIONS = "CONDITIONS"
INCOMPLETE = "INCOMPLETE"
STOP_EXCLUDED = "STOP_EXCLUDED"
REVISION = "REVISION"
STOP_PENDING = "STOP_PENDING"
STOP_CONFIRMED = "STOP_CONFIRMED"
RANK = {NOT_ENGAGED: 0, CLEAR: 1, CONDITIONS: 2, INCOMPLETE: 3, STOP_EXCLUDED: 3, REVISION: 4,
        STOP_PENDING: 5, STOP_CONFIRMED: 6}
LABELS = {
    NOT_ENGAGED: "Not engaged",
    CLEAR: "No unjustified interference found",
    CONDITIONS: "Justified subject to conditions",
    INCOMPLETE: "Incomplete",
    STOP_EXCLUDED: "Stop: excluded by legal review",
    REVISION: "Revision required",
    STOP_PENDING: "Stop: legal review pending",
    STOP_CONFIRMED: "Stop: confirmed",
}
#: Positions that leave the assessment incomplete.
OPEN = (INCOMPLETE, STOP_EXCLUDED, STOP_PENDING)

# Step statuses.
MISSING = "MISSING"  # no record, incomplete record, or edited since it was recorded
STALE = "STALE"  # recorded, but the facts it relied on changed since
CURRENT = "CURRENT"

RIGHT_STEPS = ("S0", "B1", "B2", "B3R", "B3E", "B4", "B5", "B6")
SYSTEM_STEPS = ("A1", "A2", "A3")
CROSS_STEPS = ("C1", "C2")

# Answers each system step relies on: a change makes the determination out of date.
_SYSTEM_ANSWERS = {
    "A1": ("Q22", "Q23", "C13", "C14", "C15", "C16"),
    "A2": ("N01", "W01", "C10"),
    "A3": ("N01", "W01", "C10", "N02", "C38", "C39"),
}
_GUARANTEE_ANSWERS = ("C46", "C47", "C48", "C50", "C51", "C52", "C53")
_NECESSITY_ANSWERS = ("C20", "C22", "Q16", "C31", "C32")


@dataclass(frozen=True)
class StepReading:
    scope: str  # "SYSTEM", "CROSS" or a right id
    step: str
    status: str  # MISSING / STALE / CURRENT
    code: str = ""
    effect: str = ""  # the option's effect, when CURRENT
    refers_to: str | None = None
    legal_review: bool = False


@dataclass(frozen=True)
class Item:
    """One thing that sets a position: a step, a workbook finding, a stop condition."""

    position: str
    scope: str
    ref: str  # step id, rule id or stop condition
    text: str


@dataclass
class RightPosition:
    right: str
    position: str
    items: list[Item] = field(default_factory=list)
    required: list[str] = field(default_factory=list)


@dataclass
class Positions:
    rights: dict[str, RightPosition]
    system: list[Item]  # A1–A3, C1–C2 and the workbook's findings for steps 1–2
    overall: str
    complete: bool
    missing: list[Item]
    ocode: str

    def label(self) -> str:
        return LABELS[self.overall]


# -- records -------------------------------------------------------------------------------


def _record(state, scope: str, step: str):
    arg = state.argument
    if scope == "SYSTEM":
        return arg.system.get(step)
    if scope == "CROSS":
        return arg.cross.get(step)
    right = arg.rights.get(scope)
    return right.steps.get(step) if right else None


def _answers(state, ids) -> dict:
    return {q: state.answers[q].model_dump(mode="json") for q in ids if q in state.answers}


def verified_mitigations(state, cfg, risk_id: str | None):
    """Linked measures verified effective: only these change the facts a determination relies on."""
    from digcon.domain.enums import MitigationStatus
    return [m for m in linked_mitigations(state, cfg, risk_id) if m.status is MitigationStatus.VERIFIED_EFFECTIVE]


def linked_mitigations(state, cfg, risk_id: str | None):
    if not risk_id:
        return []
    out = []
    for m in state.mitigations.values():
        if not m.activated:
            continue
        try:
            catalogue_risk = cfg.mitigation(m.mitigation_id).risk_id
        except KeyError:
            continue
        if catalogue_risk == risk_id or risk_id in m.linked_risk_ids:
            out.append(m)
    return sorted(out, key=lambda m: m.mitigation_id)


def _code(state, scope, step) -> str:
    rec = _record(state, scope, step)
    return rec.code if rec else ""


def _brief(state, scope, step) -> dict:
    rec = _record(state, scope, step)
    return {"code": rec.code, "reasons": rec.reasons} if rec else {}


def _facts(state, cfg, scope: str, step: str) -> dict:
    """What a determination relies on, besides its own text."""
    if scope == "SYSTEM":
        return {"answers": _answers(state, _SYSTEM_ANSWERS[step])}
    if scope == "CROSS":
        engaged = sorted(r for r in state.argument.rights if _code(state, r, "S0") == "ENGAGED")
        return {"engaged": engaged, "balances": {r: _code(state, r, "B6") for r in engaged}}
    card = cfg.argument.right(scope)
    risk = state.risks.get(card.risk_id) if card.risk_id else None
    risk_dump = risk.model_dump(mode="json") if risk else None
    if step in ("S0", "B1"):
        return {"risk_included": risk is not None}
    if step == "B2":
        return {"risk": risk_dump, "groups": _answers(state, ("C40", "D03")), "sep": state.sep.model_dump(mode="json")}
    if step in ("B3R", "B3E"):
        return {"interference": _brief(state, scope, "B2")}
    if step == "B4":
        alt = state.alternatives_review.model_dump(mode="json") if state.alternatives_review else None
        return {"risk": risk_dump, "alternatives": alt, "answers": _answers(state, _NECESSITY_ANSWERS)}
    residual = state.residual_reviews.get(card.risk_id) if card.risk_id else None
    mitigations = [m.model_dump(mode="json", include={"mitigation_id", "status", "evidence_refs", "verification_ref"})
                   for m in verified_mitigations(state, cfg, card.risk_id)]
    if step == "B5":
        return {"mitigations": mitigations, "answers": _answers(state, _GUARANTEE_ANSWERS),
                "residual": residual.model_dump(mode="json") if residual else None}
    # B6 weighs everything before it.
    return {"risk": risk_dump, "mitigations": mitigations,
            "residual": residual.model_dump(mode="json") if residual else None,
            "aim": _brief(state, "SYSTEM", "A2"), "suitability": _brief(state, "SYSTEM", "A3"),
            "necessity": _brief(state, scope, "B4"), "guarantees": _brief(state, scope, "B5")}


def fingerprint(state, cfg, scope: str, step: str) -> str:
    rec = _record(state, scope, step)
    own = rec.model_dump(mode="json", exclude={"fingerprint", "history"}) if rec else None
    payload = {"record": own, "facts": _facts(state, cfg, scope, step)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def missing_fields(cfg, step: str, rec) -> list[str]:
    """What the record still needs before it can be recorded."""
    if rec is None or not rec.code:
        return ["determination"]
    spec = cfg.argument.step(step)
    out = []
    if spec.option(rec.code) is None:
        out.append("determination")
    if not rec.reasons.strip():
        out.append("reasons")
    if step == "A3" and rec.code == "SERVES" and not rec.evidence:
        out.append("evidence")
    if step == "B5" and rec.code == "ADEQUATE_WITH_CONDITIONS" and not rec.extra.get("conditions", "").strip():
        out.append("conditions")
    if rec.dissent.strip() and not rec.dissent_by.strip():
        out.append("author of the dissent")
    if not rec.author.strip():
        out.append("author")
    try:
        date.fromisoformat(rec.date)
    except ValueError:
        out.append("date (YYYY-MM-DD)")
    return out


def read_step(state, cfg, scope: str, step: str) -> StepReading:
    rec = _record(state, scope, step)
    if rec is None or missing_fields(cfg, step, rec) or not rec.fingerprint:
        return StepReading(scope, step, MISSING)
    if rec.fingerprint != fingerprint(state, cfg, scope, step):
        return StepReading(scope, step, STALE, rec.code)
    opt = cfg.argument.step(step).option(rec.code)
    return StepReading(scope, step, CURRENT, rec.code, opt.effect, opt.refers_to, opt.legal_review)


def current_code(state, cfg, scope: str, step: str) -> str | None:
    r = read_step(state, cfg, scope, step)
    return r.code if r.status == CURRENT else None


def referred_stops(state, cfg) -> set[str]:
    """Stop conditions a current determination of the argument refers to the legal review."""
    out = set()
    scopes = [("SYSTEM", SYSTEM_STEPS)] + [(r, ("B3R", "B3E")) for r in engaged(state, cfg)]
    for scope, steps in scopes:
        for s in steps:
            r = read_step(state, cfg, scope, s)
            if r.status == CURRENT and r.effect == "STOP":
                out.add(r.refers_to)
    return out


def engaged(state, cfg) -> list[str]:
    return [c.id for c in cfg.argument.rights if current_code(state, cfg, c.id, "S0") == "ENGAGED"]


# -- per right -----------------------------------------------------------------------------


def _title(cfg, step):
    return cfg.argument.step(step).title


def _stop_state(result, hs: str) -> str:
    hs_result = result.hard_stops.get(hs)
    if hs_result is None:
        return STOP_PENDING
    if hs_result.state is RuleElementState.MET:
        return STOP_CONFIRMED
    if hs_result.state is RuleElementState.NOT_MET and hs_result.gate is HumanGate.COMPLETED:
        return STOP_EXCLUDED
    return STOP_PENDING


def _gap_item(cfg, scope, reading) -> Item:
    why = {MISSING: "not yet determined and recorded", STALE: "out of date: the facts changed since it was recorded"}
    if reading.status == CURRENT:  # an "undetermined" determination
        text = f"{_title(cfg, reading.step)}: cannot yet be determined"
    else:
        text = f"{_title(cfg, reading.step)}: {why[reading.status]}"
    return Item(INCOMPLETE, scope, reading.step, text)


def _effect_item(cfg, result, scope, reading) -> Item | None:
    title = _title(cfg, reading.step)
    if reading.effect == "UNDETERMINED":
        return _gap_item(cfg, scope, reading)
    if reading.effect == "REVISION":
        extra = "; legal review required" if reading.legal_review else ""
        return Item(REVISION, scope, reading.step, f"{title}: {reading.code.replace('_', ' ').lower()}{extra}")
    if reading.effect == "CONDITIONS":
        return Item(CONDITIONS, scope, reading.step, f"{title}: adequate while stated measures stay in place")
    if reading.effect == "STOP":
        stop = _stop_state(result, reading.refers_to)
        if stop == STOP_EXCLUDED:
            text = f"{title}: {reading.refers_to} excluded by legal review; revise this step and continue the argument"
        else:
            text = f"{title}: {reading.refers_to} — {LABELS[stop].split(': ', 1)[1]}"
        return Item(stop, scope, reading.step, text)
    return None


def right_position(state, cfg, result, right: str) -> RightPosition:
    readings = {s: read_step(state, cfg, right, s) for s in RIGHT_STEPS}
    code = {s: (r.code if r.status == CURRENT else None) for s, r in readings.items()}
    required = ["S0"]
    if code["S0"] == "NOT_ENGAGED":
        return RightPosition(right, NOT_ENGAGED, [], required)
    required += ["B1", "B2"]
    if code["B2"] == "NO_INTERFERENCE":
        return RightPosition(right, NOT_ENGAGED, [], required)
    required.append("B3R")
    if code["B3R"] != "NO_LIMITATION":
        required.append("B3E")
    threshold = [s for s in ("B3R", "B3E") if s in required and readings[s].effect == "STOP"]
    stop_states = {s: _stop_state(result, readings[s].refers_to) for s in threshold}
    if not threshold or any(v == STOP_EXCLUDED for v in stop_states.values()):
        required += ["B4", "B5", "B6"]  # no limit at issue, or the legal review sent the right back
    items = []
    for s in required:
        r = readings[s]
        if r.status != CURRENT:
            items.append(_gap_item(cfg, right, r))
            continue
        item = _effect_item(cfg, result, right, r)
        if item:
            items.append(item)
    position = max((i.position for i in items), key=RANK.get, default=CLEAR)
    if position == NOT_ENGAGED:
        position = CLEAR
    return RightPosition(right, position, items, required)


# -- the use as a whole, workbook findings ---------------------------------------------------


def _workbook_items(cfg, result) -> list[Item]:
    """Steps 1–2 and the stop conditions, as the engine reads them. PROP-* are absorbed by the argument."""
    from digcon.domain.action_plan import title

    def keep(rid: str) -> bool:
        family = cfg.rule(rid).family
        return family not in ("PROP", "HS", "OUT")

    items = []
    for f in result.evidence_gaps:
        if keep(f.rule_id):
            items.append(Item(INCOMPLETE, "WORKBOOK", f.rule_id, title(f.rule_id)))
    for f in result.open_remediations:
        if keep(f.rule_id):
            items.append(Item(REVISION, "WORKBOOK", f.rule_id, title(f.rule_id)))
    for f in result.open_conditions:
        items.append(Item(CONDITIONS, "WORKBOOK", f.ids[0] if f.ids else f.rule_id, "Condition attached to a continuous measure"))
    for hs, v in result.hard_stops.items():
        if hs == "HS10":
            continue  # read per right, from the threshold step
        if v.state is RuleElementState.MET:
            items.append(Item(STOP_CONFIRMED, "WORKBOOK", hs, title(hs)))
        elif v.opened and v.state is RuleElementState.UNCERTAIN:
            items.append(Item(STOP_PENDING, "WORKBOOK", hs, title(hs)))
    return items


def system_items(state, cfg, result) -> list[Item]:
    items = []
    for s in SYSTEM_STEPS:
        r = read_step(state, cfg, "SYSTEM", s)
        if r.status != CURRENT:
            items.append(_gap_item(cfg, "SYSTEM", r))
        else:
            item = _effect_item(cfg, result, "SYSTEM", r)
            if item:
                items.append(item)
    n = len(engaged(state, cfg))
    for s, needed in (("C1", n >= 2), ("C2", n >= 1)):
        if not needed:
            continue
        r = read_step(state, cfg, "CROSS", s)
        if r.status != CURRENT:
            items.append(_gap_item(cfg, "CROSS", r))
        else:
            item = _effect_item(cfg, result, "CROSS", r)
            if item:
                items.append(item)
    return items + _workbook_items(cfg, result)


def ocode(overall: str, complete: bool) -> str:
    if overall == STOP_CONFIRMED:
        return "O5"
    if not complete:
        return "O4"
    return {REVISION: "O3", CONDITIONS: "O2"}.get(overall, "O1")


def read(state, cfg, result) -> Positions:
    if cfg.argument is None:
        raise RuntimeError("config/argument.yaml is missing")
    rights = {c.id: right_position(state, cfg, result, c.id) for c in cfg.argument.rights}
    system = system_items(state, cfg, result)
    every = system + [i for p in rights.values() for i in p.items]
    missing = [i for i in every if i.position in OPEN]
    complete = not missing
    overall = max([i.position for i in every] + [p.position for p in rights.values()], key=RANK.get, default=CLEAR)
    if overall == NOT_ENGAGED:
        overall = CLEAR
    return Positions(rights, system, overall, complete, missing, ocode(overall, complete))


def governance_departs(state, positions: Positions) -> bool | None:
    """Whether the recorded governance decision departs from the overall position (None: not recorded)."""
    follows = state.governance.follows_position
    if follows is None:
        return None
    return follows == "DEPARTS"
