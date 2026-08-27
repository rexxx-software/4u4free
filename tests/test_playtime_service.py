import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from four_u_four_free.errors import FourUFourFreeError
from four_u_four_free.playtime_service import (
    PlaytimeSession,
    format_duration,
    playtime_idler_path,
    require_playtime_app_id,
    require_session_duration,
    start_headless_idle,
    start_steam_game,
    stop_headless_idle,
)


class PlaytimeServiceTests(unittest.TestCase):
    def test_validation_and_formatting(self):
        self.assertEqual(require_playtime_app_id(" 233450 "), "233450")
        self.assertEqual(require_session_duration(1, 30), 5400)
        self.assertEqual(format_duration(5405), "1h 30m 05s")
        with self.assertRaises(FourUFourFreeError):
            require_playtime_app_id("not-an-app")
        with self.assertRaises(FourUFourFreeError):
            require_session_duration(0, 0)
        with self.assertRaises(FourUFourFreeError):
            require_session_duration(720, 1)

    def test_session_snapshot_is_bounded(self):
        session = PlaytimeSession.create("42", "Example", 0, 1, now=100)
        self.assertEqual(session.snapshot(now=90), (0, 60, 0.0))
        self.assertEqual(session.snapshot(now=130), (30, 30, 0.5))
        self.assertEqual(session.snapshot(now=200), (60, 0, 1.0))

    def test_launch_requires_steam_and_uses_validated_uri(self):
        with patch(
            "four_u_four_free.playtime_service.steam_is_running",
            return_value=False,
        ):
            with self.assertRaises(FourUFourFreeError):
                start_steam_game("42")

        with (
            patch(
                "four_u_four_free.playtime_service.steam_is_running",
                return_value=True,
            ),
            patch("four_u_four_free.playtime_service.sys.platform", "win32"),
            patch("four_u_four_free.playtime_service.os.startfile", create=True) as start,
        ):
            self.assertEqual(start_steam_game("42"), "steam://run/42")
            start.assert_called_once_with("steam://run/42")

    def test_idler_path_uses_the_bundled_sam_directory(self):
        root = Path("C:/example/app")
        self.assertEqual(
            playtime_idler_path(root),
            root
            / "third_party"
            / "steam-achievement-manager"
            / "4u4free.PlaytimeIdler.exe",
        )

    def test_headless_idle_starts_and_stops_the_helper(self):
        executable = Path("C:/example/4u4free.PlaytimeIdler.exe")
        process = MagicMock()
        process.poll.return_value = None
        process.stdout.readline.return_value = "READY 42\n"

        with (
            patch("four_u_four_free.playtime_service.sys.platform", "win32"),
            patch(
                "four_u_four_free.playtime_service.steam_is_running",
                return_value=True,
            ),
            patch(
                "four_u_four_free.playtime_service.require_playtime_idler",
                return_value=executable,
            ),
            patch(
                "four_u_four_free.playtime_service.subprocess.Popen",
                return_value=process,
            ) as popen,
        ):
            result = start_headless_idle("42", parent_process_id=1234)

        self.assertIs(result, process)
        self.assertEqual(
            popen.call_args.args[0],
            [str(executable), "42", "1234"],
        )
        self.assertEqual(popen.call_args.kwargs["cwd"], str(executable.parent))

        process.wait.return_value = 0
        stop_headless_idle(process)
        process.stdin.write.assert_called_once_with("stop\n")
        process.stdin.flush.assert_called_once_with()
        process.wait.assert_called_once()

    def test_headless_idle_requires_running_steam(self):
        with (
            patch("four_u_four_free.playtime_service.sys.platform", "win32"),
            patch(
                "four_u_four_free.playtime_service.steam_is_running",
                return_value=False,
            ),
        ):
            with self.assertRaisesRegex(FourUFourFreeError, "Steam is not running"):
                start_headless_idle("42")


if __name__ == "__main__":
    unittest.main()
