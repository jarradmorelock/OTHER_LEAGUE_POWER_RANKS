import unittest
from contextlib import redirect_stderr
from io import StringIO

from other_league_rankings.__main__ import build_parser


class CliTests(unittest.TestCase):
    def test_defaults_to_all_leagues_and_dry_run(self):
        args = build_parser().parse_args([])
        self.assertEqual(args.league, "all")
        self.assertFalse(args.publish)
        self.assertFalse(args.force)

    def test_publish_week_and_force_options(self):
        args = build_parser().parse_args(["--league", "sec", "--publish", "--force", "--week", "4"])
        self.assertEqual(args.league, "sec")
        self.assertTrue(args.publish)
        self.assertTrue(args.force)
        self.assertEqual(args.week, 4)

    def test_publish_and_dry_run_are_mutually_exclusive(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["--publish", "--dry-run"])


if __name__ == "__main__":
    unittest.main()
