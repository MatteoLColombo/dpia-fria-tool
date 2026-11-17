"""Load config/*.yaml into a validated ConfigBundle. The only runtime reader of the spec."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from digcon.domain.models import ArgumentFile, ConfigBundle, ExtensionFile

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
_FILES = ("questions", "rules", "risks", "mitigations", "sep")


class ConfigError(Exception):
    pass


def load_config(config_dir: Path = DEFAULT_CONFIG_DIR) -> ConfigBundle:
    version = (config_dir / "VERSION").read_text(encoding="utf-8").strip()
    data: dict[str, object] = {"version": version}
    for name in _FILES:
        with open(config_dir / f"{name}.yaml", encoding="utf-8") as fh:
            data[name] = yaml.safe_load(fh)
    extension = _load_extension(config_dir, data, version)
    _load_argument(config_dir, data)
    bundle = ConfigBundle.model_validate(data)
    metas = {name: getattr(bundle, name).meta for name in _FILES}
    if {m.workbook_version for m in metas.values()} != {version}:
        raise ConfigError(f"config files disagree with VERSION {version}: {metas}")
    if len({m.workbook_sha256 for m in metas.values()}) != 1:
        raise ConfigError("config files were generated from different workbooks")
    return bundle


def _load_extension(config_dir: Path, data: dict, version: str) -> ExtensionFile | None:
    """Append the rules of config/extension.yaml (PX-1) after the rule each one names."""
    path = config_dir / "extension.yaml"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    anchors = {x["id"]: x.pop("insert_after") for x in raw["rules"]}
    ext = ExtensionFile.model_validate(raw)
    if ext.meta.base_workbook_version != version:
        raise ConfigError(f"extension {ext.meta.extension_version} is for {ext.meta.base_workbook_version}, not {version}")
    rules = data["rules"]["rules"]
    for spec in ext.rules:
        ids = [r["id"] for r in rules]
        if spec.id in ids:
            raise ConfigError(f"extension rule {spec.id} already exists in the workbook export")
        anchor = anchors[spec.id]
        if anchor not in ids:
            raise ConfigError(f"extension rule {spec.id}: anchor {anchor} not found")
        rules.insert(ids.index(anchor) + 1, spec.model_dump(mode="json", by_alias=True, exclude_unset=True))
    data["extension"] = ext.meta.model_dump(mode="json")
    return ext


# Step ids the argument code reads (src/digcon/argument). The wording lives in config/argument.yaml.
ARGUMENT_STEPS = {"S0": "RIGHT", "A1": "SYSTEM", "A2": "SYSTEM", "A3": "SYSTEM", "B1": "RIGHT", "B2": "RIGHT",
                  "B3R": "RIGHT", "B3E": "RIGHT", "B4": "RIGHT", "B5": "RIGHT", "B6": "RIGHT", "C1": "CROSS", "C2": "CROSS"}


def _load_argument(config_dir: Path, data: dict) -> None:
    """config/argument.yaml (RA-1): the steps of the rights argument and the cards per right."""
    path = config_dir / "argument.yaml"
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        arg = ArgumentFile.model_validate(yaml.safe_load(fh))
    found = {s.id: s.level for s in arg.steps}
    if found != ARGUMENT_STEPS:
        raise ConfigError(f"argument steps {found} != {ARGUMENT_STEPS}")
    risks = {r["id"] for r in data["risks"]["risks"]}
    for card in arg.rights:
        if card.risk_id and card.risk_id not in risks:
            raise ConfigError(f"right card {card.id}: risk {card.risk_id} not in the register")
    data["argument"] = arg.model_dump(mode="json", by_alias=True)


@lru_cache(maxsize=1)
def default_config() -> ConfigBundle:
    return load_config()
