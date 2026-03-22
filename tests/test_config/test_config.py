import pytest
import tempfile
import os
from open_packet.config.config import AppConfig, load_config, ConfigError

VALID_YAML = """
connection:
  type: kiss_tcp
  host: localhost
  port: 8001

store:
  db_path: /tmp/test.db
  export_path: /tmp/export

ui:
  console_visible: false
  console_buffer: 500
"""

SERIAL_YAML = """
connection:
  type: kiss_serial
  device: /dev/ttyUSB0
  baud: 9600

store:
  db_path: /tmp/test.db
  export_path: /tmp/export

ui:
  console_visible: false
  console_buffer: 500
"""

def write_yaml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return f.name


def test_load_valid_tcp_config():
    path = write_yaml(VALID_YAML)
    try:
        config = load_config(path)
        assert config.connection.type == "kiss_tcp"
        assert config.connection.host == "localhost"
        assert config.connection.port == 8001
        assert config.store.db_path == "/tmp/test.db"
        assert config.ui.console_buffer == 500
        assert config.ui.console_visible is False
        assert config.ui.console_log is None
    finally:
        os.unlink(path)


def test_load_valid_serial_config():
    path = write_yaml(SERIAL_YAML)
    try:
        config = load_config(path)
        assert config.connection.type == "kiss_serial"
        assert config.connection.device == "/dev/ttyUSB0"
        assert config.connection.baud == 9600
    finally:
        os.unlink(path)


def test_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/path/config.yaml")


def test_invalid_connection_type_raises():
    bad_yaml = VALID_YAML.replace("kiss_tcp", "invalid_type")
    path = write_yaml(bad_yaml)
    try:
        with pytest.raises(ConfigError):
            load_config(path)
    finally:
        os.unlink(path)


def test_console_log_optional():
    yaml_with_log = VALID_YAML + "\n  console_log: /tmp/console.log\n"
    path = write_yaml(yaml_with_log)
    try:
        config = load_config(path)
        assert config.ui.console_log == "/tmp/console.log"
    finally:
        os.unlink(path)
