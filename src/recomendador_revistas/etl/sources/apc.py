"""
ETL OpenAPC: Pagos observados de APC y cargos de publicación institucional.

Lee el CSV bronce de OpenAPC, valida el formato, normaliza los ISSNs y montos de APC,
convierte a USD preservando moneda y tasa original, calcula el valor equivalente en PPP USD,
extrae el modelo de publicación (híbrido vs gold) y persiste en la capa silver con trazabilidad.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ...config.settings import (
    FACTS_FILE,
    FACTS_SILVER,
    FECHA_CAPTURA,
    OPENAPC_FILE,
    OPENAPC_SILVER,
    VERSION_PROCESO,
)
from ...data.normalization import (
    convertir_a_ppp_usd,
    convertir_a_usd,
    hash_registro,
    limpiar_issn,
    normalizar_titulo,
    parsear_numero_es_en,
)

logger = logging.getLogger("etl_openapc")

_COLUMN_ALIASES = {
    "issn_normalizado": ("issn", "journal_issn", "journal issn", "ISSN", "issn_l", "issn_electronic", "issn_print"),
    "apc_monto": (
        "euro", "apc", "apc_amount", "amount", "fee", "journal_fee", "journal_fees",
        "amount_paid", "apc_amount_paid", "usd",
    ),
    "apc_moneda": ("currency", "apc_currency", "currency_code"),
    "titulo": (
        "journal_full_title", "journal_name", "journal title", "title", "journal",
    ),
    "editorial": ("publisher", "publisher_name"),
    "is_hybrid": ("is_hybrid", "hybrid", "journal_type"),
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


def _procesar_apc(path: Path, silver_path: Path, source_name: str) -> pd.DataFrame:
    """Normaliza una fuente de pagos APC y la guarda en Silver."""
    if not path.exists():
        logger.warning("%s no encontrado: %s", source_name, path)
        return pd.DataFrame()

    try:
        source = _read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        logger.warning("%s no utilizable: %s", source_name, exc)
        return pd.DataFrame()

    issn_col = _find_column(list(source.columns), _COLUMN_ALIASES["issn_normalizado"])
    amount_col = _find_column(list(source.columns), _COLUMN_ALIASES["apc_monto"])
    if not issn_col or not amount_col:
        logger.warning("%s no contiene columnas identificables de ISSN y APC", source_name)
        return pd.DataFrame()

    result = pd.DataFrame(index=source.index)
    result["issn_normalizado"] = source[issn_col].apply(limpiar_issn)
    result["apc_monto_original"] = source[amount_col].apply(parsear_numero_es_en)

    currency_col = _find_column(list(source.columns), _COLUMN_ALIASES["apc_moneda"])
    if currency_col:
        result["apc_moneda_original"] = source[currency_col].str.upper().str.strip()
    else:
        result["apc_moneda_original"] = "EUR" if "euro" in amount_col.lower() else "USD"

    usd_conv = result.apply(
        lambda r: convertir_a_usd(r["apc_monto_original"], r["apc_moneda_original"]),
        axis=1,
    )
    result["apc_monto_usd"] = usd_conv.apply(lambda x: x[0])
    result["tasa_usd_utilizada"] = usd_conv.apply(lambda x: x[1])

    # Transformación PPP USD
    result["apc_monto_ppp_usd"] = result["apc_monto_usd"].apply(
        lambda x: convertir_a_ppp_usd(x, "DEFAULT")
    )

    result["apc_monto"] = result["apc_monto_original"]
    result["apc_moneda"] = result["apc_moneda_original"]
    result["apc_tipo"] = "observado"

    # Título y editorial
    for target in ("titulo", "editorial"):
        col = _find_column(list(source.columns), _COLUMN_ALIASES[target])
        if col:
            result[target] = source[col]

    if "titulo" in result.columns:
        result["titulo_normalizado"] = result["titulo"].apply(normalizar_titulo)

    # Flag is_hybrid
    hybrid_col = _find_column(list(source.columns), _COLUMN_ALIASES["is_hybrid"])
    if hybrid_col:
        result["is_hybrid"] = source[hybrid_col].str.strip().str.upper().isin(["TRUE", "1", "YES"])
    else:
        result["is_hybrid"] = False

    # Deduplicación y filtrado
    result = (
        result.dropna(subset=["issn_normalizado", "apc_monto_usd"])
        .drop_duplicates("issn_normalizado", keep="first")
        .reset_index(drop=True)
    )

    # Metadatos de trazabilidad
    result["_fuente"] = source_name.lower()
    result["_fecha_captura"] = FECHA_CAPTURA
    result["_version_proceso"] = VERSION_PROCESO
    result["_estado_calidad"] = "normalizado"
    result["_hash_registro"] = result.apply(hash_registro, axis=1)

    silver_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(silver_path, index=False, engine="pyarrow")
    logger.info("%s Silver guardado: %s (%d registros)", source_name, silver_path, len(result))
    return result


def procesar_openapc() -> pd.DataFrame:
    """Lee, valida, normaliza OpenAPC y guarda el parquet Silver."""
    return _procesar_apc(OPENAPC_FILE, OPENAPC_SILVER, "openapc")


def procesar_facts() -> pd.DataFrame:
    """Lee, valida, normaliza facts.csv y guarda el parquet Silver."""
    return _procesar_apc(FACTS_FILE, FACTS_SILVER, "facts")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    procesar_openapc()


if __name__ == "__main__":
    main()
