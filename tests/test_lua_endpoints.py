from four_u_four_free._compat.lua import endpoints
from four_u_four_free._compat.network import steam_client


def _app_info(depot_id="42001"):
    return {
        "common": {"name": "Test Game"},
        "depots": {
            depot_id: {"manifests": {"public": {"gid": "123456789", "size": "1024"}}},
            "branches": {"public": {"buildid": "123"}},
        },
    }


def test_oureveryday_uses_http_before_steam_client(monkeypatch, tmp_path):
    expected = _app_info()
    monkeypatch.setattr(steam_client, "fetch_app_info_http", lambda _app_id: expected)

    def fail_if_created():
        raise AssertionError("SteamClient should not be created after an HTTP hit")

    monkeypatch.setattr(
        steam_client, "create_provider_for_current_thread", fail_if_created
    )
    monkeypatch.setattr(endpoints, "_provider_key_map", lambda: {"42001": "a" * 64})
    monkeypatch.setattr(
        "four_u_four_free._compat.lua.dlc_appid_enricher.append_depotless_dlcs",
        lambda *_args, **_kwargs: 0,
    )

    result = endpoints.get_oureverday(tmp_path, "42")

    assert result == tmp_path / "42.lua"
    assert 'addappid(42001, 1, "' + "a" * 64 + '")' in result.read_text(
        encoding="utf-8"
    )


def test_oureveryday_falls_back_to_steam_client(monkeypatch, tmp_path):
    expected = _app_info()
    monkeypatch.setattr(steam_client, "fetch_app_info_http", lambda _app_id: None)

    class Provider:
        def get_single_app_info(self, app_id, quick=False):
            assert app_id == 42
            assert quick is True
            return expected

    monkeypatch.setattr(
        steam_client, "create_provider_for_current_thread", lambda: Provider()
    )
    monkeypatch.setattr(endpoints, "_provider_key_map", lambda: {"42001": "b" * 64})
    monkeypatch.setattr(
        "four_u_four_free._compat.lua.dlc_appid_enricher.append_depotless_dlcs",
        lambda *_args, **_kwargs: 0,
    )

    result = endpoints.get_oureverday(tmp_path, "42")

    assert result == tmp_path / "42.lua"
