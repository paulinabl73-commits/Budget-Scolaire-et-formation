import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.richtext import from_plain_text, is_valid_doc, to_plain_text
from app.security.roles import Role
from tests import helpers


@pytest.fixture
def ctx(client, account):
    """Mission avec un chef, une auditrice, un data analyst et une procédure P-01."""
    chef = account(Role.CHEF_MISSION)
    aud = account(Role.AUDITEUR)
    da = account(Role.DATA_ANALYST)
    m = helpers.mission(
        client, chef.headers, membres=[(aud.user, "auditeur"), (da.user, "data_analyst")]
    )
    url = f"/api/engagements/{m['id']}"
    r = client.post(
        f"{url}/risks",
        json={"libelle": "Fournisseurs fictifs", "cycle": "achats", "categorie": "fraude"},
        headers=chef.headers,
    ).json()
    c = client.post(
        f"{url}/controls",
        json={
            "libelle": "Validation des créations",
            "cycle": "achats",
            "type_controle": "preventif",
            "nature": "manuel",
            "frequence": "ponctuel",
            "risk_ids": [r["id"]],
        },
        headers=chef.headers,
    ).json()
    p = client.post(
        f"{url}/procedures",
        json={
            "control_id": c["id"],
            "type_test": "efficacite",
            "description": "Revue des créations",
        },
        headers=chef.headers,
    ).json()
    return {"chef": chef, "aud": aud, "da": da, "mission": m, "url": url, "procedure": p}


WP = {
    "reference": "A-1.1",
    "titre": "Revue des créations de fournisseurs",
    "objectif": "S'assurer que chaque création est validée hors du service achats",
}


