"""Command-line entry point for local previews and GitHub Actions."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import load_leagues
from .runner import run


def build_parser() -> argparse.ArgumentParser:
    configs = load_leagues(Path(__file__).resolve().parents[1] / "leagues.json")
    parser = argparse.ArgumentParser(description="Build or publish weekly power rankings for connected Sleeper leagues.")
    parser.add_argument("--league", choices=["all", *configs.keys()], default="all")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Build graphics but do not post or advance state (default).")
    mode.add_argument("--publish", action="store_true", help="Post to each selected Discord Forum.")
    parser.add_argument("--force", action="store_true", help="Republish even if this league/week was already posted.")
    parser.add_argument("--week", type=int, help="Override Sleeper's current NFL week for a recovery run.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configs = load_leagues(Path(__file__).resolve().parents[1] / "leagues.json")
    summary = run(
        configs,
        selected=args.league,
        dry_run=not args.publish,
        force=args.force,
        week=args.week,
    )
    failed = False
    for key, status in summary.statuses.items():
        print(f"{key}: {status.state}")
        if status.message:
            print(f"  {status.message}")
        for warning in status.warnings:
            print(f"  warning: {warning}")
        failed |= status.state == "failed"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
