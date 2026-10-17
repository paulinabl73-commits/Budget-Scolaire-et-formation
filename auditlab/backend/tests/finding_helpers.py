"""Mission de test avec risque, contrôle, papier de travail et audité (Module 3)."""

import pytest

from app.richtext import from_plain_text
from app.security.roles import Role
from tests import helpers


@pytest.fixture
def team(client, account):
    chef = account(Role.CHEF_MISSION)
    aud = account(Role.AUDITEUR)
    da = account(Role.DATA_ANALYST)
    directeur = account(Role.DIRECTEUR)
    audite = account(Role.AUDITE)
    m = helpers.mission(
        client, chef.headers, membres=[(aud.user, "auditeur"), (da.user, "data_analyst")]
    )
    url = f"/api/engagements/{m['id']}"
    risk = client.post(
        f"{url}/risks",
        json={"libelle": "Fournisseurs fictifs", "cycle": "achats", "categorie": "fraude"},
        headers=chef.headers,
    ).json()
    control = client.post(
        f"{url}/controls",
        json={"libelle": "Validation des créations", "cycle": "achats", "type_controle": "preventif",
              "nature": "manuel", "frequence": "ponctuel", "risk_ids": [risk["id"]]},
        headers=chef.headers,
    ).json()  # fmt: skip
    wp = client.post(
        f"{url}/workpapers",
        json={"reference": "A-1", "titre": "Créations de fournisseurs", "travaux": from_plain_text("x"),
              "conclusion": "Défaillance", "evaluation": "inefficace"},
        headers=aud.headers,
    ).json()  # fmt: skip
    return {
        "chef": chef, "aud": aud, "da": da, "directeur": directeur, "audite": audite,
        "mission": m, "url": url, "risk": risk, "control": control, "wp": wp,
    }  # fmt: skip


FINDING = {
    "titre": "Fournisseurs créés sans validation",
    "critere": "Toute création de fournisseur est validée par la comptabilité (procédure ACH-02).",
    "constat": "12 fournisseurs sur 40 créés en 2026 l'ont été sans validation.",
    "cause": "Le contrôle bloquant du progiciel est désactivé.",
    "consequence": "Risque de paiements à des fournisseurs fictifs.",
    "recommandation": "Réactiver le contrôle bloquant et revoir les 12 fournisseurs.",
}


def create_finding(client, team, **kw):
    resp = client.post(
        f"{team['url']}/findings", json={**FINDING, **kw}, headers=team["aud"].headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
