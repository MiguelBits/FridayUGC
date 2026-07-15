"""CLI entrypoint for the ADB executor loop."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRAIN_ROOT = _REPO_ROOT / "brain"
for path in (_REPO_ROOT, _BRAIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from brain.adb.loop import LoopConfig, run_loop_sync  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Friday UGC ADB executor")
    parser.add_argument("--brain-url", default=os.getenv("FRIDAY_BRAIN_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--token", default=os.getenv("FRIDAY_API_TOKEN", ""))
    parser.add_argument("--goal", default="Open Instagram and scroll Reels")
    parser.add_argument("--mode", choices=["read_only", "full"], default="read_only")
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--serial", default=None, help="ADB device serial when multiple connected")
    parser.add_argument("--autonomous", action="store_true", help="Skip terminal approval prompts")
    parser.add_argument(
        "--routine",
        choices=[
            "full_session",
            "reels_scroll",
            "reels_comment_likes",
            "stories",
            "feed_engagement",
            "inbox",
            "comments",
            "post",
        ],
        default=None,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.token:
        parser.error("Set FRIDAY_API_TOKEN or pass --token")

    config = LoopConfig(
        brain_url=args.brain_url,
        token=args.token,
        goal=args.goal,
        mode=args.mode,  # type: ignore[arg-type]
        max_steps=args.max_steps,
        serial=args.serial,
        autonomous=args.autonomous,
        routine=args.routine,  # type: ignore[arg-type]
    )
    state = run_loop_sync(config)
    logging.info("Finished after %d steps", state.step)


if __name__ == "__main__":
    main()
