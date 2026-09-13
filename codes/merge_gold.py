"""
Módulo Gold: Integración, Cruce Multifuente, Imputación y Matriz de Características.

Consolida los datos limpios de Publindex, Scimago JR, DOAJ y OpenAPC:
- Cruce primario por ISSN canónico normalizado.
- Cruce secundario por similitud de títulos normalizados (sin diacríticos, puntuación ni stopwords).
- Resolución de conflictos con precedencias explícitas.
- Transformación monetaria a USD y PPP USD para análisis de asequibilidad.
- Detección de cobros atípicos mediante umbral de 3 rangos intercuartílicos (3 * IQR).
- Imputación condicional de APC vía regresión multivariable con fallback a estrato cuartil-disciplina.
- Generación de variables binarias (exención LMIC, acceso diamante, revisión abierta, indexada DOAJ).
- Codificación ordinal y análisis de contraste/brecha Publindex vs Scimago.
- Estandarización de atributos continuos (Z-Score para PCA/distancias y Min-Max para visualización/scoring).
- Generación de matrices con One-Hot Encoding para modelos.
- Trazabilidad con fuentes combinadas, fecha de consolidación y versión de proceso.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz
    from rapidfuzz import process as rapidfuzz_process
except ImportError:
    rapidfuzz_fuzz = None
    rapidfuzz_process = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    CATALOGO_GOLD,
    CATALOGO_GOLD_CSV,
    CATEGORIAS_PUBLINDEX,
    CUARTIL_ORD,
    DOAJ_SILVER,
    FACTS_SILVER,
    FECHA_CAPTURA,
    FEATURES_GOLD,
    FUZZY_THRESHOLD,
    GOLD_DIR,
    MERGE_LOG,
    OPENAPC_SILVER,
    PUBLINDEX_SILVER,
    SCIMAGO_SILVER,
    VERSION_PROCESO,
)
from normalize import (
    calcular_concentracion_mercado,
    calcular_variables_binarias,
    codificar_one_hot,
    codificar_ordinal_y_contraste,
    convertir_a_ppp_usd,
    detectar_outliers_apc,
    escalar_minmax,
    estandarizar_zscore,
    hash_registro,
    imputar_apc,
    normalizar_titulo,
    similitud_titulos,
)

logger = logging.getLogger("merge_gold")


def cargar_silver() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carga los DataFrames Silver de las fuentes disponibles."""
    dfs = {}
    for nombre, ruta in [
        ("publindex", PUBLINDEX_SILVER),
        ("scimago", SCIMAGO_SILVER),
        ("doaj", DOAJ_SILVER),
        ("facts", FACTS_SILVER),
        ("openapc", OPENAPC_SILVER),
    ]:
        if ruta.exists():
            df = pd.read_parquet(ruta)
            logger.info("  %s: %d registros cargados desde %s", nombre, len(df), ruta.name)
            dfs[nombre] = df
        else:
            logger.warning("  %s: archivo no encontrado en %s", nombre, ruta)
            dfs[nombre] = pd.DataFrame()

    return dfs["publindex"], dfs["scimago"], dfs["doaj"], dfs["facts"], dfs["openapc"]


