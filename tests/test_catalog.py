import tempfile
import unittest
from pathlib import Path

from four_u_four_free.catalog import Catalog
from four_u_four_free.steam import list_games, list_libraries
from tests.helpers import make_fake_steam


class CatalogTests(unittest.TestCase):
    def test_sync_query_and_lua_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam, _ = make_fake_steam(root)
            catalog = Catalog(root / "catalog.sqlite3")
            count = catalog.sync_games(list_games(list_libraries(steam)))
            self.assertEqual(count, 2)
            self.assertEqual(len(catalog.games("Counter")), 1)

            source = steam / "config" / "stplug-in" / "10.lua"
            imported = catalog.import_lua(source, root / "archive")
            self.assertTrue(imported.archived_path.is_file())
            self.assertFalse(imported.already_present)
            again = catalog.import_lua(source, root / "archive")
            self.assertTrue(again.already_present)
            self.assertEqual(catalog.stats()["lua_files"], 1)
            self.assertEqual(catalog.lua_files("10")[0]["inferred_app_id"], "10")


if __name__ == "__main__":
    unittest.main()
