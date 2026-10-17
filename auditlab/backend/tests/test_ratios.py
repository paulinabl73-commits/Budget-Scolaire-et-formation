"""REV-13 : ratios financiers comparés sur trois exercices."""

from tests import revision_data as data
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_balances import upload


def test_rev13_ratios_sur_trois_exercices(client, rev):  # noqa: F811
    aud = rev["aud"].headers
    # Dossier 2025 : N-1 (2024) = soldes de 2025 réduits de 20 %, N (2025) = jeu N-1 de référence.
    n2 = {c: v * 4 // 5 for c, v in data.N1.items()}
    opening = {c: v for c, v in n2.items() if c[0] in "12345"}
    opening["121000"] -= 1_200_000  # résultat 2024 affecté en report à nouveau
    old = create_file(client, rev, exercice=2025)
    assert (
        upload(client, rev, old["id"], "2024.xlsx", data.odoo_xlsx(n2), periode="N-1").json()[
            "statut"
        ]
        == "accepte"
    )
    tb = upload(client, rev, old["id"], "2025.csv", data.sage_csv(data.N1, opening=opening)).json()
    assert tb["statut"] == "accepte", tb["anomalies"]
    # Dossier 2026 : N-1 repris du dossier 2025, N importé.
    new = create_file(client, rev, exercice=2026)
    url = f"/api/audit-files/{new['id']}/ratios"
    assert client.get(url, headers=aud).status_code == 409  # aucune balance N
    assert upload(client, rev, new["id"], "2026.csv", data.sage_csv()).json()["statut"] == "accepte"
    result = client.get(url, headers=aud).json()
    assert result["exercices"] == [
        {"periode": "N", "exercice": 2026, "disponible": True},
        {"periode": "N-1", "exercice": 2025, "disponible": True},
        {"periode": "N-2", "exercice": 2024, "disponible": True},
    ]
    ratios = {r["code"]: r for r in result["ratios"]}
    assert {r["famille"] for r in result["ratios"]} == {
        "liquidite",
        "solvabilite",
        "rentabilite",
        "delais",
    }
    assert ratios["autonomie_financiere"]["valeurs"] == {
        "N": "63.41",
        "N-1": "54.62",
        "N-2": "54.62",
    }
    assert ratios["rentabilite_nette"]["valeurs"]["N"] == "17.75"
    assert (
        ratios["delai_clients"]["valeurs"]["N"] == "63"
        and ratios["delai_clients"]["unite"] == "jours"
    )
    # Le dossier 2025 n'a pas de dossier antérieur : N-2 indisponible.
    old_ratios = client.get(f"/api/audit-files/{old['id']}/ratios", headers=aud).json()
    assert old_ratios["exercices"][2]["disponible"] is False
    assert all(r["valeurs"]["N-2"] is None for r in old_ratios["ratios"])
