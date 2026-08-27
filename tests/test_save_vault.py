import tempfile
import unittest
from pathlib import Path

from four_u_four_free.errors import FourUFourFreeError
from four_u_four_free.save_vault import SaveVault


class SaveVaultTests(unittest.TestCase):
    def test_snapshot_verify_and_safe_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "saves"
            source.mkdir()
            (source / "slot1.sav").write_text("first", encoding="utf-8")
            vault = SaveVault(root / "vault")

            snapshot = vault.create_snapshot("42", "Example", source)
            self.assertTrue(vault.verify_snapshot(snapshot))
            self.assertEqual(snapshot.file_count, 1)

            (source / "slot1.sav").write_text("changed", encoding="utf-8")
            result = vault.restore_snapshot(snapshot)
            self.assertEqual((source / "slot1.sav").read_text(encoding="utf-8"), "first")
            self.assertEqual(result.restored_files, 1)
            self.assertIsNotNone(result.safety_snapshot)
            self.assertEqual(len(vault.list_snapshots("42")), 2)

    def test_tampered_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "saves"
            source.mkdir()
            (source / "slot.sav").write_bytes(b"save")
            vault = SaveVault(root / "vault")
            snapshot = vault.create_snapshot("42", "Example", source)
            Path(snapshot.archive_path).write_bytes(b"tampered")

            self.assertFalse(vault.verify_snapshot(snapshot))
            with self.assertRaisesRegex(FourUFourFreeError, "SHA-256"):
                vault.restore_snapshot(snapshot)
