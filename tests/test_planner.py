import tempfile
import unittest
from pathlib import Path

from four_u_four_free.lua import inspect_lua
from four_u_four_free.planner import make_import_plan


class PlannerTests(unittest.TestCase):
    def test_plan_is_explicitly_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "10.lua"
            source.write_text("addappid(10)\n", encoding="utf-8")
            plan = make_import_plan(inspect_lua(source), root / "Steam")
        self.assertTrue(plan.actions[0].implemented)
        self.assertFalse(plan.actions[-1].implemented)
        self.assertIn("dry-run", " ".join(plan.warnings).lower())


if __name__ == "__main__":
    unittest.main()

