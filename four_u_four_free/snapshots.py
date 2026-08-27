"""Portable Steam inventory snapshots and deterministic comparisons."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .catalog import sha256_file
from .errors import FourUFourFreeError
from .steam import list_games, list_libraries


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _validated_games(
    snapshot: Dict[str, object], label: str
) -> List[Dict[str, object]]:
    if snapshot.get("schema_version") != 1 or not isinstance(
        snapshot.get("games"), list
    ):
        raise FourUFourFreeError(f"Unsupported inventory snapshot: {label}")
    result: List[Dict[str, object]] = []
    seen = set()
    for index, game in enumerate(snapshot["games"]):
        if not isinstance(game, dict):
            raise FourUFourFreeError(
                f"Snapshot {label} has a non-object game at index {index}"
            )
        app_id = game.get("app_id")
        if not isinstance(app_id, str) or not app_id.isdigit():
            raise FourUFourFreeError(
                f"Snapshot {label} has an invalid App ID at index {index}"
            )
        if app_id in seen:
            raise FourUFourFreeError(
                f"Snapshot {label} contains duplicate App ID {app_id}"
            )
        seen.add(app_id)
        for field in (
            "name",
            "install_dir",
            "build_id",
            "last_updated",
            "library",
            "manifest",
        ):
            if not isinstance(game.get(field), str):
                raise FourUFourFreeError(
                    f"Snapshot {label} has an invalid {field!r} for App ID {app_id}"
                )
        digest = game.get("manifest_sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise FourUFourFreeError(
                f"Snapshot {label} has an invalid manifest hash for App ID {app_id}"
            )
        result.append(game)
    return result


def create_inventory_snapshot(steam_root: Path) -> Dict[str, object]:
    libraries = list_libraries(steam_root)
    games = list_games(libraries)
    records = []
    for game in games:
        value = game.to_dict()
        value["manifest_sha256"] = sha256_file(game.manifest)
        records.append(value)
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "steam_root": str(steam_root.resolve(strict=False)),
        "libraries": [str(path) for path in libraries],
        "games": records,
    }


def write_snapshot(
    snapshot: Dict[str, object], output: Path, force: bool = False
) -> Path:
    _validated_games(snapshot, "generated data")
    destination = output.resolve(strict=False)
    if destination.exists() and not force:
        raise FourUFourFreeError(
            f"Snapshot already exists: {destination}. Use --force to replace it."
        )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)
    except OSError as exc:
        raise FourUFourFreeError(
            f"Could not write snapshot {destination}: {exc}"
        ) from exc
    return destination


def load_snapshot(path: Path) -> Dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FourUFourFreeError(f"Could not read snapshot {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FourUFourFreeError(f"Unsupported inventory snapshot: {path}")
    _validated_games(value, str(path))
    return value


def compare_snapshots(
    before: Dict[str, object], after: Dict[str, object]
) -> Dict[str, object]:
    old = {str(game["app_id"]): game for game in _validated_games(before, "before")}
    new = {str(game["app_id"]): game for game in _validated_games(after, "after")}
    added = [new[key] for key in sorted(new.keys() - old.keys())]
    removed = [old[key] for key in sorted(old.keys() - new.keys())]
    changed: List[Dict[str, object]] = []
    compared_fields = (
        "name",
        "install_dir",
        "build_id",
        "last_updated",
        "library",
        "manifest",
        "manifest_sha256",
    )
    for key in sorted(old.keys() & new.keys()):
        differences = {
            field: {"before": old[key].get(field), "after": new[key].get(field)}
            for field in compared_fields
            if old[key].get(field) != new[key].get(field)
        }
        if differences:
            changed.append(
                {
                    "app_id": key,
                    "library": new[key].get("library"),
                    "changes": differences,
                }
            )
    return {
        "before_created_at": before.get("created_at"),
        "after_created_at": after.get("created_at"),
        "added": added,
        "removed": removed,
        "changed": changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }
