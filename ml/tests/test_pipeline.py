"""
Suite de Pruebas Unitarias e Integración — Pipeline ETL y Preprocesamiento.

Cubre:
- Normalización y checksum de ISSN (ISO 3297).
- Normalización y similitud de títulos (sin diacríticos, puntuación ni stopwords).
- Parsing de números con separadores decimales (coma/punto) y miles.
- Conversión monetaria a USD y transformación por Paridad de Poder Adquisitivo (PPP USD).
- Detección de cobros de APC atípicos con umbral de 3 rangos intercuartílicos (3 * IQR).
- Imputación condicional de APC (regresión multivariable y fallback estratificado).
- Estandarización Z-Score y escalamiento Min-Max [0, 1].
- Cálculo de variables binarias (exención LMIC, diamante, revisión abierta, indexada DOAJ).
- Codificación ordinal y contraste/brecha Publindex vs Scimago.
- Precedencia de APC observado en OpenAPC sobre APC declarado.
- Cruce secundario por similitud de título.
"""

import numpy as np
import pandas as pd
import pytest

from recomendador_revistas.etl.sources.apc import (
    _read_csv,
    procesar_facts,
    procesar_openapc,
)
from recomendador_revistas.etl.sources import papers as papers_etl
from recomendador_revistas.etl.gold import (
    construir_dataset_texto_modelos,
    cruce_multietapa,
    enriquecer_dataset_texto,
    exportar_apc_observado_declarado,
    resolver_conflictos_y_precedencias,
)
from recomendador_revistas.data.normalization import (
    calcular_variables_binarias,
    codificar_one_hot,
    codificar_ordinal_y_contraste,
    convertir_a_ppp_usd,
    convertir_a_usd,
    detectar_outliers_apc,
    escalar_minmax,
    estandarizar_zscore,
    imputar_apc,
    limpiar_issn,
    normalizar_pais,
    normalizar_titulo,
    parsear_numero_es_en,
    similitud_titulos,
    validar_issn_checksum,
)


def test_issn_normalization_and_checksum():
    """Valida normalización de formatos y verificación de dígito de control módulo 11."""
    assert limpiar_issn("ISSN: 0124-5376") == "0124-5376"
    assert limpiar_issn("e-issn 2539200X") == "2539-200X"
    assert limpiar_issn("1234567") is None  # Longitud inválida
    assert validar_issn_checksum("0124-5376") is True
    assert validar_issn_checksum("2539-200X") is True
    assert validar_issn_checksum("0124-5377") is False  # Checksum incorrecto


def test_title_normalization_and_similarity():
    """Valida remoción de diacríticos, puntuación y stopwords, y cálculo de similitud."""
    tit1 = "Revista Colombiana de Biotecnología!"
    tit2 = "colombiana biotecnologia"
    assert normalizar_titulo(tit1) == "colombiana biotecnologia"
    assert similitud_titulos(tit1, tit2) == 100.0
    assert similitud_titulos("Journal of Applied Physics", "Applied Physics") > 85.0


def test_numeric_parsing_delimiters():
    """Valida la lectura correcta de coma decimal y punto de miles."""
    assert parsear_numero_es_en("0,914") == 0.914
    assert parsear_numero_es_en("1.500,50") == 1500.50
    assert parsear_numero_es_en("1,500.50") == 1500.50
    assert parsear_numero_es_en("36,11") == 36.11
    assert parsear_numero_es_en(None) is None


def test_usd_and_ppp_conversions():
    """Valida conversión de moneda a USD y transformación por PPP según país."""
    usd, tasa = convertir_a_usd(1000, "EUR")
    assert usd == 1080.0
    assert tasa == 1.08

    # PPP en Colombia (factor 0.38): el costo relativo en PPP es mayor al poder adquisitivo local
    ppp_co = convertir_a_ppp_usd(1000.0, "CO")
    assert ppp_co == round(1000.0 / 0.38, 2)

    # PPP en EE.UU. (factor 1.00):
    ppp_us = convertir_a_ppp_usd(1000.0, "US")
    assert ppp_us == 1000.0


