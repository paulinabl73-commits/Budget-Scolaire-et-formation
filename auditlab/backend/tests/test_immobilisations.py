"""RCO-11 : tableau des immobilisations, amortissements et écriture de dotation."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload

BALANCE = """Compte;Intitulé;Solde débit;Solde crédit
101000;Capital;;3000000
244100;Matériel;2200000;
521000;Banque;800000;
"""


def asset(code, valeur, date, **kw):
    return {"code": code, "libelle": f"Bien {code}", "compte_immobilisation": "244100",
            "compte_amortissement": "284100", "compte_dotation": "681300",
            "date_mise_en_service": date, "valeur_origine": str(valeur), "duree_annees": 5, **kw}  # fmt: skip


def test_rco11_immobilisations(client, cabinet, db):  # noqa: F811
    collab, expert = cabinet["collab"], cabinet["expert"]
    c = new_client(client, cabinet)
    fid = open_closing(client, cabinet, c)["audit_file_id"]
    assert (
        upload(client, {"aud": collab}, fid, "b.csv", BALANCE.encode()).json()["statut"]
        == "accepte"
    )
    url = f"/api/audit-files/{fid}/fixed-assets"
    client.post(url, json=asset("A1", 1_200_000, "2026-07-15"), headers=collab.headers)
    resp = client.post(
        url, json=asset("B1", 1_000_000, "2026-04-10", mode="degressif"), headers=collab.headers
    )
    assert resp.status_code == 422  # coefficient fiscal à saisir
    client.post(
        url,
        json=asset("B1", 1_000_000, "2026-04-10", mode="degressif", coefficient="2"),
        headers=collab.headers,
    )
    sold = asset(
        "D1",
        600_000,
        "2020-01-01",
        duree_annees=10,
        date_cession="2026-06-30",
        prix_cession="400000",
    )
    data = client.post(url, json=sold, headers=collab.headers).json()
    a1 = next(r for r in data["immobilisations"] if r["code"] == "A1")
    parts = asset("A1-M", 200_000, "2026-07-15", composant_de=a1["id"], duree_annees=2)
    data = client.post(url, json=parts, headers=collab.headers).json()
    rows = {r["code"]: r for r in data["immobilisations"]}
    assert rows["A1"]["dotation"] == "110667" and rows["A1"]["acquisition"]
    assert rows["A1-M"]["dotation"] == "46111" and rows["A1-M"]["composant_de"] == a1["id"]
    assert rows["B1"]["dotation"] == "300000"
    assert (rows["D1"]["cumul_fin"], rows["D1"]["dotation"], rows["D1"]["resultat_cession"]) == (
        "390000", "30000", "190000.00")  # fmt: skip
    gross = {r["compte"]: r for r in data["rapprochement"]}["244100"]
    assert (gross["tableau"], gross["ecart"]) == ("2400000.00", "-200000.00")
    bad = asset("X", 1, "2026-01-01", compte_dotation="012345")
    assert client.post(url, json=bad, headers=collab.headers).status_code == 422
    # Écriture de dotation proposée, remplacée tant qu'elle n'est pas acceptée.
    entry = client.post(f"{url}/entry", headers=collab.headers).json()
    assert (
        entry["type"] == "inventaire"
        and entry["origine"] == "RCO-11"
        and entry["total"] == "486778.00"
    )
    again = client.post(f"{url}/entry", headers=collab.headers).json()
    entries = client.get(f"/api/audit-files/{fid}/adjustments", headers=collab.headers).json()
    assert [e["numero"] for e in entries] == [again["numero"]]
    decision = {"statut": "acceptee"}
    assert (
        client.post(
            f"/api/adjustments/{again['id']}/decision", json=decision, headers=expert.headers
        ).status_code
        == 200
    )
    assert client.post(f"{url}/entry", headers=collab.headers).status_code == 409
    assert client.delete(f"{url}/{a1['id']}", headers=collab.headers).status_code == 204
