"""samples/*.json: up to date with tools/make_samples.py, and loaded in the app they show their outcome."""

from pathlib import Path

import pytest

from digcon.ui import state as ui_state
from test_ui import app, no_errors, outcome
from tools import make_samples

SPEC = {f"{name}.json": expected for name, _, expected in make_samples.SAMPLES_SPEC}


def test_samples_on_disk_match_the_generator():
    built = make_samples.build()
    assert sorted(built) == sorted(p.name for p in make_samples.SAMPLES.glob("*.json"))
    for name, text in built.items():
        assert (make_samples.SAMPLES / name).read_text(encoding="utf-8") == text, f"run tools/make_samples.py ({name})"


@pytest.mark.parametrize("name", sorted(SPEC))
def test_sample_loaded_in_the_app_shows_its_outcome(name):
    at = app()
    at.session_state[ui_state.STORE] = ui_state.parse_upload(Path(make_samples.SAMPLES / name).read_bytes())
    at.run()
    no_errors(at)
    assert outcome(at) == SPEC[name]
