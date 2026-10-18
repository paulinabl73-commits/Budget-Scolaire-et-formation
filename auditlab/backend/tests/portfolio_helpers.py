"""Cabinet de test (Module 6) : expert-comptable, collaborateur, directeur, contact client."""

import pytest

from app.security.roles import Role


@pytest.fixture
def cabinet(client, account, syscohada):
    return {
        "expert": account(Role.EXPERT_COMPTABLE),
        "collab": account(Role.COLLABORATEUR),
        "directeur": account(Role.DIRECTEUR),
        "contact": account(Role.AUDITE),
        "framework": syscohada,
    }


def new_client(client, cab, by="expert", **kw):
    body = {"raison_sociale": "Boulangerie du Plateau SARL", "forme_juridique": "SARL",
            "regime_fiscal": "reel_simplifie", "framework_id": str(cab["framework"].id), "pays": "CI",
            "collaborateur_id": str(cab["collab"].user.id), "contact_id": str(cab["contact"].user.id), **kw}  # fmt: skip
    resp = client.post("/api/clients", json=body, headers=cab[by].headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def open_closing(client, cab, c, exercice=2026, by="expert"):
    resp = client.post(
        f"/api/clients/{c['id']}/closings", json={"exercice": exercice}, headers=cab[by].headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
