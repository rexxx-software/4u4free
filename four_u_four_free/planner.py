"""Generate an auditable import plan without changing Steam."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .lua import LuaInfo


@dataclass(frozen=True)
class PlanAction:
    order: int
    kind: str
    target: str
    description: str
    implemented: bool


@dataclass
class ImportPlan:
    created_at: str
    steam_root: str
    source_lua: str
    inferred_app_id: str | None
    actions: List[PlanAction]
    warnings: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "created_at": self.created_at,
            "steam_root": self.steam_root,
            "source_lua": self.source_lua,
            "inferred_app_id": self.inferred_app_id,
            "actions": [asdict(action) for action in self.actions],
            "warnings": self.warnings,
        }


def make_import_plan(lua: LuaInfo, steam_root: Path) -> ImportPlan:
    target = steam_root / "config" / "stplug-in" / lua.path.name
    actions = [
        PlanAction(
            1,
            "validate",
            str(lua.path),
            "Validate and parse the source Lua without executing it.",
            True,
        ),
        PlanAction(
            2,
            "backup",
            str(steam_root),
            "Create a checksummed snapshot of relevant Steam state.",
            True,
        ),
        PlanAction(
            3,
            "copy",
            str(target),
            "Copy the Lua into Steam's plug-in directory.",
            False,
        ),
        PlanAction(
            4,
            "config",
            str(steam_root / "config" / "config.vdf"),
            "Apply depot keys using a structured VDF update.",
            False,
        ),
        PlanAction(
            5,
            "manifest",
            str(steam_root / "steamapps"),
            "Resolve and install authorized manifests, then update ACF metadata.",
            False,
        ),
    ]
    warnings = [
        "This command is dry-run only; it does not alter Steam or execute the Lua file.",
        "Only import data you are legally authorized to use.",
        "Binary injection, DRM circumvention, DLC unlocking, and third-party downloaders are outside the 0.1 scope.",
    ]
    if not lua.app_directives:
        warnings.append("No active addappid directives were found.")
    if lua.tokens:
        warnings.append(
            "The file contains access tokens; command output redacts them by default."
        )
    return ImportPlan(
        created_at=datetime.now(timezone.utc).isoformat(),
        steam_root=str(steam_root.resolve(strict=False)),
        source_lua=str(lua.path),
        inferred_app_id=lua.inferred_app_id,
        actions=actions,
        warnings=warnings,
    )
