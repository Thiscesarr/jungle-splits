"""Records the README media from the demo: an animated clear (GIF) and screenshots of the overlay,
the welcome screen and the settings window, in English and Portuguese, into docs/<lang>/.

Only the app's own windows are captured (by their exact screen rectangle, fully opaque), so nothing
else on screen ends up in the images; the overlay is saved straight from the image it puts on screen. Sounds play at volume 0.
Run from the repo root: python tools/capture_media.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageGrab  # noqa: E402

import paths  # noqa: E402
from overlay import App  # noqa: E402
from sources import DemoSource  # noqa: E402
from welcome import WelcomeWindow  # noqa: E402

ROUTE = "Raptors->Red->Krugs->Recall->Wolves->Gromp->Blue"
WARMUP_SPEED, RECORD_SPEED, FPS = 12.0, 4.0, 8
BACKDROP = (14, 16, 20)


def grab(widget, target: Path) -> None:
    widget.update()
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + widget.winfo_width(), y + widget.winfo_height())).save(target)


def grab_overlay(app, target: Path) -> None:
    """The overlay's own image (shadow and rounded corners included) on the backdrop color."""
    image = Image.new("RGBA", app.last_image.size, BACKDROP + (255,))
    image.alpha_composite(app.last_image)
    image.convert("RGB").save(target)


def capture(language: str, out: Path, work: Path, seed: int = 11) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = work / "data"
    data.mkdir(parents=True)
    (data / "ui_state.json").write_text(json.dumps({
        "language": language, "welcomed": True, "x": 60, "y": 60, "champion": "Lee Sin",
        "routes": {"leesin": ROUTE}, "targets": {"leesin": 170.0}, "sound_volume": 0.0,
    }), encoding="utf-8")
    config = json.loads(paths.CONFIG.read_text(encoding="utf-8"))
    source = DemoSource(lambda: app.tracker.camps, "Lee Sin", 55.0, WARMUP_SPEED, seed=seed)
    app = App(config, data, source, paths.FALLBACK_SHEET, work / "sons", opaque=True)
    frames = work / "frames"
    frames.mkdir()
    state = {"frame": 0, "runs": 0, "recording": False}

    def step():
        tracker = app.tracker
        # Two quick runs build a PB and best segments; the third is recorded at watchable speed.
        if tracker.state == "finished" and not state.get("counted"):
            state["counted"] = True
            state["runs"] += 1
            if state["runs"] == 2:
                source.speed = RECORD_SPEED
                state["arm"] = True
            elif state["runs"] == 3:
                grab_overlay(app, out / "overlay-finished.png")
                app.root.after(1500, shots)
                return
        if tracker.state != "finished":
            state["counted"] = False
            if state.get("arm") and tracker.state == "waiting":
                state["recording"], state["arm"] = True, False
        if state["recording"]:
            grab_overlay(app, frames / f"{state['frame']:05d}.png")
            state["frame"] += 1
            if state["frame"] == FPS * 10:
                grab_overlay(app, out / "overlay-running.png")
        app.root.after(1000 // FPS, step)

    def shots():
        state["recording"] = False
        welcome = WelcomeWindow(app.root, app.icon_image, {"settings": "Ctrl+Shift+,", "move": "Ctrl+Shift+."},
                                lambda _lang: None)
        welcome.geometry("+520+60")  # clear of the overlay, which sits at the top left
        app.root.after(800, lambda: (grab(welcome, out / "welcome.png"), welcome.destroy(), settings()))

    def settings():
        app._open_settings()
        window = app.settings_window
        window.geometry("+520+60")
        tabs = ["general", "hotkeys", "sounds", "about"]

        def next_tab(i=0):
            if i == len(tabs):
                window._cancel()
                app.quit()
                return
            window._show_tab(tabs[i])
            app.root.after(700, lambda: (grab(window, out / f"settings-{tabs[i]}.png"), next_tab(i + 1)))

        app.root.after(500, next_tab)

    app.root.after(500, step)
    app.run()
    make_gif(frames, out / "demo.gif")


def make_gif(frames: Path, target: Path) -> None:
    """The overlay grows and shrinks during a run, so every frame goes on one canvas of the largest size,
    all sharing one palette taken from a sample of frames."""
    images = [Image.open(f).convert("RGB") for f in sorted(frames.glob("*.png"))]
    size = (max(i.width for i in images), max(i.height for i in images))
    canvases = []
    for image in images:
        canvas = Image.new("RGB", size, BACKDROP)
        canvas.paste(image, (0, 0))
        canvases.append(canvas)
    sample = Image.new("RGB", (size[0], size[1] * 4))
    for n, canvas in enumerate(canvases[:: max(1, len(canvases) // 4)][:4]):
        sample.paste(canvas, (0, size[1] * n))
    palette = sample.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    paletted = [c.quantize(palette=palette, dither=Image.Dither.NONE) for c in canvases]
    paletted[0].save(target, save_all=True, append_images=paletted[1:], duration=1000 // FPS, loop=0,
                     optimize=True, disposal=1)


def main() -> None:
    if len(sys.argv) > 1:
        language = sys.argv[1]
        work = Path(tempfile.mkdtemp(prefix="jungle-splits-media-"))
        try:
            capture(language, ROOT / "docs" / language, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        print("media written for", language)
        return
    # One process per language: two Tk sessions in one process interfere with each other.
    for language in ("en", "pt"):
        subprocess.run([sys.executable, __file__, language], check=True)


if __name__ == "__main__":
    main()
