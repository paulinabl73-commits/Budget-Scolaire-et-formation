import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.richtext import from_plain_text
from app.security.roles import Role
from tests import helpers


@pytest.fixture
def team(client, account):
    chef = account(Role.CHEF_MISSION)
    aud = account(Role.AUDITEUR)
    aud2 = account(Role.AUDITEUR)
    sup = account(Role.DIRECTEUR)
    m = helpers.mission(
        client,
        chef.headers,
        membres=[(aud.user, "auditeur"), (aud2.user, "auditeur"), (sup.user, "superviseur")],
    )
    return {
        "chef": chef,
        "aud": aud,
        "aud2": aud2,
        "sup": sup,
        "mission": m,
        "url": f"/api/engagements/{m['id']}",
    }


def ready_workpaper(client, team, acc=None):
    acc = acc or team["aud"]
    resp = client.post(
        f"{team['url']}/workpapers",
        json={
            "reference": "A-1",
            "titre": "Revue des créations",
            "travaux": from_plain_text("Tests"),
            "conclusion": "Contrôle opérant",
            "evaluation": "efficace",
        },
        headers=acc.headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def sign(client, wp, acc, kind):
    return client.post(
        f"/api/workpapers/{wp['id']}/signoffs", json={"type": kind}, headers=acc.headers
    )


def test_aud18_circuit_complet(client, team, db):
    wp = ready_workpaper(client, team)
    assert wp["statut_signature"] == "brouillon"
    assert wp["signatures_possibles"] == ["prepare"]
    assert "revu" in wp["motifs_refus"]

    resp = sign(client, wp, team["aud"], "prepare")
    assert resp.status_code == 201
    prep = resp.json()
    assert prep["user_nom"] == team["aud"].user.nom and prep["version"] == 1
    assert len(prep["hash_contenu"]) == 64 and prep["signed_at"]

    assert sign(client, wp, team["chef"], "revu").status_code == 201
    assert sign(client, wp, team["chef"], "approuve").status_code == 201
    detail = client.get(f"/api/workpapers/{wp['id']}", headers=team["aud"].headers).json()
    assert detail["statut_signature"] == "approuve"
    assert [s["type"] for s in detail["signatures"]] == ["prepare", "revu", "approuve"]
    listed = client.get(f"{team['url']}/workpapers", headers=team["aud"].headers).json()
    assert listed[0]["statut_signature"] == "approuve"
    actions = db.scalars(select(AuditLog.action).where(AuditLog.object_type == "Signoff")).all()
    assert actions == ["create", "create", "create"]


def test_aud18_ordre_et_conditions(client, team):
    resp = client.post(
        f"{team['url']}/workpapers",
        json={"reference": "A-2", "titre": "Sans conclusion"},
        headers=team["aud"].headers,
    )
    wp = resp.json()
    r = sign(client, wp, team["aud"], "prepare")
    assert r.status_code == 409 and "Conclusion" in r.json()["detail"]
    wp = ready_workpaper(client, team)
    assert sign(client, wp, team["chef"], "revu").status_code == 409  # pas encore préparé
    sign(client, wp, team["aud"], "prepare")
    assert sign(client, wp, team["aud"], "prepare").status_code == 409  # déjà signé
    assert sign(client, wp, team["chef"], "approuve").status_code == 409  # pas encore revu


def test_aud18_separation_des_taches(client, team):
    # Le chef prépare : ni lui ni un auditeur ne revoient ; le superviseur (Directeur) le peut.
    wp = ready_workpaper(client, team, acc=team["chef"])
    sign(client, wp, team["chef"], "prepare")
    r = sign(client, wp, team["chef"], "revu")
    assert r.status_code == 403 and "Séparation des tâches" in r.json()["detail"]
    r = sign(client, wp, team["aud2"], "revu")
    assert r.status_code == 403 and "chef de mission" in r.json()["detail"]
    assert sign(client, wp, team["sup"], "revu").status_code == 201
    # Approbation : pas par le préparateur ; le Directeur peut approuver.
    r = sign(client, wp, team["chef"], "approuve")
    assert r.status_code == 403 and "Séparation" in r.json()["detail"]
    assert sign(client, wp, team["sup"], "approuve").status_code == 201
    history = client.get(f"/api/workpapers/{wp['id']}/signoffs", headers=team["aud"].headers).json()
    assert [(s["type"], s["user_nom"]) for s in history] == [
        ("prepare", team["chef"].user.nom),
        ("revu", team["sup"].user.nom),
        ("approuve", team["sup"].user.nom),
    ]


def test_aud18_auditeur_ne_revoit_pas(client, team):
    wp = ready_workpaper(client, team)
    sign(client, wp, team["aud"], "prepare")
    assert sign(client, wp, team["aud2"], "revu").status_code == 403
    assert sign(client, wp, team["aud2"], "approuve").status_code == 409


def note(client, wp, acc, texte="Préciser la taille de l'échantillon", **ancre):
    return client.post(
        f"/api/workpapers/{wp['id']}/review-notes",
        json={"texte": texte, "ancre": ancre or {"champ": "travaux", "citation": "Tests"}},
        headers=acc.headers,
    )


def test_aud19_notes_de_revue(client, team):
    wp = ready_workpaper(client, team)
    resp = note(client, wp, team["chef"])
    assert resp.status_code == 201
    n = resp.json()
    assert n["statut"] == "ouverte" and n["ancre"] == {"champ": "travaux", "citation": "Tests"}
    assert n["auteur"] == team["chef"].user.nom and n["workpaper_reference"] == "A-1"

    # L'auditrice répond : la note passe à « Répondue ».
    resp = client.post(
        f"/api/review-notes/{n['id']}/replies",
        json={"texte": "Échantillon de 25 sur 312 créations"},
        headers=team["aud"].headers,
    )
    assert resp.json()["statut"] == "repondue"
    assert resp.json()["reponses"][0]["auteur"] == team["aud"].user.nom
    # Une relance du réviseur ne change pas le statut.
    resp = client.post(
        f"/api/review-notes/{n['id']}/replies",
        json={"texte": "Merci"},
        headers=team["chef"].headers,
    )
    assert resp.json()["statut"] == "repondue" and len(resp.json()["reponses"]) == 2

    # Seul un réviseur clôture ; une note clôturée n'accepte plus de réponse.
    assert (
        client.post(f"/api/review-notes/{n['id']}/close", headers=team["aud"].headers).status_code
        == 403
    )
    resp = client.post(f"/api/review-notes/{n['id']}/close", headers=team["chef"].headers)
    assert resp.json()["statut"] == "cloturee" and resp.json()["cloturee_le"]
    assert (
        client.post(
            f"/api/review-notes/{n['id']}/replies", json={"texte": "x"}, headers=team["aud"].headers
        ).status_code
        == 409
    )
    resp = client.post(f"/api/review-notes/{n['id']}/reopen", headers=team["chef"].headers)
    assert resp.json()["statut"] == "ouverte"

    listed = client.get(f"{team['url']}/review-notes?statut=ouverte", headers=team["aud"].headers)
    assert [x["id"] for x in listed.json()] == [n["id"]]
    assert (
        len(
            client.get(
                f"/api/workpapers/{wp['id']}/review-notes", headers=team["aud"].headers
            ).json()
        )
        == 1
    )


def test_aud19_droits_et_ancre(client, team, account):
    wp = ready_workpaper(client, team)
    assert note(client, wp, team["aud"]).status_code == 403  # un auditeur ne crée pas de note
    assert note(client, wp, team["sup"]).status_code == 201  # le superviseur oui
    assert note(client, wp, team["chef"], champ="inconnu").status_code == 422
    assert note(client, wp, team["chef"], champ="conclusion").status_code == 201
    import uuid

    assert (
        client.post(
            f"/api/review-notes/{uuid.uuid4()}/close", headers=team["chef"].headers
        ).status_code
        == 404
    )
    outsider = account(Role.AUDITEUR)
    n = note(client, wp, team["chef"]).json()
    assert (
        client.post(
            f"/api/review-notes/{n['id']}/replies", json={"texte": "x"}, headers=outsider.headers
        ).status_code
        == 404
    )


def test_aud19_approbation_bloquee_par_les_notes(client, team):
    wp = ready_workpaper(client, team)
    sign(client, wp, team["aud"], "prepare")
    sign(client, wp, team["chef"], "revu")
    n = note(client, wp, team["chef"]).json()
    r = sign(client, wp, team["chef"], "approuve")
    assert r.status_code == 409 and "note(s) de revue" in r.json()["detail"]
    client.post(f"/api/review-notes/{n['id']}/close", headers=team["chef"].headers)
    assert sign(client, wp, team["chef"], "approuve").status_code == 201


def test_aud20_modification_apres_signature(client, team, db):
    from sqlalchemy import select

    from app.models import EmailMessage

    wp = ready_workpaper(client, team)
    sign(client, wp, team["aud"], "prepare")
    sign(client, wp, team["chef"], "revu")
    resp = client.patch(
        f"/api/workpapers/{wp['id']}",
        json={"conclusion": "Contrôle non opérant"},
        headers=team["aud"].headers,
    )
    detail = resp.json()
    assert detail["statut_signature"] == "brouillon" and detail["signatures"] == []
    history = client.get(f"/api/workpapers/{wp['id']}/signoffs", headers=team["aud"].headers).json()
    assert all(s["annule_le"] for s in history)
    assert history[0]["motif_annulation"] == "version 2 enregistrée"

    # Le réviseur (chef de mission) est notifié, dans l'application et par e-mail.
    notes = client.get("/api/me/notifications", headers=team["chef"].headers).json()
    assert notes["non_lues"] == 1
    n = notes["items"][0]
    assert n["type"] == "signature_annulee" and "A-1" in n["titre"]
    assert n["lien"] == f"/missions/{team['mission']['id']}/papiers/{wp['id']}"
    mail = db.scalar(
        select(EmailMessage).where(EmailMessage.destinataire == team["chef"].user.email)
    )
    assert mail.statut == "en_attente" and "A-1" in mail.sujet
    # L'auteur de la modification n'est pas notifié.
    assert client.get("/api/me/notifications", headers=team["aud"].headers).json()["non_lues"] == 0

    assert (
        client.post(
            f"/api/me/notifications/{n['id']}/read", headers=team["chef"].headers
        ).status_code
        == 204
    )
    assert client.get("/api/me/notifications", headers=team["chef"].headers).json()["non_lues"] == 0
    assert (
        client.post(
            f"/api/me/notifications/{n['id']}/read", headers=team["aud"].headers
        ).status_code
        == 404
    )

    # Nouvelle signature possible sur la nouvelle version.
    resp = sign(client, wp, team["aud"], "prepare")
    assert resp.status_code == 201 and resp.json()["version"] == 2


def test_aud20_piece_jointe_apres_signature(client, team):
    from tests.test_attachments import PDF, upload

    wp = ready_workpaper(client, team)
    sign(client, wp, team["aud"], "prepare")
    a = upload(client, wp, team["aud"]).json()
    assert (
        client.get(f"/api/workpapers/{wp['id']}", headers=team["aud"].headers).json()[
            "statut_signature"
        ]
        == "brouillon"
    )
    sign(client, wp, team["aud"], "prepare")
    client.delete(f"/api/attachments/{a['id']}", headers=team["aud"].headers)
    history = client.get(f"/api/workpapers/{wp['id']}/signoffs", headers=team["aud"].headers).json()
    assert [s["motif_annulation"] for s in history] == [
        "pièce jointe « facture.pdf » ajoutée",
        "pièce jointe « facture.pdf » retirée",
    ]
    assert PDF
    client.post("/api/me/notifications/read-all", headers=team["chef"].headers)
    assert client.get("/api/me/notifications", headers=team["chef"].headers).json()["non_lues"] == 0


def test_envoi_des_emails(db, monkeypatch):
    from app.config import get_settings
    from app.models import EmailMessage
    from app.notify import send_pending

    db.add(
        EmailMessage(
            destinataire="a@exemple.org",
            sujet="Test",
            corps="Bonjour",
            statut="en_attente",
            tentatives=0,
        )
    )
    db.commit()
    assert send_pending(db) == 0  # pas de serveur SMTP configuré

    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg["To"])

    monkeypatch.setattr("app.notify.smtplib.SMTP", FakeSMTP)
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.exemple.org")
    monkeypatch.setattr(settings, "smtp_user", "auditlab")
    assert send_pending(db) == 1 and sent == ["a@exemple.org"]
    db.expire_all()
    assert db.query(EmailMessage).one().statut == "envoye"
    from app.cli import main

    assert main(["send-emails"]) == 0


