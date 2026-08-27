"""Qt desktop interface for 4u4free.

The UI intentionally uses restrained Qt Widgets and a compact dark palette:
no gradients, oversized corner radii, decorative glass, or generated filler.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    QEvent,
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .achievement_service import (
    SAM_VERSION,
    open_achievement_manager,
    start_achievement_manager,
)
from .achievement_showcase import ShowcaseAchievement, recommend_for_game
from .config import AppConfig, ConfigStore, default_data_dir
from .dlc_service import (
    UNLOCKER_LABELS,
    fetch_dlc_catalog,
    inspect_game_apis,
    inspect_unlockers,
    install_unlocker,
    require_app_id,
    require_game_directory,
    uninstall_unlocker,
)
from .errors import FourUFourFreeError
from .online_compat import OnlineCompatibility, online_compatibility
from .online_probe import OnlineProbe, probe_online_compatibility
from .plugin_system import PluginManager, PluginState, PluginTool
from .playtime_service import (
    PlaytimeSession,
    format_duration,
    start_headless_idle,
    start_steam_game,
    stop_headless_idle,
)
from .profiles import list_profiles
from .save_vault import SaveVault, VaultSnapshot, discover_save_folders, format_bytes
from .steam import SteamGame, doctor, list_games, list_libraries, require_steam_root

try:
    from four_u_four_free._compat.core.processes import (
        is_proc_running,
        launch_steam_unelevated,
    )
    from four_u_four_free._compat.core.storage.settings import get_setting
    from four_u_four_free._compat.core.storage.vdf import ensure_library_has_app
    from four_u_four_free._compat.core.structs import LuaEndpoint, Settings
    from four_u_four_free._compat.game.crack_fix import (
        _badge_summary,
        _extract_to_game_folder,
        fetch_crack_games,
        search_crack_games,
    )
    from four_u_four_free._compat.game.fix_game.steamstub_unpacker import (
        SteamStubUnpacker,
    )
    from four_u_four_free._compat.game.launch_options import (
        launch_options_backup_path,
        online_fix_enabled,
        toggle_online_fix,
    )
    from four_u_four_free._compat.game_list_fallback import (
        browse_games_json,
        search_games_json,
        search_name_fallback,
    )
    from four_u_four_free._compat.lua.choices import download_lua_direct
    from four_u_four_free._compat.lua.manager import parse_lua_contents
    from four_u_four_free._compat.lua.writer import ACFWriter, ConfigVDFWriter
    from four_u_four_free._compat.lumacore.lumacore_setup import (
        deactivate_lumacore,
        get_installed_lumacore_version,
        install_lumacore,
    )
    from four_u_four_free._compat.network.pixeldrain import (
        _extract_pixeldrain_id,
        download_pixeldrain,
    )
    from four_u_four_free._compat.steam_tools_compat import install_lua_to_steam

    HAS_COMPAT = True
    COMPAT_IMPORT_ERROR = ""
except ImportError as exc:  # pragma: no cover - exercised by source-only installs
    HAS_COMPAT = False
    COMPAT_IMPORT_ERROR = str(exc)


APP_BG = "#090C10"
SIDEBAR_BG = "#0D1116"
SURFACE = "#12171D"
SURFACE_RAISED = "#181E26"
BORDER = "#222A34"
TEXT = "#F2F5F7"
MUTED = "#8D98A5"
ACCENT = "#75DEC0"
ACCENT_HOVER = "#91E7CF"
ACCENT_INK = "#07130F"
DANGER = "#F28B82"
STEAM_PRIVACY_URL = "https://steamcommunity.com/my/edit/settings"

PER_PAGE = 24
UNLOCKER_CACHE_DIR = default_data_dir() / "unlockers"
HEADER_URL = "https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"


def _asset_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / name


def _load_application_fonts() -> str:
    family = "IBM Plex Sans"
    for filename in (
        "IBMPlexSans-Regular.ttf",
        "IBMPlexSans-Medium.ttf",
        "IBMPlexSans-SemiBold.ttf",
    ):
        QFontDatabase.addApplicationFont(str(_asset_path(f"fonts/{filename}")))
    return family


def _header_url_for(game: dict) -> str:
    value = str(game.get("header_image") or "")
    if value.startswith("http"):
        return value
    app_id = int(game.get("app_id") or 0)
    return HEADER_URL.format(app_id=app_id) if app_id else ""


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.fn()
        except FourUFourFreeError as exc:
            self.signals.error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"{exc.__class__.__name__}: {exc}")
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class UiEvents(QObject):
    log = Signal(str)
    status = Signal(str)
    download = Signal(object)


class PageTitle(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        detail = QLabel(subtitle)
        detail.setObjectName("pageSubtitle")
        detail.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(detail)


class Panel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("panel")


class DataTable(QTableWidget):
    """Consistent data table with a deliberate zero-row state."""

    def __init__(
        self,
        rows: int,
        columns: int,
        empty_text: str,
        parent: QWidget | None = None,
    ):
        super().__init__(rows, columns, parent)
        self.empty_text = empty_text
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setMouseTracking(True)
        self.verticalHeader().setDefaultSectionSize(40)
        self.horizontalHeader().setHighlightSections(False)
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

    def set_empty_text(self, text: str) -> None:
        self.empty_text = str(text)
        self.viewport().update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.rowCount() or not self.empty_text:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(MUTED))
        font = painter.font()
        font.setPointSizeF(10.0)
        painter.setFont(font)
        painter.drawText(
            self.viewport().rect().adjusted(32, 32, -32, -32),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self.empty_text,
        )


class StoreCard(Panel):
    download_requested = Signal(int, str)

    def __init__(self, game: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.game = game
        self.app_id = int(game.get("app_id") or 0)
        self._source_pixmap: QPixmap | None = None
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.image = QLabel(f"APP {self.app_id}" if self.app_id else "")
        self.image.setObjectName("gameImage")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedHeight(96)
        self.image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.image)

        name = QLabel(str(game.get("name") or f"App {self.app_id}"))
        name.setObjectName("cardTitle")
        name.setWordWrap(True)
        name.setFixedHeight(38)
        name.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        name.setToolTip(name.text())
        layout.addWidget(name)

        meta_parts = [f"App {self.app_id}"]
        updated = str(game.get("last_updated") or game.get("updated") or "")
        if updated:
            meta_parts.append(updated[:10])
        meta = QLabel("  /  ".join(meta_parts))
        meta.setObjectName("muted")
        layout.addWidget(meta)

        button = QPushButton("Get for free")
        button.setObjectName("primaryButton")
        button.setEnabled(bool(self.app_id))
        button.clicked.connect(
            lambda: self.download_requested.emit(
                self.app_id, str(game.get("name") or f"App {self.app_id}")
            )
        )
        layout.addWidget(button)

    def set_header(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._refresh_header()

    def _refresh_header(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        self.image.setPixmap(
            self._source_pixmap.scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.image.setText("")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_header()


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("welcomeDialog")
        self.setWindowTitle("Welcome to 4u4free")
        self.setModal(True)
        self.setMinimumWidth(470)
        self.setMaximumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 26)
        layout.setSpacing(12)

        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QLabel()
        logo.setFixedSize(44, 44)
        logo_path = _asset_path("brand-mark.png")
        if logo_path.exists():
            logo.setPixmap(
                QPixmap(str(logo_path)).scaled(
                    logo.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        title = QLabel("Welcome to 4u4free")
        title.setObjectName("welcomeTitle")
        brand.addWidget(logo)
        brand.addWidget(title)
        brand.addStretch(1)
        layout.addLayout(brand)

        developer = QLabel("Developed by rexxxx")
        developer.setObjectName("welcomeDeveloper")
        layout.addWidget(developer)

        open_source = QLabel("This app remains free and open source.")
        open_source.setObjectName("welcomeBody")
        layout.addWidget(open_source)

        warning = QLabel("If you paid for this, you were scammed.")
        warning.setObjectName("welcomeWarning")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        enjoy = QLabel("Enjoy.")
        enjoy.setObjectName("welcomeBody")
        layout.addWidget(enjoy)
        layout.addSpacing(8)

        actions = QHBoxLayout()
        actions.addStretch(1)
        accept = QPushButton("OK, continue")
        accept.setObjectName("primaryButton")
        accept.setDefault(True)
        accept.clicked.connect(self.accept)
        actions.addWidget(accept)
        layout.addLayout(actions)


class MainWindow(QMainWindow):
    def __init__(self, *, auto_start: bool = True):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.store = ConfigStore()
        self.preferences = self.store.load()
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[Worker] = set()
        self.events = UiEvents()
        self.events.log.connect(self._append_log)
        self.events.status.connect(self._set_status)
        self.events.download.connect(self._update_download)
        self._busy_count = 0
        self._store_games: list[dict] = []
        self._store_offset = 0
        self._store_total = 0
        self._store_columns = 0
        self._store_cards: dict[int, StoreCard] = {}
        self._pixmap_cache: dict[int, QPixmap] = {}
        self._image_replies: set[QNetworkReply] = set()
        self._crack_results: list[dict] = []
        self._installed_games: list[SteamGame] = []
        self._achievement_batch_queue: list[dict[str, str]] = []
        self._achievement_batch_current: subprocess.Popen | None = None
        self._achievement_batch_total = 0
        self._achievement_batch_completed = 0
        self._playtime_session: PlaytimeSession | None = None
        self._playtime_idler_process: subprocess.Popen | None = None
        self._playtime_session_mode = "launch"
        self._download_rows: dict[str, int] = {}
        self._vault_snapshots: list[VaultSnapshot] = []
        self._showcase_results: list[ShowcaseAchievement] = []
        self.plugin_manager = PluginManager()
        self._plugin_states: list[PluginState] = []
        self._plugin_tools: list[PluginTool] = []
        self.network = QNetworkAccessManager(self)

        self.setWindowTitle(f"4u4free {__version__}")
        self.resize(1220, 780)
        self.setMinimumSize(860, 600)
        icon_path = _asset_path("brand-mark.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_shell()
        self._apply_style()
        self._load_settings_into_ui()
        self._reload_plugins()
        self._show_page("home")

        if auto_start:
            QTimer.singleShot(80, self._begin_startup)

    # ---- shared UI -----------------------------------------------------

    def _begin_startup(self) -> None:
        self._show_first_launch_welcome()
        self._start_initial_tasks()

    def _show_first_launch_welcome(self) -> None:
        if self.preferences.welcome_acknowledged:
            return
        dialog = WelcomeDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.preferences.welcome_acknowledged = True
        try:
            self.store.save(self.preferences)
        except FourUFourFreeError as exc:
            self._task_error(str(exc), modal=True)

    def _build_shell(self) -> None:
        central = QWidget()
        central.setObjectName("windowCanvas")
        self.setCentralWidget(central)
        self.window_layout = QVBoxLayout(central)
        self.window_layout.setContentsMargins(0, 0, 0, 0)
        self.window_layout.setSpacing(0)

        self.window_frame = QFrame()
        self.window_frame.setObjectName("windowFrame")
        self.window_frame.setProperty("maximized", False)
        self.window_layout.addWidget(self.window_frame)

        frame_layout = QVBoxLayout(self.window_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        body = QWidget()
        body.setObjectName("windowBody")
        shell = QHBoxLayout(body)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        frame_layout.addWidget(body, 1)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(196)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 20, 14, 14)
        side.setSpacing(5)
        navigation = QLabel("NAVIGATION")
        navigation.setObjectName("sidebarSection")
        side.addWidget(navigation)
        side.addSpacing(7)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        nav_items = (
            ("home", "Home", "nav-home.svg"),
            ("store", "Store", "nav-store.svg"),
            ("downloads", "Downloads", "nav-downloads.svg"),
            ("dlc", "DLC", "nav-dlc.svg"),
            ("tools", "Tools", "nav-tools.svg"),
            ("settings", "Settings", "nav-settings.svg"),
            ("logs", "Activity", "nav-activity.svg"),
        )
        for key, label, icon_name in nav_items:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(QIcon(str(_asset_path(f"icons/{icon_name}"))))
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(
                lambda _checked=False, page=key: self._show_page(page)
            )
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            side.addWidget(button)

        side.addStretch(1)
        restart = QPushButton("Restart Steam")
        restart.setObjectName("quietButton")
        restart.clicked.connect(self._confirm_restart_steam)
        side.addWidget(restart)
        version = QLabel(f"4u4free  ·  v{__version__}")
        version.setObjectName("sidebarVersion")
        side.addWidget(version)
        shell.addWidget(self.sidebar)

        content = QFrame()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.pages = QStackedWidget()
        self.page_indexes: dict[str, int] = {}
        content_layout.addWidget(self.pages, 1)
        shell.addWidget(content, 1)

        for key, page in (
            ("home", self._build_home_page()),
            ("store", self._build_store_page()),
            ("downloads", self._build_downloads_page()),
            ("dlc", self._build_dlc_page()),
            ("tools", self._build_tools_page()),
            ("settings", self._build_settings_page()),
            ("logs", self._build_logs_page()),
        ):
            self.page_indexes[key] = self.pages.addWidget(page)

        status = QFrame()
        status.setObjectName("embeddedStatus")
        status.setFixedHeight(34)
        self.status_bar = status
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(14, 0, 14, 0)
        self.status_text = QLabel("Ready")
        self.status_text.setObjectName("statusText")
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setFixedSize(90, 4)
        self.busy.setTextVisible(False)
        self.busy.hide()
        self.task_count = QLabel("")
        self.task_count.setObjectName("taskCount")
        self.task_count.hide()
        status_layout.addWidget(self.status_text, 1)
        status_layout.addWidget(self.task_count)
        status_layout.addWidget(self.busy)
        content_layout.addWidget(status)

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        return page, layout

    def _show_page(self, key: str) -> None:
        self.pages.setCurrentIndex(self.page_indexes[key])
        self.nav_buttons[key].setChecked(True)
        if key == "store" and not self._store_games:
            self._load_store_page()

    def _start_initial_tasks(self) -> None:
        self._refresh_environment()
        self._refresh_lumacore(quiet=True)

    def _require_compat(self) -> None:
        if not HAS_COMPAT:
            detail = f": {COMPAT_IMPORT_ERROR}" if COMPAT_IMPORT_ERROR else ""
            raise FourUFourFreeError(
                f"Compatibility components are unavailable{detail}"
            )

    def _steam_root(self) -> Path:
        config = self.store.load()
        try:
            return require_steam_root(None, config.steam_root).path
        except Exception:
            guess = Path(r"C:\Program Files (x86)\Steam")
            if guess.is_dir():
                return guess
            raise FourUFourFreeError(
                "Steam folder not found. Configure it from the 4u4free CLI first."
            )

    def run_task(
        self,
        fn: Callable[[], Any],
        on_result: Callable[[Any], None] | None = None,
        *,
        label: str = "Working",
        error_modal: bool = True,
    ) -> None:
        self._busy_count += 1
        self.busy.show()
        self.task_count.setText(
            "1 task" if self._busy_count == 1 else f"{self._busy_count} tasks"
        )
        self.task_count.show()
        self._set_status(label)
        worker = Worker(fn)
        if on_result is not None:
            worker.signals.result.connect(on_result)
        worker.signals.error.connect(
            lambda message: self._task_error(message, modal=error_modal)
        )
        worker.signals.finished.connect(self._task_finished)
        worker.signals.finished.connect(
            lambda current=worker: self._workers.discard(current)
        )
        # QThreadPool owns the C++ runnable while it executes, but keeping the
        # Python wrapper alive is also required for its queued signal object.
        self._workers.add(worker)
        self.thread_pool.start(worker)

    def _task_error(self, message: str, *, modal: bool) -> None:
        self.log(f"Error: {message}")
        self._set_status(message)
        if modal:
            QMessageBox.critical(self, "4u4free", message)

    def _task_finished(self) -> None:
        self._busy_count = max(0, self._busy_count - 1)
        if self._busy_count == 0:
            self.busy.hide()
            self.task_count.hide()
            self.task_count.clear()
        else:
            self.task_count.setText(
                "1 task" if self._busy_count == 1 else f"{self._busy_count} tasks"
            )

    def log(self, message: str) -> None:
        self.events.log.emit(message)

    def _append_log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"{stamp}  {message}")

    def _set_status(self, message: str) -> None:
        self.status_text.setText(str(message))

    # ---- home ----------------------------------------------------------

    def _build_home_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(PageTitle("Home", "Steam status and local library overview"))

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        steam_panel = Panel()
        steam_layout = QVBoxLayout(steam_panel)
        steam_layout.setContentsMargins(16, 14, 16, 14)
        steam_title = QLabel("STEAM")
        steam_title.setObjectName("eyebrow")
        self.home_steam_status = QLabel("Checking installation")
        self.home_steam_status.setObjectName("metric")
        self.home_steam_detail = QLabel("")
        self.home_steam_detail.setObjectName("muted")
        self.home_steam_detail.setWordWrap(True)
        steam_layout.addWidget(steam_title)
        steam_layout.addWidget(self.home_steam_status)
        steam_layout.addWidget(self.home_steam_detail)
        status_row.addWidget(steam_panel, 1)

        core_panel = Panel()
        core_layout = QVBoxLayout(core_panel)
        core_layout.setContentsMargins(16, 14, 16, 14)
        core_title = QLabel("INTEGRATION")
        core_title.setObjectName("eyebrow")
        self.home_core_status = QLabel("Checking LumaCore")
        self.home_core_status.setObjectName("metric")
        core_detail = QLabel("Library registration and native Steam downloads")
        core_detail.setObjectName("muted")
        core_detail.setWordWrap(True)
        core_layout.addWidget(core_title)
        core_layout.addWidget(self.home_core_status)
        core_layout.addWidget(core_detail)
        status_row.addWidget(core_panel, 1)
        layout.addLayout(status_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        open_store = QPushButton("Open Store")
        open_store.setObjectName("primaryButton")
        open_store.clicked.connect(lambda: self._show_page("store"))
        refresh = QPushButton("Refresh library")
        refresh.clicked.connect(self._refresh_games)
        restart = QPushButton("Restart Steam")
        restart.clicked.connect(self._confirm_restart_steam)
        actions.addWidget(open_store)
        actions.addWidget(refresh)
        actions.addWidget(restart)
        actions.addStretch(1)
        layout.addLayout(actions)

        library_title = QLabel("Installed games")
        library_title.setObjectName("sectionTitle")
        layout.addWidget(library_title)
        self.library_table = DataTable(
            0,
            3,
            "Your installed Steam games will appear here after the library scan.",
        )
        self.library_table.setHorizontalHeaderLabels(["App ID", "Name", "Build"])
        self.library_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.library_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.library_table.verticalHeader().hide()
        header = self.library_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.library_table, 1)
        return page

    def _refresh_environment(self) -> None:
        def task():
            config = self.store.load()
            return doctor(None, config.steam_root)

        def done(report):
            found = bool(report.get("steam_found"))
            root = str(report.get("steam_root") or "Not found")
            self.home_steam_status.setText("Connected" if found else "Not found")
            self.home_steam_detail.setText(root)
            self.log(f"Steam check: {'ready' if found else 'not found'}")
            if found:
                self._refresh_games()

        self.run_task(task, done, label="Checking Steam", error_modal=False)

    def _refresh_games(self) -> None:
        self.library_table.set_empty_text("Scanning installed Steam libraries…")

        def task():
            config = self.store.load()
            location = require_steam_root(None, config.steam_root)
            return list_games(list_libraries(location.path))

        def done(games):
            self._installed_games = list(games)
            self.library_table.set_empty_text(
                "No installed games were found in the detected Steam libraries."
            )
            self.library_table.setRowCount(len(games))
            for row, game in enumerate(games):
                self.library_table.setItem(row, 0, QTableWidgetItem(str(game.app_id)))
                self.library_table.setItem(row, 1, QTableWidgetItem(game.name))
                self.library_table.setItem(
                    row, 2, QTableWidgetItem(str(game.build_id or "—"))
                )
            self._populate_dlc_games(self._installed_games)
            self._populate_achievement_games(self._installed_games)
            self._populate_stats_games(self._installed_games)
            self._populate_showcase_games(self._installed_games)
            self._populate_save_vault_games(self._installed_games)
            self._populate_playtime_games(self._installed_games)
            self._populate_online_fix_games(self._installed_games)
            self._reload_plugins()
            self._set_status(f"{len(games)} installed games")

        self.run_task(task, done, label="Refreshing library", error_modal=False)

    # ---- store ---------------------------------------------------------

    def _build_store_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(
            PageTitle(
                "Store",
                "Browse the catalog and prepare a title for Steam's native downloader",
            )
        )

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.store_search = QLineEdit()
        self.store_search.setPlaceholderText("Search by title or App ID")
        self.store_search.returnPressed.connect(self._search_store)
        search = QPushButton("Search")
        search.setObjectName("primaryButton")
        search.clicked.connect(self._search_store)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_store_search)
        controls.addWidget(self.store_search, 1)
        controls.addWidget(search)
        controls.addWidget(clear)
        layout.addLayout(controls)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        source_label = QLabel("Source")
        source_label.setObjectName("muted")
        self.store_source = QComboBox()
        for label, key in (
            ("Auto", "auto"),
            ("OurEveryday", "oureveryday"),
            ("Hubcap", "hubcap"),
            ("Ryuu", "ryuu"),
            ("DepotBox", "depotbox"),
        ):
            self.store_source.addItem(label, key)
        self.store_source.setMinimumWidth(150)
        self.store_hide_adult = QCheckBox("Hide adult content")
        self.store_hide_adult.setChecked(True)
        self.store_info = QLabel("")
        self.store_info.setObjectName("muted")
        filters.addWidget(source_label)
        filters.addWidget(self.store_source)
        filters.addWidget(self.store_hide_adult)
        filters.addStretch(1)
        filters.addWidget(self.store_info)
        layout.addLayout(filters)

        self.store_scroll = QScrollArea()
        self.store_scroll.setWidgetResizable(True)
        self.store_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.store_host = QWidget()
        self.store_host.setObjectName("storeHost")
        self.store_grid = QGridLayout(self.store_host)
        self.store_grid.setContentsMargins(0, 0, 0, 0)
        self.store_grid.setHorizontalSpacing(12)
        self.store_grid.setVerticalSpacing(12)
        self.store_scroll.setWidget(self.store_host)
        layout.addWidget(self.store_scroll, 1)

        pager = QHBoxLayout()
        self.store_previous = QPushButton("Previous")
        self.store_previous.clicked.connect(self._previous_store_page)
        self.store_previous.setEnabled(False)
        self.store_page_label = QLabel("Page 1")
        self.store_page_label.setObjectName("muted")
        self.store_next = QPushButton("Next")
        self.store_next.clicked.connect(self._next_store_page)
        self.store_next.setEnabled(False)
        pager.addWidget(self.store_previous)
        pager.addWidget(self.store_page_label)
        pager.addWidget(self.store_next)
        pager.addStretch(1)
        layout.addLayout(pager)
        return page

    def _load_store_page(self) -> None:
        offset = self._store_offset
        hide_adult = self.store_hide_adult.isChecked()
        self.store_info.setText("Loading catalog…")

        def task():
            return browse_games_json(
                offset=offset,
                per_page=PER_PAGE,
                sort_by="updated",
                block_nsfw=hide_adult,
            )

        def done(result):
            self._store_games = list(result.get("games", []))
            self._store_total = int(result.get("total", len(self._store_games)) or 0)
            self.store_info.setText(f"{self._store_total:,} titles")
            self._render_store()

        self.run_task(task, done, label="Loading store")

    def _search_store(self) -> None:
        query = self.store_search.text().strip()
        if not query:
            self._store_offset = 0
            self._load_store_page()
            return
        self.store_info.setText(f"Searching for “{query}”…")

        def task():
            results = search_games_json(query, limit=60)
            if not results:
                results = [
                    {**row, "header_image": ""}
                    for row in search_name_fallback(query, limit=60)
                ]
            return results

        def done(results):
            self._store_games = list(results)
            self._store_total = len(self._store_games)
            self._store_offset = 0
            self.store_info.setText(f"{len(results)} results for “{query}”")
            self._render_store()

        self.run_task(task, done, label=f"Searching for {query}")

    def _clear_store_search(self) -> None:
        self.store_search.clear()
        self._store_offset = 0
        self._load_store_page()

    def _previous_store_page(self) -> None:
        if self._store_offset <= 0:
            return
        self._store_offset = max(0, self._store_offset - PER_PAGE)
        self._load_store_page()

    def _next_store_page(self) -> None:
        if self._store_offset + PER_PAGE >= self._store_total:
            return
        self._store_offset += PER_PAGE
        self._load_store_page()

    def _desired_store_columns(self) -> int:
        width = max(1, self.store_scroll.viewport().width())
        compact = self.preferences.store_density == "compact"
        thresholds = (500, 740, 980) if compact else (560, 850, 1130)
        if width < thresholds[0]:
            columns = 1
        elif width < thresholds[1]:
            columns = 2
        elif width < thresholds[2]:
            columns = 3
        else:
            columns = 4
        return min(5, columns + (1 if compact and width >= 1180 else 0))

    def _render_store(self) -> None:
        while self.store_grid.count():
            item = self.store_grid.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().setParent(None)
                item.widget().deleteLater()
        self._store_cards.clear()
        columns = self._desired_store_columns()
        self._store_columns = columns
        if not self._store_games:
            empty = QLabel("No results. Try another search.")
            empty.setObjectName("emptyState")
            self.store_grid.addWidget(empty, 0, 0)
            self.store_page_label.setText("Page 1")
            self.store_previous.setEnabled(False)
            self.store_next.setEnabled(False)
            return
        for index, game in enumerate(self._store_games):
            card = StoreCard(game)
            card.download_requested.connect(self._confirm_store_download)
            self.store_grid.addWidget(card, index // columns, index % columns)
            if card.app_id:
                self._store_cards[card.app_id] = card
                cached = self._pixmap_cache.get(card.app_id)
                if cached is not None:
                    card.set_header(cached)
                elif self.preferences.show_store_art:
                    self._request_store_image(card.app_id, _header_url_for(game))
        for column in range(columns):
            self.store_grid.setColumnStretch(column, 1)
        page_number = self._store_offset // PER_PAGE + 1
        self.store_page_label.setText(f"Page {page_number}")
        self.store_previous.setEnabled(self._store_offset > 0)
        self.store_next.setEnabled(self._store_offset + PER_PAGE < self._store_total)

    def _request_store_image(self, app_id: int, url: str) -> None:
        if not url:
            return
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", f"4u4free/{__version__}".encode("ascii"))
        reply = self.network.get(request)
        reply.setProperty("app_id", app_id)
        reply.finished.connect(
            lambda current=reply: self._store_image_finished(current)
        )
        self._image_replies.add(reply)

    def _store_image_finished(self, reply: QNetworkReply) -> None:
        self._image_replies.discard(reply)
        app_id = int(reply.property("app_id") or 0)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(bytes(reply.readAll())):
                self._pixmap_cache[app_id] = pixmap
                card = self._store_cards.get(app_id)
                if card is not None:
                    card.set_header(pixmap)
        reply.deleteLater()

    def _selected_source(self):
        selected = str(self.store_source.currentData() or "auto")
        key_mapping = {
            "oureveryday": LuaEndpoint.OUREVERYDAY,
            "hubcap": LuaEndpoint.HUBCAP,
            "ryuu": LuaEndpoint.RYUU,
            "depotbox": LuaEndpoint.DEPOTBOX,
        }
        if selected in key_mapping:
            return key_mapping[selected]
        try:
            if str(get_setting(Settings.HUBCAP_KEY) or "").strip():
                return LuaEndpoint.HUBCAP
        except Exception:
            pass
        return LuaEndpoint.OUREVERYDAY

    def _confirm_store_download(self, app_id: int, name: str) -> None:
        if self.preferences.confirm_downloads:
            answer = QMessageBox.question(
                self,
                "Prepare download",
                f"Prepare {name} (App {app_id}) for Steam?\n\n"
                "The metadata and library entry will be written locally. Steam must be restarted to begin the native download.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        source = self._selected_source()
        self._show_page("downloads")
        self.run_task(
            lambda: self._download_game(app_id, name, source),
            lambda _result: None,
            label=f"Preparing {name}",
        )

    def _download_game(self, app_id: int, name: str, source) -> bool:
        self._require_compat()
        steam_path = self._steam_root()
        configured_library = self.preferences.preferred_library
        library_path = (
            Path(configured_library)
            if configured_library and Path(configured_library).is_dir()
            else steam_path
        )

        def progress(value: int, message: str) -> None:
            self.events.download.emit(
                {
                    "app_id": app_id,
                    "name": name,
                    "status": message,
                    "progress": value,
                    "time": time.strftime("%H:%M:%S"),
                }
            )

        progress(5, "Downloading metadata")
        saved_lua_root = default_data_dir() / "saved_lua"
        saved_lua_root.mkdir(parents=True, exist_ok=True)
        lua_path = download_lua_direct(
            dest=saved_lua_root,
            app_id=str(app_id),
            source=source,
            steam_path=steam_path,
        )
        if not lua_path:
            progress(0, "Metadata unavailable — install owned copy")
            raise FourUFourFreeError(
                f"No supported metadata provider returned a usable result for App {app_id}. "
                "Try another source. If your Steam account owns the game, use "
                "Install in Steam in Downloads to request the official install. "
                "A Steam purchase or activation is still required."
            )

        progress(22, "Parsing metadata")
        parsed = parse_lua_contents(
            lua_path.read_text(encoding="utf-8", errors="replace"), lua_path
        )
        if not parsed:
            progress(0, "Invalid metadata — try another source")
            raise FourUFourFreeError(
                f"The metadata returned for App {app_id} could not be parsed. "
                "Choose another source, or use Install in Steam if you own the game."
            )
        progress(48, "Writing depot configuration")
        ConfigVDFWriter(steam_path).add_decryption_keys_to_config(parsed)
        progress(62, "Installing Steam metadata")
        install_lua_to_steam(steam_path, str(app_id), lua_path)
        progress(76, "Writing library manifest")
        acf = ACFWriter(library_path)
        acf.write_acf(parsed)
        if hasattr(acf, "patch_workshop_acf"):
            acf.patch_workshop_acf(parsed)
        progress(90, "Registering library entry")
        ensure_library_has_app(steam_path, library_path, str(app_id))
        if self.preferences.restart_steam_after_setup:
            progress(96, "Restarting Steam")
            self._restart_steam()
            progress(100, "Ready — Steam restarted")
            self.log(f"Prepared {name} (App {app_id}) and restarted Steam.")
        else:
            progress(100, "Ready — restart Steam")
            self.log(f"Prepared {name} (App {app_id}); restart Steam to begin.")
        return True

    # ---- downloads -----------------------------------------------------

    def _build_downloads_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(
            PageTitle(
                "Downloads",
                "Preparation progress for titles queued from the Store",
            )
        )
        self.download_table = DataTable(
            0,
            6,
            "Titles prepared from the Store will appear here with their current status.",
        )
        self.download_table.setHorizontalHeaderLabels(
            ["App ID", "Title", "Status", "Progress", "Updated", "Action"]
        )
        self.download_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.download_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.download_table.verticalHeader().hide()
        header = self.download_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.download_table, 1)
        return page

    def _update_download(self, data: dict) -> None:
        key = str(data.get("row_key") or data["app_id"])
        if key not in self._download_rows:
            row = self.download_table.rowCount()
            self.download_table.insertRow(row)
            self._download_rows[key] = row
            self.download_table.setItem(row, 0, QTableWidgetItem(key))
            self.download_table.setItem(row, 1, QTableWidgetItem(str(data["name"])))
            bar = QProgressBar()
            bar.setTextVisible(True)
            self.download_table.setCellWidget(row, 3, bar)
            if data.get("action") == "open-folder":
                action = QPushButton("Open folder")
                action.setToolTip("Open the local game folder changed by this setup.")
                action.clicked.connect(
                    lambda _checked=False, folder=str(data.get("folder") or ""): (
                        self._open_local_folder(folder)
                    )
                )
            else:
                action = QPushButton("Install in Steam")
                action.setToolTip(
                    "Ask the official Steam client to install this App ID. "
                    "The signed-in account must own or have activated it."
                )
                action.clicked.connect(
                    lambda _checked=False, current_id=str(data["app_id"]), current_name=str(data["name"]): (
                        self._open_official_steam_install(current_id, current_name)
                    )
                )
            self.download_table.setCellWidget(row, 5, action)
        row = self._download_rows[key]
        self.download_table.setItem(row, 2, QTableWidgetItem(str(data["status"])))
        self.download_table.setItem(row, 4, QTableWidgetItem(str(data["time"])))
        bar = self.download_table.cellWidget(row, 3)
        if isinstance(bar, QProgressBar):
            bar.setValue(int(data["progress"]))

    def _open_official_steam_install(self, app_id: str, name: str = "") -> None:
        normalized = str(app_id).strip()
        if not normalized.isdigit():
            QMessageBox.warning(
                self, "Install in Steam", "This row has an invalid App ID."
            )
            return
        opened = QDesktopServices.openUrl(QUrl(f"steam://install/{normalized}"))
        if not opened:
            QMessageBox.warning(
                self,
                "Install in Steam",
                "Windows could not open the Steam install link. Start Steam and try again.",
            )
            return
        label = name.strip() or f"App {normalized}"
        self.log(
            f"Sent {label} (App {normalized}) to the official Steam installer; "
            "ownership is required."
        )
        self._set_status(f"Install request sent to Steam for App {normalized}")

    def _open_local_folder(self, folder: str) -> None:
        path = Path(folder)
        if not path.is_dir():
            QMessageBox.warning(self, "Open folder", "The local game folder was not found.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ---- DLC -----------------------------------------------------------

    def _build_dlc_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(
            PageTitle(
                "DLC",
                "Check a game's public DLC catalog, inspect its API files, and manage a local unlocker installation",
            )
        )

        target = Panel()
        form = QGridLayout(target)
        form.setContentsMargins(16, 16, 16, 16)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        game_label = QLabel("Installed game")
        game_label.setObjectName("fieldLabel")
        self.dlc_game_select = QComboBox()
        self.dlc_game_select.setMinimumWidth(260)
        self.dlc_game_select.currentIndexChanged.connect(self._select_dlc_game)
        self.dlc_refresh_button = QPushButton("Refresh DLC")
        self.dlc_refresh_button.clicked.connect(self._check_dlc)
        form.addWidget(game_label, 0, 0)
        form.addWidget(self.dlc_game_select, 0, 1)
        form.addWidget(self.dlc_refresh_button, 0, 2)
        detected_note = QLabel(
            "App ID and install folder are detected automatically from your Steam libraries."
        )
        detected_note.setObjectName("muted")
        detected_note.setWordWrap(True)
        form.addWidget(detected_note, 1, 1, 1, 2)
        form.setColumnStretch(1, 1)
        layout.addWidget(target)

        self.dlc_summary = QLabel("Choose an installed game to load its DLC catalog.")
        self.dlc_summary.setObjectName("muted")
        layout.addWidget(self.dlc_summary)

        self.dlc_table = DataTable(
            0,
            3,
            "Choose an installed Steam game to load its public DLC catalog.",
        )
        self.dlc_table.setHorizontalHeaderLabels(["Use", "DLC App ID", "Name"])
        self.dlc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dlc_table.verticalHeader().hide()
        dlc_header = self.dlc_table.horizontalHeader()
        dlc_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        dlc_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        dlc_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.dlc_table, 1)

        action_panel = Panel()
        action_layout = QHBoxLayout(action_panel)
        action_layout.setContentsMargins(14, 12, 14, 12)
        unlocker_label = QLabel("Unlocker")
        unlocker_label.setObjectName("fieldLabel")
        self.dlc_unlocker = QComboBox()
        for key, label in UNLOCKER_LABELS.items():
            self.dlc_unlocker.addItem(label, key)
        self.dlc_inspect_button = QPushButton("Inspect folder")
        self.dlc_inspect_button.clicked.connect(self._inspect_dlc_target)
        self.dlc_install_button = QPushButton("Install selected")
        self.dlc_install_button.setObjectName("primaryButton")
        self.dlc_install_button.clicked.connect(self._confirm_dlc_install)
        self.dlc_uninstall_button = QPushButton("Uninstall")
        self.dlc_uninstall_button.setObjectName("dangerButton")
        self.dlc_uninstall_button.clicked.connect(self._confirm_dlc_uninstall)
        action_layout.addWidget(unlocker_label)
        action_layout.addWidget(self.dlc_unlocker)
        action_layout.addStretch(1)
        action_layout.addWidget(self.dlc_inspect_button)
        action_layout.addWidget(self.dlc_install_button)
        action_layout.addWidget(self.dlc_uninstall_button)
        layout.addWidget(action_panel)
        setup_note = QLabel(
            "DLC setup updates the selected game's local API configuration. Restart the "
            "game afterward; Steam will not show an update unless owned DLC has a separate "
            "depot to download. The result is recorded under Downloads and Activity."
        )
        setup_note.setObjectName("muted")
        setup_note.setWordWrap(True)
        layout.addWidget(setup_note)
        return page

    def _populate_dlc_games(self, games: list[SteamGame]) -> None:
        previous = self._selected_combo_game(self.dlc_game_select)
        selected_app_id = str(previous.get("app_id") or "") if previous else ""
        self.dlc_game_select.blockSignals(True)
        self.dlc_game_select.clear()
        selected_index = 0
        for index, game in enumerate(games):
            self.dlc_game_select.addItem(
                f"{game.name}  ·  {game.app_id}", self._game_combo_data(game)
            )
            if str(game.app_id) == selected_app_id:
                selected_index = index
        has_games = bool(games)
        if has_games:
            self.dlc_game_select.setCurrentIndex(selected_index)
        else:
            self.dlc_game_select.addItem("No installed games found", None)
        self.dlc_game_select.blockSignals(False)
        for button in (
            self.dlc_refresh_button,
            self.dlc_inspect_button,
            self.dlc_install_button,
            self.dlc_uninstall_button,
        ):
            button.setEnabled(has_games)
        self._select_dlc_game(self.dlc_game_select.currentIndex())

    def _select_dlc_game(self, _index: int) -> None:
        game = self._selected_combo_game(self.dlc_game_select)
        if game is None:
            self.dlc_table.setRowCount(0)
            self.dlc_summary.setText("Refresh the Steam library to continue.")
            return
        self.dlc_table.setRowCount(0)
        self.dlc_summary.setText(f"Loading DLC for {game['name']}…")
        self._check_dlc()

    def _pick_directory(self, target: QLineEdit) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose folder", target.text()
        )
        if selected:
            target.setText(selected)

    def _check_dlc(self) -> None:
        game = self._selected_combo_game(self.dlc_game_select)
        if game is None:
            QMessageBox.warning(self, "DLC check", "Choose an installed game first.")
            return
        try:
            app_id = require_app_id(game["app_id"])
        except FourUFourFreeError as exc:
            QMessageBox.warning(self, "DLC check", str(exc))
            return

        def done(catalog):
            current = self._selected_combo_game(self.dlc_game_select)
            if current is None or current.get("app_id") != str(app_id):
                return
            rows = catalog["dlcs"]
            self.dlc_table.setRowCount(len(rows))
            for row, dlc in enumerate(rows):
                checkbox = QTableWidgetItem()
                checkbox.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                )
                checkbox.setCheckState(Qt.CheckState.Checked)
                self.dlc_table.setItem(row, 0, checkbox)
                self.dlc_table.setItem(row, 1, QTableWidgetItem(str(dlc["id"])))
                self.dlc_table.setItem(row, 2, QTableWidgetItem(str(dlc["name"])))
            self.dlc_summary.setText(
                f"{catalog['name']}  /  {len(rows)} DLC entries found"
            )
            self.log(f"DLC check: {catalog['name']} returned {len(rows)} entries")

        self.run_task(
            lambda: fetch_dlc_catalog(app_id),
            done,
            label=f"Checking DLC for App {app_id}",
            error_modal=False,
        )

    def _selected_dlc_ids(self) -> list[int]:
        selected = []
        for row in range(self.dlc_table.rowCount()):
            check = self.dlc_table.item(row, 0)
            app_id = self.dlc_table.item(row, 1)
            if (
                check is not None
                and check.checkState() == Qt.CheckState.Checked
                and app_id is not None
            ):
                selected.append(int(app_id.text()))
        return selected

    def _inspect_dlc_target(self) -> None:
        game = self._selected_combo_game(self.dlc_game_select)
        if game is None:
            QMessageBox.warning(self, "DLC inspection", "Choose an installed game first.")
            return
        folder_text = game["folder"]

        def task():
            folder = require_game_directory(folder_text)
            return {
                "apis": inspect_game_apis(folder),
                "unlockers": inspect_unlockers(folder),
            }

        def done(report):
            found = [row for row in report["apis"] if row["found"]]
            installed = [row["name"] for row in report["unlockers"] if row["installed"]]
            self.log("DLC target inspection")
            for row in report["apis"]:
                detail = ", ".join(str(path) for path in row["paths"]) or "not found"
                self.log(f"  {row['label']}: {detail}")
            self.dlc_summary.setText(
                f"{len(found)} supported API type(s) found  /  "
                f"Installed: {', '.join(installed) if installed else 'none'}"
            )

        self.run_task(task, done, label="Inspecting game folder")

    def _confirm_dlc_install(self) -> None:
        try:
            selected_game = self._selected_combo_game(self.dlc_game_select)
            if selected_game is None:
                raise FourUFourFreeError("Choose an installed game first.")
            folder = require_game_directory(selected_game["folder"])
            app_id = require_app_id(selected_game["app_id"])
            dlc_ids = self._selected_dlc_ids()
            if not dlc_ids:
                raise FourUFourFreeError(
                    "Select at least one DLC from the table first."
                )
            key = str(self.dlc_unlocker.currentData())
            game_name = str(selected_game.get("name") or f"App {app_id}")
        except FourUFourFreeError as exc:
            QMessageBox.warning(self, "DLC install", str(exc))
            return

        answer = QMessageBox.question(
            self,
            "Install DLC unlocker",
            f"Install {UNLOCKER_LABELS[key]} for {len(dlc_ids)} DLC entries into:\n{folder}\n\n"
            "Original API files will be backed up before replacement.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        row_key = f"dlc:{app_id}"

        def update_setup(progress: int, status: str) -> None:
            self.events.download.emit(
                {
                    "row_key": row_key,
                    "app_id": app_id,
                    "name": f"{game_name} DLC setup",
                    "status": status,
                    "progress": progress,
                    "time": time.strftime("%H:%M:%S"),
                    "action": "open-folder",
                    "folder": str(folder),
                }
            )

        update_setup(5, f"Applying {UNLOCKER_LABELS[key]}")

        def task():
            try:
                ok = install_unlocker(
                    folder,
                    key,
                    app_id,
                    dlc_ids,
                    cache_dir=UNLOCKER_CACHE_DIR,
                )
                if not ok:
                    raise FourUFourFreeError(
                        f"{UNLOCKER_LABELS[key]} installation did not complete."
                    )
                installed = {
                    row["key"] for row in inspect_unlockers(folder) if row["installed"]
                }
                if key not in installed:
                    raise FourUFourFreeError(
                        f"{UNLOCKER_LABELS[key]} files were written, but the installed "
                        "state could not be verified."
                    )
                return True
            except Exception as exc:
                update_setup(0, f"Failed: {exc}")
                raise

        def done(_ok):
            status = f"Files installed · {len(dlc_ids)} DLC entries"
            update_setup(100, status)
            self.log(
                f"Installed {UNLOCKER_LABELS[key]} files for {game_name} "
                f"({len(dlc_ids)} DLC entries) in {folder}"
            )
            self.dlc_summary.setText(
                f"{UNLOCKER_LABELS[key]} files installed  /  "
                f"{len(dlc_ids)} DLC entries configured  /  Verify in game"
            )
            self._set_status(f"DLC files installed for {game_name}")
            QMessageBox.information(
                self,
                "DLC files installed",
                f"{UNLOCKER_LABELS[key]} files were installed for {game_name}.\n\n"
                f"Configured entries: {len(dlc_ids)}\n"
                "4u4free verified the local configuration and backup, not the game's "
                "runtime entitlement result.\n\n"
                "Restart the game now. Do not wait for a Steam update: a local unlocker "
                "does not create one. DLC files with separate depots are installed by "
                "Steam only when the signed-in account owns them.",
            )

        self.run_task(
            task,
            done,
            label=f"Installing {UNLOCKER_LABELS[key]}",
        )

    def _confirm_dlc_uninstall(self) -> None:
        try:
            selected_game = self._selected_combo_game(self.dlc_game_select)
            if selected_game is None:
                raise FourUFourFreeError("Choose an installed game first.")
            folder = require_game_directory(selected_game["folder"])
            key = str(self.dlc_unlocker.currentData())
        except FourUFourFreeError as exc:
            QMessageBox.warning(self, "DLC uninstall", str(exc))
            return
        answer = QMessageBox.question(
            self,
            "Uninstall DLC unlocker",
            f"Remove {UNLOCKER_LABELS[key]} from:\n{folder}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def done(ok):
            message = "Removed" if ok else "Could not remove"
            self.log(f"{message} {UNLOCKER_LABELS[key]} from {folder}")
            self.dlc_summary.setText(f"{message} {UNLOCKER_LABELS[key]}")

        self.run_task(
            lambda: uninstall_unlocker(folder, key),
            done,
            label=f"Removing {UNLOCKER_LABELS[key]}",
        )

    # ---- tools ---------------------------------------------------------

    def _build_tools_page(self) -> QWidget:
        page, layout = self._page()
        layout.addWidget(
            PageTitle(
                "Tools",
                "Local integration maintenance and compatibility utilities",
            )
        )
        workspace = QFrame()
        workspace.setObjectName("toolWorkspace")
        workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        self.tools_nav = QListWidget()
        self.tools_nav.setObjectName("toolNavigation")
        self.tools_nav.setFixedWidth(152)
        self.tools_nav.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tools_tabs = QStackedWidget()
        self.tools_tabs.setObjectName("toolStack")
        tool_pages = (
            ("Achievements", self._build_achievements_tab()),
            ("Stats", self._build_stats_tab()),
            ("Showcase", self._build_showcase_tab()),
            ("Save Vault", self._build_save_vault_tab()),
            ("Playtime", self._build_playtime_tab()),
            ("Online Fix", self._build_online_fix_tab()),
            ("LumaCore", self._build_lumacore_tab()),
            ("SteamStub", self._build_steamstub_tab()),
            ("Community fixes", self._build_fixes_tab()),
            ("Plugins", self._build_plugins_tab()),
        )
        for label, tool_page in tool_pages:
            self.tools_nav.addItem(label)
            self.tools_tabs.addWidget(tool_page)
        self.tools_nav.currentRowChanged.connect(self.tools_tabs.setCurrentIndex)
        self.tools_nav.setCurrentRow(0)
        workspace_layout.addWidget(self.tools_nav)
        workspace_layout.addWidget(self.tools_tabs, 1)
        layout.addWidget(workspace, 1)
        return page

    @staticmethod
    def _game_combo_data(game: SteamGame) -> dict[str, str]:
        return {
            "app_id": str(game.app_id),
            "name": game.name,
            "folder": str(game.library / "steamapps" / "common" / game.install_dir),
        }

    @staticmethod
    def _selected_combo_game(combo: QComboBox) -> dict[str, str] | None:
        selected = combo.currentData()
        return selected if isinstance(selected, dict) else None

    def _build_achievements_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.achievement_status = QLabel("Choose an installed game")
        self.achievement_status.setObjectName("metric")
        detail = QLabel(
            "Manage achievements on the currently signed-in Steam profile. "
            "4u4free never asks for or stores Steam credentials, and it never "
            "changes achievements until you confirm them in the manager."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)

        row = QHBoxLayout()
        self.achievement_game_select = QComboBox()
        self.achievement_game_select.setMinimumWidth(220)
        self.achievement_game_select.currentIndexChanged.connect(
            self._select_achievement_game
        )
        self.achievement_open_button = QPushButton("Open achievement manager")
        self.achievement_open_button.setObjectName("primaryButton")
        self.achievement_open_button.clicked.connect(
            self._confirm_open_achievement_manager
        )
        row.addWidget(self.achievement_game_select, 1)
        row.addWidget(self.achievement_open_button)

        batch_actions = QHBoxLayout()
        self.achievement_batch_button = QPushButton("Review all installed games")
        self.achievement_batch_button.clicked.connect(self._confirm_achievement_batch)
        self.achievement_batch_cancel = QPushButton("Cancel queue")
        self.achievement_batch_cancel.setEnabled(False)
        self.achievement_batch_cancel.clicked.connect(self._cancel_achievement_batch)
        batch_actions.addWidget(self.achievement_batch_button)
        batch_actions.addWidget(self.achievement_batch_cancel)
        batch_actions.addStretch(1)
        self.achievement_batch_status = QLabel(
            "Batch mode opens each game in SAM one at a time for Unlock all + Commit."
        )
        self.achievement_batch_status.setObjectName("muted")
        self.achievement_batch_status.setWordWrap(True)
        self.achievement_batch_timer = QTimer(self)
        self.achievement_batch_timer.setInterval(750)
        self.achievement_batch_timer.timeout.connect(self._poll_achievement_batch)

        provenance = QLabel(
            f"Backend: official open-source Steam Achievement Manager {SAM_VERSION} "
            "by gibbed (zlib license). Protected achievements remain unavailable."
        )
        provenance.setObjectName("muted")
        provenance.setWordWrap(True)

        caution = QLabel(
            "Steam-profile changes can be public and may not be reversible. "
            "Only change achievements on your own account."
        )
        caution.setObjectName("warningText")
        caution.setWordWrap(True)

        layout.addWidget(self.achievement_status)
        layout.addWidget(detail)
        layout.addLayout(row)
        layout.addLayout(batch_actions)
        layout.addWidget(self.achievement_batch_status)
        layout.addWidget(provenance)
        layout.addWidget(caution)
        layout.addStretch(1)
        return tab

    def _populate_achievement_games(self, games: list[SteamGame]) -> None:
        previous = self._selected_combo_game(self.achievement_game_select)
        previous_id = str(previous.get("app_id") or "") if previous else ""
        self.achievement_game_select.blockSignals(True)
        self.achievement_game_select.clear()
        selected_index = 0
        for index, game in enumerate(games):
            self.achievement_game_select.addItem(
                f"{game.name}  ·  {game.app_id}", self._game_combo_data(game)
            )
            if str(game.app_id) == previous_id:
                selected_index = index
        if games:
            self.achievement_game_select.setCurrentIndex(selected_index)
            self.achievement_open_button.setEnabled(True)
            self.achievement_batch_button.setEnabled(
                self._achievement_batch_current is None
                and not self._achievement_batch_queue
            )
        else:
            self.achievement_game_select.addItem("No installed games found", None)
            self.achievement_open_button.setEnabled(False)
            self.achievement_batch_button.setEnabled(False)
        self.achievement_game_select.blockSignals(False)
        self._select_achievement_game(self.achievement_game_select.currentIndex())

    def _select_achievement_game(self, _index: int) -> None:
        game = self._selected_combo_game(self.achievement_game_select)
        if game is None:
            self.achievement_status.setText("Refresh the Steam library to continue")
            return
        self.achievement_status.setText(
            f"{game['name']}  ·  App {game['app_id']}  ·  Steam profile"
        )

    def _confirm_open_achievement_manager(self) -> None:
        game = self._selected_combo_game(self.achievement_game_select)
        if game is None:
            QMessageBox.warning(self, "Achievements", "Choose an installed game first.")
            return
        if (
            QMessageBox.question(
                self,
                "Open achievement manager",
                f"Open the achievement manager for {game['name']}?\n\n"
                "It uses the Steam account currently signed in on this PC. "
                "Review each change there and use its Commit button to write it "
                "to your Steam profile.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            process_id = open_achievement_manager(game["app_id"])
        except FourUFourFreeError as exc:
            self._task_error(str(exc), modal=True)
            return
        message = (
            f"Achievement manager opened for {game['name']} "
            f"(App {game['app_id']}, process {process_id})"
        )
        self.achievement_status.setText(f"Opened for {game['name']}")
        self.log(message)
        self._set_status(message)

    def _set_achievement_batch_active(self, active: bool) -> None:
        has_games = bool(self._installed_games)
        self.achievement_game_select.setEnabled(not active)
        self.achievement_open_button.setEnabled(not active and has_games)
        self.achievement_batch_button.setEnabled(not active and has_games)
        self.achievement_batch_cancel.setEnabled(active)

    def _confirm_achievement_batch(self) -> None:
        games = [
            self._game_combo_data(game)
            for game in self._installed_games
            if str(game.app_id).isdigit() and int(game.app_id) > 0
        ]
        if not games:
            QMessageBox.warning(
                self, "Achievements", "Refresh the Steam library before starting."
            )
            return
        if self._achievement_batch_current is not None or self._achievement_batch_queue:
            return
        if (
            QMessageBox.question(
                self,
                "Review all installed games",
                f"Prepare all {len(games)} installed games for achievement review?\n\n"
                "4u4free will open one SAM window at a time. For each game, review "
                "the list, use Unlock all, then Commit changes and close SAM to "
                "continue. Protected achievements remain unavailable.\n\n"
                "This does not silently mass-write your account; every game keeps "
                "SAM's explicit review and commit step.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        self._achievement_batch_queue = games
        self._achievement_batch_total = len(games)
        self._achievement_batch_completed = 0
        self._set_achievement_batch_active(True)
        self.log(f"Achievement review queue started for {len(games)} installed games")
        self._open_next_achievement_batch_game()

    def _open_next_achievement_batch_game(self) -> None:
        if not self._achievement_batch_queue:
            self.achievement_batch_timer.stop()
            self._achievement_batch_current = None
            self._set_achievement_batch_active(False)
            message = (
                f"Achievement review queue completed: "
                f"{self._achievement_batch_completed}/{self._achievement_batch_total} games"
            )
            self.achievement_batch_status.setText(message)
            self.log(message)
            self._set_status(message)
            QMessageBox.information(self, "Achievement review complete", message)
            return

        game = self._achievement_batch_queue.pop(0)
        position = self._achievement_batch_total - len(self._achievement_batch_queue)
        try:
            process = start_achievement_manager(game["app_id"])
        except FourUFourFreeError as exc:
            self.log(f"Achievement review skipped {game['name']}: {exc}")
            self.achievement_batch_status.setText(f"Skipped {game['name']}: {exc}")
            QTimer.singleShot(0, self._open_next_achievement_batch_game)
            return

        self._achievement_batch_current = process
        self.achievement_batch_status.setText(
            f"Game {position}/{self._achievement_batch_total}: {game['name']}  ·  "
            "Review, use Unlock all + Commit, then close SAM to continue."
        )
        self.log(
            f"Achievement review opened for {game['name']} "
            f"(App {game['app_id']}, process {process.pid})"
        )
        self.achievement_batch_timer.start()

    def _poll_achievement_batch(self) -> None:
        process = self._achievement_batch_current
        if process is None or process.poll() is None:
            return
        self.achievement_batch_timer.stop()
        self._achievement_batch_current = None
        self._achievement_batch_completed += 1
        QTimer.singleShot(150, self._open_next_achievement_batch_game)

    def _cancel_achievement_batch(self) -> None:
        remaining = len(self._achievement_batch_queue)
        self._achievement_batch_queue.clear()
        self.achievement_batch_timer.stop()
        current = self._achievement_batch_current
        self._achievement_batch_current = None
        self._set_achievement_batch_active(False)
        suffix = (
            " The currently open SAM window was left open."
            if current is not None and current.poll() is None
            else ""
        )
        message = (
            f"Achievement review queue canceled; {remaining} games skipped.{suffix}"
        )
        self.achievement_batch_status.setText(message)
        self.log(message)
        self._set_status(message)

    def _build_stats_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        self.stats_status = QLabel("Choose an installed game")
        self.stats_status.setObjectName("metric")
        detail = QLabel(
            f"Open the audited Steam Achievement Manager {SAM_VERSION} Statistics tab "
            "for a game. Enable stats editing there, change supported integer or float "
            "values, then review and Commit Changes. Server-protected stats stay read-only."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        row = QHBoxLayout()
        self.stats_game_select = QComboBox()
        self.stats_game_select.setMinimumWidth(220)
        self.stats_game_select.currentIndexChanged.connect(self._select_stats_game)
        self.stats_open_button = QPushButton("Open advanced stat editor")
        self.stats_open_button.setObjectName("primaryButton")
        self.stats_open_button.clicked.connect(self._confirm_open_stats)
        row.addWidget(self.stats_game_select, 1)
        row.addWidget(self.stats_open_button)
        warning = QLabel(
            "Steam account stats can affect progression and achievements. Changes are "
            "written only after the manager's explicit Commit Changes action."
        )
        warning.setObjectName("warningText")
        warning.setWordWrap(True)
        layout.addWidget(self.stats_status)
        layout.addWidget(detail)
        layout.addLayout(row)
        layout.addWidget(warning)
        layout.addStretch(1)
        return tab

    def _populate_stats_games(self, games: list[SteamGame]) -> None:
        previous = self._selected_combo_game(self.stats_game_select)
        previous_id = str(previous.get("app_id") or "") if previous else ""
        self.stats_game_select.blockSignals(True)
        self.stats_game_select.clear()
        selected_index = 0
        for index, game in enumerate(games):
            self.stats_game_select.addItem(
                f"{game.name}  ·  {game.app_id}", self._game_combo_data(game)
            )
            if str(game.app_id) == previous_id:
                selected_index = index
        if games:
            self.stats_game_select.setCurrentIndex(selected_index)
            self.stats_open_button.setEnabled(True)
        else:
            self.stats_game_select.addItem("No installed games found", None)
            self.stats_open_button.setEnabled(False)
        self.stats_game_select.blockSignals(False)
        self._select_stats_game(self.stats_game_select.currentIndex())

    def _select_stats_game(self, _index: int) -> None:
        game = self._selected_combo_game(self.stats_game_select)
        self.stats_status.setText(
            f"{game['name']}  ·  App {game['app_id']}  ·  Ready"
            if game
            else "Refresh the Steam library to continue"
        )

    def _confirm_open_stats(self) -> None:
        game = self._selected_combo_game(self.stats_game_select)
        if game is None:
            QMessageBox.warning(self, "Stats", "Choose an installed game first.")
            return
        if (
            QMessageBox.question(
                self,
                "Open advanced stat editor",
                f"Open the stat editor for {game['name']} (App {game['app_id']})?\n\n"
                "In the manager, open Statistics, enable stats editing, review each "
                "value, then use Commit Changes. Protected stats cannot be changed.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            process_id = open_achievement_manager(game["app_id"])
        except FourUFourFreeError as exc:
            self._task_error(str(exc), modal=True)
            return
        message = (
            f"Advanced stat editor opened for {game['name']} (process {process_id})"
        )
        self.stats_status.setText(f"Opened for {game['name']}")
        self.log(message)
        self._set_status(message)

    def _build_showcase_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        detail = QLabel(
            "Ranks your publicly visible unlocked achievements by global rarity. "
            "The scan reads Steam Community data only; it does not change the profile."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        controls = QHBoxLayout()
        self.showcase_game_select = QComboBox()
        self.showcase_game_select.setMinimumWidth(220)
        self.showcase_analyze = QPushButton("Find rarest unlocked")
        self.showcase_analyze.setObjectName("primaryButton")
        self.showcase_analyze.clicked.connect(self._analyze_showcase)
        edit = QPushButton("Open Steam showcase editor")
        edit.clicked.connect(self._open_showcase_editor)
        controls.addWidget(self.showcase_game_select, 1)
        controls.addWidget(self.showcase_analyze)
        self.showcase_status = QLabel(
            "Game details and achievements must be visible on your Steam profile"
        )
        self.showcase_status.setObjectName("muted")
        self.showcase_table = DataTable(
            0,
            4,
            "Choose a game to rank your publicly visible unlocked achievements by rarity.",
        )
        self.showcase_table.setHorizontalHeaderLabels(
            ["Global rarity", "Achievement", "Game", "Unlocked"]
        )
        self.showcase_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.showcase_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.showcase_table.verticalHeader().hide()
        header = self.showcase_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(detail)
        layout.addLayout(controls)
        edit_row = QHBoxLayout()
        edit_row.addStretch(1)
        edit_row.addWidget(edit)
        layout.addLayout(edit_row)
        layout.addWidget(self.showcase_status)
        layout.addWidget(self.showcase_table, 1)
        return tab

    def _populate_showcase_games(self, games: list[SteamGame]) -> None:
        previous = self._selected_combo_game(self.showcase_game_select)
        previous_id = str(previous.get("app_id") or "") if previous else ""
        self.showcase_game_select.clear()
        selected_index = 0
        for index, game in enumerate(games):
            self.showcase_game_select.addItem(
                f"{game.name}  ·  {game.app_id}", self._game_combo_data(game)
            )
            if str(game.app_id) == previous_id:
                selected_index = index
        if games:
            self.showcase_game_select.setCurrentIndex(selected_index)
            self.showcase_analyze.setEnabled(True)
        else:
            self.showcase_game_select.addItem("No installed games found", None)
            self.showcase_analyze.setEnabled(False)

    def _analyze_showcase(self) -> None:
        game = self._selected_combo_game(self.showcase_game_select)
        if game is None:
            QMessageBox.warning(self, "Showcase", "Choose an installed game first.")
            return

        def task():
            profiles = [
                profile
                for profile in list_profiles(self._steam_root())
                if profile.steam_id64
            ]
            if not profiles:
                raise FourUFourFreeError(
                    "No signed-in Steam profile was found. Sign in to Steam and retry."
                )
            profile = next((item for item in profiles if item.most_recent), profiles[0])
            return profile, recommend_for_game(
                profile.steam_id64, game["app_id"], game["name"]
            )

        def done(result):
            profile, achievements = result
            self._showcase_results = list(achievements)
            self.showcase_table.setRowCount(len(achievements))
            for row, achievement in enumerate(achievements):
                self.showcase_table.setItem(
                    row, 0, QTableWidgetItem(f"{achievement.global_percent:.2f}%")
                )
                name = QTableWidgetItem(achievement.name)
                name.setToolTip(achievement.description)
                self.showcase_table.setItem(row, 1, name)
                self.showcase_table.setItem(
                    row, 2, QTableWidgetItem(achievement.game_name)
                )
                unlocked = (
                    time.strftime(
                        "%Y-%m-%d", time.localtime(achievement.unlock_timestamp)
                    )
                    if achievement.unlock_timestamp
                    else "—"
                )
                self.showcase_table.setItem(row, 3, QTableWidgetItem(unlocked))
            persona = profile.persona_name or profile.account_name or profile.steam_id64
            self.showcase_status.setText(
                f"{len(achievements)} unlocked achievements ranked for {persona}; "
                "the top rows are the rarest."
            )
            self.log(
                f"Achievement showcase: ranked {len(achievements)} entries for {game['name']}"
            )

        self.run_task(task, done, label=f"Ranking achievements for {game['name']}")

    def _open_showcase_editor(self) -> None:
        QDesktopServices.openUrl(QUrl("https://steamcommunity.com/my/edit/showcases"))
        self.log("Opened the Steam showcase editor")

    def _build_save_vault_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        detail = QLabel(
            "Create versioned, SHA-256 verified ZIP snapshots of a game's save folder. "
            "Restore always creates a safety snapshot of the current destination first."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        game_row = QHBoxLayout()
        self.vault_game_select = QComboBox()
        self.vault_game_select.currentIndexChanged.connect(self._select_vault_game)
        self.vault_detect = QPushButton("Detect save folder")
        self.vault_detect.clicked.connect(self._detect_vault_source)
        game_row.addWidget(self.vault_game_select, 1)
        game_row.addWidget(self.vault_detect)
        source_row = QHBoxLayout()
        self.vault_source = QLineEdit()
        self.vault_source.setPlaceholderText("Select the folder containing save files")
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda: self._pick_directory(self.vault_source))
        snapshot = QPushButton("Create snapshot")
        snapshot.setObjectName("primaryButton")
        snapshot.clicked.connect(self._confirm_create_vault_snapshot)
        source_row.addWidget(self.vault_source, 1)
        source_row.addWidget(browse)
        source_row.addWidget(snapshot)
        self.vault_status = QLabel("Choose an installed game and its save folder")
        self.vault_status.setObjectName("muted")
        self.vault_table = DataTable(
            0,
            5,
            "No save snapshots yet. Choose a save folder and create the first snapshot.",
        )
        self.vault_table.setHorizontalHeaderLabels(
            ["Created", "Files", "Size", "Reason", "Source"]
        )
        self.vault_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.vault_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.vault_table.verticalHeader().hide()
        header = self.vault_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        actions = QHBoxLayout()
        restore = QPushButton("Restore selected")
        restore.clicked.connect(self._confirm_restore_vault_snapshot)
        open_folder = QPushButton("Open vault folder")
        open_folder.clicked.connect(self._open_vault_folder)
        actions.addWidget(restore)
        actions.addWidget(open_folder)
        actions.addStretch(1)
        layout.addWidget(detail)
        layout.addLayout(game_row)
        layout.addLayout(source_row)
        layout.addWidget(self.vault_status)
        layout.addWidget(self.vault_table, 1)
        layout.addLayout(actions)
        return tab

    def _vault_service(self) -> SaveVault:
        return SaveVault(self.preferences.save_vault_root)

    def _populate_save_vault_games(self, games: list[SteamGame]) -> None:
        previous = self._selected_combo_game(self.vault_game_select)
        previous_id = str(previous.get("app_id") or "") if previous else ""
        self.vault_game_select.blockSignals(True)
        self.vault_game_select.clear()
        selected_index = 0
        for index, game in enumerate(games):
            self.vault_game_select.addItem(
                f"{game.name}  ·  {game.app_id}", self._game_combo_data(game)
            )
            if str(game.app_id) == previous_id:
                selected_index = index
        if games:
            self.vault_game_select.setCurrentIndex(selected_index)
        else:
            self.vault_game_select.addItem("No installed games found", None)
        self.vault_game_select.blockSignals(False)
        self._select_vault_game(self.vault_game_select.currentIndex())

    def _select_vault_game(self, _index: int) -> None:
        game = self._selected_combo_game(self.vault_game_select)
        if game is None:
            self.vault_source.clear()
            self.vault_table.setRowCount(0)
            return
        saved = self.preferences.save_vault_sources.get(game["app_id"], "")
        if saved:
            self.vault_source.setText(saved)
        else:
            self._detect_vault_source(quiet=True)
        self._refresh_vault_snapshots()

    def _detect_vault_source(
        self, _checked: bool = False, *, quiet: bool = False
    ) -> None:
        game = self._selected_combo_game(self.vault_game_select)
        if game is None:
            if not quiet:
                QMessageBox.warning(
                    self, "Save Vault", "Choose an installed game first."
                )
            return
        try:
            steam_root = self._steam_root()
        except FourUFourFreeError:
            steam_root = None
        candidates = discover_save_folders(
            game["app_id"], game["name"], steam_root=steam_root
        )
        if candidates:
            self.vault_source.setText(str(candidates[0]))
            self.vault_status.setText(
                f"Detected {len(candidates)} candidate folder(s); review before snapshotting"
            )
        elif not quiet:
            QMessageBox.information(
                self,
                "Save Vault",
                "No existing save folder was detected automatically. Use Browse to select it.",
            )

    def _refresh_vault_snapshots(self) -> None:
        game = self._selected_combo_game(self.vault_game_select)
        if game is None:
            return
        self._vault_snapshots = self._vault_service().list_snapshots(game["app_id"])
        self.vault_table.setRowCount(len(self._vault_snapshots))
        for row, snapshot in enumerate(self._vault_snapshots):
            created = QTableWidgetItem(snapshot.created_at.replace("T", " ")[:19])
            created.setData(Qt.ItemDataRole.UserRole, snapshot)
            self.vault_table.setItem(row, 0, created)
            self.vault_table.setItem(row, 1, QTableWidgetItem(str(snapshot.file_count)))
            self.vault_table.setItem(
                row, 2, QTableWidgetItem(format_bytes(snapshot.total_size))
            )
            self.vault_table.setItem(row, 3, QTableWidgetItem(snapshot.reason))
            self.vault_table.setItem(row, 4, QTableWidgetItem(snapshot.source_path))
        self.vault_status.setText(
            f"{len(self._vault_snapshots)} snapshot(s) for {game['name']}"
        )

    def _confirm_create_vault_snapshot(self) -> None:
        game = self._selected_combo_game(self.vault_game_select)
        source = self.vault_source.text().strip().strip('"')
        if game is None or not source:
            QMessageBox.warning(
                self,
                "Save Vault",
                "Choose a game and the folder containing its save files.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Create save snapshot",
                f"Snapshot {game['name']} save files from:\n{source}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def done(snapshot: VaultSnapshot):
            self.preferences.save_vault_sources[game["app_id"]] = source
            self.store.save(self.preferences)
            self._refresh_vault_snapshots()
            message = (
                f"Save Vault created {snapshot.snapshot_id}: "
                f"{snapshot.file_count} files, {format_bytes(snapshot.total_size)}"
            )
            self.log(message)
            self._set_status(message)

        self.run_task(
            lambda: self._vault_service().create_snapshot(
                game["app_id"], game["name"], source
            ),
            done,
            label=f"Snapshotting saves for {game['name']}",
        )

    def _confirm_restore_vault_snapshot(self) -> None:
        row = self.vault_table.currentRow()
        item = self.vault_table.item(row, 0) if row >= 0 else None
        snapshot = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(snapshot, VaultSnapshot):
            QMessageBox.warning(self, "Save Vault", "Select a snapshot first.")
            return
        destination = (
            self.vault_source.text().strip().strip('"') or snapshot.source_path
        )
        if (
            QMessageBox.question(
                self,
                "Restore save snapshot",
                f"Restore {snapshot.game_name} snapshot to:\n{destination}?\n\n"
                "Current destination files will be snapshotted first, then archived "
                "files will be overlaid.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def done(result):
            self._refresh_vault_snapshots()
            message = (
                f"Restored {result.restored_files} save files to {result.destination}"
            )
            self.log(message)
            self._set_status(message)
            QMessageBox.information(self, "Save Vault restored", message)

        self.run_task(
            lambda: self._vault_service().restore_snapshot(snapshot, destination),
            done,
            label=f"Restoring saves for {snapshot.game_name}",
        )

    def _open_vault_folder(self) -> None:
        root = self._vault_service().root
        root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))

    def _build_playtime_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.playtime_status = QLabel("Choose an installed game")
        self.playtime_status.setObjectName("metric")
        detail = QLabel(
            "Launch an installed game through Steam and track a real-time session. "
            "Steam owns the account record: 4u4free does not edit or backdate "
            "server-side playtime. Adding 10 hours takes 10 real hours."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)

        method_row = QHBoxLayout()
        method_label = QLabel("Method")
        method_label.setObjectName("muted")
        self.playtime_method = QComboBox()
        self.playtime_method.addItem("Launch game (normal Steam session)", "launch")
        self.playtime_method.addItem("Headless idle (no game window)", "headless")
        self.playtime_method.currentIndexChanged.connect(self._select_playtime_method)
        self.playtime_method_detail = QLabel("")
        self.playtime_method_detail.setObjectName("muted")
        self.playtime_method_detail.setWordWrap(True)
        method_row.addWidget(method_label)
        method_row.addWidget(self.playtime_method, 1)

        game_row = QHBoxLayout()
        self.playtime_game_select = QComboBox()
        self.playtime_game_select.setMinimumWidth(220)
        self.playtime_game_select.currentIndexChanged.connect(
            self._select_playtime_game
        )
        game_row.addWidget(self.playtime_game_select, 1)
        privacy = QPushButton("Steam visibility settings")
        privacy.clicked.connect(self._open_playtime_privacy_settings)
        game_row.addWidget(privacy)

        duration_row = QHBoxLayout()
        duration_row.setSpacing(8)
        duration_label = QLabel("Session goal")
        duration_label.setObjectName("muted")
        self.playtime_hours = QSpinBox()
        self.playtime_hours.setRange(0, 720)
        self.playtime_hours.setValue(1)
        self.playtime_hours.setSuffix(" hours")
        self.playtime_minutes = QSpinBox()
        self.playtime_minutes.setRange(0, 59)
        self.playtime_minutes.setSuffix(" minutes")
        self.playtime_start_button = QPushButton("Launch and start tracking")
        self.playtime_start_button.setObjectName("primaryButton")
        self.playtime_start_button.clicked.connect(self._confirm_start_playtime_session)
        self.playtime_stop_button = QPushButton("Stop session")
        self.playtime_stop_button.setEnabled(False)
        self.playtime_stop_button.clicked.connect(self._stop_playtime_tracking)
        duration_row.addWidget(duration_label)
        duration_row.addWidget(self.playtime_hours)
        duration_row.addWidget(self.playtime_minutes)
        duration_row.addStretch(1)
        duration_row.addWidget(self.playtime_start_button)
        duration_row.addWidget(self.playtime_stop_button)

        self.playtime_progress = QProgressBar()
        self.playtime_progress.setRange(0, 1000)
        self.playtime_progress.setValue(0)
        self.playtime_progress.setTextVisible(False)
        self.playtime_remaining = QLabel("No local session is being tracked")
        self.playtime_remaining.setObjectName("muted")

        caution = QLabel(
            "Normal mode requires the game to remain running. Headless mode holds a "
            "SteamAPI presence without starting the game and requires a valid license. "
            "Both methods accrue time in real time; neither can jump the server clock.\n\n"
            "For other people to see the hours, Steam Game details must be Public "
            "(anyone) or Friends Only, and 'Always keep my total playtime private' "
            "must be unchecked. 4u4free never changes profile privacy."
        )
        caution.setObjectName("warningText")
        caution.setWordWrap(True)

        self.playtime_timer = QTimer(self)
        self.playtime_timer.setInterval(1000)
        self.playtime_timer.timeout.connect(self._update_playtime_session)

        layout.addWidget(self.playtime_status)
        layout.addWidget(detail)
        layout.addLayout(game_row)
        layout.addLayout(method_row)
        layout.addWidget(self.playtime_method_detail)
        layout.addLayout(duration_row)
        layout.addWidget(self.playtime_progress)
        layout.addWidget(self.playtime_remaining)
        layout.addWidget(caution)
        layout.addStretch(1)
        self._select_playtime_method(self.playtime_method.currentIndex())
        return tab

    def _open_playtime_privacy_settings(self) -> None:
        QDesktopServices.openUrl(QUrl(STEAM_PRIVACY_URL))
        self.log("Opened Steam profile privacy settings")

    def _select_playtime_method(self, _index: int) -> None:
        mode = str(self.playtime_method.currentData() or "launch")
        if mode == "headless":
            self.playtime_method_detail.setText(
                "Runs the bundled 4u4free helper against the signed-in Steam client. "
                "No credentials, game files, achievements, stats, or saves are touched. "
                "The helper closes automatically at the goal or when 4u4free exits."
            )
        else:
            self.playtime_method_detail.setText(
                "Asks Steam to launch the actual game. At the goal, 4u4free alerts you "
                "and leaves the game open so it can be closed normally."
            )

    def _populate_playtime_games(self, games: list[SteamGame]) -> None:
        previous = self._selected_combo_game(self.playtime_game_select)
        previous_id = str(previous.get("app_id") or "") if previous else ""
        self.playtime_game_select.blockSignals(True)
        self.playtime_game_select.clear()
        selected_index = 0
        for index, game in enumerate(games):
            self.playtime_game_select.addItem(
                f"{game.name}  ·  {game.app_id}", self._game_combo_data(game)
            )
            if str(game.app_id) == previous_id:
                selected_index = index
        if games:
            self.playtime_game_select.setCurrentIndex(selected_index)
            self.playtime_start_button.setEnabled(self._playtime_session is None)
        else:
            self.playtime_game_select.addItem("No installed games found", None)
            self.playtime_start_button.setEnabled(False)
        self.playtime_game_select.blockSignals(False)
        self._select_playtime_game(self.playtime_game_select.currentIndex())

    def _select_playtime_game(self, _index: int) -> None:
        if self._playtime_session is not None:
            return
        game = self._selected_combo_game(self.playtime_game_select)
        if game is None:
            self.playtime_status.setText("Refresh the Steam library to continue")
            return
        self.playtime_status.setText(
            f"{game['name']}  ·  App {game['app_id']}  ·  Ready"
        )

    def _set_playtime_controls_active(self, active: bool) -> None:
        self.playtime_game_select.setEnabled(not active)
        self.playtime_method.setEnabled(not active)
        self.playtime_hours.setEnabled(not active)
        self.playtime_minutes.setEnabled(not active)
        has_game = self._selected_combo_game(self.playtime_game_select) is not None
        self.playtime_start_button.setEnabled(not active and has_game)
        self.playtime_stop_button.setEnabled(active)

    def _confirm_start_playtime_session(self) -> None:
        game = self._selected_combo_game(self.playtime_game_select)
        if game is None:
            QMessageBox.warning(self, "Playtime", "Choose an installed game first.")
            return
        if self._playtime_session is not None:
            QMessageBox.information(
                self, "Playtime", "Stop the current tracking session first."
            )
            return
        try:
            candidate = PlaytimeSession.create(
                game["app_id"],
                game["name"],
                self.playtime_hours.value(),
                self.playtime_minutes.value(),
                now=0,
            )
        except FourUFourFreeError as exc:
            self._task_error(str(exc), modal=True)
            return

        duration = format_duration(candidate.duration_seconds)
        mode = str(self.playtime_method.currentData() or "launch")
        if mode == "headless":
            action = "start a headless SteamAPI presence"
            method_note = (
                "The game will not open. The signed-in account must own a valid license, "
                "and the helper will stop automatically at the goal."
            )
        else:
            action = f"launch {game['name']} through Steam"
            method_note = "4u4free will not automatically close the game."
        if (
            QMessageBox.question(
                self,
                "Start playtime session",
                f"For {game['name']}, {action} and track it for {duration}?\n\n"
                "This starts a real-time Steam presence. It cannot set an arbitrary past "
                "total, and Steam alone decides when the account playtime refreshes.\n\n"
                "Visibility to friends or the public depends on Steam's Game details "
                f"privacy setting. {method_note}",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            if mode == "headless":
                self._playtime_idler_process = start_headless_idle(game["app_id"])
            else:
                start_steam_game(game["app_id"])
            self._playtime_session = PlaytimeSession.create(
                game["app_id"],
                game["name"],
                self.playtime_hours.value(),
                self.playtime_minutes.value(),
            )
            self._playtime_session_mode = mode
        except FourUFourFreeError as exc:
            self._playtime_idler_process = None
            self._task_error(str(exc), modal=True)
            return

        self._set_playtime_controls_active(True)
        self.playtime_timer.start()
        self._update_playtime_session()
        message = (
            f"{'Headless playtime' if mode == 'headless' else 'Playtime'} session "
            f"started for {game['name']} "
            f"(App {game['app_id']}, goal {duration})"
        )
        self.log(message)
        self._set_status(message)

    def _update_playtime_session(self) -> None:
        session = self._playtime_session
        if session is None:
            return
        if (
            self._playtime_session_mode == "headless"
            and self._playtime_idler_process is not None
            and self._playtime_idler_process.poll() is not None
        ):
            self.playtime_timer.stop()
            self._playtime_session = None
            self._playtime_idler_process = None
            self._set_playtime_controls_active(False)
            message = f"Headless Steam session ended early for {session.game_name}"
            self.playtime_status.setText(message)
            self.playtime_remaining.setText(
                "Steam closed the helper before the requested goal. No local metadata was edited."
            )
            self.log(message)
            self._set_status(message)
            return
        elapsed, remaining, progress = session.snapshot()
        self.playtime_progress.setValue(round(progress * 1000))
        verb = (
            "Headless idling"
            if self._playtime_session_mode == "headless"
            else "Tracking"
        )
        self.playtime_status.setText(
            f"{verb} {session.game_name}  ·  App {session.app_id}"
        )
        self.playtime_remaining.setText(
            f"Elapsed {format_duration(elapsed)}  ·  Remaining {format_duration(remaining)}"
        )
        if remaining > 0:
            return

        self.playtime_timer.stop()
        was_headless = self._playtime_session_mode == "headless"
        if was_headless and self._playtime_idler_process is not None:
            stop_headless_idle(self._playtime_idler_process)
        self._playtime_idler_process = None
        self._playtime_session = None
        self._set_playtime_controls_active(False)
        self.playtime_status.setText(f"Goal reached for {session.game_name}")
        completion = (
            "The headless helper stopped automatically."
            if was_headless
            else "The game remains open."
        )
        self.playtime_remaining.setText(
            f"Tracked {format_duration(session.duration_seconds)}. {completion}"
        )
        message = (
            f"Playtime goal reached for {session.game_name} (App {session.app_id})"
        )
        self.log(message)
        self._set_status(message)
        QMessageBox.information(
            self,
            "Playtime goal reached",
            f"The {format_duration(session.duration_seconds)} tracking goal for "
            f"{session.game_name} is complete.\n\n{completion}",
        )

    def _stop_playtime_tracking(self) -> None:
        session = self._playtime_session
        if session is None:
            return
        elapsed, _remaining, progress = session.snapshot()
        self.playtime_timer.stop()
        was_headless = self._playtime_session_mode == "headless"
        if was_headless and self._playtime_idler_process is not None:
            stop_headless_idle(self._playtime_idler_process)
        self._playtime_idler_process = None
        self._playtime_session = None
        self._set_playtime_controls_active(False)
        self.playtime_progress.setValue(round(progress * 1000))
        self.playtime_status.setText(f"Tracking stopped for {session.game_name}")
        completion = (
            "Headless helper stopped." if was_headless else "The game remains open."
        )
        self.playtime_remaining.setText(
            f"Tracked locally for {format_duration(elapsed)}. {completion}"
        )
        message = (
            f"Playtime tracking stopped for {session.game_name} after "
            f"{format_duration(elapsed)}; {completion.lower()}"
        )
        self.log(message)
        self._set_status(message)

    def _build_online_fix_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.online_fix_status = QLabel("Choose an installed game")
        self.online_fix_status.setObjectName("metric")
        detail = QLabel(
            "LC Online Fix preserves the game's existing Steam launch options and "
            "toggles only -onlinefix. LumaCore redirects compatible launches through "
            "Spacewar (App 480); support still depends on the game and its network code."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)

        selection = QHBoxLayout()
        self.online_fix_game_select = QComboBox()
        self.online_fix_game_select.setMinimumWidth(220)
        self.online_fix_game_select.currentIndexChanged.connect(
            self._select_online_fix_game
        )
        selection.addWidget(self.online_fix_game_select, 1)

        actions = QHBoxLayout()
        refresh = QPushButton("Refresh status")
        refresh.clicked.connect(self._refresh_online_fix_status)
        self.online_fix_toggle = QPushButton("Enable online fix")
        self.online_fix_toggle.setObjectName("primaryButton")
        self.online_fix_toggle.clicked.connect(self._confirm_toggle_online_fix)
        self.online_fix_guide = QPushButton("Open game-specific setup")
        self.online_fix_guide.clicked.connect(self._open_online_fix_guide)
        self.online_fix_guide.hide()
        actions.addWidget(refresh)
        actions.addWidget(self.online_fix_toggle)
        actions.addWidget(self.online_fix_guide)
        actions.addStretch(1)

        self.online_fix_detail = QLabel(
            "Before every change, 4u4free creates localconfig.vdf.4u4free.bak "
            "and verifies the resulting flag."
        )
        self.online_fix_detail.setObjectName("muted")
        self.online_fix_detail.setWordWrap(True)

        layout.addWidget(self.online_fix_status)
        layout.addWidget(detail)
        layout.addLayout(selection)
        layout.addLayout(actions)
        layout.addWidget(self.online_fix_detail)
        layout.addStretch(1)
        return tab

    def _populate_online_fix_games(self, games: list[SteamGame]) -> None:
        previous = self._selected_combo_game(self.online_fix_game_select)
        previous_id = str(previous.get("app_id") or "") if previous else ""
        self.online_fix_game_select.blockSignals(True)
        self.online_fix_game_select.clear()
        selected_index = 0
        for index, game in enumerate(games):
            self.online_fix_game_select.addItem(
                f"{game.name}  ·  {game.app_id}", self._game_combo_data(game)
            )
            if str(game.app_id) == previous_id:
                selected_index = index
        if games:
            self.online_fix_game_select.setCurrentIndex(selected_index)
            self.online_fix_toggle.setEnabled(True)
        else:
            self.online_fix_game_select.addItem("No installed games found", None)
            self.online_fix_toggle.setEnabled(False)
        self.online_fix_game_select.blockSignals(False)
        self._select_online_fix_game(self.online_fix_game_select.currentIndex())

    def _select_online_fix_game(self, _index: int) -> None:
        game = self._selected_combo_game(self.online_fix_game_select)
        if game is None:
            self.online_fix_status.setText("Refresh the Steam library to continue")
            self.online_fix_guide.hide()
            return
        profile = online_compatibility(game["app_id"])
        self._online_fix_profile = profile
        self._online_fix_probe = None
        self.online_fix_guide.setVisible(bool(profile.guide_url))
        if profile.guide_url:
            self.online_fix_guide.setText(f"Open {profile.provider} setup")
        self.online_fix_status.setText(f"Checking {game['name']}")
        self._refresh_online_fix_status()

    def _open_online_fix_guide(self) -> None:
        profile = getattr(self, "_online_fix_profile", None)
        if not isinstance(profile, OnlineCompatibility) or not profile.guide_url:
            return
        QDesktopServices.openUrl(QUrl(profile.guide_url))
        self.log(f"Opened {profile.provider} compatibility guide")

    def _refresh_online_fix_status(self, _checked: bool = False) -> None:
        game = self._selected_combo_game(self.online_fix_game_select)
        if game is None:
            return

        def task():
            self._require_compat()
            steam = self._steam_root()
            enabled = online_fix_enabled(steam, game["app_id"])
            version = get_installed_lumacore_version(steam)
            backup = launch_options_backup_path(steam)
            profile = online_compatibility(game["app_id"])
            probe = (
                None
                if not profile.generic_supported
                else probe_online_compatibility(Path(game["folder"]))
            )
            return enabled, version, backup, profile, probe

        def done(result):
            enabled, version, backup, profile, probe = result
            self._online_fix_profile = profile
            self._online_fix_probe = probe
            self.online_fix_guide.setVisible(bool(profile.guide_url))
            if not profile.generic_supported:
                provider = f" · Use {profile.provider}" if profile.provider else ""
                state = (
                    "Remove incompatible generic flag" if enabled else profile.status
                )
                self.online_fix_status.setText(f"{state}{provider}")
                self.online_fix_toggle.setText(
                    "Remove generic online-fix flag"
                    if enabled
                    else "Generic fix not compatible"
                )
                self.online_fix_toggle.setEnabled(enabled)
                self.online_fix_detail.setText(profile.detail)
                return
            if not isinstance(probe, OnlineProbe):
                self.online_fix_status.setText("Compatibility scan unavailable")
                self.online_fix_toggle.setEnabled(enabled)
                return
            state = "Enabled" if enabled else "Disabled"
            readiness = f"LumaCore {version}" if version else "LumaCore not installed"
            self.online_fix_status.setText(
                f"{probe.status}  ·  {state}  ·  {game['name']}  ·  {readiness}"
            )
            self.online_fix_toggle.setText(
                "Disable online fix" if enabled else "Enable online fix"
            )
            # Always allow cleanup of an already-enabled flag, even if
            # LumaCore was removed after it was configured.
            self.online_fix_toggle.setEnabled(
                enabled or (bool(version) and probe.allow_generic)
            )
            evidence = (
                "\nEvidence: " + "; ".join(probe.evidence) if probe.evidence else ""
            )
            if backup:
                self.online_fix_detail.setText(
                    f"{probe.detail}{evidence}\n\nSafety backup: {backup}. "
                    "Existing launch options are preserved."
                )

        self.run_task(
            task,
            done,
            label=f"Checking online fix for App {game['app_id']}",
            error_modal=False,
        )

    def _confirm_toggle_online_fix(self) -> None:
        game = self._selected_combo_game(self.online_fix_game_select)
        if game is None:
            QMessageBox.warning(self, "Online Fix", "Choose an installed game first.")
            return
        try:
            self._require_compat()
            steam = self._steam_root()
            enabled = online_fix_enabled(steam, game["app_id"])
            version = get_installed_lumacore_version(steam)
            profile = online_compatibility(game["app_id"])
        except FourUFourFreeError as exc:
            self._task_error(str(exc), modal=True)
            return
        if not profile.generic_supported and not enabled:
            QMessageBox.information(
                self,
                "Game-specific online support",
                f"The generic LC Online Fix is not suitable for {game['name']}.\n\n"
                f"{profile.detail}\n\nUse the Open {profile.provider} setup button instead.",
            )
            return
        probe = getattr(self, "_online_fix_probe", None)
        if (
            profile.generic_supported
            and not enabled
            and (not isinstance(probe, OnlineProbe) or not probe.allow_generic)
        ):
            detail = (
                probe.detail
                if isinstance(probe, OnlineProbe)
                else "Run Refresh status and wait for the compatibility scan."
            )
            QMessageBox.information(
                self,
                "Online compatibility check",
                f"The generic LC Online Fix is not enabled for this game.\n\n{detail}",
            )
            return
        if not version and not enabled:
            QMessageBox.warning(
                self,
                "Online Fix",
                "Install LumaCore from the LumaCore tab before enabling LC Online Fix.",
            )
            return

        action = "disable" if enabled else "enable"
        was_running = bool(is_proc_running("steam.exe"))
        steam_note = (
            "\n\nSteam is running. 4u4free will ask it to close, make the "
            "verified change, then start Steam again. Active downloads will pause."
            if was_running
            else "\n\nSteam is already closed and will remain closed after the change."
        )
        if (
            QMessageBox.question(
                self,
                f"{action.title()} LC Online Fix",
                f"{action.title()} LC Online Fix for {game['name']} "
                f"(App {game['app_id']})?\n\nExisting launch options will be preserved "
                "and localconfig.vdf will be backed up."
                f"{steam_note}",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def task():
            steam_exe = steam / "steam.exe"
            if was_running:
                subprocess.run(
                    [str(steam_exe), "-shutdown"],
                    cwd=str(steam),
                    capture_output=True,
                    timeout=10,
                )
                deadline = time.monotonic() + 20
                while is_proc_running("steam.exe") and time.monotonic() < deadline:
                    time.sleep(0.25)
                if is_proc_running("steam.exe"):
                    raise FourUFourFreeError(
                        "Steam did not close in time. Close it manually, then try again."
                    )

            ok, message = toggle_online_fix(steam, game["app_id"])
            if not ok:
                raise FourUFourFreeError(message)

            restart_message = ""
            if was_running:
                restarted, restart_message = launch_steam_unelevated(steam_exe, steam)
                if not restarted:
                    restart_message = (
                        f" Steam was not restarted automatically: {restart_message}"
                    )
                else:
                    restart_message = " Steam was restarted."
            return f"{message}{restart_message}"

        def done(message):
            self.log(message)
            self._set_status(message)
            self._refresh_online_fix_status()
            backup = launch_options_backup_path(steam)
            backup_note = f"\n\nBackup: {backup}" if backup else ""
            QMessageBox.information(
                self, "Online Fix updated", f"{message}{backup_note}"
            )

        self.run_task(
            task,
            done,
            label=f"Updating online fix for App {game['app_id']}",
        )

    def _build_lumacore_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        self.lumacore_status = QLabel("Checking status")
        self.lumacore_status.setObjectName("metric")
        detail = QLabel(
            "Maintains the local Steam integration used for library registration and native downloads."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        actions = QHBoxLayout()
        refresh = QPushButton("Refresh status")
        refresh.clicked.connect(self._refresh_lumacore)
        install = QPushButton("Install or update")
        install.setObjectName("primaryButton")
        install.clicked.connect(self._confirm_lumacore_install)
        remove = QPushButton("Remove")
        remove.setObjectName("dangerButton")
        remove.clicked.connect(self._confirm_lumacore_remove)
        actions.addWidget(refresh)
        actions.addWidget(install)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addWidget(self.lumacore_status)
        layout.addWidget(detail)
        layout.addLayout(actions)
        layout.addStretch(1)
        return tab

    def _refresh_lumacore(self, _checked: bool = False, *, quiet: bool = False) -> None:
        def task():
            self._require_compat()
            return get_installed_lumacore_version(self._steam_root())

        def done(version):
            text = f"Installed · {version}" if version else "Not installed"
            self.lumacore_status.setText(text)
            self.home_core_status.setText(text)
            if not quiet:
                self.log(f"LumaCore: {text}")

        self.run_task(task, done, label="Checking LumaCore", error_modal=not quiet)

    def _confirm_lumacore_install(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Install LumaCore",
                "Install or update LumaCore? Steam will be closed automatically.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        steam = self._steam_root()

        def task():
            return install_lumacore(steam, progress_callback=self.log)

        def done(result):
            ok, message = result
            self.log(message)
            if ok:
                self._refresh_lumacore()

        self.run_task(task, done, label="Installing LumaCore")

    def _confirm_lumacore_remove(self) -> None:
        if (
            QMessageBox.question(
                self, "Remove LumaCore", "Remove LumaCore from the Steam folder?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        steam = self._steam_root()

        def done(result):
            _ok, message = result
            self.log(message)
            self._refresh_lumacore()

        self.run_task(
            lambda: deactivate_lumacore(steam, progress_callback=self.log),
            done,
            label="Removing LumaCore",
        )

    def _build_steamstub_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        detail = QLabel(
            "Inspect a game folder, preview protected executables, or restore existing backups."
        )
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        path_row = QHBoxLayout()
        self.stub_folder = QLineEdit()
        self.stub_folder.setPlaceholderText("Game folder")
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda: self._pick_directory(self.stub_folder))
        path_row.addWidget(self.stub_folder, 1)
        path_row.addWidget(browse)
        actions = QHBoxLayout()
        preview = QPushButton("Preview")
        preview.clicked.connect(self._preview_steamstub)
        unpack = QPushButton("Unpack")
        unpack.setObjectName("primaryButton")
        unpack.clicked.connect(self._confirm_steamstub_unpack)
        restore = QPushButton("Restore backups")
        restore.clicked.connect(self._confirm_steamstub_restore)
        actions.addWidget(preview)
        actions.addWidget(unpack)
        actions.addWidget(restore)
        actions.addStretch(1)
        layout.addWidget(detail)
        layout.addLayout(path_row)
        layout.addLayout(actions)
        layout.addStretch(1)
        return tab

    def _steamstub_inputs(self):
        self._require_compat()
        folder = require_game_directory(self.stub_folder.text())
        unpacker = SteamStubUnpacker()
        if not unpacker.is_available():
            raise FourUFourFreeError("Steamless was not found under third_party.")
        return unpacker, folder

    def _preview_steamstub(self) -> None:
        try:
            unpacker, folder = self._steamstub_inputs()
        except FourUFourFreeError as exc:
            QMessageBox.warning(self, "SteamStub", str(exc))
            return

        def task():
            return [
                path
                for path in folder.rglob("*.exe")
                if not unpacker._should_skip(path)
            ]

        def done(paths):
            self.log(f"SteamStub preview: {len(paths)} candidate executables")
            for path in paths[:30]:
                self.log(f"  {path.relative_to(folder)}")
            self._show_page("logs")

        self.run_task(task, done, label="Scanning executables")

    def _confirm_steamstub_unpack(self) -> None:
        try:
            unpacker, folder = self._steamstub_inputs()
        except FourUFourFreeError as exc:
            QMessageBox.warning(self, "SteamStub", str(exc))
            return
        if (
            QMessageBox.question(
                self,
                "Unpack SteamStub",
                f"Unpack supported executables under:\n{folder}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.run_task(
            lambda: unpacker.unpack_directory(folder, log_func=self.log),
            lambda count: self.log(f"Unpacked {count} executables"),
            label="Unpacking executables",
        )

    def _confirm_steamstub_restore(self) -> None:
        try:
            unpacker, folder = self._steamstub_inputs()
        except FourUFourFreeError as exc:
            QMessageBox.warning(self, "SteamStub", str(exc))
            return
        if (
            QMessageBox.question(
                self, "Restore backups", f"Restore SteamStub backups under:\n{folder}?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.run_task(
            lambda: unpacker.restore_directory(folder, log_func=self.log),
            lambda count: self.log(f"Restored {count} backups"),
            label="Restoring backups",
        )

    def _build_fixes_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        search_row = QHBoxLayout()
        self.fix_query = QLineEdit()
        self.fix_query.setPlaceholderText("Game name")
        self.fix_query.returnPressed.connect(self._search_fixes)
        search = QPushButton("Search")
        search.clicked.connect(self._search_fixes)
        search_row.addWidget(self.fix_query, 1)
        search_row.addWidget(search)
        self.fix_results = QListWidget()
        target_row = QHBoxLayout()
        self.fix_folder = QLineEdit()
        self.fix_folder.setPlaceholderText("Installed game folder")
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda: self._pick_directory(self.fix_folder))
        apply_fix = QPushButton("Download and apply")
        apply_fix.setObjectName("primaryButton")
        apply_fix.clicked.connect(self._confirm_apply_fix)
        target_row.addWidget(self.fix_folder, 1)
        target_row.addWidget(browse)
        target_row.addWidget(apply_fix)
        layout.addLayout(search_row)
        layout.addWidget(self.fix_results, 1)
        layout.addLayout(target_row)
        return tab

    def _search_fixes(self) -> None:
        query = self.fix_query.text().strip()
        if not query:
            QMessageBox.warning(self, "Community fixes", "Enter a game name first.")
            return

        def task():
            return search_crack_games(query, fetch_crack_games())[:50]

        def done(games):
            self._crack_results = games
            self.fix_results.clear()
            for game in games:
                parts = [str(game.get("name") or "Unknown")]
                if game.get("buildid"):
                    parts.append(f"Build {game['buildid']}")
                badges = _badge_summary(game)
                if badges:
                    parts.append(badges)
                item = QListWidgetItem("  /  ".join(parts))
                item.setData(Qt.ItemDataRole.UserRole, game)
                self.fix_results.addItem(item)
            self.log(f"Community fixes: {len(games)} results for {query}")

        self.run_task(task, done, label=f"Searching fixes for {query}")

    def _confirm_apply_fix(self) -> None:
        item = self.fix_results.currentItem()
        if item is None:
            QMessageBox.warning(self, "Community fixes", "Select a result first.")
            return
        try:
            folder = require_game_directory(self.fix_folder.text())
        except FourUFourFreeError as exc:
            QMessageBox.warning(self, "Community fixes", str(exc))
            return
        game = dict(item.data(Qt.ItemDataRole.UserRole) or {})
        name = str(game.get("name") or "game")
        if (
            QMessageBox.question(
                self,
                "Apply community fix",
                f"Download and apply the selected fix for {name} to:\n{folder}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def task():
            fixes = game.get("fixes", [])
            if not fixes:
                raise FourUFourFreeError(
                    "The selected result has no downloadable fixes."
                )
            last_error = "No fix had a usable download link."
            with tempfile.TemporaryDirectory(prefix="4u4free_fix_") as temp_name:
                temp_dir = Path(temp_name)
                for fix in fixes:
                    file_id = _extract_pixeldrain_id(str(fix.get("href") or ""))
                    if not file_id:
                        continue
                    archive = download_pixeldrain(file_id, temp_dir)
                    if (
                        not archive
                        or not archive.exists()
                        or archive.stat().st_size == 0
                    ):
                        last_error = "The fix download was empty."
                        continue
                    if _extract_to_game_folder(archive, folder, name):
                        return f"Applied fix for {name}"
                    last_error = "The downloaded archive could not be extracted."
            raise FourUFourFreeError(last_error)

        self.run_task(
            task,
            lambda message: self.log(message),
            label=f"Applying fix for {name}",
        )

    def _build_plugins_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        warning = QLabel(
            "Local plugins are ordinary Python and run with the same account permissions "
            "as 4u4free. Install only code you have reviewed. Plugins remain off until "
            "both the master switch in Settings and the individual checkbox are enabled."
        )
        warning.setObjectName("warningText")
        warning.setWordWrap(True)
        controls = QHBoxLayout()
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self._reload_plugins)
        apply_button = QPushButton("Apply selection")
        apply_button.setObjectName("primaryButton")
        apply_button.clicked.connect(self._apply_plugin_selection)
        example = QPushButton("Create example")
        example.clicked.connect(self._create_example_plugin)
        open_folder = QPushButton("Open plugin folder")
        open_folder.clicked.connect(self._open_plugin_folder)
        controls.addWidget(reload_button)
        controls.addWidget(apply_button)
        controls.addWidget(example)
        controls.addWidget(open_folder)
        controls.addStretch(1)
        self.plugin_status = QLabel("Plugins have not been loaded")
        self.plugin_status.setObjectName("muted")
        self.plugin_table = DataTable(
            0,
            5,
            "No local plugins were found. Use Create example or open the plugin folder.",
        )
        self.plugin_table.setHorizontalHeaderLabels(
            ["Use", "Plugin", "Version", "Declared permissions", "Status"]
        )
        self.plugin_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.plugin_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.plugin_table.verticalHeader().hide()
        plugin_header = self.plugin_table.horizontalHeader()
        plugin_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        plugin_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        plugin_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        plugin_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        plugin_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        tools_heading = QLabel("REGISTERED TOOLS")
        tools_heading.setObjectName("eyebrow")
        tool_row = QHBoxLayout()
        self.plugin_tools = QListWidget()
        self.plugin_tools.currentItemChanged.connect(self._select_plugin_tool)
        self.plugin_tool_detail = QLabel("Select a registered tool")
        self.plugin_tool_detail.setObjectName("muted")
        self.plugin_tool_detail.setWordWrap(True)
        run = QPushButton("Run selected tool")
        run.clicked.connect(self._confirm_run_plugin_tool)
        tool_row.addWidget(self.plugin_tools, 2)
        detail_box = QVBoxLayout()
        detail_box.addWidget(self.plugin_tool_detail)
        detail_box.addStretch(1)
        detail_box.addWidget(run)
        tool_row.addLayout(detail_box, 1)
        layout.addWidget(warning)
        layout.addLayout(controls)
        layout.addWidget(self.plugin_status)
        layout.addWidget(self.plugin_table, 1)
        layout.addWidget(tools_heading)
        layout.addLayout(tool_row, 1)
        return tab

    def _plugin_games(self) -> list[dict[str, str]]:
        return [self._game_combo_data(game) for game in self._installed_games]

    def _reload_plugins(self, _checked: bool = False) -> None:
        try:
            states = self.plugin_manager.load(
                globally_enabled=self.preferences.plugins_enabled,
                enabled_ids=self.preferences.enabled_plugins,
                games=self._plugin_games(),
                log=self.log,
            )
        except FourUFourFreeError as exc:
            self.plugin_status.setText(str(exc))
            self.log(f"Plugin discovery failed: {exc}")
            return
        self._plugin_states = states
        self._plugin_tools = list(self.plugin_manager.tools)
        self.plugin_table.setRowCount(len(states))
        selected = set(self.preferences.enabled_plugins)
        for row, state in enumerate(states):
            use = QTableWidgetItem()
            use.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            use.setCheckState(
                Qt.CheckState.Checked
                if state.manifest.plugin_id in selected
                else Qt.CheckState.Unchecked
            )
            use.setData(Qt.ItemDataRole.UserRole, state.manifest.plugin_id)
            self.plugin_table.setItem(row, 0, use)
            name = QTableWidgetItem(state.manifest.name)
            name.setToolTip(state.manifest.description)
            self.plugin_table.setItem(row, 1, name)
            self.plugin_table.setItem(row, 2, QTableWidgetItem(state.manifest.version))
            permissions = ", ".join(state.manifest.permissions) or "none declared"
            self.plugin_table.setItem(row, 3, QTableWidgetItem(permissions))
            self.plugin_table.setItem(row, 4, QTableWidgetItem(state.status))
        self.plugin_tools.clear()
        for tool in self._plugin_tools:
            item = QListWidgetItem(tool.title)
            item.setData(Qt.ItemDataRole.UserRole, tool)
            self.plugin_tools.addItem(item)
        if self.plugin_tools.count():
            self.plugin_tools.setCurrentRow(0)
        enabled_label = "enabled" if self.preferences.plugins_enabled else "disabled"
        self.plugin_status.setText(
            f"Plugin loading is {enabled_label} · {len(states)} discovered · "
            f"{len(self._plugin_tools)} tools registered"
        )

    def _apply_plugin_selection(self) -> None:
        enabled: list[str] = []
        for row in range(self.plugin_table.rowCount()):
            item = self.plugin_table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                plugin_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
                if plugin_id:
                    enabled.append(plugin_id)
        self.preferences.enabled_plugins = enabled
        try:
            self.store.save(self.preferences)
        except FourUFourFreeError as exc:
            self._task_error(str(exc), modal=True)
            return
        self._reload_plugins()
        if not self.preferences.plugins_enabled and enabled:
            QMessageBox.information(
                self,
                "Plugins selected",
                "The selection was saved. Turn on Enable local plugins in Settings "
                "before any plugin code will load.",
            )

    def _select_plugin_tool(self, current, _previous=None) -> None:
        tool = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self.plugin_tool_detail.setText(
            f"{tool.description}\n\nPlugin: {tool.plugin_id}"
            if isinstance(tool, PluginTool)
            else "Select a registered tool"
        )

    def _confirm_run_plugin_tool(self) -> None:
        item = self.plugin_tools.currentItem()
        tool = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(tool, PluginTool):
            QMessageBox.warning(self, "Plugins", "Select a registered tool first.")
            return
        if (
            QMessageBox.question(
                self,
                "Run plugin tool",
                f"Run {tool.title} from plugin {tool.plugin_id}?\n\n"
                "Plugin code runs with your account permissions.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def done(result):
            message = f"Plugin tool {tool.title} completed"
            if result is not None:
                message += f": {result}"
            self.log(message)
            self._set_status(message)

        self.run_task(tool.callback, done, label=f"Running plugin tool {tool.title}")

    def _create_example_plugin(self) -> None:
        try:
            folder = self.plugin_manager.create_example()
        except FourUFourFreeError as exc:
            self._task_error(str(exc), modal=True)
            return
        self._reload_plugins()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.log(f"Created example plugin at {folder}")

    def _open_plugin_folder(self) -> None:
        self.plugin_manager.root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.plugin_manager.root)))

    # ---- settings ------------------------------------------------------

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        settings_content = QWidget()
        settings_content.setObjectName("settingsContent")
        layout = QVBoxLayout(settings_content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        self.settings_scroll.setWidget(settings_content)
        outer.addWidget(self.settings_scroll)
        layout.addWidget(
            PageTitle(
                "Settings",
                "Local preferences for Steam paths, downloads, and Store presentation",
            )
        )

        paths = Panel()
        paths_layout = QGridLayout(paths)
        paths_layout.setContentsMargins(16, 16, 16, 16)
        paths_layout.setHorizontalSpacing(10)
        paths_layout.setVerticalSpacing(10)
        paths_heading = QLabel("LOCATIONS")
        paths_heading.setObjectName("eyebrow")
        self.settings_steam_root = QLineEdit()
        self.settings_steam_root.setPlaceholderText(r"C:\Program Files (x86)\Steam")
        steam_browse = QPushButton("Browse")
        steam_browse.clicked.connect(
            lambda: self._pick_directory(self.settings_steam_root)
        )
        self.settings_library = QLineEdit()
        self.settings_library.setPlaceholderText(
            "Optional alternate Steam library folder"
        )
        library_browse = QPushButton("Browse")
        library_browse.clicked.connect(
            lambda: self._pick_directory(self.settings_library)
        )
        self.settings_vault_root = QLineEdit()
        self.settings_vault_root.setPlaceholderText(
            "Optional custom folder for Save Vault archives"
        )
        vault_browse = QPushButton("Browse")
        vault_browse.clicked.connect(
            lambda: self._pick_directory(self.settings_vault_root)
        )
        paths_layout.addWidget(paths_heading, 0, 0, 1, 3)
        paths_layout.addWidget(QLabel("Steam folder"), 1, 0)
        paths_layout.addWidget(self.settings_steam_root, 1, 1)
        paths_layout.addWidget(steam_browse, 1, 2)
        paths_layout.addWidget(QLabel("Preferred library"), 2, 0)
        paths_layout.addWidget(self.settings_library, 2, 1)
        paths_layout.addWidget(library_browse, 2, 2)
        paths_layout.addWidget(QLabel("Save Vault"), 3, 0)
        paths_layout.addWidget(self.settings_vault_root, 3, 1)
        paths_layout.addWidget(vault_browse, 3, 2)
        paths_layout.setColumnStretch(1, 1)
        layout.addWidget(paths)

        behavior = Panel()
        behavior_layout = QFormLayout(behavior)
        behavior_layout.setContentsMargins(16, 16, 16, 16)
        behavior_layout.setHorizontalSpacing(18)
        behavior_layout.setVerticalSpacing(12)
        behavior_heading = QLabel("DOWNLOADS")
        behavior_heading.setObjectName("eyebrow")
        behavior_layout.addRow(behavior_heading)
        self.settings_source = QComboBox()
        for label, key in (
            ("Auto", "auto"),
            ("OurEveryday", "oureveryday"),
            ("Hubcap", "hubcap"),
            ("Ryuu", "ryuu"),
            ("DepotBox", "depotbox"),
        ):
            self.settings_source.addItem(label, key)
        self.settings_confirm = QCheckBox("Ask before preparing a Store download")
        self.settings_restart = QCheckBox("Restart Steam automatically after setup")
        behavior_layout.addRow("Default source", self.settings_source)
        behavior_layout.addRow("Confirmations", self.settings_confirm)
        behavior_layout.addRow("After setup", self.settings_restart)
        layout.addWidget(behavior)

        appearance = Panel()
        appearance_layout = QFormLayout(appearance)
        appearance_layout.setContentsMargins(16, 16, 16, 16)
        appearance_layout.setHorizontalSpacing(18)
        appearance_layout.setVerticalSpacing(12)
        appearance_heading = QLabel("STORE")
        appearance_heading.setObjectName("eyebrow")
        appearance_layout.addRow(appearance_heading)
        self.settings_hide_adult = QCheckBox("Hide adult content")
        self.settings_store_art = QCheckBox("Load game header artwork")
        self.settings_density = QComboBox()
        self.settings_density.addItem("Comfortable", "comfortable")
        self.settings_density.addItem("Compact", "compact")
        appearance_layout.addRow("Content filter", self.settings_hide_adult)
        appearance_layout.addRow("Artwork", self.settings_store_art)
        appearance_layout.addRow("Card density", self.settings_density)
        layout.addWidget(appearance)

        extensions_heading = QLabel("EXTENSIONS")
        extensions_heading.setObjectName("eyebrow")
        self.settings_plugins_enabled = QCheckBox(
            "Enable reviewed local Python plugins"
        )
        plugin_note = QLabel(
            "Full trust: enabled plugins run with your Windows account permissions."
        )
        plugin_note.setObjectName("warningText")
        plugin_note.setWordWrap(True)
        appearance_layout.addRow(extensions_heading)
        appearance_layout.addRow("Plugin system", self.settings_plugins_enabled)
        appearance_layout.addRow("", plugin_note)

        actions = QHBoxLayout()
        self.settings_save = QPushButton("Save settings")
        self.settings_save.setObjectName("primaryButton")
        self.settings_save.clicked.connect(self._save_settings)
        defaults = QPushButton("Restore defaults")
        defaults.clicked.connect(
            lambda: self._populate_settings_controls(AppConfig(), mark_dirty=True)
        )
        self.settings_change_status = QLabel("")
        self.settings_change_status.setObjectName("savedState")
        self.settings_path_label = QLabel(str(self.store.path))
        self.settings_path_label.setObjectName("muted")
        self.settings_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        actions.addWidget(self.settings_save)
        actions.addWidget(defaults)
        actions.addWidget(self.settings_change_status)
        actions.addStretch(1)
        actions.addWidget(self.settings_path_label)
        layout.addLayout(actions)
        layout.addStretch(1)

        for line_edit in (
            self.settings_steam_root,
            self.settings_library,
            self.settings_vault_root,
        ):
            line_edit.textChanged.connect(self._mark_settings_dirty)
        for combo in (self.settings_source, self.settings_density):
            combo.currentIndexChanged.connect(self._mark_settings_dirty)
        for checkbox in (
            self.settings_hide_adult,
            self.settings_store_art,
            self.settings_confirm,
            self.settings_restart,
            self.settings_plugins_enabled,
        ):
            checkbox.toggled.connect(self._mark_settings_dirty)
        return page

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _populate_settings_controls(
        self, config: AppConfig, *, mark_dirty: bool = False
    ) -> None:
        self.settings_steam_root.setText(config.steam_root or "")
        self.settings_library.setText(config.preferred_library or "")
        self.settings_vault_root.setText(config.save_vault_root or "")
        self._set_combo_value(self.settings_source, config.download_source)
        self.settings_hide_adult.setChecked(config.hide_adult_content)
        self.settings_confirm.setChecked(config.confirm_downloads)
        self._set_combo_value(self.settings_density, config.store_density)
        self.settings_store_art.setChecked(config.show_store_art)
        self.settings_restart.setChecked(config.restart_steam_after_setup)
        self.settings_plugins_enabled.setChecked(config.plugins_enabled)
        self._set_settings_dirty(mark_dirty)

    def _mark_settings_dirty(self, *_args) -> None:
        self._set_settings_dirty(True)

    def _set_settings_dirty(self, dirty: bool) -> None:
        self.settings_save.setEnabled(bool(dirty))
        self.settings_change_status.setText("Unsaved changes" if dirty else "")

    def _load_settings_into_ui(self) -> None:
        self._populate_settings_controls(self.preferences)
        self._set_combo_value(self.store_source, self.preferences.download_source)
        self.store_hide_adult.setChecked(self.preferences.hide_adult_content)

    def _save_settings(self) -> None:
        steam_text = self.settings_steam_root.text().strip().strip('"')
        library_text = self.settings_library.text().strip().strip('"')
        vault_text = self.settings_vault_root.text().strip().strip('"')
        if steam_text and not Path(steam_text).is_dir():
            QMessageBox.warning(
                self, "Settings", f"Steam folder does not exist:\n{steam_text}"
            )
            return
        if library_text and not Path(library_text).is_dir():
            QMessageBox.warning(
                self,
                "Settings",
                f"Preferred library folder does not exist:\n{library_text}",
            )
            return
        if (
            self.settings_plugins_enabled.isChecked()
            and not self.preferences.plugins_enabled
        ):
            if (
                QMessageBox.question(
                    self,
                    "Enable local plugins",
                    "Enabled plugins are ordinary Python code and run with the same "
                    "Windows account permissions as 4u4free. Only enable plugins you "
                    "have reviewed. Turn on the plugin system?",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return

        config = AppConfig(
            steam_root=steam_text or None,
            preferred_library=library_text or None,
            download_source=str(self.settings_source.currentData() or "auto"),
            hide_adult_content=self.settings_hide_adult.isChecked(),
            confirm_downloads=self.settings_confirm.isChecked(),
            store_density=str(self.settings_density.currentData() or "comfortable"),
            show_store_art=self.settings_store_art.isChecked(),
            restart_steam_after_setup=self.settings_restart.isChecked(),
            welcome_acknowledged=self.preferences.welcome_acknowledged,
            save_vault_root=vault_text or None,
            save_vault_sources=dict(self.preferences.save_vault_sources),
            plugins_enabled=self.settings_plugins_enabled.isChecked(),
            enabled_plugins=list(self.preferences.enabled_plugins),
        )
        try:
            self.store.save(config)
        except FourUFourFreeError as exc:
            QMessageBox.critical(self, "Settings", str(exc))
            return
        self.preferences = config
        self._set_settings_dirty(False)
        self.settings_change_status.setText("Saved")
        self._set_combo_value(self.store_source, config.download_source)
        self.store_hide_adult.setChecked(config.hide_adult_content)
        if self._store_games:
            self._render_store()
        self._refresh_vault_snapshots()
        self._reload_plugins()
        self.log("Settings saved")
        self._set_status("Settings saved")
        self._refresh_environment()

    # ---- activity and system actions ----------------------------------

    def _build_logs_page(self) -> QWidget:
        page, layout = self._page()
        header = QHBoxLayout()
        title = PageTitle("Activity", "Detailed status from the current session")
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.log_text.clear())
        header.addWidget(title, 1)
        header.addWidget(clear, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.log_text, 1)
        return page

    def _confirm_restart_steam(self) -> None:
        if sys.platform != "win32":
            QMessageBox.information(
                self, "Restart Steam", "Automatic restart is available on Windows only."
            )
            return
        if (
            QMessageBox.question(
                self, "Restart Steam", "Close Steam and launch it again now?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.run_task(
            self._restart_steam,
            lambda message: self.log(message),
            label="Restarting Steam",
        )

    def _restart_steam(self) -> str:
        steam = self._steam_root()
        flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        for process in ("steam.exe", "steamwebhelper.exe", "steamservice.exe"):
            subprocess.run(
                ["taskkill", "/F", "/IM", process],
                capture_output=True,
                **flags,
            )
        time.sleep(2)
        executable = steam / "steam.exe"
        if not executable.is_file():
            raise FourUFourFreeError(f"steam.exe was not found at {executable}")
        subprocess.Popen([str(executable)], cwd=str(steam))
        return "Steam restarted"

    def _sync_window_state(self) -> None:
        maximized = self.isMaximized()
        self.window_layout.setContentsMargins(0, 0, 0, 0)
        for widget in (
            self.window_frame,
            self.sidebar,
            self.status_bar,
        ):
            widget.setProperty("maximized", maximized)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_window_state()
        self._apply_windows_frame()

    def _apply_windows_frame(self) -> None:
        if sys.platform == "win32":
            try:
                import ctypes

                hwnd = int(self.winId())
                dwm = ctypes.windll.dwmapi

                dark = ctypes.c_int(1)
                if (
                    dwm.DwmSetWindowAttribute(
                        hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)
                    )
                    != 0
                ):
                    dwm.DwmSetWindowAttribute(
                        hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark)
                    )

                rounded = ctypes.c_int(2)  # DWMWCP_ROUND
                dwm.DwmSetWindowAttribute(
                    hwnd, 33, ctypes.byref(rounded), ctypes.sizeof(rounded)
                )

                for attribute, color in (
                    (34, 0x00352C25),  # border #252C35
                    (35, 0x0017120E),  # caption #0E1217
                    (36, 0x00F7F5F2),  # text #F2F5F7
                ):
                    value = ctypes.c_uint32(color)
                    dwm.DwmSetWindowAttribute(
                        hwnd,
                        attribute,
                        ctypes.byref(value),
                        ctypes.sizeof(value),
                    )
            except (AttributeError, OSError, TypeError, ValueError):
                pass

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_window_state()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.playtime_timer.stop()
        if self._playtime_idler_process is not None:
            stop_headless_idle(self._playtime_idler_process)
            self._playtime_idler_process = None
        self._playtime_session = None
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "store_scroll") and self._store_games:
            desired = self._desired_store_columns()
            if desired != self._store_columns:
                QTimer.singleShot(0, self._render_store)

    def _apply_style(self) -> None:
        check_icon = _asset_path("icons/check.svg").as_posix()
        chevron_icon = _asset_path("icons/chevron-down.svg").as_posix()
        self.setStyleSheet(
            f"""
            * {{
                font-family: "IBM Plex Sans";
                font-size: 13px;
            }}
            QMainWindow, QWidget#windowCanvas {{
                background: {APP_BG};
            }}
            QFrame#windowFrame {{
                background: {APP_BG};
                border: 0;
                border-radius: 0;
            }}
            QFrame#windowFrame[maximized="true"] {{
                border: 0;
                border-radius: 0;
            }}
            QWidget#windowBody, QDialog#welcomeDialog, QFrame#content, QStackedWidget {{
                background: {APP_BG};
                color: {TEXT};
            }}
            QLabel {{ color: {TEXT}; }}
            QLabel#welcomeTitle {{ color: {TEXT}; font-size: 23px; font-weight: 700; }}
            QLabel#welcomeDeveloper {{
                color: {ACCENT}; font-size: 14px; font-weight: 650; padding-top: 6px;
            }}
            QLabel#welcomeBody {{ color: {TEXT}; font-size: 14px; padding: 3px 0; }}
            QLabel#welcomeWarning {{
                color: #F0C58B;
                background: #211C16;
                border: 1px solid #4A3A25;
                border-radius: 4px;
                padding: 12px 14px;
                font-size: 14px;
                font-weight: 650;
            }}
            QFrame#sidebar {{
                background: {SIDEBAR_BG};
                border: 0;
                border-right: 1px solid {BORDER};
            }}
            QLabel#sidebarSection {{
                color: #65717F; font-size: 10px; font-weight: 600; letter-spacing: 1px;
                padding: 0 8px;
            }}
            QLabel#sidebarVersion {{ color: {MUTED}; font-size: 11px; padding: 6px 2px; }}
            QLabel#pageTitle {{ color: {TEXT}; font-size: 24px; font-weight: 600; }}
            QLabel#pageSubtitle {{ color: {MUTED}; font-size: 12px; }}
            QLabel#muted {{ color: {MUTED}; }}
            QLabel#warningText {{ color: #E8B97A; }}
            QLabel#savedState {{ color: {ACCENT}; font-size: 12px; }}
            QLabel#sectionTitle {{ color: {TEXT}; font-size: 15px; font-weight: 600; }}
            QLabel#eyebrow {{ color: {MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
            QLabel#metric {{ color: {TEXT}; font-size: 18px; font-weight: 650; }}
            QLabel#fieldLabel {{ color: {MUTED}; font-weight: 600; }}
            QLabel#cardTitle {{ color: {TEXT}; font-size: 14px; font-weight: 650; }}
            QLabel#emptyState {{ color: {MUTED}; padding: 40px; }}
            QLabel#gameImage {{
                background: #0E1115;
                color: #56616E;
                border: 1px solid {BORDER};
            }}
            QFrame#panel {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
            QPushButton {{
                background: {SURFACE_RAISED};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 5px;
                padding: 7px 13px;
                min-height: 20px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background: #222933; border-color: #3A4654; }}
            QPushButton:pressed {{ background: #11151A; }}
            QPushButton:focus {{ border-color: #5EB89E; }}
            QPushButton:disabled {{
                color: #59626D; background: #111419; border-color: #1B222A;
            }}
            QPushButton#primaryButton {{
                background: {ACCENT};
                color: {ACCENT_INK};
                border-color: {ACCENT};
                font-weight: 700;
            }}
            QPushButton#primaryButton:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
            QPushButton#dangerButton {{ color: {DANGER}; }}
            QPushButton#quietButton {{
                text-align: left; color: {MUTED}; background: #12171D;
                border-color: #222A34;
            }}
            QPushButton#navButton {{
                background: transparent;
                color: {MUTED};
                border: 0;
                border-left: 3px solid transparent;
                border-radius: 4px;
                padding: 9px 10px 9px 8px;
                text-align: left;
                font-weight: 500;
            }}
            QPushButton#navButton:hover {{ background: #151B22; color: {TEXT}; }}
            QPushButton#navButton:checked {{
                background: #171D23;
                color: {TEXT};
                border-left: 3px solid {ACCENT};
                font-weight: 600;
            }}
            QLineEdit, QComboBox, QSpinBox, QListWidget, QPlainTextEdit, QTableWidget {{
                background: #101318;
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 5px;
                selection-background-color: #294C42;
                selection-color: {TEXT};
            }}
            QLineEdit, QComboBox, QSpinBox {{ padding: 8px 11px; min-height: 20px; }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: #559982; }}
            QLineEdit {{ placeholder-text-color: #65717F; }}
            QComboBox::drop-down {{ border: 0; width: 24px; }}
            QComboBox::down-arrow {{
                image: url("{chevron_icon}"); width: 14px; height: 14px;
            }}
            QComboBox QAbstractItemView {{
                background: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid #35404C;
                padding: 4px; outline: 0;
            }}
            QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 3px 8px; }}
            QCheckBox {{ color: {TEXT}; spacing: 7px; }}
            QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #46515E; background: #101318; }}
            QCheckBox::indicator:checked {{
                background: {ACCENT}; border-color: {ACCENT};
                image: url("{check_icon}");
            }}
            QHeaderView::section {{
                background: #14191F; color: #A7B0BA; border: 0;
                border-bottom: 1px solid {BORDER}; padding: 9px 10px; font-weight: 600;
            }}
            QTableWidget {{
                gridline-color: transparent;
                alternate-background-color: #12161B;
                outline: 0;
            }}
            QTableWidget::item {{ padding: 8px 10px; border-bottom: 1px solid #1B2128; }}
            QTableWidget::item:hover {{ background: #151B22; }}
            QTableWidget::item:selected, QListWidget::item:selected {{
                background: #20372F; color: {TEXT};
            }}
            QListWidget::item {{ padding: 8px 10px; }}
            QFrame#toolWorkspace {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 7px;
            }}
            QListWidget#toolNavigation {{
                background: #0F1318;
                border: 0;
                border-right: 1px solid {BORDER};
                border-top-left-radius: 7px;
                border-bottom-left-radius: 7px;
                padding: 8px 6px;
                outline: 0;
            }}
            QListWidget#toolNavigation::item {{
                color: {MUTED};
                border: 0;
                border-left: 3px solid transparent;
                border-radius: 4px;
                padding: 9px 10px;
                margin: 1px 0;
            }}
            QListWidget#toolNavigation::item:hover {{
                background: #171D23; color: {TEXT};
            }}
            QListWidget#toolNavigation::item:selected {{
                background: #19211F;
                color: {TEXT};
                border-left: 3px solid {ACCENT};
                font-weight: 600;
            }}
            QStackedWidget#toolStack {{ background: {SURFACE}; border: 0; }}
            QWidget#settingsContent {{ background: {APP_BG}; }}
            QWidget#storeHost {{ background: {APP_BG}; }}
            QTabWidget::pane {{ border: 1px solid {BORDER}; background: {SURFACE}; top: -1px; }}
            QTabBar::tab {{
                background: {APP_BG}; color: {MUTED}; border-bottom: 1px solid {BORDER};
                padding: 9px 14px;
            }}
            QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
            QScrollArea {{ background: transparent; border: 0; }}
            QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: #303944; min-height: 28px; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0; }}
            QScrollBar::handle:horizontal {{ background: #303944; min-width: 28px; border-radius: 3px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QFrame#embeddedStatus {{
                background: #0D1116;
                border: 0;
                border-top: 1px solid {BORDER};
            }}
            QLabel#statusText {{ color: {MUTED}; font-size: 11px; }}
            QLabel#taskCount {{ color: #A7B0BA; font-size: 11px; padding-right: 4px; }}
            QProgressBar {{
                background: #11151A; border: 1px solid {BORDER}; border-radius: 2px;
                color: {TEXT}; text-align: center; min-height: 12px;
            }}
            QProgressBar::chunk {{ background: {ACCENT}; }}
            QToolTip {{ background: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER}; }}
            """
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("4u4free")
    app.setApplicationDisplayName("4u4free")
    app.setStyle("Fusion")
    app.setFont(QFont(_load_application_fonts(), 10))
    icon_path = _asset_path("brand-mark.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    smoke_test = "--smoke-test" in sys.argv
    window = MainWindow(auto_start=not smoke_test)
    window.show()
    if smoke_test:
        app.processEvents()
        window.close()
        app.processEvents()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
