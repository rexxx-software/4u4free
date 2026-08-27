import json
import tempfile
import unittest
from pathlib import Path

from four_u_four_free.errors import FourUFourFreeError
from four_u_four_free.snapshots import compare_snapshots, create_inventory_snapshot, load_snapshot, write_snapshot
from tests.helpers import make_fake_steam


class SnapshotTests(unittest.TestCase):
    def test_snapshot_round_trip_and_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, second = make_fake_steam(root)
            before = create_inventory_snapshot(steam)
            before_path = write_snapshot(before, root / "before.json")
            self.assertEqual(len(load_snapshot(before_path)["games"]), 2)

            manifest = steam / "steamapps" / "appmanifest_10.acf"
            manifest.write_text(manifest.read_text(encoding="utf-8").replace('"123"', '"124"'), encoding="utf-8")
            (second / "steamapps" / "appmanifest_20.acf").unlink()
            (second / "steamapps" / "appmanifest_30.acf").write_text(
                '"AppState" { "appid" "30" "name" "Day of Defeat" "buildid" "1" }', encoding="utf-8"
            )
            after = create_inventory_snapshot(steam)

            result = compare_snapshots(before, after)

            self.assertEqual(result["counts"], {"added": 1, "removed": 1, "changed": 1})
            self.assertEqual(result["added"][0]["app_id"], "30")
            self.assertEqual(result["removed"][0]["app_id"], "20")
            self.assertIn("build_id", result["changed"][0]["changes"])
            self.assertIn("manifest_sha256", result["changed"][0]["changes"])

    def test_invalid_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"schema_version": 1, "games": [{"app_id": "oops"}]}), encoding="utf-8")
            with self.assertRaises(FourUFourFreeError):
                load_snapshot(path)


if __name__ == "__main__":
    unittest.main()
