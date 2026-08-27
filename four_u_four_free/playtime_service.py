"""Safe Steam playtime-session support.

Steam owns the account's playtime record.  This module deliberately does not
edit local Steam metadata or claim to backdate server-side hours.  It validates
a real-time session goal and asks Steam to launch the selected installed app.
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

from .achievement_service import achievement_manager_path, steam_is_running
from .errors import FourUFourFreeError


MIN_SESSION_SECONDS = 60
MAX_SESSION_SECONDS = 30 * 24 * 60 * 60
IDLER_EXECUTABLE = "4u4free.PlaytimeIdler.exe"


def require_playtime_app_id(value: str | int) -> str:
    text = str(value).strip()
    if not text.isdigit() or int(text) <= 0:
        raise FourUFourFreeError("Choose an installed game with a valid App ID.")
    return text


def require_session_duration(hours: int, minutes: int) -> int:
    try:
        normalized_hours = int(hours)
        normalized_minutes = int(minutes)
    except (TypeError, ValueError) as exc:
        raise FourUFourFreeError("Enter a valid playtime duration.") from exc
    if normalized_hours < 0 or not 0 <= normalized_minutes <= 59:
        raise FourUFourFreeError("Hours cannot be negative; minutes must be 0-59.")
    total = normalized_hours * 60 * 60 + normalized_minutes * 60
    if total < MIN_SESSION_SECONDS:
        raise FourUFourFreeError("Choose a playtime session of at least one minute.")
    if total > MAX_SESSION_SECONDS:
        raise FourUFourFreeError("A single playtime session cannot exceed 30 days.")
    return total


def format_duration(seconds: int | float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 60 * 60)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


@dataclass(frozen=True)
class PlaytimeSession:
    app_id: str
    game_name: str
    duration_seconds: int
    started_at: float

    @classmethod
    def create(
        cls,
        app_id: str | int,
        game_name: str,
        hours: int,
        minutes: int,
        *,
        now: float | None = None,
    ) -> "PlaytimeSession":
        normalized_app_id = require_playtime_app_id(app_id)
        duration = require_session_duration(hours, minutes)
        name = str(game_name).strip() or f"App {normalized_app_id}"
        return cls(
            app_id=normalized_app_id,
            game_name=name,
            duration_seconds=duration,
            started_at=time.monotonic() if now is None else float(now),
        )

    def snapshot(self, *, now: float | None = None) -> tuple[int, int, float]:
        current = time.monotonic() if now is None else float(now)
        elapsed = max(0, min(self.duration_seconds, int(current - self.started_at)))
        remaining = max(0, self.duration_seconds - elapsed)
        progress = elapsed / self.duration_seconds
        return elapsed, remaining, progress


def start_steam_game(app_id: str | int) -> str:
    """Ask the installed Steam client to launch *app_id*.

    Returns the validated Steam URI.  Steam, not 4u4free, owns the resulting
    game process and account playtime record.
    """
    normalized_app_id = require_playtime_app_id(app_id)
    if not steam_is_running():
        raise FourUFourFreeError(
            "Steam is not running. Start Steam, sign in, then try again."
        )
    uri = f"steam://run/{normalized_app_id}"
    try:
        if sys.platform == "win32":
            os.startfile(uri)  # type: ignore[attr-defined]
        else:
            steam_command = shutil.which("steam")
            if not steam_command:
                raise FourUFourFreeError(
                    "The Steam launcher command was not found on this system."
                )
            subprocess.Popen(
                [steam_command, uri],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except FourUFourFreeError:
        raise
    except OSError as exc:
        raise FourUFourFreeError(f"Steam could not launch App {normalized_app_id}.") from exc
    return uri


def playtime_idler_path(root=None):
    return achievement_manager_path(root).parent / IDLER_EXECUTABLE


def require_playtime_idler(root=None):
    executable = playtime_idler_path(root)
    if not executable.is_file():
        raise FourUFourFreeError(
            "The headless playtime helper is missing. Reinstall the current "
            "4u4free release or use Launch game mode."
        )
    return executable


def _read_ready_line(process: subprocess.Popen, timeout: float) -> str:
    if process.stdout is None:
        return ""
    lines: queue.Queue[str] = queue.Queue(maxsize=1)

    def read_line() -> None:
        try:
            lines.put(process.stdout.readline())
        except (OSError, ValueError):
            lines.put("")

    threading.Thread(target=read_line, daemon=True).start()
    try:
        return lines.get(timeout=timeout).strip()
    except queue.Empty:
        return ""


def start_headless_idle(
    app_id: str | int,
    *,
    root=None,
    parent_process_id: int | None = None,
    ready_timeout: float = 5.0,
) -> subprocess.Popen:
    """Start the bundled credential-free SteamAPI presence helper.

    The helper verifies that the signed-in account is subscribed to the app and
    exits automatically if its 4u4free parent process ends.
    """
    if sys.platform != "win32":
        raise FourUFourFreeError("Headless playtime mode is available on Windows only.")
    normalized_app_id = require_playtime_app_id(app_id)
    if not steam_is_running():
        raise FourUFourFreeError(
            "Steam is not running. Start Steam, sign in, then try again."
        )
    executable = require_playtime_idler(root)
    parent_id = os.getpid() if parent_process_id is None else int(parent_process_id)
    if parent_id <= 0:
        raise FourUFourFreeError("The 4u4free process ID is invalid.")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            [str(executable), normalized_app_id, str(parent_id)],
            cwd=str(executable.parent),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
    except OSError as exc:
        raise FourUFourFreeError("The headless playtime helper could not start.") from exc

    ready_line = _read_ready_line(process, max(0.1, float(ready_timeout)))
    if ready_line == f"READY {normalized_app_id}" and process.poll() is None:
        return process

    try:
        process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        stderr = process.stderr.read() if process.stderr is not None else ""
    except (OSError, ValueError):
        stderr = ""
    detail = (stderr or ready_line or "Steam did not accept the idling session").strip()
    raise FourUFourFreeError(detail)


def stop_headless_idle(process: subprocess.Popen, *, timeout: float = 3.0) -> None:
    """Gracefully release a helper connection, then force it down if necessary."""
    if process.poll() is not None:
        return
    try:
        if process.stdin is not None:
            process.stdin.write("stop\n")
            process.stdin.flush()
    except (BrokenPipeError, OSError, ValueError):
        pass
    try:
        process.wait(timeout=max(0.1, float(timeout)))
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=2)
        return
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
