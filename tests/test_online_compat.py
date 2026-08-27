import unittest

from four_u_four_free.online_compat import (
    PEACOCK_SETUP_URL,
    online_compatibility,
)


class OnlineCompatibilityTests(unittest.TestCase):
    def test_hitman_world_of_assassination_uses_peacock_profile(self):
        profile = online_compatibility("1659040")
        self.assertFalse(profile.generic_supported)
        self.assertEqual(profile.provider, "Peacock")
        self.assertEqual(profile.guide_url, PEACOCK_SETUP_URL)
        self.assertIn("does not replace", profile.detail)

    def test_unknown_game_remains_explicitly_experimental(self):
        profile = online_compatibility("42")
        self.assertTrue(profile.generic_supported)
        self.assertIn("Experimental", profile.status)
        self.assertFalse(profile.guide_url)


if __name__ == "__main__":
    unittest.main()