def test_aud21_passage_en_rapport(client, team):
    url = team["url"]
    for statut in ("preparation", "terrain", "revue"):
        client.post(f"{url}/status", json={"statut": statut}, headers=team["chef"].headers)
    wp = ready_workpaper(client, team)
    n = note(client, wp, team["chef"]).json()
    mission = client.get(url, headers=team["chef"].headers).json()
    nxt = next(t for t in mission["transitions"] if t["statut"] == "rapport")
    assert nxt["motif_blocage"] == "1 note(s) de revue non clôturée(s) dans la mission"
    r = client.post(f"{url}/status", json={"statut": "rapport"}, headers=team["chef"].headers)
    assert r.status_code == 409 and "note(s) de revue" in r.json()["detail"]
    # Une note répondue ne suffit pas : elle doit être clôturée.
    client.post(
        f"/api/review-notes/{n['id']}/replies", json={"texte": "Fait"}, headers=team["aud"].headers
    )
    assert (
        client.post(
            f"{url}/status", json={"statut": "rapport"}, headers=team["chef"].headers
        ).status_code
        == 409
    )
    client.post(f"/api/review-notes/{n['id']}/close", headers=team["chef"].headers)
    assert (
        client.post(
            f"{url}/status", json={"statut": "rapport"}, headers=team["chef"].headers
        ).status_code
        == 200
    )


