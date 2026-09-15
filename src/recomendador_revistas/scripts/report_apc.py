"""Genera el reporte de calidad y completitud de APC."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recomendador_revistas.analysis.apc_report import main


if __name__ == "__main__":
    raise SystemExit(main())