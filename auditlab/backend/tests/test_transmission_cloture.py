"""RCO-27 : transmission d'un dossier de clôture à la mission d'audit de la même entité."""

from app.models import AuditableEntity
from app.security.roles import Role
from tests import helpers
from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload
from tests.test_revue_cloture import BALANCE


def test_rco27_transmission(client, cabinet, account, db):  # noqa: F811
    expert, collab = cabinet["expert"], cabinet["collab"]
    closing = open_closing(client, cabinet, new_client(client, cabinet))
    fid, cid = closing["audit_file_id"], closing["id"]
    assert (
        upload(client, {"aud": collab}, fid, "b.csv", BALANCE.encode()).json()["statut"]
        == "accepte"
    )
    entry = client.post(f"/api/audit-files/{fid}/provisions", json={
        "nature": "risque", "libelle": "Garantie", "montant_requis": "1000"}, headers=collab.headers)  # fmt: skip
    entry = client.post(f"/api/audit-files/{fid}/provisions/entry", headers=collab.headers).json()
    client.post(f"/api/adjustments/{entry['id']}/decision", json={"statut": "acceptee"},
                headers=expert.headers)  # fmt: skip

    for compte in ("101000", "521000", "198"):
        client.post(f"/api/audit-files/{fid}/justifications/{compte}/review",
                    json={"commentaire": "Vu"}, headers=expert.headers)  # fmt: skip
    att = client.post(f"/api/audit-files/{fid}/justifications/521000/files",
                      files={"file": ("releve.pdf", b"%PDF-1.4 releve")}, headers=collab.headers)  # fmt: skip
    assert att.status_code == 201, att.text
    # Mission d'audit de la même société (entité de l'univers d'audit), autre équipe.
    entity = AuditableEntity(nom="Boulangerie du Plateau SARL", type="filiale")
    db.add(entity)
    db.commit()
    chef = account(Role.CHEF_MISSION)
    m = helpers.mission(
        client, chef.headers, titre="Commissariat aux comptes", entity_id=str(entity.id)
    )
    eurl = f"/api/engagements/{m['id']}"
    assert client.get(f"{eurl}/transmitted-closings", headers=chef.headers).json() == []
    assert client.get(f"{eurl}/transmitted-closings", headers=collab.headers).status_code in (
        403,
        404,
    )
    turl = f"/api/closings/{cid}/transmission"
    body = {"mission": m["reference"]}
    assert client.post(turl, json=body, headers=collab.headers).status_code == 403
    assert client.post(turl, json=body, headers=expert.headers).status_code == 409  # visa attendu
    rv = client.post(
        f"/api/closings/{cid}/review", json={"niveau": "expert"}, headers=expert.headers
    )
    assert rv.status_code == 200, rv.text
    bad = client.post(turl, json={"mission": "INCONNUE"}, headers=expert.headers)
    assert bad.status_code == 404
    assert client.post(turl, json=body, headers=expert.headers).json()["mission"] == m["reference"]
    listed = client.get(f"{eurl}/transmitted-closings", headers=chef.headers).json()
    assert [(c["id"], c["repris"]) for c in listed] == [(cid, False)]

    resp = client.post(
        f"{eurl}/audit-files/from-closing", json={"closing_id": cid}, headers=chef.headers
    )
    assert resp.status_code == 201, resp.text
    audit = resp.json()
    assert audit["source_file_id"] == fid and audit["mode"] == "audit" and audit["id"] != fid
    # Balance N révisée de l'écriture de provision acceptée (691 / 19x pour 1 000).
    imports = client.get(f"/api/audit-files/{audit['id']}/imports", headers=chef.headers).json()
    revised = next(i for i in imports if i["periode"] == "N" and i["type"] == "balance")
    from sqlalchemy import select

    from app.models.revision import TrialBalanceLine

    rows = db.scalars(
        select(TrialBalanceLine).where(TrialBalanceLine.trial_balance_id == revised["id"])
    )
    lines = {ln.compte: ln for ln in rows}
    assert set(lines) >= {"101000", "521000"} and any(c.startswith("691") for c in lines)
    states = client.get(f"/api/audit-files/{audit['id']}/statements", headers=chef.headers).json()
    assert all(c["ok"] for c in states["controles"])
    wps = client.get(f"{eurl}/workpapers", headers=chef.headers).json()
    wp = next(w for w in wps if w["reference"] == "CLO-2026")
    files = client.get(f"/api/workpapers/{wp['id']}/attachments", headers=chef.headers).json()
    assert [f["nom_fichier"] for f in files] == ["releve.pdf"]
    # Une seule reprise ; la transmission ne peut plus être retirée.
    assert client.post(f"{eurl}/audit-files/from-closing", json={"closing_id": cid},
                       headers=chef.headers).status_code == 409  # fmt: skip
    assert client.delete(turl, headers=expert.headers).status_code == 409
    assert (
        client.get(turl, headers=collab.headers).json()["reprises"][0]["dossier_id"] == audit["id"]
    )
