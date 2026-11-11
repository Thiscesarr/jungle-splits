"""Icon in the Windows notification area, so the app can be found and closed without hotkeys."""
from __future__ import annotations

import ctypes
from pathlib import Path

import pystray
from PIL import Image

from i18n import t


class Tray:
    def __init__(self, icon_path: Path, on_action, state, ico_path: Path | None = None):
        """on_action(name) runs on the tray thread, so it should only queue work for the UI thread.
        state() returns the current {"move": bool, "sound": bool, "video": bool} for check marks."""
        self.on_action = on_action
        self.state = state
        self.icon = pystray.Icon("Jungle Splits", Image.open(icon_path), "Jungle Splits", self._menu())
        if ico_path is not None:
            self._use_small_icon(ico_path)

    def _use_small_icon(self, ico_path: Path) -> None:
        """pystray hands Windows a 32-pixel icon, which the notification area shrinks to 16 into a blur.
        The .ico has a drawing made for each small size: load the one this screen's scaling uses."""
        try:
            user32 = ctypes.WinDLL("user32")
            user32.LoadImageW.restype = ctypes.c_void_p
            user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_uint]
            width, height = user32.GetSystemMetrics(49), user32.GetSystemMetrics(50)  # SM_CXSMICON, SM_CYSMICON
            handle = user32.LoadImageW(None, str(ico_path), 1, width, height, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if handle:
                self.icon._icon_handle = handle  # pystray keeps and later frees the handle it finds here
        except (AttributeError, OSError):
            pass  # pystray's own icon is used

    def _item(self, key: str, action: str, **kwargs) -> pystray.MenuItem:
        return pystray.MenuItem(lambda _item: t(key), lambda: self.on_action(action), **kwargs)

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _item: t("menu_update", version=self.state()["update"]),
                             lambda: self.on_action("update"), visible=lambda _item: bool(self.state()["update"])),
            self._item("menu_show", "show", visible=lambda _item: self.state()["minimized"]),
            # The default item is what a click on the icon itself runs.
            self._item("menu_settings", "tray_settings", default=True),
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

    def set_title(self, title: str) -> None:
        """The text shown when the pointer rests on the icon."""
        self.icon.title = title

    def refresh(self) -> None:
        self.icon.update_menu()

    def stop(self) -> None:
        self.icon.stop()
