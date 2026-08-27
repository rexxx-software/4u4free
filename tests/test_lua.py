import tempfile
import unittest
from pathlib import Path

from four_u_four_free.lua import inspect_lua, redact, strip_comments


class LuaTests(unittest.TestCase):
    def test_active_directives_are_parsed_and_comments_ignored(self):
        key = "a" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "480.lua"
            path.write_text(
                f'''-- addappid(999, 1, "{'b' * 64}")
                addappid(481, 1, "{key}")
                --[[ setManifestid(999, "1") ]]
                setManifestid(481, "123456789")
                addtoken(480, "private-token")
                ''',
                encoding="utf-8",
            )
            info = inspect_lua(path)
        self.assertEqual(info.inferred_app_id, "480")
        self.assertEqual(len(info.app_directives), 1)
        self.assertEqual(info.manifests, {"481": "123456789"})
        self.assertEqual(info.tokens[0].token, "private-token")
        public = info.to_dict()
        self.assertNotEqual(public["app_directives"][0]["key"], key)
        self.assertNotEqual(public["tokens"][0]["token"], "private-token")

    def test_comment_markers_inside_strings_are_preserved(self):
        self.assertEqual(strip_comments('addtoken(1, "a--b") -- tail'), 'addtoken(1, "a--b") ')

    def test_redaction(self):
        self.assertEqual(redact("1234567890"), "1234…7890")


if __name__ == "__main__":
    unittest.main()

