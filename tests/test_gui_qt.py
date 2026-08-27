import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMessageBox,
    QTableWidgetItem,
)

from four_u_four_free.config import AppConfig, ConfigStore
from four_u_four_free.errors import FourUFourFreeError
from four_u_four_free.gui_qt import MainWindow, WelcomeDialog, _load_application_fonts
from four_u_four_free.steam import SteamGame


class QtGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_installed_game_selection_fills_dlc_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            folder = library / "steamapps" / "common" / "Example Game"
            folder.mkdir(parents=True)
            game = SteamGame(
                app_id="12345",
                name="Example Game",
                install_dir="Example Game",
                build_id="7",
                last_updated="",
                library=library,
                manifest=library / "steamapps" / "appmanifest_12345.acf",
            )
            window = MainWindow(auto_start=False)
            try:
                window._populate_dlc_games([game])
                window.dlc_game_select.setCurrentIndex(0)
                self.assertEqual(window.dlc_app_id.text(), "12345")
                self.assertEqual(Path(window.dlc_folder.text()), folder)
            finally:
                window.close()

    def test_installed_games_fill_achievement_and_online_fix_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            game = SteamGame(
                app_id="233450",
                name="Prison Architect",
                install_dir="Prison Architect",
                build_id="7",
                last_updated="",
                library=library,
                manifest=library / "steamapps" / "appmanifest_233450.acf",
            )
            window = MainWindow(auto_start=False)
            try:
                window._populate_achievement_games([game])
                window._populate_playtime_games([game])
                with patch.object(window, "_refresh_online_fix_status"):
                    window._populate_online_fix_games([game])

                self.assertEqual(
                    window.achievement_game_select.currentData()["app_id"], "233450"
                )
                self.assertEqual(
                    window.playtime_game_select.currentData()["app_id"], "233450"
                )
                self.assertEqual(
                    window.online_fix_game_select.currentData()["app_id"], "233450"
                )
                self.assertIn("Prison Architect", window.achievement_status.text())
            finally:
                window.close()

    def test_playtime_session_launches_through_steam_and_tracks_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            game = SteamGame(
                app_id="42",
                name="Example Game",
                install_dir="Example Game",
                build_id="",
                last_updated="",
                library=library,
                manifest=library / "steamapps" / "appmanifest_42.acf",
            )
            window = MainWindow(auto_start=False)
            window._populate_playtime_games([game])
            window.playtime_hours.setValue(0)
            window.playtime_minutes.setValue(1)
            try:
                with (
                    patch.object(
                        QMessageBox,
                        "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                    patch(
                        "four_u_four_free.gui_qt.start_steam_game",
                        return_value="steam://run/42",
                    ) as launch,
                ):
                    window._confirm_start_playtime_session()

                launch.assert_called_once_with("42")
                self.assertTrue(window.playtime_timer.isActive())
                self.assertIsNotNone(window._playtime_session)
                self.assertIn("Tracking Example Game", window.playtime_status.text())
                self.assertFalse(window.playtime_game_select.isEnabled())

                window._stop_playtime_tracking()
                self.assertFalse(window.playtime_timer.isActive())
                self.assertIsNone(window._playtime_session)
                self.assertIn("game remains open", window.playtime_remaining.text())
            finally:
                window.close()

    def test_headless_playtime_session_starts_and_stops_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            game = SteamGame(
                app_id="42",
                name="Example Game",
                install_dir="Example Game",
                build_id="",
                last_updated="",
                library=library,
                manifest=library / "steamapps" / "appmanifest_42.acf",
            )
            process = MagicMock()
            process.poll.return_value = None
            window = MainWindow(auto_start=False)
            window._populate_playtime_games([game])
            window.playtime_method.setCurrentIndex(1)
            window.playtime_hours.setValue(0)
            window.playtime_minutes.setValue(1)
            try:
                with (
                    patch.object(
                        QMessageBox,
                        "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                    patch(
                        "four_u_four_free.gui_qt.start_headless_idle",
                        return_value=process,
                    ) as start,
                    patch("four_u_four_free.gui_qt.stop_headless_idle") as stop,
                ):
                    window._confirm_start_playtime_session()
                    start.assert_called_once_with("42")
                    self.assertIs(window._playtime_idler_process, process)
                    self.assertEqual(window._playtime_session_mode, "headless")
                    self.assertTrue(window.playtime_timer.isActive())
                    self.assertIn("Headless idling", window.playtime_status.text())

                    window._stop_playtime_tracking()
                    stop.assert_called_once_with(process)
                    self.assertIsNone(window._playtime_idler_process)
                    self.assertIn(
                        "Headless helper stopped", window.playtime_remaining.text()
                    )
            finally:
                window.close()

    def test_playtime_visibility_opens_steam_privacy_settings(self):
        window = MainWindow(auto_start=False)
        try:
            with patch(
                "four_u_four_free.gui_qt.QDesktopServices.openUrl",
                return_value=True,
            ) as opened:
                window._open_playtime_privacy_settings()
            opened.assert_called_once()
            self.assertEqual(
                opened.call_args.args[0].toString(),
                "https://steamcommunity.com/my/edit/settings",
            )
        finally:
            window.close()

    def test_official_install_action_uses_steam_uri(self):
        window = MainWindow(auto_start=False)
        try:
            with patch(
                "four_u_four_free.gui_qt.QDesktopServices.openUrl",
                return_value=True,
            ) as opened:
                window._open_official_steam_install(
                    "4693030", "Congratulations On Your Purchase"
                )
            opened.assert_called_once()
            self.assertEqual(
                opened.call_args.args[0].toString(),
                "steam://install/4693030",
            )
            self.app.processEvents()
            self.assertIn("ownership is required", window.log_text.toPlainText())
        finally:
            window.close()

    def test_missing_provider_metadata_has_actionable_download_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(auto_start=False)
            updates = []
            window.events.download.connect(updates.append)
            try:
                with (
                    patch.object(window, "_require_compat"),
                    patch.object(window, "_steam_root", return_value=root),
                    patch(
                        "four_u_four_free.gui_qt.default_data_dir",
                        return_value=root / "data",
                    ),
                    patch(
                        "four_u_four_free.gui_qt.download_lua_direct",
                        return_value=None,
                    ),
                ):
                    with self.assertRaisesRegex(
                        FourUFourFreeError, "purchase or activation"
                    ):
                        window._download_game(
                            4693030,
                            "Congratulations On Your Purchase",
                            object(),
                        )
                self.app.processEvents()
                self.assertEqual(
                    updates[-1]["status"],
                    "Metadata unavailable — install owned copy",
                )
            finally:
                window.close()

    def test_achievement_launch_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            game = SteamGame(
                app_id="42",
                name="Example Game",
                install_dir="Example Game",
                build_id="",
                last_updated="",
                library=library,
                manifest=library / "steamapps" / "appmanifest_42.acf",
            )
            window = MainWindow(auto_start=False)
            window._populate_achievement_games([game])
            try:
                with (
                    patch.object(
                        QMessageBox,
                        "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                    patch(
                        "four_u_four_free.gui_qt.open_achievement_manager",
                        return_value=3141,
                    ) as launch,
                ):
                    window._confirm_open_achievement_manager()
                launch.assert_called_once_with("42")
                self.assertIn(
                    "Opened for Example Game", window.achievement_status.text()
                )
            finally:
                window.close()

    def test_achievement_review_queue_opens_each_installed_game_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            games = [
                SteamGame(
                    app_id=app_id,
                    name=name,
                    install_dir=name,
                    build_id="",
                    last_updated="",
                    library=library,
                    manifest=library / "steamapps" / f"appmanifest_{app_id}.acf",
                )
                for app_id, name in (("42", "First Game"), ("43", "Second Game"))
            ]
            first = MagicMock(pid=1001)
            first.poll.return_value = 0
            second = MagicMock(pid=1002)
            second.poll.return_value = 0
            window = MainWindow(auto_start=False)
            window._installed_games = games
            window._populate_achievement_games(games)
            try:
                with (
                    patch.object(
                        QMessageBox,
                        "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                    patch.object(QMessageBox, "information"),
                    patch(
                        "four_u_four_free.gui_qt.start_achievement_manager",
                        side_effect=[first, second],
                    ) as start,
                    patch(
                        "four_u_four_free.gui_qt.QTimer.singleShot",
                        side_effect=lambda _delay, callback: callback(),
                    ),
                ):
                    window._confirm_achievement_batch()
                    window._poll_achievement_batch()
                    window._poll_achievement_batch()

                self.assertEqual(start.call_args_list, [call("42"), call("43")])
                self.assertEqual(window._achievement_batch_completed, 2)
                self.assertIn("completed: 2/2", window.achievement_batch_status.text())
                self.assertFalse(window.achievement_batch_timer.isActive())
                self.assertTrue(window.achievement_batch_button.isEnabled())
            finally:
                window.close()

    def test_hitman_online_fix_routes_to_game_specific_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            game = SteamGame(
                app_id="1659040",
                name="HITMAN World of Assassination",
                install_dir="HITMAN 3",
                build_id="",
                last_updated="",
                library=library,
                manifest=library / "steamapps" / "appmanifest_1659040.acf",
            )
            window = MainWindow(auto_start=False)
            try:
                with patch.object(window, "_refresh_online_fix_status"):
                    window._populate_online_fix_games([game])
                self.assertFalse(window._online_fix_profile.generic_supported)
                self.assertEqual(window._online_fix_profile.provider, "Peacock")
                self.assertFalse(window.online_fix_guide.isHidden())
            finally:
                window.close()

    def test_native_window_chrome_and_bundled_font(self):
        family = _load_application_fonts()
        self.assertEqual(family, "IBM Plex Sans")
        self.assertIn(family, QFontDatabase.families())

        window = MainWindow(auto_start=False)
        try:
            self.assertFalse(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
            self.assertTrue(window.windowFlags() & Qt.WindowType.WindowTitleHint)
            self.assertTrue(
                window.windowFlags() & Qt.WindowType.WindowMinMaxButtonsHint
            )
            self.assertTrue(window.windowFlags() & Qt.WindowType.WindowCloseButtonHint)
            self.assertFalse(hasattr(window, "title_bar"))
            self.assertEqual(window.window_layout.contentsMargins().left(), 0)

            window.showMaximized()
            self.app.processEvents()
            self.assertEqual(window.window_layout.contentsMargins().left(), 0)
            self.assertTrue(window.isMaximized())

            window.showNormal()
            self.app.processEvents()
            self.assertFalse(window.isMaximized())

            window.showMinimized()
            self.app.processEvents()
            self.assertTrue(window.isMinimized())

            window.showNormal()
            self.app.processEvents()
            window.close()
            self.app.processEvents()
            self.assertFalse(window.isVisible())
        finally:
            window.close()

    def test_advanced_stats_launch_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)
            game = SteamGame(
                app_id="42",
                name="Example Game",
                install_dir="Example Game",
                build_id="",
                last_updated="",
                library=library,
                manifest=library / "steamapps" / "appmanifest_42.acf",
            )
            window = MainWindow(auto_start=False)
            window._populate_stats_games([game])
            try:
                with (
                    patch.object(
                        QMessageBox,
                        "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                    patch(
                        "four_u_four_free.gui_qt.open_achievement_manager",
                        return_value=2718,
                    ) as launch,
                ):
                    window._confirm_open_stats()
                launch.assert_called_once_with("42")
                self.assertIn("Opened for Example Game", window.stats_status.text())
            finally:
                window.close()

    def test_save_vault_tab_creates_snapshot_for_selected_game(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            source = root / "saves"
            source.mkdir()
            (source / "slot.sav").write_text("save", encoding="utf-8")
            game = SteamGame(
                app_id="42",
                name="Example Game",
                install_dir="Example Game",
                build_id="",
                last_updated="",
                library=library,
                manifest=library / "steamapps" / "appmanifest_42.acf",
            )
            window = MainWindow(auto_start=False)
            window.store = ConfigStore(root / "config.json")
            window.preferences = AppConfig(save_vault_root=str(root / "vault"))
            with patch.object(window, "_detect_vault_source"):
                window._populate_save_vault_games([game])
            window.vault_source.setText(str(source))

            def run_now(fn, on_result=None, **_kwargs):
                result = fn()
                if on_result is not None:
                    on_result(result)

            try:
                with (
                    patch.object(
                        QMessageBox,
                        "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                    patch.object(window, "run_task", side_effect=run_now),
                ):
                    window._confirm_create_vault_snapshot()
                self.assertEqual(window.vault_table.rowCount(), 1)
                self.assertEqual(
                    window.store.load().save_vault_sources["42"], str(source)
                )
            finally:
                window.close()

    def test_background_worker_delivers_queued_result(self):
        window = MainWindow(auto_start=False)
        received = []
        try:
            window.run_task(lambda: 42, received.append, error_modal=False)
            deadline = time.monotonic() + 3
            while not received and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.app.processEvents()
            self.assertEqual(received, [42])
            self.assertFalse(window._workers)
            self.assertTrue(window.task_count.isHidden())
        finally:
            window.close()

    def test_tools_navigation_and_settings_dirty_state(self):
        window = MainWindow(auto_start=False)
        try:
            self.assertEqual(window.tools_nav.count(), 10)
            self.assertEqual(window.tools_tabs.count(), 10)
            window.tools_nav.setCurrentRow(3)
            self.assertEqual(window.tools_tabs.currentIndex(), 3)

            self.assertFalse(window.settings_save.isEnabled())
            window.settings_library.setText("D:/Different Library")
            self.assertTrue(window.settings_save.isEnabled())
            self.assertEqual(window.settings_change_status.text(), "Unsaved changes")
            window._populate_settings_controls(AppConfig())
            self.assertFalse(window.settings_save.isEnabled())
        finally:
            window.close()

    def test_data_tables_have_intentional_empty_states(self):
        window = MainWindow(auto_start=False)
        try:
            self.assertIn("installed Steam games", window.library_table.empty_text)
            self.assertIn("prepared from the Store", window.download_table.empty_text)
            self.assertIn("Check DLC", window.dlc_table.empty_text)
            self.assertIn("save snapshots", window.vault_table.empty_text)
        finally:
            window.close()

    def test_dlc_install_confirms_success_and_records_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            game_dir = Path(directory)
            window = MainWindow(auto_start=False)
            window.dlc_folder.setText(str(game_dir))
            window.dlc_app_id.setText("42")
            window.dlc_table.setRowCount(1)
            check = QTableWidgetItem()
            check.setCheckState(Qt.CheckState.Checked)
            window.dlc_table.setItem(0, 0, check)
            window.dlc_table.setItem(0, 1, QTableWidgetItem("101"))
            window.dlc_table.setItem(0, 2, QTableWidgetItem("Example DLC"))

            try:
                with (
                    patch.object(
                        QMessageBox,
                        "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                    patch.object(QMessageBox, "information") as information,
                    patch(
                        "four_u_four_free.gui_qt.install_unlocker",
                        return_value=True,
                    ),
                    patch(
                        "four_u_four_free.gui_qt.inspect_unlockers",
                        return_value=[
                            {"key": "creamapi", "name": "CreamAPI", "installed": True}
                        ],
                    ),
                ):
                    window._confirm_dlc_install()
                    deadline = time.monotonic() + 3
                    while window._workers and time.monotonic() < deadline:
                        self.app.processEvents()
                        time.sleep(0.01)
                    self.app.processEvents()

                self.assertFalse(window._workers)
                information.assert_called_once()
                self.assertEqual(window.download_table.rowCount(), 1)
                self.assertIn(
                    "Installed and verified",
                    window.download_table.item(0, 2).text(),
                )
                self.assertEqual(window.download_table.cellWidget(0, 3).value(), 100)
                self.assertIn("installed and verified", window.dlc_summary.text())
            finally:
                window.close()

    def test_first_launch_welcome_is_acknowledged_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "config.json")
            window = MainWindow(auto_start=False)
            window.store = store
            window.preferences = AppConfig()
            try:
                with patch.object(
                    WelcomeDialog,
                    "exec",
                    return_value=QDialog.DialogCode.Accepted,
                ) as execute:
                    window._show_first_launch_welcome()
                    execute.assert_called_once()

                self.assertTrue(store.load().welcome_acknowledged)

                with patch.object(WelcomeDialog, "exec") as execute_again:
                    window._show_first_launch_welcome()
                    execute_again.assert_not_called()
            finally:
                window.close()

    def test_welcome_dialog_contains_requested_message(self):
        dialog = WelcomeDialog()
        try:
            text = "\n".join(label.text() for label in dialog.findChildren(QLabel))
            self.assertIn("Welcome to 4u4free", text)
            self.assertIn("Developed by rexxxx", text)
            self.assertIn("free and open source", text)
            self.assertIn("If you paid for this, you were scammed", text)
            self.assertIn("Enjoy", text)
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
