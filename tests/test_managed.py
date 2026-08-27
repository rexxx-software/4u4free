import tempfile
import unittest
from pathlib import Path

from four_u_four_free.integrity import verify_backup
from four_u_four_free.managed import list_managed_lua, quarantine_managed_lua
from tests.helpers import make_fake_steam


class ManagedLuaTests(unittest.TestCase):
    def test_list_preview_and_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, _ = make_fake_steam(root)
            plugin = steam / "config" / "stplug-in" / "named.lua"
            plugin.write_text("addappid(42)\n", encoding="utf-8")
            self.assertEqual(len(list_managed_lua(steam)), 2)

            preview = quarantine_managed_lua(steam, "42")
            self.assertFalse(preview["applied"])
            self.assertEqual(preview["files"], [str(plugin.resolve(strict=False))])
            self.assertTrue(plugin.exists())

            result = quarantine_managed_lua(
                steam,
                "42",
                apply=True,
                quarantine_root=root / "quarantine",
                backup_output=root / "backup",
            )

            self.assertTrue(result["applied"])
            self.assertFalse(plugin.exists())
            self.assertTrue(Path(result["moved"][0]).is_file())
            self.assertTrue(verify_backup(root / "backup").valid)


if __name__ == "__main__":
    unittest.main()
