import unittest

from four_u_four_free.vdf import VDFParseError, get_mapping, get_string, parse_vdf


class VDFTests(unittest.TestCase):
    def test_nested_comments_and_escaped_path(self):
        parsed = parse_vdf(
            """// comment
            "libraryfolders" {
                "0" { "path" "C:\\\\Program Files (x86)\\\\Steam" }
            }
            """
        )
        zero = get_mapping(get_mapping(parsed, "LIBRARYFOLDERS"), "0")
        self.assertEqual(get_string(zero, "PATH"), r"C:\Program Files (x86)\Steam")

    def test_unterminated_string_is_rejected(self):
        with self.assertRaises(VDFParseError):
            parse_vdf('"key" "unterminated')

    def test_missing_brace_is_rejected(self):
        with self.assertRaises(VDFParseError):
            parse_vdf('"root" { "key" "value"')


if __name__ == "__main__":
    unittest.main()
