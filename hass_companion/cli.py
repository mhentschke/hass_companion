"""CLI entry point for hass-companion."""

import argparse
import asyncio
import sys

from hass_companion import __version__


def _build_service_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'service' subcommand group."""
    service_parser = subparsers.add_parser(
        "service",
        help="Manage the hass-companion system service",
    )
    service_sub = service_parser.add_subparsers(dest="service_action")

    # service install
    install_parser = service_sub.add_parser(
        "install",
        help="Install hass-companion as a system service",
    )
    install_parser.add_argument(
        "--user",
        action="store_true",
        help="Install as a user-level service (Linux systemd only)",
    )
    install_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file to embed in the service (default: config.yaml)",
    )

    # service uninstall
    uninstall_parser = service_sub.add_parser(
        "uninstall",
        help="Uninstall the hass-companion system service",
    )
    uninstall_parser.add_argument(
        "--user",
        action="store_true",
        help="Uninstall the user-level service (Linux systemd only)",
    )

    # service status
    service_sub.add_parser(
        "status",
        help="Show the current service installation status",
    )


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
        "--log-format",
        default="text",
        choices=["text", "json"],
        help="Log output format (default: text)",
    )
    parser.add_argument(
        "--watch-config",
        action="store_true",
        help="Watch configuration file for changes and reload automatically",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")
    _build_service_parser(subparsers)

    return parser


def _handle_service(args: argparse.Namespace) -> None:
    """Handle the 'service' subcommand."""
    from hass_companion.service import ServiceManager

    manager = ServiceManager()

    if args.service_action == "install":
        config_path = str(args.config)
        manager.install(config_path=config_path, user=args.user)
    elif args.service_action == "uninstall":
        manager.uninstall(user=args.user)
    elif args.service_action == "status":
        status = manager.status()
        if not status.installed:
            print("Service not installed.")
            sys.exit(1)
        state = "running" if status.running else "stopped"
        enabled = "enabled" if status.enabled else "disabled"
        print(f"Service: installed ({enabled}, {state})")
        if status.unit_path:
            print(f"  Path: {status.unit_path}")
    else:
        # No service action specified, print help
        build_parser().parse_args(["service", "--help"])


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Handle service subcommand
    if args.command == "service":
        _handle_service(args)
        return

    from core.logging import setup_logging
    from hass_companion.main import dry_run, run_app, validate_config

    setup_logging(args.log_level, format=args.log_format)

    if args.validate:
        sys.exit(validate_config(args.config))

    if args.dry_run:
        sys.exit(dry_run(args.config))

    # Acquire single-instance lock before starting the app
    from core.config import ConfigError, load_config
    from core.lockfile import InstanceAlreadyRunning, SingleInstanceLock

    from dotenv import load_dotenv

    load_dotenv()

    try:
        app_config = load_config(args.config)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    lock = SingleInstanceLock(device_id=app_config.hass.device_id)
    try:
        lock.acquire()
    except InstanceAlreadyRunning as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(run_app(args.config, watch_config=args.watch_config))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        lock.release()
