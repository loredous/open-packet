# tests/test_ui/test_tui.py
import pytest
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.config.config import AppConfig, TCPConnectionConfig, StoreConfig, UIConfig


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        connection=TCPConnectionConfig(type="kiss_tcp", host="localhost", port=8001),
        store=StoreConfig(
            db_path=str(tmp_path / "test.db"),
            export_path=str(tmp_path / "export"),
        ),
        ui=UIConfig(),
    )


@pytest.mark.asyncio
async def test_app_mounts(app_config):
    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        assert app.query_one("StatusBar") is not None
        assert app.query_one("FolderTree") is not None
        assert app.query_one("MessageList") is not None
        assert app.query_one("MessageBody") is not None


@pytest.mark.asyncio
async def test_console_toggle(app_config):
    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        # Console starts hidden by default
        console = app.query_one("ConsolePanel")
        assert not console.display
        # Backtick toggles console
        await pilot.press("`")
        assert console.display
        await pilot.press("`")
        assert not console.display
