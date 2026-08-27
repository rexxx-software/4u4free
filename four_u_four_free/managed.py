"""Inspect and recoverably quarantine Steam plug-in Lua files."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .backup import create_backup
from .config import default_data_dir
from .errors import FourUFourFreeError
from .lua import LuaInfo, inspect_lua
from .steam import list_libraries


def list_managed_lua(steam_root: Path) -> List[LuaInfo]:
    directory = steam_root / "config" / "stplug-in"
    if not directory.is_dir():
        return []
    result = []
    for path in sorted(directory.glob("*.lua")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            result.append(inspect_lua(path))
        except FourUFourFreeError:
            continue
    return result


def _matches_app(info: LuaInfo, app_id: str) -> bool:
    return (
        info.path.stem == app_id
        or info.inferred_app_id == app_id
        or any(directive.app_or_depot_id == app_id for directive in info.app_directives)
        or any(token.app_id == app_id for token in info.tokens)
    )


def quarantine_managed_lua(
    steam_root: Path,
    app_id: str,
    apply: bool = False,
    quarantine_root: Optional[Path] = None,
    backup_output: Optional[Path] = None,
) -> Dict[str, object]:
    if not app_id.isdigit():
        raise FourUFourFreeError("App ID must be numeric")
    matches = [
        info.path for info in list_managed_lua(steam_root) if _matches_app(info, app_id)
    ]
    payload: Dict[str, object] = {
        "app_id": app_id,
        "applied": False,
        "files": [str(path) for path in matches],
    }
    if not matches or not apply:
        return payload

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = (
        (quarantine_root or default_data_dir() / "quarantine") / f"{app_id}-{stamp}"
    ).resolve(strict=False)
    if destination.exists():
        raise FourUFourFreeError(
            f"Quarantine destination already exists: {destination}"
        )
    snapshot = create_backup(
        steam_root, output=backup_output, libraries=list_libraries(steam_root)
    )
    moved: List[Path] = []
    try:
        destination.mkdir(parents=True, exist_ok=False)
        for source in matches:
            target = destination / source.name
            shutil.move(str(source), str(target))
            moved.append(target)
    except OSError as exc:
        rollback_errors = []
        for target in reversed(moved):
            source = steam_root / "config" / "stplug-in" / target.name
            try:
                shutil.move(str(target), str(source))
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        try:
            destination.rmdir()
        except OSError:
            pass
        detail = (
            f" Rollback errors: {'; '.join(rollback_errors)}" if rollback_errors else ""
        )
        raise FourUFourFreeError(
            f"Quarantine failed after {len(moved)} files: {exc}. Snapshot: {snapshot.destination}.{detail}"
        ) from exc
    payload.update(
        {
            "applied": True,
            "quarantine": str(destination),
            "snapshot": str(snapshot.destination),
            "moved": [str(path) for path in moved],
        }
    )
    return payload
