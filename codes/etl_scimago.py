"""
ETL Scimago JR — Procesamiento de datos de Scimago Journal & Country Rank.

Lee el CSV bronze de Scimago (delimitador ';', coma decimal para números),
normaliza campos, parsea categorías temáticas y cuartiles ordinales (Q1=4, Q2=3, Q3=2, Q4=1),
extrae H-index, SJR, país y editorial, deduplica por ISSN canónico
y persiste el dataset limpio con metadatos de trazabilidad en la capa silver.
"""

import logging
import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    CUARTIL_ORD,
    FECHA_CAPTURA,
    SCIMAGO_FILE,
    SCIMAGO_SILVER,
    VERSION_PROCESO,
)
from normalize import (
    hash_registro,
    limpiar_issn,
    normalizar_pais,
    normalizar_titulo,
    parsear_numero_es_en,
)

logger = logging.getLogger("etl_scimago")

_RE_CAT_QUARTILE = re.compile(r"(.+?)\s*\(([Qq][1-4])\)")


def _parsear_issns(campo_issn: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Divide campo ISSN de Scimago (pueden venir separados por ', ') y normaliza."""
    if pd.isna(campo_issn) or not str(campo_issn).strip():
        return None, None
    partes = [p.strip() for p in str(campo_issn).split(",")]
    normalizados = [limpiar_issn(p) for p in partes if limpiar_issn(p)]
    issn_print = normalizados[0] if len(normalizados) >= 1 else None
    issn_electronic = normalizados[1] if len(normalizados) >= 2 else None
    return issn_print, issn_electronic


def _parsear_categorias(campo_cat: Optional[str]) -> list[tuple[str, str]]:
    """Parsea categorías Scimago con cuartil: 'Law (Q1); Sociology (Q2)'."""
    if pd.isna(campo_cat) or not str(campo_cat).strip():
        return []
    resultados = []
    for entrada in str(campo_cat).split(";"):
        entrada = entrada.strip()
        match = _RE_CAT_QUARTILE.match(entrada)
        if match:
            categoria = match.group(1).strip()
            cuartil = match.group(2).upper()
            resultados.append((categoria, cuartil))
        elif entrada:
            resultados.append((entrada, None))
    return resultados


def _mejor_cuartil(categorias: list[tuple[str, str]]) -> Optional[str]:
    """Determina el mejor cuartil de la lista de categorías."""
    cuartiles = [q for _, q in categorias if q in CUARTIL_ORD]
    if not cuartiles:
        return None
    return max(cuartiles, key=lambda q: CUARTIL_ORD.get(q, 0))


def _parsear_areas(campo_areas: Optional[str]) -> list[str]:
    """Divide campo Areas por ';' y retorna lista de áreas temáticas."""
    if pd.isna(campo_areas) or not str(campo_areas).strip():
        return []
    return [a.strip() for a in str(campo_areas).split(";") if a.strip()]


def _bool_yes_no(valor: Optional[str]) -> Optional[bool]:
    """Convierte cadenas 'Yes'/'No' a booleano."""
    if pd.isna(valor):
        return None
    v = str(valor).strip().lower()
    if v == "yes":
        return True
    if v == "no":
        return False
    return None


def procesar_scimago() -> pd.DataFrame:
    """
    Pipeline completo de Scimago JR bronze -> silver.
    """
    logger.info("Leyendo CSV bronze de Scimago: %s", SCIMAGO_FILE)
    if not SCIMAGO_FILE.exists():
        raise FileNotFoundError(f"Archivo Scimago no encontrado: {SCIMAGO_FILE}")

    df = pd.read_csv(
        SCIMAGO_FILE,
        sep=";",
        encoding="utf-8",
        dtype=str,
        keep_default_na=True,
    )
    filas_entrada = len(df)
    logger.info("Filas leídas: %d | Columnas: %d", filas_entrada, len(df.columns))

    if "Publisher.1" in df.columns:
        df = df.drop(columns=["Publisher.1"])

    # Parsing de ISSNs
    issn_parsed = df["Issn"].apply(_parsear_issns)
    df["issn_print"] = issn_parsed.apply(lambda x: x[0])
    df["issn_electronic"] = issn_parsed.apply(lambda x: x[1])
    df["issn_normalizado"] = df["issn_print"].combine_first(df["issn_electronic"])

    # Normalización de títulos
    df["titulo_normalizado"] = df["Title"].apply(normalizar_titulo)

    # Campos numéricos con posible coma decimal
    columnas_decimal = {
        "SJR": "sjr_score",
        "Citations / Doc. (2years)": "citas_por_doc_2y",
        "Ref. / Doc.": "refs_por_doc",
        "%Female": "pct_female_raw",
    }
    for col_orig, col_nuevo in columnas_decimal.items():
        if col_orig in df.columns:
            df[col_nuevo] = df[col_orig].apply(parsear_numero_es_en)

    # Campos enteros
    columnas_enteras = {
        "Rank": "rank_scimago",
        "H index": "h_index",
        "Total Docs. (2025)": "total_docs",
        "Total Docs. (3years)": "total_docs_3y",
        "Total Refs.": "total_refs",
        "Total Citations (3years)": "total_citas_3y",
        "Citable Docs. (3years)": "docs_citables_3y",
        "Overton": "overton",
    }
    for col_orig, col_nuevo in columnas_enteras.items():
        if col_orig in df.columns:
            df[col_nuevo] = pd.to_numeric(df[col_orig].apply(parsear_numero_es_en), errors="coerce").astype("Int64")

    # Categorías y cuartiles
    df["categorias_parsed"] = df["Categories"].apply(_parsear_categorias)
    df["mejor_cuartil"] = df["categorias_parsed"].apply(_mejor_cuartil)
    df["cuartil_sjr"] = df["mejor_cuartil"].combine_first(
        df["SJR Best Quartile"].str.strip().str.upper() if "SJR Best Quartile" in df.columns else None
    )
    df["cuartil_sjr_ord"] = df["cuartil_sjr"].map(CUARTIL_ORD).fillna(0).astype(int)

    df["categorias_scimago"] = df["categorias_parsed"].apply(
        lambda cats: "; ".join(f"{c} ({q})" if q else c for c, q in cats) if cats else None
    )

    # Áreas temáticas
    df["areas_parsed"] = df["Areas"].apply(_parsear_areas)
    df["areas_scimago"] = df["areas_parsed"].apply(
        lambda areas: "; ".join(areas) if areas else None
    )

    # Booleanos
    df["open_access"] = df["Open Access"].apply(_bool_yes_no) if "Open Access" in df.columns else None
    df["oa_diamond"] = df["Open Access Diamond"].apply(_bool_yes_no) if "Open Access Diamond" in df.columns else None

    # %Female a proporción decimal
    if "pct_female_raw" in df.columns:
        df["pct_female"] = df["pct_female_raw"].apply(
            lambda x: x / 100.0 if pd.notna(x) and x > 1.0 else x
        )

    # País normalizado a código ISO
    df["pais_iso"] = df["Country"].apply(normalizar_pais)

    # Selección y renombrado de columnas
    columnas_finales = {
        "rank_scimago": "rank_scimago",
        "Sourceid": "sourceid",
        "Title": "titulo",
        "Type": "tipo_publicacion",
        "issn_print": "issn_print",
        "issn_electronic": "issn_electronic",
        "issn_normalizado": "issn_normalizado",
        "titulo_normalizado": "titulo_normalizado",
        "Publisher": "editorial",
        "open_access": "open_access",
        "oa_diamond": "oa_diamond",
        "sjr_score": "sjr_score",
        "cuartil_sjr": "cuartil_sjr",
        "cuartil_sjr_ord": "cuartil_sjr_ord",
        "h_index": "h_index",
        "total_docs": "total_docs",
        "total_docs_3y": "total_docs_3y",
        "total_refs": "total_refs",
        "total_citas_3y": "total_citas_3y",
        "docs_citables_3y": "docs_citables_3y",
        "citas_por_doc_2y": "citas_por_doc_2y",
        "refs_por_doc": "refs_por_doc",
        "pct_female": "pct_female",
        "overton": "overton",
        "pais_iso": "pais_iso",
        "Region": "region",
        "Coverage": "cobertura",
        "categorias_scimago": "categorias_scimago",
        "areas_scimago": "areas_scimago",
    }
    cols_presentes = [c for c in columnas_finales if c in df.columns]
    df_clean = df[cols_presentes].rename(columns=columnas_finales)

    # Deduplicación por ISSN normalizado
    df_clean = df_clean.dropna(subset=["issn_normalizado"]).drop_duplicates(
        subset=["issn_normalizado"], keep="first"
    ).reset_index(drop=True)

    # Metadatos de trazabilidad
    df_clean["_fuente"] = "scimago"
    df_clean["_fecha_captura"] = FECHA_CAPTURA
    df_clean["_version_proceso"] = VERSION_PROCESO
    df_clean["_estado_calidad"] = "normalizado"
    df_clean["_hash_registro"] = df_clean.apply(hash_registro, axis=1)

    # Persistencia en Silver
    SCIMAGO_SILVER.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(SCIMAGO_SILVER, index=False, engine="pyarrow")
    logger.info("Parquet Silver guardado: %s (%d filas)", SCIMAGO_SILVER, len(df_clean))

    return df_clean


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    procesar_scimago()


if __name__ == "__main__":
    main()
