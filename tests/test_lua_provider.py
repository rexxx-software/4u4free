import gzip
import json

from four_u_four_free._compat.lua.provider import load_provider_file


def test_load_provider_file_supports_gzip(tmp_path):
    path = tmp_path / "fallback_depotkeys.json.gz"
    payload = {
        "480": {
            "key": "a" * 64,
            "name": "Example",
            "kind": "game",
        }
    }
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)

    assert load_provider_file(path) == payload
