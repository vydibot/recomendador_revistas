"""
ETL Publindex — Revistas Indexadas, Índice Nacional Publindex (MinCiencias).

Lee el CSV bronce de Publindex (delimitador ',', codificación UTF-8),
normaliza campos clave (ISSN impreso, electrónico y linking), calcula el ISSN canónico,
normaliza títulos (minúsculas, sin diacríticos ni puntuación), país a código ISO,
trata la categoría como atributo ordinal (A1=4, A2=3, B=2, C=1),
deduplica por ISSN canónico conservando el año más reciente,
y persiste el dataset limpio con metadatos de trazabilidad en la capa silver.
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    CATEGORIAS_PUBLINDEX,
    FECHA_CAPTURA,
    PUBLINDEX_FILE,
    PUBLINDEX_SILVER,
    VERSION_PROCESO,
)
from normalize import (
    hash_registro,
    limpiar_issn,
    normalizar_pais,
    normalizar_titulo,
    obtener_issn_canonico,
    validar_issn_checksum,
)

logger = logging.getLogger("etl_publindex")

# Mapeo de columnas originales → nombres silver normalizados
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

_COLS_TO_KEEP = list(_RENAME_MAP.values())


def _limpiar_anio(valor) -> object:
    """Convierte valores como '2021.0', '2021', 2021.0, NaN -> int o None."""
    if pd.isna(valor):
        return None
    try:
        return int(float(str(valor).strip()))
    except (ValueError, TypeError):
        return None


def procesar_publindex() -> pd.DataFrame:
    """
    Ejecuta el pipeline ETL completo para Publindex.

    Pasos:
        1. Lectura del CSV bronce con delimitador ',' y codificación UTF-8.
        2. Normalización y validación de los 3 campos ISSN.
        3. Cálculo del ISSN canónico (prioridad ISSN-L > print > electronic).
        4. Eliminación de registros sin ISSN identificable.
        5. Normalización del título para cruce secundario.
        6. Limpieza y tipado del año de clasificación.
        7. Normalización del país a código ISO.
        8. Codificación ordinal de categoría Publindex (A1=4, A2=3, B=2, C=1).
        9. Deduplicación por ISSN canónico (conservando el año más reciente).
       10. Adición de metadatos de trazabilidad (fuente, fecha de captura, versión de proceso, hash).
       11. Escritura a formato Parquet en la capa Silver.
    """
    logger.info("Leyendo CSV bronce de Publindex: %s", PUBLINDEX_FILE)
    if not PUBLINDEX_FILE.exists():
        raise FileNotFoundError(f"Archivo Publindex no encontrado: {PUBLINDEX_FILE}")

    df = pd.read_csv(
        PUBLINDEX_FILE,
        sep=",",
        encoding="utf-8",
        dtype=str,
        keep_default_na=True,
    )
    df = df.apply(lambda col: col.str.strip() if col.dtype == "object" else col)
    rows_in = len(df)
    logger.info("Filas leídas: %d | Columnas: %d", rows_in, len(df.columns))

    # 2. Normalización de ISSN
    logger.info("Normalizando campos ISSN...")
    df["TXT_ISSN_P"] = df["TXT_ISSN_P"].apply(limpiar_issn)
    df["TXT_ISSN_E"] = df["TXT_ISSN_E"].apply(limpiar_issn)
    df["TXT_ISSN_L"] = df["TXT_ISSN_L"].apply(limpiar_issn)

    # 3. ISSN canónico
    df["issn_normalizado"] = df.apply(
        lambda r: obtener_issn_canonico(r["TXT_ISSN_P"], r["TXT_ISSN_E"], r["TXT_ISSN_L"]),
        axis=1,
    )

    # 4. Filtrado de registros sin ISSN válido
    sin_issn = df["issn_normalizado"].isna().sum()
    if sin_issn > 0:
        logger.warning("Descartando %d registros sin ISSN válido en Publindex", sin_issn)
        df = df.dropna(subset=["issn_normalizado"]).copy()

    # 5. Normalización de título
    df["titulo_normalizado"] = df["NME_REVISTA_IN"].apply(normalizar_titulo)

    # 6. Limpieza del año
    df["NRO_ANO"] = df["NRO_ANO"].apply(_limpiar_anio)

    # 7. País ISO
    df["pais_iso"] = df["PAIS_REV_IN"].apply(normalizar_pais).fillna("CO")

    # 8. Renombrado
    df = df.rename(columns=_RENAME_MAP)

    # Codificación ordinal de categoría Publindex
    df["categoria_publindex_ord"] = (
        df["categoria_publindex"].map(CATEGORIAS_PUBLINDEX).fillna(0).astype(int)
    )

    cols_final = (
        _COLS_TO_KEEP
        + ["issn_normalizado", "titulo_normalizado", "pais_iso", "categoria_publindex_ord"]
    )
    cols_presentes = [c for c in cols_final if c in df.columns]
    df = df[cols_presentes].copy()

    # 9. Deduplicación por ISSN normalizado
    pre_dedup = len(df)
    df["_anio_sort"] = pd.to_numeric(df["anio_clasificacion"], errors="coerce")
    df = (
        df.sort_values("_anio_sort", ascending=False, na_position="last")
        .drop_duplicates(subset=["issn_normalizado"], keep="first")
        .drop(columns=["_anio_sort"])
        .reset_index(drop=True)
    )
    duplicados_removidos = pre_dedup - len(df)
    logger.info("Duplicados removidos: %d | Filas restantes: %d", duplicados_removidos, len(df))

    # 10. Metadatos de trazabilidad
    df["_fuente"] = "publindex"
    df["_fecha_captura"] = FECHA_CAPTURA
    df["_version_proceso"] = VERSION_PROCESO
    df["_estado_calidad"] = "normalizado"
    df["_hash_registro"] = df.apply(hash_registro, axis=1)

    # 11. Escritura Parquet Silver
    PUBLINDEX_SILVER.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PUBLINDEX_SILVER, index=False, engine="pyarrow")
    logger.info("Parquet Silver guardado: %s (%d registros)", PUBLINDEX_SILVER, len(df))

    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    procesar_publindex()


if __name__ == "__main__":
    main()
