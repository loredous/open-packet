from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml

VALID_CONNECTION_TYPES = {"kiss_tcp", "kiss_serial"}


class ConfigError(Exception):
    pass


@dataclass
class TCPConnectionConfig:
    type: str
    host: str = "localhost"
    port: int = 8001


@dataclass
class SerialConnectionConfig:
    type: str
    device: str = ""
    baud: int = 9600


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
    connection: TCPConnectionConfig | SerialConnectionConfig
    store: StoreConfig = field(default_factory=StoreConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _parse_connection(raw: dict) -> TCPConnectionConfig | SerialConnectionConfig:
    conn_type = raw.get("type", "")
    if conn_type not in VALID_CONNECTION_TYPES:
        raise ConfigError(
            f"Invalid connection type '{conn_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_CONNECTION_TYPES))}"
        )
    if conn_type == "kiss_tcp":
        return TCPConnectionConfig(
            type=conn_type,
            host=str(raw.get("host", "localhost")),
            port=int(raw.get("port", 8001)),
        )
    else:
        if "device" not in raw:
            raise ConfigError("kiss_serial connection requires 'device' field")
        return SerialConnectionConfig(
            type=conn_type,
            device=str(raw["device"]),
            baud=int(raw.get("baud", 9600)),
        )


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
    if "connection" not in raw:
        raise ConfigError("Config missing required 'connection' section")
    try:
        return AppConfig(
            connection=_parse_connection(raw["connection"]),
            store=_parse_store(raw.get("store", {})),
            ui=_parse_ui(raw.get("ui", {})),
        )
    except (TypeError, ValueError) as e:
        raise ConfigError(f"Invalid config value: {e}") from e
