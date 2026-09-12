"""
Módulo Gold: Integración y consolidación del catálogo maestro de revistas.

Une los datos limpios de Publindex, DOAJ y Scimago en un único catálogo
consolidado con resolución de conflictos, feature engineering y
representaciones temáticas.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    PUBLINDEX_SILVER,
    DOAJ_SILVER,
    SCIMAGO_SILVER,
    OPENAPC_SILVER,
    CATALOGO_GOLD,
    FEATURES_GOLD,
    GOLD_DIR,
    MERGE_LOG,
    FECHA_CAPTURA,
    CUARTIL_ORD,
    CATEGORIAS_PUBLINDEX,
)
from normalize import (
    imputar_apc,
    detectar_outliers_apc,
    normalizar_titulo,
    similitud_titulos,
    hash_registro,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("merge_gold")

# Umbral de similitud para fuzzy matching de títulos
FUZZY_THRESHOLD = 85


def cargar_silver() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carga los cuatro archivos silver; OpenAPC puede estar ausente."""
    dfs = {}
    for nombre, ruta in [
        ("publindex", PUBLINDEX_SILVER),
        ("doaj", DOAJ_SILVER),
        ("scimago", SCIMAGO_SILVER),
        ("openapc", OPENAPC_SILVER),
    ]:
        if ruta.exists():
            df = pd.read_parquet(ruta)
            logger.info(f"  {nombre}: {len(df)} registros cargados")
            dfs[nombre] = df
        else:
            logger.warning(f"  {nombre}: archivo no encontrado en {ruta}")
            dfs[nombre] = pd.DataFrame()

    return dfs["publindex"], dfs["doaj"], dfs["scimago"], dfs["openapc"]


def merge_por_issn(
    base: pd.DataFrame,
    derecha: pd.DataFrame,
    nombre_derecha: str,
    merge_log: list[dict],
) -> pd.DataFrame:
    """
    Realiza un left join de base con derecha por issn_normalizado.
    Registra las coincidencias y no coincidencias en merge_log.
    """
    if derecha.empty or "issn_normalizado" not in derecha.columns:
        logger.warning(f"  {nombre_derecha}: DataFrame vacío o sin issn_normalizado")
        return base

    # Las columnas comunes se conservan en la base, excepto APC observado,
    # que debe poder reemplazar el valor declarado de DOAJ.
    cols_comunes = set(base.columns) & set(derecha.columns) - {"issn_normalizado"}
    columnas_override = {
        "apc_monto", "apc_moneda", "apc_monto_usd", "apc_tipo",
    } if nombre_derecha == "openapc" else set()
    columnas_fuente = {"_fuente"} if "_fuente" in derecha.columns else set()
    conservar = columnas_override | columnas_fuente
    derecha_renombrada = derecha.drop(
        columns=[c for c in cols_comunes if c not in conservar], errors="ignore"
    ).copy()
    derecha_renombrada = derecha_renombrada.rename(
        columns={
            **{c: f"{c}_{nombre_derecha}" for c in columnas_override if c in derecha_renombrada},
            "_fuente": f"_fuente_{nombre_derecha}",
        }
    )

    # ISSNs en derecha
    issns_derecha = set(derecha["issn_normalizado"].dropna().unique())
    issns_base = set(base["issn_normalizado"].dropna().unique())

    coincidencias = issns_base & issns_derecha
    solo_derecha = issns_derecha - issns_base
    solo_base = issns_base - issns_derecha

    logger.info(f"  Merge con {nombre_derecha}:")
    logger.info(f"    Coincidencias por ISSN: {len(coincidencias)}")
    logger.info(f"    Solo en base: {len(solo_base)}")
    logger.info(f"    Solo en {nombre_derecha}: {len(solo_derecha)}")

    # Registrar en log
    for issn in coincidencias:
        merge_log.append({
            "issn": issn,
            "fuente": nombre_derecha,
            "tipo_match": "issn_exacto",
            "resultado": "coincidencia",
        })

    for issn in solo_derecha:
        merge_log.append({
            "issn": issn,
            "fuente": nombre_derecha,
            "tipo_match": "issn_exacto",
            "resultado": "sin_coincidencia_en_base",
        })

    # Left join
    resultado = base.merge(
        derecha_renombrada,
        on="issn_normalizado",
        how="left",
        suffixes=("", f"_{nombre_derecha}"),
    )

    return resultado


