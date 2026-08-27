"""Verify and restore 4u4free backup manifests with strict path checks."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from .backup import BackupResult, create_backup
from .catalog import sha256_file
from .errors import FourUFourFreeError
from .steam import list_libraries


@dataclass(frozen=True)
class VerificationResult:
    backup: Path
    valid: bool
    checked: int
    missing: List[str]
    mismatched: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "backup": str(self.backup),
            "valid": self.valid,
            "checked": self.checked,
            "missing": self.missing,
            "mismatched": self.mismatched,
        }


def _load_manifest(backup_dir: Path) -> Dict[str, object]:
    path = backup_dir / "backup-manifest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FourUFourFreeError(f"Could not read backup manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise FourUFourFreeError(f"Invalid backup manifest: {path}")
    return value


def _normalized_relative(value: object, label: str) -> Path:
    if not isinstance(value, str):
        raise FourUFourFreeError(f"Backup entry has a non-string {label} path")
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise FourUFourFreeError(f"Unsafe {label} path in backup manifest: {value!r}")
    return Path(*pure.parts)


def _safe_backup_relative(value: object) -> Path:
    path = _normalized_relative(value, "backup")
    if len(path.parts) < 4 or path.parts[0] != "roots":
        raise FourUFourFreeError(f"Backup file path is outside the archive layout: {value!r}")
    return path


def _safe_target_relative(value: object) -> Path:
    path = _normalized_relative(value, "target")
    pure = PurePosixPath(path.as_posix())
    allowed = (
        len(pure.parts) == 2 and pure.parts[0] == "config" and pure.parts[1] == "config.vdf",
        len(pure.parts) == 3 and pure.parts[:2] == ("config", "stplug-in") and pure.suffix.lower() == ".lua",
        len(pure.parts) == 2 and pure.parts[0] == "steamapps" and pure.parts[1] == "libraryfolders.vdf",
        len(pure.parts) == 2 and pure.parts[0] == "steamapps" and pure.name.startswith("appmanifest_") and pure.suffix == ".acf",
    )
    if not any(allowed):
        raise FourUFourFreeError(f"Backup target is outside the restore allowlist: {value!r}")
    return path


def _entry_paths(entry: Dict[str, object], schema_version: int) -> tuple[Path, Path]:
    if schema_version >= 2:
        return _safe_backup_relative(entry.get("backup")), _safe_target_relative(entry.get("target"))
    legacy = _safe_target_relative(entry.get("backup"))
    return legacy, legacy


def verify_backup(backup_dir: Path) -> VerificationResult:
    root = backup_dir.resolve(strict=False)
    manifest = _load_manifest(root)
    schema_version = int(manifest.get("schema_version", 1))
    missing: List[str] = []
    mismatched: List[str] = []
    checked = 0
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise FourUFourFreeError("Backup manifest contains a non-object file entry")
        relative, _ = _entry_paths(entry, schema_version)
        expected = entry.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise FourUFourFreeError(f"Invalid SHA-256 for {relative}")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            missing.append(str(relative))
            continue
        checked += 1
        if sha256_file(path) != expected.lower():
            mismatched.append(str(relative))
    return VerificationResult(root, not missing and not mismatched, checked, missing, mismatched)


def _reject_symlink_path(root: Path, relative: Path) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise FourUFourFreeError(f"Refusing restore through symlink: {current}")


def restore_backup(
    backup_dir: Path,
    steam_root: Path,
    apply: bool = False,
    pre_restore_output: Optional[Path] = None,
) -> Dict[str, object]:
    verification = verify_backup(backup_dir)
    if not verification.valid:
        raise FourUFourFreeError("Backup verification failed; restore was refused")
    root = steam_root.resolve(strict=False)
    if not root.is_dir():
        raise FourUFourFreeError(f"Steam root does not exist: {root}")
    manifest = _load_manifest(verification.backup)
    schema_version = int(manifest.get("schema_version", 1))
    allowed_roots = {str(path.resolve(strict=False)).casefold(): path.resolve(strict=False) for path in list_libraries(root)}
    allowed_roots[str(root).casefold()] = root
    resolved_entries = []
    for entry in manifest["files"]:
        backup_relative, target_relative = _entry_paths(entry, schema_version)
        target_root_value = entry.get("target_root", str(root)) if schema_version >= 2 else str(root)
        if not isinstance(target_root_value, str):
            raise FourUFourFreeError("Backup entry has a non-string target root")
        target_root = Path(target_root_value).resolve(strict=False)
        allowed_root = allowed_roots.get(str(target_root).casefold())
        if allowed_root is None:
            raise FourUFourFreeError(f"Backup targets an unregistered Steam library: {target_root}")
        _reject_symlink_path(allowed_root, target_relative)
        resolved_entries.append((entry, backup_relative, allowed_root, target_relative))
    targets = [str(target_root / target_relative) for _, _, target_root, target_relative in resolved_entries]
    if not apply:
        return {"applied": False, "verified": verification.to_dict(), "targets": targets, "pre_restore_backup": None}

    pre_restore: Optional[BackupResult] = create_backup(root, pre_restore_output, allowed_roots.values())
    restored: List[str] = []
    try:
        for _, backup_relative, target_root, target_relative in resolved_entries:
            source = verification.backup / backup_relative
            target = target_root / target_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored.append(str(target))
    except OSError as exc:
        raise FourUFourFreeError(
            f"Restore stopped after {len(restored)} files: {exc}. Pre-restore backup: {pre_restore.destination}"
        ) from exc
    return {
        "applied": True,
        "verified": verification.to_dict(),
        "targets": targets,
        "restored": restored,
        "pre_restore_backup": str(pre_restore.destination),
    }
