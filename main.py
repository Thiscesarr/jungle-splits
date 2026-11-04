"""Jungle Splits: F1-style split timer overlay for jungle full clears in the Practice Tool."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from overlay import App
from sources import DemoSource, LiveClientSource
from tracker import parse_clock

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="simula clears sem abrir o jogo")
    parser.add_argument("--demo-speed", type=float, default=1.0, help="velocidade da simulação (ex.: 3)")
    args = parser.parse_args()

    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if args.demo:
        # Demo runs keep their own PBs so they never mix with real ones.
        source = DemoSource(lambda: app.tracker.camps, parse_clock(config.get("camp_spawn", "1:30")),
                            args.demo_speed)
        app = App(config, ROOT / "data_demo", source)
    else:
        app = App(config, ROOT / "data", LiveClientSource())
    app.run()


if __name__ == "__main__":
    main()
