import tempfile
import unittest
from pathlib import Path

from four_u_four_free.config import AppConfig, ConfigStore


class ConfigTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            store = ConfigStore(path)
            self.assertEqual(store.load(), AppConfig())
            expected = AppConfig(
                steam_root="C:/Steam",
                preferred_library="D:/Games",
                download_source="hubcap",
                hide_adult_content=False,
                confirm_downloads=False,
                store_density="compact",
                show_store_art=False,
                restart_steam_after_setup=True,
                welcome_acknowledged=True,
                save_vault_root="E:/Backups/4u4free",
                save_vault_sources={"233450": "E:/Saves/Prison Architect"},
                plugins_enabled=True,
                enabled_plugins=["example-tools"],
            )
            store.save(expected)
            self.assertEqual(store.load(), expected)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_migrates_old_or_invalid_preferences_to_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                '{"schema_version": 1, "download_source": "unknown", '
                '"hide_adult_content": "yes", "store_density": "huge"}',
                encoding="utf-8",
            )

            config = ConfigStore(path).load()

            self.assertEqual(config.schema_version, 3)
            self.assertEqual(config.download_source, "auto")
            self.assertTrue(config.hide_adult_content)
            self.assertEqual(config.store_density, "comfortable")
            self.assertFalse(config.welcome_acknowledged)


if __name__ == "__main__":
    unittest.main()
