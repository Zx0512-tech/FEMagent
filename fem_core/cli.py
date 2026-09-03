from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fem_core.health import build_health_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fem_core", description="FEMagent engineering core CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Return deterministic bootstrap health JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "health":
        print(json.dumps(build_health_report(), ensure_ascii=False, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
