import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from four_u_four_free.cli import main
from tests.helpers import make_fake_steam


class CLITests(unittest.TestCase):
    def setUp(self):
        self.data_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.data_directory.cleanup)
        variable = "LOCALAPPDATA" if os.name == "nt" else "XDG_CONFIG_HOME"
        self.environment = patch.dict(os.environ, {variable: self.data_directory.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_cli(self, *arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(list(arguments))
        return code, output.getvalue(), errors.getvalue()

    def test_read_only_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, _ = make_fake_steam(root)
            code, output, errors = self.run_cli(
                "doctor", "--steam-root", str(steam), "--json"
            )
            self.assertEqual((code, errors), (0, ""))
            self.assertIn('"steam_found": true', output)
            code, output, _ = self.run_cli("games", "--steam-root", str(steam))
            self.assertEqual(code, 0)
            self.assertIn("Counter-Strike", output)
            code, output, _ = self.run_cli(
                "plan-import",
                str(steam / "config" / "stplug-in" / "10.lua"),
                "--steam-root",
                str(steam),
            )
            self.assertEqual(code, 0)
            self.assertIn("Dry-run import plan", output)

    def test_catalog_and_backup_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, _ = make_fake_steam(root)
            catalog = root / "catalog.sqlite3"
            code, _, errors = self.run_cli(
                "scan", "--catalog", str(catalog), "--steam-root", str(steam)
            )
            self.assertEqual((code, errors), (0, ""))
            code, output, _ = self.run_cli(
                "catalog", "--catalog", str(catalog), "stats", "--json"
            )
            self.assertEqual(code, 0)
            self.assertIn('"games": 2', output)
            backup = root / "backup"
            code, output, _ = self.run_cli(
                "backup", "--output", str(backup), "--steam-root", str(steam)
            )
            self.assertEqual(code, 0)
            self.assertIn("Backup created", output)
            code, output, _ = self.run_cli("verify-backup", str(backup))
            self.assertEqual(code, 0)
            self.assertIn("Valid: yes", output)

    def test_invalid_explicit_root_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, errors = self.run_cli(
                "games", "--steam-root", str(Path(directory) / "missing")
            )
        self.assertEqual(code, 2)
        self.assertIn("Steam was not found", errors)

    def test_dlc_validation_finds_nested_steam_api(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            release = game / "Release"
            release.mkdir()
            (release / "steam_api64.dll").write_bytes(b"dll")

            code, output, errors = self.run_cli(
                "dlc-unlocker", str(game), "--validate", "--json"
            )

        self.assertEqual((code, errors), (0, ""))
        self.assertIn('"steam_api64": true', output)

    def test_integrated_profiles_snapshots_managed_lua_and_config_io(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, _ = make_fake_steam(root)
            (steam / "userdata" / "7").mkdir(parents=True)
            config = root / "config.json"
            code, output, errors = self.run_cli(
                "profiles", "--steam-root", str(steam), "--json"
            )
            self.assertEqual((code, errors), (0, ""))
            self.assertIn('"account_id": "7"', output)

            before = root / "before.json"
            after = root / "after.json"
            code, _, errors = self.run_cli(
                "snapshot", "create", str(before), "--steam-root", str(steam)
            )
            self.assertEqual((code, errors), (0, ""))
            code, _, _ = self.run_cli(
                "snapshot", "create", str(after), "--steam-root", str(steam)
            )
            self.assertEqual(code, 0)
            code, output, _ = self.run_cli(
                "snapshot", "diff", str(before), str(after), "--json"
            )
            self.assertEqual(code, 0)
            self.assertIn('"changed": 0', output)

            code, output, _ = self.run_cli(
                "managed-lua", "list", "--steam-root", str(steam), "--json"
            )
            self.assertEqual(code, 0)
            self.assertIn('"inferred_app_id": "10"', output)
            code, output, _ = self.run_cli(
                "managed-lua", "quarantine", "10", "--steam-root", str(steam), "--json"
            )
            self.assertEqual(code, 0)
            self.assertIn('"applied": false', output)

            code, _, errors = self.run_cli(
                "--config", str(config), "config", "set", "--steam-root", str(steam)
            )
            self.assertEqual((code, errors), (0, ""))
            exported = root / "settings-export.json"
            code, _, _ = self.run_cli(
                "--config", str(config), "config", "export", str(exported)
            )
            self.assertEqual(code, 0)
            code, output, _ = self.run_cli(
                "--config",
                str(root / "imported.json"),
                "config",
                "import",
                str(exported),
                "--json",
            )
            self.assertEqual(code, 0)
            self.assertIn('"applied": false', output)


if __name__ == "__main__":
    unittest.main()
