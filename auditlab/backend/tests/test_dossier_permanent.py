"""RCO-05 : dossier permanent du client, repris d'un exercice à l'autre."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401

PDF = b"%PDF-1.4\n%statuts\n"


def test_rco05_dossier_permanent(client, cabinet):  # noqa: F811
    expert, collab, contact = cabinet["expert"], cabinet["collab"], cabinet["contact"]
    c = new_client(client, cabinet)
    url = f"/api/clients/{c['id']}/permanent"
    form = {"categorie": "statuts", "libelle": "Statuts à jour", "date_document": "2019-05-02"}
    docs = client.post(
        url, data=form, files={"file": ("statuts.pdf", PDF)}, headers=collab.headers
    ).json()
    assert docs[0]["fichiers"][0]["nom_fichier"] == "statuts.pdf"
    bail = {"categorie": "bail", "libelle": "Bail du siège", "date_validite": "2027-03-31"}
    docs = client.post(url, data=bail, headers=collab.headers).json()
    assert [d["categorie"] for d in docs] == ["bail", "statuts"]
    assert (
        client.post(url, data={**bail, "categorie": "inconnue"}, headers=collab.headers).status_code
        == 422
    )
    assert client.post(url, data=bail, headers=contact.headers).status_code == 404  # hors équipe
    doc_id = docs[0]["id"]
    docs = client.post(
        f"/api/permanent/{doc_id}/files", files={"file": ("bail.pdf", PDF)}, headers=collab.headers
    ).json()
    assert len(docs[0]["fichiers"]) == 1
    docs = client.patch(
        f"/api/permanent/{doc_id}", json={"date_validite": "2030-03-31"}, headers=expert.headers
    ).json()
    assert docs[0]["date_validite"] == "2030-03-31"
    # Repris d'un exercice à l'autre : rattaché au client, pas à la clôture.
    open_closing(client, cabinet, c, 2025)
    open_closing(client, cabinet, c, 2026)
    assert len(client.get(url, headers=expert.headers).json()) == 2
    assert client.delete(f"/api/permanent/{doc_id}", headers=collab.headers).status_code == 204
    assert len(client.get(url, headers=expert.headers).json()) == 1
