import pytest

from app.services import normalizers as nz


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("~USD 3990", 3990.0),
        ("~USD 2310 | CHF 1800", 2310.0),
        ("~USD 175-1450", 812.5),
        ("~USD 990–2000", 1495.0),
        ("CHF 1800", 2034.0),
        ("€ 1.500", 1620.0),
        ("Gratis", 0.0),
        ("~USD", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_apc(text, expected):
    assert nz.parse_apc(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("3–6 meses", 19.6), ("2-4 semanas", 3.0), ("45 días", 6.4), ("continuo", None), ("12", None)],
)
def test_parse_weeks(text, expected):
    assert nz.parse_weeks(text) == expected


def test_quartile_access_country_format():
    assert nz.normalize_quartile("Q2/Q1") == "Q1"
    assert nz.normalize_quartile("sin dato") is None
    assert nz.normalize_access("Híbrido") == "Híbrido"
    assert nz.normalize_access("Gold OA") == "Open Access"
    assert nz.normalize_access("Suscripción") == "Suscripción"
    assert nz.normalize_country("USA") == "Estados Unidos"
    assert nz.normalize_country("China/Elsevier") == "China"
    assert nz.normalize_submission_format("Elsevier (Editorial Manager, APA)") == "Elsevier"
    assert nz.normalize_submission_format("IEEE format") == "IEEE"
    assert nz.normalize_submission_format("Elsevier/SAGE") == "Elsevier"


def test_issn_and_blank_markers():
    assert nz.normalize_issn("1873-4707") == "1873-4707"
    assert nz.normalize_issn("17504729") == "1750-4729"
    assert nz.normalize_issn("2434-561x") == "2434-561X"
    assert nz.normalize_issn("N/A") is None
    assert nz.clean("  N/A ") is None
    assert nz.clean(float("nan")) is None


def test_search_key_ignores_accents_and_case():
    assert nz.search_key("Agronomía", "  Ciberseguridad ") == "agronomia ciberseguridad"


def test_apc_status_and_topics():
    assert nz.apc_status(None) == "desconocido"
    assert nz.apc_status(0) == "sin_costo"
    assert nz.apc_status(10) == "con_costo"
    assert "Computación en la Nube" in nz.infer_topics("IEEE Transactions on Cloud Computing")
    assert nz.infer_topics("Nature Machine Intelligence")[0] == "Inteligencia Artificial"
    assert nz.infer_topics("Zzz Qqq") == ["Ingeniería General"]
