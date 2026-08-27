import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from four_u_four_free._compat.game.launch_options import (
    get_launch_options,
    launch_options_backup_path,
    online_fix_enabled,
    toggle_online_fix,
)


LOCALCONFIG = """"UserLocalConfigStore"
{
    "Software"
    {
        "Valve"
        {
            "Steam"
            {
                "apps"
                {
                    "42"
                    {
                        "LaunchOptions" "-novid  -windowed"
                    }
                }
            }
        }
    }
}
"""


class LaunchOptionsTests(unittest.TestCase):
    def test_online_fix_is_backed_up_preserved_and_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            steam = Path(directory)
            config = steam / "userdata" / "123" / "config" / "localconfig.vdf"
            config.parent.mkdir(parents=True)
            config.write_text(LOCALCONFIG, encoding="utf-8")

            with patch(
                "four_u_four_free._compat.game.launch_options._is_steam_running",
                return_value=False,
            ):
                ok, message = toggle_online_fix(steam, "42")

            self.assertTrue(ok, message)
            self.assertIn("verified", message)
            self.assertTrue(online_fix_enabled(steam, "42"))
            self.assertEqual(
                get_launch_options(steam, "42"), "-novid  -windowed -onlinefix"
            )
            backup = launch_options_backup_path(steam)
            self.assertIsNotNone(backup)
            self.assertEqual(backup.read_text(encoding="utf-8"), LOCALCONFIG)
            self.assertFalse(config.with_name("localconfig.vdf.4u4free.tmp").exists())

            with patch(
                "four_u_four_free._compat.game.launch_options._is_steam_running",
                return_value=False,
            ):
                ok, message = toggle_online_fix(steam, "42")

            self.assertTrue(ok, message)
            self.assertFalse(online_fix_enabled(steam, "42"))
            self.assertEqual(get_launch_options(steam, "42"), "-novid  -windowed")


if __name__ == "__main__":
    unittest.main()
