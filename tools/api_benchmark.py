"""Benchmark: deterministic engine only vs deterministic engine + API, against a reference.

    python tools/api_benchmark.py                    # 3 API repetitions per case
    python tools/api_benchmark.py --repeat 1         # cheaper
    python tools/api_benchmark.py --dry-run          # no calls: checks the harness offline
    python tools/api_benchmark.py --price-in 2 --price-out 10   # USD per million tokens, for a cost line

Settings as in tools/api_first_test.py (OPENAI_API_KEY, OPENAI_MODEL, optional OPENAI_REASONING_EFFORT and
OPENAI_BASE_URL, from the environment or .streamlit/secrets.toml).

Cases: the workbook's interpretive fixtures (tests/fixtures/api_interpretive.yaml) and the benchmark cases
(tests/fixtures/api_benchmark.yaml, written for the benchmark and awaiting validation by the DIGCON team).
Each case runs in three arms over the same answers:

  deterministic  the MANUAL elements of the case's rules are left empty (nobody did the 3.3 checks);
  api            the interpreter fills them, repeated N times (models are not fully deterministic);
  reference      the expected element states (what a careful reviewer would enter).

An arm's verdict compares its engine result with the reference arm's:
  PASS     same outcome, same rule effects, same rule statuses;
  PENDING  same outcome and effects, but checks left "to be verified" for a person (no wrong decision);
  FAIL     a different outcome or different rule effects;
and, for workbook fixtures, the fixture's own expectation must hold too.

Results in api-runs/benchmark-<timestamp>/ (git-ignored): report.md and calls.jsonl.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT / "tools"), str(ROOT)]

from api_first_test import FIXTURE_FILES, RUNS_DIR, _ExpectedInterpreter, _merge, _run, _secret, _states  # noqa: E402
from digcon.config import default_config  # noqa: E402
from digcon.domain.enums import ElementSource, RuleEffect  # noqa: E402
from digcon.domain.models import AssessmentState  # noqa: E402
from digcon.interpret.openai_interpreter import PROMPT_VERSION, PROMPTS, OpenAIInterpreter, apply_evaluations, pending_elements  # noqa: E402
from engine_support import build_state, expectation_failures, load_yaml  # noqa: E402

PENDING_EFFECTS = {RuleEffect.VERIFICATION_REQUEST}


# -- cases ----------------------------------------------------------------------------------

def load_cases(cfg) -> list[dict[str, Any]]:
    fixtures = {f["id"]: f for name in FIXTURE_FILES for f in load_yaml(name)}
    cases = []
    for c in load_yaml("api_interpretive.yaml"):
        fx = fixtures[c["fixture"]] if c.get("fixture") else {"id": c["id"], "patch": {}, "expect": c["expect"]}
        cases.append({"id": c["id"], "kind": "workbook" if c.get("fixture") else "control", "rules": c["rules"],
                      "patch": _merge(fx.get("patch"), c.get("evidence")), "expect_fx": fx, "validated": True,
                      "authored": c.get("authored", False)})
    bench = load_yaml("api_benchmark.yaml")
    for c in bench["cases"]:
        targets = _targets(cfg, c["rules"])
        answers = {**copy.deepcopy(bench["bases"][c["base"]]), **copy.deepcopy(c.get("evidence") or {})}
        elements = {e: c["reference"].get(e, "NOT_MET") for e in targets}
        cases.append({"id": c["id"], "kind": "benchmark", "rules": c["rules"],
                      "patch": {"answers": answers, "elements": elements}, "expect_fx": None,
                      "validated": c.get("validated", False), "authored": True})
    return cases


def _targets(cfg, rules: list[str]) -> list[str]:
    return [el.id for rid in rules for el in cfg.rule(rid).encoding.elements if el.source is ElementSource.MANUAL]


# -- one arm --------------------------------------------------------------------------------

def signature(result, rules: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"outcome": result.outcome.value}
    for rid in rules:
        rr = result.rules[rid]
        status = result.prop_statuses.get(rid)
        out[rid] = {
            "effects": sorted(e.value for e in rr.effects if e not in PENDING_EFFECTS),
            "pending": bool(set(rr.effects) & PENDING_EFFECTS or rr.review),
            "status": status.value if status else None,
            "fired": rr.fired,
        }
    return out


def verdict(sig: dict[str, Any], ref: dict[str, Any], fx_failures: list[str]) -> str:
    if fx_failures or sig["outcome"] != ref["outcome"]:
        return "FAIL"
    rules = [k for k in sig if k != "outcome"]
    if any(sig[r]["effects"] != ref[r]["effects"] for r in rules):
        return "FAIL"
    if any(sig[r]["status"] != ref[r]["status"] or sig[r]["fired"] != ref[r]["fired"] for r in rules):
        # only acceptable if the difference comes from checks left to a person
        return "PENDING" if any(sig[r]["pending"] and not ref[r]["pending"] for r in rules) else "FAIL"
    return "PENDING" if any(sig[r]["pending"] and not ref[r]["pending"] for r in rules) else "PASS"


def arm(cfg, case, state: AssessmentState, ref_sig) -> tuple[str, dict[str, Any], list[str]]:
    result = _run(cfg, state)
    fx_fail = expectation_failures(result, case["expect_fx"]) if case["expect_fx"] else []
    sig = signature(result, case["rules"])
    return verdict(sig, ref_sig, fx_fail), sig, fx_fail


# -- the benchmark --------------------------------------------------------------------------

def prepare(cfg, case) -> dict[str, Any]:
    full = build_state(case["patch"])
    targets = _targets(cfg, case["rules"])
    reference = _states(full, targets)
    ref_result = _run(cfg, full)
    ref_sig = signature(ref_result, case["rules"])
    invalid = expectation_failures(ref_result, case["expect_fx"]) if case["expect_fx"] else []
    data = full.model_dump(mode="json")
    for e in targets:
        data["elements"].pop(e, None)
    blank = AssessmentState.model_validate(data)
    det = arm(cfg, case, blank, ref_sig)
    return {"case": case, "targets": targets, "reference": reference, "ref_sig": ref_sig, "blank": blank,
            "invalid": invalid, "deterministic": {"verdict": det[0], "sig": det[1], "fx": det[2]}}


def api_run(cfg, prep, make_interpreter) -> dict[str, Any]:
    case, blank = prep["case"], prep["blank"]
    interp = make_interpreter(prep["reference"])
    evaluations = interp.evaluate(blank, pending_elements(cfg, blank, case["rules"]))
    after = apply_evaluations(blank, evaluations)
    v, sig, fx = arm(cfg, case, after, prep["ref_sig"])
    calls = [asdict(c) for c in getattr(interp, "calls", [])]
    if any(c.get("error") for c in calls):
        v = "ERROR"
    return {"verdict": v, "sig": sig, "fx": fx, "states": _states(after, prep["targets"]),
            "rationales": {e.element_id: e.rationale for e in evaluations}, "calls": calls}


def element_stats(preps, runs) -> dict[str, Any]:
    c = Counter()
    for p in preps:
        for r in runs.get(p["case"]["id"], []):
            if r["verdict"] == "ERROR":
                continue
            for e, ref in p["reference"].items():
                got = r["states"][e]
                if got == ref:
                    c["correct"] += 1
                elif got in ("UNCERTAIN", "—"):
                    c["cautious"] += 1
                else:
                    c["wrong"] += 1
                if ref == "MET":
                    c["met_total"] += 1
                    c["met_caught"] += got == "MET"
                if ref == "NOT_MET":
                    c["clean_total"] += 1
                    c["false_alarm"] += got == "MET"
    stable = total = 0
    for p in preps:
        rs = [r for r in runs.get(p["case"]["id"], []) if r["verdict"] != "ERROR"]
        if len(rs) < 2:
            continue
        for e in p["targets"]:
            total += 1
            stable += len({r["states"][e] for r in rs}) == 1
    c["stable"], c["stable_total"] = stable, total
    return dict(c)


def report(preps, runs, label: str, repeat: int, price_in: float | None, price_out: float | None) -> str:
    def count(verdicts):
        k = Counter(verdicts)
        return " · ".join(f"{name} {k[name]}" for name in ("PASS", "PENDING", "FAIL", "ERROR") if k[name])

    det = [p["deterministic"]["verdict"] for p in preps]
    api = [r["verdict"] for p in preps for r in runs.get(p["case"]["id"], [])]
    s = element_stats(preps, runs)
    calls = [c for rs in runs.values() for r in rs for c in r["calls"]]
    usage = [c["usage"] for c in calls if c.get("usage")]
    tin = sum(u.get("input_tokens") or 0 for u in usage)
    tout = sum(u.get("output_tokens") or 0 for u in usage)
    cost = (f" · estimated cost ${tin / 1e6 * price_in + tout / 1e6 * price_out:.3f}"
            if price_in is not None and price_out is not None and usage else "")
    pct = lambda a, b: f"{a}/{b} ({100 * a / b:.0f}%)" if b else "—"  # noqa: E731

    lines = [
        f"# DIGCON — benchmark: deterministic only vs + API ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)",
        "",
        f"Model: `{label}` · cases: {len(preps)} · API repetitions per case: {repeat} · "
        f"calls: {len(calls)} · tokens in {tin:,} / out {tout:,}{cost}",
        "",
        "## Summary",
        "",
        "| | Deterministic only | Deterministic + API |",
        "|---|---|---|",
        f"| Case verdicts | {count(det)} | {count(api)} |",
        f"| Deficiencies caught (reference MET) | 0 — left to a person | {pct(s.get('met_caught', 0), s.get('met_total', 0))} |",
        f"| False alarms (reference NOT_MET, API said MET) | 0 | {pct(s.get('false_alarm', 0), s.get('clean_total', 0))} |",
        f"| Element states: correct / cautious (UNCERTAIN) / wrong | all left \"to be verified\" | "
        f"{s.get('correct', 0)} / {s.get('cautious', 0)} / {s.get('wrong', 0)} |",
        f"| Same answer on every repetition | n/a (deterministic) | {pct(s.get('stable', 0), s.get('stable_total', 0))} |",
        "",
        "PASS = same decision as the reference · PENDING = same outcome and effects, but checks left \"to be verified\" "
        "for a person · FAIL = a different decision. For the deterministic arm a FAIL means the deficiency goes "
        "unnoticed unless a person completes the check in 3.3. Benchmark cases (BM-*) are written for the benchmark: their "
        "reference states await validation by the DIGCON team.",
        "",
        "## Cases",
        "",
        "| Case | Kind | Reference (MET) | Deterministic | API verdicts | API elements (last run) | Stable |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in preps:
        cid = p["case"]["id"]
        rs = runs.get(cid, [])
        met = ", ".join(e for e, v in p["reference"].items() if v == "MET") or "none (clean)"
        kind = p["case"]["kind"] + ("" if p["case"]["validated"] else " · to validate")
        if p["invalid"]:
            lines.append(f"| {cid} | {kind} | {met} | INVALID: {'; '.join(p['invalid'])} | — | — | — |")
            continue
        verdicts = " ".join(r["verdict"] for r in rs) or "—"
        last = rs[-1]["states"] if rs else {}
        diff = ", ".join(f"{e}={v}" for e, v in last.items() if v != p["reference"][e]) or "all as reference"
        stable = all(len({r["states"][e] for r in rs}) == 1 for e in p["targets"]) if len(rs) > 1 else None
        lines.append(f"| {cid} | {kind} | {met} | {p['deterministic']['verdict']} | {verdicts} | {diff} | "
                     f"{ {True: 'yes', False: '**no**', None: '—'}[stable] } |")
    lines += ["", "## Where the API differs from the reference", ""]
    for p in preps:
        for i, r in enumerate(runs.get(p["case"]["id"], []), 1):
            off = [e for e in p["targets"] if r["states"][e] != p["reference"][e]]
            errs = [c["error"] for c in r["calls"] if c.get("error")] + [x for c in r["calls"] for x in c.get("rejected", [])]
            if not off and not errs and r["verdict"] == "PASS":
                continue
            lines += [f"**{p['case']['id']}** run {i}: {r['verdict']}", ""]
            for e in off:
                lines.append(f"- `{e}` reference {p['reference'][e]}, API {r['states'][e]}: {r['rationales'].get(e) or '—'}")
            for x in errs:
                lines.append(f"- {x}")
            for f in r["fx"]:
                lines.append(f"- fixture: {f}")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--case", action="append", help="run only these case ids")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--prompt", choices=sorted(PROMPTS), help=f"prompt version (default {PROMPT_VERSION})")
    ap.add_argument("--price-in", type=float, help="USD per million input tokens")
    ap.add_argument("--price-out", type=float, help="USD per million output tokens")
    args = ap.parse_args()

    cfg = default_config()
    cases = [c for c in load_cases(cfg) if not args.case or c["id"] in args.case]
    preps = [prepare(cfg, c) for c in cases]

    if args.dry_run:
        label, make = "dry-run", _ExpectedInterpreter
    else:
        key, model, effort = _secret("OPENAI_API_KEY"), _secret("OPENAI_MODEL"), _secret("OPENAI_REASONING_EFFORT")
        prompt = args.prompt or PROMPT_VERSION
        if not key or not model:
            print("Set OPENAI_API_KEY and OPENAI_MODEL (environment or .streamlit/secrets.toml).", file=sys.stderr)
            return 2
        from openai import OpenAI

        base_url = _secret("OPENAI_BASE_URL")
        client = OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)
        label = (f"{model} (effort {effort})" if effort else model) + f", prompt {prompt}"

        def make(_reference):  # the model never sees the reference
            return OpenAIInterpreter(cfg, client, model, reasoning_effort=effort, prompt_version=prompt)

    jobs = [(p, i) for p in preps if not p["invalid"] for i in range(args.repeat)]
    runs: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for (p, _), result in zip(jobs, pool.map(lambda j: api_run(cfg, j[0], make), jobs)):
            runs.setdefault(p["case"]["id"], []).append(result)
            print(f"{p['case']['id']:<24} {result['verdict']}", flush=True)

    out_dir = RUNS_DIR / datetime.now(timezone.utc).strftime("benchmark-%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report(preps, runs, label, args.repeat, args.price_in, args.price_out), encoding="utf-8")
    with (out_dir / "calls.jsonl").open("w", encoding="utf-8") as fh:
        for cid, rs in runs.items():
            for i, r in enumerate(rs, 1):
                for c in r["calls"]:
                    fh.write(json.dumps({"case": cid, "repeat": i, **c}, ensure_ascii=False) + "\n")
    print(f"\nReport: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
