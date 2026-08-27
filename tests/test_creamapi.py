import os

from sff.dlc_unlockers import creamapi as creamapi_module
from sff.dlc_unlockers.creamapi import CreamAPIUnlocker


class _FixtureDownloader:
    def __init__(self, dll_path):
        self.dll_path = dll_path

    def get_dll(self, _unlocker_type, _architecture):
        return self.dll_path


def _fixture(tmp_path):
    game_dir = tmp_path / "game"
    resources_dir = tmp_path / "resources"
    game_dir.mkdir()
    resources_dir.mkdir()
    original = game_dir / "steam_api64.dll"
    replacement = resources_dir / "steam_api64.dll"
    original.write_bytes(b"original Steam API")
    replacement.write_bytes(b"CreamAPI replacement")
    return game_dir, original, replacement


def test_install_is_detectable_and_uninstall_restores_original(tmp_path):
    game_dir, original, replacement = _fixture(tmp_path)
    unlocker = CreamAPIUnlocker(_FixtureDownloader(replacement))

    assert unlocker.install(game_dir, [101, 102], 42) is True
    assert unlocker.is_installed(game_dir) is True
    assert original.read_bytes() == b"CreamAPI replacement"
    assert (game_dir / "steam_api64_o.dll").read_bytes() == b"original Steam API"
    assert (game_dir / "cream_api.ini").exists()

    assert unlocker.uninstall(game_dir) is True
    assert original.read_bytes() == b"original Steam API"
    assert not (game_dir / "steam_api64_o.dll").exists()
    assert not (game_dir / "cream_api.ini").exists()
    assert unlocker.is_installed(game_dir) is False


def test_failed_replacement_leaves_original_untouched(monkeypatch, tmp_path):
    game_dir, original, replacement = _fixture(tmp_path)
    unlocker = CreamAPIUnlocker(_FixtureDownloader(replacement))
    real_replace = os.replace
    replace_calls = 0

    def fail_on_dll_replace(source, destination):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise PermissionError(13, "file is in use", str(destination))
        return real_replace(source, destination)

    monkeypatch.setattr(creamapi_module.os, "replace", fail_on_dll_replace)

    assert unlocker.install(game_dir, [101], 42) is False
    assert original.read_bytes() == b"original Steam API"
    assert not (game_dir / "steam_api64_o.dll").exists()
    assert not (game_dir / "cream_api.ini").exists()
    assert "Close the game" in unlocker.last_error
    assert not list(game_dir.glob("*.4u4free.tmp"))


def test_install_rejects_bundled_dll_as_its_own_target(tmp_path):
    game_dir = tmp_path / "not-a-game"
    game_dir.mkdir()
    target = game_dir / "steam_api64.dll"
    target.write_bytes(b"bundled resource")
    unlocker = CreamAPIUnlocker(_FixtureDownloader(target))

    assert unlocker.install(game_dir, [101], 42) is False
    assert "bundled resources" in unlocker.last_error
    assert target.read_bytes() == b"bundled resource"
    assert not (game_dir / "cream_api.ini").exists()
    assert not (game_dir / "steam_api64_o.dll").exists()
