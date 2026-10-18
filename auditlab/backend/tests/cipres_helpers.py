"""Organisme de prévoyance sociale de test : plan CIPRES complété de comptes par branche
(le plan officiel est à obtenir auprès de la CIPRES), balance N et dossier."""

import copy

import pytest

from app.revision.frameworks import builtin, load_framework
from tests.revision_helpers import create_file
from tests.test_balances import upload

ACCOUNTS = [
    ("1011", "Réserves – prestations familiales", 1, "PF"),
    ("1013", "Réserves – pensions", 1, "PV"),
    ("21", "Immobilisations de gestion", 2, "GA"),
    ("411", "Cotisants", 4, None),
    ("52", "Banques", 5, "GA"),
    ("631", "Prestations familiales servies", 6, "PF"),
    ("633", "Pensions servies", 6, "PV"),
    ("66", "Charges de personnel", 6, "GA"),
    ("701", "Cotisations – prestations familiales", 7, "PF"),
    ("703", "Cotisations – pensions", 7, "PV"),
]
# Soldes N (débit positif) : résultat 30 M, dont PF +15 M, PV +30 M, GA −15 M.
BALANCE = {
    "101100": -50_000_000,
    "101300": -100_000_000,
    "210000": 20_000_000,
    "411000": 15_000_000,
    "520000": 145_000_000,
    "631000": 25_000_000,
    "633000": 30_000_000,
    "660000": 15_000_000,
    "701000": -40_000_000,
    "703000": -60_000_000,
}


@pytest.fixture
def ops(db):
    doc = copy.deepcopy(builtin("cipres_modele"))
    doc["version"] = "test"
    doc["comptes"] += [
        {"numero": n, "libelle": lib, "classe": c, "branche": b} for n, lib, c, b in ACCOUNTS
    ]
    fw = load_framework(db, doc)
    db.commit()
    return fw


def ops_file(client, rev, ops, **kw):  # noqa: F811
    f = create_file(client, rev, framework_id=str(ops.id), **kw)
    lines = ["Compte;Intitulé;Solde débit;Solde crédit"]
    lines += [f"{c};Compte {c};{max(v, 0) or ''};{max(-v, 0) or ''}" for c, v in BALANCE.items()]
    tb = upload(client, rev, f["id"], "balance.csv", ("\n".join(lines) + "\n").encode()).json()
    assert tb["statut"] == "accepte", tb["anomalies"]
    return f


def set_params(db, fw, *rows):
    """Paramètres réglementaires (code, valeur, branche) pour la Côte d'Ivoire, à partir de 2026."""
    from decimal import Decimal

    from app.models.revision import RegulatoryParameter

    for code, valeur, branche in rows:
        db.add(RegulatoryParameter(framework_id=fw.id, code=code, libelle=code, valeur=Decimal(valeur),
                                   pays="CI", exercice=2026, branche=branche))  # fmt: skip
    db.commit()


def launch_ops(client, rev, file, code, table, second=None, status=202, **params):
    body = {"table_id": str(table.id), "parametres": params}
    if second is not None:
        body["seconde_table_id"] = str(second.id)
    resp = client.post(
        f"/api/audit-files/{file['id']}/ops-controls/{code}", json=body, headers=rev["aud"].headers
    )
    assert resp.status_code == status, resp.text
    return resp.json()
