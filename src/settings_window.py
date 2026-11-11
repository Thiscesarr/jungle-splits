"""Settings window: a sidebar of pages (general, overlay, hotkeys, sounds, records, about), each a few
cards of settings, drawn with the app's own widgets (ui.py)."""
from __future__ import annotations

import tkinter as tk
import webbrowser

import display
from hotkeys import MODIFIER_VKS, combo_from_vk, has_modifier, pretty_combo
from i18n import LANGUAGES, language, set_language, t
from popup import Popup
from sound import THEMES
from tracker import fmt_clock, parse_clock
from ui import (BG, CARD, FONT, FONT_BUTTON, FONT_KEYS, FONT_LABEL, FONT_SMALL, FONT_TINY, FONT_TITLE, ICONS, MUTED,
                SIDEBAR, TEXT, WARN, Button, Card, Field, NavItem, Segmented, Slider, Switch, ThinScrollbar, label,
                fit_cards, px, separator, stripe, style_window)
from version import GITHUB_URL, SHEET_VIEW_URL, __version__

ACTIONS = ["split", "undo", "reset", "next_route", "smites", "move", "settings", "mute", "quit"]
PAGES = ["general", "overlay", "hotkeys", "sounds", "records", "about"]
VK_ESCAPE = 0x1B
HINT_WRAP = 250  # logical pixels


def parse_target(text: str) -> float | None:
    """'2:50' -> 170.0; raises ValueError for anything that isn't m:ss."""
    text = text.strip()
    if not text:
        return None
    if ":" not in text:
        raise ValueError(text)
    seconds = parse_clock(text)
    if not 30 <= seconds <= 900:
        raise ValueError(text)
    return seconds


def record_line(record) -> str:
    """One line of the records list: champion, route, smites, PB and attempts."""
    return t("records_line", champion=record.champion, route="-".join(camp[:3] for camp in record.camps),
             smites=" · 2 smites" if record.smites == 2 else "", pb=fmt_clock(record.pb) if record.pb else "-",
             attempts=record.attempts)


