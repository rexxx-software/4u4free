"""Generate a human-readable local environment report."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .steam import SteamGame


def environment_report(steam_root: Path, libraries: Iterable[Path], games: Iterable[SteamGame]) -> str:
    library_list = list(libraries)
    game_list = list(games)
    lines = [
        "# 4u4free environment report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Steam root: `{steam_root}`",
        f"Libraries: {len(library_list)}",
        f"Installed manifests: {len(game_list)}",
        "",
        "## Libraries",
        "",
    ]
    lines.extend(f"- `{library}`" for library in library_list)
    lines.extend(["", "## Games", "", "| App ID | Name | Build ID | Library |", "|---:|---|---:|---|"])
    for game in game_list:
        name = game.name.replace("|", "\\|")
        lines.append(f"| {game.app_id} | {name} | {game.build_id or '-'} | `{game.library}` |")
    lines.extend(
        [
            "",
            "## Safety boundary",
            "",
            "This report was created from local VDF/ACF metadata. No game, Steam, Lua, or third-party executable was launched.",
            "",
        ]
    )
    return "\n".join(lines)