def test_observed_doaj_currencies_have_conversion_rates():
    """Valida las monedas observadas en DOAJ que antes quedaban sin tasa."""
    for currency in ["YER", "IRR", "SYP", "XOF", "IQD", "KZT", "NPR", "VND"]:
        usd, rate = convertir_a_usd(100, currency)
        assert usd is not None
        assert rate is not None


def test_outlier_detection_3_iqr():
    """Valida detección de cobros de APC atípicos con el umbral de 3 * IQR."""
    df = pd.DataFrame({
        "apc_monto_usd": [100.0, 110.0, 120.0, 105.0, 115.0, 95.0, 10000.0]
    })
    outliers = detectar_outliers_apc(df, columna_apc="apc_monto_usd", iqr_factor=3.0)
    assert bool(outliers.iloc[6]) is True
    assert bool(outliers.iloc[0]) is False


def test_conditional_apc_imputation():
    """Valida imputación condicional y asignación del flag apc_imputado."""
    df = pd.DataFrame({
        "apc_monto_usd": [100.0, 120.0, 110.0, 130.0, 115.0, None],
        "cuartil_sjr": ["Q1", "Q1", "Q1", "Q2", "Q2", "Q1"],
        "gran_area": ["Ciencias Naturales"] * 6,
        "editorial": ["Editorial X"] * 6,
        "is_hybrid": [False] * 6,
    })
    imputed = imputar_apc(df)
    assert bool(imputed.loc[5, "apc_imputado"]) is True
    assert imputed.loc[5, "apc_tipo"] == "imputado"
    assert pd.notna(imputed.loc[5, "apc_monto_usd"])
    assert imputed.loc[5, "apc_metodo_imputacion"] in [
        "regresion_condicional",
        "mediana_estrato_cuartil_disciplina",
        "mediana_disciplina",
        "mediana_cuartil",
    ]


def test_continuous_scaling_zscore_minmax():
    """Valida estandarización Z-score y escalamiento Min-Max [0, 1]."""
    df = pd.DataFrame({
        "sjr_score": [0.2, 0.4, 0.6, 0.8, 1.0],
        "h_index": [5, 10, 15, 20, 25],
    })
    df_scaled = estandarizar_zscore(df, ["sjr_score", "h_index"])
    assert "sjr_score_zscore" in df_scaled.columns
    assert abs(df_scaled["sjr_score_zscore"].mean()) < 1e-3

    df_minmax = escalar_minmax(df, ["sjr_score", "h_index"])
    assert df_minmax["sjr_score_minmax"].min() == 0.0
    assert df_minmax["sjr_score_minmax"].max() == 1.0


def test_binary_variables_and_contrasts():
    """Valida flags binarios y cálculo de brecha ordinal Publindex vs Scimago."""
    df = pd.DataFrame({
        "open_access": [True, False, True],
        "tiene_apc": [False, True, True],
        "apc_monto_usd": [0.0, 500.0, 1000.0],
        "politica_exencion": [False, True, False],
        "pais_iso": ["CO", "US", "DE"],
        "tipo_revision": ["Double anonymous", "Open peer review", "Anonymous"],
        "_fuentes": [["publindex", "doaj"], ["publindex"], ["publindex", "scimago"]],
        "categoria_publindex": ["A1", "B", "C"],
        "cuartil_sjr": ["Q1", "Q3", "Q1"],
    })
    df = calcular_variables_binarias(df)
    assert bool(df.loc[0, "oa_diamond"]) is True
    assert bool(df.loc[1, "oa_diamond"]) is False
    assert bool(df.loc[0, "exencion_apc_lmic"]) is True  # Colombia está en LMIC
    assert bool(df.loc[1, "revision_abierta"]) is True
    assert bool(df.loc[0, "indexada_doaj"]) is True
    assert bool(df.loc[1, "indexada_doaj"]) is False

    df = codificar_ordinal_y_contraste(df)
    assert df.loc[0, "categoria_publindex_ord"] == 4  # A1
    assert df.loc[0, "cuartil_sjr_ord"] == 4          # Q1
    assert df.loc[0, "brecha_publindex_sjr"] == 0
    assert df.loc[1, "categoria_publindex_ord"] == 2  # B
    assert df.loc[1, "cuartil_sjr_ord"] == 2          # Q3
    assert df.loc[2, "categoria_publindex_ord"] == 1  # C
    assert df.loc[2, "cuartil_sjr_ord"] == 4          # Q1
    assert df.loc[2, "brecha_publindex_sjr"] == -3    # 1 - 4


