import io

from tests.conftest import make_journal


def titles(response):
    return [item["title"] for item in response.json()["items"]]


def test_list_and_pagination(client, catalog):
    body = client.get("/api/journals", params={"page_size": 2}).json()
    assert body["total"] == 4 and len(body["items"]) == 2 and body["page"] == 1
    second = client.get("/api/journals", params={"page_size": 2, "page": 2}).json()
    assert {i["id"] for i in body["items"]}.isdisjoint({i["id"] for i in second["items"]})


def test_filters(client, catalog):
    get = lambda **p: titles(client.get("/api/journals", params=p))  # noqa: E731
    assert get(quartile="Q1") == ["Journal of Machine Learning"]
    assert sorted(get(quartile=["Q1", "Q3"])) == [
        "Journal of Machine Learning",
        "Revista Colombiana de Agronomía",
    ]
    assert get(access="Híbrido") == ["Revista Colombiana de Agronomía"]
    assert get(country="España") == ["Ciberseguridad Aplicada"]
    assert get(topic="Aprendizaje Automático") == [
        "Ciberseguridad Aplicada",
        "Journal of Machine Learning",
    ]
    assert get(apc_status="sin_costo") == ["Journal of Machine Learning"]
    assert get(apc_max=600, apc_min=100) == ["Revista Colombiana de Agronomía"]
    assert get(weeks_max=10) == ["Journal of Machine Learning"]
    assert get(h_index_min=100) == ["Journal of Machine Learning"]
    assert get(publindex="A2") == ["Revista Colombiana de Agronomía"]
    assert get(format="Springer") == ["Ciberseguridad Aplicada"]
    assert get(language="Español") == ["Ciberseguridad Aplicada", "Revista Colombiana de Agronomía"]
    assert get(origin="manual") and not get(origin="etl")


def test_search_is_accent_insensitive_and_matches_issn(client, catalog):
    assert titles(client.get("/api/journals", params={"q": "agronomia"})) == [
        "Revista Colombiana de Agronomía"
    ]
    assert titles(client.get("/api/journals", params={"q": "AGRONOMÍA colombiana"})) == [
        "Revista Colombiana de Agronomía"
    ]
    assert titles(client.get("/api/journals", params={"q": "3333-3333"})) == [
        "Ciberseguridad Aplicada"
    ]
    assert client.get("/api/journals", params={"q": "%"}).json()["total"] == 0


def test_sort_puts_nulls_last(client, catalog):
    asc = titles(client.get("/api/journals", params={"sort": "apc", "order": "asc"}))
    assert (
        asc[:3]
        == [
            "Journal of Machine Learning",
            "Revista Colombiana de Agronomía",
            "Ciberseguridad Aplicada",
        ]
        and asc[-1] == "Sin Datos"
    )
    desc = titles(client.get("/api/journals", params={"sort": "apc", "order": "desc"}))
    assert desc[0] == "Ciberseguridad Aplicada" and desc[-1] == "Sin Datos"
    assert client.get("/api/journals", params={"sort": "drop table"}).status_code == 422


def test_facets(client, catalog):
    facets = client.get("/api/journals/facets").json()
    assert facets["total"] == 4
    assert {"value": "Aprendizaje Automático", "count": 2} in facets["topics"]
    assert [q["value"] for q in facets["quartiles"]] == ["Q1", "Q2", "Q3"]
    assert facets["max_apc_usd"] == 2500.0 and facets["max_h_index"] == 120
    assert {"value": "Español", "count": 2} in facets["languages"]


def test_detail_and_404(client, catalog):
    ok = client.get(f"/api/journals/{catalog[0].id}")
    assert ok.status_code == 200 and ok.json()["topics"] == ["Aprendizaje Automático"]
    assert client.get("/api/journals/99999").status_code == 404


def test_write_requires_auth(client, catalog):
    assert client.post("/api/journals", json={"title": "X"}).status_code == 401
    assert client.patch(f"/api/journals/{catalog[0].id}", json={"title": "Y"}).status_code == 401
    assert client.delete(f"/api/journals/{catalog[0].id}").status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.post("/api/journals", json={"title": "X"}, headers=bad).status_code == 401


