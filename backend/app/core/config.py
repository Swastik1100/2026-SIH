"""Application configuration loaded from YAML."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = BACKEND_ROOT / "configs" / "config.yaml"


@lru_cache
def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_config() -> dict[str, Any]:
    return load_config()


def config_path(relative: str) -> Path:
    return BACKEND_ROOT / relative