def cruce_multietapa(
    base: pd.DataFrame,
    derecha: pd.DataFrame,
    nombre_derecha: str,
    merge_log: list[dict],
    umbral_similitud: float = FUZZY_THRESHOLD,
) -> pd.DataFrame:
    """
    Realiza el cruce de 'base' con 'derecha' en dos etapas:
    1. Cruce primario: coincidencia exacta por issn_normalizado.
    2. Cruce secundario: para registros no coincidentes, comparación por titulo_normalizado
       (sin puntuación ni diacríticos) con umbral de similitud.
    Registra cada coincidencia y no coincidencia en merge_log.
    """
    if derecha.empty or "issn_normalizado" not in derecha.columns:
        logger.warning("  %s: DataFrame vacío o sin issn_normalizado", nombre_derecha)
        return base

    # Preparar columnas de derecha con sufijo
    cols_comunes = set(base.columns) & set(derecha.columns) - {"issn_normalizado", "titulo_normalizado"}
    derecha_prep = derecha.copy()
    derecha_prep = derecha_prep.rename(
        columns={c: f"{c}_{nombre_derecha}" for c in cols_comunes if c != "_fuente"}
    )
    if "_fuente" in derecha_prep.columns:
        derecha_prep = derecha_prep.rename(columns={"_fuente": f"_fuente_{nombre_derecha}"})

    # 1. Cruce Primario por ISSN
    merged = base.merge(
        derecha_prep,
        on="issn_normalizado",
        how="left",
        suffixes=("", f"_{nombre_derecha}_dup"),
    )

    issns_base = set(base["issn_normalizado"].dropna())
    issns_derecha = set(derecha["issn_normalizado"].dropna())
    coincidencias_issn = issns_base & issns_derecha
    logger.info("  Cruce con %s: %d coincidencias por ISSN primario", nombre_derecha, len(coincidencias_issn))

    for issn in coincidencias_issn:
        merge_log.append({
            "issn": issn,
            "fuente": nombre_derecha,
            "tipo_cruce": "issn_primario",
            "resultado": "coincidencia",
            "similitud": 100.0,
        })

    # 2. Cruce Secundario por Título Normalizado para registros sin match
    col_fuente_flag = f"_fuente_{nombre_derecha}"
    if col_fuente_flag in merged.columns and "titulo_normalizado" in base.columns and "titulo_normalizado" in derecha.columns:
        sin_match_mask = merged[col_fuente_flag].isna() & merged["titulo_normalizado"].notna()
        indices_sin_match = merged[sin_match_mask].index

        # Construir índice de títulos de derecha que no hicieron match por ISSN
        derecha_disponible = derecha_prep[~derecha_prep["issn_normalizado"].isin(coincidencias_issn)].copy()
        titulos_derecha = derecha_disponible.dropna(subset=["titulo_normalizado"]).set_index("titulo_normalizado")
        titulos_candidatos = list(titulos_derecha.index)

        cruce_secundario_count = 0
        for idx in indices_sin_match:
            tit_base = merged.loc[idx, "titulo_normalizado"]
            if not tit_base or pd.isna(tit_base):
                continue

            # Buscar coincidencia exacta de título normalizado
            if tit_base in titulos_derecha.index:
                fila_match = titulos_derecha.loc[tit_base]
                if isinstance(fila_match, pd.DataFrame):
                    fila_match = fila_match.iloc[0]
                for c in derecha_prep.columns:
                    if c in merged.columns and c not in {"issn_normalizado", "titulo_normalizado"}:
                        merged.loc[idx, c] = fila_match[c]
                cruce_secundario_count += 1
                merge_log.append({
                    "issn": merged.loc[idx, "issn_normalizado"],
                    "fuente": nombre_derecha,
                    "tipo_cruce": "titulo_secundario_exacto",
                    "resultado": "coincidencia",
                    "similitud": 100.0,
                })
            elif umbral_similitud < 100:
                # Fuzzy matching sobre títulos disponibles
                mejor_fila = None
                if rapidfuzz_process is not None and rapidfuzz_fuzz is not None:
                    mejor_match = rapidfuzz_process.extractOne(
                        str(tit_base),
                        titulos_candidatos,
                        scorer=rapidfuzz_fuzz.WRatio,
                        score_cutoff=umbral_similitud,
                    )
                    mejor_sim = mejor_match[1] if mejor_match else 0.0
                    if mejor_match:
                        fila_match = titulos_derecha.loc[mejor_match[0]]
                        mejor_fila = fila_match.iloc[0] if isinstance(fila_match, pd.DataFrame) else fila_match
                else:
                    mejor_sim = 0.0
                    for tit_der, row_der in titulos_derecha.iterrows():
                        sim = similitud_titulos(tit_base, str(tit_der))
                        if sim > mejor_sim:
                            mejor_sim = sim
                            mejor_fila = row_der
                if mejor_sim >= umbral_similitud and mejor_fila is not None:
                    for c in derecha_prep.columns:
                        if c in merged.columns and c not in {"issn_normalizado", "titulo_normalizado"}:
                            merged.loc[idx, c] = mejor_fila[c]
                    cruce_secundario_count += 1
                    merge_log.append({
                        "issn": merged.loc[idx, "issn_normalizado"],
                        "fuente": nombre_derecha,
                        "tipo_cruce": "titulo_secundario_fuzzy",
                        "resultado": "coincidencia",
                        "similitud": mejor_sim,
                    })

        logger.info("  Cruce secundario por título con %s: %d matches adicionales", nombre_derecha, cruce_secundario_count)

    return merged


