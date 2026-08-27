"""Validated export/import for non-secret 4u4free configuration."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict

from .config import AppConfig, ConfigStore
from .errors import FourUFourFreeError


def export_config(store: ConfigStore, output: Path, force: bool = False) -> Path:
    destination = output.resolve(strict=False)
    if destination.exists() and not force:
        raise FourUFourFreeError(
            f"Export already exists: {destination}. Use --force to replace it."
        )
    payload = {
        "format": "4u4free-config",
        "export_version": 1,
        "config": asdict(store.load()),
    }
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)
    except OSError as exc:
        raise FourUFourFreeError(
            f"Could not export settings to {destination}: {exc}"
        ) from exc
    return destination


def read_config_export(path: Path) -> AppConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FourUFourFreeError(
            f"Could not read settings export {path}: {exc}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("format") != "4u4free-config"
        or payload.get("export_version") != 1
    ):
        raise FourUFourFreeError(f"Unsupported settings export: {path}")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise FourUFourFreeError("Settings export does not contain a config object")
    allowed = {
        "schema_version",
        "steam_root",
        "preferred_library",
        "download_source",
        "hide_adult_content",
        "confirm_downloads",
        "store_density",
        "show_store_art",
        "restart_steam_after_setup",
        "welcome_acknowledged",
        "save_vault_root",
        "save_vault_sources",
        "plugins_enabled",
        "enabled_plugins",
    }
    unknown = set(config) - allowed
    if unknown:
        raise FourUFourFreeError(
            f"Settings export contains unknown keys: {', '.join(sorted(unknown))}"
        )
    if config.get("schema_version", 1) not in {1, 2, 3}:
        raise FourUFourFreeError(
            f"Unsupported configuration schema version: {config.get('schema_version')!r}"
        )

    def optional_path(name: str):
        value = config.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise FourUFourFreeError(f"Settings export has an invalid {name!r} value")
        return value

    def choice(name: str, values: set[str], default: str) -> str:
        value = config.get(name, default)
        if not isinstance(value, str) or value not in values:
            raise FourUFourFreeError(f"Settings export has an invalid {name!r} value")
        return value

    def boolean(name: str, default: bool) -> bool:
        value = config.get(name, default)
        if not isinstance(value, bool):
            raise FourUFourFreeError(f"Settings export has an invalid {name!r} value")
        return value

    def text_mapping(name: str) -> dict[str, str]:
        value = config.get(name, {})
        if not isinstance(value, dict):
            raise FourUFourFreeError(f"Settings export has an invalid {name!r} value")
        result: dict[str, str] = {}
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(item, str)
                or not item.strip()
            ):
                raise FourUFourFreeError(
                    f"Settings export has an invalid {name!r} entry"
                )
            result[key.strip()] = item.strip()
        return result

    def text_list(name: str) -> list[str]:
        value = config.get(name, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise FourUFourFreeError(f"Settings export has an invalid {name!r} value")
        return list(dict.fromkeys(item.strip() for item in value))

    return AppConfig(
        schema_version=3,
        steam_root=optional_path("steam_root"),
        preferred_library=optional_path("preferred_library"),
        download_source=choice(
            "download_source",
            {"auto", "oureveryday", "hubcap", "ryuu", "depotbox"},
            "auto",
        ),
        hide_adult_content=boolean("hide_adult_content", True),
        confirm_downloads=boolean("confirm_downloads", True),
        store_density=choice(
            "store_density", {"compact", "comfortable"}, "comfortable"
        ),
        show_store_art=boolean("show_store_art", True),
        restart_steam_after_setup=boolean("restart_steam_after_setup", False),
        welcome_acknowledged=boolean("welcome_acknowledged", False),
        save_vault_root=optional_path("save_vault_root"),
        save_vault_sources=text_mapping("save_vault_sources"),
        plugins_enabled=boolean("plugins_enabled", False),
        enabled_plugins=text_list("enabled_plugins"),
    )


def import_config(
    store: ConfigStore, source: Path, apply: bool = False
) -> Dict[str, object]:
    config = read_config_export(source)
    result: Dict[str, object] = {
        "applied": False,
        "source": str(source.resolve(strict=False)),
        "config": asdict(config),
    }
    if not apply:
        return result
    backup = None
    if store.path.is_file():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = store.path.with_name(f"{store.path.name}.{stamp}.bak")
        try:
            shutil.copy2(store.path, backup)
        except OSError as exc:
            raise FourUFourFreeError(
                f"Could not back up current config: {exc}"
            ) from exc
    store.save(config)
    result.update(
        {
            "applied": True,
            "backup": str(backup) if backup else None,
            "destination": str(store.path),
        }
    )
    return result
