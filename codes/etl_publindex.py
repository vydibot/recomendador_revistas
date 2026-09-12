"""
ETL Publindex — Revistas Indexadas, Índice Nacional Publindex.

Lee el CSV bronce de Publindex, normaliza campos clave (ISSN, título, país,
año de clasificación), deduplica por ISSN canónico y escribe un parquet
limpio en la capa silver.
"""

import logging
import sys

import pandas as pd
import numpy as np

from config import (
    PUBLINDEX_FILE,
    PUBLINDEX_SILVER,
    FECHA_CAPTURA,
    CATEGORIAS_PUBLINDEX,
)
from normalize import (
    limpiar_issn,
    validar_issn_checksum,
    obtener_issn_canonico,
    normalizar_titulo,
    normalizar_pais,
    hash_registro,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Mapeo de columnas originales → nombres silver ────────────────────────────
_RENAME_MAP = {
    "TXT_ISSN_P": "issn_print",
    "TXT_ISSN_E": "issn_electronic",
    "TXT_ISSN_L": "issn_linking",
    "NME_REVISTA_IN": "titulo",
    "NRO_ANO": "anio_clasificacion",
    "ID_CLAS_REV": "categoria_publindex",
    "PAIS_REV_IN": "pais",
    "REG_REV_IN": "region",
    "DEP_REV_IN": "departamento",
    "MUN_REV_IN": "municipio",
    "COD_DANE_REV_IN": "codigo_dane",
    "NME_ESPECIALIDAD": "especialidad",
    "NME_AREA": "area_conocimiento",
    "NME_GRAN_AREA": "gran_area",
    "NME_INST_EDIT_1": "institucion_editora_1",
    "TIPO_INS_N1_E1": "tipo_institucion_1",
    "NME_INST_EDIT_2": "institucion_editora_2",
    "NME_INST_EDIT_3": "institucion_editora_3",
    "ID_REVISTA_P": "id_revista_publindex",
}

# Columnas que se mantienen del CSV (las que aparecen en _RENAME_MAP)
_COLS_TO_KEEP = list(_RENAME_MAP.values())


# ═════════════════════════════════════════════════════════════════════════════
# Funciones auxiliares
# ═════════════════════════════════════════════════════════════════════════════

def _limpiar_anio(valor) -> object:
    """Convierte valores como '2021.0', '2021', 2021.0, NaN → int o None."""
    if pd.isna(valor):
        return None
    try:
        return int(float(str(valor).strip()))
    except (ValueError, TypeError):
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline principal
# ═════════════════════════════════════════════════════════════════════════════

def procesar_publindex() -> pd.DataFrame:
    """
    Ejecuta el pipeline ETL completo para Publindex.

    Pasos:
        1. Lectura del CSV bronce con codificación UTF-8.
        2. Normalización de los 3 campos ISSN.
        3. Cálculo del ISSN canónico (issn_normalizado).
        4. Eliminación de registros sin ISSN válido.
        5. Normalización del título.
        6. Limpieza del año de clasificación.
        7. Normalización del país a código ISO.
        8. Renombrado de columnas a snake_case.
        9. Deduplicación por issn_normalizado (se conserva el año más reciente).
       10. Adición de columnas de metadatos y hash de registro.
       11. Escritura del parquet silver.

    Returns:
        pd.DataFrame: DataFrame limpio listo para la capa silver.
    """
    # ── 1. Lectura ───────────────────────────────────────────────────────────
    logger.info("Leyendo CSV bronce: %s", PUBLINDEX_FILE)
    df = pd.read_csv(
        PUBLINDEX_FILE,
        sep=",",
        encoding="utf-8",
        dtype=str,
        lineterminator=None,  # pandas maneja \r\n automáticamente
    )
    # Eliminar posibles \r residuales en los valores
    df = df.apply(lambda col: col.str.strip() if col.dtype == "object" else col)
    rows_in = len(df)
    logger.info("Filas leídas: %d | Columnas: %d", rows_in, len(df.columns))

    # ── 2. Normalización de ISSN ─────────────────────────────────────────────
    logger.info("Normalizando campos ISSN...")
    df["TXT_ISSN_P"] = df["TXT_ISSN_P"].apply(limpiar_issn)
    df["TXT_ISSN_E"] = df["TXT_ISSN_E"].apply(limpiar_issn)
    df["TXT_ISSN_L"] = df["TXT_ISSN_L"].apply(limpiar_issn)

    # Validación de checksum (solo para logging)
    for col in ["TXT_ISSN_P", "TXT_ISSN_E", "TXT_ISSN_L"]:
        no_nulos = df[col].dropna()
        invalidos = no_nulos.apply(lambda x: not validar_issn_checksum(x)).sum()
        if invalidos > 0:
            logger.warning(
                "  %s: %d ISSN con checksum inválido de %d no nulos",
                col, invalidos, len(no_nulos),
            )

    # ── 3. ISSN canónico ─────────────────────────────────────────────────────
    logger.info("Calculando ISSN canónico (prioridad: ISSN-L > print > electronic)...")
    df["issn_normalizado"] = df.apply(
        lambda r: obtener_issn_canonico(
            r["TXT_ISSN_P"], r["TXT_ISSN_E"], r["TXT_ISSN_L"]
        ),
        axis=1,
    )

    # ── 4. Eliminar filas sin ISSN válido ────────────────────────────────────
    sin_issn = df["issn_normalizado"].isna().sum()
    logger.info("Filas sin ISSN válido: %d (serán eliminadas)", sin_issn)
    df = df.dropna(subset=["issn_normalizado"]).copy()

    # ── 5. Título normalizado ────────────────────────────────────────────────
    logger.info("Normalizando títulos...")
    df["titulo_normalizado"] = df["NME_REVISTA_IN"].apply(normalizar_titulo)

    # ── 6. Año de clasificación ──────────────────────────────────────────────
    logger.info("Limpiando año de clasificación (NRO_ANO)...")
    df["NRO_ANO"] = df["NRO_ANO"].apply(_limpiar_anio)
    anio_nulos = df["NRO_ANO"].isna().sum()
    if anio_nulos > 0:
        logger.warning("  Años nulos tras limpieza: %d", anio_nulos)

    # ── 7. País ISO ──────────────────────────────────────────────────────────
    logger.info("Normalizando país a código ISO...")
    df["pais_iso"] = df["PAIS_REV_IN"].apply(normalizar_pais)

    # ── 8. Renombrar columnas ────────────────────────────────────────────────
    logger.info("Renombrando columnas a esquema silver...")
    df = df.rename(columns=_RENAME_MAP)

    # Conservar solo las columnas del esquema + las intermedias generadas
    cols_final = (
        _COLS_TO_KEEP
        + ["issn_normalizado", "titulo_normalizado", "pais_iso"]
    )
    # Filtrar columnas que realmente existen (por seguridad)
    cols_presentes = [c for c in cols_final if c in df.columns]
    df = df[cols_presentes].copy()

    # ── 9. Deduplicación ─────────────────────────────────────────────────────
    pre_dedup = len(df)
    logger.info("Deduplicando por issn_normalizado (conservar año más reciente)...")

    # Convertir año a numérico para ordenar; NaN irá al final
    df["_anio_sort"] = pd.to_numeric(df["anio_clasificacion"], errors="coerce")
    df = (
        df.sort_values("_anio_sort", ascending=False, na_position="last")
        .drop_duplicates(subset=["issn_normalizado"], keep="first")
        .drop(columns=["_anio_sort"])
        .reset_index(drop=True)
    )
    duplicados_removidos = pre_dedup - len(df)
    logger.info(
        "  Duplicados removidos: %d | Filas tras deduplicación: %d",
        duplicados_removidos, len(df),
    )

    # ── 10. Columnas de metadatos ────────────────────────────────────────────
    logger.info("Agregando metadatos de trazabilidad...")
    df["_fuente"] = "publindex"
    df["_fecha_captura"] = FECHA_CAPTURA
    df["_estado_calidad"] = "normalizado"

    # ── 11. Hash de registro ─────────────────────────────────────────────────
    logger.info("Calculando hash de registro...")
    df["_hash_registro"] = df.apply(hash_registro, axis=1)

    # ── 12. Escritura del parquet silver ──────────────────────────────────────
    logger.info("Escribiendo parquet silver: %s", PUBLINDEX_SILVER)
    df.to_parquet(PUBLINDEX_SILVER, index=False, engine="pyarrow")

    # ── 13. Resumen de calidad ───────────────────────────────────────────────
    rows_out = len(df)
    logger.info("═" * 60)
    logger.info("RESUMEN ETL PUBLINDEX")
    logger.info("═" * 60)
    logger.info("  Filas entrada       : %d", rows_in)
    logger.info("  Sin ISSN (eliminadas): %d", sin_issn)
    logger.info("  Duplicados removidos : %d", duplicados_removidos)
    logger.info("  Filas salida         : %d", rows_out)

    campos_clave = [
        "issn_normalizado", "titulo", "titulo_normalizado",
        "anio_clasificacion", "categoria_publindex", "pais_iso",
    ]
    for campo in campos_clave:
        if campo in df.columns:
            nulos = df[campo].isna().sum()
            pct = 100.0 * nulos / rows_out if rows_out else 0
            logger.info("  Nulos en %-25s: %5d (%5.1f%%)", campo, nulos, pct)

    categorias = df["categoria_publindex"].value_counts(dropna=False)
    logger.info("  Distribución de categorías:")
    for cat, count in categorias.items():
        logger.info("    %-5s: %d", cat if pd.notna(cat) else "NaN", count)

    logger.info("═" * 60)
    return df


# ═════════════════════════════════════════════════════════════════════════════
# Punto de entrada
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Punto de entrada del módulo ETL Publindex."""
    logger.info("Iniciando ETL Publindex...")
    try:
        df = procesar_publindex()
        logger.info("ETL Publindex completado exitosamente. Registros: %d", len(df))
    except FileNotFoundError:
        logger.error("Archivo bronce no encontrado: %s", PUBLINDEX_FILE)
        sys.exit(1)
    except Exception:
        logger.exception("Error inesperado en ETL Publindex")
        sys.exit(1)


if __name__ == "__main__":
    main()