def test_openapc_observed_precedence():
    """Valida que los pagos observados de OpenAPC reemplazan los montos declarados."""
    df = pd.DataFrame({
        "apc_monto_usd": [2000.0],
        "apc_tipo": ["declarado"],
        "apc_monto_usd_openapc": [1500.0],
        "apc_tipo_openapc": ["observado"],
    })
    res = resolver_conflictos_y_precedencias(df)
    assert res.loc[0, "apc_monto_usd"] == 1500.0
    assert res.loc[0, "apc_tipo"] == "observado"


def test_facts_registry_is_normalized_as_observed_apc():
    """Valida que el registro Facts se incorpore con sus columnas APC compatibles."""
    facts = procesar_facts()
    assert not facts.empty
    assert facts["_fuente"].eq("facts").all()
    assert facts["apc_tipo"].eq("observado").all()
    assert facts["apc_monto_original"].notna().all()


def test_one_hot_encoding():
    """Valida la generación de variables One-Hot para país, disciplina y licencia."""
    df = pd.DataFrame({
        "pais_iso": ["CO", "BR", "ES"],
        "gran_area": ["Ciencias Naturales", "Ingenierías", "Humanidades"],
        "licencia": ["CC BY", "CC BY-NC", "CC BY-SA"],
    })
    encoded = codificar_one_hot(df, ["pais_iso", "gran_area", "licencia"])
    assert "pais_iso_CO" in encoded.columns
    assert "gran_area_Ingenierías" in encoded.columns
    assert "licencia_CC BY" in encoded.columns


def test_export_apc_observado_declarado_non_imputed(tmp_path):
    """Valida que se exporte un CSV adicional solo con APC real (no imputado)."""
    df = pd.DataFrame({
        "issn_normalizado": ["1111-1111", "2222-2222", "3333-3333"],
        "titulo": ["Revista A", "Revista B", "Revista C"],
        "apc_tipo": ["observado", "declarado", "imputado"],
        "apc_imputado": [False, False, True],
        "apc_monto_usd": [300.0, 400.0, 150.0],
    })

    out = exportar_apc_observado_declarado(df, output_path=tmp_path / "apc_real.csv")

    assert out is not None
    assert len(out) == 2
    assert set(out["apc_tipo"]) == {"observado", "declarado"}
    assert out["apc_imputado"].eq(False).all()
    assert out["apc_monto_usd"].notna().all()


def test_text_model_dataset_separates_languages_and_removes_no_registra():
    """Valida ISSN físico/virtual, textos separados y limpieza de No registra."""
    df = pd.DataFrame({
        "issn_print": ["1234-5678", "2345-6789"],
        "issn_electronic": ["8765-4321", "9876-5432"],
        "issn_normalizado": ["1234-5678", "2345-6789"],
        "especialidad": ["Medicina", "No registra"],
        "area_conocimiento": ["Medicina Clínica", "Economía"],
        "gran_area": ["Ciencias Médicas", "Ciencias Sociales"],
        "categoria_publindex": ["A1", "B"],
        "categorias_scimago": ["Medicine (Q1)", "Law (Q2)"],
        "areas_scimago": ["Medicine", "Social Sciences"],
        "titulo_normalizado": ["salud publica", "derecho"],
        "titulo_normalizado_scimago_dup": ["public health", "law"],
        "titulo_alternativo": ["Public Health Journal", "Revista de Derecho"],
        "palabras_clave": ["health, public health, salud", "derecho, sociedad, law"],
        "materias": ["Medicine, salud", "Law"],
        "idiomas": ["Spanish, English", "Spanish"],
    })

    out = construir_dataset_texto_modelos(df)

    assert len(out) == 2
    assert out.loc[0, "issn_fisico"] == "1234-5678"
    assert out.loc[0, "issn_virtual"] == "8765-4321"
    assert "medicina" in out.loc[0, "texto_espanol"]
    assert "medicine" in out.loc[0, "texto_ingles"]
    assert "health" in out.loc[0, "texto_ingles"]
    assert "health" not in out.loc[0, "texto_espanol"]
    assert "salud" in out.loc[0, "texto_espanol"]
    assert "salud" not in out.loc[0, "texto_ingles"]
    assert "no registra" not in out["texto_espanol"].str.cat(sep=" ")
    assert "http" not in out.loc[0, "texto_espanol"]