def test_login(client):
    assert client.post("/api/auth/login", json={"password": "mala"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_login_throttle(client):
    from app.api.routes import auth as auth_routes

    auth_routes._throttle.reset("testclient")
    for _ in range(5):
        client.post("/api/auth/login", json={"password": "mala"})
    assert client.post("/api/auth/login", json={"password": "mala"}).status_code == 429
    auth_routes._throttle.reset("testclient")


def test_create_update_delete(client, auth):
    created = client.post(
        "/api/journals",
        headers=auth,
        json={
            "title": "Nueva Revista",
            "issn_electronic": "4444-4444",
            "apc_text": "~USD 1200",
            "time_text": "2-4 semanas",
            "quartile": "Q2",
            "topics": ["Robótica y Automatización"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["apc_usd"] == 1200.0 and body["apc_status"] == "con_costo"
    assert body["weeks_to_publication"] == 3.0 and body["origin"] == "manual"
    assert body["locally_modified"] is True

    patched = client.patch(
        f"/api/journals/{body['id']}",
        headers=auth,
        json={"apc_usd": 0, "topics": ["Redes Sociales", "redes sociales"], "country": "Chile"},
    )
    assert patched.status_code == 200
    assert patched.json()["apc_status"] == "sin_costo"
    assert patched.json()["topics"] == ["Redes Sociales"]
    found = client.get("/api/journals", params={"q": "chile"}).json()
    assert found["total"] == 1

    assert client.delete(f"/api/journals/{body['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/journals/{body['id']}").status_code == 404


def test_patch_text_reparses_number(client, auth, catalog):
    jid = catalog[1].id
    res = client.patch(f"/api/journals/{jid}", headers=auth, json={"apc_text": "~USD 3000"})
    assert res.json()["apc_usd"] == 3000.0


def test_validation(client, auth):
    assert client.post("/api/journals", headers=auth, json={"title": ""}).status_code == 422
    assert (
        client.post(
            "/api/journals", headers=auth, json={"title": "A", "quartile": "Q9"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/journals", headers=auth, json={"title": "A", "apc_usd": -1}).status_code
        == 422
    )
    assert (
        client.post("/api/journals", headers=auth, json={"title": "A", "x": 1}).status_code == 422
    )
    res = client.post("/api/journals", headers=auth, json={"title": "A", "issn_print": "abc"})
    assert res.status_code == 422


def test_duplicate_issn_requires_force(client, auth, catalog):
    payload = {"title": "Copia", "issn_electronic": "1111-1111"}
    conflict = client.post("/api/journals", headers=auth, json=payload)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "duplicate_issn"
    assert client.post("/api/journals?force=true", headers=auth, json=payload).status_code == 201


def test_import_csv_flow(client, auth, db):
    make_journal(db, title="Ya Existe", issn_electronic="5555-5555")
    csv_text = (
        "Nombre,Indexación,ISSN Electrónico,Acceso,Costo,Cuanto demora en publicar?\n"
        "Revista CSV 1,Q1,6666-6666,Open Access,~USD 900,1–2 meses\n"
        "Ya Existe Otra Vez,Q2,5555-5555,Híbrido,~USD 100,\n"
        "500,,,,,\n"
    )
    files = lambda: {"file": ("revistas.csv", io.BytesIO(csv_text.encode()), "text/csv")}  # noqa: E731
    dry = client.post("/api/journals/import", headers=auth, files=files()).json()
    assert dry["dry_run"] and dry["rows"] == 3 and dry["invalid"] == 1
    assert dry["skipped"] == 1 and dry["created"] == 1 and len(dry["duplicates"]) == 1
    assert client.get("/api/journals", params={"q": "csv"}).json()["total"] == 0  # no escribió

    done = client.post(
        "/api/journals/import",
        headers=auth,
        files=files(),
        params={"dry_run": "false", "mode": "update"},
    ).json()
    assert done["created"] == 1 and done["updated"] == 1
    csv_journal = client.get("/api/journals", params={"q": "csv"}).json()["items"][0]
    assert csv_journal["apc_usd"] == 900.0 and csv_journal["weeks_to_publication"] == 6.5


def test_import_rejects_bad_files(client, auth):
    no_name = io.BytesIO(b"Foo,Bar\n1,2\n")
    res = client.post("/api/journals/import", headers=auth, files={"file": ("x.csv", no_name)})
    assert res.status_code == 422
    not_utf8 = io.BytesIO("Nombre\nÁrea".encode("latin-1"))
    res = client.post("/api/journals/import", headers=auth, files={"file": ("x.csv", not_utf8)})
    assert res.status_code == 422
    res = client.post("/api/journals/import", files={"file": ("x.csv", io.BytesIO(b"Nombre\nA"))})
    assert res.status_code == 401


def test_only_manual_journals_can_be_deleted(client, auth, db):
    from app.services import journals as service

    seeded = service.create_journal(db, {"title": "Del ETL"}, origin="manual")
    seeded.origin = "etl"
    db.commit()
    res = client.delete(f"/api/journals/{seeded.id}", headers=auth)
    assert res.status_code == 409


def test_duplicate_check_sees_alias_issns(client, auth, db):
    from app.services import journals as service

    journal = service.create_journal(db, {"title": "Con alias"})
    service.apply_values(db, journal, {"issn_aliases": ["7777-7777"]})
    db.commit()
    res = client.post("/api/journals", headers=auth, json={"title": "X", "issn_print": "7777-7777"})
    assert res.status_code == 409
