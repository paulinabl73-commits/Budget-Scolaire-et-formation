"""Import des données comptables d'un dossier de révision (REV-05) et reprise N-1 (REV-04).

Une balance acceptée remplace la précédente de même période et de même type (suppression
logique) ; une balance rejetée par un contrôle bloquant (REV-06) est conservée avec ses
anomalies mais n'est jamais utilisée.
"""

import datetime as dt
import hashlib
import io
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models.data import Dataset, DatasetStatus
from app.models.revision import AuditFile, TrialBalance, TrialBalanceLine
from app.revision.balances import (
    AMOUNTS,
    BalanceLine,
    ImportError_,
    locate,
    parse_balance,
    parse_ledger,
    read_rows,
)
from app.storage import get_storage

TYPES = ("balance", "grand_livre", "aux_clients", "aux_fournisseurs", "aux_cotisants",
         "aux_allocataires")  # fmt: skip
LOGICIELS = ("generique", "sage", "odoo", "perfecto", "saari")


@dataclass
class ImportRequest:
    periode: str
    type: str
    logiciel: str = "generique"
    correspondance: dict[str, str] | None = None
    compte_collectif: str | None = None
    devise_source: str | None = None
    date_cours: dt.date | None = None
    journaux_a_nouveaux: tuple[str, ...] = ("AN", "RAN", "ANO", "ANX")


@dataclass
class Parsed:
    """Contenu lu, soumis aux contrôles et aux conversions avant enregistrement."""

    request: ImportRequest
    file: AuditFile
    lines: list[BalanceLine] = field(default_factory=list)
    ledger: Any = None  # DataFrame Polars du grand livre
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    avertissements: list[dict[str, Any]] = field(default_factory=list)
    cours: Decimal | None = None
    # Écart supplémentaire toléré par les contrôles (arrondis de conversion, REV-07).
    tolerance: Decimal = Decimal(0)


# Étapes ajoutées par les exigences suivantes : conversion de devise (REV-07), contrôles (REV-06).
PREPARE: list[Callable[[Session, Parsed], None]] = []
CONTROLS: list[Callable[[Session, Parsed], None]] = []


def active_balance(
    db: Session, file_id: uuid.UUID, periode: str, type_: str = "balance"
) -> TrialBalance | None:
    return db.scalar(
        select(TrialBalance).where(
            TrialBalance.audit_file_id == file_id,
            TrialBalance.periode == periode,
            TrialBalance.type == type_,
            TrialBalance.statut == "accepte",
            TrialBalance.deleted_at.is_(None),
        )
    )


def balance_lines(db: Session, tb: TrialBalance | None) -> list[BalanceLine]:
    if tb is None:
        return []
    rows = db.scalars(
        select(TrialBalanceLine)
        .where(TrialBalanceLine.trial_balance_id == tb.id)
        .order_by(TrialBalanceLine.compte)
    )
    return [BalanceLine(r.compte, r.libelle, {k: getattr(r, k) for k in AMOUNTS}) for r in rows]


def totals(lines: list[BalanceLine]) -> dict[str, str]:
    return {k: str(sum((ln.amounts[k] for ln in lines), Decimal(0))) for k in AMOUNTS}


def _save(
    db: Session, file: AuditFile, parsed: Parsed, meta: dict[str, Any], user_id: uuid.UUID | None
) -> TrialBalance:
    req = parsed.request
    accepted = not parsed.anomalies
    tb = TrialBalance(
        engagement_id=file.engagement_id,
        audit_file_id=file.id,
        periode=req.periode,
        type=req.type,
        logiciel=req.logiciel,
        statut="accepte" if accepted else "rejete",
        anomalies=parsed.anomalies,
        avertissements=parsed.avertissements,
        devise_source=req.devise_source,
        cours=parsed.cours,
        compte_collectif=req.compte_collectif,
        **meta,
    )
    if parsed.ledger is not None:
        tb.nb_lignes = parsed.ledger.height
        tb.totaux = {
            "debit": str(parsed.ledger["debit"].sum()),
            "credit": str(parsed.ledger["credit"].sum()),
            "ecritures": parsed.ledger.height,
        }
    else:
        tb.nb_lignes = len(parsed.lines)
        tb.totaux = totals(parsed.lines)
    if accepted:
        previous = active_balance(db, file.id, req.periode, req.type)
        if previous is not None:
            previous.deleted_at, previous.deleted_by = dt.datetime.now(dt.UTC), user_id
    db.add(tb)
    db.flush()
    if parsed.ledger is not None and accepted:
        tb.dataset_id = _ledger_dataset(db, file, tb, parsed.ledger).id
    elif parsed.lines:
        db.execute(
            insert(TrialBalanceLine),
            [{"id": uuid.uuid4(), "trial_balance_id": tb.id, "compte": ln.compte,
              "libelle": ln.libelle, **ln.amounts} for ln in parsed.lines],
        )  # fmt: skip
    return tb