def test_text_model_dataset_contains_only_real_apc_costs():
    """Valida que la salida APC textual excluya costos imputados."""
    df = pd.DataFrame({
        "issn_print": ["1234-5678", "2345-6789"],
        "issn_electronic": ["8765-4321", "9876-5432"],
        "issn_normalizado": ["1234-5678", "2345-6789"],
        "especialidad": ["Medicina", "Economía"],
        "area_conocimiento": ["Medicina Clínica", "Economía"],
        "gran_area": ["Ciencias Médicas", "Ciencias Sociales"],
        "categoria_publindex": ["A1", "B"],
        "apc_tipo": ["observado", "imputado"],
        "apc_imputado": [False, True],
        "apc_monto_usd": [500.0, 800.0],
        "titulo_normalizado": ["salud publica", "economia"],
    })

    out = construir_dataset_texto_modelos(df)
    real = out.loc[out["apc_real_disponible"]]

    assert len(real) == 1
    assert real.loc[0, "apc_tipo"] == "observado"
    assert real.loc[0, "apc_monto_usd"] == 500.0
    assert out.loc[1, "apc_monto_usd"] is pd.NA or pd.isna(out.loc[1, "apc_monto_usd"])


def test_text_model_dataset_is_enriched_with_gold_features():
    """Valida el cruce por ISSN de métricas, fechas y escalas Gold."""
    texto = pd.DataFrame({
        "issn_normalizado": ["1234-5678"],
        "texto_espanol": ["medicina"],
        "texto_ingles": ["medicine"],
    })
    catalogo = pd.DataFrame({
        "issn_normalizado": ["1234-5678"],
        "cuartil_sjr_ord": [4],
        "h_index": [20],
        "total_docs": [100],
        "fecha_incorporacion": ["2020-01-01"],
        "semanas_pub": [10],
        "ratio_citas_docs": [2.5],
        "indice_calidad_costo": [0.8],
        "h_index_zscore": [1.2],
        "h_index_minmax": [0.9],
    })

    enriched = enriquecer_dataset_texto(texto, catalogo)

    assert len(enriched) == 1
    assert enriched.loc[0, "cuartil_sjr_ord"] == 4
    assert enriched.loc[0, "h_index"] == 20
    assert enriched.loc[0, "fecha_incorporacion"] == "2020-01-01"
    assert enriched.loc[0, "h_index_zscore"] == 1.2
    assert enriched.loc[0, "h_index_minmax"] == 0.9


def test_papers_gold_keeps_source_fields_and_normalized_text(tmp_path, monkeypatch):
    """Valida que Gold conserve campos fuente y versiones normalizadas."""
    monkeypatch.setattr(papers_etl, "ARTICULOS_GOLD", tmp_path / "articulos.parquet")
    monkeypatch.setattr(papers_etl, "ARTICULOS_GOLD_CSV", tmp_path / "articulos.csv")
    silver = pd.DataFrame({
        "issn_normalizado": ["1234-5678"],
        "articulo_id": ["paper_1"],
        "archivo": ["paper.pdf"],
        "idioma": ["es"],
        "titulo": [r"Estudio -- clínico $x^2$"],
        "resumen": ["Las políticas públicas mejoran resultados"],
        "palabras_clave": ["salud, educación"],
    })

    processed = papers_etl.normalizar_papers(silver)
    gold = papers_etl.construir_gold_articulos(processed)

    assert "--" not in gold.loc[0, "tokens_normalizados"]
    assert "clin" in gold.loc[0, "titulo_normalizado"]
    assert gold.loc[0, "titulo"] == r"Estudio -- clínico $x^2$"
    assert gold.loc[0, "resumen"] == "Las políticas públicas mejoran resultados"
    assert gold.loc[0, "palabras_clave"] == "salud, educación"
    assert gold.loc[0, "issn_normalizado"] == "1234-5678"
