"""RCO-20 : tableau de passage du résultat comptable au résultat fiscal, IS et impôt minimum."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload
from tests.test_revision_fiscale import vat_files


def test_rco20_passage_fiscal(client, cabinet):  # noqa: F811
    collab, expert = cabinet["collab"], cabinet["expert"]
    fid = open_closing(client, cabinet, new_client(client, cabinet))["audit_file_id"]
    balance, _ = vat_files()
    assert upload(client, {"aud": collab}, fid, "b.csv", balance).json()["statut"] == "accepte"
    rule = {"pays": "CI", "code": "ACH50", "libelle": "Charges non déductibles (test)", "sens": "reintegration",
            "racines": ["601"], "pourcentage": "50"}  # fmt: skip
    assert client.post("/api/fiscal-rules", json=rule, headers=collab.headers).status_code == 403
    assert client.post("/api/fiscal-rules", json=rule, headers=expert.headers).status_code == 201
    url = f"/api/audit-files/{fid}/tax-bridge"
    deficit = {
        "libelle": "Déficits antérieurs reportables",
        "sens": "deduction",
        "montant": "30000",
    }
    data = client.post(f"{url}/lines", json=deficit, headers=collab.headers).json()
    assert (data["resultat_net"], data["resultat_avant_impot"], data["reintegrations"], data["deductions"]) == (
        "260000.00", "260000.00", "20000", "30000.00")  # fmt: skip
    assert data["resultat_fiscal"] == "250000.00" and data["impot"] is None
    assert set(data["parametres_manquants"]) == {"taux_is", "taux_impot_minimum", "impot_minimum_plancher",
                                                 "impot_minimum_plafond"}  # fmt: skip
    for code, valeur in (("taux_is", "25"), ("taux_impot_minimum", "1"), ("impot_minimum_plancher", "500000"),
                         ("impot_minimum_plafond", "0")):  # fmt: skip
        client.post(
            "/api/fiscal-parameters",
            json={"pays": "CI", "code": code, "valeur": valeur},
            headers=expert.headers,
        )
    impot = client.get(url, headers=collab.headers).json()["impot"]
    assert (impot["impot_societes"], impot["impot_minimum"], impot["impot_du"], impot["regime"]) == (
        "62500", "500000", "500000", "impot_minimum")  # fmt: skip
    # Montant retenu à la place du montant calculé par la règle.
    data = client.post(f"{url}/lines", json={"rule_code": "ACH50", "libelle": "Retenu après analyse", "sens": "deduction",
                                             "montant": "10000"}, headers=collab.headers).json()  # fmt: skip
    line = next(e for e in data["elements"] if e["code"] == "ACH50")
    assert (line["calcule"], line["montant"], line["origine"], line["sens"]) == (
        "20000",
        "10000.00",
        "saisi",
        "reintegration",
    )
    assert data["resultat_fiscal"] == "240000.00"
    assert client.delete(f"{url}/lines/{line['id']}", headers=collab.headers).status_code == 204