def _to_rapport(client, team):
    for statut in ("preparation", "terrain", "revue", "rapport"):
        assert (
            client.post(
                f"{team['url']}/status", json={"statut": statut}, headers=team["chef"].headers
            ).status_code
            == 200
        )


def test_aud22_cloture_et_verrouillage(client, team, db):
    from app.models import Engagement

    e = helpers.entity(client, team["sup"].headers, "Achats", date_dernier_audit="2023-01-31")
    db.query(Engagement).filter_by(id=team["mission"]["id"]).update({"entity_id": e["id"]})
    db.commit()
    wp = ready_workpaper(client, team)
    t_url = f"{team['url']}/time-entries"
    client.post(
        t_url,
        json={"date": "2026-09-01", "heures": 4, "activite": "terrain"},
        headers=team["aud"].headers,
    )
    _to_rapport(client, team)

    helpers.diffused_report(db, team["mission"]["id"])  # REP-03
    # Clôture refusée tant que les papiers ne sont pas approuvés.
    mission = client.get(team["url"], headers=team["chef"].headers).json()
    blocked = next(t for t in mission["transitions"] if t["statut"] == "cloturee")
    assert blocked["motif_blocage"] == "Papiers de travail non approuvés : A-1"
    sign(client, wp, team["aud"], "prepare")
    sign(client, wp, team["chef"], "revu")
    sign(client, wp, team["chef"], "approuve")
    resp = client.post(
        f"{team['url']}/status", json={"statut": "cloturee"}, headers=team["chef"].headers
    )
    assert resp.status_code == 200 and resp.json()["cloturee_le"]
    # La date du dernier audit de l'entité devient la fin de la mission.
    assert (
        client.get(f"/api/universe/entities/{e['id']}", headers=team["sup"].headers).json()[
            "date_dernier_audit"
        ]
        == "2027-03-31"
    )

    # Plus aucune modification, quelle que soit la route.
    h = team["aud"].headers
    assert (
        client.patch(f"/api/workpapers/{wp['id']}", json={"titre": "X"}, headers=h).status_code
        == 409
    )
    assert (
        client.post(
            f"{team['url']}/workpapers", json={"reference": "Z-1", "titre": "x"}, headers=h
        ).status_code
        == 409
    )
    assert (
        client.post(
            t_url, json={"date": "2026-09-02", "heures": 1, "activite": "rapport"}, headers=h
        ).status_code
        == 409
    )
    assert note(client, wp, team["chef"]).status_code == 409
    assert (
        client.post(
            f"{team['url']}/risks",
            json={"libelle": "x", "cycle": "achats", "categorie": "fraude"},
            headers=team["chef"].headers,
        ).status_code
        == 409
    )
    # Consultation toujours possible.
    assert client.get(f"/api/workpapers/{wp['id']}", headers=h).status_code == 200
    assert client.get(f"/api/workpapers/{wp['id']}/versions", headers=h).status_code == 200


def test_aud22_verrou_au_niveau_des_donnees(client, team, db):
    """Même une écriture qui contournerait l'API est refusée."""
    from app.audit.listeners import AuditIntegrityError, set_actor
    from app.models import Workpaper

    wp = ready_workpaper(client, team)
    sign(client, wp, team["aud"], "prepare")
    sign(client, wp, team["chef"], "revu")
    sign(client, wp, team["chef"], "approuve")
    _to_rapport(client, team)
    helpers.diffused_report(db, team["mission"]["id"])  # REP-03
    client.post(f"{team['url']}/status", json={"statut": "cloturee"}, headers=team["chef"].headers)
    set_actor(db, team["chef"].user.id)
    paper = db.get(Workpaper, wp["id"])
    paper.titre = "Falsifié"
    with pytest.raises(AuditIntegrityError, match="clôturée"):
        db.flush()
    db.rollback()
