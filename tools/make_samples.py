"""Write ready-made assessments to samples/*.json, to load in the app instead of typing them.

    python tools/make_samples.py            # write samples/
    python tools/make_samples.py --check    # compare with samples/ on disk, write nothing

Every sample is the test baseline (tests/fixtures/baseline.yaml) plus a patch: either a
07_TEST_FIXTURES case, by id, or one of the per-role assessments below (the same answers
tests/test_ui.py enters through the widgets). Each one is run through the engine before it
is written, and must reach the outcome listed here; tests/test_samples.py checks the same.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]

from engine_support import build_state, load_yaml, run  # noqa: E402

FIXTURE_FILES = ["outcome.yaml", "hard_stops.yaml", "calibration.yaml", "proportionality.yaml", "process.yaml"]

PROVIDER: dict[str, Any] = {
    "answers": {
        "FOLLOW": "YES", "C05": "PROVIDER",
        "P01": "YES", "P02": "NO", "P03": "YES", "P04": "YES", "P05": "NO",
        "P06": "YES", "P07": "YES", "P08": "YES", "P09": "YES", "P10": "YES",
    },
    "human_gates": {
        "RMS-9I": {"gate": "COMPLETED", "decision": "Residual risk acceptable", "decided_by": "Provider governance board"},
    },
}

DEPLOYER: dict[str, Any] = {
    "answers": {
        "FOLLOW": "YES", "C05": "DEPLOYER", "D00": "YES",
        "D01": "Recruiters use the ranking when shortlisting",
        "D02": "12-month pilot, daily use",
        "D03": ["WORKERS_CANDIDATES"],
        "D04": ["RISK-21"],
        "D05": "Every list reviewed by a recruiter",
        "D06": "Complaint channel, HR lead owner",
        "D07": "NO", "D08": "NO",
        "D09": "DPIA-2026-04",
        "D10": "DONE",
    },
    "elements": {e: "NOT_MET" for e in ("FRIA-27A.E1", "FRIA-27D.E1", "FRIA-27E.E1", "FRIA-27F.E1", "FRIA-27I.E1")},
}

JOINT: dict[str, Any] = {
    "answers": {**PROVIDER["answers"], **DEPLOYER["answers"], "C05": "JOINT"},
    "human_gates": PROVIDER["human_gates"],
    "elements": DEPLOYER["elements"],
}

# (file name, fixture id or patch, expected outcome)
SAMPLES_SPEC: list[tuple[str, str | dict[str, Any], str]] = [
    ("role-provider-O1", PROVIDER, "O1"),
    ("role-deployer-O1", DEPLOYER, "O1"),
    ("role-joint-O1", JOINT, "O1"),
    ("outcome-O1-proceed", "FIX-O1", "O1"),
    ("outcome-O2-conditions", "FIX-O2", "O2"),
    ("outcome-O3-remediation-open", "FIX-O3", "O3"),
    ("outcome-O4-evidence-gap", "FIX-O4", "O4"),
    ("outcome-O5-hard-stop-HS07", "FIX-O5", "O5"),
    ("hard-stop-unknown-not-O5", "HS-UNK-01", "O4"),
]


def _fixture_patches() -> dict[str, dict[str, Any]]:
    return {case["id"]: case.get("patch", {}) for name in FIXTURE_FILES for case in load_yaml(name)}


def build() -> dict[str, str]:
    """File name -> JSON text, after checking each sample reaches its outcome."""
    fixtures = _fixture_patches()
    out: dict[str, str] = {}
    for name, source, expected in SAMPLES_SPEC:
        patch = fixtures[source] if isinstance(source, str) else source
        got = run(patch).outcome.value
        if got != expected:
            raise SystemExit(f"{name}: engine gives {got}, sample promises {expected}")
        state = build_state(patch).model_copy(update={"assessment_id": f"sample-{name}"})
        out[f"{name}.json"] = state.model_dump_json(indent=2) + "\n"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="compare with samples/ on disk, write nothing")
    args = parser.parse_args()
    files = build()
    if args.check:
        stale = [n for n, text in files.items() if not (SAMPLES / n).exists() or (SAMPLES / n).read_text(encoding="utf-8") != text]
        for n in stale:
            print(f"stale: samples/{n}")
        return 1 if stale else 0
    SAMPLES.mkdir(exist_ok=True)
    for n, text in files.items():
        (SAMPLES / n).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote samples/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
