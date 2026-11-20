"""Comandos de administración: ``python -m app.cli seed``."""

from __future__ import annotations

import argparse
import logging
import sys

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services import seed

log = logging.getLogger("app.cli")


def cmd_seed(_: argparse.Namespace) -> int:
    settings = get_settings()
    with get_sessionmaker()() as db:
        results = seed.seed_all(db, settings.ml_gold_path, settings.lider_seed_path)
    for name, stats in results.items():
        log.info("seed %s: %s", name, stats)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="Carga/actualiza el catálogo (Gold ETL + LIDER)").set_defaults(
        func=cmd_seed
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
