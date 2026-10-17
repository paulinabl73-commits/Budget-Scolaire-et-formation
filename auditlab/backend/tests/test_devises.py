"""REV-07 : devises, cours de conversion par date et montants sans décimales en FCFA."""

from decimal import Decimal

from app.security.roles import Role
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_balances import upload

EUR = (
    "Compte;Intitulé;Solde débit;Solde crédit\n"
    "101300;Capital;;1 000,00\n521100;Banque;600,55;\n571100;Caisse;399,45;\n"
)


def rate(client, headers, date, taux, source="EUR", cible="XOF"):
    body = {"devise_source": source, "devise_cible": cible, "date": date, "taux": taux}
    return client.post("/api/exchange-rates", json=body, headers=headers)


def test_rev07_devises_et_cours(client, rev, account):  # noqa: F811
    chef, aud = rev["chef"].headers, rev["aud"].headers
    devises = {c["code"]: c["decimales"] for c in client.get("/api/currencies", headers=aud).json()}
    assert devises["XOF"] == devises["XAF"] == 0 and devises["EUR"] == 2
    body = {"code": "GHS", "libelle": "Cedi ghanéen", "decimales": 2}
    assert client.post("/api/currencies", json=body, headers=chef).status_code == 403
    admin = account(Role.ADMIN).headers
    assert client.post("/api/currencies", json=body, headers=admin).status_code == 201
    assert client.post("/api/currencies", json=body, headers=admin).status_code == 409
    # Cours : saisis par le chef de mission, uniques par date, devises définies.
    assert rate(client, aud, "2026-12-31", "655.957").status_code == 403
    created = rate(client, chef, "2026-12-31", "655.957")
    assert created.status_code == 201 and created.json()["taux"] == "655.957"
    assert rate(client, chef, "2026-12-31", "656").status_code == 409
    assert rate(client, chef, "2026-12-31", "1", cible="ZZZ").status_code == 422
    assert rate(client, chef, "2026-12-31", "1", cible="EUR").status_code == 422
    assert rate(client, chef, "2026-12-31", "0").status_code == 422
    listed = client.get("/api/exchange-rates?devise=EUR", headers=aud).json()
    assert [(r["devise_source"], r["date"]) for r in listed] == [("EUR", "2026-12-31")]
    resp = client.delete(f"/api/exchange-rates/{created.json()['id']}", headers=chef)
    assert resp.status_code == 204
    assert client.get("/api/exchange-rates", headers=aud).json() == []
    assert (
        client.delete(f"/api/exchange-rates/{created.json()['id']}", headers=chef).status_code
        == 404
    )
    # Un dossier ne peut être tenu que dans une devise définie.
    resp = client.post(f"{rev['url']}/audit-files", headers=chef, json={
        "exercice": 2026, "date_debut": "2026-01-01", "date_fin": "2026-12-31",
        "framework_id": str(rev["framework"].id), "devise": "ZZZ"})  # fmt: skip
    assert resp.status_code == 422 and "ZZZ" in resp.text


def test_rev07_conversion_a_l_import(client, rev):  # noqa: F811
    chef = rev["chef"].headers
    f = create_file(client, rev)
    # Sans cours enregistré : import refusé avec l'indication de la saisie à faire.
    resp = upload(client, rev, f["id"], "eur.csv", EUR.encode(), devise_source="EUR")
    assert resp.status_code == 422 and "Aucun cours EUR → XOF" in resp.text
    # Seul le cours inverse d'une date antérieure est connu : il est appliqué et signalé.
    rate(client, chef, "2026-06-30", "0.0015244", source="XOF", cible="EUR")
    tb = upload(client, rev, f["id"], "eur.csv", EUR.encode(), devise_source="EUR").json()
    assert tb["statut"] == "accepte" and tb["devise_source"] == "EUR"
    assert [w["code"] for w in tb["avertissements"]][:2] == ["cours_anterieur", "arrondi"]
    assert "30/06/2026" in tb["avertissements"][0]["message"]
    # Cours de clôture : montants convertis, arrondis au franc, balance équilibrée.
    rate(client, chef, "2026-12-31", "655.957")
    tb = upload(client, rev, f["id"], "eur.csv", EUR.encode(), devise_source="EUR").json()
    assert tb["statut"] == "accepte" and Decimal(tb["cours"]) == Decimal("655.957")
    assert tb["totaux"]["solde_debit"] == tb["totaux"]["solde_credit"] == "655957"
    lines = client.get(f"/api/trial-balances/{tb['id']}/lines", headers=chef).json()
    assert {x["compte"]: x["solde_debit"] for x in lines}["521100"] == "393935.00"
    # Un cours à une autre date peut être choisi.
    tb = upload(client, rev, f["id"], "eur.csv", EUR.encode(), devise_source="EUR",
                date_cours="2026-07-01").json()  # fmt: skip
    assert tb["avertissements"][0]["code"] == "cours_anterieur"
    # Fichier en FCFA comportant des centimes : arrondi au franc et signalé.
    fcfa = "Compte;Intitulé;Solde débit;Solde crédit\n101300;Capital;;1 000,40\n521100;Banque;1 000,40;\n"
    tb = upload(client, rev, f["id"], "fcfa.csv", fcfa.encode(), devise_source="XOF").json()
    assert tb["statut"] == "accepte" and tb["devise_source"] is None
    assert tb["totaux"]["solde_debit"] == "1000"
    assert [w["code"] for w in tb["avertissements"]] == ["arrondi", "a_nouveaux_differes"]