def resolver_conflictos_y_precedencias(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resuelve conflictos entre columnas de múltiples fuentes respetando las reglas de precedencia:
    - OpenAPC tiene precedencia absoluta para APC observado (reemplaza declarado).
    - Publindex tiene precedencia para nombres y categorías nacionales.
    - Scimago tiene precedencia para métricas bibliométricas internacionales (SJR, H-index, cuartil).
    - DOAJ complementa con licencias, modelo de acceso, políticas de exención y revisión.
    """
    df = df.copy()

    # 1. Integración prioritaria de OpenAPC (pagos observados)
    apc_cols_openapc = [
        ("apc_monto_usd", "apc_monto_usd_openapc"),
        ("apc_monto_original", "apc_monto_original_openapc"),
        ("apc_moneda_original", "apc_moneda_original_openapc"),
        ("tasa_usd_utilizada", "tasa_usd_utilizada_openapc"),
        ("apc_monto_ppp_usd", "apc_monto_ppp_usd_openapc"),
        ("apc_tipo", "apc_tipo_openapc"),
        ("is_hybrid", "is_hybrid_openapc"),
    ]
    for col_base, col_alt in apc_cols_openapc:
        if col_alt in df.columns:
            if col_base not in df.columns:
                df[col_base] = df[col_alt]
            else:
                mask = df[col_alt].notna()
                df.loc[mask, col_base] = df.loc[mask, col_alt]
            df = df.drop(columns=[col_alt])

    # 2. Resolución para Scimago y DOAJ
    sufijos = ["_scimago", "_doaj", "_facts", "_openapc"]
    for sufijo in sufijos:
        cols_sufijo = [c for c in df.columns if c.endswith(sufijo) and not c.startswith("_fuente")]
        for col in cols_sufijo:
            base_col = col[:-len(sufijo)]
            if base_col in df.columns:
                mask = df[base_col].isna() & df[col].notna()
                df.loc[mask, base_col] = df.loc[mask, col]
                df = df.drop(columns=[col])
            else:
                df = df.rename(columns={col: base_col})

    return df


def consolidar_fuentes_trazabilidad(df: pd.DataFrame) -> pd.DataFrame:
    """
    Consolida la lista de fuentes que aportaron información a cada registro y asigna trazabilidad.
    """
    df = df.copy()
    fuentes_cols = [c for c in df.columns if c == "_fuente" or c.startswith("_fuente_")]

    def _combinar(row):
        fuentes = set()
        for c in fuentes_cols:
            val = row.get(c)
            if pd.notna(val) and val:
                if isinstance(val, (list, set)):
                    fuentes.update(val)
                else:
                    fuentes.add(str(val))
        return sorted(fuentes) if fuentes else ["publindex"]

    df["_fuentes"] = df.apply(_combinar, axis=1)
    df = df.drop(columns=[c for c in fuentes_cols if c != "_fuentes"], errors="ignore")

    df["_fecha_captura"] = FECHA_CAPTURA
    df["_version_proceso"] = VERSION_PROCESO
    df["_estado_calidad"] = "consolidado"

    return df


def calcular_features_avanzadas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ejecuta el pipeline completo de Feature Engineering (Sección 8.1.2):
    - Detección de outliers en APC (3 * IQR).
    - Imputación condicional de APC (regresión + estratos con flag apc_imputado).
    - Cálculo de PPP USD para todas las revistas con APC (incluyendo imputadas).
    - Cálculo de variables binarias (exención LMIC, diamante, revisión abierta, DOAJ).
    - Codificación ordinal y métrica de contraste/brecha Publindex vs Scimago.
    - Estandarización continua Z-Score (para PCA/distancias).
    - Escalamiento continuo Min-Max en [0, 1] (para visualización/scoring).
    - Índices derivados (ratio citas/doc, índice calidad-costo).
    """
    df = df.copy()

    # 1. Concentración de mercado editorial
    df["concentracion_editorial"] = calcular_concentracion_mercado(df, "editorial")

    # 2. Detección de outliers en APC (3 * IQR)
    df["apc_es_outlier"] = detectar_outliers_apc(
        df,
        columna_apc="apc_monto_usd",
        iqr_factor=3.0,
        grupo_cols=["gran_area"] if "gran_area" in df.columns else None,
    )
    logger.info("Outliers detectados en APC (3*IQR): %d", df["apc_es_outlier"].sum())

    # 3. Imputación condicional de APC
    df = imputar_apc(
        df,
        col_apc="apc_monto_usd",
        col_editorial="editorial",
        col_area="gran_area",
        col_cuartil="cuartil_sjr",
        col_hibrido="is_hybrid",
    )

    # 4. Asegurar cálculo de PPP USD tras imputación
    df["apc_monto_ppp_usd"] = df.apply(
        lambda r: convertir_a_ppp_usd(r.get("apc_monto_usd"), r.get("pais_iso")),
        axis=1,
    )

    # 5. Variables binarias (LMIC waiver, diamond, open review, DOAJ, colombiana)
    df = calcular_variables_binarias(df)

    # 6. Codificación ordinal y contraste Publindex vs Scimago
    df = codificar_ordinal_y_contraste(df)

    # 7. Tiempo editorial (semanas submission -> publicación)
    if "semanas_submission_publicacion" in df.columns:
        df["semanas_pub"] = pd.to_numeric(df["semanas_submission_publicacion"], errors="coerce")
        df["editorial_rapida"] = df["semanas_pub"] <= 12
    else:
        df["semanas_pub"] = np.nan
        df["editorial_rapida"] = False

    # 8. Ratio citas por documento
    if "total_citas_3y" in df.columns and "total_docs_3y" in df.columns:
        citas = pd.to_numeric(df["total_citas_3y"], errors="coerce")
        docs = pd.to_numeric(df["total_docs_3y"], errors="coerce").fillna(0)
        df["ratio_citas_docs"] = np.where(docs > 0, citas / docs, np.nan)
    elif "citas_por_doc_2y" in df.columns:
        df["ratio_citas_docs"] = pd.to_numeric(df["citas_por_doc_2y"], errors="coerce")
    else:
        df["ratio_citas_docs"] = np.nan

    # 9. Índice compuesto calidad-costo
    if "sjr_score" in df.columns and "apc_monto_usd" in df.columns:
        sjr = pd.to_numeric(df["sjr_score"], errors="coerce").fillna(0.1)
        apc = pd.to_numeric(df["apc_monto_usd"], errors="coerce").fillna(0.0)
        sjr_max = sjr.max() if sjr.max() > 0 else 1.0
        apc_max = apc.max() if apc.max() > 0 else 1.0
        sjr_n = sjr / sjr_max
        apc_n = apc / apc_max
        df["indice_calidad_costo"] = np.where(apc_n > 0, sjr_n / (0.1 + apc_n), sjr_n * 2.0)
        idx_max = df["indice_calidad_costo"].max()
        if pd.notna(idx_max) and idx_max > 0:
            df["indice_calidad_costo"] = (df["indice_calidad_costo"] / idx_max).round(4)

    # 10. Estandarización continua Z-Score (para PCA y distancias)
    cols_continuas = ["apc_monto_usd", "sjr_score", "h_index", "semanas_pub"]
    df = estandarizar_zscore(df, cols_continuas, sufijo="_zscore")

    # 11. Escalamiento continuo Min-Max [0, 1] (para visualización y scoring)
    df = escalar_minmax(df, cols_continuas, sufijo="_minmax")

    return df


def merge_gold() -> pd.DataFrame:
    """
    Pipeline principal de integración Medallion Gold.
    """
    logger.info("=" * 60)
    logger.info("INICIO: Consolidación Gold — Catálogo Maestro de Revistas")
    logger.info("=" * 60)

    # 1. Cargar Silver
    publindex, scimago, doaj, facts, openapc = cargar_silver()
    if publindex.empty:
        raise ValueError("Publindex Silver está vacío. No se puede generar el catálogo maestro.")

    merge_log = []
    base = publindex.copy()
    logger.info("Base inicial (Publindex): %d registros", len(base))

    # 2. Cruce con Scimago (métrica bibliométrica internacional)
    if not scimago.empty:
        base = cruce_multietapa(base, scimago, "scimago", merge_log)

    # 3. Cruce con DOAJ (políticas de acceso, APC declarado, licencias)
    if not doaj.empty:
        base = cruce_multietapa(base, doaj, "doaj", merge_log)

    # 4. Cruce con Facts (registro adicional de pagos observados)
    if not facts.empty:
        base = cruce_multietapa(base, facts, "facts", merge_log)

    # 5. Cruce con OpenAPC (pagos observados institucionales; precedencia máxima)
    if not openapc.empty:
        base = cruce_multietapa(base, openapc, "openapc", merge_log)

    # 5. Resolución de conflictos
    logger.info("Resolviendo conflictos y precedencias...")
    catalogo = resolver_conflictos_y_precedencias(base)

    # 6. Consolidación de fuentes y metadatos
    catalogo = consolidar_fuentes_trazabilidad(catalogo)

    # 7. Deduplicación por ISSN normalizado
    antes_dedup = len(catalogo)
    catalogo = catalogo.drop_duplicates(subset=["issn_normalizado"], keep="first").reset_index(drop=True)
    if antes_dedup != len(catalogo):
        logger.info("Duplicados eliminados en Gold: %d", antes_dedup - len(catalogo))

    # 8. Feature Engineering avanzado (Limpieza, Outliers, Imputación, Z-score, MinMax, Binarias)
    logger.info("Generando variables derivadas, imputación y transformaciones continuas...")
    catalogo = calcular_features_avanzadas(catalogo)

    # 9. Hash de registro final
    catalogo["_hash_registro"] = catalogo.apply(hash_registro, axis=1)

    # 10. Persistencia del Catálogo Maestro Gold
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    catalogo.to_parquet(CATALOGO_GOLD, index=False, engine="pyarrow")
    catalogo.to_csv(CATALOGO_GOLD_CSV, index=False, encoding="utf-8")
    logger.info("Catálogo Maestro Parquet guardado: %s (%d revistas)", CATALOGO_GOLD, len(catalogo))
    logger.info("Catálogo Maestro CSV guardado: %s", CATALOGO_GOLD_CSV)

    # 11. Generación y persistencia de Matriz de Características para Modelos (features_modelo.parquet)
    # Incluye One-Hot Encoding para país, disciplina y licencia
    logger.info("Generando matriz de características con One-Hot Encoding...")
    cols_modelo_base = [
        "issn_normalizado",
        "titulo",
        "pais_iso",
        "gran_area",
        "licencia",
        "categoria_publindex",
        "categoria_publindex_ord",
        "cuartil_sjr",
        "cuartil_sjr_ord",
        "brecha_publindex_sjr",
        "contraste_publindex_cuartil",
        "sjr_score",
        "sjr_score_zscore",
        "sjr_score_minmax",
        "h_index",
        "h_index_zscore",
        "h_index_minmax",
        "apc_monto_usd",
        "apc_monto_usd_zscore",
        "apc_monto_usd_minmax",
        "apc_monto_ppp_usd",
        "apc_tipo",
        "apc_imputado",
        "apc_metodo_imputacion",
        "apc_es_outlier",
        "oa_diamond",
        "exencion_apc_lmic",
        "revision_abierta",
        "indexada_doaj",
        "es_colombiana",
        "editorial_rapida",
        "ratio_citas_docs",
        "indice_calidad_costo",
        "concentracion_editorial",
    ]
    cols_existentes = [c for c in cols_modelo_base if c in catalogo.columns]
    features_df = catalogo[cols_existentes].copy()

    # Aplicar One-Hot Encoding sobre variables categóricas clave
    features_df = codificar_one_hot(features_df, columnas=["pais_iso", "gran_area", "licencia"])
    features_df.to_parquet(FEATURES_GOLD, index=False, engine="pyarrow")
    logger.info("Matriz de features del modelo guardada: %s (%d columnas)", FEATURES_GOLD, len(features_df.columns))

    # 12. Guardar Log de Merge
    if merge_log:
        df_log = pd.DataFrame(merge_log)
        df_log.to_csv(MERGE_LOG, index=False, encoding="utf-8")
        logger.info("Log de cruces guardado en: %s (%d entradas)", MERGE_LOG, len(df_log))

    # 13. Resumen en consola
    logger.info("=" * 60)
    logger.info("RESUMEN CATÁLOGO MAESTRO GOLD")
    logger.info("=" * 60)
    logger.info("  Total de revistas consolidadas : %d", len(catalogo))
    logger.info("  Revistas con APC observado     : %d", (catalogo["apc_tipo"] == "observado").sum())
    logger.info("  Revistas con APC declarado     : %d", (catalogo["apc_tipo"] == "declarado").sum())
    logger.info("  Revistas con APC imputado      : %d", (catalogo["apc_imputado"] == True).sum())
    logger.info("  Revistas con Acceso Diamante   : %d", catalogo["oa_diamond"].sum())
    logger.info("  Revistas con Exención LMIC     : %d", catalogo["exencion_apc_lmic"].sum())
    logger.info("  Revistas con Revisión Abierta  : %d", catalogo["revision_abierta"].sum())
    logger.info("  Revistas indexadas en DOAJ     : %d", catalogo["indexada_doaj"].sum())
    logger.info("=" * 60)

    return catalogo


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    merge_gold()


if __name__ == "__main__":
    main()
