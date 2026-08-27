import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from four_u_four_free.achievement_service import (
    achievement_manager_path,
    open_achievement_manager,
    require_achievement_app_id,
)
from four_u_four_free.errors import FourUFourFreeError


class AchievementServiceTests(unittest.TestCase):
    def test_manager_path_is_relative_to_application_root(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = (
                Path(directory)
                / "third_party"
                / "steam-achievement-manager"
                / "SAM.Game.exe"
            )
            self.assertEqual(achievement_manager_path(Path(directory)), expected)

    def test_app_id_validation(self):
        self.assertEqual(require_achievement_app_id(" 233450 "), "233450")
        for value in ("", "0", "abc", "-1"):
            with self.subTest(value=value), self.assertRaises(FourUFourFreeError):
                require_achievement_app_id(value)

    @unittest.skipUnless(os.name == "nt", "Windows-only helper")
    def test_open_manager_uses_selected_app_and_helper_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = achievement_manager_path(Path(directory))
            executable.parent.mkdir(parents=True)
            executable.touch()
            process = Mock(pid=3141)
            with (
                patch(
                    "four_u_four_free.achievement_service.steam_is_running",
                    return_value=True,
                ),
                patch(
                    "four_u_four_free.achievement_service.subprocess.Popen",
                    return_value=process,
                ) as popen,
            ):
                self.assertEqual(
                    open_achievement_manager("233450", root=Path(directory)), 3141
                )
            arguments, keywords = popen.call_args
            self.assertEqual(arguments[0], [str(executable), "233450"])
            self.assertEqual(keywords["cwd"], str(executable.parent))


if __name__ == "__main__":
    unittest.main()
