"""RCO-04 : pièces demandées au client, envoi par le portail, dépôt, relances."""

import datetime as dt

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401

PDF = b"%PDF-1.4\n%test\n"


def test_rco04_pieces(client, cabinet, db):  # noqa: F811
    from app.cabinet.pieces import send_piece_reminders
    from app.models import PieceRequest

    expert, collab, contact = cabinet["expert"], cabinet["collab"], cabinet["contact"]
    c = new_client(client, cabinet, taille="tpe")
    closing = open_closing(client, cabinet, c)
    url = f"/api/closings/{closing['id']}/pieces"
    limit = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    data = client.post(
        f"{url}/standard", json={"date_limite": limit}, headers=collab.headers
    ).json()
    n = len(data["pieces"])
    assert n == 8 and data["totaux"]["a_envoyer"] == 8  # liste type d'une très petite entreprise
    assert (
        len(
            client.post(
                f"{url}/standard", json={"date_limite": limit}, headers=collab.headers
            ).json()["pieces"]
        )
        == n
    )
    data = client.post(url, json={"libelle": "Bail commercial", "categorie": "juridique", "date_limite": limit},
                       headers=collab.headers).json()  # fmt: skip
    assert client.get("/api/portal/pieces", headers=contact.headers).json() == []  # rien d'envoyé
    assert client.get("/api/portal/pieces", headers=collab.headers).status_code == 403
    sent = client.post(f"{url}/send", headers=collab.headers).json()
    assert sent["totaux"]["demandee"] == n + 1
    assert client.post(f"{url}/send", headers=collab.headers).status_code == 409
    portal = client.get("/api/portal/pieces", headers=contact.headers).json()
    assert len(portal) == n + 1 and portal[0]["client"] == "Boulangerie du Plateau SARL"
    # Dépôt par le client : pièce reçue, fichier téléchargeable par l'équipe et le client.
    bail = next(p for p in portal if p["libelle"] == "Bail commercial")
    resp = client.post(
        f"/api/portal/pieces/{bail['id']}/files",
        files={"file": ("bail.pdf", PDF)},
        headers=contact.headers,
    )
    assert resp.status_code == 201, resp.text
    file_id = resp.json()["id"]
    assert client.post(f"/api/portal/pieces/{bail['id']}/files", files={"file": ("x.exe", b"MZ")},
                       headers=contact.headers).status_code == 415  # fmt: skip
    data = client.get(url, headers=expert.headers).json()
    received = next(p for p in data["pieces"] if p["libelle"] == "Bail commercial")
    assert received["statut"] == "recue" and received["fichiers"][0]["nom_fichier"] == "bail.pdf"
    assert client.get(f"/api/client-files/{file_id}/content", headers=collab.headers).content == PDF
    assert (
        client.get(f"/api/client-files/{file_id}/content", headers=contact.headers).status_code
        == 200
    )
    # Pièce rouverte avec motif ; reçue hors portail.
    assert (
        client.patch(
            f"/api/pieces/{bail['id']}", json={"recue": False}, headers=collab.headers
        ).status_code
        == 422
    )
    data = client.patch(f"/api/pieces/{bail['id']}", json={"recue": False, "commentaire": "Page 3 manquante"},
                        headers=collab.headers).json()  # fmt: skip
    assert next(p for p in data["pieces"] if p["id"] == bail["id"])["statut"] == "demandee"
    assert client.delete(f"/api/pieces/{bail['id']}", headers=collab.headers).status_code == 204
    # Relances : manuelle, puis automatique après la date limite, tous les 7 jours.
    remind = client.post(f"{url}/remind", headers=collab.headers).json()
    assert all(len(p["relances"]) == 1 for p in remind["pieces"])
    later = dt.date.today() + dt.timedelta(days=11)
    assert send_piece_reminders(db, later) == n  # la relance manuelle date d'aujourd'hui : 11 jours
    assert send_piece_reminders(db, later) == 0
    assert send_piece_reminders(db, later + dt.timedelta(days=7)) == n
    db.expire_all()
    assert all(
        len(p.relances) == 3
        for p in db.query(PieceRequest).filter(PieceRequest.deleted_at.is_(None))
    )
