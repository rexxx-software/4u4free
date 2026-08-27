"""Compatibility guidance for online features that need more than Steam P2P."""

from __future__ import annotations

from dataclasses import dataclass


PEACOCK_SETUP_URL = "https://thepeacockproject.org/wiki/intel/installation/"


@dataclass(frozen=True)
class OnlineCompatibility:
    generic_supported: bool
    status: str
    detail: str
    provider: str = ""
    guide_url: str = ""


GENERIC_PROFILE = OnlineCompatibility(
    generic_supported=True,
    status="Experimental LC Online Fix",
    detail=(
        "This game has no verified 4u4free compatibility profile. The App 480 "
        "redirect may help games that use Steam networking, but it cannot replace "
        "a publisher account, dedicated backend, anti-cheat service, or game server."
    ),
)


_PROFILES = {
    # The HITMAN World of Assassination trilogy relies on IOI-style game-service
    # endpoints rather than only Steam P2P. Peacock is the maintained open-source
    # server replacement for supported, legitimately owned PC versions.
    app_id: OnlineCompatibility(
        generic_supported=False,
        status="Game-specific backend required",
        detail=(
            "The generic LC Online Fix does not replace HITMAN's game-service "
            "backend. Peacock is the appropriate project for a supported PC copy; "
            "its maintainers do not support cracked or pirated versions. Peacock "
            "progress is separate from the official IOI profile."
        ),
        provider="Peacock",
        guide_url=PEACOCK_SETUP_URL,
    )
    for app_id in ("236870", "863550", "1659040")
}


def online_compatibility(app_id: str | int) -> OnlineCompatibility:
    return _PROFILES.get(str(app_id).strip(), GENERIC_PROFILE)
