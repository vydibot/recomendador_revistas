"""
ETL DOAJ — Procesamiento de la base de datos DOAJ (Directory of Open Access Journals).

Lee el CSV bronze de DOAJ, normaliza campos (ISSN, títulos, países, APC declarado),
conserva monto original, moneda original, tasa de cambio y valor transformado a PPP USD,
extrae licencias CC, modelo de acceso, tipo de revisión por pares y políticas de exención,
y genera un archivo parquet limpio en la capa silver con trazabilidad completa.
"""

import logging
from io import StringIO
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ...config.settings import (
    DOAJ_FILE,
    DOAJ_SILVER,
    FECHA_CAPTURA,
    MONEDAS_CONVERSION_REPORT,
    TASAS_USD,
    VERSION_PROCESO,
)
from ...data.normalization import (
    convertir_a_ppp_usd,
    convertir_a_usd,
    hash_registro,
    limpiar_issn,
    normalizar_pais,
    normalizar_titulo,
    obtener_issn_canonico,
    parsear_apc_doaj,
)

logger = logging.getLogger("etl_doaj")

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

YES_NO_FIELDS = [
    "politica_plagio",
    "autor_retiene_copyright",
    "tiene_otros_cobros",
    "politica_exencion",
    "subscribe_to_open",
    "cumple_oa_doaj",
    "cc_legible_maquina",
]


def _leer_csv_doaj(ruta: Path) -> pd.DataFrame:
    """Lee CSV DOAJ normalizando finales de línea redundantes."""
    logger.info("Leyendo archivo DOAJ: %s", ruta)
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        contenido = f.read()
    contenido = contenido.replace("\r\r\n", "\n").replace("\r\n", "\n")
    df = pd.read_csv(StringIO(contenido), sep=",", dtype=str)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()
    return df


def _yes_no_a_bool(serie: pd.Series) -> pd.Series:
    """Convierte 'Yes'/'No' a booleano nullable."""
    mapa = {"Yes": True, "No": False, "yes": True, "no": False, "TRUE": True, "FALSE": False}
    return serie.map(mapa).astype("boolean")


def procesar_doaj() -> pd.DataFrame:
    """Pipeline completo de DOAJ bronze -> silver."""
    if not DOAJ_FILE.exists():
        raise FileNotFoundError(f"Archivo DOAJ no encontrado: {DOAJ_FILE}")

    df = _leer_csv_doaj(DOAJ_FILE)
    filas_entrada = len(df)
    logger.info("DOAJ leído: %d filas x %d columnas", filas_entrada, len(df.columns))

    # Renombrar columnas
    cols_presentes = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    df = df.rename(columns=cols_presentes)

    # Normalización de ISSN
    df["issn_impreso"] = df["issn_impreso"].apply(limpiar_issn) if "issn_impreso" in df.columns else None
    df["issn_electronico"] = df["issn_electronico"].apply(limpiar_issn) if "issn_electronico" in df.columns else None
    df["issn_normalizado"] = df.apply(
        lambda r: obtener_issn_canonico(r.get("issn_impreso"), r.get("issn_electronico")),
        axis=1,
    )

    # Normalización de título
    df["titulo_normalizado"] = df["titulo"].apply(normalizar_titulo)

    # Normalización de país
    df["pais_iso"] = df["pais_editorial"].apply(normalizar_pais)

    # Booleanos
    df["tiene_apc"] = _yes_no_a_bool(df["tiene_apc"])
    for campo in YES_NO_FIELDS:
        if campo in df.columns and campo != "tiene_apc":
            df[campo] = _yes_no_a_bool(df[campo])

    # Parsing de APC declarado
    apc_parsed = df["apc_amount_raw"].apply(parsear_apc_doaj) if "apc_amount_raw" in df.columns else None
    if apc_parsed is not None:
        df["apc_monto_original"] = apc_parsed.apply(lambda x: x[0])
        df["apc_moneda_original"] = apc_parsed.apply(lambda x: x[1])
    else:
        df["apc_monto_original"] = None
        df["apc_moneda_original"] = None

    # Conversión a USD y tasa utilizada
    usd_conv = df.apply(
        lambda r: convertir_a_usd(r["apc_monto_original"], r["apc_moneda_original"]),
        axis=1,
    )
    df["apc_monto_usd"] = usd_conv.apply(lambda x: x[0])
    df["tasa_usd_utilizada"] = usd_conv.apply(lambda x: x[1])
    df["apc_conversion_estado"] = df.apply(
        lambda r: "convertida" if pd.notna(r["apc_monto_original"]) and pd.notna(r["apc_monto_usd"])
        else "sin_monto" if pd.isna(r["apc_monto_original"])
        else "sin_tasa",
        axis=1,
    )

    # Transformación por Paridad de Poder Adquisitivo (PPP USD)
    df["apc_monto_ppp_usd"] = df.apply(
        lambda r: convertir_a_ppp_usd(r["apc_monto_usd"], r["pais_iso"]),
        axis=1,
    )

    # Alias para compatibilidad
    df["apc_monto"] = df["apc_monto_original"]
    df["apc_moneda"] = df["apc_moneda_original"]
    df["apc_tipo"] = np.where(df["apc_monto_usd"].notna(), "declarado", None)

    # Semanas submission -> publicación
    if "semanas_submission_publicacion" in df.columns:
        df["semanas_submission_publicacion"] = pd.to_numeric(
            df["semanas_submission_publicacion"].astype(str).str.extract(r"(\d+)", expand=False),
            errors="coerce",
        ).astype("Int64")

    # Deduplicación por ISSN normalizado
    con_issn = df[df["issn_normalizado"].notna()].drop_duplicates(subset=["issn_normalizado"], keep="first")
    sin_issn = df[df["issn_normalizado"].isna()]
    df = pd.concat([con_issn, sin_issn], ignore_index=True)

    # Metadatos de trazabilidad
    df["_fuente"] = "doaj"
    df["_fecha_captura"] = FECHA_CAPTURA
    df["_version_proceso"] = VERSION_PROCESO
    df["_estado_calidad"] = "normalizado"
    df["_hash_registro"] = df.apply(hash_registro, axis=1)

    conversion_report = (
        df.loc[df["apc_moneda_original"].notna()]
        .groupby("apc_moneda_original", dropna=False)
        .agg(
            registros=("apc_moneda_original", "size"),
            registros_con_monto=("apc_monto_original", lambda s: s.notna().sum()),
            registros_convertidos=("apc_conversion_estado", lambda s: (s == "convertida").sum()),
            registros_sin_tasa=("apc_conversion_estado", lambda s: (s == "sin_tasa").sum()),
            tasa_usd=("tasa_usd_utilizada", "first"),
        )
        .reset_index()
        .rename(columns={"apc_moneda_original": "moneda"})
    )
    conversion_report["estado"] = np.where(
        conversion_report["moneda"].isin(TASAS_USD), "tasa_disponible", "tasa_pendiente"
    )
    MONEDAS_CONVERSION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    conversion_report.sort_values("moneda").to_csv(
        MONEDAS_CONVERSION_REPORT, index=False, encoding="utf-8"
    )
    logger.info("Tabla de conversión guardada: %s (%d monedas)", MONEDAS_CONVERSION_REPORT, len(conversion_report))

    # Persistencia
    DOAJ_SILVER.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DOAJ_SILVER, index=False, engine="pyarrow")
    logger.info("DOAJ Parquet Silver guardado: %s (%d registros)", DOAJ_SILVER, len(df))

    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    procesar_doaj()


if __name__ == "__main__":
    main()
