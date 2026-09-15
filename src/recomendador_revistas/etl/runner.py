"""
Pipeline ETL principal — Recomendador de Revistas Científicas.

Orquesta la ejecución secuencial del pipeline Medallion:
  Bronze (datos crudos) → Silver (limpios/normalizados) → Gold (consolidados y features)

Uso:
    python pipeline.py              # Ejecutar todo el pipeline
    python pipeline.py silver       # Solo capa silver
    python pipeline.py gold         # Solo capa gold
    python pipeline.py validate     # Solo validación de bronze
"""

import hashlib
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..config.settings import (
    BRONZE_DIR,
    CATALOGO_GOLD,
    CATALOGO_GOLD_CSV,
    DOAJ_FILE,
    DOAJ_SILVER,
    FACTS_FILE,
    FEATURES_GOLD,
    GOLD_DIR,
    LOGS_DIR,
    MERGE_LOG,
    OPENAPC_FILE,
    OPENAPC_SILVER,
    PUBLINDEX_FILE,
    PUBLINDEX_SILVER,
    SCIMAGO_FILE,
    SCIMAGO_SILVER,
    SILVER_DIR,
    VERSION_PROCESO,
)

# ── Logging ──────────────────────────────────────────────────────────────
LOGS_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("pipeline")


def calcular_hash_archivo(ruta: Path) -> str:
    """Calcula el SHA-256 de un archivo."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validar_bronze() -> dict:
    """
    Valida los archivos de la capa bronze:
    - Existencia
    - Tamaño no vacío
    - Hash SHA-256
    - Parsing del header y delimitadores
    """
    logger.info("=" * 60)
    logger.info("VALIDACIÓN BRONZE")
    logger.info("=" * 60)

    archivos = {
        "publindex": PUBLINDEX_FILE,
        "scimago": SCIMAGO_FILE,
        "doaj": DOAJ_FILE,
        "openapc": OPENAPC_FILE,
        "facts": FACTS_FILE,
    }

    resultados = {}

    for nombre, ruta in archivos.items():
        info = {
            "archivo": str(ruta),
            "existe": ruta.exists(),
            "tamano_bytes": None,
            "hash_sha256": None,
            "header_valido": False,
            "num_columnas": None,
            "num_filas_aprox": None,
            "delimitador_detectado": None,
            "errores": [],
        }

        if not ruta.exists():
            info["errores"].append("Archivo no encontrado")
            logger.warning("  ✗ %s: archivo no encontrado (%s)", nombre, ruta)
            resultados[nombre] = info
            continue

        info["tamano_bytes"] = ruta.stat().st_size

        if info["tamano_bytes"] < 100:
            info["errores"].append(f"Archivo sospechosamente pequeño: {info['tamano_bytes']} bytes")
            logger.warning("  ⚠ %s: archivo muy pequeño (%d bytes)", nombre, info["tamano_bytes"])

        # Verificar que no sea HTML
        try:
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                primeras_lineas = f.read(500)
            if "<!DOCTYPE" in primeras_lineas or "<html" in primeras_lineas.lower():
                info["errores"].append("El archivo contiene HTML en lugar de datos CSV")
                info["header_valido"] = False
                logger.error("  ✗ %s: contiene HTML (posible error de descarga)", nombre)
                resultados[nombre] = info
                continue
        except Exception as e:
            info["errores"].append(f"Error al leer archivo: {e}")

        # Hash SHA-256
        try:
            info["hash_sha256"] = calcular_hash_archivo(ruta)
        except Exception as e:
            info["errores"].append(f"Error calculando hash: {e}")

        # Intentar parsear header
        try:
            sep = ";" if nombre == "scimago" else ","
            info["delimitador_detectado"] = sep
            if nombre == "doaj":
                contenido = ruta.read_text(encoding="utf-8", errors="replace")
                contenido = contenido.replace("\r\r\n", "\n").replace("\r\n", "\n")
                from io import StringIO
                df_test = pd.read_csv(StringIO(contenido), sep=sep, nrows=5)
            else:
                df_test = pd.read_csv(ruta, sep=sep, nrows=5)

            info["header_valido"] = True
            info["num_columnas"] = len(df_test.columns)

            with open(ruta, "rb") as f:
                info["num_filas_aprox"] = sum(1 for _ in f) - 1

            logger.info(
                "  ✓ %s: ~%d filas, %d columnas, sep='%s', %s bytes",
                nombre,
                info["num_filas_aprox"],
                info["num_columnas"],
                sep,
                f"{info['tamano_bytes']:,}",
            )
        except Exception as e:
            info["errores"].append(f"Error parseando CSV: {e}")
            logger.error("  ✗ %s: error de parseo — %s", nombre, e)

        resultados[nombre] = info

    registro_path = LOGS_DIR / "bronze_validation.json"
    with open(registro_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False, default=str)
    logger.info("  Registro de validación guardado en: %s", registro_path)

    return resultados


def ejecutar_silver() -> bool:
    """Ejecuta la capa silver: limpieza y normalización de cada fuente."""
    logger.info("\n" + "=" * 60)
    logger.info("CAPA SILVER — Limpieza y Normalización (Sección 8.1.1 & 8.1.2)")
    logger.info("=" * 60)

    exitos = 0
    errores = 0

    # 1. Publindex
    logger.info("\n── Procesando Publindex (MinCiencias) ──")
    try:
        from .sources.publindex import procesar_publindex
        df = procesar_publindex()
        if df is not None and not df.empty:
            logger.info("  ✓ Publindex: %d registros normalizados en Silver", len(df))
            exitos += 1
        else:
            logger.warning("  ⚠ Publindex: resultado vacío")
            errores += 1
    except Exception as e:
        logger.error("  ✗ Publindex error: %s", e, exc_info=True)
        errores += 1

    # 2. Scimago JR
    logger.info("\n── Procesando Scimago Journal & Country Rank ──")
    try:
        from .sources.scimago import procesar_scimago
        df = procesar_scimago()
        if df is not None and not df.empty:
            logger.info("  ✓ Scimago: %d registros normalizados en Silver", len(df))
            exitos += 1
        else:
            logger.warning("  ⚠ Scimago: resultado vacío")
            errores += 1
    except Exception as e:
        logger.error("  ✗ Scimago error: %s", e, exc_info=True)
        errores += 1

    # 3. DOAJ
    logger.info("\n── Procesando DOAJ (Directory of Open Access Journals) ──")
    try:
        from .sources.doaj import procesar_doaj
        df = procesar_doaj()
        if df is not None and not df.empty:
            logger.info("  ✓ DOAJ: %d registros normalizados en Silver", len(df))
            exitos += 1
        else:
            logger.warning("  ⚠ DOAJ: resultado vacío")
            errores += 1
    except Exception as e:
        logger.error("  ✗ DOAJ error: %s", e, exc_info=True)
        errores += 1

    # 4. OpenAPC
    logger.info("\n── Procesando OpenAPC (Pagos observados) ──")
    try:
        from .sources.apc import procesar_openapc
        df = procesar_openapc()
        if df is not None and not df.empty:
            logger.info("  ✓ OpenAPC: %d registros normalizados en Silver", len(df))
        else:
            logger.warning("  ⚠ OpenAPC: fuente no disponible o resultado vacío")
    except Exception as e:
        logger.warning("  ⚠ OpenAPC omitido: %s", e, exc_info=True)

    # 5. Facts (registro adicional de pagos APC)
    logger.info("\n── Procesando Facts (Registro adicional de APC) ──")
    try:
        from .sources.apc import procesar_facts
        df = procesar_facts()
        if df is not None and not df.empty:
            logger.info("  ✓ Facts: %d registros normalizados en Silver", len(df))
        else:
            logger.warning("  ⚠ Facts: fuente no disponible o resultado vacío")
    except Exception as e:
        logger.warning("  ⚠ Facts omitido: %s", e, exc_info=True)

    logger.info("\n  Silver completado: %d fuentes exitosas, %d errores", exitos, errores)
    return errores == 0


def ejecutar_gold() -> bool:
    """Ejecuta la capa gold: cruce multifuente, imputación y feature engineering."""
    logger.info("\n" + "=" * 60)
    logger.info("CAPA GOLD — Integración, Imputación y Matriz de Features")
    logger.info("=" * 60)

    try:
        from .gold import merge_gold
        catalogo = merge_gold()
        if catalogo is not None and not catalogo.empty:
            logger.info("  ✓ Gold completado con éxito: %d revistas en Catálogo Maestro", len(catalogo))
            return True
        else:
            logger.error("  ✗ Gold: catálogo resultante vacío")
            return False
    except Exception as e:
        logger.error("  ✗ Gold error: %s", e, exc_info=True)
        return False


def main():
    inicio = time.time()
    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║  PIPELINE ETL — Recomendador de Revistas Científicas    ║")
    logger.info("║  Versión: %-15s Fecha: %-25s ║", VERSION_PROCESO, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("╚══════════════════════════════════════════════════════════╝")

    etapas = sys.argv[1:] if len(sys.argv) > 1 else ["validate", "silver", "gold"]
    exito = True

    if "validate" in etapas:
        validar_bronze()

    if "silver" in etapas and exito:
        exito = ejecutar_silver()

    if "gold" in etapas and exito:
        exito = ejecutar_gold()

    duracion = time.time() - inicio
    logger.info("\n" + "=" * 60)
    logger.info("Duración total de ejecución: %.2f segundos", duracion)
    logger.info("Log del pipeline registrado en: %s", log_file)
    logger.info("=" * 60)

    if exito:
        logger.info("✓ Pipeline finalizado exitosamente.")
    else:
        logger.error("✗ Pipeline finalizado con errores.")
        sys.exit(1)


if __name__ == "__main__":
    main()
