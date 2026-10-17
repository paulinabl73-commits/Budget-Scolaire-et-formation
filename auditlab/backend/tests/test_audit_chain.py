import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit.chain import GENESIS_HASH, compute_hash, verify_chain
from app.audit.listeners import AuditIntegrityError, record_event, set_actor
from app.cli import main as cli_main
from app.db import engine
from app.models import AuditLog, Team
from app.security.roles import Role


def _entries(db):
    return db.scalars(select(AuditLog).order_by(AuditLog.seq)).all()


def test_creation_journalisee_et_chainee(db, make_user):
    admin = make_user(Role.ADMIN)
    set_actor(db, admin.id)
    db.add(Team(nom="Équipe Achats"))
    record_event(db, "custom", details={"montant": 1250.5})
    db.commit()

    entries = _entries(db)
    assert [e.seq for e in entries] == list(range(1, len(entries) + 1))
    assert entries[0].hash_precedent == GENESIS_HASH
    for prev, cur in zip(entries, entries[1:], strict=False):
        assert cur.hash_precedent == prev.hash
    team_entry = next(e for e in entries if e.object_type == "Team")
    assert team_entry.action == "create"
    assert team_entry.user_id == admin.id
    assert team_entry.apres["nom"] == "Équipe Achats"
    report = verify_chain(db)
    assert report.ok and report.entries == len(entries)


def test_modification_journalise_avant_apres_et_masque_les_secrets(db, make_user):
    user = make_user(Role.AUDITEUR)
    creation = db.scalar(select(AuditLog).where(AuditLog.object_id == str(user.id)))
    assert creation.apres["password_hash"] == "***"

    set_actor(db, user.id)
    user.nom = "Nouveau nom"
    user.password_hash = "autre"
    db.commit()
    entry = db.scalar(
        select(AuditLog).where(AuditLog.action == "update").order_by(AuditLog.seq.desc())
    )
    assert entry.avant == {"nom": "Utilisateur auditeur", "password_hash": "***"}
    assert entry.apres == {"nom": "Nouveau nom", "password_hash": "***"}
    assert user.updated_by == user.id


def test_suppression_physique_interdite(db, make_user):
    user = make_user()
    db.delete(user)
    with pytest.raises(AuditIntegrityError):
        db.flush()
    db.rollback()


def test_modification_orm_du_journal_interdite(db, make_user):
    make_user()
    entry = _entries(db)[0]
    entry.action = "falsifie"
    with pytest.raises(AuditIntegrityError):
        db.flush()
    db.rollback()


@pytest.mark.parametrize(
    "sql",
    ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log", "TRUNCATE audit_log"],
)
def test_base_refuse_toute_alteration(make_user, sql):
    make_user()
    with pytest.raises(DBAPIError, match="ajout seul"), engine.begin() as conn:
        conn.execute(text(sql))


def _tamper(sql):
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text(sql))


def test_verification_detecte_une_falsification(db, make_user):
    make_user(Role.AUDITEUR)
    make_user(Role.DATA_ANALYST)
    assert verify_chain(db).ok
    _tamper('UPDATE audit_log SET apres = \'{"nom": "pirate"}\' WHERE seq = 2')
    report = verify_chain(db)
    assert not report.ok
    assert report.first_broken_seq == 2
    assert report.reason == "contenu modifié"


def test_verification_detecte_une_suppression(db, make_user):
    make_user(Role.AUDITEUR)
    make_user(Role.DATA_ANALYST)
    make_user(Role.CHEF_MISSION)
    _tamper("DELETE FROM audit_log WHERE seq = 2")
    report = verify_chain(db)
    assert (report.ok, report.first_broken_seq, report.reason) == (False, 2, "entrée manquante")


def test_verification_detecte_un_lien_rompu(db, make_user):
    make_user(Role.AUDITEUR)
    make_user(Role.DATA_ANALYST)
    entry = _entries(db)[1]
    entry_hash = entry.hash
    db.expunge_all()
    # Réécrit une entrée de façon cohérente avec elle-même mais pas avec la précédente.
    forged = AuditLog(
        **{
            c: getattr(entry, c)
            for c in (
                "id",
                "seq",
                "horodatage",
                "user_id",
                "action",
                "object_type",
                "object_id",
                "avant",
                "apres",
            )
        }
    )
    forged.hash_precedent = "f" * 64
    new_hash = compute_hash(forged)
    _tamper(
        f"UPDATE audit_log SET hash_precedent = '{'f' * 64}', hash = '{new_hash}' "
        f"WHERE hash = '{entry_hash}'"
    )
    report = verify_chain(db)
    assert (report.ok, report.first_broken_seq) == (False, 2)
    assert report.reason == "lien vers l'entrée précédente rompu"


def test_verification_par_lots(db, make_user):
    for role in Role:
        make_user(role)
    assert verify_chain(db, batch_size=2).ok


def test_commande_de_verification(make_user, capsys):
    make_user()
    assert cli_main(["verify-audit-chain"]) == 0
    assert "intègre" in capsys.readouterr().out
    _tamper("UPDATE audit_log SET action = 'x' WHERE seq = 1")
    assert cli_main(["verify-audit-chain"]) == 1
    assert "RUPTURE" in capsys.readouterr().err
