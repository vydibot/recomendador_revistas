"""Reporte de imputación APC y valores faltantes en la capa Gold.

Uso:
    python codes/report_apc_gold.py
    python codes/report_apc_gold.py --input data/gold/catalogo_maestro_revistas.csv

Genera:
    reports/apc_quality_summary.json
    reports/apc_missing_by_row.csv
    reports/missing_by_variable.csv
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PARQUET = PROJECT_ROOT / "data" / "gold" / "catalogo_maestro_revistas.parquet"
DEFAULT_CSV = PROJECT_ROOT / "data" / "gold" / "catalogo_maestro_revistas.csv"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports"

IDENTIFICATION_COLUMNS = [
    "issn_normalizado",
    "titulo",
    "titulo_normalizado",
]
APC_COLUMNS = [
    "apc_monto",
    "apc_moneda",
    "apc_monto_usd",
    "apc_tipo",
    "apc_metodo_imputacion",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calcula imputación APC y faltantes por registro Gold."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Archivo Gold .parquet o .csv. Por defecto se busca Parquet y luego CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directorio donde se guardan los reportes.",
    )
    return parser.parse_args()


def _resolve_input(input_path: Path | None) -> Path:
    if input_path:
        if not input_path.exists():
            raise FileNotFoundError(f"No existe el archivo Gold: {input_path}")
        return input_path
    if DEFAULT_PARQUET.exists():
        return DEFAULT_PARQUET
    if DEFAULT_CSV.exists():
        return DEFAULT_CSV
    raise FileNotFoundError(
        "No se encontró data/gold/catalogo_maestro_revistas.parquet ni .csv"
    )


def _load_gold(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, low_memory=False)
    raise ValueError("La entrada debe tener extensión .parquet o .csv")


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip().lower() in {"nan", "none", "null"}
    result = pd.isna(value)
    return bool(result) if not hasattr(result, "__len__") else False


def _missing_columns(row: pd.Series) -> list[str]:
    return [column for column, value in row.items() if _is_missing(value)]


def build_report(
    df: pd.DataFrame,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    missing_columns = [column for column in APC_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Faltan columnas APC obligatorias en Gold: "
            + ", ".join(missing_columns)
        )

    total_rows = len(df)
    apc_type = df["apc_tipo"].astype("string").str.strip().str.lower()
    imputed_mask = apc_type.eq("imputado")
    classified_mask = apc_type.notna() & apc_type.ne("")
    missing_apc_mask = df[APC_COLUMNS].isna().any(axis=1)

    details = pd.DataFrame(index=df.index)
    for column in IDENTIFICATION_COLUMNS:
        if column in df.columns:
            details[column] = df[column]
    details["fila_gold"] = df.index + 2
    details["apc_tipo"] = df["apc_tipo"]
    details["apc_monto_usd"] = df["apc_monto_usd"]
    details["apc_imputado"] = imputed_mask
    details["faltan_campos_apc"] = df[APC_COLUMNS].apply(
        lambda row: ", ".join(_missing_columns(row)), axis=1
    )
    details["faltan_campos_todos"] = df.apply(
        lambda row: ", ".join(_missing_columns(row)), axis=1
    )

    variable_missing = pd.DataFrame(
        {
            "variable": df.columns,
            "registros_faltantes": [
                int(df[column].apply(_is_missing).sum()) for column in df.columns
            ],
        }
    )
    variable_missing["registros_totales"] = total_rows
    variable_missing["porcentaje_faltantes"] = (
        100 * variable_missing["registros_faltantes"] / total_rows
        if total_rows
        else 0.0
    ).round(2)
    variable_missing = variable_missing.sort_values(
        ["porcentaje_faltantes", "variable"], ascending=[False, True]
    ).reset_index(drop=True)

    summary = {
        "total_registros": total_rows,
        "registros_apc_clasificados": int(classified_mask.sum()),
        "registros_apc_imputados": int(imputed_mask.sum()),
        "registros_con_faltantes_apc": int(missing_apc_mask.sum()),
        "porcentaje_imputados_sobre_total": round(
            100 * imputed_mask.sum() / total_rows, 2
        ) if total_rows else 0.0,
        "porcentaje_imputados_sobre_apc_clasificados": round(
            100 * imputed_mask.sum() / classified_mask.sum(), 2
        ) if classified_mask.sum() else 0.0,
        "campos_apc_revisados": APC_COLUMNS,
        "variables": variable_missing.to_dict(orient="records"),
    }
    return summary, details, variable_missing


def main() -> int:
    args = _parse_args()
    try:
        input_path = _resolve_input(args.input)
        gold = _load_gold(input_path)
        summary, details, variable_missing = build_report(gold)
    except (FileNotFoundError, ValueError, ImportError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "apc_quality_summary.json"
    details_path = args.output_dir / "apc_missing_by_row.csv"
    variable_missing_path = args.output_dir / "missing_by_variable.csv"
    summary["archivo_entrada"] = str(input_path)

    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    details.to_csv(details_path, index=False, encoding="utf-8")
    variable_missing.to_csv(variable_missing_path, index=False, encoding="utf-8")

    print(f"Archivo Gold: {input_path}")
    print(f"Registros: {summary['total_registros']}")
    print(
        "APC imputados: "
        f"{summary['registros_apc_imputados']} "
        f"({summary['porcentaje_imputados_sobre_total']:.2f}% del total; "
        f"{summary['porcentaje_imputados_sobre_apc_clasificados']:.2f}% de APC clasificados)"
    )
    print(f"Registros con faltantes APC: {summary['registros_con_faltantes_apc']}")
    print(f"Resumen: {summary_path}")
    print(f"Detalle por fila: {details_path}")
    print(f"Faltantes por variable: {variable_missing_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
