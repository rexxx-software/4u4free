import json
import unittest

from four_u_four_free.achievement_showcase import recommend_for_game
from four_u_four_free.errors import FourUFourFreeError


class AchievementShowcaseTests(unittest.TestCase):
    def test_unlocked_achievements_are_ranked_by_global_rarity(self):
        profile_xml = """<playerstats><achievements>
          <achievement closed="1"><apiname>COMMON</apiname><name>Common</name>
            <description>Common unlock</description><unlockTimestamp>100</unlockTimestamp></achievement>
          <achievement closed="1"><apiname>RARE</apiname><name>Rare</name>
            <description>Rare unlock</description><unlockTimestamp>200</unlockTimestamp></achievement>
          <achievement closed="0"><apiname>LOCKED</apiname><name>Locked</name></achievement>
        </achievements></playerstats>"""
        percentages = json.dumps(
            {
                "achievementpercentages": {
                    "achievements": [
                        {"name": "COMMON", "percent": 72.5},
                        {"name": "RARE", "percent": 0.4},
                        {"name": "LOCKED", "percent": 0.01},
                    ]
                }
            }
        )

        def fetch(url):
            return profile_xml if "steamcommunity" in url else percentages

        ranked = recommend_for_game("76561198000000000", "42", "Example", fetch_text=fetch)
        self.assertEqual([item.name for item in ranked], ["Rare", "Common"])
        self.assertEqual(ranked[0].global_percent, 0.4)

    def test_private_or_empty_profile_is_explained(self):
        with self.assertRaisesRegex(FourUFourFreeError, "private"):
            recommend_for_game(
                "76561198000000000",
                "42",
                "Example",
                fetch_text=lambda _url: "not xml",
            )
