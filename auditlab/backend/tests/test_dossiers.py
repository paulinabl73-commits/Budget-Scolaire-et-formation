"""REV-02 à REV-04 : dossier de révision, référentiels, cadre normatif, exercice N-1."""

from app.models import NormativeFramework
from app.revision.frameworks import builtin, load_framework
from tests.revision_helpers import create_file, rev  # noqa: F401


def test_rev02_rev03_dossier_et_referentiels(client, rev, db):  # noqa: F811
    nf = NormativeFramework(code="isa", libelle="Normes ISA")
    db.add(nf)
    ifrs_doc = builtin("syscohada_2017") | {"code": "IFRS", "version": "2026", "libelle": "IFRS"}
    ifrs = load_framework(db, ifrs_doc)
    db.commit()
    f = create_file(
        client, rev, normative_id=str(nf.id), ifrs_framework_id=str(ifrs.id), devise="XAF"
    )
    assert f["referentiel"] == "SYSCOHADA 2017 (OHADA)" and f["referentiel_ifrs"] == "IFRS 2026"
    assert f["cadre_normatif"] == "Normes ISA" and f["devise"] == "XAF"
    assert f["entite"] == "Société Ivoirienne de Négoce SA" and f["precedent_id"] is None
    assert f["peut_gerer"] and f["statut"] == "ouvert"
    # Référentiel principal : SYSCOHADA ou CIPRES uniquement, IFRS seulement en restitution.
    bad = client.post(f"{rev['url']}/audit-files",
                      json={"exercice": 2025, "date_debut": "2025-01-01", "date_fin": "2025-12-31",
                            "framework_id": str(ifrs.id)}, headers=rev["chef"].headers)  # fmt: skip
    assert bad.status_code == 422
    resp = client.patch(f"/api/audit-files/{f['id']}", json={"ifrs_framework_id": str(rev["framework"].id)},
                        headers=rev["chef"].headers)  # fmt: skip
    assert resp.status_code == 422
    resp = client.patch(f"/api/audit-files/{f['id']}", json={"ifrs_framework_id": None},
                        headers=rev["chef"].headers)  # fmt: skip
    assert resp.json()["referentiel_ifrs"] is None
    # Lecture par l'équipe ; création et paramètres réservés au chef.
    assert not client.get(f"/api/audit-files/{f['id']}", headers=rev["aud"].headers).json()[
        "peut_gerer"
    ]
    assert (
        client.patch(f"/api/audit-files/{f['id']}", json={}, headers=rev["aud"].headers).status_code
        == 403
    )
    assert [
        x["exercice"]
        for x in client.get(f"{rev['url']}/audit-files", headers=rev["da"].headers).json()
    ] == [2026]


def test_rev04_exercice_precedent_et_unicite(client, rev):  # noqa: F811
    old = create_file(client, rev, exercice=2025)
    new = create_file(client, rev, exercice=2026)
    assert new["precedent_id"] == old["id"] and new["precedent_exercice"] == 2025
    dup = client.post(f"{rev['url']}/audit-files",
                      json={"exercice": 2026, "date_debut": "2026-01-01", "date_fin": "2026-12-31",
                            "framework_id": str(rev["framework"].id)}, headers=rev["chef"].headers)  # fmt: skip
    assert dup.status_code == 409
    bad_dates = client.post(f"{rev['url']}/audit-files",
                            json={"exercice": 2027, "date_debut": "2027-12-31", "date_fin": "2027-01-01",
                                  "framework_id": str(rev["framework"].id)}, headers=rev["chef"].headers)  # fmt: skip
    assert bad_dates.status_code == 422
    assert client.post(
        f"{rev['url']}/audit-files", json={}, headers=rev["aud"].headers
    ).status_code in (403, 422)
