"""Command-line entry point for adoption and diagnostics."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from ._version import __version__
from .doctor import DoctorOptions, format_report, run_doctor
from .starter import generate_starter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyrealtime", description="Create and verify PyRealtime applications")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="generate a minimal backend in a new or empty directory")
    init.add_argument("directory", nargs="?", default="pyrealtime-starter")

    doctor = commands.add_parser("doctor", help="check configuration and optional connectivity without printing secrets")
    doctor.add_argument("--api-url", default=os.getenv("PYREALTIME_API_URL", "").strip() or None)
    doctor.add_argument("--origin", default=os.getenv("PYREALTIME_DOCTOR_ORIGIN", "").strip() or None)
    doctor.add_argument("--no-network", action="store_true")
    doctor.add_argument("--skip-openai", action="store_true")
    doctor.add_argument("--strict", action="store_true", help="return failure for warnings as well as errors")

    demo = commands.add_parser("demo", help="run an explicit local fake-chat API without an OpenAI key")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "init":
        try:
            created = generate_starter(Path(args.directory))
        except FileExistsError as exc:
            print(f"Error: {exc}")
            return 2
        print(f"Created PyRealtime starter at {created[0].parent}")
        print("Next: copy .env.example to .env, install requirements.txt, and run the README command.")
        return 0
    if args.command == "doctor":
        report = run_doctor(DoctorOptions(
            api_url=args.api_url,
            origin=args.origin,
            check_openai=not args.skip_openai,
            network=not args.no_network,
        ))
        print(format_report(report))
        return report.exit_code(strict=args.strict)
    if args.command == "demo":
        try:
            import uvicorn
        except ImportError:
            print("Error: install pyrealtime-ai[api] to run the demo")
            return 2
        token = os.getenv("APP_API_KEY", "").strip() or "local-demo-token"
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            print("Error: no-key demo mode may bind only to a loopback host.")
            return 2
        print("Starting explicit fake-chat demo; no OpenAI request will be made.")
        print("Use the configured APP_API_KEY, or 'local-demo-token' when none is configured.")
        from .demo import create_demo_app

        uvicorn.run(create_demo_app(token=token), host=args.host, port=args.port)
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
