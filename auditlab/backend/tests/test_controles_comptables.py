"""RCO-08 : contrôles automatiques sur balance et grand livre."""

from collections import defaultdict

from app.models import Dataset
from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload

ENTRIES = [  # journal, pièce, [(compte, débit, crédit)]
    ("BQ", "B1", [("521000", 1_000_000, 0), ("101000", 0, 1_000_000)]),
    ("AC", "A1", [("601000", 40_000, 0), ("401100", 0, 40_000)]),
    ("AC", "A1", [("601000", 40_000, 0), ("401100", 0, 40_000)]),  # saisie en double
    ("BQ", "B2", [("401100", 170_000, 0), ("521000", 0, 170_000)]),  # fournisseur débiteur
    ("VT", "V1", [("411100", 310_000, 0), ("701000", 0, 310_000)]),
    ("BQ", "B3", [("521000", 10_000, 0), ("411100", 0, 10_000)]),
    ("BQ", "B4", [("409000", 20_000, 0), ("521000", 0, 20_000)]),
    ("BQ", "B6", [("419000", 10_000, 0), ("521000", 0, 10_000)]),  # B5 manquante ; avance débitrice
    ("BQ", "B7", [("471000", 5_000, 0), ("521000", 0, 5_000)]),  # compte d'attente
    ("CA", "C1", [("601000", 15_000, 0), ("571000", 0, 15_000)]),  # caisse créditrice
    ("OD", "", [("601000", 1_000, 0), ("401100", 0, 1_000)]),  # écriture sans pièce
]  # fmt: skip


def files():
    gl = ["Date;Journal;Pièce;Compte;Libellé;Débit;Crédit"]
    net: dict[str, int] = defaultdict(int)
    for entry in ENTRIES:
        journal, piece, lines = entry
        i = ENTRIES.index(entry)  # une saisie en double garde la date de l'original
        for compte, d, c in lines:
            gl.append(
                f"{10 + i:02d}/03/2026;{journal};{piece};{compte};Écriture {piece};{d or ''};{c or ''}"
            )
            net[compte] += d - c
    bal = ["Compte;Intitulé;Solde débit;Solde crédit"]
    bal += [f"{c};Compte {c};{max(v, 0) or ''};{max(-v, 0) or ''}" for c, v in sorted(net.items())]
    return ("\n".join(bal) + "\n").encode(), ("\n".join(gl) + "\n").encode()


def test_rco08_controles(client, cabinet, db):  # noqa: F811
    collab = cabinet["collab"]
    c = new_client(client, cabinet)
    closing = open_closing(client, cabinet, c)
    fid = closing["audit_file_id"]
    ctx = {"aud": collab}
    balance, ledger = files()
    for name, content, kind in (("b.csv", balance, "balance"), ("gl.csv", ledger, "grand_livre")):
        tb = upload(client, ctx, fid, name, content, type=kind).json()
        assert tb["statut"] == "accepte", tb["anomalies"]
    data = client.get(f"/api/audit-files/{fid}/accounting-controls", headers=collab.headers).json()
    assert {r["compte"]: r["anomalie"] for r in data["soldes_anormaux"]} == {
        "401100": "Fournisseur débiteur", "419000": "Avance de client débitrice",
        "471000": "Compte d'attente non soldé", "571000": "Caisse créditrice"}  # fmt: skip
    assert "401100" in {t["compte"] for t in data["tiers_non_lettres"]}
    launched = client.post(
        f"/api/audit-files/{fid}/accounting-controls/ledger", headers=collab.headers
    ).json()
    assert [x["controle"] for x in launched["lances"]] == [
        "Écritures sans pièce", "Ruptures de numérotation des pièces", "Doublons d'écritures"]  # fmt: skip
    results = {x["controle"]: db.get(Dataset, x["dataset_id"]) for x in launched["lances"]}
    for ds in results.values():
        db.refresh(ds)
        assert ds.statut == "pret", ds.erreur
    assert results["Écritures sans pièce"].nb_lignes == 2
    seq = results["Ruptures de numérotation des pièces"].resultat
    assert (seq["manquants"], seq["doubles"], seq["groupes"]) == (1, 0, 4)
    assert results["Doublons d'écritures"].nb_lignes == 4  # deux lignes, chacune en double
    data = client.get(f"/api/audit-files/{fid}/accounting-controls", headers=collab.headers).json()
    assert len(data["analyses"]) == 3