def create(client, ctx, **kw):
    resp = client.post(f"{ctx['url']}/workpapers", json={**WP, **kw}, headers=ctx["aud"].headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_aud13_papier_de_travail(client, ctx, db):
    wp = create(
        client,
        ctx,
        procedure_id=ctx["procedure"]["id"],
        travaux=from_plain_text("25 créations testées\nAucune anomalie"),
        conclusion="Contrôle opérant",
        evaluation="efficace",
    )
    assert wp["procedure_reference"] == "P-01" and wp["version"] == 1
    assert wp["evaluation"] == "efficace" and wp["peut_modifier"] is True
    assert to_plain_text(wp["travaux"]) == "25 créations testées\nAucune anomalie"

    resp = client.patch(
        f"/api/workpapers/{wp['id']}",
        json={"evaluation": "partiellement_efficace", "conclusion": "Deux exceptions"},
        headers=ctx["aud"].headers,
    )
    assert resp.json()["evaluation"] == "partiellement_efficace" and resp.json()["version"] == 2
    # Un enregistrement sans changement ne crée pas de version.
    resp = client.patch(
        f"/api/workpapers/{wp['id']}",
        json={"conclusion": "Deux exceptions"},
        headers=ctx["aud"].headers,
    )
    assert resp.json()["version"] == 2

    listed = client.get(f"{ctx['url']}/workpapers", headers=ctx["da"].headers).json()
    assert [(w["reference"], w["procedure_reference"]) for w in listed] == [("A-1.1", "P-01")]
    detail = client.get(f"/api/workpapers/{wp['id']}", headers=ctx["da"].headers).json()
    assert detail["peut_modifier"] is False  # le data analyst lit les papiers
    log = db.scalar(
        select(AuditLog).where(AuditLog.object_type == "Workpaper", AuditLog.action == "update")
    )
    assert log.avant["evaluation"] == "efficace"


def test_aud13_reference_unique_et_format(client, ctx):
    create(client, ctx)
    resp = client.post(f"{ctx['url']}/workpapers", json=WP, headers=ctx["aud"].headers)
    assert resp.status_code == 409
    for ref in ("a-1", "B 2", "B-2..3", ""):
        resp = client.post(
            f"{ctx['url']}/workpapers", json={**WP, "reference": ref}, headers=ctx["aud"].headers
        )
        assert resp.status_code == 422, ref
    for ref in ("B-2.3", "P01", "AB-12.1.4"):
        assert (
            client.post(
                f"{ctx['url']}/workpapers",
                json={**WP, "reference": ref},
                headers=ctx["aud"].headers,
            ).status_code
            == 201
        )
    second = client.get(f"{ctx['url']}/workpapers", headers=ctx["aud"].headers).json()[1]
    resp = client.patch(
        f"/api/workpapers/{second['id']}", json={"reference": "A-1.1"}, headers=ctx["aud"].headers
    )
    assert resp.status_code == 409


def test_aud13_controles(client, ctx):
    bad_doc = client.post(
        f"{ctx['url']}/workpapers",
        json={**WP, "travaux": {"type": "x"}},
        headers=ctx["aud"].headers,
    )
    assert bad_doc.status_code == 422
    bad_eval = client.post(
        f"{ctx['url']}/workpapers", json={**WP, "evaluation": "bof"}, headers=ctx["aud"].headers
    )
    assert bad_eval.status_code == 422
    resp = client.post(
        f"{ctx['url']}/workpapers",
        json={**WP, "procedure_id": str(uuid.uuid4())},
        headers=ctx["aud"].headers,
    )
    assert resp.status_code == 404
    assert (
        client.get(f"/api/workpapers/{uuid.uuid4()}", headers=ctx["aud"].headers).status_code == 404
    )


def test_aud13_droits(client, ctx, account):
    wp = create(client, ctx)
    # Le data analyst lit mais ne rédige pas.
    resp = client.post(
        f"{ctx['url']}/workpapers", json={**WP, "reference": "X-1"}, headers=ctx["da"].headers
    )
    assert resp.status_code == 403
    # Hors de l'équipe : mission invisible.
    other = account(Role.AUDITEUR)
    assert client.get(f"/api/workpapers/{wp['id']}", headers=other.headers).status_code == 404
    # Le Directeur lit tous les papiers sans les rédiger.
    directeur = account(Role.DIRECTEUR)
    assert client.get(f"/api/workpapers/{wp['id']}", headers=directeur.headers).status_code == 200
    assert (
        client.patch(
            f"/api/workpapers/{wp['id']}", json={"titre": "X"}, headers=directeur.headers
        ).status_code
        == 403
    )
    # Suppression : auteur ou chef de mission.
    assert (
        client.delete(f"/api/workpapers/{wp['id']}", headers=ctx["da"].headers).status_code == 403
    )
    assert (
        client.delete(f"/api/workpapers/{wp['id']}", headers=ctx["chef"].headers).status_code == 204
    )
    assert client.get(f"{ctx['url']}/workpapers", headers=ctx["aud"].headers).json() == []


def test_richtext():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Total "},
                    {"type": "tickmark", "attrs": {"symbole": "Σ"}},
                ],
            },
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "A"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "B"}],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "point"}]}
                        ],
                    }
                ],
            },
            {
                "type": "paragraph",
                "content": [{"type": "image", "attrs": {"alt": "facture"}}, {"type": "hardBreak"}],
            },
        ],
    }
    assert to_plain_text(doc) == "Total [Σ]\nA\tB\n- point\n[image facture]\n"
    assert to_plain_text(None) == ""
    assert is_valid_doc(doc) and not is_valid_doc({"type": "paragraph"})


def _doc(*content):
    return {"type": "doc", "content": list(content)}


def _para(text, marks=None):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return {"type": "paragraph", "content": [node]}


def test_aud14_contenu_riche(client, ctx):
    from tests.test_attachments import PNG, upload

    other = create(client, ctx, reference="A-1.2")
    table = {
        "type": "table",
        "content": [
            {
                "type": "tableRow",
                "content": [
                    {"type": "tableHeader", "content": [_para("Facture")]},
                    {"type": "tableCell", "content": [_para("1 250 000")]},
                ],
            }
        ],
    }
    link = _para(
        "voir A-1.2",
        [
            {
                "type": "link",
                "attrs": {"href": f"/missions/{ctx['mission']['id']}/papiers/{other['id']}"},
            }
        ],
    )
    wp = create(
        client,
        ctx,
        travaux=_doc(
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Échantillon"}],
            },
            table,
            link,
            _para("gras", [{"type": "bold"}]),
        ),
    )
    assert to_plain_text(wp["travaux"]) == "Échantillon\nFacture\t1 250 000\nvoir A-1.2\ngras"

    # Image : uniquement une pièce jointe du même papier.
    img = upload(client, wp, ctx["aud"], "capture.png", PNG).json()
    image = {
        "type": "paragraph",
        "content": [
            {"type": "image", "attrs": {"src": f"attachment:{img['id']}", "alt": "capture"}}
        ],
    }
    resp = client.patch(
        f"/api/workpapers/{wp['id']}", json={"travaux": _doc(image)}, headers=ctx["aud"].headers
    )
    assert resp.status_code == 200
    foreign = {
        "type": "paragraph",
        "content": [{"type": "image", "attrs": {"src": f"attachment:{uuid.uuid4()}"}}],
    }
    resp = client.patch(
        f"/api/workpapers/{wp['id']}", json={"travaux": _doc(foreign)}, headers=ctx["aud"].headers
    )
    assert resp.status_code == 422 and "pièce jointe" in resp.json()["detail"]


