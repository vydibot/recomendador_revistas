"""ETL OpenAPC: pagos observados de APC a la capa silver.

El esquema de OpenAPC ha cambiado entre exportaciones. Este módulo acepta
los nombres habituales de la fuente, normaliza ISSN y APC, y rechaza HTML o
archivos sin columnas identificables para no convertir respuestas de error en
datos.
"""

import logging
import sys
from pathlib import Path

import pandas as pd

from config import FECHA_CAPTURA, OPENAPC_FILE, OPENAPC_SILVER
from normalize import convertir_a_usd, hash_registro, limpiar_issn

logger = logging.getLogger(__name__)


_COLUMN_ALIASES = {
    "issn_normalizado": ("issn", "journal_issn", "journal issn", "ISSN"),
    "apc_monto": (
        "apc", "apc_amount", "amount", "fee", "journal_fee", "journal_fees",
        "amount_paid", "apc_amount_paid", "usd", "euro",
    ),
    "apc_moneda": ("currency", "apc_currency", "currency_code"),
    "titulo": (
        "journal_name", "journal_full_title", "journal title", "title", "journal",
    ),
    "editorial": ("publisher", "publisher_name"),
}


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {str(column).strip().lower(): column for column in columns}
    for alias in aliases:
        if alias.lower() in normalized:
            return normalized[alias.lower()]
    return None


def _read_csv(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    prefix = raw[:512].lower()
    if b"<html" in prefix or b"<!doctype" in prefix or b"<?xml" in prefix:
        raise ValueError("OpenAPC contiene HTML/XML en lugar de un CSV")
    if not raw.strip():
        raise ValueError("OpenAPC está vacío")
    return pd.read_csv(path, dtype=str, sep=None, engine="python")


def procesar_openapc() -> pd.DataFrame:
    """Lee, valida y normaliza OpenAPC; guarda un parquet silver."""
    if not OPENAPC_FILE.exists():
        logger.warning("OpenAPC no encontrado: %s", OPENAPC_FILE)
        return pd.DataFrame()

    try:
        source = _read_csv(OPENAPC_FILE)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        logger.warning("OpenAPC no utilizable: %s", exc)
        return pd.DataFrame()

    issn_col = _find_column(list(source.columns), _COLUMN_ALIASES["issn_normalizado"])
    amount_col = _find_column(list(source.columns), _COLUMN_ALIASES["apc_monto"])
    if not issn_col or not amount_col:
        logger.warning("OpenAPC no tiene columnas de ISSN y APC reconocibles")
        return pd.DataFrame()

    result = pd.DataFrame(index=source.index)
    result["issn_normalizado"] = source[issn_col].apply(limpiar_issn)
    result["apc_monto"] = pd.to_numeric(
        source[amount_col].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    currency_col = _find_column(list(source.columns), _COLUMN_ALIASES["apc_moneda"])
    result["apc_moneda"] = (
        source[currency_col].str.upper().str.strip()
        if currency_col
        else ("EUR" if amount_col.strip().lower() == "euro" else "USD")
    )
    result["apc_monto_usd"] = result.apply(
        lambda row: convertir_a_usd(row["apc_monto"], row["apc_moneda"]), axis=1
    )
    result["apc_tipo"] = "observado"

    for target in ("titulo", "editorial"):
        column = _find_column(list(source.columns), _COLUMN_ALIASES[target])
        if column:
            result[target] = source[column]

    result = result.dropna(subset=["issn_normalizado", "apc_monto"]) \
        .drop_duplicates("issn_normalizado") \
        .reset_index(drop=True)
    result["_fuente"] = "openapc"
    result["_fecha_captura"] = FECHA_CAPTURA
    result["_estado_calidad"] = "normalizado"
    result["_hash_registro"] = result.apply(hash_registro, axis=1)
    result.to_parquet(OPENAPC_SILVER, index=False, engine="pyarrow")
    logger.info("OpenAPC: %d registros normalizados", len(result))
    return result


def main() -> None:
    procesar_openapc()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    main()
