"""RCO-10 : rapprochement des tiers avec les balances auxiliaires et des banques avec les relevés."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload
from tests.test_controles_comptables import files


def test_rco10_rapprochements(client, cabinet):  # noqa: F811
    collab = cabinet["collab"]
    c = new_client(client, cabinet)
    fid = open_closing(client, cabinet, c)["audit_file_id"]
    ctx = {"aud": collab}
    balance, _ = files()
    upload(client, ctx, fid, "b.csv", balance)
    # Clôture : l'écart avec le compte collectif est un avertissement, à rapprocher.
    aux = "Code tiers;Nom;Solde débit;Solde crédit\nC001;Client A;200 000;\nC002;Client B;90 000;\n"
    tb = upload(
        client, ctx, fid, "clients.csv", aux.encode(), type="aux_clients", compte_collectif="411"
    ).json()
    assert tb["statut"] == "accepte" and [w["code"] for w in tb["avertissements"]] == [
        "auxiliaire_ecart"
    ]
    data = client.get(f"/api/audit-files/{fid}/reconciliations", headers=collab.headers).json()
    [clients] = data["auxiliaires"]
    assert (clients["total_auxiliaire"], clients["solde_collectif"], clients["ecart"]) == (
        "290000.00", "300000.00", "10000.00")  # fmt: skip
    assert not clients["rapproche"] and clients["tiers"][0]["code"] == "C001"
    assert "521000" in data["banques"]["comptes_sans_rapprochement"]
