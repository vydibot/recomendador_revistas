"""
Pipeline ETL principal — Recomendador de Revistas Científicas.

Orquesta la ejecución secuencial del pipeline medallion:
  Bronze (datos crudos) → Silver (limpios/normalizados) → Gold (consolidados)

Uso:
    python pipeline.py              # Ejecutar todo el pipeline
    python pipeline.py silver       # Solo capa silver
    python pipeline.py gold         # Solo capa gold
    python pipeline.py validate     # Solo validación de bronze
"""

import logging
import sys
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    BRONZE_DIR,
    SILVER_DIR,
    GOLD_DIR,
    LOGS_DIR,
    PUBLINDEX_FILE,
    DOAJ_FILE,
    SCIMAGO_FILE,
    OPENAPC_FILE,
    PUBLINDEX_SILVER,
    DOAJ_SILVER,
    SCIMAGO_SILVER,
    OPENAPC_SILVER,
    CATALOGO_GOLD,
)

# ── Logging ──────────────────────────────────────────────────────────────
log_file = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

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
    - Parsing del header
    """
    logger.info("=" * 60)
    logger.info("VALIDACIÓN BRONZE")
    logger.info("=" * 60)

    archivos = {
        "publindex": PUBLINDEX_FILE,
        "doaj": DOAJ_FILE,
        "scimago": SCIMAGO_FILE,
        "openapc": OPENAPC_FILE,
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
            "errores": [],
        }

        if not ruta.exists():
            info["errores"].append("Archivo no encontrado")
            logger.warning(f"  ✗ {nombre}: archivo no encontrado ({ruta})")
            resultados[nombre] = info
            continue

        info["tamano_bytes"] = ruta.stat().st_size

        if info["tamano_bytes"] < 100:
            info["errores"].append(f"Archivo sospechosamente pequeño: {info['tamano_bytes']} bytes")
            logger.warning(f"  ⚠ {nombre}: archivo muy pequeño ({info['tamano_bytes']} bytes)")

        # Verificar que no sea una respuesta de error HTTP
        try:
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                primeras_lineas = f.read(500)
            if "<!DOCTYPE" in primeras_lineas or "<html" in primeras_lineas.lower():
                info["errores"].append("El archivo contiene HTML en lugar de datos CSV")
                info["header_valido"] = False
                logger.error(f"  ✗ {nombre}: contiene HTML (posible error de descarga)")
                resultados[nombre] = info
                continue
        except Exception as e:
            info["errores"].append(f"Error al leer archivo: {str(e)}")

        # Hash
        try:
            info["hash_sha256"] = calcular_hash_archivo(ruta)
        except Exception as e:
            info["errores"].append(f"Error calculando hash: {str(e)}")

        # Intentar parsear header
        try:
            sep = ";" if nombre == "scimago" else ","
            if nombre == "doaj":
                # DOAJ tiene \r\r\n
                contenido = ruta.read_text(encoding="utf-8")
                contenido = contenido.replace("\r\r\n", "\n").replace("\r\n", "\n")
                from io import StringIO
                df_test = pd.read_csv(StringIO(contenido), sep=sep, nrows=5)
            else:
                df_test = pd.read_csv(ruta, sep=sep, nrows=5)

            info["header_valido"] = True
            info["num_columnas"] = len(df_test.columns)

            # Contar líneas
            with open(ruta, "rb") as f:
                info["num_filas_aprox"] = sum(1 for _ in f) - 1

            logger.info(
                f"  ✓ {nombre}: {info['num_filas_aprox']} filas, "
                f"{info['num_columnas']} columnas, "
                f"{info['tamano_bytes']:,} bytes"
            )
        except Exception as e:
            info["errores"].append(f"Error parseando CSV: {str(e)}")
            logger.error(f"  ✗ {nombre}: error de parseo — {e}")

        resultados[nombre] = info

    # Guardar registro de validación
    registro_path = LOGS_DIR / "bronze_validation.json"
    with open(registro_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"\n  Registro de validación: {registro_path}")

    return resultados


def ejecutar_silver() -> bool:
    """Ejecuta la capa silver: limpieza y normalización de cada fuente."""
    logger.info("\n" + "=" * 60)
    logger.info("CAPA SILVER — Limpieza y normalización")
    logger.info("=" * 60)

    exitos = 0
    errores = 0

    # Publindex
    logger.info("\n── Procesando Publindex ──")
    try:
        from etl_publindex import procesar_publindex
        df = procesar_publindex()
        if df is not None and not df.empty:
            logger.info(f"  ✓ Publindex: {len(df)} registros procesados")
            exitos += 1
        else:
            logger.warning("  ⚠ Publindex: resultado vacío")
            errores += 1
    except Exception as e:
        logger.error(f"  ✗ Publindex: {e}", exc_info=True)
        errores += 1

    # DOAJ
    logger.info("\n── Procesando DOAJ ──")
    try:
        from etl_doaj import procesar_doaj
        df = procesar_doaj()
        if df is not None and not df.empty:
            logger.info(f"  ✓ DOAJ: {len(df)} registros procesados")
            exitos += 1
        else:
            logger.warning("  ⚠ DOAJ: resultado vacío")
            errores += 1
    except Exception as e:
        logger.error(f"  ✗ DOAJ: {e}", exc_info=True)
        errores += 1

    # Scimago
    logger.info("\n── Procesando Scimago ──")
    try:
        from etl_scimago import procesar_scimago
        df = procesar_scimago()
        if df is not None and not df.empty:
            logger.info(f"  ✓ Scimago: {len(df)} registros procesados")
            exitos += 1
        else:
            logger.warning("  ⚠ Scimago: resultado vacío")
            errores += 1
    except Exception as e:
        logger.error(f"  ✗ Scimago: {e}", exc_info=True)
        errores += 1

    # OpenAPC es una fuente opcional: un archivo ausente o una respuesta HTTP
    # inválida se registra, pero no impide consolidar las otras fuentes.
    logger.info("\n── Procesando OpenAPC ──")
    try:
        from etl_openapc import procesar_openapc
        df = procesar_openapc()
        if df is not None and not df.empty:
            logger.info(f"  ✓ OpenAPC: {len(df)} registros procesados")
        else:
            logger.warning("  ⚠ OpenAPC: fuente no disponible o resultado vacío")
    except Exception as e:
        logger.warning(f"  ⚠ OpenAPC omitido: {e}", exc_info=True)

    logger.info(f"\n  Silver completado: {exitos} éxitos, {errores} errores")
    return errores == 0


def ejecutar_gold() -> bool:
    """Ejecuta la capa gold: integración y consolidación."""
    logger.info("\n" + "=" * 60)
    logger.info("CAPA GOLD — Integración y consolidación")
    logger.info("=" * 60)

    try:
        from merge_gold import merge_gold
        catalogo = merge_gold()
        if catalogo is not None and not catalogo.empty:
            logger.info(f"  ✓ Gold: {len(catalogo)} registros en catálogo maestro")
            return True
        else:
            logger.error("  ✗ Gold: catálogo vacío")
            return False
    except Exception as e:
        logger.error(f"  ✗ Gold: {e}", exc_info=True)
        return False


def analizar_cruces_silver() -> None:
    """Reporta la cobertura de las claves Silver antes de generar Gold."""
    logger.info("\nANÁLISIS DE CRUCES SILVER")
    rutas = {
        "publindex": PUBLINDEX_SILVER,
        "doaj": DOAJ_SILVER,
        "scimago": SCIMAGO_SILVER,
        "openapc": OPENAPC_SILVER,
    }
    tablas = {}
    for nombre, ruta in rutas.items():
        if not ruta.exists():
            logger.warning("  %s: Silver no disponible", nombre)
            continue
        tablas[nombre] = pd.read_parquet(ruta)
        logger.info("  %s: %d registros", nombre, len(tablas[nombre]))

    base = tablas.get("publindex")
    if base is None or "issn_normalizado" not in base.columns:
        logger.warning("  No se puede analizar cobertura sin Publindex Silver")
        return

    base_keys = set(base["issn_normalizado"].dropna())
    for nombre in ("doaj", "scimago", "openapc"):
        tabla = tablas.get(nombre)
        if tabla is None or "issn_normalizado" not in tabla.columns:
            logger.warning("  %s: sin datos para cruce", nombre)
            continue
        keys = set(tabla["issn_normalizado"].dropna())
        matches = len(base_keys & keys)
        percentage_base = 100 * matches / len(base_keys) if base_keys else 0
        percentage_source = 100 * matches / len(keys) if keys else 0
        logger.info(
            "  Publindex ↔ %s: %d coincidencias (%.2f%% de Publindex; "
            "%.2f%% de %s)",
            nombre,
            matches,
            percentage_base,
            percentage_source,
            nombre,
        )


def resumen_final():
    """Genera un resumen del estado final del pipeline."""
    logger.info("\n" + "=" * 60)
    logger.info("RESUMEN FINAL DEL PIPELINE")
    logger.info("=" * 60)

    # Bronze
    logger.info("\n🥉 Bronze:")
    for f in BRONZE_DIR.glob("*"):
        if f.is_file():
            logger.info(f"    {f.name}: {f.stat().st_size:,} bytes")

    # Silver
    logger.info("\n🥈 Silver:")
    for f in SILVER_DIR.glob("*"):
        if f.is_file():
            tamano = f.stat().st_size
            if f.suffix == ".parquet":
                try:
                    df = pd.read_parquet(f)
                    logger.info(f"    {f.name}: {len(df)} registros, {len(df.columns)} columnas")
                except Exception:
                    logger.info(f"    {f.name}: {tamano:,} bytes")
            else:
                logger.info(f"    {f.name}: {tamano:,} bytes")

    # Gold
    logger.info("\n🥇 Gold:")
    for f in GOLD_DIR.glob("*"):
        if f.is_file():
            tamano = f.stat().st_size
            if f.suffix == ".parquet":
                try:
                    df = pd.read_parquet(f)
                    logger.info(f"    {f.name}: {len(df)} registros, {len(df.columns)} columnas")
                except Exception:
                    logger.info(f"    {f.name}: {tamano:,} bytes")
            else:
                logger.info(f"    {f.name}: {tamano:,} bytes")


def main():
    """Punto de entrada principal del pipeline."""
    inicio = time.time()

    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║  PIPELINE ETL — Recomendador de Revistas Científicas    ║")
    logger.info(f"║  Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<47} ║")
    logger.info("╚══════════════════════════════════════════════════════════╝")

    # Determinar qué etapas ejecutar
    etapas = sys.argv[1:] if len(sys.argv) > 1 else ["validate", "silver", "gold"]

    exito = True

    if "validate" in etapas:
        resultados = validar_bronze()
        # Continuar incluso si hay advertencias, pero parar si archivos críticos faltan
        for nombre in ["publindex", "doaj", "scimago"]:
            if nombre in resultados and not resultados[nombre].get("header_valido", False):
                logger.error(f"Archivo bronze crítico inválido: {nombre}")
                if nombre == "publindex":
                    exito = False

    if "silver" in etapas and exito:
        exito = ejecutar_silver()
        if exito:
            analizar_cruces_silver()

    if "gold" in etapas and exito:
        exito = ejecutar_gold()

    # Resumen
    resumen_final()

    duracion = time.time() - inicio
    logger.info(f"\nDuración total: {duracion:.1f} segundos")
    logger.info(f"Log guardado en: {log_file}")

    if exito:
        logger.info("\n✓ Pipeline completado exitosamente.")
    else:
        logger.error("\n✗ Pipeline completado con errores.")
        sys.exit(1)


if __name__ == "__main__":
    main()
