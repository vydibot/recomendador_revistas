import json

import pandas as pd
from sqlalchemy import func, select

from app.models import Journal
from app.services import journals as service
from app.services import mappers, seed


def _lider_file(tmp_path):
    records = [
        {"Nombre": "500", "ISSN Electrónico": "", "Costo": ""},
        {
            "Nombre": "IEEE Transactions on Cloud Computing",
            "ISSN Electrónico": "2168-7161",
            "ISSN Impreso": "N/A",
            "Costo": "~USD 2160",
            "Cuanto demora en publicar?": "3–6 meses",
            "Indexación": "Q1",
            "Acceso": "Híbrido",
            "Ubicación": "USA",
        },
        {"Nombre": "IEEE Transactions on Cloud Computing", "ISSN Electrónico": "2168-7161"},
        {"Nombre": "Journal B", "ISSN Electrónico": "1234-5678", "Indexación": "Q2/Q1"},
    ]
    path = tmp_path / "lider.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def _gold_file(tmp_path):
    base_a = {
        "titulo": "Revista A",
        "issn_print": "0034-7450",
        "pais": "Colombia",
        "id_revista_publindex": 10,
    }
    frame = pd.DataFrame(
        [
            {
                **base_a,
                "issn_normalizado": "0034-7450",
                "issn_electronic": "1657-0448",
                "anio_clasificacion": 2022,
                "gran_area": "Ciencias Sociales",
                "area_conocimiento": "Derecho",
                "cuartil_sjr": "Q4",
                "categoria_publindex": "B",
                "apc_monto_usd_real": 100.5,
                "open_access": True,
                "is_hybrid": None,
                "semanas_pub": 12.0,
                "h_index": 5.0,
                "indice_topsis_calidad_costo": 0.4,
                "idiomas": "English, Spanish",
                "_fuentes": ["doaj", "publindex"],
                "tiene_apc": True,
            },
            # Misma revista (id 10) clasificada en 2016 bajo otro ISSN: debe colapsar en una sola.
            {
                **base_a,
                "issn_normalizado": "1657-0448",
                "anio_clasificacion": 2016,
                "categoria_publindex": "C",
                "_fuentes": ["publindex"],
            },
            {
                "issn_normalizado": "1111-2222",
                "titulo": "Revista B",
                "pais": "No disponible",
                "gran_area": "No registra",
                "area_conocimiento": "No registra",
                "tiene_apc": False,
                "open_access": None,
                "_fuentes": ["publindex"],
                "id_revista_publindex": None,
                "anio_clasificacion": 2020,
            },
        ]
    )
    path = tmp_path / "gold.parquet"
    frame.to_parquet(path)
    return path


def test_lider_junk_and_duplicates(db, tmp_path):
    stats = seed.seed_lider(db, _lider_file(tmp_path))
    assert stats.created == 2 and stats.skipped_invalid == 1
    cloud = db.scalar(select(Journal).where(Journal.title.like("IEEE%")))
    assert cloud.apc_usd == 2160.0 and cloud.weeks_to_publication == 19.6
    assert cloud.country == "Estados Unidos" and cloud.issn_normalized == "2168-7161"
    assert [t.name for t in cloud.topics]  # temas inferidos
    journal_b = db.scalar(select(Journal).where(Journal.title == "Journal B"))
    assert journal_b.quartile == "Q1"


def test_gold_mapping(db, tmp_path):
    stats = seed.seed_etl(db, _gold_file(tmp_path))
    assert stats.created == 2  # 3 filas del Gold = 2 revistas
    a = db.scalar(select(Journal).where(Journal.issn_normalized == "0034-7450"))
    assert a.apc_usd == 100.5 and a.apc_status == "con_costo"
    assert a.access_type == "Open Access" and a.language == "Inglés, Español"
    assert a.h_index == 5 and a.quality_cost_index == 0.4
    assert a.sources == ["doaj", "publindex"]
    assert sorted(t.name for t in a.topics) == ["Ciencias Sociales", "Derecho"]
    b = db.scalar(select(Journal).where(Journal.issn_normalized == "1111-2222"))
    assert b.country is None and b.apc_usd == 0.0 and b.apc_status == "sin_costo"
    assert [t.name for t in b.topics] == ["Sin clasificar"]
    assert isinstance(
        a.details["total_docs_3y"] if "total_docs_3y" in a.details else None, (int, type(None))
    )


def test_seed_is_idempotent_and_protects_edits(db, tmp_path):
    gold = _gold_file(tmp_path)
    lider = _lider_file(tmp_path)
    seed.seed_all(db, gold, lider)
    total = db.scalar(select(func.count(Journal.id)))
    edited = db.scalar(select(Journal).where(Journal.issn_normalized == "0034-7450"))
    service.update_journal(db, edited, {"title": "Título corregido a mano"})

    results = seed.seed_all(db, gold, lider)
    assert db.scalar(select(func.count(Journal.id))) == total
    assert results["etl"].created == 0 and results["etl"].protected == 1
    db.refresh(edited)
    assert edited.title == "Título corregido a mano"


def test_missing_sources_are_skipped(db, tmp_path):
    results = seed.seed_all(db, tmp_path / "no.parquet", tmp_path / "no.json")
    assert results["etl"].created == 0 and results["lider"].created == 0


def test_valid_lider_record():
    assert not mappers.is_valid_lider_record({"Nombre": "500"})
    assert mappers.is_valid_lider_record({"Nombre": "Nature"})


def test_lider_link_that_is_not_a_url_is_kept_aside():
    values = mappers.from_lider({"Nombre": "Journal X", "Link": "IEEE Xplore: Journal X"})
    assert values["url"] is None
    assert values["details"]["enlace_original"] == "IEEE Xplore: Journal X"
    ok = mappers.from_lider({"Nombre": "Journal X", "Link": "https://example.org/x"})
    assert ok["url"] == "https://example.org/x" and "enlace_original" not in ok["details"]


def test_seed_prunes_rows_that_left_the_source(db, tmp_path):
    gold = _gold_file(tmp_path)
    seed.seed_etl(db, gold)
    frame = pd.read_parquet(gold)
    frame[frame.issn_normalizado != "1111-2222"].to_parquet(gold)
    stats = seed.seed_etl(db, gold)
    assert stats.pruned == 1
    assert db.scalar(select(func.count(Journal.id)).where(Journal.origin == "etl")) == 1


def test_gold_flags_work_with_numpy_booleans():
    """Filas obtenidas con ``iloc``/groupby traen np.bool_ (``is False`` fallaría en silencio)."""
    import numpy as np

    row = pd.Series(
        {
            "issn_normalizado": "1111-2222",
            "titulo": "X",
            "tiene_apc": np.False_,
            "is_hybrid": np.True_,
            "open_access": np.False_,
            "_fuentes": ["publindex"],
        }
    )
    values = mappers.from_gold_row(row)
    assert values["apc_usd"] == 0.0
    assert values["access_type"] == "Híbrido"
    only_closed = mappers.from_gold_row(pd.Series({**row.to_dict(), "is_hybrid": np.False_}))
    assert only_closed["access_type"] == "Suscripción"