def resolver_conflictos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resuelve conflictos entre columnas duplicadas (con sufijos _doaj, _scimago).
    Prioridad: publindex > scimago > doaj.
    """
    df = df.copy()

    # Patrones de resolución: (columna_base, columna_alternativa)
    resoluciones = []
    for col in df.columns:
        if col.endswith("_doaj") or col.endswith("_scimago"):
            base_col = col.rsplit("_", 1)[0]
            if base_col in df.columns:
                resoluciones.append((base_col, col))

    for base_col, alt_col in resoluciones:
        # Llenar nulos de la columna base con la alternativa
        mask = df[base_col].isna() & df[alt_col].notna()
        df.loc[mask, base_col] = df.loc[mask, alt_col]
        df = df.drop(columns=[alt_col])

    # OpenAPC contiene pagos observados y por ello tiene precedencia sobre
    # montos declarados, incluso cuando ya existe un valor en la base.
    for col in ("apc_monto", "apc_moneda", "apc_monto_usd", "apc_tipo"):
        alt_col = f"{col}_openapc"
        if alt_col in df.columns:
            if col not in df.columns:
                df[col] = df[alt_col]
            else:
                mask = df[alt_col].notna()
                df.loc[mask, col] = df.loc[mask, alt_col]
            df = df.drop(columns=[alt_col])

    return df


def consolidar_fuentes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea la lista de fuentes que contribuyeron a cada registro.
    """
    df = df.copy()

    # Detectar qué fuentes contribuyeron
    fuentes_cols = [c for c in df.columns if c == "_fuente" or c.startswith("_fuente_")]
    if fuentes_cols:
        # Combinar todas las fuentes en una lista
        def combinar_fuentes(row):
            fuentes = set()
            for col in fuentes_cols:
                val = row.get(col)
                if pd.notna(val):
                    if isinstance(val, list):
                        fuentes.update(val)
                    else:
                        fuentes.add(str(val))
            return sorted(fuentes) if fuentes else ["desconocida"]

        df["_fuentes"] = df.apply(combinar_fuentes, axis=1)
        # Limpiar columnas de fuente individuales
        df = df.drop(columns=[c for c in fuentes_cols if c != "_fuentes"], errors="ignore")
    else:
        df["_fuentes"] = [["publindex"]] * len(df)

    return df


