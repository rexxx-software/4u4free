# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import gzip
import json
import logging
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

import httpx

from four_u_four_free._compat.core.utils import app_data_dir

logger = logging.getLogger(__name__)

PROVIDER_URLS = [
    "https://raw.githubusercontent.com/KoriaPolis/Steam-Depot/main/fallback_depotkeys.json",
    "https://pub-d3ba7941fdf24c2c84da530b93221e1c.r2.dev/fallback_depotkeys.json",
]
ALLOWED_FIELDS = {"id", "key", "name", "kind", "parent_appid", "parent_name"}
ALLOWED_KINDS = {"game", "software", "dlc", "depot", "dlc_depot", "unknown"}
ROOT_KINDS = {"game", "software"}
PROVIDER_REFRESH_INTERVAL_SECONDS = 6 * 60 * 60

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ID_RE = re.compile(r"^\d+$")
_ADDAPPID_KEY_RE = re.compile(
    r"addappid\s*\(\s*(\d+)\s*,\s*[01]\s*,\s*[\"']([0-9a-fA-F]{64})[\"']\s*\)"
)
_ADDAPPID_KEY_LINE_RE = re.compile(
    r"addappid\s*\(\s*(\d+)\s*,\s*[01]\s*,\s*[\"']([0-9a-fA-F]{64})[\"']\s*\)"
    r"\s*(?:--\s*(.*))?$",
    re.IGNORECASE,
)
_ADDAPPID_PLAIN_LINE_RE = re.compile(
    r"addappid\s*\(\s*(\d+)\s*\)\s*(?:--\s*(.*))?$",
    re.IGNORECASE,
)

# ── Scan gates for the anonymous pool ─────────────────────────────
_SCAN_GATE_K1 = bytes([0x5E, 0x2A, 0x91, 0xC7])
_SCAN_GATE_K2 = bytes([0x33, 0x8D, 0xA2, 0x11, 0x7F])
_SCAN_GATE_K3 = bytes([0xA7, 0x4E, 0xD4, 0x19, 0x7C])
_SCAN_GATE_P0 = bytes([26, 69, 230, 169])
_SCAN_GATE_P1 = bytes([86, 233, 195, 126, 19])
_SCAN_GATE_P2 = bytes([117, 49, 134, 132])
_SCAN_GATE_P3 = bytes([56, 57, 179, 32, 206])
_SCAN_GATE_P4 = bytes([101, 115, 111, 119, 66, 114, 120])


def bundled_provider_path() -> Path:
    return Path(__file__).resolve().parent / "fallback_depotkeys.json.gz"


def installed_provider_path() -> Path:
    """Persistent bundled-provider path beside a frozen one-dir EXE.

    In source/dev this points at <repo>/_internal/... and usually does not
    exist. In a PyInstaller one-dir build it points at:
      <exe_dir>/_internal/four_u_four_free/_compat/lua/fallback_depotkeys.json.gz
    """
    return (
        app_data_dir()
        / "_internal"
        / "four_u_four_free"
        / "_compat"
        / "lua"
        / "fallback_depotkeys.json.gz"
    )


def provider_file_candidates() -> list[Path]:
    paths: list[Path] = []
    for path in (bundled_provider_path(), installed_provider_path(), cache_path()):
        if path not in paths:
            paths.append(path)
    return paths


def cache_dir() -> Path:
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        d = app_data_dir() / "provider_cache"
    else:
        d = bundled_provider_path().parent
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_path() -> Path:
    return cache_dir() / "fallback_depotkeys.json"


def is_valid_id(value) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def is_valid_key(value) -> bool:
    return (
        isinstance(value, str)
        and bool(_HEX64_RE.fullmatch(value))
        and value.strip("0") != ""
    )


def _clean_text(value) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:160]


def _strip_parent_for_root(item: dict) -> dict:
    kind = str(item.get("kind") or "unknown").strip().lower()
    if kind in ROOT_KINDS:
        item.pop("parent_appid", None)
        item.pop("parent_name", None)
    return item


