import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl_openapc import _read_csv, procesar_openapc
from merge_gold import resolver_conflictos
from normalize import detectar_outliers_apc, imputar_apc, limpiar_issn, validar_issn_checksum


def test_issn_normalization_and_checksum():
    assert limpiar_issn("ISSN: 0124-5376") == "0124-5376"
    assert validar_issn_checksum("0124-5376")
    assert limpiar_issn("not-an-issn") is None


def test_openapc_rejects_html(tmp_path):
    html = tmp_path / "apc.html"
    html.write_text("<?xml version='1.0'?><html>503</html>", encoding="utf-8")
    with pytest.raises(ValueError):
        _read_csv(html)


def test_apc_imputation_and_outliers():
    frame = pd.DataFrame(
        {
            "editorial": ["A", "A", "B", "B", "B", "B"],
            "gran_area": ["X"] * 6,
            "cuartil_sjr": ["Q1"] * 6,
            "apc_monto_usd": [100.0, 120.0, 100.0, 110.0, 105.0, None],
            "apc_tipo": ["declarado"] * 5 + [None],
        }
    )
    imputed = imputar_apc(frame)
    assert imputed.loc[5, "apc_tipo"] == "imputado"
    assert imputed.loc[5, "apc_monto_usd"] == 105.0
    flags = detectar_outliers_apc(imputed)
    assert flags.dtype == bool


def test_openapc_overrides_declared_apc():
    frame = pd.DataFrame(
        {
            "apc_monto": [500.0],
            "apc_moneda": ["USD"],
            "apc_monto_usd": [500.0],
            "apc_tipo": ["declarado"],
            "apc_monto_openapc": [300.0],
            "apc_moneda_openapc": ["USD"],
            "apc_monto_usd_openapc": [300.0],
            "apc_tipo_openapc": ["observado"],
        }
    )
    result = resolver_conflictos(frame)
    assert result.loc[0, "apc_monto_usd"] == 300.0
    assert result.loc[0, "apc_tipo"] == "observado"
