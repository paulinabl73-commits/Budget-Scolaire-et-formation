"""RCO-09 : justification de chaque compte de bilan, signalement jusqu'à la revue."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload
from tests.test_controles_comptables import files

PDF = b"%PDF-1.4\n%releve\n"


def test_rco09_justifications(client, cabinet):  # noqa: F811
    expert, collab = cabinet["expert"], cabinet["collab"]
    c = new_client(client, cabinet)
    fid = open_closing(client, cabinet, c)["audit_file_id"]
    balance, _ = files()
    assert upload(client, {"aud": collab}, fid, "b.csv", balance).json()["statut"] == "accepte"
    url = f"/api/audit-files/{fid}/justifications"
    data = client.get(url, headers=collab.headers).json()
    comptes = {r["compte"]: r for r in data["comptes"]}
    assert "601000" not in comptes and data["signales"] == data["total"] == 8  # classes 1 à 5
    bank = comptes["521000"]["solde"]
    # Justifié : montant égal au solde et pièce jointe.
    data = client.put(f"{url}/521000", json={"montant_justifie": bank, "commentaire": "Relevé du 31/12"},
                      headers=collab.headers).json()  # fmt: skip
    assert {r["compte"]: r for r in data["comptes"]}["521000"]["statut"] == "sans_piece"
    data = client.post(
        f"{url}/521000/files", files={"file": ("releve.pdf", PDF)}, headers=collab.headers
    ).json()
    row = {r["compte"]: r for r in data["comptes"]}["521000"]
    assert (row["statut"], row["signale"], row["ecart"]) == ("justifie", False, "0.00")
    # Écart : signalé jusqu'à la revue ; revue réservée à l'expert, commentaire obligatoire.
    data = client.put(
        f"{url}/401100", json={"montant_justifie": "120000"}, headers=collab.headers
    ).json()
    row = {r["compte"]: r for r in data["comptes"]}["401100"]
    assert (row["statut"], row["ecart"]) == ("ecart", "-31000.00")
    assert client.post(f"{url}/401100/review", json={}, headers=collab.headers).status_code == 403
    assert client.post(f"{url}/401100/review", json={}, headers=expert.headers).status_code == 422
    data = client.post(f"{url}/401100/review", json={"commentaire": "Avance à régulariser en N+1"},
                       headers=expert.headers).json()  # fmt: skip
    row = {r["compte"]: r for r in data["comptes"]}["401100"]
    assert row["revu"] and not row["signale"] and data["signales"] == 6
    assert (
        client.put(
            f"{url}/601000", json={"montant_justifie": "1"}, headers=collab.headers
        ).status_code
        == 404
    )
