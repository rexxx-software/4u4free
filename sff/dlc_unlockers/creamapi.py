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

"""CreamAPI DLC unlocker implementation"""

import logging
import os
import shutil
from pathlib import Path

from .base import Platform, UnlockerBase, UnlockerType
from .downloader import GitHubReleaseDownloader
from .steam_dll_utils import detect_steam_architecture, find_steam_api_dll
from .validation import (
    validate_game_directory,
    validate_write_permissions,
    validate_app_id,
    validate_dlc_ids,
    check_disk_space,
)

logger = logging.getLogger(__name__)


class CreamAPIUnlocker(UnlockerBase):
    """SmokeAPI alternative — replaces steam_api.dll, uses INI config instead of JSON."""

    CONFIG_FILENAME = "cream_api.ini"
    STEAM_API_32 = "steam_api.dll"
    STEAM_API_64 = "steam_api64.dll"
    BACKUP_SUFFIX = "_o.dll"

    # CreamAPI DLL names (same as SmokeAPI - they replace steam_api.dll)
    CREAMAPI_32_DLL = "steam_api.dll"
    CREAMAPI_64_DLL = "steam_api64.dll"

    def __init__(self, downloader=None):
        self.downloader = downloader
        self.last_error = None

    @property
    def unlocker_type(self):
        return UnlockerType.CREAMAPI

    @property
    def supported_platforms(self):
        return [Platform.STEAM]

    @property
    def display_name(self):
        return "CreamAPI"

    def _find_steam_api_dll(self, game_dir, dll_name):
        exclude_backup = "_o" not in dll_name  # When searching for backups, don't exclude
        return find_steam_api_dll(game_dir, dll_name, exclude_backup=exclude_backup)

    def _detect_architecture(self, game_dir):
        return detect_steam_architecture(game_dir, self.BACKUP_SUFFIX.replace(".dll", ""))

    def _backup_name(self, dll_name):
        return f"{Path(dll_name).stem}{self.BACKUP_SUFFIX}"

    def _fail(self, message):
        self.last_error = str(message)
        logger.error(self.last_error)
        return False

    @staticmethod
    def _cleanup_file(path):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove temporary file %s", path)

    def is_installed(self, game_dir):
        config_exists = (game_dir / self.CONFIG_FILENAME).exists()
        if not config_exists:
            for _ in game_dir.rglob(self.CONFIG_FILENAME):
                config_exists = True
                break
        backup_32 = self._find_steam_api_dll(
            game_dir, self._backup_name(self.STEAM_API_32)
        )
        backup_64 = self._find_steam_api_dll(
            game_dir, self._backup_name(self.STEAM_API_64)
        )
        return config_exists or backup_32 is not None or backup_64 is not None

    def install(self, game_dir, dlc_ids, app_id):
        self.last_error = None
        game_dir = Path(game_dir)
        valid, error = validate_game_directory(game_dir)
        if not valid:
            return self._fail(f"Invalid game directory: {error}")
        valid, error = validate_app_id(app_id)
        if not valid:
            return self._fail(f"Invalid App ID: {error}")
        valid, error = validate_dlc_ids(dlc_ids)
        if not valid:
            return self._fail(f"Invalid DLC IDs: {error}")
        valid, error = validate_write_permissions(game_dir)
        if not valid:
            return self._fail(
                f"Write permission check failed: {error}. "
                "Try running 4u4free as administrator."
            )
        valid, error = check_disk_space(game_dir, required_bytes=10 * 1024 * 1024)
        if not valid:
            return self._fail(f"Disk space check failed: {error}")

        steam_api_path = None
        backup_path = None
        backup_created = False
        dll_replaced = False
        temporary_paths = []
        try:
            arch = self._detect_architecture(game_dir)
            if not arch:
                return self._fail(
                    f"Could not detect a Steam API DLL in {game_dir}."
                )
            dll_name = self.STEAM_API_64 if arch == "64" else self.STEAM_API_32
            steam_api_path = self._find_steam_api_dll(game_dir, dll_name)
            if not steam_api_path:
                return self._fail(f"Could not find {dll_name} in {game_dir}.")
            target_dir = steam_api_path.parent
            backup_name = self._backup_name(dll_name)
            backup_path = target_dir / backup_name
            creamapi_dll = None
            if self.downloader:
                creamapi_dll = self.downloader.get_dll(
                    UnlockerType.CREAMAPI,
                    arch
                )
            if not creamapi_dll or not creamapi_dll.exists():
                return self._fail(
                    f"Could not find the bundled CreamAPI DLL for {arch}-bit games."
                )
            if creamapi_dll.resolve(strict=False) == steam_api_path.resolve(strict=False):
                return self._fail(
                    "The selected folder resolves to 4u4free's bundled resources, not an "
                    "installed game folder. Choose the game's Steam library folder."
                )

            config_path = target_dir / self.CONFIG_FILENAME
            config_content = self._generate_ini_config(dlc_ids, app_id)

            replacement_tmp = target_dir / f".{dll_name}.4u4free.tmp"
            config_tmp = target_dir / f".{self.CONFIG_FILENAME}.4u4free.tmp"
            temporary_paths.extend((replacement_tmp, config_tmp))
            replacement_tmp.unlink(missing_ok=True)
            config_tmp.unlink(missing_ok=True)
            shutil.copy2(creamapi_dll, replacement_tmp)
            config_tmp.write_text(config_content, encoding="utf-8")

            if not backup_path.exists():
                backup_tmp = target_dir / f".{backup_name}.4u4free.tmp"
                temporary_paths.append(backup_tmp)
                backup_tmp.unlink(missing_ok=True)
                logger.info(f"Backing up {steam_api_path} to {backup_path}")
                shutil.copy2(steam_api_path, backup_tmp)
                os.replace(backup_tmp, backup_path)
                backup_created = True

            logger.info(f"Installing CreamAPI: {creamapi_dll} -> {steam_api_path}")
            os.replace(replacement_tmp, steam_api_path)
            dll_replaced = True
            logger.info(f"Writing CreamAPI config to {config_path}")
            os.replace(config_tmp, config_path)
            logger.info(f"CreamAPI installed successfully to {target_dir}")
            return True
        except Exception as exc:
            for temporary_path in temporary_paths:
                self._cleanup_file(temporary_path)

            rollback_succeeded = not dll_replaced
            rollback_error = None
            if dll_replaced and backup_path and backup_path.exists() and steam_api_path:
                restore_tmp = steam_api_path.parent / f".{steam_api_path.name}.restore.tmp"
                try:
                    restore_tmp.unlink(missing_ok=True)
                    shutil.copy2(backup_path, restore_tmp)
                    os.replace(restore_tmp, steam_api_path)
                    rollback_succeeded = True
                except Exception as restore_exc:
                    rollback_error = restore_exc
                finally:
                    self._cleanup_file(restore_tmp)

            if backup_created and rollback_succeeded and backup_path:
                self._cleanup_file(backup_path)

            winerror = getattr(exc, "winerror", None)
            if isinstance(exc, PermissionError) or winerror in {5, 32, 33}:
                message = (
                    f"Windows could not replace {steam_api_path or 'the Steam API DLL'}: "
                    f"{exc}. Close the game and any process using that DLL, then try again."
                )
            else:
                message = f"CreamAPI installation failed: {exc}"
            if rollback_error:
                message += f" Automatic rollback also failed: {rollback_error}"
            return self._fail(message)

    def uninstall(self, game_dir):
        try:
            success = True
            config_removed = False
            steam_api_32 = self._find_steam_api_dll(game_dir, self.STEAM_API_32)
            if steam_api_32:
                target_dir = steam_api_32.parent
                backup_name_32 = self._backup_name(self.STEAM_API_32)
                backup_32 = target_dir / backup_name_32
                if backup_32.exists():
                    logger.info(f"Restoring {backup_32} to {steam_api_32}")
                    os.replace(backup_32, steam_api_32)
                config_path = target_dir / self.CONFIG_FILENAME
                if config_path.exists():
                    logger.info(f"Removing config: {config_path}")
                    config_path.unlink()
                    config_removed = True
            steam_api_64 = self._find_steam_api_dll(game_dir, self.STEAM_API_64)
            if steam_api_64:
                target_dir = steam_api_64.parent
                backup_name_64 = self._backup_name(self.STEAM_API_64)
                backup_64 = target_dir / backup_name_64
                if backup_64.exists():
                    logger.info(f"Restoring {backup_64} to {steam_api_64}")
                    os.replace(backup_64, steam_api_64)
                config_path = target_dir / self.CONFIG_FILENAME
                if config_path.exists():
                    logger.info(f"Removing config: {config_path}")
                    config_path.unlink()
                    config_removed = True
            if not steam_api_32 and not steam_api_64 and not config_removed:
                config_path = game_dir / self.CONFIG_FILENAME
                if config_path.exists():
                    logger.info(f"Removing config from root: {config_path}")
                    config_path.unlink()
                else:
                    for found_config in game_dir.rglob(self.CONFIG_FILENAME):
                        logger.info(f"Removing config: {found_config}")
                        found_config.unlink()
                        break
            logger.info("CreamAPI uninstalled successfully")
            return success
        except Exception as e:
            logger.error(f"Failed to uninstall CreamAPI: {e}")
            return False

    def generate_config(self, dlc_ids, app_id):
        return {
            "app_id": app_id,
            "dlc_ids": dlc_ids,
            "unlockall": False,
            "orgapi": self.STEAM_API_32.replace(".dll", self.BACKUP_SUFFIX),
            "orgapi64": self.STEAM_API_64.replace(".dll", self.BACKUP_SUFFIX),
            "extraprotection": False,
            "forceoffline": False,
            "disableuserinterface": False
        }

    def _generate_ini_config(self, dlc_ids, app_id):
        lines = []
        lines.append(f"; CreamAPI Configuration for App ID {app_id}")
        lines.append("")
        lines.append("[steam]")
        lines.append(f"appid = {app_id}")
        lines.append("unlockall = false")
        lines.append(f"orgapi = {self.STEAM_API_32.replace('.dll', self.BACKUP_SUFFIX)}")
        lines.append(f"orgapi64 = {self.STEAM_API_64.replace('.dll', self.BACKUP_SUFFIX)}")
        lines.append("extraprotection = false")
        lines.append("forceoffline = false")
        lines.append("")
        # [steam_misc] section (required in v5.3.0.0+)
        lines.append("[steam_misc]")
        lines.append("disableuserinterface = false")
        lines.append("")
        lines.append("[dlc]")
        for dlc_id in dlc_ids:
            lines.append(f"{dlc_id} = DLC_{dlc_id}")
        return "\n".join(lines)