@pytest.mark.parametrize(
    ("node", "message"),
    [
        ({"type": "script"}, "Élément non admis"),
        (_para("x", [{"type": "highlight"}]), "Mise en forme"),
        (_para("x", [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}]), "Lien"),
        ({"type": "image", "attrs": {"src": "https://pistage.example/pixel.gif"}}, "pièce jointe"),
        ("texte nu", "invalide"),
    ],
)
def test_aud14_contenu_refuse(client, ctx, node, message):
    resp = client.post(
        f"{ctx['url']}/workpapers", json={**WP, "travaux": _doc(node)}, headers=ctx["aud"].headers
    )
    assert resp.status_code == 422 and message in resp.json()["detail"]


def test_aud16_marques_de_revision(client, ctx, account):
    directeur = account(Role.DIRECTEUR).headers
    tm = client.post(
        "/api/tickmarks",
        json={"symbole": "✓", "libelle": "Vérifié sur pièce", "couleur": "#15803d"},
        headers=directeur,
    )
    assert tm.status_code == 201
    tm = tm.json()
    assert (
        client.post(
            "/api/tickmarks", json={"symbole": "✓", "libelle": "Doublon"}, headers=directeur
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/tickmarks",
            json={"symbole": "Σ", "libelle": "x", "couleur": "rouge"},
            headers=directeur,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/tickmarks", json={"symbole": "Σ", "libelle": "x"}, headers=ctx["aud"].headers
        ).status_code
        == 403
    )

    mark = {"type": "tickmark", "attrs": {"id": tm["id"], "symbole": "✓"}}
    cell = {
        "type": "tableCell",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "150 000 "}, mark]}],
    }
    doc = _doc(
        _para("Montant vérifié"),
        {"type": "paragraph", "content": [mark]},
        {"type": "table", "content": [{"type": "tableRow", "content": [cell]}]},
    )
    wp = create(client, ctx, travaux=doc)
    assert to_plain_text(wp["travaux"]) == "Montant vérifié\n[✓]\n150 000 [✓]"

    from app.richtext import tickmark_ids

    assert tickmark_ids(wp["travaux"]) == {tm["id"]}
    unknown = _doc(
        {
            "type": "paragraph",
            "content": [{"type": "tickmark", "attrs": {"id": str(uuid.uuid4()), "symbole": "?"}}],
        }
    )
    resp = client.patch(
        f"/api/workpapers/{wp['id']}", json={"travaux": unknown}, headers=ctx["aud"].headers
    )
    assert resp.status_code == 422 and "Marque" in resp.json()["detail"]

    # Une marque désactivée n'est plus proposée mais reste valide dans les papiers existants.
    resp = client.patch(
        f"/api/tickmarks/{tm['id']}", json={"actif": False, "couleur": "#000000"}, headers=directeur
    )
    assert resp.json()["actif"] is False
    resp = client.patch(
        f"/api/workpapers/{wp['id']}",
        json={"travaux": doc, "titre": "Revu"},
        headers=ctx["aud"].headers,
    )
    assert resp.status_code == 200
    listed = client.get("/api/tickmarks", headers=ctx["aud"].headers).json()
    assert [(t["symbole"], t["actif"]) for t in listed] == [("✓", False)]
    assert (
        client.patch(
            f"/api/tickmarks/{uuid.uuid4()}", json={"ordre": 1}, headers=directeur
        ).status_code
        == 404
    )
