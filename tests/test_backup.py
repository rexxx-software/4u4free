import json
import tempfile
import unittest
from pathlib import Path

from four_u_four_free.backup import create_backup
from four_u_four_free.errors import FourUFourFreeError
from four_u_four_free.integrity import restore_backup, verify_backup
from tests.helpers import make_fake_steam


class BackupTests(unittest.TestCase):
    def test_backup_verify_dry_run_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, _ = make_fake_steam(root)
            backup = create_backup(steam, root / "backup", [steam, root / "Library Two"])
            self.assertGreaterEqual(len(backup.files), 5)
            self.assertTrue(verify_backup(backup.destination).valid)

            plan = restore_backup(backup.destination, steam)
            self.assertFalse(plan["applied"])
            original = (steam / "config" / "config.vdf").read_text(encoding="utf-8")
            external_manifest = root / "Library Two" / "steamapps" / "appmanifest_20.acf"
            external_original = external_manifest.read_text(encoding="utf-8")
            (steam / "config" / "config.vdf").write_text("changed", encoding="utf-8")
            external_manifest.write_text("changed", encoding="utf-8")
            result = restore_backup(backup.destination, steam, apply=True, pre_restore_output=root / "pre-restore")
            self.assertTrue(result["applied"])
            self.assertEqual((steam / "config" / "config.vdf").read_text(encoding="utf-8"), original)
            self.assertEqual(external_manifest.read_text(encoding="utf-8"), external_original)
            self.assertTrue((root / "pre-restore" / "backup-manifest.json").is_file())

    def test_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, _ = make_fake_steam(root)
            backup = create_backup(steam, root / "backup")
            manifest = json.loads(backup.manifest.read_text(encoding="utf-8"))
            first = backup.destination / Path(manifest["files"][0]["backup"])
            first.write_text("tampered", encoding="utf-8")
            self.assertFalse(verify_backup(backup.destination).valid)

    def test_traversal_and_unregistered_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, _ = make_fake_steam(root)
            backup = create_backup(steam, root / "backup", [steam, root / "Library Two"])
            manifest = json.loads(backup.manifest.read_text(encoding="utf-8"))
            original = json.loads(json.dumps(manifest))
            manifest["files"][0]["target"] = "../outside.txt"
            backup.manifest.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(FourUFourFreeError):
                verify_backup(backup.destination)

            original["files"][0]["target_root"] = str(root / "Not Registered")
            backup.manifest.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaises(FourUFourFreeError):
                restore_backup(backup.destination, steam)


if __name__ == "__main__":
    unittest.main()
