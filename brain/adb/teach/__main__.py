"""CLI: python -m adb.teach record|replay|show"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BRAIN_ROOT = _REPO_ROOT / "brain"
for path in (_REPO_ROOT, _BRAIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from brain.adb.device import device_id_from_serial, resolve_serial  # noqa: E402
from brain.adb.teach.demo import run_demo  # noqa: E402
from brain.adb.teach.replay import run_replay  # noqa: E402
from brain.adb.teach.session import run_record  # noqa: E402
from brain.adb.teach.store import VALID_SKILLS, TeachStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Human teach mode for Instagram Reels skills")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="Interactive demo recording")
    p_rec.add_argument("--skill", default="open_comments", choices=sorted(VALID_SKILLS))
    p_rec.add_argument("--count", type=int, default=10, help="Episodes to record")
    p_rec.add_argument("--open-reels", action="store_true", help="Open Reels before teaching")
    p_rec.add_argument("--serial", default=None)
    p_rec.add_argument("--root", default=None, help="Override data/teach root")

    p_rep = sub.add_parser("replay", help="Deterministic replay of taught coords")
    p_rep.add_argument("--skill", default="open_comments")
    p_rep.add_argument("--trials", type=int, default=10)
    p_rep.add_argument("--serial", default=None)
    p_rep.add_argument("--no-open-reels", action="store_true")
    p_rep.add_argument("--root", default=None)

    p_show = sub.add_parser("show", help="Print aggregated skill")
    p_show.add_argument("--skill", default="open_comments")
    p_show.add_argument("--serial", default=None)
    p_show.add_argument("--root", default=None)

    p_demo = sub.add_parser("demo", help="Print learnt skill and try taught tap on device")
    p_demo.add_argument("--trials", type=int, default=3)
    p_demo.add_argument("--serial", default=None)
    p_demo.add_argument("--root", default=None)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    root = Path(args.root) if getattr(args, "root", None) else None
    store = TeachStore(root=root) if root else TeachStore()

    if args.cmd == "record":
        n = run_record(
            skill=args.skill,
            count=args.count,
            open_reels=args.open_reels,
            serial=args.serial,
            store=store,
        )
        return 0 if n >= 0 else 1

    if args.cmd == "replay":
        try:
            report = run_replay(
                skill=args.skill,
                trials=args.trials,
                serial=args.serial,
                open_reels=not args.no_open_reels,
                store=store,
            )
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        rate = float(report.get("pass_rate") or 0)
        return 0 if rate >= 0.7 else 2

    if args.cmd == "show":
        try:
            serial = resolve_serial(args.serial)
            device_id = device_id_from_serial(serial)
        except Exception:
            device_id = "default"
            print("(no device — showing skills matching any device_id if present)")
            # Fall back: list skill files for this skill
            matches = list(store.skills_dir.glob(f"{args.skill}__*.json"))
            if not matches:
                print(f"No skill file for {args.skill}")
                return 1
            for m in matches:
                print(m.read_text(encoding="utf-8"))
            return 0
        data = store.get_skill(args.skill, device_id)
        if not data:
            print(f"No skill for {args.skill} device={device_id}")
            return 1
        print(
            f"skill={data.get('skill_id')} device={data.get('device_id')} "
            f"n_ok={data.get('n_ok')} xy=({data.get('x')}, {data.get('y')}) "
            f"frac=({data.get('x_frac')}, {data.get('y_frac')})"
        )
        print(f"episodes={data.get('episode_ids')}")
        return 0

    if args.cmd == "demo":
        try:
            report = run_demo(trials=args.trials, serial=args.serial, store=store)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0 if float(report.get("pass_rate") or 0) > 0 else 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
