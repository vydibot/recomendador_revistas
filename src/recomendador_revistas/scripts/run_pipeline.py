"""Ejecuta el pipeline ETL profesional desde la raíz del repositorio."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recomendador_revistas.etl.runner import main


if __name__ == "__main__":
    main()