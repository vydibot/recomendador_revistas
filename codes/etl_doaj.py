"""
ETL DOAJ — Procesamiento de la base de datos DOAJ (Directory of Open Access Journals).

Lee el CSV bronze de DOAJ, normaliza campos (ISSN, títulos, países, APC),
convierte tipos, renombra columnas al esquema del catálogo y genera un
archivo parquet limpio en la capa silver.

Entrada:  data/bronze/doaj_journalcsv_20260812_2320_utf8.csv
Salida:   data/silver/doaj_clean.parquet
"""

import logging
import sys
from io import StringIO

import numpy as np
import pandas as pd

from config import DOAJ_FILE, DOAJ_SILVER, FECHA_CAPTURA
from normalize import (
    convertir_a_usd,
    hash_registro,
    limpiar_issn,
    normalizar_pais,
    normalizar_titulo,
    obtener_issn_canonico,
    parsear_apc_doaj,
)

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ── Mapeo de columnas originales → esquema catálogo (snake_case español) ──
RENAME_MAP = {
    "Journal title": "titulo",
    "Alternative title": "titulo_alternativo",
    "Journal ISSN (print version)": "issn_impreso",
    "Journal EISSN (online version)": "issn_electronico",
    "Keywords": "palabras_clave",
    "Languages in which the journal accepts manuscripts": "idiomas",
    "Publisher": "editorial",
    "Country of publisher": "pais_editorial",
    "Journal license": "licencia",
    "License attributes": "atributos_licencia",
    "Machine-readable CC licensing information embedded or displayed in articles": "cc_legible_maquina",
    "Author holds copyright without restrictions": "autor_retiene_copyright",
    "Review process": "tipo_revision",
    "Journal plagiarism screening policy": "politica_plagio",
    "Average number of weeks between article submission and publication": "semanas_submission_publicacion",
    "APC": "tiene_apc",
    "APC amount": "apc_amount_raw",
    "Journal waiver policy (for developing country authors etc)": "politica_exencion",
    "Has other fees": "tiene_otros_cobros",
    "Preservation Services": "servicios_preservacion",
    "Persistent article identifiers": "identificadores_persistentes",
    "Does the journal comply to DOAJ's definition of open access?": "cumple_oa_doaj",
    "LCC Codes": "codigos_lcc",
    "Subjects": "materias",
    "Subscribe to Open": "subscribe_to_open",
    "Added on Date": "fecha_incorporacion_doaj",
    "Last updated Date": "fecha_actualizacion_doaj",
    "Number of Article Records": "num_articulos",
    "Most Recent Article Added": "fecha_ultimo_articulo",
    "Journal URL": "url_revista",
    "URL in DOAJ": "url_doaj",
}

# Campos Yes/No que se convierten a booleano
YES_NO_FIELDS = [
    "politica_plagio",
    "autor_retiene_copyright",
    "tiene_otros_cobros",
    "politica_exencion",
    "subscribe_to_open",
    "cumple_oa_doaj",
    "cc_legible_maquina",
]


# ═══════════════════════════════════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════


def _leer_csv_doaj(ruta: str) -> pd.DataFrame:
    """
    Lee el CSV de DOAJ manejando los finales de línea ``\\r\\r\\n``.

    Lee el contenido completo del archivo, reemplaza ``\\r\\r\\n`` por ``\\n``
    y luego parsea con pandas.
    """
    logger.info("Leyendo archivo DOAJ: %s", ruta)

    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()

    # Normalizar finales de línea dobles (\r\r\n → \n)
    contenido = contenido.replace("\r\r\n", "\n").replace("\r\n", "\n")

    df = pd.read_csv(StringIO(contenido), sep=",", dtype=str)

    # Limpiar posibles \r residuales en la última columna
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()

    logger.info(
        "  CSV leído: %d filas × %d columnas",
        len(df),
        len(df.columns),
    )
    return df


