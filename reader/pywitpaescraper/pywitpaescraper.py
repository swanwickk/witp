import argparse
import logging
import struct
from pathlib import Path

# local patch (ekko): rich removed so the 32-bit embeddable Python needs no pip installs
from witpae_today import WITPAE_Today


def setup_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[logging.StreamHandler()],
    )
    return logging.getLogger("pywitpae")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrapes WITPAE save files and game log files for one side per run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --dll-dir DIR --start-of-day-file SOD --end-of-day-file EOD --ALLIED\n"
            "  %(prog)s --dll-dir DIR --start-of-day-file SOD --end-of-day-file EOD --JAPAN\n"
            "\n"
            "Exactly one of --ALLIED/--US or --JAPAN is required.\n"
            "\n"
            "NOTE: Must be run with a 32-bit Python interpreter."
        ),
    )
    parser.add_argument(
        "--dll-dir",
        dest="dll_dir",
        type=Path,
        required=True,
        help="Directory containing DLL files.",
    )
    parser.add_argument(
        "--start-of-day-file",
        dest="start_of_day_file",
        type=Path,
        required=True,
        help="Path to start-of-day file.",
    )
    parser.add_argument(
        "--end-of-day-file",
        dest="end_of_day_file",
        type=Path,
        required=True,
        help="Path to end-of-day file.",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        type=Path,
        default=None,
        help=(
            "Directory for JSON exports. If omitted, defaults to a side-specific "
            "subdirectory (JAPAN or ALLIED) under the PWS file directory."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level.",
    )
    side_group = parser.add_mutually_exclusive_group(required=True)
    side_group.add_argument(
        "--US",
        "--ALLIED",
        "--allied",
        "--alllied",
        dest="side",
        action="store_const",
        const="ALLIED",
        help="Load Allied nations only (excludes IJA/IJN).",
    )
    side_group.add_argument(
        "--JAPAN",
        "--japan",
        dest="side",
        action="store_const",
        const="JAPAN",
        help="Load IJA/IJN only (excludes Allied nations).",
    )
    return parser


def parse_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    return parser.parse_args()


def main() -> int:
    parser = build_parser()
    args = parse_args(parser)
    logger = setup_logging(args.log_level)

    logger.info("Starting run")
    logger.info("dll_dir=%s", args.dll_dir)
    logger.info("start_of_day_file=%s", args.start_of_day_file)
    logger.info("end_of_day_file=%s", args.end_of_day_file)
    logger.info("side=%s", args.side)

    if args.output_dir is None:
        default_subdir = "JAPAN" if args.side == "JAPAN" else "ALLIED"
        args.output_dir = args.end_of_day_file.parent / default_subdir

    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("output_dir=%s", args.output_dir)

    if not args.dll_dir.exists() or not args.dll_dir.is_dir():
        logger.error("DLL directory does not exist or is not a directory: %s", args.dll_dir)
        return 1

    # local patch (ekko): verified with `objdump -p pwsdll.dll` that this build imports only
    # KERNEL32.dll, so pwsdll7.dll is not actually needed. Require it only if present.
    required_dlls = ["pwsdll.dll"] + (["pwsdll7.dll"] if (args.dll_dir / "pwsdll7.dll").exists() else [])
    missing_dlls = [name for name in required_dlls if not (args.dll_dir / name).exists()]
    if missing_dlls:
        logger.error("Missing required DLL(s) in %s: %s", args.dll_dir, ", ".join(missing_dlls))
        return 1

    if not args.start_of_day_file.exists() or not args.start_of_day_file.is_file():
        logger.error("Start-of-day file does not exist or is not a file: %s", args.start_of_day_file)
        return 1
    if not args.end_of_day_file.exists() or not args.end_of_day_file.is_file():
        logger.error("End-of-day file does not exist or is not a file: %s", args.end_of_day_file)
        return 1

    witpae_today = WITPAE_Today(
        dll_dir=args.dll_dir,
        start_of_day_file=args.start_of_day_file,
        end_of_day_file=args.end_of_day_file,
        side=args.side,
    )

    logger.debug("All input paths validated")
    logger.debug("Initialized WITPAE_Today: %s", witpae_today)
    witpae_today.export_json(args.output_dir)
    logger.info("Wrote JSON exports to %s", args.output_dir)
    return 0


if __name__ == "__main__":
    parser = build_parser()
    if struct.calcsize("P") * 8 != 32:
        parser.print_usage()
        raise SystemExit("This script must be run with a 32-bit Python interpreter.")
    raise SystemExit(main())