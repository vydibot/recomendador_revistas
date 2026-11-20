"""Importación de revistas desde CSV (mismo formato que el prototipo LIDER)."""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.journal import ImportReport
from app.services import journals as service
from app.services import mappers
from app.services import normalizers as nz

MAX_ROWS = 5_000


class CsvFormatError(ValueError):
    pass


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError("El archivo debe estar codificado en UTF-8") from exc
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [col for col in mappers.LIDER_REQUIRED_COLUMNS if col not in headers]
    if missing:
        raise CsvFormatError(f"Faltan columnas obligatorias: {', '.join(missing)}")
    rows = []
    for raw in reader:
        rows.append({(key or "").strip(): value for key, value in raw.items()})
        if len(rows) > MAX_ROWS:
            raise CsvFormatError(f"El CSV supera el máximo de {MAX_ROWS} filas")
    return rows


def import_rows(
    db: Session, rows: list[dict[str, Any]], mode: str = "skip", dry_run: bool = True
) -> ImportReport:
    """``mode``: ``skip`` ignora duplicados por ISSN, ``update`` los actualiza, ``add`` los crea."""
    report = ImportReport(
        dry_run=dry_run,
        mode=mode,
        rows=len(rows),
        created=0,
        updated=0,
        skipped=0,
        invalid=0,
        duplicates=[],
        errors=[],
    )
    for line, record in enumerate(rows, start=2):
        if not mappers.is_valid_lider_record(record):
            report.invalid += 1
            report.errors.append(f"Fila {line}: sin nombre de revista válido")
            continue
        values = mappers.from_lider(record)
        for key in ("origin", "source_key", "sources"):
            values.pop(key)
        duplicates = service.find_issn_duplicates(
            db, [values.get("issn_print"), values.get("issn_electronic")]
        )
        if duplicates:
            report.duplicates.append(f"{values['title']} ↔ {duplicates[0].title}")
            if mode == "skip":
                report.skipped += 1
                continue
        if dry_run:
            report.updated += 1 if duplicates and mode == "update" else 0
            report.created += 0 if duplicates and mode == "update" else 1
            continue
        if duplicates and mode == "update":
            service.apply_values(db, duplicates[0], values)
            duplicates[0].locally_modified = True
            report.updated += 1
        else:
            journal = service.create_journal(db, values)
            journal.details = {
                "importado_csv": True,
                "titulo_normalizado": nz.search_key(journal.title),
            }
            report.created += 1
        db.commit()
    return report
