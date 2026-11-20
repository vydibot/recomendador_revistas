"""Carga idempotente del catálogo: Gold del ETL + prototipo LIDER.

Se puede ejecutar en cada arranque: inserta revistas nuevas y actualiza las
existentes, **salvo** las que un usuario editó (``locally_modified``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Journal
from app.services import journals as service
from app.services import mappers

log = logging.getLogger(__name__)


@dataclass
class SeedStats:
    created: int = 0
    updated: int = 0
    protected: int = 0
    skipped_invalid: int = 0
    pruned: int = 0

    def __str__(self) -> str:
        return (
            f"creadas={self.created} actualizadas={self.updated} "
            f"protegidas(editadas)={self.protected} descartadas={self.skipped_invalid} "
            f"retiradas={self.pruned}"
        )


def _upsert(db: Session, origin: str, rows: list[dict[str, Any]]) -> SeedStats:
    stats = SeedStats()
    existing = {
        journal.source_key: journal
        for journal in db.scalars(select(Journal).where(Journal.origin == origin))
    }
    for values in rows:
        key = values["source_key"]
        journal = existing.get(key)
        if journal is None:
            journal = Journal(origin=origin, source_key=key, sources=[], details={})
            db.add(journal)
            existing[key] = journal
            stats.created += 1
        elif journal.locally_modified:
            stats.protected += 1
            continue
        else:
            stats.updated += 1
        service.apply_values(db, journal, values, reparse_text=False)
    # Filas de una carga anterior que ya no existen en la fuente (salvo las editadas a mano).
    incoming = {values["source_key"] for values in rows}
    for key, journal in existing.items():
        if key not in incoming and not journal.locally_modified:
            db.delete(journal)
            stats.pruned += 1
    db.commit()
    return stats


def seed_etl(db: Session, gold_path: Path) -> SeedStats:
    if not gold_path.exists():
        log.warning("Gold del ETL no encontrado: %s (se omite)", gold_path)
        return SeedStats()
    frame = pd.read_parquet(gold_path) if gold_path.suffix == ".parquet" else pd.read_csv(gold_path)
    return _upsert(db, "etl", mappers.collapse_gold(frame))


def seed_lider(db: Session, path: Path) -> SeedStats:
    if not path.exists():
        log.warning("Semilla LIDER no encontrada: %s (se omite)", path)
        return SeedStats()
    records = json.loads(path.read_text(encoding="utf-8"))
    valid = [record for record in records if mappers.is_valid_lider_record(record)]
    rows = mappers.dedupe_lider(mappers.from_lider(record) for record in valid)
    stats = _upsert(db, "lider", rows)
    stats.skipped_invalid = len(records) - len(valid)
    return stats


def seed_all(db: Session, gold_path: Path, lider_path: Path) -> dict[str, SeedStats]:
    return {
        "etl": seed_etl(db, gold_path),
        "lider": seed_lider(db, lider_path),
    }
