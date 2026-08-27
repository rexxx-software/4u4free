import json
import tempfile
import unittest
from pathlib import Path

from four_u_four_free.config import AppConfig, ConfigStore
from four_u_four_free.errors import FourUFourFreeError
from four_u_four_free.settings_io import export_config, import_config, read_config_export


class SettingsIOTests(unittest.TestCase):
    def test_export_preview_import_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_store = ConfigStore(root / "source.json")
            source_store.save(AppConfig(steam_root=str(root / "Steam"), preferred_library=str(root / "Library")))
            exported = export_config(source_store, root / "export.json")

            target_store = ConfigStore(root / "target.json")
            target_store.save(AppConfig(steam_root="old"))
            preview = import_config(target_store, exported)
            self.assertFalse(preview["applied"])
            self.assertEqual(target_store.load().steam_root, "old")

            result = import_config(target_store, exported, apply=True)
            self.assertTrue(result["applied"])
            self.assertTrue(Path(result["backup"]).is_file())
            self.assertEqual(target_store.load().preferred_library, str(root / "Library"))

    def test_unknown_fields_and_schema_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for config in ({"schema_version": 3, "secret": "no"}, {"schema_version": 4}):
                path.write_text(
                    json.dumps({"format": "4u4free-config", "export_version": 1, "config": config}),
                    encoding="utf-8",
                )
                with self.subTest(config=config), self.assertRaises(FourUFourFreeError):
                    read_config_export(path)


if __name__ == "__main__":
    unittest.main()
