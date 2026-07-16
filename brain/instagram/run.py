"""CLI entrypoint — Instagram API transport (replaces ADB executor)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRAIN_ROOT = _REPO_ROOT / "brain"
for path in (_REPO_ROOT, _BRAIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:
    from dotenv import load_dotenv

    # Defaults in brain/.env; repo-root .env overrides (where you set IG creds).
    load_dotenv(_BRAIN_ROOT / ".env")
    load_dotenv(_REPO_ROOT / ".env", override=True)
except ImportError:
    pass

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import brain.app.instagram.client as _ig_client_mod  # noqa: E402

_ig_client_mod._client = None

from brain.app.instagram.client import get_instagram_client  # noqa: E402
from brain.app.instagram.orchestrator import InstagramOrchestrator  # noqa: E402
from brain.app.instagram.runner import run_routine  # noqa: E402


def _cmd_login(_: argparse.Namespace) -> int:
    ig = get_instagram_client()
    ig.login(prompt_2fa=True)
    info = ig.me()
    print(json.dumps(info, indent=2))
    return 0


def _cmd_login_cookies(args: argparse.Namespace) -> int:
    ig = get_instagram_client()
    raw = args.file.read() if args.file else None
    ig.login_by_cookies(raw)
    info = ig.me()
    print(json.dumps(info, indent=2))
    return 0


def _cmd_doctor(_: argparse.Namespace) -> int:
    rows = get_instagram_client().doctor()
    for row in rows:
        mark = {"pass": "OK", "fail": "FAIL", "warn": "WARN"}.get(row["status"], row["status"])
        print(f"[{mark}] {row['check']}: {row['detail']}")
    return 0 if all(r["status"] == "pass" for r in rows) else 1


def _cmd_status(_: argparse.Namespace) -> int:
    print(json.dumps(InstagramOrchestrator().status(), indent=2))
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    orch = InstagramOrchestrator()
    result = orch.plan_reels_day(mode=args.mode, sessions=args.sessions)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_reels(args: argparse.Namespace) -> int:
    read_only = args.dry_run or args.mode == "read_only"
    result = InstagramOrchestrator().run_reels_now(
        reels_max=args.reels_max,
        comment_likes_per_reel=args.comment_likes_per_reel,
        read_only=read_only,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_daemon(args: argparse.Namespace) -> int:
    InstagramOrchestrator().daemon(poll_seconds=args.poll)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    result = run_routine(
        args.routine,  # type: ignore[arg-type]
        mode=args.mode,
        reels_max=args.reels_max,
        comment_likes_per_reel=args.comment_likes_per_reel,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Friday UGC — Instagram API worker. Primary: scroll reels + like comments."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Login with username/password (+ 2FA prompt)").set_defaults(func=_cmd_login)
    p_cookies = sub.add_parser(
        "login-cookies",
        help="Login from Cookie-Editor JSON (FRIDAY_IG_SESSION_JSON or --file)",
    )
    p_cookies.add_argument("--file", type=argparse.FileType("r", encoding="utf-8"), default=None)
    p_cookies.set_defaults(func=_cmd_login_cookies)
    sub.add_parser("doctor", help="Check credentials and API connectivity").set_defaults(func=_cmd_doctor)
    sub.add_parser("status", help="Operator + daily budget status").set_defaults(func=_cmd_status)

    p_plan = sub.add_parser("plan", help="Schedule reels-only sessions for today")
    p_plan.add_argument("--mode", choices=["read_only", "full"], default="full")
    p_plan.add_argument("--sessions", type=int, default=4)
    p_plan.set_defaults(func=_cmd_plan)

    p_reels = sub.add_parser("reels", help="Scroll reels and like comments (one shot)")
    p_reels.add_argument("--reels-max", type=int, default=None)
    p_reels.add_argument("--comment-likes-per-reel", type=int, default=None)
    p_reels.add_argument("--mode", choices=["read_only", "full"], default="full")
    p_reels.add_argument("--dry-run", action="store_true", help="Simulate without API writes")
    p_reels.set_defaults(func=_cmd_reels)

    p_daemon = sub.add_parser("daemon", help="Poll operator queue and run reels tasks")
    p_daemon.add_argument("--poll", type=float, default=None, help="Seconds between polls")
    p_daemon.set_defaults(func=_cmd_daemon)

    p_run = sub.add_parser("run", help="Run reels_comment_likes routine")
    p_run.add_argument(
        "--routine",
        default="reels_comment_likes",
        choices=["reels_comment_likes", "reels_scroll"],
    )
    p_run.add_argument("--mode", choices=["read_only", "full"], default="full")
    p_run.add_argument("--reels-max", type=int, default=None)
    p_run.add_argument("--comment-likes-per-reel", type=int, default=None)
    p_run.set_defaults(func=_cmd_run)

    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not os.getenv("FRIDAY_LLM_PROVIDER"):
        os.environ.setdefault("FRIDAY_LLM_PROVIDER", "mock")

    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
