import json
import tempfile
import unittest
from pathlib import Path

from four_u_four_free.errors import FourUFourFreeError
from four_u_four_free.plugin_system import PluginManager


class PluginSystemTests(unittest.TestCase):
    def _plugin(self, root: Path, *, entrypoint="plugin.py") -> Path:
        folder = root / "counter"
        folder.mkdir()
        (folder / "plugin.json").write_text(
            json.dumps(
                {
                    "id": "counter",
                    "name": "Counter",
                    "version": "1.0",
                    "entrypoint": entrypoint,
                    "permissions": ["installed_games"],
                }
            ),
            encoding="utf-8",
        )
        if entrypoint == "plugin.py":
            (folder / "plugin.py").write_text(
                "def setup(api):\n"
                "    api.register_tool('Count', 'Counts games', "
                "lambda: len(api.installed_games()))\n",
                encoding="utf-8",
            )
        return folder

    def test_plugins_are_opt_in_and_register_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._plugin(root)
            manager = PluginManager(root)
            states = manager.load(
                globally_enabled=False,
                enabled_ids=["counter"],
                games=[{"app_id": "42"}],
            )
            self.assertEqual(states[0].status, "Disabled")
            self.assertEqual(manager.tools, [])

            states = manager.load(
                globally_enabled=True,
                enabled_ids=["counter"],
                games=[{"app_id": "42"}],
            )
            self.assertTrue(states[0].status.startswith("Loaded"))
            self.assertEqual(manager.tools[0].callback(), 1)

    def test_entrypoint_cannot_escape_plugin_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._plugin(root, entrypoint="../outside.py")
            (root / "outside.py").write_text("def setup(api): pass", encoding="utf-8")
            with self.assertRaisesRegex(FourUFourFreeError, "inside its plugin folder"):
                PluginManager(root).discover()
