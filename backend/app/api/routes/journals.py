from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.api.deps import AdminDep, DbSession, SettingsDep
from app.models import Journal
from app.schemas.journal import (
    Facets,
    ImportReport,
    JournalCreate,
    JournalDetail,
    JournalPage,
    JournalUpdate,
)
from app.services import importer
from app.services import journals as service
from app.services.journals import SORT_COLUMNS, JournalFilters

router = APIRouter(prefix="/journals", tags=["revistas"])

Multi = Annotated[list[str] | None, Query()]


def _filters(
    q: Annotated[str | None, Query(max_length=200)] = None,
    topic: Multi = None,
    quartile: Multi = None,
    access: Multi = None,
    country: Multi = None,
    language: Multi = None,
    format: Multi = None,  # noqa: A002 - nombre público del parámetro
    publindex: Multi = None,
    origin: Multi = None,
    apc_status: Annotated[Literal["sin_costo", "con_costo", "desconocido"] | None, Query()] = None,
    apc_min: Annotated[float | None, Query(ge=0)] = None,
    apc_max: Annotated[float | None, Query(ge=0)] = None,
    weeks_max: Annotated[float | None, Query(ge=0)] = None,
    h_index_min: Annotated[int | None, Query(ge=0)] = None,
    sjr_min: Annotated[float | None, Query(ge=0)] = None,
    citescore_min: Annotated[float | None, Query(ge=0)] = None,
    impact_factor_min: Annotated[float | None, Query(ge=0)] = None,
    quality_min: Annotated[float | None, Query(ge=0, le=1)] = None,
) -> JournalFilters:
    return JournalFilters(
        q=q,
        topics=topic or [],
        quartiles=quartile or [],
        access_types=access or [],
        countries=country or [],
        languages=language or [],
        submission_formats=format or [],
        publindex_categories=publindex or [],
        origins=origin or [],
        apc_status=apc_status,
        apc_min=apc_min,
        apc_max=apc_max,
        weeks_max=weeks_max,
        h_index_min=h_index_min,
        sjr_min=sjr_min,
        citescore_min=citescore_min,
        impact_factor_min=impact_factor_min,
        quality_min=quality_min,
    )


Filters = Annotated[JournalFilters, Depends(_filters)]


@router.get("", response_model=JournalPage)
def list_journals(
    db: DbSession,
    filters: Filters,
    sort: Annotated[str, Query(pattern="^(" + "|".join(SORT_COLUMNS) + ")$")] = "title",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
) -> JournalPage:
    items, total = service.list_journals(db, filters, sort, order == "desc", page, page_size)
    return JournalPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/facets", response_model=Facets)
def facets(db: DbSession) -> dict:
    return service.build_facets(db)


@router.post("/import", response_model=ImportReport, dependencies=[AdminDep])
async def import_csv(
    db: DbSession,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    mode: Annotated[Literal["skip", "update", "add"], Query()] = "skip",
    dry_run: Annotated[bool, Query()] = True,
) -> ImportReport:
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Archivo demasiado grande")
    try:
        rows = importer.parse_csv(content)
    except importer.CsvFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    return importer.import_rows(db, rows, mode=mode, dry_run=dry_run)


def _get_or_404(db: DbSession, journal_id: int) -> Journal:
    journal = db.get(Journal, journal_id)
    if journal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revista no encontrada")
    return journal


def _check_duplicates(
    db: DbSession, values: dict, force: bool, exclude_id: int | None = None
) -> None:
    from app.services.normalizers import normalize_issn

    issns = [
        normalize_issn(values.get("issn_print")),
        normalize_issn(values.get("issn_electronic")),
    ]
    duplicates = service.find_issn_duplicates(db, issns, exclude_id)
    if duplicates and not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_issn",
                "message": "Ya existe una revista con el mismo ISSN",
                "journals": [{"id": j.id, "title": j.title} for j in duplicates[:5]],
            },
        )


def _normalize_issns(values: dict) -> dict:
    from app.services.normalizers import normalize_issn

    for key in ("issn_print", "issn_electronic"):
        if key in values and values[key] is not None:
            normalized = normalize_issn(values[key])
            if normalized is None:
                raise HTTPException(422, f"{key}: formato esperado NNNN-NNNN")
            values[key] = normalized
    return values


@router.get("/{journal_id}", response_model=JournalDetail)
def get_journal(db: DbSession, journal_id: int) -> Journal:
    return _get_or_404(db, journal_id)


@router.post(
    "", response_model=JournalDetail, status_code=status.HTTP_201_CREATED, dependencies=[AdminDep]
)
def create_journal(
    db: DbSession, body: JournalCreate, force: Annotated[bool, Query()] = False
) -> Journal:
    values = _normalize_issns(body.model_dump(exclude_unset=True))
    _check_duplicates(db, values, force)
    return service.create_journal(db, values)


@router.patch("/{journal_id}", response_model=JournalDetail, dependencies=[AdminDep])
def update_journal(
    db: DbSession, journal_id: int, body: JournalUpdate, force: Annotated[bool, Query()] = False
) -> Journal:
    journal = _get_or_404(db, journal_id)
    values = _normalize_issns(body.model_dump(exclude_unset=True))
    _check_duplicates(db, values, force, exclude_id=journal.id)
    return service.update_journal(db, journal, values)


@router.delete("/{journal_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminDep])
def delete_journal(db: DbSession, journal_id: int) -> None:
    journal = _get_or_404(db, journal_id)
    if journal.origin != "manual":
        # Las revistas del ETL/LIDER volverían a aparecer en el siguiente seed.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Solo se pueden eliminar revistas agregadas manualmente; las demás se editan.",
        )
    db.delete(journal)
    db.commit()
