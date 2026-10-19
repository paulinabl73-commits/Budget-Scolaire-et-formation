"""RCO-02 : tableau de bord du portefeuille et étapes de la clôture."""

import datetime as dt

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401


def test_rco02_tableau_de_bord(client, cabinet, db):  # noqa: F811
    expert, collab = cabinet["expert"], cabinet["collab"]
    today = dt.date.today()
    c = new_client(client, cabinet)
    other = new_client(client, cabinet, raison_sociale="Pharmacie des Lagunes")
    closing = open_closing(client, cabinet, c, today.year - 1)
    url = f"/api/closings/{closing['id']}/stage"
    assert client.put(url, json={"etape": "revision"}, headers=collab.headers).status_code == 409
    for stage in ("saisie", "revision", "revue"):
        assert (
            client.put(url, json={"etape": stage}, headers=collab.headers).json()["etape"] == stage
        )
    assert client.put(url, json={"etape": "depot"}, headers=collab.headers).status_code == 403
    # RCO-23 : le dépôt suit le visa de revue de l'expert-comptable.
    assert client.put(url, json={"etape": "depot"}, headers=expert.headers).status_code == 409
    review = client.post(
        f"/api/closings/{closing['id']}/review", json={"niveau": "expert"}, headers=expert.headers
    )
    assert review.status_code == 200, review.text
    deposit = (today - dt.timedelta(days=1)).isoformat()
    done = client.put(url, json={"etape": "depot", "date": deposit}, headers=expert.headers).json()
    assert done["date_depot"] == deposit and set(done["etapes"]) == {
        "pieces",
        "saisie",
        "revision",
        "revue",
        "depot",
    }
    back = client.put(url, json={"etape": "revision"}, headers=expert.headers).json()
    assert back["date_depot"] is None and "revue" not in back["etapes"]
    # Échéance liée à la clôture : passée sans dépôt, le dossier est en retard.
    rule = {"pays": "CI", "code": "DSF", "libelle": "Dépôt de la liasse", "nature": "fiscal",
            "periodicite": "cloture", "decalage_mois": 0}  # fmt: skip
    assert client.post("/api/calendar-rules", json=rule, headers=expert.headers).status_code == 201
    upcoming = {"pays": "CI", "code": "TVA", "libelle": "TVA", "nature": "fiscal", "periodicite": "mensuelle",
                "jour": 28}  # fmt: skip
    client.post("/api/calendar-rules", json=upcoming, headers=expert.headers)
    board = client.get("/api/portfolio/dashboard", headers=collab.headers).json()
    rows = {r["client"]: r for r in board["dossiers"]}
    assert (
        rows["Boulangerie du Plateau SARL"]["avancement"] == 40
        and rows["Boulangerie du Plateau SARL"]["en_retard"]
    )
    assert rows["Pharmacie des Lagunes"]["cloture"] is None and board["par_etape"]["revision"] == 1
    assert "Boulangerie du Plateau SARL" in board["dossiers_en_retard"]
    assert any(d["code"] == "TVA" for d in board["echeances_a_venir"])
    assert other["id"] in {r["client_id"] for r in board["dossiers"]}
