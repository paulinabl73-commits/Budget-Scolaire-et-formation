"""REV-12 : revue analytique N/N-1 avec justification obligatoire des variations signalées."""

from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load


def test_rev12_revue_analytique(client, rev):  # noqa: F811
    f = create_file(client, rev)
    url = f"/api/audit-files/{f['id']}"
    aud = rev["aud"].headers
    load(client, rev, f["id"])
    resp = client.get(f"{url}/analytical-review", headers=aud)
    assert resp.status_code == 409 and "seuil" in resp.text
    # Seuil : 1,5 % de 31,7 M = 475 500 ; planification 356 625 ; insignifiance 23 775.
    body = {
        "base_seuil": "total_bilan",
        "pct_seuil": "1.5",
        "justification": "Total du bilan retenu",
    }
    client.put(f"{url}/materiality", json=body, headers=rev["chef"].headers)
    review = client.get(f"{url}/analytical-review", headers=aud).json()
    comptes = {x["code"]: x for x in review["comptes"]}
    banque = comptes["521100"]  # +7,6 M : au-delà du seuil de planification
    assert (banque["N"], banque["N-1"], banque["variation"]) == (
        "14200000.00",
        "6600000.00",
        "7600000.00",
    )
    assert banque["variation_pct"] == "115.2" and banque["signale"]
    assert comptes["571100"]["signale"]  # +100 000, +50 % : au-delà du % et de l'insignifiance
    assert comptes["401200"]["signale"] and comptes["401200"]["variation_pct"] is None  # nouveau
    assert comptes["421000"]["variation_pct"] == "-33.3" and comptes["421000"]["signale"]
    assert not comptes["101300"]["signale"] and not comptes["681300"]["signale"]
    postes = {x["code"]: x for x in review["postes"]}
    assert postes["BS"]["signale"] and postes["BS"]["variation"] == "7700000.00"
    assert postes["BZ"]["total"] and not postes["BZ"]["signale"]
    flagged = [x["code"] for x in review["postes"] + review["comptes"] if x["signale"]]
    assert review["nb_signales"] == len(flagged) == review["nb_non_justifies"] > 5
    # Justification : obligatoire, motivée, réservée à l'équipe.
    note = {
        "niveau": "compte",
        "code": "521100",
        "texte": "Encaissement de la créance Alpha en décembre (relevé bancaire).",
    }
    assert client.put(f"{url}/analytical-review/justifications", json={**note, "texte": "vu"},
                      headers=aud).status_code == 422  # fmt: skip
    assert client.put(f"{url}/analytical-review/justifications", json={**note, "code": "999999"},
                      headers=aud).status_code == 404  # fmt: skip
    assert client.put(f"{url}/analytical-review/justifications", json=note,
                      headers=rev["da"].headers).status_code == 403  # fmt: skip
    after = client.put(f"{url}/analytical-review/justifications", json=note, headers=aud).json()
    assert after["nb_non_justifies"] == review["nb_non_justifies"] - 1
    banque = next(x for x in after["comptes"] if x["code"] == "521100")
    assert banque["justification"].startswith("Encaissement") and banque["justifie_le"]
    note["texte"] = "Encaissement de la créance Alpha, rapproché du relevé de décembre."
    after = client.put(f"{url}/analytical-review/justifications", json=note, headers=aud).json()
    assert (
        next(x for x in after["comptes"] if x["code"] == "521100")["justification"] == note["texte"]
    )
