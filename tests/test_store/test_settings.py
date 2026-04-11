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


def test_scheduled_sr_defaults(db):
    s = Settings(db)
    assert s.scheduled_sr_enabled is False
    assert s.scheduled_sr_interval == 30


def test_scheduled_sr_enabled_set(db):
    s = Settings(db)
    s.scheduled_sr_enabled = True
    assert s.scheduled_sr_enabled is True
    s.scheduled_sr_enabled = False
    assert s.scheduled_sr_enabled is False


def test_scheduled_sr_interval_set(db):
    s = Settings(db)
    s.scheduled_sr_interval = 15
    assert s.scheduled_sr_interval == 15


def test_scheduled_sr_interval_minimum_enforced(db):
    s = Settings(db)
    with pytest.raises(ValueError, match="5 minutes"):
        s.scheduled_sr_interval = 4


def test_scheduled_sr_persisted_across_instances(db):
    s1 = Settings(db)
    s1.scheduled_sr_enabled = True
    s1.scheduled_sr_interval = 10
    s2 = Settings(db)
    assert s2.scheduled_sr_enabled is True
    assert s2.scheduled_sr_interval == 10


def test_notifications_enabled_default(db):
    s = Settings(db)
    assert s.notifications_enabled is True


def test_notifications_enabled_set(db):
    s = Settings(db)
    s.notifications_enabled = False
    assert s.notifications_enabled is False
    s.notifications_enabled = True
    assert s.notifications_enabled is True


def test_notifications_enabled_persisted_across_instances(db):
    s1 = Settings(db)
    s1.notifications_enabled = False
    s2 = Settings(db)
    assert s2.notifications_enabled is False
