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
