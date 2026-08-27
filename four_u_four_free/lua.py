"""Read-only parser for the SteamTools-style Lua directives used by SteaMidra."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .errors import FourUFourFreeError

MAX_LUA_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class AppDirective:
    app_or_depot_id: str
    flag: Optional[str]
    key: Optional[str]

    def to_dict(self, show_secrets: bool = False) -> Dict[str, Optional[str]]:
        value = asdict(self)
        if self.key and not show_secrets:
            value["key"] = redact(self.key)
        return value


@dataclass(frozen=True)
class TokenDirective:
    app_id: str
    token: str

    def to_dict(self, show_secrets: bool = False) -> Dict[str, str]:
        return {"app_id": self.app_id, "token": self.token if show_secrets else redact(self.token)}


@dataclass
class LuaInfo:
    path: Path
    inferred_app_id: Optional[str]
    app_directives: List[AppDirective]
    manifests: Dict[str, str]
    tokens: List[TokenDirective]

    def to_dict(self, show_secrets: bool = False) -> Dict[str, object]:
        return {
            "path": str(self.path),
            "inferred_app_id": self.inferred_app_id,
            "app_directives": [item.to_dict(show_secrets) for item in self.app_directives],
            "manifests": dict(self.manifests),
            "tokens": [item.to_dict(show_secrets) for item in self.tokens],
            "counts": {
                "app_directives": len(self.app_directives),
                "keys": sum(item.key is not None for item in self.app_directives),
                "manifests": len(self.manifests),
                "tokens": len(self.tokens),
            },
        }


_ADD_APP = re.compile(
    r"\baddappid\s*\(\s*(?P<id>\d+)\s*"
    r"(?:,\s*(?P<flag>\d+)\s*)?"
    r"(?:,\s*['\"](?P<key>[0-9a-fA-F]{64})['\"]\s*)?\)",
    re.IGNORECASE,
)
_SET_MANIFEST = re.compile(
    r"\bsetManifestid\s*\(\s*(?P<depot>\d+)\s*,\s*['\"](?P<gid>\d+)['\"]\s*\)",
    re.IGNORECASE,
)
_ADD_TOKEN = re.compile(
    r"\baddtoken\s*\(\s*(?P<appid>\d+)\s*,\s*['\"](?P<token>[^'\"]+)['\"]\s*\)",
    re.IGNORECASE,
)


def redact(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def strip_comments(text: str) -> str:
    """Remove Lua line and long comments while preserving quoted strings."""

    output: List[str] = []
    index = 0
    quote: Optional[str] = None
    while index < len(text):
        char = text[index]
        if quote:
            output.append(char)
            if char == "\\" and index + 1 < len(text):
                output.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            output.append(char)
            index += 1
            continue
        if text.startswith("--[[", index):
            end = text.find("]]", index + 4)
            if end == -1:
                break
            output.append("\n" * text[index : end + 2].count("\n"))
            index = end + 2
            continue
        if text.startswith("--", index):
            end = text.find("\n", index + 2)
            if end == -1:
                break
            output.append("\n")
            index = end + 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def inspect_lua(path: Path) -> LuaInfo:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FourUFourFreeError(f"Could not inspect {path}: {exc}") from exc
    if size > MAX_LUA_BYTES:
        raise FourUFourFreeError(f"Lua file is larger than the {MAX_LUA_BYTES // (1024 * 1024)} MiB safety limit")
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise FourUFourFreeError(f"Could not read {path}: {exc}") from exc

    active = strip_comments(text)
    app_directives = [
        AppDirective(match.group("id"), match.group("flag"), match.group("key"))
        for match in _ADD_APP.finditer(active)
    ]
    manifests = {match.group("depot"): match.group("gid") for match in _SET_MANIFEST.finditer(active)}
    tokens = [TokenDirective(match.group("appid"), match.group("token")) for match in _ADD_TOKEN.finditer(active)]
    inferred = path.stem if path.stem.isdigit() else (tokens[0].app_id if tokens else None)
    return LuaInfo(path.resolve(strict=False), inferred, app_directives, manifests, tokens)

