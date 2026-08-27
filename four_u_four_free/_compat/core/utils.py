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


"""Miscellaneous stuff used across various files"""

import logging
import os
import sys

from pathlib import Path


logger = logging.getLogger(__name__)


def app_data_dir() -> Path:
    """Return the writable 4u4free data directory.

    Always returns the directory containing the running script or exe.
    In a frozen build this is the executable's parent. When running from source,
    it is the project root. Settings and caches stay beside the entry point.
    """
    return root_folder(outside_internal=True)


def root_folder(outside_internal=False):
    bundled = getattr(sys, "frozen", False)

    if bundled:
        if outside_internal:
            ai = os.environ.get("APPIMAGE")
            if ai:
                return Path(ai).resolve().parent
            return Path(sys.executable).resolve().parent

        internal_path = getattr(sys, "_MEIPASS", None)
        if internal_path:
            return Path(internal_path).resolve()
        return Path(sys.executable).resolve().parent

    script_root = Path(__file__).resolve().parents[3]
    if outside_internal:
        return script_root
    return script_root


def manifests_staging_dir() -> Path:
    """Canonical staging directory for downloaded .manifest files.

    Returns the writable application-data root plus ``manifests/``, creating it.
    """
    out = root_folder(outside_internal=True) / "manifests"
    out.mkdir(parents=True, exist_ok=True)
    return out


def enter_path(
    obj,
    *paths,
    mutate=False,
    ignore_case=False,
    default=None,
):
    """

    Walks or creates nested dicts in a VDFDict/dict.

    Returns an empty dict-like if not found.

    `default` key only works when `mutate` is False.

    """

    current = obj

    for key in paths:
        if isinstance(key, int):
            try:
                current = current[key]  # pyright: ignore[reportUnknownVariableType]
            except IndexError:
                return type(current)()
            continue
        original_key = key
        if ignore_case:
            key = key.lower()
        key_map = {}
        for x in current:  # pyright: ignore[reportUnknownVariableType]
            if ignore_case and isinstance(x, str):
                key_map[x.lower()] = x
            else:
                key_map[x] = x
        if key in key_map:
            current = current[  # pyright: ignore[reportUnknownVariableType]
                key_map[key]
            ]
        else:
            if not mutate:
                return default if default else type(current)()
            # create a new key that's the same type as current
            new_node = type(current)()
            current[original_key] = new_node
            current = new_node

    return current  # pyright: ignore[reportUnknownVariableType]
