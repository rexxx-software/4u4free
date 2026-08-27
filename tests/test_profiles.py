import tempfile
import unittest
from pathlib import Path

from four_u_four_free.errors import FourUFourFreeError
from four_u_four_free.profiles import account_id_from_steam_id64, list_profiles
from tests.helpers import make_fake_steam


class ProfileTests(unittest.TestCase):
    def test_login_users_and_orphan_userdata_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            steam, _ = make_fake_steam(Path(directory))
            (steam / "config" / "loginusers.vdf").write_text(
                '''"users"
{
    "76561197960265729"
    {
        "AccountName" "alice"
        "PersonaName" "Alice"
        "MostRecent" "1"
        "RememberPassword" "1"
        "Timestamp" "123"
    }
}
''',
                encoding="utf-8",
            )
            (steam / "userdata" / "1").mkdir(parents=True)
            (steam / "userdata" / "42").mkdir()

            profiles = list_profiles(steam)

            self.assertEqual([profile.account_id for profile in profiles], ["1", "42"])
            self.assertEqual(profiles[0].persona_name, "Alice")
            self.assertTrue(profiles[0].most_recent)
            self.assertEqual(profiles[1].steam_id64, "")

    def test_steam_id_validation(self):
        self.assertEqual(account_id_from_steam_id64("76561197960265729"), "1")
        for value in ("", "-1", "abc", str(2**64)):
            with self.subTest(value=value), self.assertRaises(FourUFourFreeError):
                account_id_from_steam_id64(value)


if __name__ == "__main__":
    unittest.main()
