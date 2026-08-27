"""Use the pinned SteamDB filename rules for local compatibility diagnostics."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_EXTERNAL_BACKEND_RULES = {
    "Azure_Playfab_Party",
    "EpicOnlineServices",
    "Nakama",
    "Photon",
    "Vivox",
}


@dataclass(frozen=True)
class SteamDbRule:
    section: str
    name: str
    expression: re.Pattern[str]


@dataclass(frozen=True)
class SteamDbRiskMatches:
    anti_cheat: tuple[str, ...] = ()
    external_backend: tuple[str, ...] = ()


def _application_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def steamdb_rules_path() -> Path:
    return (
        _application_root()
        / "third_party"
        / "steamdb-file-detection"
        / "rules.ini"
    )


def _python_compatible_pattern(pattern: str) -> str:
    # SteamDB's PCRE rules use atomic groups in a few expressions. Atomicity is
    # irrelevant for our filename classification, so a normal non-capturing
    # group preserves the match while remaining compatible with Python 3.10.
    return pattern.replace("(?>", "(?:")


@lru_cache(maxsize=1)
def load_risk_rules() -> tuple[SteamDbRule, ...]:
    path = steamdb_rules_path()
    if not path.is_file():
        return ()

    section = ""
    rules: list[SteamDbRule] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section not in {"AntiCheat", "SDK"} or "=" not in line:
            continue
        raw_name, raw_pattern = line.split("=", 1)
        name = raw_name.strip().removesuffix("[]")
        if section == "SDK" and name not in _EXTERNAL_BACKEND_RULES:
            continue
        try:
            expression = re.compile(
                _python_compatible_pattern(raw_pattern.strip()), re.IGNORECASE
            )
        except re.error:
            continue
        rules.append(SteamDbRule(section, name, expression))
    return tuple(rules)


def detect_risks(relative_paths: list[str]) -> SteamDbRiskMatches:
    anti_cheat: list[str] = []
    external_backend: list[str] = []
    normalized = [path.replace("\\", "/") for path in relative_paths]
    for rule in load_risk_rules():
        for path in normalized:
            if rule.expression.search(path) is None:
                continue
            match = f"{rule.name}: {path}"
            target = anti_cheat if rule.section == "AntiCheat" else external_backend
            if match not in target:
                target.append(match)
            break
    return SteamDbRiskMatches(tuple(anti_cheat), tuple(external_backend))
