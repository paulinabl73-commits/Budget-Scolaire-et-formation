"""Rôles du Module 5 : Associé signataire et Inspecteur CIPRES (section 2)."""

from app.models import AuditableEntity
from app.security.roles import Perm, Role, has_permission
from tests import helpers


def test_droits_des_roles_du_module5():
    associe, directeur = Role.ASSOCIE.value, Role.DIRECTEUR.value
    assert has_permission(associe, Perm.OPINION_SIGN) and not has_permission(
        directeur, Perm.OPINION_SIGN
    )
    assert has_permission(associe, Perm.REVISION_MANAGE) and has_permission(
        associe, Perm.MISSIONS_MANAGE
    )
    # Sur ses seuls dossiers : pas de lecture de toutes les missions, ni du plan.
    assert not has_permission(associe, Perm.MISSIONS_READ_ALL) and has_permission(
        associe, Perm.MISSIONS_READ_OWN
    )
    assert not has_permission(associe, Perm.PLAN_MANAGE)
    inspecteur = Role.INSPECTEUR_CIPRES.value
    assert all(
        has_permission(inspecteur, p) for p in Perm if has_permission(Role.CHEF_MISSION.value, p)
    )


def test_associe_dirige_les_dossiers_qu_il_supervise(client, account, db, syscohada):
    chef, associe, autre = account(Role.CHEF_MISSION), account(Role.ASSOCIE), account(Role.ASSOCIE)
    entity = AuditableEntity(nom="Société Test SA", type="filiale")
    db.add(entity)
    db.commit()
    m = helpers.mission(
        client, chef.headers, membres=[(associe.user, "superviseur")], entity_id=str(entity.id)
    )
    # L'associé voit et dirige la mission qu'il supervise (ouverture d'un dossier de révision) ;
    # un autre associé ne la voit pas.
    body = {
        "exercice": 2026,
        "date_debut": "2026-01-01",
        "date_fin": "2026-12-31",
        "framework_id": str(syscohada.id),
    }
    resp = client.post(
        f"/api/engagements/{m['id']}/audit-files", json=body, headers=associe.headers
    )
    assert resp.status_code == 201, resp.text
    assert client.get(f"/api/engagements/{m['id']}", headers=autre.headers).status_code == 404
