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


# Plan détaillé portant les postes réservés des indicateurs (CIP-06, CIP-07).
DETAIL_ACCOUNTS = [
    ("1511", "Réserves techniques PF", 1, "PF"),
    ("1513", "Réserves techniques PV", 1, "PV"),
    ("221", "Immeubles de placement", 2, "PV"),
    ("501", "Obligations", 5, "PV"),
    ("511", "Dépôts à terme", 5, "PF"),
    ("771", "Produits des placements", 7, "PV"),
]
DETAIL_POSTES = [
    ("compte_resultat", "COT", "Cotisations émises", "produit", "70", None),
    ("compte_resultat", "PPL", "Produits des placements", "produit", "77", None),
    ("compte_resultat", "PRE", "Prestations servies", "charge", "63", None),
    ("compte_resultat", "FGE", "Frais de gestion", "charge", "66", None),
    ("bilan_actif", "CCO", "Créances sur cotisants", "actif", "41", "debit"),
    ("bilan_actif", "PLA_IMMO", "Placements immobiliers", "actif", "22", None),
    ("bilan_actif", "PLA_OBLIG", "Obligations", "actif", "50", None),
    ("bilan_actif", "PLA_DAT", "Dépôts à terme", "actif", "51", None),
    ("bilan_passif", "RTE", "Réserves techniques", "passif", "15", None),
]  # fmt: skip
FORMULAS = {
    "PC": "COT+PPL",
    "CH": "PRE+FGE",
    "CR": "CCO",
    "IM": "PLA_IMMO",
    "TA": "PLA_OBLIG+PLA_DAT",
    "RE": "RN+RTE",
}
# Soldes (débit positif) en millions.
DETAIL_N = {
    "411000": 15,
    "660000": 9.5,
    "631000": 24,
    "633000": 36,
    "221000": 30,
    "501000": 50,
    "511000": 20,
    "520000": 20,
    "701000": -40,
    "703000": -60,
    "151100": -10,
    "151300": -54,
    "771000": -4.5,
    "101300": -36,
}
DETAIL_N1 = {"411000": 10, "221000": 30, "501000": 40, "511000": 10, "520000": 20, "101300": -110}  # fmt: skip


@pytest.fixture
def ops_detail(db):
    doc = copy.deepcopy(builtin("cipres_modele"))
    doc["version"] = "detail"
    doc["comptes"] += [{"numero": n, "libelle": lib, "classe": c, "branche": b}
                       for n, lib, c, b in ACCOUNTS + DETAIL_ACCOUNTS]  # fmt: skip
    doc["postes"] += [{"etat": e, "code": c, "libelle": lib, "nature": nat, "racines": [{"racine": r, "sens": s}]}
                      for e, c, lib, nat, r, s in DETAIL_POSTES]  # fmt: skip
    for p in doc["postes"]:
        if p["code"] in FORMULAS:
            p["formule"] = FORMULAS[p["code"]]
    fw = load_framework(db, doc)
    db.commit()
    return fw


def balance_csv(closing, opening=None) -> bytes:
    """Balance en millions ; avec `opening`, colonnes d'à-nouveaux et de mouvements."""
    opening = opening or {}
    m = 1_000_000

    def pair(v):
        return [f"{max(v, 0) * m:.0f}" if v > 0 else "", f"{max(-v, 0) * m:.0f}" if v < 0 else ""]

    lines = ["Compte;Intitulé;Solde début débit;Solde début crédit;Mouvements débit;Mouvements crédit;"
             "Solde fin débit;Solde fin crédit"]  # fmt: skip
    for c in sorted(set(closing) | set(opening)):
        o, f = opening.get(c, 0), closing.get(c, 0)
        lines.append(";".join([c, f"Compte {c}", *pair(o), *pair(f - o), *pair(f)]))
    return ("\n".join(lines) + "\n").encode()


def detail_file(client, rev, fw, exercice=2026):
    f = create_file(client, rev, exercice=exercice, framework_id=str(fw.id), pays="CI")
    opening = {c: v for c, v in DETAIL_N1.items() if c[0] in "12345"}
    for periode, content in (
        ("N-1", balance_csv(DETAIL_N1)),
        ("N", balance_csv(DETAIL_N, opening)),
    ):
        tb = upload(client, rev, f["id"], "b.csv", content, periode=periode).json()
        assert tb["statut"] == "accepte", tb["anomalies"]
    return f
