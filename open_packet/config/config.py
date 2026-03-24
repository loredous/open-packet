from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml


class ConfigError(Exception):
    pass


@dataclass
class StoreConfig:
    db_path: str = "~/.local/share/open-packet/messages.db"
    export_path: str = "~/.local/share/open-packet/export"


@dataclass
class UIConfig:
    console_visible: bool = False
    console_buffer: int = 500
    console_log: Optional[str] = None


@dataclass
class AppConfig:
    store: StoreConfig = field(default_factory=StoreConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _parse_store(raw: dict) -> StoreConfig:
    return StoreConfig(
        db_path=str(raw.get("db_path", "~/.local/share/open-packet/messages.db")),
        export_path=str(raw.get("export_path", "~/.local/share/open-packet/export")),
    )


def _parse_ui(raw: dict) -> UIConfig:
    return UIConfig(
        console_visible=bool(raw.get("console_visible", False)),
        console_buffer=int(raw.get("console_buffer", 500)),
        console_log=raw.get("console_log"),
    )


def load_config(path: str) -> AppConfig:
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        raise ConfigError(f"Config file not found: {expanded}")
    with open(expanded) as f:
        raw = yaml.safe_load(f) or {}
    try:
        return AppConfig(
            store=_parse_store(raw.get("store", {})),
            ui=_parse_ui(raw.get("ui", {})),
        )
    except (TypeError, ValueError) as e:
        raise ConfigError(f"Invalid config value: {e}") from e
