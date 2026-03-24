import pytest
import tempfile
import os
from open_packet.config.config import AppConfig, StoreConfig, UIConfig, load_config, ConfigError


MINIMAL_YAML = """
store:
  db_path: /tmp/test.db
  export_path: /tmp/export

ui:
  console_visible: false
  console_buffer: 500
"""

YAML_WITH_CONNECTION = """
connection:
  type: kiss_tcp
  host: localhost
  port: 8001

store:
  db_path: /tmp/test.db
  export_path: /tmp/export
"""


def write_yaml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return f.name


def test_load_config_store_and_ui():
    path = write_yaml(MINIMAL_YAML)
    try:
        config = load_config(path)
        assert config.store.db_path == "/tmp/test.db"
        assert config.store.export_path == "/tmp/export"
        assert config.ui.console_visible is False
        assert config.ui.console_buffer == 500
        assert config.ui.console_log is None
    finally:
        os.unlink(path)


def test_load_config_ignores_connection_section():
    """A YAML with a legacy 'connection' key is silently accepted."""
    path = write_yaml(YAML_WITH_CONNECTION)
    try:
        config = load_config(path)
        assert config.store.db_path == "/tmp/test.db"
        assert not hasattr(config, "connection")
    finally:
        os.unlink(path)


def test_load_config_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/path/config.yaml")


def test_load_config_empty_file_uses_defaults():
    path = write_yaml("")
    try:
        config = load_config(path)
        assert "open-packet" in config.store.db_path
    finally:
        os.unlink(path)


def test_console_log_optional():
    yaml_with_log = MINIMAL_YAML + "\n  console_log: /tmp/console.log\n"
    path = write_yaml(yaml_with_log)
    try:
        config = load_config(path)
        assert config.ui.console_log == "/tmp/console.log"
    finally:
        os.unlink(path)
