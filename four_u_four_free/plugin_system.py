"""Opt-in local plugin discovery and loading.

Plugins are ordinary Python and therefore run with the same permissions as
4u4free. They are never imported unless the global switch and the individual
plugin switch are both enabled.
"""

from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterable

from .config import default_data_dir
from .errors import FourUFourFreeError


PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
KNOWN_PERMISSIONS = {"installed_games", "network", "filesystem", "process"}


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    description: str
    author: str
    entrypoint: str
    permissions: tuple[str, ...]
    directory: Path


@dataclass(frozen=True)
class PluginTool:
    plugin_id: str
    title: str
    description: str
    callback: Callable[[], object]


@dataclass(frozen=True)
class PluginState:
    manifest: PluginManifest
    enabled: bool
    status: str


class PluginAPI:
    def __init__(
        self,
        manifest: PluginManifest,
        games: Iterable[dict],
        log: Callable[[str], None],
    ):
        self.manifest = manifest
        self._games = tuple(dict(game) for game in games)
        self._log = log
        self.tools: list[PluginTool] = []

    def installed_games(self) -> tuple[dict, ...]:
        if "installed_games" not in self.manifest.permissions:
            raise FourUFourFreeError(
                f"Plugin {self.manifest.name} did not declare installed_games permission."
            )
        return tuple(dict(game) for game in self._games)

    def log(self, message: object) -> None:
        self._log(f"Plugin {self.manifest.name}: {message}")

    def register_tool(
        self,
        title: str,
        description: str,
        callback: Callable[[], object],
    ) -> None:
        normalized = str(title).strip()
        if not normalized or not callable(callback):
            raise FourUFourFreeError("Plugin tools require a title and callable callback.")
        self.tools.append(
            PluginTool(
                self.manifest.plugin_id,
                normalized,
                str(description).strip(),
                callback,
            )
        )


class PluginManager:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else default_data_dir() / "plugins"
        self.root = self.root.expanduser().resolve(strict=False)
        self.modules: list[ModuleType] = []
        self.tools: list[PluginTool] = []

    def discover(self) -> list[PluginManifest]:
        if not self.root.is_dir():
            return []
        manifests: list[PluginManifest] = []
        for folder in sorted(self.root.iterdir(), key=lambda item: item.name.lower()):
            manifest_path = folder / "plugin.json"
            if not folder.is_dir() or not manifest_path.is_file():
                continue
            manifests.append(self._read_manifest(folder, manifest_path))
        return manifests

    def _read_manifest(self, folder: Path, path: Path) -> PluginManifest:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FourUFourFreeError(f"Invalid plugin manifest {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise FourUFourFreeError(f"Plugin manifest {path} must be a JSON object.")
        plugin_id = str(raw.get("id") or "").strip().lower()
        if not PLUGIN_ID_RE.fullmatch(plugin_id):
            raise FourUFourFreeError(f"Plugin manifest {path} has an invalid id.")
        entrypoint = str(raw.get("entrypoint") or "plugin.py").strip()
        target = (folder / entrypoint).resolve(strict=False)
        try:
            target.relative_to(folder.resolve(strict=False))
        except ValueError as exc:
            raise FourUFourFreeError(
                f"Plugin {plugin_id} entrypoint must stay inside its plugin folder."
            ) from exc
        if target.suffix.lower() != ".py" or not target.is_file():
            raise FourUFourFreeError(f"Plugin {plugin_id} entrypoint was not found: {target}")
        permissions_raw = raw.get("permissions") or []
        if not isinstance(permissions_raw, list):
            raise FourUFourFreeError(f"Plugin {plugin_id} permissions must be a list.")
        permissions = tuple(dict.fromkeys(str(item).strip() for item in permissions_raw))
        unknown = sorted(set(permissions) - KNOWN_PERMISSIONS)
        if unknown:
            raise FourUFourFreeError(
                f"Plugin {plugin_id} declares unknown permissions: {', '.join(unknown)}"
            )
        return PluginManifest(
            plugin_id=plugin_id,
            name=str(raw.get("name") or plugin_id).strip(),
            version=str(raw.get("version") or "0.0.0").strip(),
            description=str(raw.get("description") or "").strip(),
            author=str(raw.get("author") or "Unknown").strip(),
            entrypoint=entrypoint,
            permissions=permissions,
            directory=folder.resolve(strict=False),
        )

    def load(
        self,
        *,
        globally_enabled: bool,
        enabled_ids: Iterable[str],
        games: Iterable[dict] = (),
        log: Callable[[str], None] | None = None,
    ) -> list[PluginState]:
        self.modules.clear()
        self.tools.clear()
        enabled = {str(item).strip().lower() for item in enabled_ids}
        output: list[PluginState] = []
        logger = log or (lambda _message: None)
        for manifest in self.discover():
            selected = globally_enabled and manifest.plugin_id in enabled
            if not selected:
                output.append(PluginState(manifest, False, "Disabled"))
                continue
            try:
                target = manifest.directory / manifest.entrypoint
                module_name = f"four_u_four_free_user_plugin_{manifest.plugin_id.replace('.', '_')}"
                spec = importlib.util.spec_from_file_location(module_name, target)
                if spec is None or spec.loader is None:
                    raise FourUFourFreeError("Python could not create a module loader.")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                setup = getattr(module, "setup", None)
                if not callable(setup):
                    raise FourUFourFreeError("entrypoint must define setup(api).")
                api = PluginAPI(manifest, games, logger)
                setup(api)
                self.modules.append(module)
                self.tools.extend(api.tools)
                output.append(
                    PluginState(manifest, True, f"Loaded · {len(api.tools)} tools")
                )
            except Exception as exc:  # noqa: BLE001 - plugin boundary
                output.append(PluginState(manifest, True, f"Error · {exc}"))
                logger(f"Plugin {manifest.name} failed: {exc}")
        return output

    def create_example(self) -> Path:
        folder = self.root / "example-tools"
        folder.mkdir(parents=True, exist_ok=True)
        manifest = folder / "plugin.json"
        entrypoint = folder / "plugin.py"
        if not manifest.exists():
            manifest.write_text(
                json.dumps(
                    {
                        "id": "example-tools",
                        "name": "Example Tools",
                        "version": "1.0.0",
                        "description": "A minimal local 4u4free plugin.",
                        "author": "Local user",
                        "entrypoint": "plugin.py",
                        "permissions": ["installed_games"],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        if not entrypoint.exists():
            entrypoint.write_text(
                "def setup(api):\n"
                "    def report():\n"
                "        count = len(api.installed_games())\n"
                "        api.log(f'{count} installed games are visible to this plugin')\n"
                "        return f'Found {count} installed games'\n"
                "    api.register_tool('Count installed games', "
                "'Reports the current library size.', report)\n",
                encoding="utf-8",
            )
        return folder