def normalize_entry(item_id: str, value) -> dict | None:
    if not is_valid_id(str(item_id)):
        return None
    if isinstance(value, str):
        value = {"key": value}
    if not isinstance(value, dict):
        return None
    kind = str(value.get("kind") or "unknown").strip().lower()
    if kind not in ALLOWED_KINDS:
        kind = "unknown"
    out = {
        "id": str(item_id),
        "key": str(value.get("key") or "").strip().lower(),
        "name": _clean_text(value.get("name")),
        "kind": kind,
        "parent_appid": str(value.get("parent_appid") or "").strip(),
        "parent_name": _clean_text(value.get("parent_name")),
    }
    if out["parent_appid"] and not is_valid_id(out["parent_appid"]):
        out["parent_appid"] = ""
    if out["kind"] in ROOT_KINDS:
        out["parent_appid"] = ""
        out["parent_name"] = ""
    return out


def validate_provider_data(data) -> dict[str, dict]:
    if not isinstance(data, dict):
        raise ValueError("provider root must be an object")
    cleaned: dict[str, dict] = {}
    for item_id, value in data.items():
        entry = normalize_entry(str(item_id), value)
        if entry is None:
            continue
        out = {k: entry[k] for k in ("key", "name", "kind")}
        if entry.get("kind") not in ROOT_KINDS:
            if entry.get("parent_appid"):
                out["parent_appid"] = entry["parent_appid"]
            if entry.get("parent_name"):
                out["parent_name"] = entry["parent_name"]
        cleaned[entry["id"]] = out
    return dict(sorted(cleaned.items(), key=lambda kv: int(kv[0])))


def load_provider_file(path: Path) -> dict[str, dict]:
    if path.suffix.casefold() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    return validate_provider_data(data)


def load_provider() -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for path in provider_file_candidates():
        if not path.exists():
            continue
        try:
            data = load_provider_file(path)
        except Exception as exc:
            logger.warning("provider load failed for %s: %s", path, exc)
            continue
        merged.update(data)
    return _strip_provider_metadata(merged)


_PROVIDER_KEY_FIELDS = frozenset({"key"})


def _strip_provider_metadata(data: dict[str, dict]) -> dict[str, dict]:
    """Drop non-essential fields from provider entries to save RAM.
    Each entry normally has ~5 keys (key, name, kind, parent_appid, parent_name).
    After stripping, only the 'key' field is kept per entry, saving ~80% memory
    for the 364K-entry provider dict.
    """
    stripped: dict[str, dict] = {}
    for appid, entry in data.items():
        if isinstance(entry, dict):
            slim = {k: v for k, v in entry.items() if k in _PROVIDER_KEY_FIELDS}
            stripped[appid] = slim
        else:
            stripped[appid] = entry
    return stripped


def get_key(item_id: str) -> str:
    entry = load_provider().get(str(item_id))
    if not isinstance(entry, dict):
        return ""
    key = str(entry.get("key") or "")
    return key if is_valid_key(key) else ""


def get_entry(item_id: str) -> dict:
    entry = load_provider().get(str(item_id))
    return dict(entry) if isinstance(entry, dict) else {}


def atomic_save_provider(data: dict[str, dict], path: Path | None = None) -> Path:
    path = path or cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = validate_provider_data(data)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2, ensure_ascii=False)
            f.write("\n")
        tmp_path.replace(path)
        return path
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def _writable_provider_update_targets() -> list[Path]:
    targets = [cache_path()]
    for path in (bundled_provider_path(), installed_provider_path()):
        if path in targets:
            continue
        if path.exists() or path.parent.exists():
            targets.append(path)
    return targets


def _provider_epoch(value) -> int:
    try:
        return max(0, int(float(str(value or "0"))))
    except (TypeError, ValueError):
        return 0


