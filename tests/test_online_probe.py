import tempfile
import unittest
from pathlib import Path

from four_u_four_free.online_probe import probe_online_compatibility


class OnlineProbeTests(unittest.TestCase):
    def test_unknown_small_steam_game_is_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / "bin" / "win64").mkdir(parents=True)
            (game / "bin" / "win64" / "steam_api64.dll").touch()
            result = probe_online_compatibility(game)
            self.assertTrue(result.allow_generic)
            self.assertIn("Likely Steam API compatible", result.status)
            self.assertIn("steam_api64.dll", result.evidence[0])

    def test_anti_cheat_blocks_generic_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / "steam_api64.dll").touch()
            (game / "EasyAntiCheat_EOS_Setup.exe").touch()
            result = probe_online_compatibility(game)
            self.assertFalse(result.allow_generic)
            self.assertEqual(result.status, "Anti-cheat detected")

    def test_external_backend_blocks_generic_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / "steam_api64.dll").touch()
            (game / "EOSSDK-Win64-Shipping.dll").touch()
            result = probe_online_compatibility(game)
            self.assertFalse(result.allow_generic)
            self.assertEqual(result.status, "External backend detected")

    def test_steamdb_community_rule_detects_less_common_anticheat(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / "steam_api64.dll").touch()
            marker = game / "AntiCheatExpert" / "client.bin"
            marker.parent.mkdir()
            marker.touch()
            result = probe_online_compatibility(game)
            self.assertFalse(result.allow_generic)
            self.assertEqual(result.status, "Anti-cheat detected")
            self.assertTrue(any("AntiCheatExpert" in item for item in result.evidence))

    def test_steamdb_backend_rule_detects_playfab_party(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            (game / "steam_api64.dll").touch()
            (game / "PartyWin32.dll").touch()
            result = probe_online_compatibility(game)
            self.assertFalse(result.allow_generic)
            self.assertEqual(result.status, "External backend detected")
            self.assertTrue(any("Playfab" in item for item in result.evidence))


if __name__ == "__main__":
    unittest.main()
