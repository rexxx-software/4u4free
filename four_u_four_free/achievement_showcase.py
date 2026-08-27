"""Public Steam achievement rarity recommendations for profile showcases."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable

from .errors import FourUFourFreeError


@dataclass(frozen=True)
class ShowcaseAchievement:
    app_id: str
    game_name: str
    api_name: str
    name: str
    description: str
    global_percent: float
    unlock_timestamp: int | None


def _validate_id(value: str | int, label: str) -> str:
    text = str(value).strip()
    if not text.isdigit() or int(text) <= 0:
        raise FourUFourFreeError(f"{label} is invalid.")
    return text


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "4u4free/0.5"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError) as exc:
        raise FourUFourFreeError(f"Steam achievement request failed: {exc}") from exc


def recommend_for_game(
    steam_id64: str | int,
    app_id: str | int,
    game_name: str,
    *,
    fetch_text: Callable[[str], str] = _fetch_text,
) -> list[ShowcaseAchievement]:
    steam_id = _validate_id(steam_id64, "Steam profile ID")
    normalized_app_id = _validate_id(app_id, "App ID")
    profile_url = (
        f"https://steamcommunity.com/profiles/{steam_id}/stats/"
        f"{normalized_app_id}/?xml=1"
    )
    global_url = (
        "https://api.steampowered.com/ISteamUserStats/"
        "GetGlobalAchievementPercentagesForApp/v2/"
        f"?gameid={normalized_app_id}"
    )
    try:
        root = ET.fromstring(fetch_text(profile_url))
    except ET.ParseError as exc:
        raise FourUFourFreeError(
            "Steam did not return a readable achievement list. The profile or Game "
            "details may be private, or this game may not expose achievements."
        ) from exc

    error = root.findtext("error")
    if error:
        raise FourUFourFreeError(f"Steam could not expose these achievements: {error}")

    unlocked: dict[str, tuple[str, str, int | None]] = {}
    for item in root.findall(".//achievement"):
        if str(item.attrib.get("closed") or "0") != "1":
            continue
        api_name = str(item.findtext("apiname") or "").strip()
        if not api_name:
            continue
        timestamp_text = str(item.findtext("unlockTimestamp") or "").strip()
        timestamp = int(timestamp_text) if timestamp_text.isdigit() else None
        unlocked[api_name.casefold()] = (
            str(item.findtext("name") or api_name).strip(),
            str(item.findtext("description") or "").strip(),
            timestamp,
        )
    if not unlocked:
        raise FourUFourFreeError(
            "No public unlocked achievements were returned for this game."
        )

    try:
        global_data = json.loads(fetch_text(global_url))
        rows = global_data["achievementpercentages"]["achievements"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise FourUFourFreeError(
            "Steam did not return global achievement percentages for this game."
        ) from exc

    recommendations: list[ShowcaseAchievement] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        api_name = str(row.get("name") or "").strip()
        details = unlocked.get(api_name.casefold())
        if details is None:
            continue
        try:
            percent = max(0.0, min(100.0, float(row.get("percent"))))
        except (TypeError, ValueError):
            continue
        display_name, description, timestamp = details
        recommendations.append(
            ShowcaseAchievement(
                normalized_app_id,
                str(game_name).strip() or f"App {normalized_app_id}",
                api_name,
                display_name,
                description,
                percent,
                timestamp,
            )
        )
    return sorted(
        recommendations,
        key=lambda item: (item.global_percent, item.name.casefold()),
    )
