"""RCO-06 : documents permanents expirés signalés à l'ouverture de l'exercice."""

import datetime as dt

from sqlalchemy import select

from tests.portfolio_helpers import cabinet, new_client  # noqa: F401


def test_rco06_documents_expires(client, cabinet, db):  # noqa: F811
    from app.models import Notification

    expert, collab = cabinet["expert"], cabinet["collab"]
    c = new_client(client, cabinet)
    url = f"/api/clients/{c['id']}/permanent"
    today = dt.date.today()
    for libelle, validite in (("Attestation de régularité fiscale", today - dt.timedelta(days=10)),
                              ("Bail du siège", today + dt.timedelta(days=400)), ("Statuts", None)):  # fmt: skip
        data = {"categorie": "autre", "libelle": libelle}
        if validite:
            data["date_validite"] = validite.isoformat()
        client.post(url, data=data, headers=collab.headers)
    docs = {d["libelle"]: d["expire"] for d in client.get(url, headers=expert.headers).json()}
    assert docs == {
        "Attestation de régularité fiscale": True,
        "Bail du siège": False,
        "Statuts": False,
    }
    # À l'ouverture d'un exercice qui se termine après la fin de validité du bail, il est signalé.
    year = (today + dt.timedelta(days=400)).year + 1
    resp = client.post(
        f"/api/clients/{c['id']}/closings", json={"exercice": year}, headers=expert.headers
    ).json()
    assert [d["libelle"] for d in resp["documents_expires"]] == [
        "Attestation de régularité fiscale",
        "Bail du siège",
    ]
    note = db.scalar(select(Notification).where(Notification.user_id == collab.user.id,
                                                Notification.type == "documents_expires"))  # fmt: skip
    assert note is not None and "Bail du siège" in note.message
    board = client.get("/api/portfolio/dashboard", headers=expert.headers).json()
    assert board["dossiers"][0]["documents_expires"] == 1
