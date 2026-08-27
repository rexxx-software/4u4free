"""SQLite catalog for indexed Steam games and safely archived Lua metadata."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import default_data_dir
from .errors import FourUFourFreeError
from .lua import LuaInfo, inspect_lua
from .steam import SteamGame


SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    app_id TEXT NOT NULL,
    library TEXT NOT NULL,
    name TEXT NOT NULL,
    install_dir TEXT NOT NULL,
    build_id TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    manifest TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    PRIMARY KEY (app_id, library)
);
CREATE TABLE IF NOT EXISTS lua_files (
    sha256 TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    archived_path TEXT NOT NULL,
    inferred_app_id TEXT,
    metadata_json TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_games_name ON games(name);
CREATE INDEX IF NOT EXISTS idx_lua_app_id ON lua_files(inferred_app_id);
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise FourUFourFreeError(f"Could not hash {path}: {exc}") from exc
    return digest.hexdigest()


@dataclass(frozen=True)
class ImportResult:
    sha256: str
    archived_path: Path
    already_present: bool
    info: LuaInfo

    def to_dict(self) -> Dict[str, object]:
        return {
            "sha256": self.sha256,
            "archived_path": str(self.archived_path),
            "already_present": self.already_present,
            "metadata": self.info.to_dict(show_secrets=False),
        }


class Catalog:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or default_data_dir() / "catalog.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        return connection

    def sync_games(self, games: Iterable[SteamGame]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        rows = list(games)
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO games
                    (app_id, library, name, install_dir, build_id, last_updated, manifest, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id, library) DO UPDATE SET
                    name=excluded.name,
                    install_dir=excluded.install_dir,
                    build_id=excluded.build_id,
                    last_updated=excluded.last_updated,
                    manifest=excluded.manifest,
                    indexed_at=excluded.indexed_at
                """,
                [
                    (
                        game.app_id,
                        str(game.library),
                        game.name,
                        game.install_dir,
                        game.build_id,
                        game.last_updated,
                        str(game.manifest),
                        now,
                    )
                    for game in rows
                ],
            )
        return len(rows)

    def import_lua(
        self, source: Path, archive_dir: Optional[Path] = None
    ) -> ImportResult:
        info = inspect_lua(source)
        digest = sha256_file(source)
        archive = (archive_dir or default_data_dir() / "imports").resolve(strict=False)
        archive.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() if source.suffix else ".lua"
        destination = archive / f"{digest}{suffix}"
        already_present = destination.exists()
        if already_present:
            if destination.is_symlink():
                raise FourUFourFreeError(f"Refusing archive symlink: {destination}")
            if sha256_file(destination) != digest:
                raise FourUFourFreeError(f"Archive collision at {destination}")
        else:
            shutil.copy2(source, destination)

        metadata = info.to_dict(show_secrets=False)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO lua_files
                    (sha256, source_path, archived_path, inferred_app_id, metadata_json, imported_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(sha256) DO UPDATE SET
                    source_path=excluded.source_path,
                    archived_path=excluded.archived_path,
                    inferred_app_id=excluded.inferred_app_id,
                    metadata_json=excluded.metadata_json
                """,
                (
                    digest,
                    str(source.resolve(strict=False)),
                    str(destination),
                    info.inferred_app_id,
                    json.dumps(metadata),
                    now,
                ),
            )
        return ImportResult(digest, destination, already_present, info)

    def games(self, query: Optional[str] = None) -> List[Dict[str, object]]:
        with self._connect() as connection:
            if query:
                pattern = f"%{query}%"
                rows = connection.execute(
                    "SELECT * FROM games WHERE name LIKE ? OR app_id LIKE ? ORDER BY name COLLATE NOCASE",
                    (pattern, pattern),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM games ORDER BY name COLLATE NOCASE"
                ).fetchall()
        return [dict(row) for row in rows]

    def lua_files(self, app_id: Optional[str] = None) -> List[Dict[str, object]]:
        with self._connect() as connection:
            if app_id:
                rows = connection.execute(
                    "SELECT * FROM lua_files WHERE inferred_app_id = ? ORDER BY imported_at DESC",
                    (app_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM lua_files ORDER BY imported_at DESC"
                ).fetchall()
        result: List[Dict[str, object]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(str(item.pop("metadata_json")))
            result.append(item)
        return result

    def stats(self) -> Dict[str, object]:
        with self._connect() as connection:
            games = connection.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            lua_files = connection.execute("SELECT COUNT(*) FROM lua_files").fetchone()[
                0
            ]
            libraries = connection.execute(
                "SELECT COUNT(DISTINCT library) FROM games"
            ).fetchone()[0]
        return {
            "catalog": str(self.path),
            "games": games,
            "lua_files": lua_files,
            "libraries": libraries,
        }
