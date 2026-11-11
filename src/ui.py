"""The app's own widgets for its windows (settings, first-run screen, pop-ups), in the overlay's look:
dark, rounded and smooth. Tk can't round a widget or smooth an edge, so every shape is a Pillow image
(drawn 4x larger and scaled down) on a Canvas; Tk blends their alpha over what's behind them. Also the
Windows bits that make a Tk window match: dark title bar, rounded corners and dark native menus."""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
import tkinter.font as tkfont
from collections import OrderedDict

from PIL import Image, ImageDraw, ImageTk

BG = "#0e1014"  # window
SIDEBAR = "#0a0c10"
CARD = "#161a21"
CARD_EDGE = "#232935"
FIELD = "#232933"
FIELD_HI = "#2e3542"
TEXT, MUTED, FAINT = "#eef0f3", "#8a93a4", "#5b6373"
ACCENT, ACCENT_HI = "#a63dff", "#b964ff"
DANGER, DANGER_HI = "#c4314b", "#d8475f"
WARN = "#ffb020"
SECTORS = ("#a63dff", "#1fc85f", "#e8333a")

FONT = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY = ("Segoe UI", 8)
FONT_LABEL = ("Segoe UI", 11)
FONT_BUTTON = ("Segoe UI Semibold", 10)
FONT_TITLE = ("Segoe UI Semibold", 17)
FONT_SECTION = ("Segoe UI Semibold", 9)
FONT_KEYS = ("Bahnschrift SemiBold", 11)
FONT_NUMBER = ("Bahnschrift SemiBold", 13)

# Glyphs of Windows' icon font (Segoe Fluent Icons on Windows 11, Segoe MDL2 Assets on 10).
ICONS = {"general": "", "overlay": "", "hotkeys": "", "sounds": "", "records": "",
         "about": "", "play": "", "folder": "", "link": "", "bug": "",
         "delete": "", "refresh": "", "download": ""}
SUPERSAMPLE = 4


def dpi(widget: tk.Misc) -> float:
    return widget.winfo_fpixels("1i") / 96


def px(widget: tk.Misc, n: float) -> int:
    """Logical pixels (96 dpi) to the screen's: the app is DPI aware, so Tk doesn't scale them itself."""
    return round(n * dpi(widget))


def icon_font(widget: tk.Misc, size: int = 12) -> tuple[str, int]:
    families = set(tkfont.families(widget))
    return ("Segoe Fluent Icons" if "Segoe Fluent Icons" in families else "Segoe MDL2 Assets", size)


def parent_bg(widget: tk.Misc) -> str:
    try:
        return widget.cget("bg")
    except tk.TclError:
        return BG


def text_size(widget: tk.Misc, text: str, font) -> tuple[int, int]:
    measured = tkfont.Font(root=widget, font=font)
    return measured.measure(text), measured.metrics("linespace")


# --- shapes ---------------------------------------------------------------------------------------

_images: OrderedDict = OrderedDict()


def _rgba(color: str) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), 255


