"""CIP-01 : suivi par branche (comptes, contrôles, états et ratios)."""

from tests.cipres_helpers import ops, ops_file  # noqa: F401
from tests.revision_helpers import create_file, rev  # noqa: F401


def test_cip01_suivi_par_branche(client, rev, ops, db):  # noqa: F811
    from app.models import Control

    aud = rev["aud"].headers
    syscohada = create_file(client, rev, exercice=2025)
    assert (
        client.get(f"/api/audit-files/{syscohada['id']}/branches", headers=aud).status_code == 409
    )
    f = ops_file(client, rev, ops)
    url = f"/api/audit-files/{f['id']}/branches"
    data = client.get(url, headers=aud).json()
    assert [b["code"] for b in data["branches"]] == ["PF", "RP", "PV", "AM", "GA"]
    assert data["non_rattaches"] == ["411000"]
    comptes = {c["compte"]: c for c in data["comptes"]}
    assert (comptes["631000"]["branche"], comptes["631000"]["origine"]) == ("PF", "plan")
    pf = {x["code"]: x for x in data["etats"]["PF"]}
    ga = {x["code"]: x for x in data["etats"]["GA"]}
    assert (pf["PC"]["N"], pf["CH"]["N"], pf["RN"]["N"]) == (
        "40000000.00",
        "25000000.00",
        "15000000.00",
    )
    assert pf["RE"]["N"] == "65000000.00"  # réserves PF et résultat PF
    assert ga["RN"]["N"] == "-15000000.00" and ga["TA"]["N"] == "145000000.00"
    assert {r["code"]: r["N"] for r in data["ratios"]["PF"]}[
        "autonomie"
    ] is None  # pas d'actif propre à PF
    # Rattachement manuel d'un compte, puis retour au plan.
    data = client.put(f"{url}/accounts/411000", json={"branche": "PV"}, headers=aud).json()
    assert (
        data["non_rattaches"] == []
        and {c["compte"]: c for c in data["comptes"]}["411000"]["origine"] == "manuelle"
    )
    assert {x["code"]: x for x in data["etats"]["PV"]}["CR"]["N"] == "15000000.00"
    assert (
        client.put(f"{url}/accounts/411000", json={"branche": "XX"}, headers=aud).status_code == 422
    )
    assert client.put(f"{url}/accounts/411000", json={"branche": None}, headers=aud).json()[
        "non_rattaches"
    ] == ["411000"]
    # Contrôles de la mission rattachés à une branche.
    control = Control(
        libelle="Contrôle des liquidations de pensions",
        cycle="autre",
        type_controle="detectif",
        nature="manuel",
        frequence="mensuel",
        bibliotheque=False,
        engagement_id=rev["mission"]["id"],
    )
    db.add(control)
    db.commit()
    data = client.put(f"{url}/controls/{control.id}", json={"branche": "PV"}, headers=aud).json()
    assert data["controles"] == [
        {"id": str(control.id), "libelle": control.libelle, "branche": "PV"}
    ]
    assert (
        client.put(f"{url}/controls/{f['id']}", json={"branche": "PV"}, headers=aud).status_code
        == 404
    )
    assert (
        client.put(
            f"{url}/accounts/411000", json={"branche": "PF"}, headers=rev["da"].headers
        ).status_code
        == 403
    )
