import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScheduleTests(unittest.TestCase):
    def test_weekly_schedule_is_saturday_at_fifteen_utc(self):
        workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '0 15 * * 6'", workflow)

    def test_workflow_maps_all_distinct_webhook_secrets(self):
        workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        for secret in (
            "BROKEN_HEARTS_WEEKLY_WEBHOOK",
            "ROCKY_TOP_RUMBLE_WEEKLY_WEBHOOK",
            "NINE_TO_FIVE_WEEKLY_WEBHOOK",
            "BEST_CHARACTERS_WEEKLY_WEBHOOK",
            "SEC_WEEKLY_WEBHOOK",
            "DONT_TELL_MY_WIFE_WEEKLY_WEBHOOK",
        ):
            self.assertIn(secret, workflow)

    def test_workflow_runs_tests_and_persists_successful_state(self):
        workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover", workflow)
        self.assertIn("git add -A -- state/", workflow)
        self.assertIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
