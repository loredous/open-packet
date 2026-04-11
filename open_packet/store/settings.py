from __future__ import annotations
from open_packet.store.database import Database


class Settings:
    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def export_path(self) -> str:
        return self._db.get_setting("export_path")

    @export_path.setter
    def export_path(self, value: str) -> None:
        self._db.set_setting("export_path", value)

    @property
    def console_visible(self) -> bool:
        return self._db.get_setting("console_visible") == "true"

    @console_visible.setter
    def console_visible(self, value: bool) -> None:
        self._db.set_setting("console_visible", "true" if value else "false")

    @property
    def console_buffer(self) -> int:
        return int(self._db.get_setting("console_buffer"))

    @console_buffer.setter
    def console_buffer(self, value: int) -> None:
        self._db.set_setting("console_buffer", str(value))

    @property
    def auto_discover(self) -> bool:
        return self._db.get_setting("auto_discover") == "true"

    @auto_discover.setter
    def auto_discover(self, value: bool) -> None:
        self._db.set_setting("auto_discover", "true" if value else "false")

    @property
    def console_log_level(self) -> str:
        return self._db.get_setting("console_log_level")

    @console_log_level.setter
    def console_log_level(self, value: str) -> None:
        self._db.set_setting("console_log_level", value)

    @property
    def scheduled_sr_enabled(self) -> bool:
        return self._db.get_setting("scheduled_sr_enabled") == "true"

    @scheduled_sr_enabled.setter
    def scheduled_sr_enabled(self, value: bool) -> None:
        self._db.set_setting("scheduled_sr_enabled", "true" if value else "false")

    @property
    def scheduled_sr_interval(self) -> int:
        return int(self._db.get_setting("scheduled_sr_interval"))

    @scheduled_sr_interval.setter
    def scheduled_sr_interval(self, value: int) -> None:
        if value < 5:
            raise ValueError(f"scheduled_sr_interval must be >= 5 minutes, got {value}")
        self._db.set_setting("scheduled_sr_interval", str(value))

    @property
    def notifications_enabled(self) -> bool:
        return self._db.get_setting("notifications_enabled") == "true"

    @notifications_enabled.setter
    def notifications_enabled(self, value: bool) -> None:
        self._db.set_setting("notifications_enabled", "true" if value else "false")
