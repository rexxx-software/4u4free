import tempfile
import unittest
from pathlib import Path

from four_u_four_free.steam import find_steam_root, list_games, list_libraries
from tests.helpers import make_fake_steam


class SteamTests(unittest.TestCase):
    def test_explicit_discovery_libraries_and_games(self):
        with tempfile.TemporaryDirectory() as directory:
            steam, second = make_fake_steam(Path(directory))
            location = find_steam_root(steam)
            self.assertIsNotNone(location)
            self.assertEqual(location.source, "command-line")
            libraries = list_libraries(steam)
            self.assertEqual(libraries, [steam.resolve(), second.resolve()])
            games = list_games(libraries)
        self.assertEqual([game.app_id for game in games], ["10", "20"])
        self.assertEqual(games[0].name, "Counter-Strike")

    def test_missing_explicit_root_is_not_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "not-steam"
            self.assertIsNone(find_steam_root(missing, None))


if __name__ == "__main__":
    unittest.main()

