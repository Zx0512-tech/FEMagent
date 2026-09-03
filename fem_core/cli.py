from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from fem_core.bridge import handle_request
from fem_core.health import build_health_report
from fem_core.protocol import error_envelope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fem_core", description="FEMagent engineering core CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Return deterministic bootstrap health JSON")
    subparsers.add_parser("bridge", help="Read one versioned bridge request from stdin and write one JSON response")
    return parser


def _run_bridge() -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        response = error_envelope(
            request_id="unknown",
            command="unknown",
            code="INVALID_JSON",
            message="Bridge stdin must contain one valid JSON request",
            details={"line": exc.lineno, "column": exc.colno},
        )
    else:
        response = handle_request(request, workspace=Path.cwd())
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "health":
        print(json.dumps(build_health_report(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "bridge":
        return _run_bridge()
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
