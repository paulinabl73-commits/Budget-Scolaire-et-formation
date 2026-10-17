"""REV-05 : import des balances, balances auxiliaires et grand livre ; reprise N-1 (REV-04)."""

from decimal import Decimal

import pytest

from app.revision.balances import ImportError_, clean_account, parse_amount, parse_date
from tests import revision_data as data
from tests.revision_helpers import create_file, rev  # noqa: F401


def upload(client, rev, file_id, name, content, acc="aud", **form):  # noqa: F811
    form = {"periode": "N", "type": "balance", **form}
    resp = client.post(f"/api/audit-files/{file_id}/imports", files={"file": (name, content)},
                       data=form, headers=rev[acc].headers)  # fmt: skip
    return resp


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1 234 567,89", "1234567.89"), ("1.234,56", "1234.56"), ("1,234.56", "1234.56"),
     ("(450,00)", "-450.00"), ("12-", "-12"), ("", "0"), (1500, "1500"), ("1 000", "1000"),
     ("12.000.000", "12000000"), ("-", "0")],
)  # fmt: skip
def test_montants(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


def test_lectures_diverses():
    with pytest.raises(ImportError_):
        parse_amount("douze")
    assert (
        str(parse_date("31/12/2026")) == "2026-12-31" and str(parse_date("46022")) == "2025-12-31"
    )
    with pytest.raises(ImportError_):
        parse_date("32/13/2026")
    assert clean_account("401 100") == "401100" and clean_account("411100.0") == "411100"


def test_rev05_balance_sage_et_odoo(client, rev):  # noqa: F811
    f = create_file(client, rev)
    resp = upload(client, rev, f["id"], "balance_N.csv", data.sage_csv(), logiciel="sage")
    assert resp.status_code == 201, resp.text
    tb = resp.json()
    assert tb["statut"] == "accepte", tb["anomalies"]
    assert tb["nb_lignes"] == 27 and len(tb["sha256"]) == 64
    assert tb["totaux"]["solde_debit"] == tb["totaux"]["solde_credit"] == "67600000.00"
    lines = client.get(f"/api/trial-balances/{tb['id']}/lines", headers=rev["da"].headers).json()
    banque = next(x for x in lines if x["compte"] == "521200")
    assert banque["solde_credit"] == "800000.00" and banque["libelle"] == "Banque BICICI"
    # Balance N-1 façon Odoo (colonnes signées), en Excel.
    resp = upload(
        client, rev, f["id"], "balance_N-1.xlsx", data.odoo_xlsx(), periode="N-1", logiciel="odoo"
    )
    assert resp.status_code == 201 and resp.json()["statut"] == "accepte", resp.text
    n1 = client.get(
        f"/api/trial-balances/{resp.json()['id']}/lines", headers=rev["aud"].headers
    ).json()
    capital = next(x for x in n1 if x["compte"] == "101300")
    assert capital["solde_credit"] == "10000000.00" and capital["mouvement_credit"] == "10000000.00"
    # Un nouvel import remplace le précédent ; l'historique reste visible.
    upload(client, rev, f["id"], "balance_N_v2.csv", data.sage_csv())
    history = client.get(f"/api/audit-files/{f['id']}/imports", headers=rev["aud"].headers).json()
    balances_n = [h for h in history if h["periode"] == "N" and h["type"] == "balance"]
    assert len(balances_n) == 2 and sum(1 for h in balances_n if h["deleted_at"] is None) == 1


def test_rev05_grand_livre_et_auxiliaire(client, rev, db):  # noqa: F811
    from app.models import Dataset

    f = create_file(client, rev)
    upload(client, rev, f["id"], "balance.csv", data.sage_csv())
    resp = upload(client, rev, f["id"], "gl.csv", data.ledger_csv(), type="grand_livre")
    assert resp.status_code == 201 and resp.json()["statut"] == "accepte", resp.text
    gl = resp.json()
    ds = db.get(Dataset, gl["dataset_id"])
    assert ds.nb_lignes == gl["nb_lignes"] and [c["nom"] for c in ds.schema][:4] == [
        "date",
        "journal",
        "piece",
        "compte",
    ]
    assert {c["nom"]: c["type"] for c in ds.schema}["debit"] == "decimal"
    aux = "Code tiers;Nom;Solde débit;Solde crédit\nC001;Client A;4 000 000;\nC002;Client B;3 000 000;\n"
    resp = upload(
        client,
        rev,
        f["id"],
        "clients.csv",
        aux.encode(),
        type="aux_clients",
        compte_collectif="411",
    )
    assert resp.status_code == 201 and resp.json()["nb_lignes"] == 2


def test_rev05_erreurs(client, rev):  # noqa: F811
    f = create_file(client, rev)
    for name, content, form, message in [
        ("x.pdf", b"%PDF", {}, "Format attendu"),
        ("x.csv", b"a;b\n1;2\n", {}, "en-tête introuvable"),
        ("x.csv", data.sage_csv(), {"periode": "N+1"}, "inconnu"),
        ("x.csv", data.ledger_csv(), {"type": "grand_livre", "periode": "N-1"}, "exercice N"),
        ("x.csv", data.sage_csv(), {"correspondance": "[1]"}, "objet JSON"),
    ]:
        resp = upload(client, rev, f["id"], name, content, **form)
        assert resp.status_code == 422 and message in resp.text, (name, resp.text)
    assert upload(client, rev, f["id"], "x.csv", data.sage_csv(), acc="da").status_code == 403
    # Correspondance imposée par l'utilisateur.
    odd = "Cpt;Lib;Deb;Cre\n101300;Capital;;10 000 000\n521100;Banque;10 000 000;\n"
    resp = upload(client, rev, f["id"], "odd.csv", odd.encode(),
                  correspondance='{"Cpt": "compte", "Lib": "libelle", "Deb": "solde_debit", "Cre": "solde_credit"}')  # fmt: skip
    assert resp.status_code == 201 and resp.json()["nb_lignes"] == 2


def test_rev04_reprise_de_la_balance_n_moins_1(client, rev):  # noqa: F811
    old = create_file(client, rev, exercice=2025)
    upload(client, rev, old["id"], "balance_2025.csv", data.sage_csv(data.N1, opening={}))
    new = create_file(client, rev, exercice=2026)
    imports = client.get(f"/api/audit-files/{new['id']}/imports", headers=rev["aud"].headers).json()
    assert [(i["periode"], i["statut"]) for i in imports] == [("N-1", "accepte")]
    assert imports[0]["nom_fichier"] == "Reprise de la balance N du dossier 2025"
    lines = client.get(
        f"/api/trial-balances/{imports[0]['id']}/lines", headers=rev["aud"].headers
    ).json()
    assert len(lines) == len(data.N1)