def _ledger_dataset(db: Session, file: AuditFile, tb: TrialBalance, df: Any) -> Dataset:
    """Le grand livre devient une table du Module 2 (tests d'écritures, REV-17)."""
    from app.analytics.lineage import record_operation
    from app.analytics.store import control_totals, file_sha256, write_table

    written = write_table(df, file.engagement_id)
    ds = Dataset(
        engagement_id=file.engagement_id,
        nom=f"Grand livre {tb.periode} – exercice {file.exercice}",
        kind="import",
        statut=DatasetStatus.PRET.value,
        source_nom=tb.nom_fichier,
        source_format="grand_livre",
        source_sha256=tb.sha256,
        source_storage_key=tb.storage_key,
        chemin_parquet=written.chemin,
        nb_lignes=written.nb_lignes,
        nb_colonnes=written.nb_colonnes,
        schema=written.schema,
        totaux_controle=control_totals(written.chemin, written.schema),
        parquet_sha256=file_sha256(written.chemin),
        options={"audit_file_id": str(file.id), "trial_balance_id": str(tb.id)},
        definition={},
    )
    db.add(ds)
    db.flush()
    record_operation(db, ds, "import", {"grand_livre": str(tb.id)}, [])
    return ds


def import_file(
    db: Session, file: AuditFile, content: bytes, filename: str, req: ImportRequest,
    user_id: uuid.UUID | None,
) -> TrialBalance:  # fmt: skip
    if req.type not in TYPES or req.periode not in ("N", "N-1") or req.logiciel not in LOGICIELS:
        raise ImportError_("Type, période ou logiciel inconnu")
    if req.type == "grand_livre" and req.periode != "N":
        raise ImportError_("Le grand livre importé est celui de l'exercice N")
    if req.type.startswith("aux_") and not (req.compte_collectif or "").isdigit():
        raise ImportError_("Indiquez le compte collectif de la balance auxiliaire (ex. 411)")
    rows = read_rows(content, filename)
    kind = "grand_livre" if req.type == "grand_livre" else "balance"
    table = locate(rows, kind, req.correspondance)
    parsed = Parsed(req, file)
    if kind == "grand_livre":
        parsed.ledger = parse_ledger(table)
    else:
        parsed.lines = parse_balance(table, digits_only=req.type == "balance")
    for step in PREPARE:
        step(db, parsed)
    for control in CONTROLS:
        control(db, parsed)
    digest = hashlib.sha256(content).hexdigest()
    key = f"revision/{file.id}/{uuid.uuid4()}{PurePath(filename).suffix.lower()}"
    stored = get_storage().put(key, io.BytesIO(content))
    meta = {"nom_fichier": PurePath(filename).name[:255], "sha256": digest,
            "storage_key": stored.key}  # fmt: skip
    return _save(db, file, parsed, meta, user_id)


def carry_over(db: Session, file: AuditFile, previous: AuditFile) -> None:
    """REV-04 : la balance N du dossier précédent devient la balance N-1 du nouveau dossier."""
    source = active_balance(db, previous.id, "N")
    if source is None:
        return
    parsed = Parsed(ImportRequest("N-1", "balance", "generique"), file)
    parsed.lines = balance_lines(db, source)
    meta = {"nom_fichier": f"Reprise de la balance N du dossier {previous.exercice}",
            "sha256": source.sha256, "storage_key": source.storage_key}  # fmt: skip
    _save(db, file, parsed, meta, None)