def provider_update_state(now: int | None = None) -> dict:
    from four_u_four_free._compat.core.storage.settings import get_setting
    from four_u_four_free._compat.core.structs import Settings

    now = int(time.time()) if now is None else int(now)
    last_attempt = _provider_epoch(get_setting(Settings.PROVIDER_LAST_UPDATE_ATTEMPT))
    last_success = _provider_epoch(get_setting(Settings.PROVIDER_LAST_UPDATE_SUCCESS))
    last_error = str(get_setting(Settings.PROVIDER_LAST_UPDATE_ERROR) or "")
    age = now - last_attempt if last_attempt else None
    return {
        "last_attempt_at": last_attempt,
        "last_success_at": last_success,
        "last_error": last_error,
        "next_due_at": (last_attempt + PROVIDER_REFRESH_INTERVAL_SECONDS)
        if last_attempt
        else 0,
        "due": not last_attempt
        or age is None
        or age >= PROVIDER_REFRESH_INTERVAL_SECONDS,
        "interval_seconds": PROVIDER_REFRESH_INTERVAL_SECONDS,
    }


def provider_update_due(now: int | None = None) -> bool:
    return bool(provider_update_state(now).get("due"))


def _record_provider_update_attempt(
    result: dict, attempted_at: int | None = None
) -> dict:
    from four_u_four_free._compat.core.storage.settings import set_setting
    from four_u_four_free._compat.core.structs import Settings

    attempted_at = int(time.time()) if attempted_at is None else int(attempted_at)
    ok = bool(result.get("ok"))
    error = (
        ""
        if ok
        else "; ".join(str(x) for x in (result.get("errors") or []) if str(x).strip())
    )
    set_setting(Settings.PROVIDER_LAST_UPDATE_ATTEMPT, str(attempted_at))
    set_setting(Settings.PROVIDER_LAST_UPDATE_CHECK, str(attempted_at))
    if ok:
        set_setting(Settings.PROVIDER_LAST_UPDATE_SUCCESS, str(attempted_at))
        set_setting(Settings.PROVIDER_LAST_UPDATE_ERROR, "")
    else:
        set_setting(
            Settings.PROVIDER_LAST_UPDATE_ERROR, error or "Provider update failed"
        )
    result.update(provider_update_state())
    return result


def download_provider_update(
    urls: Iterable[str] = PROVIDER_URLS, timeout: float = 20.0
) -> dict:
    attempted_at = int(time.time())
    errors: list[str] = []
    for url in urls:
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            if resp.status_code != 200:
                errors.append(f"{url}: HTTP {resp.status_code}")
                continue
            data = validate_provider_data(resp.json())
            saved_paths: list[str] = []
            save_errors: list[str] = []
            for target in _writable_provider_update_targets():
                try:
                    atomic_save_provider(data, target)
                    saved_paths.append(str(target))
                except Exception as exc:
                    save_errors.append(f"{target}: {exc}")
            if not saved_paths:
                errors.extend(save_errors)
                continue
            return _record_provider_update_attempt(
                {
                    "ok": True,
                    "url": url,
                    "count": len(data),
                    "paths": saved_paths,
                    "save_errors": save_errors,
                    "errors": errors,
                },
                attempted_at,
            )
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    return _record_provider_update_attempt(
        {"ok": False, "errors": errors}, attempted_at
    )


def update_cache_from_lua_bytes(
    lua_bytes: bytes, app_id: str = "", app_name: str = ""
) -> int:
    text = lua_bytes.decode("utf-8", errors="ignore")
    pairs = _ADDAPPID_KEY_RE.findall(text)
    if not pairs:
        return 0
    data = load_provider()
    added = 0
    for depot_id, key in pairs:
        if not is_valid_key(key):
            continue
        existing = data.get(depot_id) or {}
        if existing.get("key"):
            continue
        is_root = str(app_id or "") == str(depot_id) and bool(app_name)
        entry = {
            "key": key.lower(),
            "name": existing.get("name")
            or (_clean_text(app_name) if is_root else f"Depot {depot_id}"),
            "kind": existing.get("kind") or ("game" if is_root else "depot"),
            "parent_appid": ""
            if is_root
            else (existing.get("parent_appid") or str(app_id or "")),
            "parent_name": ""
            if is_root
            else (existing.get("parent_name") or _clean_text(app_name)),
        }
        data[depot_id] = _strip_parent_for_root(entry)
        added += 1
    if added:
        atomic_save_provider(data)
    return added
