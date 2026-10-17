"""DAT-23 : projection des erreurs d'un échantillon MUS."""

from decimal import Decimal

import pytest

from app.analytics.sampling import Misstatement, evaluate_mus, poisson_factor
from tests.analysis_helpers import analyse, result_df
from tests.test_datasets import ctx  # noqa: F401
from tests.test_echantillon import factures  # noqa: F401


def test_evaluation_mus_calcul_de_reference():
    interval = Decimal(10_000)
    errors = [
        Misstatement(1, Decimal(2_000), Decimal(1_500)),  # taux 25 %
        Misstatement(2, Decimal(500), Decimal(0)),  # taux 100 %
        Misstatement(3, Decimal(15_000), Decimal(14_000)),  # ligne > intervalle : 1 000 réels
        Misstatement(4, Decimal(800), Decimal(900)),  # sous-évaluation
    ]
    r = evaluate_mus(errors, interval, 0.95, Decimal(60_000))
    over = r["surevaluations"]
    f0, f1, f2 = (poisson_factor(k, 0.95) for k in range(3))
    expected_upper = (
        1_000 + f0 * 10_000 + 12_500 + 1.0 * 10_000 * (f1 - f0 - 1) + 0.25 * 10_000 * (f2 - f1 - 1)
    )
    assert over["erreurs"] == 3
    assert over["erreur_lignes_superieures"] == "1000.00"
    assert over["erreur_projetee"] == "13500.00"
    assert float(over["precision_de_base"]) == pytest.approx(29_957, abs=1)
    assert float(over["limite_superieure"]) == pytest.approx(expected_upper, abs=0.05)
    assert float(over["limite_superieure"]) == pytest.approx(52_319, abs=2)
    assert r["conclusion"] == "acceptable"
    assert r["sous_evaluations"]["erreurs"] == 1
    assert r["sous_evaluations"]["erreur_projetee"] == "1250.00"  # 100/800 × 10 000
    assert evaluate_mus(errors, interval, 0.95, Decimal(50_000))["conclusion"] == "non_acceptable"
    # Sans erreur : la limite supérieure est la précision de base.
    empty = evaluate_mus([], interval, 0.95, None)
    assert (
        empty["surevaluations"]["limite_superieure"] == empty["surevaluations"]["precision_de_base"]
    )
    assert "conclusion" not in empty


def test_dat23_api(client, ctx, factures, db):  # noqa: F811
    params = {"taille": 20, "methode": "mus", "champ_montant": "montant", "graine": 7}
    sample = analyse(client, ctx, factures, "echantillon", params)
    out = result_df(db, sample)
    lines = out["ligne"].to_list()
    book = {r: Decimal(str(a)) for r, a in zip(lines, out["montant"], strict=True)}
    url = f"/api/datasets/{sample['id']}/mus-evaluations"
    body = {
        "confiance": "0.95",
        "erreur_tolerable": "40000",
        "erreurs": [
            {"ligne": lines[0], "montant_audite": str(book[lines[0]] / 2), "commentaire": "Remise"}
        ],
    }
    resp = client.post(url, json=body, headers=ctx["aud"].headers)
    assert resp.status_code == 201, resp.text
    ev = resp.json()
    assert ev["erreurs"][0]["montant_comptable"] == str(book[lines[0]])
    r = ev["resultat"]
    assert r["intervalle"] == "10050.00" and r["population"] == "201000.00"
    assert r["surevaluations"]["erreur_projetee"] == "5025.00"  # 50 % × 10 050
    assert r["conclusion"] in ("acceptable", "non_acceptable")
    assert len(client.get(url, headers=ctx["chef"].headers).json()) == 1
    bad = client.post(url, json={"erreurs": [{"ligne": 99999, "montant_audite": "1"}]},
                      headers=ctx["aud"].headers)  # fmt: skip
    assert bad.status_code == 422 and "pas dans l'échantillon" in bad.text
    dup = {"erreurs": [{"ligne": lines[1], "montant_audite": "1"}] * 2}
    assert client.post(url, json=dup, headers=ctx["aud"].headers).status_code == 422
    other = analyse(client, ctx, factures, "echantillon", {"taille": 5, "methode": "aleatoire"})
    resp = client.post(f"/api/datasets/{other['id']}/mus-evaluations", json={},
                       headers=ctx["aud"].headers)  # fmt: skip
    assert resp.status_code == 409
