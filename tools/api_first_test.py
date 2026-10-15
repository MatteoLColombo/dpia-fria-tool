"""First API test: run the interpretive fixtures through the OpenAI interpreter and the engine.

    python tools/api_first_test.py              # real calls (needs OPENAI_API_KEY and OPENAI_MODEL)
    python tools/api_first_test.py --dry-run    # no calls: a fake interpreter returns the expected states
    python tools/api_first_test.py --case API-PROP-T05

Key and model come from the environment or from .streamlit/secrets.toml (git-ignored):
    OPENAI_API_KEY = "sk-..."
    OPENAI_MODEL = "<model id>"
    OPENAI_REASONING_EFFORT = "medium"   # optional: low / medium / high ...; omit for the model default
    OPENAI_BASE_URL = "https://eu.api.openai.com/v1"   # optional: needed for EU data-residency projects

For each case in tests/fixtures/api_interpretive.yaml:
  1. oracle: the engine runs on the fixture with the EXPECTED element states; if the fixture does not
     hold, the case is INVALID (a test-authoring problem) and no call is made;
  2. the rule's MANUAL elements are emptied and sent to the interpreter (the model never sees the
     expected values);
  3. the engine runs on the interpreter's states and is compared with the fixture's expectation.

Results go to api-runs/<timestamp>/ (git-ignored): report.md (the PASS/FAIL table) and
calls.jsonl (one audit record per call: model, prompt and schema version, request, raw output, usage,
applied and rejected items). Only synthetic data is sent.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tomllib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT)]

from digcon.config import default_config  # noqa: E402
from digcon.domain.enums import ElementSource, RuleElementState  # noqa: E402
from digcon.domain.models import AssessmentState, ElementEvaluation  # noqa: E402
from digcon.engine import RunContext, run_engine  # noqa: E402
from digcon.interpret.openai_interpreter import PROMPT_VERSION, PROMPTS, OpenAIInterpreter, apply_evaluations, pending_elements  # noqa: E402
from engine_support import build_state, expectation_failures, load_yaml  # noqa: E402

FIXTURE_FILES = ["outcome.yaml", "hard_stops.yaml", "calibration.yaml", "proportionality.yaml", "process.yaml"]
RUNS_DIR = ROOT / "api-runs"  # git-ignored


def _secret(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        return tomllib.loads(path.read_text(encoding="utf-8")).get(name)
    return None


def _merge(patch: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(patch or {})
    for section, values in (extra or {}).items():
        out.setdefault(section, {}).update(values)
    return out


def _run(cfg, state: AssessmentState):
    return run_engine(cfg, state, RunContext(run_id="api-first-test", timestamp=datetime.now(timezone.utc)))


def _states(state: AssessmentState, element_ids: list[str]) -> dict[str, str]:
    return {e: (state.elements[e].state.value if e in state.elements else "—") for e in element_ids}


class _ExpectedInterpreter:
    """--dry-run stand-in: returns the expected states, so the harness itself can be checked offline."""

    def __init__(self, expected: dict[str, str]):
        self.expected = expected
        self.calls: list = []

    def evaluate(self, state, elements):
        return [
            ElementEvaluation(element_id=el.id, state=RuleElementState(self.expected[el.id]), source=ElementSource.API,
                              evidence_refs=["answer:dry-run"], provenance="dry-run")
            for el in elements if self.expected.get(el.id) in RuleElementState.__members__
        ]


def run_case(cfg, case: dict[str, Any], fixtures: dict[str, dict], make_interpreter) -> dict[str, Any]:
    fx = fixtures[case["fixture"]] if case.get("fixture") else {"id": case["id"], "patch": {}, "expect": case["expect"]}
    expect_fx = {"id": fx["id"], "patch": _merge(fx.get("patch"), case.get("evidence")), "expect": fx["expect"]}
    full = build_state(expect_fx["patch"])
    targets = [el.id for rid in case["rules"] for el in cfg.rule(rid).encoding.elements
               if el.source is ElementSource.MANUAL]
    expected = _states(full, targets)
    row: dict[str, Any] = {"case": case["id"], "fixture": fx["id"], "rules": case["rules"],
                           "authored": case.get("authored", False), "expected": expected}

    oracle = expectation_failures(_run(cfg, full), expect_fx)
    if oracle:
        row.update(verdict="INVALID", note="fixture does not hold with the expected states: " + "; ".join(oracle))
        return row

    data = full.model_dump(mode="json")
    for e in targets:
        data["elements"].pop(e, None)
    blank = AssessmentState.model_validate(data)

    interpreter = make_interpreter(expected)
    evaluations = interpreter.evaluate(blank, pending_elements(cfg, blank, case["rules"]))
    after = apply_evaluations(blank, evaluations)
    actual = _states(after, targets)
    result = _run(cfg, after)
    failures = expectation_failures(result, expect_fx)
    row.update(
        actual=actual,
        elements_match=all(actual[e] == expected[e] for e in targets),
        engine_expected=fx["expect"],
        engine_actual={"outcome": result.outcome.value,
                       "prop": {r: s.value for r, s in result.prop_statuses.items() if r in case["rules"]}},
        engine_failures=failures,
        # a call that failed says nothing about the model: never let it count as a pass
        verdict="ERROR" if any(c.error for c in getattr(interpreter, "calls", [])) else ("PASS" if not failures else "FAIL"),
        rationales={ev.element_id: ev.rationale for ev in evaluations},
        calls=[asdict(c) for c in getattr(interpreter, "calls", [])],
    )
    return row


def _usage_line(rows: list[dict[str, Any]]) -> str:
    """Token totals of the run (the bill is priced per input / output token; reasoning counts as output)."""
    calls = [c for r in rows for c in r.get("calls", [])]
    usages = [c["usage"] for c in calls if c.get("usage")]
    if not usages:
        return f"Calls: {len(calls)} · token usage not reported."
    tin = sum(u.get("input_tokens") or 0 for u in usages)
    tout = sum(u.get("output_tokens") or 0 for u in usages)
    reasoning = sum((u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0 for u in usages)
    return (f"Calls: {len(calls)} · input tokens {tin:,} · output tokens {tout:,} (of which reasoning {reasoning:,}). "
            "Multiply by the model's per-token price to get the cost of this run.")


def report(rows: list[dict[str, Any]], model: str) -> str:
    lines = [
        f"# DIGCON — first API test ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)",
        "",
        f"Model: `{model}` · cases: {len(rows)} · "
        f"PASS {sum(r['verdict'] == 'PASS' for r in rows)} · FAIL {sum(r['verdict'] == 'FAIL' for r in rows)} · "
        f"INVALID {sum(r['verdict'] == 'INVALID' for r in rows)} · "
        f"ERROR {sum(r['verdict'] == 'ERROR' for r in rows)} (a call failed: no verdict on the model)",
        "",
        _usage_line(rows),
        "",
        "PASS/FAIL judges the final engine output against the workbook fixture. Element match is shown "
        "separately: a case can pass with a different element state if the engine result is unchanged.",
        "",
        "| Case | Fixture | Rules | Expected elements | API elements | Elements match | Engine result | Verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        exp = ", ".join(f"{k.split('.', 1)[1]}={v}" for k, v in r["expected"].items())
        act = ", ".join(f"{k.split('.', 1)[1]}={v}" for k, v in r.get("actual", {}).items()) or "—"
        engine = (f"{r['engine_actual']['outcome']}; " + ", ".join(f"{k}={v}" for k, v in r["engine_actual"]["prop"].items())
                  if "engine_actual" in r else "—")
        match = {True: "yes", False: "**no**"}.get(r.get("elements_match"), "—")
        authored = " ✎" if r["authored"] else ""
        lines.append(f"| {r['case']}{authored} | {r['fixture']} | {', '.join(r['rules'])} | {exp} | {act} | {match} | {engine} | **{r['verdict']}** |")
    lines += ["", "✎ = evidence text written for this test (tests/fixtures/api_interpretive.yaml).", "", "## Details", ""]
    for r in rows:
        lines += [f"### {r['case']} — {r['verdict']}", ""]
        if r.get("note"):
            lines.append(r["note"])
        for f in r.get("engine_failures", []):
            lines.append(f"- engine: {f}")
        for eid, why in (r.get("rationales") or {}).items():
            lines.append(f"- `{eid}`: {why}")
        for c in r.get("calls", []):
            for rej in c.get("rejected", []):
                lines.append(f"- rejected: {rej}")
            if c.get("error"):
                lines.append(f"- call error: {c['error']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="no API calls: return the expected states")
    ap.add_argument("--case", action="append", help="run only these case ids")
    ap.add_argument("--prompt", choices=sorted(PROMPTS), help=f"prompt version (default {PROMPT_VERSION})")
    args = ap.parse_args()

    cfg = default_config()
    fixtures = {f["id"]: f for name in FIXTURE_FILES for f in load_yaml(name)}
    cases = [c for c in load_yaml("api_interpretive.yaml") if not args.case or c["id"] in args.case]

    if args.dry_run:
        label = "dry-run"
        make = _ExpectedInterpreter
    else:
        key, model, effort = _secret("OPENAI_API_KEY"), _secret("OPENAI_MODEL"), _secret("OPENAI_REASONING_EFFORT")
        prompt = args.prompt or PROMPT_VERSION
        if not key or not model:
            print("Set OPENAI_API_KEY and OPENAI_MODEL (environment or .streamlit/secrets.toml).", file=sys.stderr)
            return 2
        from openai import OpenAI

        base_url = _secret("OPENAI_BASE_URL")
        client = OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)

        def make(_expected):  # the model never sees the expected states
            return OpenAIInterpreter(cfg, client, model, reasoning_effort=effort, prompt_version=prompt)

        label = (f"{model} (effort {effort})" if effort else model) + f", prompt {prompt}"

    rows = [run_case(cfg, c, fixtures, make) for c in cases]
    out_dir = RUNS_DIR / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report(rows, label), encoding="utf-8")
    with (out_dir / "calls.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            for c in r.get("calls", []):
                fh.write(json.dumps({"case": r["case"], **c}, ensure_ascii=False) + "\n")
    for r in rows:
        print(f"{r['case']:<24} {r['verdict']:<8} elements match: {r.get('elements_match', '—')}")
    print(f"\nReport: {out_dir / 'report.md'}")
    return 0 if all(r["verdict"] == "PASS" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
