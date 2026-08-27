"""Read-only Steam account/profile discovery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

from .errors import FourUFourFreeError
from .vdf import get_mapping, get_string, read_vdf


@dataclass(frozen=True)
class SteamProfile:
    steam_id64: str
    account_id: str
    account_name: str
    persona_name: str
    most_recent: bool
    remember_password: bool
    timestamp: str
    userdata: Path

    def to_dict(self) -> Dict[str, object]:
        value = asdict(self)
        value["userdata"] = str(self.userdata)
        return value


def account_id_from_steam_id64(value: str) -> str:
    if not value.isdigit():
        raise FourUFourFreeError(f"Invalid SteamID64: {value!r}")
    numeric = int(value)
    if numeric > 0xFFFFFFFFFFFFFFFF:
        raise FourUFourFreeError(
            f"SteamID64 is outside the unsigned 64-bit range: {value!r}"
        )
    return str(numeric & 0xFFFFFFFF)


def list_profiles(steam_root: Path) -> List[SteamProfile]:
    users_path = steam_root / "config" / "loginusers.vdf"
    entries = {}
    if users_path.is_file():
        users = get_mapping(read_vdf(users_path), "users")
        entries = {
            key: value for key, value in users.items() if isinstance(value, dict)
        }

    profiles: List[SteamProfile] = []
    seen_accounts = set()
    for steam_id64, metadata in entries.items():
        if not str(steam_id64).isdigit():
            continue
        account_id = account_id_from_steam_id64(str(steam_id64))
        seen_accounts.add(account_id)
        profiles.append(
            SteamProfile(
                steam_id64=str(steam_id64),
                account_id=account_id,
                account_name=get_string(metadata, "AccountName"),
                persona_name=get_string(metadata, "PersonaName"),
                most_recent=get_string(metadata, "MostRecent") == "1",
                remember_password=get_string(metadata, "RememberPassword") == "1",
                timestamp=get_string(metadata, "Timestamp"),
                userdata=steam_root / "userdata" / account_id,
            )
        )

    userdata = steam_root / "userdata"
    if userdata.is_dir():
        try:
            paths = sorted(userdata.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise FourUFourFreeError(
                f"Could not read Steam userdata directory {userdata}: {exc}"
            ) from exc
        for path in paths:
            if path.is_dir() and path.name.isdigit() and path.name not in seen_accounts:
                profiles.append(
                    SteamProfile("", path.name, "", "", False, False, "", path)
                )
    return sorted(
        profiles,
        key=lambda profile: (
            not profile.most_recent,
            profile.persona_name.casefold(),
            profile.account_id,
        ),
    )