def _yes_no_a_bool(serie: pd.Series) -> pd.Series:
    """Convierte una serie con valores 'Yes'/'No' a booleano nullable."""
    mapa = {"Yes": True, "No": False, "yes": True, "no": False}
    return serie.map(mapa).astype("boolean")


def _parsear_semanas(valor):
    """Convierte el campo de semanas a entero, retornando pd.NA si falla."""
    if pd.isna(valor) or not str(valor).strip():
        return pd.NA
    try:
        return int(float(str(valor).strip()))
    except (ValueError, TypeError):
        return pd.NA


def _parsear_lista(valor: str) -> list[str] | None:
    """Convierte un string separado por comas en una lista de strings limpios."""
    if pd.isna(valor) or not str(valor).strip():
        return None
    items = [item.strip() for item in str(valor).split(",") if item.strip()]
    return items if items else None


# ═══════════════════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL DE PROCESAMIENTO
# ═══════════════════════════════════════════════════════════════════════════


def procesar_doaj() -> pd.DataFrame:
    """
    Pipeline completo de procesamiento DOAJ bronze → silver.

    Retorna el DataFrame limpio y lo guarda como parquet.
    """
    # ── 1. Lectura ────────────────────────────────────────────────────────
    df = _leer_csv_doaj(str(DOAJ_FILE))
    filas_entrada = len(df)

    # ── 2. Renombrar columnas ─────────────────────────────────────────────
    cols_presentes = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    df = df.rename(columns=cols_presentes)
    logger.info("  Columnas renombradas: %d de %d mapeadas", len(cols_presentes), len(RENAME_MAP))

    # ── 3. Normalización de ISSN ──────────────────────────────────────────
    df["issn_impreso"] = df["issn_impreso"].apply(limpiar_issn)
    df["issn_electronico"] = df["issn_electronico"].apply(limpiar_issn)
    df["issn_normalizado"] = df.apply(
        lambda r: obtener_issn_canonico(r["issn_impreso"], r["issn_electronico"]),
        axis=1,
    )
    nulos_issn = df["issn_normalizado"].isna().sum()
    logger.info("  ISSN normalizados — nulos: %d (%.1f%%)", nulos_issn, 100 * nulos_issn / len(df))

    # ── 4. Normalización de título ────────────────────────────────────────
    df["titulo_normalizado"] = df["titulo"].apply(normalizar_titulo)
    nulos_titulo = df["titulo_normalizado"].isna().sum()
    logger.info("  Títulos normalizados — nulos: %d", nulos_titulo)

    # ── 5. Normalización de país ──────────────────────────────────────────
    df["pais_iso"] = df["pais_editorial"].apply(normalizar_pais)
    nulos_pais = df["pais_iso"].isna().sum()
    logger.info("  Países normalizados — nulos: %d", nulos_pais)

    # ── 6. Conversión de APC Yes/No → booleano ────────────────────────────
    df["tiene_apc"] = _yes_no_a_bool(df["tiene_apc"])

    # ── 7. Parseo de APC amount ───────────────────────────────────────────
    apc_parsed = df["apc_amount_raw"].apply(parsear_apc_doaj)
    df["apc_monto"] = apc_parsed.apply(lambda x: x[0])
    df["apc_moneda"] = apc_parsed.apply(lambda x: x[1])

    # ── 8. Conversión a USD ───────────────────────────────────────────────
    df["apc_monto_usd"] = df.apply(
        lambda r: convertir_a_usd(r["apc_monto"], r["apc_moneda"]),
        axis=1,
    )
    apc_validos = df["apc_monto_usd"].notna().sum()
    logger.info("  APC convertidos a USD: %d registros", apc_validos)

    # ── 9. Tipo de APC ────────────────────────────────────────────────────
    df["apc_tipo"] = np.where(df["apc_monto"].notna(), "declarado", None)

    # ── 10. Conversión de campos Yes/No a booleanos ───────────────────────
    for campo in YES_NO_FIELDS:
        if campo in df.columns and campo != "tiene_apc":
            df[campo] = _yes_no_a_bool(df[campo])
    logger.info("  Campos Yes/No convertidos a booleano: %s", YES_NO_FIELDS)

    # ── 11. Semanas submission → publicación ──────────────────────────────
    if "semanas_submission_publicacion" in df.columns:
        df["semanas_submission_publicacion"] = (
            df["semanas_submission_publicacion"]
            .apply(_parsear_semanas)
            .astype("Int64")
        )

    # ── 12. Parseo de fechas ──────────────────────────────────────────────
    for col_fecha in ["fecha_incorporacion_doaj", "fecha_actualizacion_doaj", "fecha_ultimo_articulo"]:
        if col_fecha in df.columns:
            df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce", utc=True)
            df[col_fecha] = df[col_fecha].dt.date
            nulos_fecha = df[col_fecha].isna().sum()
            logger.info("  Fecha '%s' parseada — nulos: %d", col_fecha, nulos_fecha)

    # ── 13. Parseo de listas (keywords, idiomas) ──────────────────────────
    df["palabras_clave"] = df["palabras_clave"].apply(_parsear_lista)
    df["idiomas"] = df["idiomas"].apply(_parsear_lista)

    # ── 14. Deduplicación por issn_normalizado ────────────────────────────
    filas_pre_dedup = len(df)
    # Mantener registros sin ISSN (no se pueden deduplicar por ISSN)
    con_issn = df[df["issn_normalizado"].notna()]
    sin_issn = df[df["issn_normalizado"].isna()]

    con_issn = con_issn.drop_duplicates(subset="issn_normalizado", keep="first")
    df = pd.concat([con_issn, sin_issn], ignore_index=True)
    duplicados = filas_pre_dedup - len(df)
    logger.info("  Deduplicación por ISSN: %d duplicados eliminados", duplicados)

    # ── 15. Columnas de trazabilidad ──────────────────────────────────────
    df["_fuente"] = "doaj"
    df["_fecha_captura"] = FECHA_CAPTURA
    df["_estado_calidad"] = "normalizado"
    df["_hash_registro"] = df.apply(hash_registro, axis=1)

    # Eliminar columna auxiliar de APC raw
    df = df.drop(columns=["apc_amount_raw"], errors="ignore")

    # ── 16. Guardado a parquet ────────────────────────────────────────────
    DOAJ_SILVER.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(DOAJ_SILVER), index=False, engine="pyarrow")
    logger.info("  Parquet guardado en: %s", DOAJ_SILVER)

    # ── 17. Resumen final ─────────────────────────────────────────────────
    filas_salida = len(df)
    logger.info("=" * 60)
    logger.info("  RESUMEN ETL DOAJ")
    logger.info("=" * 60)
    logger.info("  Filas entrada:       %d", filas_entrada)
    logger.info("  Filas salida:        %d", filas_salida)
    logger.info("  Duplicados removidos:%d", duplicados)
    logger.info("  ISSN nulos:          %d", df["issn_normalizado"].isna().sum())
    logger.info("  Títulos nulos:       %d", df["titulo_normalizado"].isna().sum())
    logger.info("  País ISO nulos:      %d", df["pais_iso"].isna().sum())
    logger.info("  APC en USD válidos:  %d", df["apc_monto_usd"].notna().sum())
    logger.info("  tiene_apc True:      %d", df["tiene_apc"].sum() if df["tiene_apc"].any() else 0)
    logger.info("  Columnas finales:    %s", list(df.columns))
    logger.info("=" * 60)

    return df


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════


def main():
    """Punto de entrada principal del ETL DOAJ."""
    logger.info("Iniciando ETL DOAJ...")
    try:
        df = procesar_doaj()
        logger.info("ETL DOAJ completado exitosamente — %d registros.", len(df))
    except Exception:
        logger.exception("Error fatal en ETL DOAJ")
        sys.exit(1)


if __name__ == "__main__":
    main()