def generar_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Genera variables derivadas para el sistema de recomendación:
    - Codificación ordinal de cuartiles y categorías
    - Ratio citas/documentos
    - Índice compuesto calidad-costo
    - Flags binarios
    """
    df = df.copy()

    # Codificación ordinal de cuartil SJR
    if "cuartil_sjr" in df.columns:
        df["cuartil_sjr_ord"] = df["cuartil_sjr"].map(CUARTIL_ORD).fillna(0).astype(int)

    # Codificación ordinal de categoría Publindex
    if "categoria_publindex" in df.columns:
        df["categoria_publindex_ord"] = (
            df["categoria_publindex"].map(CATEGORIAS_PUBLINDEX).fillna(0).astype(int)
        )

    # Ratio citas por documento (ya puede existir de Scimago)
    if "total_citas_3y" in df.columns and "total_docs_3y" in df.columns:
        df["ratio_citas_docs"] = np.where(
            df["total_docs_3y"] > 0,
            df["total_citas_3y"] / df["total_docs_3y"],
            np.nan,
        )

    # Flag de acceso diamante
    if "oa_diamond" not in df.columns:
        # Diamante = OA sin APC
        tiene_apc = df.get("tiene_apc", pd.Series(dtype=bool))
        oa = df.get("open_access", pd.Series(dtype=bool))
        df["oa_diamond"] = oa.fillna(False) & ~tiene_apc.fillna(True)

    # Índice compuesto calidad-costo (normalizado 0-1)
    # Mayor = mejor relación calidad/precio
    if "sjr_score" in df.columns and "apc_monto_usd" in df.columns:
        sjr_norm = df["sjr_score"] / df["sjr_score"].max() if df["sjr_score"].max() > 0 else 0
        apc_norm = df["apc_monto_usd"] / df["apc_monto_usd"].max() if df["apc_monto_usd"].max() > 0 else 0
        # Calidad alta + costo bajo = índice alto
        df["indice_calidad_costo"] = np.where(
            apc_norm > 0,
            sjr_norm / apc_norm,
            sjr_norm * 2,  # Sin APC = bonus
        )
        # Normalizar a 0-1
        max_idx = df["indice_calidad_costo"].replace([np.inf, -np.inf], np.nan).max()
        if pd.notna(max_idx) and max_idx > 0:
            df["indice_calidad_costo"] = (
                df["indice_calidad_costo"].replace([np.inf, -np.inf], np.nan) / max_idx
            )

    # Flag de revista colombiana
    if "pais_iso" in df.columns:
        df["es_colombiana"] = df["pais_iso"] == "CO"

    # Tiempo editorial binario (rápido <= 12 semanas)
    if "semanas_submission_publicacion" in df.columns:
        df["editorial_rapida"] = df["semanas_submission_publicacion"] <= 12

    return df


def merge_gold() -> pd.DataFrame:
    """
    Proceso principal de integración gold.

    1. Carga datos silver
    2. Merge por ISSN (left join desde Publindex)
    3. Resolución de conflictos
    4. Consolidación de fuentes
    5. Imputación de APC
    6. Detección de outliers
    7. Feature engineering
    8. Guardado
    """
    logger.info("=" * 60)
    logger.info("INICIO: Merge Gold — Catálogo maestro de revistas")
    logger.info("=" * 60)

    # 1. Cargar silver
    logger.info("\n1. Cargando datos silver...")
    publindex, doaj, scimago, openapc = cargar_silver()

    if publindex.empty:
        logger.error("Publindex vacío. No se puede generar el catálogo.")
        return pd.DataFrame()

    merge_log = []
    base = publindex.copy()
    logger.info(f"\n  Base inicial (Publindex): {len(base)} registros")

    # 2. Merge con Scimago (mayor precedencia bibliométrica)
    logger.info("\n2. Merge con Scimago...")
    if not scimago.empty:
        base = merge_por_issn(base, scimago, "scimago", merge_log)
        logger.info(f"  Registros tras merge Scimago: {len(base)}")

    # 3. Merge con DOAJ (información editorial y APC)
    logger.info("\n3. Merge con DOAJ...")
    if not doaj.empty:
        base = merge_por_issn(base, doaj, "doaj", merge_log)
        logger.info(f"  Registros tras merge DOAJ: {len(base)}")

    # OpenAPC tiene precedencia solo para el costo observado. Se integra al
    # final para que sus columnas de APC no desplacen el dato declarado DOAJ.
    logger.info("\n4. Merge con OpenAPC...")
    if not openapc.empty:
        base = merge_por_issn(base, openapc, "openapc", merge_log)
        logger.info(f"  Registros tras merge OpenAPC: {len(base)}")

    # 4. Resolver conflictos de columnas duplicadas
    logger.info("\n5. Resolviendo conflictos...")
    catalogo = resolver_conflictos(base)

    # 5. Consolidar fuentes
    logger.info("\n6. Consolidando fuentes...")
    catalogo = consolidar_fuentes(catalogo)

    # 6. Deduplicar por issn_normalizado (por si el merge generó duplicados)
    antes = len(catalogo)
    catalogo = catalogo.drop_duplicates(subset=["issn_normalizado"], keep="first")
    despues = len(catalogo)
    if antes != despues:
        logger.info(f"  Duplicados eliminados en gold: {antes - despues}")

    # 7. Imputación de APC
    logger.info("\n6. Imputación de APC...")
    if "apc_monto_usd" in catalogo.columns:
        nulos_antes = catalogo["apc_monto_usd"].isna().sum()
        catalogo = imputar_apc(catalogo)
        nulos_despues = catalogo["apc_monto_usd"].isna().sum()
        logger.info(f"  APC nulos antes: {nulos_antes}, después: {nulos_despues}")
        logger.info(f"  Valores imputados: {nulos_antes - nulos_despues}")

    # 8. Detección de outliers
    logger.info("\n7. Detección de outliers en APC...")
    if "apc_monto_usd" in catalogo.columns:
        grupo_cols = []
        if "gran_area" in catalogo.columns:
            grupo_cols.append("gran_area")
        if "cuartil_sjr" in catalogo.columns:
            grupo_cols.append("cuartil_sjr")

        catalogo["apc_es_outlier"] = detectar_outliers_apc(
            catalogo,
            columna_apc="apc_monto_usd",
            grupo_cols=grupo_cols if grupo_cols else None,
        )
        n_outliers = catalogo["apc_es_outlier"].sum()
        logger.info(f"  Outliers detectados: {n_outliers}")

    # 9. Feature engineering
    logger.info("\n8. Generando features...")
    catalogo = generar_features(catalogo)

    # 10. Metadatos finales
    catalogo["_estado_calidad"] = "consolidado"
    catalogo["_fecha_consolidacion"] = FECHA_CAPTURA

    # 11. Hash final
    cols_hash = [c for c in catalogo.columns if not c.startswith("_hash")]
    catalogo["_hash_registro"] = catalogo[cols_hash].apply(hash_registro, axis=1)

    # 12. Guardar
    logger.info("\n9. Guardando catálogo gold...")
    catalogo.to_parquet(CATALOGO_GOLD, index=False)
    logger.info(f"  Guardado: {CATALOGO_GOLD}")
    logger.info(f"  Registros finales: {len(catalogo)}")
    logger.info(f"  Columnas: {len(catalogo.columns)}")

    # También guardar como CSV para inspección fácil
    csv_path = GOLD_DIR / "catalogo_maestro_revistas.csv"
    catalogo.to_csv(csv_path, index=False)
    logger.info(f"  CSV de referencia: {csv_path}")

    # 13. Guardar features para el modelo
    feature_cols = [
        "issn_normalizado",
        "titulo",
        "gran_area",
        "area_conocimiento",
        "categoria_publindex",
        "categoria_publindex_ord",
        "cuartil_sjr",
        "cuartil_sjr_ord",
        "sjr_score",
        "h_index",
        "apc_monto_usd",
        "apc_tipo",
        "apc_es_outlier",
        "open_access",
        "oa_diamond",
        "licencia",
        "semanas_submission_publicacion",
        "ratio_citas_docs",
        "indice_calidad_costo",
        "es_colombiana",
        "editorial_rapida",
        "pais_iso",
    ]
    feature_cols = [c for c in feature_cols if c in catalogo.columns]
    features = catalogo[feature_cols].copy()
    features.to_parquet(FEATURES_GOLD, index=False)
    logger.info(f"  Features del modelo: {FEATURES_GOLD} ({len(feature_cols)} columnas)")

    # 14. Guardar log de merge
    if merge_log:
        df_log = pd.DataFrame(merge_log)
        df_log.to_csv(MERGE_LOG, index=False)
        logger.info(f"  Log de merge: {MERGE_LOG} ({len(df_log)} entradas)")

    # 15. Resumen final
    logger.info("\n" + "=" * 60)
    logger.info("RESUMEN DEL CATÁLOGO MAESTRO")
    logger.info("=" * 60)
    logger.info(f"  Total revistas: {len(catalogo)}")

    if "categoria_publindex" in catalogo.columns:
        logger.info(f"\n  Distribución por categoría Publindex:")
        for cat, count in catalogo["categoria_publindex"].value_counts().items():
            logger.info(f"    {cat}: {count}")

    if "cuartil_sjr" in catalogo.columns:
        logger.info(f"\n  Distribución por cuartil SJR:")
        for q, count in catalogo["cuartil_sjr"].value_counts().items():
            logger.info(f"    {q}: {count}")

    if "tiene_apc" in catalogo.columns:
        logger.info(f"\n  Revistas con APC: {catalogo['tiene_apc'].sum()}")

    if "apc_tipo" in catalogo.columns:
        logger.info(f"\n  Distribución tipo APC:")
        for tipo, count in catalogo["apc_tipo"].value_counts().items():
            logger.info(f"    {tipo}: {count}")

    fuentes_count = {}
    if "_fuentes" in catalogo.columns:
        for fuentes_list in catalogo["_fuentes"]:
            if isinstance(fuentes_list, list):
                for f in fuentes_list:
                    fuentes_count[f] = fuentes_count.get(f, 0) + 1
        logger.info(f"\n  Cobertura por fuente:")
        for f, c in sorted(fuentes_count.items()):
            logger.info(f"    {f}: {c} registros")

    logger.info("=" * 60)
    return catalogo


def main():
    """Punto de entrada del módulo de merge gold."""
    catalogo = merge_gold()
    if catalogo.empty:
        logger.error("No se generó el catálogo. Revise los archivos silver.")
        sys.exit(1)
    logger.info("Proceso Gold completado exitosamente.")


if __name__ == "__main__":
    main()
