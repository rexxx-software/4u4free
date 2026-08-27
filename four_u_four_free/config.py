"""Simple, inspectable JSON configuration. No credentials are stored here."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .errors import FourUFourFreeError


def default_data_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "4u4free"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "4u4free"


@dataclass
class AppConfig:
    schema_version: int = 3
    steam_root: Optional[str] = None
    preferred_library: Optional[str] = None
    download_source: str = "auto"
    hide_adult_content: bool = True
    confirm_downloads: bool = True
    store_density: str = "comfortable"
    show_store_art: bool = True
    restart_steam_after_setup: bool = False
    welcome_acknowledged: bool = False
    save_vault_root: Optional[str] = None
    save_vault_sources: dict[str, str] = field(default_factory=dict)
    plugins_enabled: bool = False
    enabled_plugins: list[str] = field(default_factory=list)


class ConfigStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or default_data_dir() / "config.json"

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FourUFourFreeError(f"Could not load config {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise FourUFourFreeError(f"Config {self.path} must contain a JSON object")
        return AppConfig(
            schema_version=3,
            steam_root=_optional_text(raw.get("steam_root")),
            preferred_library=_optional_text(raw.get("preferred_library")),
            download_source=_choice(
                raw.get("download_source"),
                {"auto", "oureveryday", "hubcap", "ryuu", "depotbox"},
                "auto",
            ),
            hide_adult_content=_boolean(raw.get("hide_adult_content"), True),
            confirm_downloads=_boolean(raw.get("confirm_downloads"), True),
            store_density=_choice(
                raw.get("store_density"),
                {"compact", "comfortable"},
                "comfortable",
            ),
            show_store_art=_boolean(raw.get("show_store_art"), True),
            restart_steam_after_setup=_boolean(
                raw.get("restart_steam_after_setup"), False
            ),
            welcome_acknowledged=_boolean(
                raw.get("welcome_acknowledged"), False
            ),
            save_vault_root=_optional_text(raw.get("save_vault_root")),
            save_vault_sources=_text_mapping(raw.get("save_vault_sources")),
            plugins_enabled=_boolean(raw.get("plugins_enabled"), False),
            enabled_plugins=_text_list(raw.get("enabled_plugins")),
        )

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        except OSError as exc:
            raise FourUFourFreeError(f"Could not save config {self.path}: {exc}") from exc


def _optional_text(value) -> Optional[str]:
    return value if isinstance(value, str) and value.strip() else None


def _choice(value, choices: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in choices else default


def _boolean(value, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _text_mapping(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        normalized_value = str(item).strip() if isinstance(item, str) else ""
        if normalized_key and normalized_value:
            result[normalized_key] = normalized_value
    return result


def _text_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        normalized = str(item).strip() if isinstance(item, str) else ""
        if normalized and normalized not in result:
            result.append(normalized)
    return result
