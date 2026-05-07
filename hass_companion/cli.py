"""CLI entry point for hass-companion."""

import argparse
import asyncio
import sys

from hass_companion import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for hass-companion."""
    parser = argparse.ArgumentParser(
        prog="hass-companion",
        description="Home Assistant companion for Linux/macOS",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate config and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Create entities without connecting to MQTT, print summary and exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    from hass_companion.main import dry_run, run_app, setup_logging, validate_config

    setup_logging(args.log_level)

    if args.validate:
        sys.exit(validate_config(args.config))

    if args.dry_run:
        sys.exit(dry_run(args.config))

    try:
        asyncio.run(run_app(args.config))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
