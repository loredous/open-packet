import pytest
from open_packet.store.database import Database
from open_packet.store.settings import Settings


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


def test_settings_defaults(db):
    s = Settings(db)
    assert "open-packet" in s.export_path
    assert s.console_visible is False
    assert s.console_buffer == 500
    assert s.auto_discover is True


def test_settings_set_export_path(db):
    s = Settings(db)
    s.export_path = "/tmp/my-export"
    assert s.export_path == "/tmp/my-export"


def test_settings_set_console_visible(db):
    s = Settings(db)
    s.console_visible = True
    assert s.console_visible is True


def test_settings_set_console_buffer(db):
    s = Settings(db)
    s.console_buffer = 1000
    assert s.console_buffer == 1000


def test_settings_set_auto_discover(db):
    s = Settings(db)
    s.auto_discover = False
    assert s.auto_discover is False


def test_settings_persisted_across_instances(db):
    s1 = Settings(db)
    s1.export_path = "/tmp/persistent"
    s2 = Settings(db)
    assert s2.export_path == "/tmp/persistent"


def test_set_unknown_setting_raises(db):
    with pytest.raises(KeyError, match="Unknown setting"):
        db.set_setting("nonexistent_key", "value")
