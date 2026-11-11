"""The live game feed (sources.py): only the Practice Tool is timed. In a ranked or normal game a laner's
gold would look like jungle camps, so those games are never read."""
import io
import json
import queue
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sources
from sources import LiveClientSource, Sample, game_mode, read_game


def game(mode="PRACTICETOOL", game_time=61.5, gold=512.0, **game_data) -> dict:
    """What the Live Client Data API answers during a game."""
    data = {"gameData": {"gameTime": game_time, "mapName": "Map11", **game_data},
            "activePlayer": {"currentGold": gold, "level": 2, "riotId": "Me#BR1"},
            "allPlayers": [{"riotId": "Me#BR1", "championName": "Lee Sin", "scores": {"creepScore": 4},
                            "items": [{"itemID": 1102}]},
                           {"riotId": "Other#BR1", "championName": "Garen", "scores": {"creepScore": 30}, "items": []}]}
    if mode is not None:
        data["gameData"]["gameMode"] = mode
    return data


class Stop(BaseException):
    """Ends the feed's endless loop in a test."""


class SourcesTest(unittest.TestCase):
    def test_practice_tool_gives_a_sample(self):
        kind, sample = read_game(game(), received=9.0)
        self.assertEqual(kind, "sample")
        self.assertIsInstance(sample, Sample)
        self.assertEqual((sample.game_time, sample.gold, sample.cs, sample.level, sample.items, sample.champion,
                          sample.received), (61.5, 512.0, 4, 2, 1, "Lee Sin", 9.0))

    def test_other_games_are_not_read(self):
        """Ranked and normal games (CLASSIC), ARAM and the rest: no gold, no CS, only the mode."""
        for mode in ("CLASSIC", "ARAM", "URF", "TUTORIAL", "NEXUSBLITZ", "CHERRY", "TFT", "practice"):
            self.assertEqual(read_game(game(mode), 0.0), ("other_game", mode.upper()), mode)

    def test_a_game_that_does_not_say_its_mode_is_not_read(self):
        for data in (game(None), game(""), game(7), {"gameData": None, "activePlayer": {"currentGold": 1}}, {}):
            self.assertEqual(read_game(data, 0.0), ("other_game", "?"))

    def test_mode_spelling(self):
        for text in ("PRACTICETOOL", "PracticeTool", "practice_tool", " PRACTICE TOOL "):
            self.assertEqual(game_mode(game(text)), "PRACTICETOOL", text)
            self.assertEqual(read_game(game(text), 0.0)[0], "sample", text)

    def test_broken_practice_data_still_raises(self):
        """The feed treats these as the game not being ready (offline), as before."""
        data = game()
        del data["activePlayer"]["currentGold"]
        with self.assertRaises(KeyError):
            read_game(data, 0.0)

    # --- the polling loop ----------------------------------------------------------------------

    def feed(self, answers: list) -> tuple[list, list]:
        """Runs the feed over these API answers (a dict, or an exception for no game); returns the events
        it sent and how long it waited after each answer."""
        answers = list(answers)
        sleeps = []

        class Opener:
            def open(self, _url, timeout):
                if not answers:
                    raise Stop
                answer = answers.pop(0)
                if isinstance(answer, Exception):
                    raise answer
                return io.BytesIO(json.dumps(answer).encode())

        source = LiveClientSource(interval=0.1)
        source.out = queue.Queue()
        with mock.patch.object(sources.urllib.request, "build_opener", return_value=Opener()), \
                mock.patch.object(sources.time, "sleep", sleeps.append):
            with self.assertRaises(Stop):
                source.run()
        events = []
        while not source.out.empty():
            events.append(source.out.get())
        return events, sleeps

    def test_ranked_game_is_announced_once_and_polled_slowly(self):
        events, sleeps = self.feed([OSError()] + [game("CLASSIC", gold=500.0 + 300 * i) for i in range(4)] + [OSError()])
        self.assertEqual(events, [("offline",), ("other_game", "CLASSIC"), ("offline",)])
        self.assertEqual(sleeps, [1.0] + [sources.OTHER_GAME_POLL] * 4 + [1.0])
        self.assertGreaterEqual(sources.OTHER_GAME_POLL, 3.0)  # a ranked game is left alone

    def test_practice_tool_is_sampled_every_time(self):
        events, sleeps = self.feed([game(game_time=60.0 + i) for i in range(3)])
        self.assertEqual([e[0] for e in events], ["sample"] * 3)
        self.assertEqual([e[1].game_time for e in events], [60.0, 61.0, 62.0])
        self.assertTrue(all(s <= 0.1 for s in sleeps))

    def test_ranked_then_practice_tool(self):
        events, _ = self.feed([game("CLASSIC"), game("CLASSIC"), OSError(), game(), game("ARAM"), game("ARAM")])
        self.assertEqual([e[0] for e in events], ["other_game", "offline", "sample", "other_game"])
        self.assertEqual(events[-1], ("other_game", "ARAM"))

    def test_offline_is_announced_once(self):
        events, _ = self.feed([OSError(), ValueError(), OSError(), game()])
        self.assertEqual([e[0] for e in events], ["offline", "sample"])


if __name__ == "__main__":
    unittest.main()
