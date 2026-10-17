"""REV-08 à REV-10 : affectation des comptes aux postes, comptes à double sens, comptes non
affectés et aperçu des états."""

from sqlalchemy import select

from app.models import StatementLine
from tests import revision_data as data
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_balances import upload


def load(client, rev, file_id, n1=None):  # noqa: F811
    n1 = n1 or data.N1
    opening = {c: v for c, v in n1.items() if c[0] in "12345"}
    opening["121000"] -= data.RESULTAT_N1
    tb = upload(client, rev, file_id, "n1.xlsx", data.odoo_xlsx(n1), periode="N-1").json()
    assert tb["statut"] == "accepte", tb["anomalies"]
    tb = upload(client, rev, file_id, "n.csv", data.sage_csv(opening=opening)).json()
    assert tb["statut"] == "accepte", tb["anomalies"]


def mapping(client, rev, file_id, acc="aud"):  # noqa: F811
    return client.get(f"/api/audit-files/{file_id}/mapping", headers=rev[acc].headers).json()


def test_rev08_rev09_affectation_automatique(client, rev):  # noqa: F811
    f = create_file(client, rev)
    # La banque BICICI est débitrice en N-1 et créditrice (découvert) en N.
    load(client, rev, f["id"], dict(data.N1, **{"521100": 6_500_000, "521200": 100_000}))
    m = mapping(client, rev, f["id"])
    assert m["non_affectes"] == []
    by = {a["compte"]: a for a in m["comptes"]}
    # Racine la plus longue : 245 (matériel de transport) plutôt que 24.
    assert (
        by["245100"]["postes"] == {"N-1": "AN", "N": "AN"} and by["245100"]["racines"]["N"] == "245"
    )
    assert by["284510"]["postes"]["N"] == "AN" and by["284400"]["postes"]["N"] == "AM"
    assert by["419100"]["postes"]["N"] == "DI"
    # Comptes à double sens, classés selon leur solde.
    assert by["401200"]["postes"]["N"] == "BH" and by["401100"]["postes"]["N"] == "DJ"
    assert by["521200"]["postes"] == {"N-1": "BS", "N": "DR"}
    assert by["521200"]["libelles_postes"]["N"].startswith("Banques, établissements financiers")
    assert all(a["origine"] == "auto" for a in m["comptes"])
    assert {p["code"] for p in m["postes"]} >= {"AD", "CJ", "DR"} and "BZ" not in {
        p["code"] for p in m["postes"]
    }


def test_rev10_comptes_non_affectes_et_apercu(client, rev, db):  # noqa: F811
    f = create_file(client, rev)
    url = f"/api/audit-files/{f['id']}"
    aud = rev["aud"].headers
    assert client.get(f"{url}/statements/preview", headers=aud).status_code == 409
    # Référentiel incomplet : la caisse (57) n'est rattachée à aucun poste.
    for code in ("BS", "DR"):
        line = db.scalar(select(StatementLine).where(StatementLine.code == code))
        line.racines = [r for r in line.racines if r["racine"] != "57"]
    db.commit()
    load(client, rev, f["id"])
    m = mapping(client, rev, f["id"])
    assert m["non_affectes"] == ["571100"]
    resp = client.get(f"{url}/statements/preview", headers=aud)
    assert resp.status_code == 409 and resp.json()["detail"]["comptes"] == ["571100"]
    # Affectation manuelle : contrôles des postes, droits, puis aperçu disponible.
    for body in ({"poste": "ZZ"}, {"poste": "BZ"}, {"poste": "BS", "poste_crediteur": "XI"}):
        assert client.put(f"{url}/mapping/571100", json=body, headers=aud).status_code == 422
    body = {"poste": "BS", "poste_crediteur": "DR", "commentaire": "Caisse : trésorerie"}
    assert (
        client.put(f"{url}/mapping/571100", json=body, headers=rev["da"].headers).status_code == 403
    )
    m = client.put(f"{url}/mapping/571 100", json=body, headers=aud).json()
    assert m["non_affectes"] == []
    caisse = next(a for a in m["comptes"] if a["compte"] == "571100")
    assert caisse["origine"] == "manuel" and caisse["postes"] == {"N-1": "BS", "N": "BS"}
    assert caisse["commentaire"] == "Caisse : trésorerie" and caisse["poste_crediteur"] == "DR"
    preview = client.get(f"{url}/statements/preview", headers=aud).json()
    actif = {x["code"]: x for x in preview["etats"]["bilan_actif"]}
    passif = {x["code"]: x for x in preview["etats"]["bilan_passif"]}
    resultat = {x["code"]: x for x in preview["etats"]["compte_resultat"]}
    assert actif["BZ"]["N"] == passif["DZ"]["N"] == "31700000.00" and actif["BZ"]["total"]
    assert actif["AN"]["N"] == "3000000.00" and actif["BS"]["N"] == "14500000.00"
    assert resultat["XB"]["N"] == "40000000.00" and resultat["XI"]["N"] == "7100000.00"
    assert passif["CJ"]["N"] == "7100000.00" and resultat["XI"]["N-1"] == "1500000.00"
    assert all(c["ok"] for c in preview["controles"]), preview["controles"]
    # Modification puis retour à l'affectation automatique.
    m = client.put(f"{url}/mapping/571100", json={"poste": "BS"}, headers=aud).json()
    assert next(a for a in m["comptes"] if a["compte"] == "571100")["commentaire"] is None
    assert client.delete(f"{url}/mapping/571100", headers=aud).json()["non_affectes"] == ["571100"]
    assert client.delete(f"{url}/mapping/571100", headers=aud).status_code == 404


def test_rev04_reprise_des_affectations(client, rev):  # noqa: F811
    old = create_file(client, rev, exercice=2025)
    body = {"poste": "BJ", "commentaire": "Compte d'attente classé en autres créances"}
    client.put(
        f"/api/audit-files/{old['id']}/mapping/471000", json=body, headers=rev["aud"].headers
    )
    new = create_file(client, rev, exercice=2026)
    upload(client, rev, new["id"], "n.csv",
           "Compte;Intitulé;Solde débit;Solde crédit\n101300;Capital;;100\n471000;Attente;100;\n".encode())  # fmt: skip
    m = mapping(client, rev, new["id"])
    attente = next(a for a in m["comptes"] if a["compte"] == "471000")
    assert attente["origine"] == "manuel" and attente["postes"] == {"N": "BJ"}
