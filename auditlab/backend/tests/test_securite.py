"""Tests de sécurité attendus par le cahier des charges : injection SQL dans les expressions
de filtre (NF-05) et tentatives de sortie du bac à sable des scripts (DAT-27)."""

import polars as pl
import pytest

from app.analytics.store import absolute
from app.security.roles import Role
from tests import helpers
from tests.analysis_helpers import analyse
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401

PAYLOADS = [
    "montant > 0 OR read_csv('/etc/passwd') IS NOT NULL",
    "montant > 0; DROP TABLE datasets; --",
    "getenv('AUDITLAB_DATABASE_URL') = 'x'",
    "montant > 0) UNION SELECT * FROM read_parquet('/tmp/*.parquet') --",
    "[montant] > 0 AND (SELECT 1) = 1",
]


@pytest.fixture
def table(db, ctx):  # noqa: F811
    df = pl.DataFrame({"piece": ["P1", "P2"], "montant": [10.0, 20.0]})
    return make_dataset(db, ctx["mission"]["id"], df, "Paiements")


@pytest.mark.parametrize("payload", PAYLOADS)
def test_injection_expression_extraction(client, ctx, table, payload):  # noqa: F811
    # Analyse refusée à l'exécution : table en erreur, l'expression n'est jamais passée à DuckDB.
    resp = analyse(client, ctx, table, "extraction", {"expression": payload})
    assert resp["statut"] == "erreur" and resp["erreur"].startswith("Expression :"), resp["erreur"]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_injection_champ_calcule(client, ctx, table, payload):  # noqa: F811
    resp = client.post(f"/api/datasets/{table.id}/views", headers=ctx["da"].headers,
                       json={"nom": "Vue", "champs": [{"nom": "x", "expression": payload}]})  # fmt: skip
    assert resp.status_code == 422, resp.text


def test_injection_grille(client, ctx, table):  # noqa: F811
    url, h = f"/api/datasets/{table.id}/rows", ctx["aud"].headers
    bad_sort = {"tri": [{"colonne": 'montant" DESC; DROP TABLE datasets; --'}]}
    assert client.post(url, json=bad_sort, headers=h).status_code == 422
    bad_column = {"colonnes": ["piece", "read_csv('/etc/passwd')"]}
    assert client.post(url, json=bad_column, headers=h).status_code == 422
    # Valeurs : toujours paramètres, donc comparées comme du texte, sans effet.
    payload = {"filtres": {"piece": {"filterType": "text", "type": "equals", "filter": "x' OR '1'='1"}},
               "recherche": "'; DROP TABLE datasets; --"}  # fmt: skip
    page = client.post(url, json=payload, headers=h).json()
    assert page["lignes"] == []
    assert client.post(url, json={}, headers=h).json()["total"] == 2


def _run(client, ctx, code, entrees=()):  # noqa: F811
    da = ctx["da"].headers
    s = client.post(f"{ctx['url']}/scripts", headers=da,
                    json={"nom": "Évasion", "code": code, "entrees": list(entrees)}).json()  # fmt: skip
    run = client.post(f"/api/scripts/{s['id']}/runs", headers=da).json()
    return client.get(f"/api/script-runs/{run['id']}", headers=da).json()


def _other_mission_parquet(client, db, account):
    chef = account(Role.CHEF_MISSION)
    other = helpers.mission(client, chef.headers, titre="Mission confidentielle")
    secret = make_dataset(db, other["id"], pl.DataFrame({"salaire": [99_999.0]}), "Salaires")
    return str(absolute(secret.chemin_parquet))


def test_evasion_manifeste_falsifie(client, ctx, db, account):  # noqa: F811
    """Le script désigne le Parquet d'une autre mission dans son manifeste de sorties."""
    target = _other_mission_parquet(client, db, account)
    forged = "audit._OUTPUTS.append({'nom': 'Vol', 'fichier': FICHIER})\naudit._flush()\n"
    for code in (
        forged.replace("FICHIER", repr(target)),
        "import os\nos.symlink(CIBLE, 'out/table_0.parquet')\n".replace("CIBLE", repr(target))
        + forged.replace("FICHIER", "'out/table_0.parquet'"),
        forged.replace("FICHIER", repr("out/../../../.." + target)),
    ):
        run = _run(client, ctx, code)
        assert run["statut"] == "erreur" and run["erreur"].startswith("Sortie refusée"), run[
            "erreur"
        ]
        assert run["tables"] == []
    datasets = client.get(f"{ctx['url']}/datasets", headers=ctx["da"].headers).json()
    assert "Vol" not in [d["nom"] for d in datasets]


def test_evasion_base_de_donnees_et_fichiers(client, ctx):  # noqa: F811
    code = (
        "import socket\n"
        "for port in (5432, 6379, 8000):\n"
        "    s = socket.socket(); s.settimeout(2)\n"
        "    try:\n"
        "        s.connect(('127.0.0.1', port)); print('ouvert', port)\n"
        "    except OSError as exc:\n"
        "        print('fermé', port, exc.errno)\n"
    )
    run = _run(client, ctx, code)
    assert run["statut"] == "termine" and "ouvert" not in run["sortie"], run["sortie"]
    run = _run(client, ctx, "audit.import_csv('../../../../etc/passwd')\n")
    assert run["statut"] == "erreur" and "absent des entrées" in run["erreur"]


def test_evasion_indicateurs_et_sorties_hors_limites(client, ctx):  # noqa: F811
    code = "audit._METRICS.update({f'm{i}': i for i in range(500)})\naudit._flush()\n"
    assert "Au plus 100 indicateurs" in _run(client, ctx, code)["erreur"]
    code = "audit._METRICS['x'] = 'texte'\naudit._flush()\n"
    assert "non numérique" in _run(client, ctx, code)["erreur"]
