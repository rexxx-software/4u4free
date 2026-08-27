"""Versioned, hash-verified local save snapshots.

The vault never guesses during restore: the user selects a source directory,
every archive is hash-verified, and an existing destination is snapshotted
before files are overlaid.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import default_data_dir
from .errors import FourUFourFreeError
from .profiles import list_profiles


METADATA_SUFFIX = ".snapshot.json"


def _require_app_id(value: str | int) -> str:
    text = str(value).strip()
    if not text.isdigit() or int(text) <= 0:
        raise FourUFourFreeError("Choose a game with a valid App ID.")
    return text


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _folder_has_files(path: Path) -> bool:
    try:
        return path.is_dir() and any(item.is_file() for item in path.rglob("*"))
    except OSError:
        return False


@dataclass(frozen=True)
class VaultSnapshot:
    snapshot_id: str
    app_id: str
    game_name: str
    source_path: str
    archive_path: str
    created_at: str
    file_count: int
    total_size: int
    sha256: str
    reason: str = "manual"

    @classmethod
    def from_dict(cls, value: dict) -> "VaultSnapshot":
        try:
            return cls(
                snapshot_id=str(value["snapshot_id"]),
                app_id=_require_app_id(value["app_id"]),
                game_name=str(value.get("game_name") or ""),
                source_path=str(value["source_path"]),
                archive_path=str(value["archive_path"]),
                created_at=str(value["created_at"]),
                file_count=max(0, int(value["file_count"])),
                total_size=max(0, int(value["total_size"])),
                sha256=str(value["sha256"]).lower(),
                reason=str(value.get("reason") or "manual"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FourUFourFreeError("Save Vault metadata is invalid.") from exc


@dataclass(frozen=True)
class RestoreResult:
    restored_files: int
    destination: str
    safety_snapshot: VaultSnapshot | None


class SaveVault:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else default_data_dir() / "save-vault"
        self.root = self.root.expanduser().resolve(strict=False)

    def _app_root(self, app_id: str | int) -> Path:
        return self.root / _require_app_id(app_id)

    def create_snapshot(
        self,
        app_id: str | int,
        game_name: str,
        source: Path | str,
        *,
        reason: str = "manual",
    ) -> VaultSnapshot:
        normalized_app_id = _require_app_id(app_id)
        source_path = Path(source).expanduser().resolve(strict=True)
        if not source_path.is_dir():
            raise FourUFourFreeError("Save Vault currently snapshots directories only.")
        if _within(self.root, source_path) or _within(source_path, self.root):
            raise FourUFourFreeError(
                "The selected save folder and Save Vault folder cannot contain each other."
            )

        files: list[tuple[Path, Path]] = []
        total_size = 0
        try:
            for candidate in source_path.rglob("*"):
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                relative = candidate.relative_to(source_path)
                files.append((candidate, relative))
                total_size += candidate.stat().st_size
        except OSError as exc:
            raise FourUFourFreeError(
                f"Could not scan save folder {source_path}: {exc}"
            ) from exc
        if not files:
            raise FourUFourFreeError("The selected save folder contains no files.")

        app_root = self._app_root(normalized_app_id)
        app_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot_id = f"snapshot_{stamp}"
        archive = app_root / f"{snapshot_id}.zip"
        metadata = app_root / f"{snapshot_id}{METADATA_SUFFIX}"
        temporary_archive = archive.with_suffix(".zip.tmp")
        temporary_metadata = metadata.with_suffix(metadata.suffix + ".tmp")

        try:
            with zipfile.ZipFile(
                temporary_archive,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as bundle:
                for path, relative in files:
                    bundle.write(path, relative.as_posix())
            digest = _sha256(temporary_archive)
            snapshot = VaultSnapshot(
                snapshot_id=snapshot_id,
                app_id=normalized_app_id,
                game_name=str(game_name).strip() or f"App {normalized_app_id}",
                source_path=str(source_path),
                archive_path=str(archive),
                created_at=datetime.now(timezone.utc).isoformat(),
                file_count=len(files),
                total_size=total_size,
                sha256=digest,
                reason=str(reason).strip() or "manual",
            )
            temporary_metadata.write_text(
                json.dumps(asdict(snapshot), indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_archive.replace(archive)
            temporary_metadata.replace(metadata)
            return snapshot
        except (OSError, zipfile.BadZipFile) as exc:
            temporary_archive.unlink(missing_ok=True)
            temporary_metadata.unlink(missing_ok=True)
            raise FourUFourFreeError(
                f"Could not create Save Vault snapshot: {exc}"
            ) from exc

    def list_snapshots(self, app_id: str | int) -> list[VaultSnapshot]:
        app_root = self._app_root(app_id)
        if not app_root.is_dir():
            return []
        snapshots: list[VaultSnapshot] = []
        for metadata in app_root.glob(f"snapshot_*{METADATA_SUFFIX}"):
            try:
                value = json.loads(metadata.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    continue
                snapshot = VaultSnapshot.from_dict(value)
                archive = Path(snapshot.archive_path).resolve(strict=False)
                if (
                    snapshot.app_id == _require_app_id(app_id)
                    and _within(archive, app_root.resolve(strict=False))
                    and archive.is_file()
                ):
                    snapshots.append(snapshot)
            except (OSError, json.JSONDecodeError, FourUFourFreeError):
                continue
        return sorted(snapshots, key=lambda item: item.created_at, reverse=True)

    def verify_snapshot(self, snapshot: VaultSnapshot) -> bool:
        archive = Path(snapshot.archive_path).resolve(strict=False)
        app_root = self._app_root(snapshot.app_id).resolve(strict=False)
        return (
            _within(archive, app_root)
            and archive.is_file()
            and _sha256(archive) == snapshot.sha256
        )

    def restore_snapshot(
        self,
        snapshot: VaultSnapshot,
        destination: Path | str | None = None,
    ) -> RestoreResult:
        if not self.verify_snapshot(snapshot):
            raise FourUFourFreeError(
                "The selected Save Vault archive is missing or failed SHA-256 verification."
            )
        target = (
            Path(destination or snapshot.source_path).expanduser().resolve(strict=False)
        )
        if _within(self.root, target) or _within(target, self.root):
            raise FourUFourFreeError(
                "The restore destination and Save Vault folder cannot contain each other."
            )

        safety = None
        if _folder_has_files(target):
            safety = self.create_snapshot(
                snapshot.app_id,
                snapshot.game_name,
                target,
                reason=f"before_restore_{snapshot.snapshot_id}",
            )

        archive = Path(snapshot.archive_path)
        temporary_root = Path(tempfile.mkdtemp(prefix="4u4free-vault-"))
        restored = 0
        try:
            with zipfile.ZipFile(archive, "r") as bundle:
                for member in bundle.infolist():
                    relative = Path(member.filename)
                    if (
                        member.is_dir()
                        or relative.is_absolute()
                        or relative.drive
                        or ".." in relative.parts
                    ):
                        if member.is_dir():
                            continue
                        raise FourUFourFreeError(
                            "The snapshot contains an unsafe path."
                        )
                    extracted = temporary_root / relative
                    extracted.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        bundle.open(member, "r") as source_handle,
                        extracted.open("wb") as output,
                    ):
                        shutil.copyfileobj(source_handle, output)

            target.mkdir(parents=True, exist_ok=True)
            for path in temporary_root.rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(temporary_root)
                output = target / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, output)
                restored += 1
        except (OSError, zipfile.BadZipFile) as exc:
            raise FourUFourFreeError(
                f"Could not restore Save Vault snapshot: {exc}"
            ) from exc
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)

        return RestoreResult(restored, str(target), safety)


def discover_save_folders(
    app_id: str | int,
    game_name: str,
    *,
    steam_root: Path | None = None,
) -> list[Path]:
    """Return conservative existing save-folder candidates without modifying them."""
    normalized_app_id = _require_app_id(app_id)
    name = str(game_name).strip()
    candidates: list[Path] = []

    if steam_root is not None:
        try:
            profiles = list_profiles(Path(steam_root))
        except FourUFourFreeError:
            profiles = []
        for profile in profiles:
            candidates.append(profile.userdata / normalized_app_id / "remote")

    if name:
        user_home = Path(os.environ.get("USERPROFILE") or Path.home())
        roaming = Path(os.environ.get("APPDATA") or user_home / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or user_home / "AppData" / "Local")
        candidates.extend(
            [
                user_home / "Documents" / "My Games" / name,
                user_home / "Documents" / name,
                user_home / "Saved Games" / name,
                roaming / name,
                local / name,
                local.parent / "LocalLow" / name,
            ]
        )

    results: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.expanduser().resolve(strict=False)
        key = os.path.normcase(str(normalized))
        if key not in seen and _folder_has_files(normalized):
            seen.add(key)
            results.append(normalized)
    return results


def format_bytes(value: int) -> str:
    size = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
