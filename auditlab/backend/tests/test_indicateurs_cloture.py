"""RCO-26 : comparatif N/N-1 et indicateurs de gestion de la clôture."""

from tests import revision_data as data
from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload


def test_rco26_indicateurs(client, cabinet):  # noqa: F811
    collab = cabinet["collab"]
    closing = open_closing(client, cabinet, new_client(client, cabinet))
    fid, url = closing["audit_file_id"], f"/api/closings/{closing['id']}/management"
    assert client.get(url, headers=collab.headers).status_code == 409  # aucune balance
    rev = {"aud": collab}
    n1 = upload(client, rev, fid, "n1.xlsx", data.odoo_xlsx(data.N1), periode="N-1").json()
    assert n1["statut"] == "accepte", n1
    assert upload(client, rev, fid, "n.csv", data.sage_csv()).json()["statut"] == "accepte"
    result = client.get(url, headers=collab.headers).json()
    assert result["n1_disponible"]
    ind = {i["code"]: i for i in result["indicateurs"]}
    assert {i["famille"] for i in result["indicateurs"]} >= {
        "activite",
        "marge",
        "tresorerie",
        "endettement",
    }
    ca = ind["chiffre_affaires"]
    assert (ca["N"], ca["N-1"], ca["variation"], ca["variation_pct"]) == (
        "40000000",
        "30000000",
        "10000000",
        "33.3",
    )
    assert (
        ind["tresorerie_nette"]["N"] == "13700000" and ind["tresorerie_nette"]["N-1"] == "6800000"
    )
    assert (
        ind["taux_marge"]["unite"] == "pourcentage" and ind["taux_marge"]["variation_pct"] is None
    )
    xb = next(ln for ln in result["comparatif"] if ln["code"] == "XB")
    assert xb["variation_pct"] == "33.3" and xb["etat"] == "compte_resultat"
    for fmt, magic in (("pdf", b"%PDF"), ("docx", b"PK")):
        resp = client.get(f"{url}/export?format={fmt}", headers=collab.headers)
        assert resp.status_code == 200 and resp.content[: len(magic)] == magic
