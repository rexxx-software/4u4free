"""UI-independent DLC catalog and unlocker orchestration helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from .errors import FourUFourFreeError

from four_u_four_free._compat.dlc_unlockers.base import UnlockerType
from four_u_four_free._compat.dlc_unlockers.creamapi import CreamAPIUnlocker
from four_u_four_free._compat.dlc_unlockers.downloader import GitHubReleaseDownloader
from four_u_four_free._compat.dlc_unlockers.smokeapi import SmokeAPIUnlocker
from four_u_four_free._compat.dlc_unlockers.uplay_r1 import UplayR1Unlocker
from four_u_four_free._compat.dlc_unlockers.uplay_r2 import UplayR2Unlocker
from four_u_four_free._compat.dlc_unlockers.validation import (
    validate_app_id,
    validate_dlc_ids,
    validate_game_directory,
)
from four_u_four_free._compat.network.steam_store import (
    get_dlc_list_from_store,
    get_dlc_names_from_store,
)


UNLOCKER_KEYS = ("creamapi", "smokeapi", "uplay-r1", "uplay-r2")
UNLOCKER_LABELS = {
    "creamapi": "CreamAPI",
    "smokeapi": "SmokeAPI",
    "uplay-r1": "Uplay R1",
    "uplay-r2": "Uplay R2",
}
_UNLOCKER_TYPES = {
    "creamapi": UnlockerType.CREAMAPI,
    "smokeapi": UnlockerType.SMOKEAPI,
    "uplay-r1": UnlockerType.UPLAY_R1,
    "uplay-r2": UnlockerType.UPLAY_R2,
}


def parse_dlc_ids(value: str) -> list[int]:
    """Parse comma, semicolon, or whitespace separated DLC IDs."""
    text = str(value or "").strip()
    if not text:
        return []
    tokens = [token for token in re.split(r"[\s,;]+", text) if token]
    if any(not token.isdigit() for token in tokens):
        raise FourUFourFreeError("DLC IDs must contain digits separated by commas.")
    ids = list(dict.fromkeys(int(token) for token in tokens))
    valid, error = validate_dlc_ids(ids)
    if not valid:
        raise FourUFourFreeError(str(error))
    return ids


def require_app_id(value: str | int) -> int:
    raw = str(value or "").strip()
    if not raw.isdigit():
        raise FourUFourFreeError("Enter a numeric Steam App ID first.")
    app_id = int(raw)
    valid, error = validate_app_id(app_id)
    if not valid:
        raise FourUFourFreeError(str(error))
    return app_id


def require_game_directory(value: str | Path) -> Path:
    raw = str(value or "").strip().strip('"')
    if not raw:
        raise FourUFourFreeError("Choose an installed game folder first.")
    folder = Path(raw).expanduser()
    valid, error = validate_game_directory(folder)
    if not valid:
        raise FourUFourFreeError(str(error))
    return folder


def fetch_dlc_catalog(app_id: int) -> dict:
    """Return the public Steam DLC catalog for an app without CM login."""
    app_id = require_app_id(app_id)
    result = get_dlc_list_from_store(app_id)
    if result is None:
        raise FourUFourFreeError(
            "Steam did not return DLC data for this App ID. Check the ID and try again."
        )
    app_name, dlc_ids = result
    names = get_dlc_names_from_store(dlc_ids)
    return {
        "app_id": app_id,
        "name": app_name,
        "dlcs": [
            {"id": dlc_id, "name": names.get(dlc_id, f"DLC {dlc_id}")}
            for dlc_id in dlc_ids
        ],
    }


def unlocker_instance(key: str):
    factories = {
        "creamapi": CreamAPIUnlocker,
        "smokeapi": SmokeAPIUnlocker,
        "uplay-r1": UplayR1Unlocker,
        "uplay-r2": UplayR2Unlocker,
    }
    try:
        return factories[key]()
    except KeyError as exc:
        raise FourUFourFreeError(f"Unsupported unlocker: {key}") from exc


def inspect_unlockers(game_dir: str | Path) -> list[dict]:
    folder = require_game_directory(game_dir)
    return [
        {
            "key": key,
            "name": UNLOCKER_LABELS[key],
            "installed": bool(unlocker_instance(key).is_installed(folder)),
        }
        for key in UNLOCKER_KEYS
    ]


def inspect_game_apis(game_dir: str | Path) -> list[dict]:
    """Find supported API DLLs recursively, matching installer behavior."""
    folder = require_game_directory(game_dir)
    definitions = (
        ("steam_api.dll", "Steam API 32-bit"),
        ("steam_api64.dll", "Steam API 64-bit"),
        ("uplay_r1_loader.dll", "Ubisoft Uplay R1"),
        ("upc_r2_loader.dll", "Ubisoft Connect R2"),
    )
    rows = []
    for filename, label in definitions:
        matches = [path for path in folder.rglob(filename) if path.is_file()]
        rows.append(
            {
                "filename": filename,
                "label": label,
                "found": bool(matches),
                "paths": matches,
            }
        )
    return rows


def _dll_dir_for(downloader: GitHubReleaseDownloader, key: str):
    unlocker_type = _UNLOCKER_TYPES[key]
    return downloader.get_cached_dll(unlocker_type) or downloader._get_local_resource(
        unlocker_type
    )


def install_unlocker(
    game_dir: str | Path,
    key: str,
    app_id: int,
    dlc_ids: list[int],
    *,
    cache_dir: str | Path,
    downloader_factory: Callable[
        [Path], GitHubReleaseDownloader
    ] = GitHubReleaseDownloader,
) -> bool:
    folder = require_game_directory(game_dir)
    app_id = require_app_id(app_id)
    valid, error = validate_dlc_ids(dlc_ids)
    if not valid:
        raise FourUFourFreeError(str(error))
    if key not in UNLOCKER_KEYS:
        raise FourUFourFreeError(f"Unsupported unlocker: {key}")

    downloader = downloader_factory(Path(cache_dir))
    if key == "creamapi":
        unlocker = CreamAPIUnlocker(downloader)
        if unlocker.install(folder, dlc_ids, app_id):
            return True
        raise FourUFourFreeError(
            unlocker.last_error or "CreamAPI installation did not complete."
        )

    dll_dir = _dll_dir_for(downloader, key)
    if dll_dir is None:
        raise FourUFourFreeError(
            f"{UNLOCKER_LABELS[key]} files are unavailable. Check the bundled resources."
        )
    if key == "smokeapi":
        return bool(
            SmokeAPIUnlocker().install(folder, dlc_ids, app_id, smokeapi_dir=dll_dir)
        )
    if key == "uplay-r1":
        return bool(
            UplayR1Unlocker().install(folder, dlc_ids, app_id, unlocker_dir=dll_dir)
        )
    return bool(
        UplayR2Unlocker().install(folder, dlc_ids, app_id, unlocker_dir=dll_dir)
    )


def uninstall_unlocker(game_dir: str | Path, key: str) -> bool:
    folder = require_game_directory(game_dir)
    return bool(unlocker_instance(key).uninstall(folder))
