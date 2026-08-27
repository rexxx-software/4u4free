import pytest

from four_u_four_free import dlc_service
from four_u_four_free.errors import FourUFourFreeError


def test_parse_dlc_ids_accepts_common_separators_and_deduplicates():
    assert dlc_service.parse_dlc_ids("101, 202;101\n303") == [101, 202, 303]


def test_parse_dlc_ids_rejects_non_numeric_values():
    with pytest.raises(FourUFourFreeError, match="digits"):
        dlc_service.parse_dlc_ids("101, nope")


def test_require_game_directory_rejects_blank_value():
    with pytest.raises(FourUFourFreeError, match="Choose an installed game folder"):
        dlc_service.require_game_directory("")


def test_fetch_dlc_catalog_returns_names(monkeypatch):
    monkeypatch.setattr(
        dlc_service, "get_dlc_list_from_store", lambda _app_id: ("Game", [11, 12])
    )
    monkeypatch.setattr(
        dlc_service,
        "get_dlc_names_from_store",
        lambda _ids: {11: "First DLC", 12: "Second DLC"},
    )

    result = dlc_service.fetch_dlc_catalog(42)

    assert result["name"] == "Game"
    assert result["dlcs"] == [
        {"id": 11, "name": "First DLC"},
        {"id": 12, "name": "Second DLC"},
    ]


def test_inspect_game_apis_searches_subdirectories(tmp_path):
    nested = tmp_path / "bin" / "win64"
    nested.mkdir(parents=True)
    (nested / "steam_api64.dll").write_bytes(b"dll")

    rows = dlc_service.inspect_game_apis(tmp_path)

    steam64 = next(row for row in rows if row["filename"] == "steam_api64.dll")
    assert steam64["found"] is True
    assert steam64["paths"] == [nested / "steam_api64.dll"]


def test_install_smokeapi_dispatches_with_bundled_directory(monkeypatch, tmp_path):
    dll_dir = tmp_path / "resources"
    dll_dir.mkdir()
    calls = {}

    class Downloader:
        def __init__(self, cache_dir):
            calls["cache_dir"] = cache_dir

        def get_cached_dll(self, _kind):
            return dll_dir

        def _get_local_resource(self, _kind):
            return None

    class Smoke:
        def install(self, folder, dlc_ids, app_id, smokeapi_dir=None):
            calls.update(
                folder=folder,
                dlc_ids=dlc_ids,
                app_id=app_id,
                smokeapi_dir=smokeapi_dir,
            )
            return True

    monkeypatch.setattr(dlc_service, "SmokeAPIUnlocker", Smoke)

    ok = dlc_service.install_unlocker(
        tmp_path,
        "smokeapi",
        42,
        [101, 102],
        cache_dir=tmp_path / "cache",
        downloader_factory=Downloader,
    )

    assert ok is True
    assert calls == {
        "cache_dir": tmp_path / "cache",
        "folder": tmp_path,
        "dlc_ids": [101, 102],
        "app_id": 42,
        "smokeapi_dir": dll_dir,
    }


def test_install_creamapi_surfaces_specific_failure(monkeypatch, tmp_path):
    class Downloader:
        def __init__(self, _cache_dir):
            pass

    class Cream:
        def __init__(self, _downloader):
            self.last_error = "Windows reports that steam_api64.dll is in use."

        def install(self, _folder, _dlc_ids, _app_id):
            return False

    monkeypatch.setattr(dlc_service, "CreamAPIUnlocker", Cream)

    with pytest.raises(FourUFourFreeError, match="steam_api64.dll is in use"):
        dlc_service.install_unlocker(
            tmp_path,
            "creamapi",
            42,
            [101],
            cache_dir=tmp_path / "cache",
            downloader_factory=Downloader,
        )
