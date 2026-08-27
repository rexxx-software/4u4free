"""Read-only Steam installation, library, and installed-game discovery."""

from __future__ import annotations

import os
import platform
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .errors import FourUFourFreeError
from .vdf import get_mapping, get_string, read_vdf


_STEAM_CONNECTION_STATE_RE = re.compile(
    r"\[(Logged On|Logged Off|Logging On|Connecting),"
)


@dataclass(frozen=True)
class SteamLocation:
    path: Path
    source: str


@dataclass(frozen=True)
class SteamGame:
    app_id: str
    name: str
    install_dir: str
    build_id: str
    last_updated: str
    library: Path
    manifest: Path

    def to_dict(self) -> Dict[str, str]:
        values = asdict(self)
        values["library"] = str(self.library)
        values["manifest"] = str(self.manifest)
        return values


def steam_connection_state(steam_root: str | Path) -> str:
    """Return Steam's latest connection state from its own connection log."""
    log_path = Path(steam_root) / "logs" / "connection_log.txt"
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 262_144), os.SEEK_SET)
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return "Unknown"
    matches = _STEAM_CONNECTION_STATE_RE.findall(text)
    return matches[-1] if matches else "Unknown"


def _looks_like_steam(path: Path) -> bool:
    return path.is_dir() and (
        (path / "steamapps").is_dir() or (path / "config").is_dir()
    )


def _registry_candidates() -> Iterable[Tuple[Path, str]]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    found: List[Tuple[Path, str]] = []
    queries = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    )
    for hive, key_name, value_name in queries:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
            if value:
                found.append((Path(value), f"registry:{key_name}"))
        except OSError:
            continue
    return found


def find_steam_root(
    explicit: Optional[Path] = None, configured: Optional[str] = None
) -> Optional[SteamLocation]:
    candidates: List[Tuple[Path, str]] = []
    if explicit:
        normalized = explicit.expanduser().resolve(strict=False)
        return (
            SteamLocation(normalized, "command-line")
            if _looks_like_steam(normalized)
            else None
        )
    if configured:
        candidates.append((Path(configured), "config"))
    for variable in ("STEAM_ROOT", "STEAM_PATH"):
        if os.environ.get(variable):
            candidates.append((Path(os.environ[variable]), f"environment:{variable}"))
    candidates.extend(_registry_candidates())
    if os.name == "nt":
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            if os.environ.get(variable):
                candidates.append(
                    (Path(os.environ[variable]) / "Steam", f"default:{variable}")
                )
    else:
        candidates.extend(
            [
                (Path.home() / ".steam" / "steam", "default"),
                (Path.home() / ".local" / "share" / "Steam", "default"),
            ]
        )

    seen = set()
    for path, source in candidates:
        normalized = path.expanduser().resolve(strict=False)
        key = os.path.normcase(str(normalized))
        if key in seen:
            continue
        seen.add(key)
        if _looks_like_steam(normalized):
            return SteamLocation(normalized, source)
    return None


def require_steam_root(
    explicit: Optional[Path] = None, configured: Optional[str] = None
) -> SteamLocation:
    result = find_steam_root(explicit, configured)
    if result is None:
        raise FourUFourFreeError(
            "Steam was not found. Pass --steam-root or save one with '4u4free config set'."
        )
    return result


def list_libraries(steam_root: Path) -> List[Path]:
    root = steam_root.resolve(strict=False)
    paths: List[Path] = [root]
    library_file = root / "steamapps" / "libraryfolders.vdf"
    if library_file.exists():
        parsed = read_vdf(library_file)
        folders = get_mapping(parsed, "libraryfolders")
        for key, value in folders.items():
            if not str(key).isdigit():
                continue
            raw_path = get_string(value, "path") if isinstance(value, dict) else value
            if isinstance(raw_path, str) and raw_path:
                paths.append(Path(raw_path))

    result: List[Path] = []
    seen = set()
    for path in paths:
        normalized = path.expanduser().resolve(strict=False)
        key = os.path.normcase(str(normalized))
        if key not in seen and (normalized / "steamapps").is_dir():
            seen.add(key)
            result.append(normalized)
    return result


def list_games(libraries: Iterable[Path]) -> List[SteamGame]:
    games: List[SteamGame] = []
    for library in libraries:
        steamapps = library / "steamapps"
        for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
            try:
                parsed = read_vdf(manifest)
            except FourUFourFreeError:
                continue
            state = get_mapping(parsed, "AppState")
            app_id = get_string(state, "appid") or manifest.stem.removeprefix(
                "appmanifest_"
            )
            games.append(
                SteamGame(
                    app_id=app_id,
                    name=get_string(state, "name", "Unknown"),
                    install_dir=get_string(state, "installdir"),
                    build_id=get_string(state, "buildid"),
                    last_updated=get_string(state, "LastUpdated"),
                    library=library,
                    manifest=manifest,
                )
            )
    return sorted(games, key=lambda game: (game.name.casefold(), game.app_id))


def doctor(
    explicit: Optional[Path] = None, configured: Optional[str] = None
) -> Dict[str, object]:
    location = find_steam_root(explicit, configured)
    report: Dict[str, object] = {
        "application": "4u4free",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "steam_found": location is not None,
        "steam_root": str(location.path) if location else None,
        "steam_source": location.source if location else None,
        "libraries": 0,
        "games": 0,
        "status": "ok" if location else "steam-not-found",
    }
    if location:
        libraries = list_libraries(location.path)
        report["libraries"] = len(libraries)
        report["games"] = len(list_games(libraries))
    return report