def shape(widget: tk.Misc, width: int, height: int, radius: int, fill: str | None, outline: str | None = None,
          line: int = 1) -> ImageTk.PhotoImage:
    """A smooth rounded rectangle (a circle when radius is half the size) with a see-through outside."""
    root = widget._root()
    key = (id(root), width, height, radius, fill, outline, line)
    if key in _images:
        _images.move_to_end(key)
        return _images[key]
    k = SUPERSAMPLE
    big = Image.new("RGBA", (max(1, width) * k, max(1, height) * k), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    box = (0, 0, big.width - 1, big.height - 1)
    if outline:
        draw.rounded_rectangle(box, radius * k, fill=_rgba(outline))
        inset = line * k
        box = (inset, inset, big.width - 1 - inset, big.height - 1 - inset)
        draw.rounded_rectangle(box, max(0, radius - line) * k, fill=_rgba(fill) if fill else (0, 0, 0, 0))
    elif fill:
        draw.rounded_rectangle(box, radius * k, fill=_rgba(fill))
    image = ImageTk.PhotoImage(big.resize((max(1, width), max(1, height)), Image.Resampling.LANCZOS), master=root)
    _images[key] = image
    while len(_images) > 600:
        _images.popitem(last=False)
    return image


def logo(widget: tk.Misc, path, size: int) -> ImageTk.PhotoImage:
    """The app's icon for a window's header, scaled smoothly to size logical pixels."""
    side = px(widget, size)
    return ImageTk.PhotoImage(Image.open(path).convert("RGBA").resize((side, side), Image.Resampling.LANCZOS),
                              master=widget._root())


def fit_cards(window: tk.Misc) -> None:
    """Gives every Card its final size now. A card normally sizes itself when Tk tells it its contents
    changed, which is after the window is first laid out; a window that must know its size at once
    (to open centered) calls this first."""
    window.update_idletasks()
    todo = [window]
    while todo:
        widget = todo.pop()
        if isinstance(widget, Card):
            widget._fit()
        todo.extend(widget.winfo_children())
    window.update_idletasks()


class Shape(tk.Canvas):
    """A Canvas in its parent's color, with nothing of Tk's own focus ring or border."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=kwargs.pop("bg", parent_bg(parent)), highlightthickness=0, bd=0, takefocus=0,
                         **kwargs)


# --- buttons ----------------------------------------------------------------------------------------

KINDS = {  # background, background under the pointer, text
    "primary": (ACCENT, ACCENT_HI, "#ffffff"),
    "secondary": (FIELD, FIELD_HI, TEXT),
    "danger": (DANGER, DANGER_HI, "#ffffff"),
    "ghost": (None, FIELD, TEXT),
}


class Button(Shape):
    """A rounded button; width (logical pixels) fixes its size, otherwise it fits the text."""

    def __init__(self, parent, text: str, command, kind: str = "secondary", font=FONT_BUTTON, width: int | None = None,
                 icon: str | None = None, padx: int = 16, pady: int = 7):
        super().__init__(parent, cursor="hand2")
        self.command, self.kind, self.font, self.icon = command, kind, font, icon
        self.fixed_width, self.padx, self.pady = width, padx, pady
        self.text, self.fg = text, None
        self.hover = self.pressed = False
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        icon_w = 0
        icon_f = icon_font(self, self.font[1] + 1)
        if self.icon:
            icon_w = text_size(self, self.icon, icon_f)[0] + px(self, 8)
        text_w, line = text_size(self, self.text, self.font)
        width = px(self, self.fixed_width) if self.fixed_width else text_w + icon_w + 2 * px(self, self.padx)
        height = line + 2 * px(self, self.pady)
        self.configure(width=width, height=height)
        fill, hover, fg = KINDS[self.kind]
        background = hover if self.hover else fill
        if background:
            self.create_image(0, 0, image=shape(self, width, height, px(self, 7), background), anchor="nw")
        left = (width - text_w - icon_w) // 2
        fg = self.fg or fg
        if self.icon:
            self.create_text(left, height // 2, text=self.icon, font=icon_f, fill=fg, anchor="w")
        self.create_text(left + icon_w, height // 2, text=self.text, font=self.font, fill=fg, anchor="w")

    def _set_hover(self, hover: bool) -> None:
        self.hover = hover
        self._draw()

    def _press(self, _event) -> None:
        self.pressed = True

    def _release(self, event) -> None:
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if self.pressed and inside:
            self.invoke()
        self.pressed = False

    def invoke(self) -> None:
        if self.command:
            self.command()

    def set(self, text: str | None = None, fg: str | None = None, kind: str | None = None) -> None:
        if text is not None:
            self.text = text
        self.fg = fg
        if kind is not None:
            self.kind = kind
        if self.winfo_exists():
            self._draw()


class Segmented(Shape):
    """Choice between a few options, the chosen one lit: a rounded track with a pill on the choice."""

    def __init__(self, parent, variable: tk.Variable, options: list[tuple[object, str]], on_change=None,
                 font=FONT_BUTTON, padx: int = 14):
        super().__init__(parent, cursor="hand2")
        self.variable, self.options, self.on_change, self.font = variable, options, on_change, font
        widest = max(text_size(self, label, font)[0] for _, label in options)
        self.segment = widest + 2 * px(self, padx)
        self.pad = px(self, 3)
        self.line = text_size(self, "Ag", font)[1]
        self.hover: int | None = None
        self.configure(width=self.segment * len(options) + 2 * self.pad,
                       height=self.line + 2 * px(self, 6) + 2 * self.pad)
        self._trace = variable.trace_add("write", lambda *_a: self.winfo_exists() and self._draw())
        self.bind("<Destroy>", self._untrace)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda _e: self._move(None))
        self.bind("<ButtonRelease-1>", self._click)
        self._draw()

    def _untrace(self, event) -> None:
        if event.widget is self:
            try:
                self.variable.trace_remove("write", self._trace)
            except tk.TclError:
                pass

    def _index_at(self, x: int) -> int | None:
        i = (x - self.pad) // self.segment
        return i if 0 <= i < len(self.options) else None

    def _move(self, event) -> None:
        hover = None if event is None else self._index_at(event.x)
        if hover != self.hover:
            self.hover = hover
            self._draw()

    def _click(self, event) -> None:
        i = self._index_at(event.x)
        if i is not None and 0 <= event.y < self.winfo_height():
            self.choose(self.options[i][0])

    def choose(self, value) -> None:
        if self.variable.get() != value:
            self.variable.set(value)
            if self.on_change:
                self.on_change()

    def _draw(self) -> None:
        self.delete("all")
        width, height = int(self.cget("width")), int(self.cget("height"))
        radius = px(self, 8)
        self.create_image(0, 0, image=shape(self, width, height, radius, FIELD), anchor="nw")
        for i, (value, label) in enumerate(self.options):
            left = self.pad + i * self.segment
            chosen = self.variable.get() == value
            if chosen or i == self.hover:
                self.create_image(left, self.pad, anchor="nw", image=shape(
                    self, self.segment, height - 2 * self.pad, radius - self.pad, ACCENT if chosen else FIELD_HI))
            self.create_text(left + self.segment // 2, height // 2, text=label, font=self.font,
                             fill="#ffffff" if chosen else (TEXT if i == self.hover else MUTED))


class Switch(Shape):
    """An on/off toggle, like Windows 11's."""

    def __init__(self, parent, variable: tk.BooleanVar, on_change=None):
        super().__init__(parent, cursor="hand2")
        self.variable, self.on_change = variable, on_change
        self.w, self.h = px(self, 40), px(self, 20)
        self.configure(width=self.w, height=self.h)
        self.hover = False
        self._trace = variable.trace_add("write", lambda *_a: self.winfo_exists() and self._draw())
        self.bind("<Destroy>", lambda e: e.widget is self and self._untrace())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", lambda _e: self.toggle())
        self._draw()

    def _untrace(self) -> None:
        try:
            self.variable.trace_remove("write", self._trace)
        except tk.TclError:
            pass

    def _set_hover(self, hover: bool) -> None:
        self.hover = hover
        self._draw()

    def toggle(self) -> None:
        self.variable.set(not self.variable.get())
        if self.on_change:
            self.on_change()

    def _draw(self) -> None:
        self.delete("all")
        on = bool(self.variable.get())
        radius = self.h // 2
        if on:
            track = shape(self, self.w, self.h, radius, ACCENT_HI if self.hover else ACCENT)
        else:
            track = shape(self, self.w, self.h, radius, FIELD_HI if self.hover else FIELD, MUTED, px(self, 1))
        self.create_image(0, 0, image=track, anchor="nw")
        knob = self.h - 2 * px(self, 5 if not on else 4)
        x = self.w - self.h // 2 if on else self.h // 2
        self.create_image(x, self.h // 2, image=shape(self, knob, knob, knob // 2, "#ffffff" if on else MUTED))


class Slider(Shape):
    """A value between from_ and to in steps, dragged or clicked, with the value written at its end."""

    def __init__(self, parent, variable: tk.IntVar, from_: int, to: int, step: int = 1, length: int = 200,
                 suffix: str = "%", command=None):
        super().__init__(parent, cursor="hand2")
        self.variable, self.from_, self.to, self.step = variable, from_, to, step
        self.suffix, self.command = suffix, command
        self.knob = px(self, 18)
        self.track_x = self.knob // 2
        self.length = px(self, length)
        self.label_w = text_size(self, f"{to}{suffix}", FONT_NUMBER)[0] + px(self, 12)
        self.h = px(self, 26)
        self.configure(width=self.track_x * 2 + self.length + self.label_w, height=self.h)
        self.hover = False
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<MouseWheel>", lambda e: self.set(self.variable.get() + (self.step if e.delta > 0 else -self.step)))
        self._draw()

    def _set_hover(self, hover: bool) -> None:
        self.hover = hover
        self._draw()

    def value_at(self, x: int) -> int:
        fraction = min(1.0, max(0.0, (x - self.track_x) / self.length))
        raw = self.from_ + fraction * (self.to - self.from_)
        return self.from_ + round((raw - self.from_) / self.step) * self.step

    def _drag(self, event) -> None:
        self.set(self.value_at(event.x))

    def set(self, value: int) -> None:
        value = min(self.to, max(self.from_, int(value)))
        if value != self.variable.get():
            self.variable.set(value)
            if self.command:
                self.command(value)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        value = self.variable.get()
        fraction = (value - self.from_) / (self.to - self.from_)
        knob_x = self.track_x + round(fraction * self.length)
        mid, thick = self.h // 2, px(self, 6)
        self.create_image(self.track_x, mid, anchor="w", image=shape(self, self.length, thick, thick // 2, FIELD_HI))
        if knob_x > self.track_x:
            self.create_image(self.track_x, mid, anchor="w",
                              image=shape(self, knob_x - self.track_x + thick // 2, thick, thick // 2, ACCENT))
        ring = shape(self, self.knob, self.knob, self.knob // 2, "#ffffff", ACCENT_HI if self.hover else ACCENT,
                     px(self, 4 if self.hover else 3))
        self.create_image(knob_x, mid, image=ring)
        self.create_text(self.track_x * 2 + self.length + px(self, 12), mid, text=f"{value}{self.suffix}",
                         font=FONT_NUMBER, fill=TEXT, anchor="w")


class Field(Shape):
    """A rounded text field; the accent outline shows when it has the focus."""

    def __init__(self, parent, variable: tk.StringVar, width: int = 90, font=FONT_NUMBER):
        super().__init__(parent)
        line = text_size(self, "Ag", font)[1]
        self.w, self.h = px(self, width), line + px(self, 12)
        self.configure(width=self.w, height=self.h)
        self.entry = tk.Entry(self, textvariable=variable, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                              bd=0, highlightthickness=0, font=font, justify="center")
        self.focused = False
        self.entry.bind("<FocusIn>", lambda _e: self._focus(True))
        self.entry.bind("<FocusOut>", lambda _e: self._focus(False))
        self._draw()

    def _focus(self, focused: bool) -> None:
        self.focused = focused
        self._draw()

    def _draw(self) -> None:
        self.delete("background")
        outline = ACCENT if self.focused else CARD_EDGE
        self.create_image(0, 0, anchor="nw", tags="background",
                          image=shape(self, self.w, self.h, px(self, 7), FIELD, outline, px(self, 1)))
        if not self.find_withtag("entry"):
            inset = px(self, 8)
            self.create_window(inset, self.h // 2, window=self.entry, anchor="w", width=self.w - 2 * inset,
                               tags="entry")
        self.tag_raise("entry")


class Card(Shape):
    """A rounded panel: put its contents in .body (a Frame in the card's color), packed or gridded."""

    def __init__(self, parent, padx: int = 18, pady: int = 14):
        super().__init__(parent)
        self.padx, self.pady = px(self, padx), px(self, pady)
        self.body = tk.Frame(self, bg=CARD)
        self.create_window(self.padx, self.pady, window=self.body, anchor="nw", tags="body")
        self.body.bind("<Configure>", self._fit)
        self.bind("<Configure>", self._redraw)

    def _fit(self, _event=None) -> None:
        self.configure(width=self.body.winfo_reqwidth() + 2 * self.padx,
                       height=self.body.winfo_reqheight() + 2 * self.pady)

    def _redraw(self, event) -> None:
        self.delete("background")
        self.create_image(0, 0, anchor="nw", tags="background", image=shape(
            self, event.width, event.height, px(self, 12), CARD, CARD_EDGE, px(self, 1)))
        self.tag_lower("background")
        self.itemconfigure("body", width=max(1, event.width - 2 * self.padx))


class NavItem(Shape):
    """An entry of the settings window's sidebar: icon and name, the current one lit."""

    def __init__(self, parent, icon: str, text: str, command, selected: bool = False, width: int = 170):
        super().__init__(parent, cursor="hand2")
        self.icon, self.text, self.command, self.selected = icon, text, command, selected
        self.w, self.h = px(self, width), px(self, 38)
        self.configure(width=self.w, height=self.h)
        self.hover = False
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", lambda _e: self.command())
        self._draw()

    def _set_hover(self, hover: bool) -> None:
        self.hover = hover
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        if self.selected or self.hover:
            self.create_image(0, 0, anchor="nw",
                              image=shape(self, self.w, self.h, px(self, 8), FIELD if self.selected else CARD))
        if self.selected:
            bar = px(self, 3)
            self.create_image(0, self.h // 2, anchor="w",
                              image=shape(self, bar, self.h - 2 * px(self, 10), bar // 2 or 1, ACCENT))
        fg = TEXT if self.selected or self.hover else MUTED
        self.create_text(px(self, 16), self.h // 2, text=self.icon, font=icon_font(self, 12),
                         fill=ACCENT_HI if self.selected else fg, anchor="w")
        self.create_text(px(self, 46), self.h // 2, text=self.text, font=FONT_BUTTON, fill=fg, anchor="w")


class ThinScrollbar(Shape):
    """A slim scrollbar for a Listbox: Windows' own can't be colored."""

    def __init__(self, parent, target):
        super().__init__(parent, width=px(parent, 8), cursor="hand2")
        self.target = target
        self.first, self.last = 0.0, 1.0
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<ButtonPress-1>", self._grab)
        self.bind("<B1-Motion>", self._drag)
        self._grab_at = 0.0

    def set(self, first, last) -> None:
        self.first, self.last = float(first), float(last)
        self._draw()

    def _grab(self, event) -> None:
        self._grab_at = event.y / max(1, self.winfo_height()) - self.first

    def _drag(self, event) -> None:
        self.target.yview_moveto(event.y / max(1, self.winfo_height()) - self._grab_at)

    def _draw(self) -> None:
        self.delete("all")
        height, width = self.winfo_height(), int(self.cget("width"))
        if self.last - self.first >= 1.0 or height < 4:
            return
        top, bottom = round(self.first * height), round(self.last * height)
        self.create_image(0, top, anchor="nw", image=shape(self, width, max(width, bottom - top), width // 2, FIELD_HI))


# --- layout helpers -------------------------------------------------------------------------------

def label(parent, text: str, font=FONT, fg: str = TEXT, wrap: int = 0, **kwargs) -> tk.Label:
    return tk.Label(parent, text=text, bg=parent_bg(parent), fg=fg, font=font, justify="left", anchor="w",
                    wraplength=px(parent, wrap) if wrap else 0, **kwargs)


def stripe(parent, width: int = 40, height: int = 4) -> tk.Canvas:
    """The three F1 sector colors, as rounded bars."""
    w, h, gap = px(parent, width), px(parent, height), px(parent, 6)
    canvas = Shape(parent, width=3 * w + 2 * gap, height=h)
    canvas.images = [shape(canvas, w, h, h // 2, color) for color in SECTORS]
    for i, image in enumerate(canvas.images):
        canvas.create_image(i * (w + gap), 0, image=image, anchor="nw")
    return canvas


def separator(parent) -> tk.Frame:
    return tk.Frame(parent, bg=CARD_EDGE, height=1)


# --- Windows chrome -----------------------------------------------------------------------------------

DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_WINDOW_CORNER_PREFERENCE = 20, 33
DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR = 34, 35, 36
DWMWCP_ROUND = 2


def _colorref(color: str) -> int:
    r, g, b, _ = _rgba(color)
    return r | g << 8 | b << 16


def style_window(window: tk.Toplevel, caption: str = BG) -> None:
    """Dark title bar in the window's color, rounded corners (Windows 11) and a dark border."""
    try:
        window.update_idletasks()
        hwnd = int(window.wm_frame(), 16)
        dwm = ctypes.windll.dwmapi
        for attribute, value in ((DWMWA_USE_IMMERSIVE_DARK_MODE, 1), (DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND),
                                 (DWMWA_CAPTION_COLOR, _colorref(caption)), (DWMWA_BORDER_COLOR, _colorref(CARD_EDGE)),
                                 (DWMWA_TEXT_COLOR, _colorref(TEXT))):
            value = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError, ValueError, tk.TclError):
        pass  # an older Windows keeps its own title bar


def use_dark_menus() -> None:
    """Native menus (the tray icon's) in Windows' dark style. uxtheme's SetPreferredAppMode and
    FlushMenuThemes have no names, only ordinals (Windows 10 1903 and later); elsewhere this does nothing."""
    try:
        if sys.getwindowsversion().build < 18362:
            return
        uxtheme = ctypes.WinDLL("uxtheme")
        uxtheme[135](2)  # SetPreferredAppMode(ForceDark)
        uxtheme[136]()  # FlushMenuThemes
    except (AttributeError, OSError):
        pass


def menu_colors() -> dict:
    """For a tk.Menu: Tk draws its menus itself, in these colors."""
    return {"bg": CARD, "fg": TEXT, "activebackground": ACCENT, "activeforeground": "#ffffff",
            "disabledforeground": FAINT, "selectcolor": TEXT, "bd": 0, "relief": "flat",
            "font": ("Segoe UI", 10)}
