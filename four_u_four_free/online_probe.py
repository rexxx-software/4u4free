"""Read-only compatibility probe for games without a curated online profile."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .steamdb_detection import detect_risks


@dataclass(frozen=True)
class OnlineProbe:
    allow_generic: bool
    status: str
    detail: str
    evidence: tuple[str, ...] = ()


_STEAM_API_MARKERS = {
    "steam_api.dll",
    "steam_api64.dll",
    "libsteam_api.so",
}
_ANTI_CHEAT_MARKERS = (
    "easyanticheat",
    "start_protected_game",
    "battleye",
    "beservice",
    "equ8",
    "xigncode",
    "faceit",
)
_BACKEND_MARKERS = (
    "eossdk",
    "playfab",
    "photon",
    "nakama",
    "gamesparks",
    "vivox",
    "uplay_r1",
    "upc_r2",
    "rockstar games",
)
_SKIP_DIRECTORIES = {
    ".git",
    "assets",
    "audio",
    "content",
    "localization",
    "movies",
    "screenshots",
    "sound",
}
_MAX_FILES = 10_000
_MAX_DEPTH = 4


def _matches_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def probe_online_compatibility(game_folder: Path) -> OnlineProbe:
    """Classify a local game folder without modifying or launching anything."""
    folder = Path(game_folder)
    if not folder.is_dir():
        return OnlineProbe(
            allow_generic=False,
            status="Game folder unavailable",
            detail="The installed game folder could not be scanned. Refresh the Steam library.",
        )

    steam_api: list[str] = []
    anti_cheat: list[str] = []
    backend: list[str] = []
    inspected = 0
    scanned_paths: list[str] = []

    try:
        for current, directories, files in os.walk(folder, followlinks=False):
            current_path = Path(current)
            try:
                depth = len(current_path.relative_to(folder).parts)
            except ValueError:
                continue
            if depth >= _MAX_DEPTH:
                directories[:] = []
            else:
                directories[:] = [
                    name
                    for name in directories
                    if name.casefold() not in _SKIP_DIRECTORIES
                    and not (current_path / name).is_symlink()
                ]

            for filename in files:
                inspected += 1
                lowered = filename.casefold()
                relative = str((current_path / filename).relative_to(folder))
                scanned_paths.append(relative)
                if lowered in _STEAM_API_MARKERS:
                    steam_api.append(relative)
                if _matches_any(lowered, _ANTI_CHEAT_MARKERS):
                    anti_cheat.append(relative)
                if _matches_any(lowered, _BACKEND_MARKERS):
                    backend.append(relative)
                if inspected >= _MAX_FILES:
                    directories[:] = []
                    break
            if inspected >= _MAX_FILES:
                break
    except OSError as exc:
        return OnlineProbe(
            allow_generic=False,
            status="Compatibility scan incomplete",
            detail=f"The game folder could not be fully inspected: {exc}",
        )

    steamdb = detect_risks(scanned_paths)
    anti_cheat.extend(steamdb.anti_cheat)
    backend.extend(steamdb.external_backend)

    if anti_cheat:
        return OnlineProbe(
            allow_generic=False,
            status="Anti-cheat detected",
            detail=(
                "The generic online redirect is blocked because this game contains "
                "anti-cheat components. 4u4free will not alter or bypass anti-cheat."
            ),
            evidence=tuple(anti_cheat[:8]),
        )
    if backend:
        return OnlineProbe(
            allow_generic=False,
            status="External backend detected",
            detail=(
                "This game appears to depend on a non-Steam online service. App 480 "
                "cannot replace that backend; a verified game-specific adapter is needed."
            ),
            evidence=tuple(backend[:8]),
        )
    if steam_api:
        return OnlineProbe(
            allow_generic=True,
            status="Likely Steam API compatible · unverified",
            detail=(
                "A Steam API library was found and no known anti-cheat or external "
                "backend marker was detected. This extends support to games that are "
                "not in the curated database, but successful multiplayer is not guaranteed."
            ),
            evidence=tuple(steam_api[:8]),
        )
    return OnlineProbe(
        allow_generic=False,
        status="Steam API not detected",
        detail=(
            "No Steam API library was found in the first four folder levels. The "
            "generic LC Online Fix is disabled because there is no evidence that this "
            "build uses Steam networking."
        ),
    )
