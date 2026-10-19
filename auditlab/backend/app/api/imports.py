"""Import de données (DAT-01) : dépôt du fichier, puis import en tâche de fond."""

import uuid
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.analytics.formats import FORMATS_BY_EXTENSION
from app.api.datasets import dataset_out, require_analyst
from app.api.deps import CurrentUser, DbSession, require
from app.api.mission_access import get_engagement
from app.config import get_settings
from app.models.data import Dataset, DatasetKind, DatasetStatus, DataSource, Upload
from app.models.user import User
from app.schemas_data import (
    DatasetOut,
    DataSourceIn,
    DataSourceOut,
    ImportIn,
    ReadOptionsIn,
    UploadOut,
)
from app.security.roles import Perm
from app.storage import TooLarge, get_storage

router = APIRouter(tags=["Import de données"])
Admin = Annotated[User, Depends(require(Perm.SETTINGS_MANAGE))]
Analyst = Annotated[User, Depends(require(Perm.DATA_ANALYZE))]


@router.get("/engagements/{engagement_id}/uploads", response_model=list[UploadOut])
def list_uploads(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[Upload]:
    """Fichiers déposés dans la mission (entrées possibles d'un script, DAT-26)."""
    from app.api.datasets import require_read

    engagement = get_engagement(db, engagement_id, user)
    require_read(engagement, user)
    return list(
        db.scalars(
            select(Upload)
            .where(Upload.engagement_id == engagement.id, Upload.deleted_at.is_(None))
            .order_by(Upload.created_at.desc())
        )
    )


@router.post("/engagements/{engagement_id}/uploads", response_model=UploadOut, status_code=201)
def upload_source(
    engagement_id: uuid.UUID, file: UploadFile, user: CurrentUser, db: DbSession
) -> Upload:
    engagement = get_engagement(db, engagement_id, user)
    require_analyst(engagement, user)
    name = PurePath(file.filename or "source").name[:255]
    fmt = FORMATS_BY_EXTENSION.get(PurePath(name).suffix.lower())
    if fmt is None:
        raise HTTPException(415, "Formats admis : CSV, TXT, Excel, JSON, Parquet, PDF")
    max_bytes = get_settings().max_import_mb * 1024 * 1024
    key = f"sources/{engagement.id}/{uuid.uuid4()}{PurePath(name).suffix.lower()}"
    try:
        stored = get_storage().put(key, file.file, max_bytes=max_bytes)
    except TooLarge as exc:
        raise HTTPException(413, "Fichier trop volumineux") from exc
    upload = Upload(
        engagement_id=engagement.id,
        nom_fichier=name,
        format=fmt,
        taille=stored.size,
        sha256=stored.sha256,
        storage_key=stored.key,
    )
    db.add(upload)
    db.commit()
    return upload


def get_upload(db: DbSession, upload_id: uuid.UUID, user: User) -> Upload:
    upload = db.scalar(select(Upload).where(Upload.id == upload_id, Upload.deleted_at.is_(None)))
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier déposé introuvable")
    get_engagement(db, upload.engagement_id, user)
    return upload


@router.post("/engagements/{engagement_id}/imports", response_model=DatasetOut, status_code=202)
def start_import(
    engagement_id: uuid.UUID, body: ImportIn, user: CurrentUser, db: DbSession
) -> DatasetOut:
    """Crée la table « en cours » et confie la lecture à la file de tâches."""
    from app.analytics.jobs import import_dataset

    engagement = get_engagement(db, engagement_id, user)
    require_analyst(engagement, user)
    if body.upload_id:
        upload = get_upload(db, body.upload_id, user)
        if upload.engagement_id != engagement.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier déposé introuvable")
        opts = body.options.model_dump() if body.options else {"format": upload.format}
        options = {"upload_id": str(upload.id), "lecture": opts}
        source = {
            "source_nom": upload.nom_fichier,
            "source_format": opts["format"],
            "source_sha256": upload.sha256,
            "source_taille": upload.taille,
            "source_storage_key": upload.storage_key,
        }
    elif body.source_id and body.requete:
        ds_source = db.get(DataSource, body.source_id)
        if ds_source is None or not ds_source.actif or ds_source.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source de données introuvable")
        from app.analytics.formats import ImportFailure
        from app.analytics.sql_source import check_query

        try:
            check_query(body.requete)
        except ImportFailure as exc:
            raise HTTPException(422, str(exc)) from exc
        options = {"source_id": str(ds_source.id), "requete": body.requete}
        source = {"source_nom": ds_source.nom, "source_format": "sql"}
    else:
        raise HTTPException(422, "Indiquez un fichier déposé ou une source et une requête")
    ds = Dataset(
        engagement_id=engagement.id,
        nom=body.nom,
        description=body.description,
        kind=DatasetKind.IMPORT.value,
        statut=DatasetStatus.EN_COURS.value,
        options=options,
        schema=[],
        totaux_controle={},
        definition={},
        **source,
    )
    db.add(ds)
    db.commit()
    import_dataset.delay(str(ds.id))
    db.refresh(ds)
    return dataset_out(ds)


@router.get("/data-sources", response_model=list[DataSourceOut])
def list_sources(_: Analyst, db: DbSession) -> list[DataSourceOut]:
    rows = db.scalars(
        select(DataSource).where(DataSource.deleted_at.is_(None)).order_by(DataSource.nom)
    )
    return [
        DataSourceOut.model_validate(r).model_copy(
            update={"dialecte": make_url(r.url).get_backend_name()}
        )
        for r in rows
    ]


@router.post("/data-sources", response_model=DataSourceOut, status_code=201)
def create_source(body: DataSourceIn, _: Admin, db: DbSession) -> DataSourceOut:
    try:
        dialect = make_url(body.url).get_backend_name()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, "Adresse de connexion invalide") from exc
    if db.scalar(select(DataSource.id).where(DataSource.nom == body.nom)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Une source porte déjà ce nom")
    source = DataSource(nom=body.nom, description=body.description, url=body.url, actif=True)
    db.add(source)
    db.commit()
    return DataSourceOut.model_validate(source).model_copy(update={"dialecte": dialect})


def _with_upload_file(upload: Upload, action):  # noqa: ANN001,ANN202
    import tempfile
    from pathlib import Path

    from app.storage import copy_to

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"source{PurePath(upload.nom_fichier).suffix.lower()}"
        copy_to(get_storage(), upload.storage_key, path)
        return action(path)


@router.post("/uploads/{upload_id}/detect")
def detect(upload_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict:
    """DAT-02 : options proposées (encodage, séparateur, types…) et aperçu correspondant."""
    from app.analytics.detect import preview, suggest
    from app.analytics.formats import ImportFailure

    upload = get_upload(db, upload_id, user)
    try:

        def run(path):  # noqa: ANN001,ANN202
            options = suggest(path, upload.format)
            return {"options": options, "apercu": preview(path, options)}

        return _with_upload_file(upload, run)
    except ImportFailure as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/uploads/{upload_id}/preview")
def preview_upload(
    upload_id: uuid.UUID, body: ReadOptionsIn, user: CurrentUser, db: DbSession
) -> dict:
    """DAT-02 : aperçu des 100 premières lignes avec les options choisies."""
    from app.analytics.detect import preview
    from app.analytics.formats import ImportFailure

    upload = get_upload(db, upload_id, user)
    try:
        return _with_upload_file(upload, lambda path: preview(path, body.model_dump()))
    except ImportFailure as exc:
        raise HTTPException(422, str(exc)) from exc
