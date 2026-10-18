"""IFR-02 : assistants de calcul des retraitements IFRS (cas calculés à la main)."""

from decimal import Decimal

import pytest

from app.revision.frameworks import builtin, load_framework
from app.revision.ifrs_assistants import AssistantError, run
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load

Q = Decimal(1)


def entry(result) -> list[tuple[str, str, str]]:
    lines = result["lignes"]
    debit = sum(Decimal(ln.get("debit", "0")) for ln in lines)
    credit = sum(Decimal(ln.get("credit", "0")) for ln in lines)
    assert debit == credit, lines  # écriture équilibrée
    return [(ln["compte"], ln.get("debit", ""), ln.get("credit", "")) for ln in lines]


def test_ifrs16_location():
    r = run("ifrs16", {"loyer_annuel": "100000", "duree_annees": 5, "taux_actualisation": "10"}, Q)
    assert (
        r["calcul"]["valeur_actualisee"] == "379079"
        and r["calcul"]["amortissement_annuel"] == "75816"
    )
    assert entry(r) == [
        ("231000", "379079", ""),
        ("172000", "", "379079"),
        ("172000", "62092", ""),
        ("671000", "37908", ""),
        ("622000", "", "100000"),
        ("681300", "75816", ""),
        ("283100", "", "75816"),
    ]
    later = run(
        "ifrs16",
        {
            "loyer_annuel": "100000",
            "duree_annees": 5,
            "taux_actualisation": "10",
            "annees_ecoulees": 2,
            "paiement": "debut",
        },
        Q,
    )
    entry(later)
    assert later["calcul"]["annee_en_cours"] == 3
    with pytest.raises(AssistantError):
        run(
            "ifrs16",
            {
                "loyer_annuel": "100000",
                "duree_annees": 5,
                "taux_actualisation": "10",
                "annees_ecoulees": 5,
            },
            Q,
        )


def test_ias19_indemnites():
    r = run(
        "ias19",
        {
            "taux_actualisation": "5",
            "mois_par_annee": "1",
            "age_retraite": 60,
            "salaries": [{"nom": "Koné", "salaire_annuel": "1200000", "anciennete": 10, "age": 50}],
        },
        Q,
    )
    assert r["calcul"]["engagement"] == "613913"
    assert entry(r) == [("661000", "613913", ""), ("196000", "", "613913")]
    with pytest.raises(AssistantError, match="manquant"):
        run("ias19", {"taux_actualisation": "5", "age_retraite": 60, "salaries": []}, Q)


def test_ifrs9_ias16_ias12_ifrs15():
    r = run(
        "ifrs9",
        {
            "tranches": [
                {"libelle": "0-180", "montant": "1000000", "taux_perte": "1"},
                {"libelle": "181-365", "montant": "500000", "taux_perte": "10"},
            ],
            "depreciation_comptabilisee": "20000",
        },
        Q,
    )
    assert r["calcul"]["pertes_attendues"] == "60000"
    assert entry(r) == [("691000", "40000", ""), ("491000", "", "40000")]
    r = run(
        "ias16",
        {
            "cout": "10000000",
            "annees_ecoulees": 2,
            "dotation_comptabilisee": "1000000",
            "cumul_anterieur_comptabilise": "2000000",
            "composants": [
                {"libelle": "Structure", "quote_part": "60", "duree": 20},
                {"libelle": "Toiture", "quote_part": "40", "duree": 5},
            ],
        },
        Q,
    )
    assert entry(r) == [
        ("681300", "100000", ""),
        ("121000", "200000", ""),
        ("283100", "", "300000"),
    ]
    r = run(
        "ias12", {"taux_impot": "25", "effet_resultat": "-313724", "effet_capitaux": "-313724"}, Q
    )
    assert entry(r) == [("449800", "78431", ""), ("891000", "", "78431")]
    r = run(
        "ifrs15",
        {
            "prix_contrat": "1000000",
            "produit_comptabilise": "1000000",
            "obligations": [
                {"libelle": "Équipement", "prix_vente_spontane": "900000", "pct_execution": "100"},
                {"libelle": "Maintenance", "prix_vente_spontane": "300000", "pct_execution": "25"},
            ],
        },
        Q,
    )
    assert r["calcul"]["produit_ifrs"] == "812500"
    assert entry(r) == [("477000", "", "187500"), ("701100", "187500", "")]
    with pytest.raises(AssistantError, match="100 %"):
        run("ias16", {"cout": "1000", "composants": [{"quote_part": "50", "duree": 5}]}, Q)
    with pytest.raises(AssistantError, match="inconnu"):
        run("ias99", {}, Q)


def test_ifr02_assistant_dans_le_dossier(client, rev, db):  # noqa: F811
    load_framework(db, builtin("ifrs_2024"))
    db.commit()
    f = create_file(client, rev)
    base = f"/api/audit-files/{f['id']}"
    aud = rev["aud"].headers
    load(client, rev, f["id"])
    assert len(client.get("/api/ifrs/assistants", headers=aud).json()) == 6
    params = {"loyer_annuel": "100000", "duree_annees": 5, "taux_actualisation": "10"}
    preview = client.post(
        f"{base}/ifrs/assistants/ifrs16", json={"parametres": params}, headers=aud
    ).json()
    assert "retraitement" not in preview and preview["norme"] == "IFRS 16"
    created = client.post(
        f"{base}/ifrs/assistants/ifrs16", json={"parametres": params, "creer": True}, headers=aud
    ).json()
    adj = created["retraitement"]
    assert (adj["type"], adj["norme"], adj["statut"], adj["date_ecriture"]) == (
        "retraitement_ifrs",
        "IFRS 16",
        "proposee",
        "2026-12-31",
    )
    client.post(f"/api/adjustments/{adj['id']}/decision", json={"statut": "acceptee"}, headers=aud)
    # IAS 12 : bases reprises des retraitements validés (−13 724 sur le résultat).
    tax = client.post(
        f"{base}/ifrs/assistants/ias12", json={"parametres": {"taux_impot": "25"}}, headers=aud
    ).json()
    assert (
        Decimal(tax["calcul"]["base_resultat"]) == -13724
        and tax["calcul"]["impot_differe"] == "3431"
    )
    bad = client.post(f"{base}/ifrs/assistants/ias19", json={"parametres": {}}, headers=aud)
    assert bad.status_code == 422
