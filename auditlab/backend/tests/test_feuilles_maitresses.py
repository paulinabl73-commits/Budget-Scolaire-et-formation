"""REV-15 : feuilles maîtresses par cycle."""

from app.models import Workpaper
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load
from tests.test_ajustements import PROVISION


def test_rev15_feuilles_maitresses(client, rev, db):  # noqa: F811
    f = create_file(client, rev)
    aud = rev["aud"].headers
    load(client, rev, f["id"])
    papers = [Workpaper(engagement_id=rev["mission"]["id"], reference=ref, titre=titre,
                        travaux={"type": "doc", "content": []})
              for ref, titre in (("C-1", "Circularisation clients"), ("C-2", "Dépréciations"))]  # fmt: skip
    db.add_all(papers)
    db.commit()
    adj = client.post(f"/api/audit-files/{f['id']}/adjustments",
                      json={**PROVISION, "workpaper_id": str(papers[1].id)}, headers=aud).json()  # fmt: skip
    client.post(f"/api/adjustments/{adj['id']}/decision", json={"statut": "acceptee"}, headers=aud)
    reclass = {"type": "reclassement", "libelle": "Avances clients", "justification": "Avance reçue mal classée.",
               "lignes": [{"compte": "411100", "debit": "300000"}, {"compte": "419100", "credit": "300000"}]}  # fmt: skip
    client.post(f"/api/audit-files/{f['id']}/adjustments", json=reclass, headers=aud)
    url = f"/api/audit-files/{f['id']}/lead-schedules"
    resp = client.put(
        f"{url}/clients/workpapers", json={"workpaper_ids": [str(papers[0].id)]}, headers=aud
    )
    assert resp.status_code == 200
    sheets = {s["cycle"]: s for s in resp.json()}
    assert len(sheets) == 11
    clients = sheets["clients"]
    assert clients["totaux"] == {"N-1": "6000000.00", "N": "6700000.00", "ajustements": "-500000.00",
                                 "revise": "6200000.00"}  # fmt: skip
    assert [c["compte"] for c in clients["comptes"]] == ["411100", "419100", "491000"]
    assert clients["comptes"][2] == {"compte": "491000", "libelle": None, "N-1": "0", "N": "0",
                                     "ajustements": "-500000.00", "revise": "-500000.00"}  # fmt: skip
    assert [(p["reference"], p["rattache"]) for p in clients["papiers"]] == [
        ("C-1", True),
        ("C-2", False),
    ]
    assert clients["ecritures"] == [
        {"numero": 1, "statut": "acceptee"},
        {"numero": 2, "statut": "proposee"},
    ]
    assert sheets["produits_charges"]["totaux"]["ajustements"] == "500000.00"
    assert (
        sheets["tresorerie"]["totaux"]["revise"]
        == sheets["tresorerie"]["totaux"]["N"]
        == "13700000.00"
    )
    # Contrôles : cycle inconnu, papier d'une autre mission, droits ; retrait d'un renvoi.
    assert (
        client.put(f"{url}/inconnu/workpapers", json={"workpaper_ids": []}, headers=aud).status_code
        == 404
    )
    other = {"workpaper_ids": ["00000000-0000-0000-0000-000000000000"]}
    assert client.put(f"{url}/clients/workpapers", json=other, headers=aud).status_code == 422
    assert client.put(f"{url}/clients/workpapers", json={"workpaper_ids": []},
                      headers=rev["da"].headers).status_code == 403  # fmt: skip
    sheets = {s["cycle"]: s for s in client.put(f"{url}/clients/workpapers", json={"workpaper_ids": []},
                                                headers=aud).json()}  # fmt: skip
    assert [p["reference"] for p in sheets["clients"]["papiers"]] == ["C-2"]
