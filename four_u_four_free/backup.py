"""Recoverable, checksummed backups of the Steam files 4u4free may later manage."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .config import default_data_dir
from .errors import FourUFourFreeError


@dataclass(frozen=True)
class BackupResult:
    destination: Path
    files: List[Path]
    manifest: Path

    def to_dict(self) -> Dict[str, object]:
        return {
            "destination": str(self.destination),
            "files": [str(path) for path in self.files],
            "manifest": str(self.manifest),
        }


def _source_files(steam_root: Path, libraries: Iterable[Path]) -> Iterable[Tuple[Path, Path, Path]]:
    fixed = (
        steam_root / "config" / "config.vdf",
        steam_root / "steamapps" / "libraryfolders.vdf",
    )
    for path in fixed:
        if path.is_file() and not path.is_symlink():
            yield path, steam_root, path.relative_to(steam_root)
    plugin_dir = steam_root / "config" / "stplug-in"
    if plugin_dir.is_dir():
        for path in sorted(plugin_dir.glob("*.lua")):
            if path.is_file() and not path.is_symlink():
                yield path, steam_root, path.relative_to(steam_root)
    seen = set()
    for library in libraries:
        library = library.resolve(strict=False)
        key = str(library).casefold()
        if key in seen:
            continue
        seen.add(key)
        steamapps = library / "steamapps"
        if steamapps.is_dir():
            for path in sorted(steamapps.glob("appmanifest_*.acf")):
                if path.is_file() and not path.is_symlink():
                    yield path, library, path.relative_to(library)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_backup(
    steam_root: Path,
    output: Optional[Path] = None,
    libraries: Optional[Iterable[Path]] = None,
) -> BackupResult:
    root = steam_root.resolve(strict=False)
    if not root.is_dir():
        raise FourUFourFreeError(f"Steam root does not exist: {root}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = (output or default_data_dir() / "backups" / stamp).resolve(strict=False)
    if destination.exists():
        raise FourUFourFreeError(f"Backup destination already exists: {destination}")

    records: List[Dict[str, object]] = []
    copied: List[Path] = []
    library_roots = list(libraries) if libraries is not None else [root]
    normalized_libraries = [path.resolve(strict=False) for path in library_roots]
    if root not in normalized_libraries:
        normalized_libraries.insert(0, root)
    root_labels = {str(path).casefold(): ("steam" if path == root else f"library-{index}") for index, path in enumerate(normalized_libraries)}
    try:
        destination.mkdir(parents=True, exist_ok=False)
        for source, target_root, target_relative in _source_files(root, normalized_libraries):
            label = root_labels[str(target_root).casefold()]
            backup_relative = Path("roots") / label / target_relative
            target = destination / backup_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target)
            records.append(
                {
                    "source": str(source),
                    "backup": backup_relative.as_posix(),
                    "target_root": str(target_root),
                    "target": target_relative.as_posix(),
                    "size": target.stat().st_size,
                    "sha256": _sha256(target),
                }
            )
        manifest = destination / "backup-manifest.json"
        payload = {
            "schema_version": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "steam_root": str(root),
            "libraries": [str(path) for path in normalized_libraries],
            "files": records,
        }
        manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise FourUFourFreeError(f"Backup failed in {destination}: {exc}") from exc
    return BackupResult(destination, copied, manifest)
