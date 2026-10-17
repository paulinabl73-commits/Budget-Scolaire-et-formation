"""REV-22 : tableau des anomalies non corrigées comparé au seuil de signification."""

from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load


def entry(compte_d, compte_c, montant, type_="correction"):
    return {"type": type_, "libelle": f"{compte_d}/{compte_c}", "justification": "Anomalie relevée en revue.",
            "lignes": [{"compte": compte_d, "debit": montant}, {"compte": compte_c, "credit": montant}]}  # fmt: skip


def test_rev22_anomalies_non_corrigees(client, rev):  # noqa: F811
    f = create_file(client, rev)
    base = f"/api/audit-files/{f['id']}"
    aud = rev["aud"].headers
    load(client, rev, f["id"])
    assert client.get(f"{base}/unadjusted", headers=aud).status_code == 409
    body = {
        "base_seuil": "total_bilan",
        "pct_seuil": "1.5",
        "justification": "Total du bilan retenu",
    }
    client.put(f"{base}/materiality", json=body, headers=rev["chef"].headers)
    # Seuils : signification 475 500, planification 356 625, insignifiance 23 775.
    ids = [client.post(f"{base}/adjustments", json=e, headers=aud).json()["id"] for e in (
        entry("681300", "491000", "200000"),          # refusée : charge non comptabilisée
        entry("411100", "701100", "10000"),           # insignifiante
        entry("601100", "401100", "180000"),          # proposée
        entry("411100", "419100", "300000", "reclassement"),
        entry("622000", "401100", "90000"),           # acceptée : corrigée
    )]  # fmt: skip
    client.post(
        f"/api/adjustments/{ids[0]}/decision",
        json={"statut": "refusee", "motif": "Désaccord"},
        headers=aud,
    )
    client.post(f"/api/adjustments/{ids[4]}/decision", json={"statut": "acceptee"}, headers=aud)
    table = client.get(f"{base}/unadjusted", headers=aud).json()
    assert [a["numero"] for a in table["anomalies"]] == [1, 2, 3, 4]
    assert (
        table["anomalies"][1]["insignifiant"]
        and table["anomalies"][0]["effet_resultat"] == "-200000.00"
    )
    assert table["cumul_resultat"] == "-380000.00" and table["cumul_reclassements"] == "300000.00"
    assert table["conclusion"] == "vigilance"  # 380 000 : entre planification et signification
    client.post(f"{base}/adjustments", json=entry("661000", "421000", "100000"), headers=aud)
    assert client.get(f"{base}/unadjusted", headers=aud).json()["conclusion"] == "significatif"
    client.post(f"/api/adjustments/{ids[2]}/decision", json={"statut": "acceptee"}, headers=aud)
    table = client.get(f"{base}/unadjusted", headers=aud).json()
    assert table["cumul_resultat"] == "-300000.00" and table["conclusion"] == "non_significatif"
    big = client.post(
        f"{base}/adjustments", json=entry("411100", "419100", "500000", "reclassement"), headers=aud
    )
    assert big.status_code == 201
    table = client.get(f"{base}/unadjusted", headers=aud).json()
    assert (
        table["anomalies"][-1]["individuellement_significatif"]
        and table["conclusion"] == "significatif"
    )
