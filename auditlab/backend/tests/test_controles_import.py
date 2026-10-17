"""REV-06 : contrôles d'intégrité bloquants à l'import des données comptables."""

from tests import revision_data as data
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_balances import upload


def codes(tb: dict) -> list[str]:
    return [a["code"] for a in tb["anomalies"]]


def test_rev06_balance_desequilibree_et_ligne_incoherente(client, rev):  # noqa: F811
    f = create_file(client, rev)
    head = "Compte;Intitulé;Solde début débit;Solde début crédit;Mouvements débit;Mouvements crédit;Solde fin débit;Solde fin crédit\n"
    bad = head + (
        "101300;Capital;;1 000;;;;1 000\n521100;Banque;1 000;;500;;1 600;\n"  # 1 000 + 500 ≠ 1 600
    )
    tb = upload(client, rev, f["id"], "bad.csv", bad.encode()).json()
    assert tb["statut"] == "rejete"
    assert codes(tb) == ["desequilibre", "desequilibre", "ligne_incoherente"]
    assert tb["anomalies"][2]["compte"] == "521100"
    assert "1 000 + mouvements 500 ≠ solde 1 600" in tb["anomalies"][2]["message"]
    # Une balance rejetée n'est jamais active : aucune balance N disponible.
    history = client.get(f"/api/audit-files/{f['id']}/imports", headers=rev["aud"].headers).json()
    assert [(h["statut"], h["deleted_at"]) for h in history] == [("rejete", None)]


def test_rev06_comptes_hors_plan(client, rev):  # noqa: F811
    f = create_file(client, rev)
    content = (
        "Compte;Intitulé;Solde débit;Solde crédit\n101300;Capital;;1 000\n001500;Divers;1 000;\n"
    )
    tb = upload(client, rev, f["id"], "hp.csv", content.encode()).json()
    assert tb["statut"] == "rejete" and codes(tb) == ["hors_plan"]
    assert tb["anomalies"][0]["compte"] == "001500"
    # Grand livre : même contrôle.
    gl = "Date;Journal;Compte;Débit;Crédit\n01/02/2026;OD;001500;100;\n01/02/2026;OD;521100;;100\n"
    tb = upload(client, rev, f["id"], "gl.csv", gl.encode(), type="grand_livre").json()
    assert tb["statut"] == "rejete" and codes(tb) == ["hors_plan"]


def test_rev06_a_nouveaux(client, rev):  # noqa: F811
    f = create_file(client, rev)
    # Balance N importée en premier : le contrôle est reporté à l'import de N-1.
    tb = upload(client, rev, f["id"], "n.csv", data.sage_csv()).json()
    assert tb["statut"] == "accepte"
    assert [w["code"] for w in tb["avertissements"]] == ["a_nouveaux_differes"]
    # N-1 dont la banque ne correspond pas aux à-nouveaux N : rejetée.
    n1 = dict(data.N1, **{"521100": 6_500_000, "571100": 300_000})
    tb = upload(client, rev, f["id"], "n1.xlsx", data.odoo_xlsx(n1), periode="N-1").json()
    assert tb["statut"] == "rejete" and codes(tb) == ["a_nouveaux", "a_nouveaux"]
    assert [a["compte"] for a in tb["anomalies"]] == ["521100", "571100"]
    # La bonne N-1 est acceptée (l'affectation du résultat N-1 en report à nouveau est admise).
    tb = upload(client, rev, f["id"], "n1.xlsx", data.odoo_xlsx(), periode="N-1").json()
    assert tb["statut"] == "accepte" and tb["avertissements"] == []
    # Nouvelle balance N dont les capitaux propres d'ouverture ne reprennent pas le résultat.
    opening = data.opening_n()
    opening["121000"] += 200_000
    opening["101300"] -= 200_000
    tb = upload(client, rev, f["id"], "n2.csv", data.sage_csv(opening=opening)).json()
    assert tb["statut"] == "accepte", tb["anomalies"]  # réaffectation interne à la classe 1
    opening["521100"] += 50_000
    opening["101300"] -= 50_000
    tb = upload(client, rev, f["id"], "n3.csv", data.sage_csv(opening=opening)).json()
    assert tb["statut"] == "rejete" and codes(tb) == ["a_nouveaux", "a_nouveaux"]
    assert "Capitaux propres" in tb["anomalies"][1]["message"]
    # Balance N sans à-nouveaux (intégrés aux mouvements) : rejetée, avec une indication.
    tb = upload(client, rev, f["id"], "n4.csv", data.sage_csv(opening={})).json()
    assert tb["statut"] == "rejete"
    assert [w["code"] for w in tb["avertissements"]] == ["a_nouveaux_absents"]


def test_rev06_grand_livre_et_balance(client, rev):  # noqa: F811
    f = create_file(client, rev)
    skew = {"601100": 1_000, "622000": -1_000}
    tb = upload(client, rev, f["id"], "gl.csv", data.ledger_csv(skew=skew), type="grand_livre")
    tb = tb.json()
    assert tb["statut"] == "accepte"
    assert [w["code"] for w in tb["avertissements"]] == ["grand_livre_differe"]
    # La balance N importée ensuite ne concorde pas avec le grand livre actif : rejetée.
    tb = upload(client, rev, f["id"], "n.csv", data.sage_csv()).json()
    assert tb["statut"] == "rejete" and codes(tb) == ["grand_livre", "grand_livre"]
    assert tb["anomalies"][0]["compte"] == "601100"
    # Grand livre corrigé (les écritures d'à-nouveaux du journal AN sont exclues), puis balance.
    tb = upload(client, rev, f["id"], "gl2.csv", data.ledger_csv(), type="grand_livre").json()
    assert tb["statut"] == "accepte"
    assert upload(client, rev, f["id"], "n.csv", data.sage_csv()).json()["statut"] == "accepte"
    # Un grand livre déséquilibré est rejeté.
    tb = upload(client, rev, f["id"], "gl3.csv", data.ledger_csv(skew={"601100": 5}),
                type="grand_livre").json()  # fmt: skip
    assert tb["statut"] == "rejete" and codes(tb) == ["desequilibre", "grand_livre"]


def test_rev06_balance_auxiliaire(client, rev):  # noqa: F811
    f = create_file(client, rev)
    aux = "Code tiers;Nom;Solde débit;Solde crédit\nC001;Client A;4 000 000;\nC002;Client B;2 000 000;\n"
    resp = upload(client, rev, f["id"], "clients.csv", aux.encode(), type="aux_clients")
    assert resp.status_code == 422 and "compte collectif" in resp.text
    tb = upload(client, rev, f["id"], "clients.csv", aux.encode(), type="aux_clients",
                compte_collectif="411").json()  # fmt: skip
    assert tb["statut"] == "accepte"
    assert [w["code"] for w in tb["avertissements"]] == ["auxiliaire_differe"]
    upload(client, rev, f["id"], "n.csv", data.sage_csv())
    tb = upload(client, rev, f["id"], "clients.csv", aux.encode(), type="aux_clients",
                compte_collectif="411").json()  # fmt: skip
    assert tb["statut"] == "rejete" and codes(tb) == ["auxiliaire"]
    assert (
        "6 000 000" in tb["anomalies"][0]["message"]
        and "7 000 000" in tb["anomalies"][0]["message"]
    )
