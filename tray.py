"""Icon in the Windows notification area, so the app can be found and closed without hotkeys."""
from __future__ import annotations

from pathlib import Path

import pystray
from PIL import Image

from i18n import t


class Tray:
    def __init__(self, icon_path: Path, on_action, state):
        """on_action(name) runs on the tray thread, so it should only queue work for the UI thread.
        state() returns the current {"move": bool, "sound": bool, "video": bool} for check marks."""
        self.on_action = on_action
        self.state = state
        self.icon = pystray.Icon("Jungle Splits", Image.open(icon_path), "Jungle Splits", self._menu())

    def _item(self, key: str, action: str, **kwargs) -> pystray.MenuItem:
        return pystray.MenuItem(lambda _item: t(key), lambda: self.on_action(action), **kwargs)

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            self._item("menu_settings", "settings", default=True),
            self._item("menu_move", "move", checked=lambda _item: self.state()["move"]),
            self._item("menu_video", "video", enabled=lambda _item: self.state()["video"]),
            self._item("menu_new_run", "reset"),
            self._item("menu_sound", "mute", checked=lambda _item: self.state()["sound"]),
            self._item("open_logs", "logs"),
            pystray.Menu.SEPARATOR,
            self._item("menu_quit", "quit"),
        )

    def start(self) -> None:
        self.icon.run_detached()

    def refresh(self) -> None:
        self.icon.update_menu()

    def stop(self) -> None:
        self.icon.stop()
