"""Steam achievement-manager integration.

The bundled helper is the unmodified official Steam Achievement Manager (SAM)
release.  It talks to the Steam client that is already running and logged in;
4u4free never asks for or stores Steam credentials.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .errors import FourUFourFreeError


SAM_VERSION = "7.0.41"
SAM_RELEASE_URL = (
    "https://github.com/gibbed/SteamAchievementManager/releases/tag/7.0.41"
)
SAM_RELEASE_SHA256 = (
    "6682a3330604aaf31f6916ddbf3b78251abda3a019d15a53b1ce33b72d5cd072"
)


def _application_root() -> Path:
    """Return the source root or PyInstaller data root."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def achievement_manager_path(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else _application_root()
    return base / "third_party" / "steam-achievement-manager" / "SAM.Game.exe"


def require_achievement_manager(root: Path | None = None) -> Path:
    executable = achievement_manager_path(root)
    if not executable.is_file():
        raise FourUFourFreeError(
            "Steam Achievement Manager is missing from this installation. "
            "Reinstall the current 4u4free release."
        )
    return executable


def require_achievement_app_id(value: str | int) -> str:
    text = str(value).strip()
    if not text.isdigit() or int(text) <= 0:
        raise FourUFourFreeError("Choose an installed game with a valid App ID.")
    return text


def steam_is_running() -> bool:
    if os.name != "nt":
        return False
    try:
        import psutil

        for process in psutil.process_iter(attrs=("name",)):
            try:
                if (process.info.get("name") or "").casefold() == "steam.exe":
                    return True
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
    except (ImportError, OSError):
        return False
    return False


def open_achievement_manager(
    app_id: str | int,
    *,
    root: Path | None = None,
) -> int:
    """Open SAM for *app_id* and return its process ID.

    SAM owns the read/write UI and performs its own final confirmation before
    storing changes through the active Steam client session.
    """
    return int(start_achievement_manager(app_id, root=root).pid)


def start_achievement_manager(
    app_id: str | int,
    *,
    root: Path | None = None,
) -> subprocess.Popen:
    """Open SAM for *app_id* and return the process for batch orchestration."""
    if sys.platform != "win32":
        raise FourUFourFreeError(
            "Steam-profile achievement management is available on Windows only."
        )
    normalized_app_id = require_achievement_app_id(app_id)
    executable = require_achievement_manager(root)
    if not steam_is_running():
        raise FourUFourFreeError(
            "Steam is not running. Start Steam, sign in, then try again."
        )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [str(executable), normalized_app_id],
        cwd=str(executable.parent),
        creationflags=creationflags,
    )
