"""Mission de révision de test : entité, équipe, référentiel SYSCOHADA (Module 5)."""

import pytest

from app.models import AuditableEntity
from app.security.roles import Role
from tests import helpers


@pytest.fixture
def rev(client, account, db, syscohada):
    chef = account(Role.CHEF_MISSION)
    aud = account(Role.AUDITEUR)
    da = account(Role.DATA_ANALYST)
    entity = AuditableEntity(nom="Société Ivoirienne de Négoce SA", type="filiale")
    db.add(entity)
    db.commit()
    m = helpers.mission(
        client, chef.headers, membres=[(aud.user, "auditeur"), (da.user, "data_analyst")],
        titre="Commissariat aux comptes 2026", entity_id=str(entity.id),
    )  # fmt: skip
    return {"chef": chef, "aud": aud, "da": da, "mission": m, "entity": entity,
            "framework": syscohada, "url": f"/api/engagements/{m['id']}"}  # fmt: skip


def create_file(client, rev, exercice=2026, **kw):
    body = {"exercice": exercice, "date_debut": f"{exercice}-01-01", "date_fin": f"{exercice}-12-31",
            "framework_id": str(rev["framework"].id), **kw}  # fmt: skip
    resp = client.post(f"{rev['url']}/audit-files", json=body, headers=rev["chef"].headers)
    assert resp.status_code == 201, resp.text
    return resp.json()