class SettingsWindow(tk.Toplevel):
    def __init__(self, master, values: dict, on_save, on_close, on_preview, on_open_sounds, on_opacity,
                 on_open_logs, on_update=None, on_records=None, on_delete_records=None, on_show=None,
                 icon_image=None, on_scale=None):
        """values: language, champion, target (seconds or None), smites, scale, opacity, show, binds,
        default_binds, sound_theme, sound_volume. on_save receives the same keys with the new values.
        on_opacity(value), on_scale(value) and on_show(parts) preview an opacity, a size or the overlay's parts while they change
        (Cancel puts the saved ones back). on_records() lists the saved records.Record and
        on_delete_records(paths) deletes some at once (not on Save), returning how many it deleted."""
        super().__init__(master)
        self.values = dict(values)
        self.on_save, self.on_close = on_save, on_close
        self.on_preview, self.on_open_sounds, self.on_opacity = on_preview, on_open_sounds, on_opacity
        self.on_open_logs = on_open_logs
        self.on_update = on_update
        self.on_records, self.on_delete_records = on_records, on_delete_records
        self.on_show, self.on_scale = on_show, on_scale
        self.icon_image = icon_image
        self.binds = {a: values["binds"].get(a, "") for a in ACTIONS}
        self.capturing: str | None = None
        self.tab = "general"
        self.original_language = language()
        self.configure(bg=BG)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<KeyPress>", self._key)
        self.language = tk.StringVar(self, value=values["language"])
        self.target = tk.StringVar(self, value=fmt_clock(values["target"])[:-2] if values["target"] else "")
        self.smites = tk.IntVar(self, value=values["smites"])
        self.scale = tk.IntVar(self, value=round(values["scale"] * 100))
        self.opacity = tk.IntVar(self, value=round(values["opacity"] * 100))
        self.original_show = display.normalize(values.get("show"))
        self.show = {part: tk.BooleanVar(self, value=on) for part, on in self.original_show.items()}
        self.preset = tk.StringVar(self, value=display.preset_of(self.original_show))
        self.theme = tk.StringVar(self, value=values["sound_theme"])
        self.volume = tk.IntVar(self, value=round(values["sound_volume"] * 100))
        self._build()
        # In the middle of the screen (Windows would otherwise put it wherever its next free spot is).
        fit_cards(self)
        x = (self.winfo_screenwidth() - self.winfo_reqwidth()) // 2
        y = (self.winfo_screenheight() - self.winfo_reqheight()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        style_window(self)
        self.after(50, self.focus_force)

    # --- layout ------------------------------------------------------------------------------

    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.title(t("settings_title"))
        self.hotkey_buttons: dict[str, Button] = {}

        side = tk.Frame(self, bg=SIDEBAR, padx=px(self, 12), pady=px(self, 18))
        side.pack(side="left", fill="y")
        brand = tk.Frame(side, bg=SIDEBAR, padx=px(self, 6))
        brand.pack(fill="x", pady=(0, px(self, 18)))
        if self.icon_image is not None:
            tk.Label(brand, image=self.icon_image, bg=SIDEBAR).pack(side="left", padx=(0, px(self, 10)))
        names = tk.Frame(brand, bg=SIDEBAR)
        names.pack(side="left")
        label(names, "Jungle Splits", ("Segoe UI Semibold", 12)).pack(anchor="w")
        stripe(names, 20, 3).pack(anchor="w", pady=(px(self, 4), 0))
        self.nav: dict[str, NavItem] = {}
        for page in PAGES:
            item = NavItem(side, ICONS[page], t(f"tab_{page}"), lambda p=page: self._show_tab(p), page == self.tab)
            item.pack(anchor="w", pady=(0, px(self, 2)))
            self.nav[page] = item
        label(side, t("version", version=__version__), FONT_TINY, MUTED).pack(side="bottom", anchor="w",
                                                                            padx=px(self, 8))

        main = tk.Frame(self, bg=BG, padx=px(self, 26), pady=px(self, 20))
        main.pack(side="left", fill="both", expand=True)
        stack = tk.Frame(main, bg=BG)
        stack.pack(fill="both", expand=True)
        stack.grid_columnconfigure(0, weight=1)
        stack.grid_rowconfigure(0, weight=1)
        # Every page sits in the same cell, so the window is as big as the biggest one and doesn't jump.
        self.pages: dict[str, tk.Frame] = {}
        for page in PAGES:
            frame = tk.Frame(stack, bg=BG)
            frame.grid(row=0, column=0, sticky="nsew")
            label(frame, t(f"tab_{page}"), FONT_TITLE).pack(anchor="w", pady=(0, px(self, 12)))
            getattr(self, f"_page_{page}")(frame)
            self.pages[page] = frame

        bar = tk.Frame(main, bg=BG)
        bar.pack(fill="x", pady=(px(self, 14), 0))
        Button(bar, t("save"), self._save, "primary", padx=22).pack(side="right")
        Button(bar, t("cancel"), self._cancel).pack(side="right", padx=(0, px(self, 8)))
        self.status = label(bar, "", FONT, WARN, wrap=330)
        self.status.pack(side="left", fill="x")
        self._show_tab(self.tab)

    def _show_tab(self, tab: str) -> None:
        self.tab = tab
        self.capturing = None
        self._refresh_binds()
        if self.status.winfo_exists():
            self.status.configure(text="")
        for page, item in self.nav.items():
            if item.selected != (page == tab):
                item.selected = page == tab
                item._draw()
        self.pages[tab].tkraise()

    def _card(self, parent, **pack) -> Card:
        card = Card(parent)
        card.body.grid_columnconfigure(0, weight=1)
        card.pack(fill="x", **({"pady": (0, px(self, 12))} | pack))
        return card

    def _row(self, card: Card, text: str, make_control, hint: str = "", gap: int = 10) -> None:
        """One setting: its name (and a hint under it) on the left, its control on the right."""
        body = card.body
        row = body.grid_size()[1]
        if row:
            separator(body).grid(row=row, column=0, columnspan=2, sticky="we", pady=px(self, gap))
            row += 1
        left = tk.Frame(body, bg=CARD)
        left.grid(row=row, column=0, sticky="w")
        if text:
            label(left, text, FONT_LABEL).pack(anchor="w")
        if hint:
            label(left, hint, FONT_SMALL, MUTED, wrap=HINT_WRAP).pack(anchor="w", pady=(px(self, 2) if text else 0, 0))
        make_control(body).grid(row=row, column=1, sticky="e", padx=(px(self, 18), 0))

    # --- pages -------------------------------------------------------------------------------

    def _page_general(self, page) -> None:
        champion = self.values["champion"]

        def change_language():
            set_language(self.language.get())
            self._build()

        card = self._card(page)
        self._row(card, t("language"),
                  lambda p: Segmented(p, self.language, list(LANGUAGES.items()), change_language))
        self._row(card, t("target_for", champion=champion), lambda p: Field(p, self.target, 90), t("target_hint"))
        self._row(card, t("smites_for", champion=champion),
                  lambda p: Segmented(p, self.smites, [(1, "1 smite"), (2, "2 smites")]), t("smites_hint"))

    def _page_overlay(self, page) -> None:
        look = self._card(page)
        self._row(look, t("overlay_size"),
                  lambda p: Slider(p, self.scale, 70, 160, 10, length=170,
                                   command=lambda v: self.on_scale and self.on_scale(v / 100)),
                  t("size_hint"))
        self._row(look, t("overlay_opacity"),
                  lambda p: Slider(p, self.opacity, 30, 100, 5, length=170,
                                   command=lambda v: self.on_opacity(v / 100)),
                  t("opacity_hint"))

        card = self._card(page)
        body = card.body
        head = tk.Frame(body, bg=CARD)
        head.grid(row=0, column=0, columnspan=2, sticky="we")
        label(head, t("display_title"), FONT_LABEL).pack(anchor="w")
        label(head, t("display_hint"), FONT_SMALL, MUTED, wrap=480).pack(anchor="w", pady=(px(self, 2), 0))
        presets = tk.Frame(body, bg=CARD)
        presets.grid(row=1, column=0, columnspan=2, sticky="w", pady=(px(self, 10), px(self, 4)))
        Segmented(presets, self.preset, [(name, t(f"preset_{name}")) for name in display.PRESET_ORDER],
                  self._apply_preset, padx=12).pack(side="left")
        custom = label(presets, "", FONT_SMALL, MUTED)
        custom.pack(side="left", padx=(px(self, 10), 0))

        def show_custom(*_args):
            if custom.winfo_exists():
                custom.configure(text=t("preset_custom") if self.preset.get() == display.CUSTOM else "")

        trace = self.preset.trace_add("write", show_custom)
        custom.bind("<Destroy>", lambda _e: self.preset.trace_remove("write", trace))
        show_custom()
        separator(body).grid(row=2, column=0, columnspan=2, sticky="we", pady=px(self, 8))
        for i, part in enumerate(display.PARTS):
            cell = tk.Frame(body, bg=CARD)
            cell.grid(row=3 + i // 2, column=i % 2, sticky="nw", pady=px(self, 5),
                      padx=(0, px(self, 14)) if i % 2 == 0 else 0)
            Switch(cell, self.show[part], self._parts_changed).pack(side="left", anchor="n", pady=(px(self, 2), 0))
            names = tk.Frame(cell, bg=CARD)
            names.pack(side="left", padx=(px(self, 10), 0))
            label(names, t(f"part_{part}"), FONT).pack(anchor="w")
            label(names, t(f"part_{part}_hint"), FONT_TINY, MUTED, wrap=175).pack(anchor="w")
        body.grid_columnconfigure(1, weight=1)

    def shown_parts(self) -> dict[str, bool]:
        return {part: bool(var.get()) for part, var in self.show.items()}

    def _apply_preset(self) -> None:
        name = self.preset.get()
        if name in display.PRESETS:
            for part, on in display.PRESETS[name].items():
                self.show[part].set(on)
        self._parts_changed()

    def _parts_changed(self) -> None:
        parts = self.shown_parts()
        self.preset.set(display.preset_of(parts))
        if self.on_show:
            self.on_show(parts)

    def _page_hotkeys(self, page) -> None:
        label(page, t("hotkeys_hint"), FONT, MUTED).pack(anchor="w", pady=(0, px(self, 10)))
        card = self._card(page)
        for action in ACTIONS:
            def make(p, a=action):
                button = Button(p, "", lambda: self._start_capture(a), font=FONT_KEYS, width=200, pady=5)
                self.hotkey_buttons[a] = button
                return button
            self._row(card, t(f"act_{action}"), make, gap=5)
        Button(page, t("restore"), self._restore_binds, "ghost", icon=ICONS["refresh"]).pack(anchor="e")
        self._refresh_binds()

    def _page_sounds(self, page) -> None:
        themes = [(key, t(f"theme_{key}")) for key in THEMES]
        card = self._card(page)
        self._row(card, t("sound_style"), lambda p: Segmented(p, self.theme, themes))
        self._row(card, t("sound_volume"), lambda p: Slider(p, self.volume, 0, 100, 1, length=170))
        buttons = tk.Frame(page, bg=BG)
        buttons.pack(anchor="w")
        Button(buttons, t("sound_test"), lambda: self.on_preview(self.theme.get(), self.volume.get() / 100),
               "primary").pack(side="left", padx=(0, px(self, 8)))
        Button(buttons, t("open_sounds_folder"), self.on_open_sounds, icon=ICONS["folder"]).pack(side="left")
        label(page, t("sound_custom"), FONT_SMALL, MUTED, wrap=480).pack(anchor="w", pady=(px(self, 8), 0))

    def _page_records(self, page) -> None:
        label(page, t("records_hint"), FONT_SMALL, MUTED, wrap=480).pack(anchor="w", pady=(0, px(self, 10)))
        self.records = self.on_records() if self.on_records else []
        self.records_list = None
        if not self.records:
            label(self._card(page).body, t("records_empty"), FONT).grid(row=0, column=0, sticky="w")
            return
        card = self._card(page)
        box = tk.Frame(card.body, bg=CARD)
        box.grid(row=0, column=0, sticky="we")
        self.records_list = tk.Listbox(box, selectmode="multiple", height=min(10, len(self.records)), width=58,
                                       bg=CARD, fg=TEXT, selectbackground="#3a2457", selectforeground=TEXT,
                                       relief="flat", bd=0, highlightthickness=0, activestyle="none",
                                       font=FONT, exportselection=False)
        for record in self.records:
            self.records_list.insert("end", "  " + record_line(record))
        self.records_list.pack(side="left", fill="x", expand=True)
        if len(self.records) > 10:
            scroll = ThinScrollbar(box, self.records_list)
            scroll.pack(side="right", fill="y", padx=(px(self, 6), 0))
            self.records_list.configure(yscrollcommand=scroll.set)
        label(page, t("records_select_hint"), FONT_SMALL, MUTED).pack(anchor="w")
        Button(page, t("records_delete"), self._delete_records, "danger", icon=ICONS["delete"]).pack(
            anchor="w", pady=(px(self, 10), 0))

    def _delete_records(self) -> None:
        chosen = [self.records[i] for i in self.records_list.curselection()] if self.records_list else []
        if not chosen:
            self.status.configure(text=t("records_none_selected"))
            return
        routes = "\n".join(record_line(record) for record in chosen)

        def delete():
            deleted = self.on_delete_records([record.path for record in chosen])
            self._build()
            self.status.configure(text=t("records_deleted", n=deleted))

        self.confirm = Popup(self, self.icon_image, t("records_delete"), t("records_confirm", routes=routes),
                             [(t("records_delete"), delete, "danger"), (t("cancel"), None, False)],
                             lambda: setattr(self, "confirm", None))
        self.confirm.transient(self)
        self.confirm.grab_set()

    def _page_about(self, page) -> None:
        card = self._card(page)
        head = tk.Frame(card.body, bg=CARD)
        head.grid(row=0, column=0, sticky="we")
        if self.icon_image is not None:
            tk.Label(head, image=self.icon_image, bg=CARD).pack(side="left", padx=(0, px(self, 12)))
        names = tk.Frame(head, bg=CARD)
        names.pack(side="left")
        label(names, "Jungle Splits", ("Segoe UI Semibold", 14)).pack(anchor="w")
        label(names, t("version", version=__version__), FONT_SMALL, MUTED).pack(anchor="w")
        label(card.body, t("about_text"), FONT, wrap=480).grid(row=1, column=0, sticky="w", pady=(px(self, 10), 0))
        links = tk.Frame(card.body, bg=CARD)
        links.grid(row=2, column=0, sticky="w", pady=(px(self, 12), 0))
        Button(links, t("open_github"), lambda: webbrowser.open(GITHUB_URL), icon=ICONS["link"]).pack(
            side="left", padx=(0, px(self, 8)))
        Button(links, t("open_sheet"), lambda: webbrowser.open(SHEET_VIEW_URL), icon=ICONS["link"]).pack(side="left")
        if self.values.get("update_version") and self.on_update:
            Button(card.body, t("menu_update", version=self.values["update_version"]), self._update, "primary",
                   icon=ICONS["download"]).grid(row=3, column=0, sticky="w", pady=(px(self, 10), 0))

        logs = self._card(page)
        self._row(logs, t("logs_title"), lambda p: Button(p, t("open_logs"), self.on_open_logs, icon=ICONS["bug"]),
                  t("logs_hint"))
        label(page, t("disclaimer"), FONT_TINY, MUTED, wrap=480).pack(anchor="w", pady=(px(self, 2), 0))

    # --- hotkey capture ----------------------------------------------------------------------

    def _refresh_binds(self) -> None:
        for action, button in getattr(self, "hotkey_buttons", {}).items():
            if action == self.capturing:
                button.set(t("press_keys"), WARN)
            else:
                button.set(pretty_combo(self.binds[action]) or t("none"))

    def _start_capture(self, action: str) -> None:
        self.capturing = action
        self.status.configure(text="")
        self._refresh_binds()
        self.focus_force()

    def _key(self, event) -> None:
        if self.capturing is None or event.keycode in MODIFIER_VKS:
            return
        action, self.capturing = self.capturing, None
        if event.keycode == VK_ESCAPE:
            self._refresh_binds()
            return
        combo = combo_from_vk(event.keycode)
        notes = []
        for other, other_combo in self.binds.items():
            if other != action and other_combo.lower() == combo.lower():
                self.binds[other] = ""
                notes.append(t("hotkey_moved", key=pretty_combo(combo), action=t(f"act_{other}")))
        if not has_modifier(combo):
            notes.append(t("hotkey_no_modifier", key=pretty_combo(combo)))
        self.binds[action] = combo
        self.status.configure(text=" ".join(notes))
        self._refresh_binds()

    def _restore_binds(self) -> None:
        self.binds = {a: self.values["default_binds"].get(a, "") for a in ACTIONS}
        self.capturing = None
        self._refresh_binds()

    # --- closing -----------------------------------------------------------------------------

    def _save(self) -> None:
        try:
            target = parse_target(self.target.get())
        except ValueError:
            self._show_tab("general")
            self.status.configure(text=t("target_invalid"))
            return
        self.on_save({
            "language": self.language.get(),
            "target": target,
            "smites": self.smites.get(),
            "scale": self.scale.get() / 100,
            "opacity": self.opacity.get() / 100,
            "show": self.shown_parts(),
            "binds": dict(self.binds),
            "sound_theme": self.theme.get(),
            "sound_volume": self.volume.get() / 100,
        })
        self.destroy()
        self.on_close()

    def _update(self) -> None:
        self._cancel()
        self.on_update()

    def _cancel(self) -> None:
        set_language(self.original_language)
        self.on_opacity(self.values["opacity"])
        if self.on_scale:
            self.on_scale(self.values["scale"])
        if self.on_show:
            self.on_show(self.original_show)
        self.destroy()
        self.on_close()
