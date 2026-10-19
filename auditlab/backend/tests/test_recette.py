"""Recette (§13 du cahier des charges) : scénario de bout en bout, par l'API HTTP.

1. Le Directeur crée l'entité « Achats », l'évalue et l'inscrit au plan 2027.
2. Le chef de mission ouvre la mission, construit la matrice risques/contrôles et affecte les
   procédures.
3. L'auditeur importe le grand livre fournisseurs (CSV) ; empreinte et totaux de contrôle.
4. Il lance doublons, Benford et rapprochement fournisseurs/salariés, puis un échantillon MUS
   de 60 factures.
5. Il joint les résultats à un papier de travail et le signe ; le chef de mission laisse une
   note de revue, qui est répondue puis clôturée ; revue et approbation dans le respect de la
   séparation des tâches.
6. Une anomalie devient un constat ; l'audité répond depuis son portail et propose un plan
   d'action.
7. Le rapport de mission PDF est généré, revu, validé et diffusé ; la mission est clôturée puis
   verrouillée.
8. La chaîne du journal d'audit est intacte et chaque étape y figure.

Volume : le grand livre généré ici compte 5 000 lignes pour garder un test rapide. Le volume
de la recette (500 000 lignes et plus) est couvert par le script de performance
`perf/nf10_import.py` (NF-10), qui suit la même chaîne d'import.
"""

import hashlib
import random
from decimal import Decimal

from app.audit.chain import verify_chain
from app.richtext import from_plain_text
from app.security.roles import Role
from tests import helpers
from tests.analysis_helpers import result_df
from tests.test_imports import run_import, upload

NB_LIGNES = 5_000
DOUBLONS_PLANTES = 5
IBAN_SUSPECT = "CI93CI0080111301134291200589"
FOURNISSEUR_SUSPECT = "ETS KOUASSI JEAN"
SALARIES = [
    "Traoré Moussa", "Koné Aminata", "Bamba Ibrahim", "Yao Christelle", "Coulibaly Seydou",
    "N'Guessan Marie", "Ouattara Lassina", "Konan Patrick", "Diabaté Fatou", "Kouassi Jean",
    "Touré Mariam", "Soro Adama",
]  # fmt: skip


# --- Jeux de données -------------------------------------------------------------------------


def grand_livre() -> tuple[bytes, dict]:
    """Grand livre fournisseurs au format comptable français, avec doublons plantés.

    Les montants suivent la loi de Benford (log-uniformes entre 10 et 100 000).
    """
    rnd = random.Random(2027)  # noqa: S311 - données de test
    fournisseurs = [(f"Fournisseur {i:03d}", f"CI00FOUR{i:06d}") for i in range(1, 151)]
    lignes = []
    for i in range(NB_LIGNES - DOUBLONS_PLANTES):
        nom, iban = (
            (FOURNISSEUR_SUSPECT, IBAN_SUSPECT) if i % 997 == 0 else rnd.choice(fournisseurs)
        )
        montant = Decimal(f"{10 ** rnd.uniform(1, 5):.2f}")
        date = f"{rnd.randint(1, 28):02d}/{rnd.randint(1, 12):02d}/2026"
        lignes.append([f"F{i + 1:06d}", nom, iban, date, montant])
    # Doublons plantés : même fournisseur, même date, même montant, autre numéro de pièce.
    for k in range(DOUBLONS_PLANTES):
        src = lignes[100 + 700 * k]
        lignes.append([f"F9{k:05d}", *src[1:]])
    keys: dict[tuple, list[str]] = {}
    for piece, nom, _, date, montant in lignes:
        keys.setdefault((nom, date, montant), []).append(piece)
    groupes = [v for v in keys.values() if len(v) > 1]
    text = "Pièce;Fournisseur;IBAN;Date;Montant TTC\n" + "".join(
        f"{p};{n};{iban};{d};{format(m, 'f').replace('.', ',')}\n" for p, n, iban, d, m in lignes
    )
    return text.encode("utf-8"), {
        "total": sum(m for *_, m in lignes),
        "groupes": len(groupes),
        "lignes_en_double": sum(len(g) for g in groupes),
        "lignes_suspect": sum(1 for line in lignes if line[1] == FOURNISSEUR_SUSPECT),
        "pieces_plantees": {f"F9{k:05d}" for k in range(DOUBLONS_PLANTES)},
    }


def salaries() -> bytes:
    rows = [
        f"M{i + 1:03d};{nom};{IBAN_SUSPECT if nom == 'Kouassi Jean' else f'CI00SAL{i:06d}'}\n"
        for i, nom in enumerate(SALARIES)
    ]
    return ("Matricule;Nom;IBAN\n" + "".join(rows)).encode("utf-8")


# --- Raccourcis HTTP -------------------------------------------------------------------------


def ok(resp, code: int = 200) -> dict:
    assert resp.status_code == code, resp.text
    return resp.json() if resp.content else {}


def analyse(client, headers, dataset_id, operation, params, second_id=None) -> dict:
    body = {"operation": operation, "parametres": params}
    if second_id:
        body["seconde_table_id"] = second_id
    res = ok(client.post(f"/api/datasets/{dataset_id}/analyses", json=body, headers=headers), 202)
    assert res["statut"] == "pret", res.get("erreur")
    return res


def move(client, url, headers, *statuts) -> None:
    """Changement de statut de la mission, un cran à la fois."""
    for statut in statuts:
        ok(client.post(f"{url}/status", json={"statut": statut}, headers=headers))


def journal(client, headers, object_type: str) -> list[dict]:
    resp = client.get(
        "/api/audit-log", params={"object_type": object_type, "limit": 1000}, headers=headers
    )
    return ok(resp)["items"]


# --- Scénario --------------------------------------------------------------------------------


def test_recette_scenario_complet(client, account, criteria, db):
    from app.reporting import templates

    directeur = account(Role.DIRECTEUR)
    chef = account(Role.CHEF_MISSION)
    aud = account(Role.AUDITEUR)
    audite = account(Role.AUDITE)
    # Modèle de rapport par défaut (installé par migration ; la troncature des tests l'efface).
    templates.seed(db)
    db.commit()
    dh, ch, ah = directeur.headers, chef.headers, aud.headers

    # 1. Le Directeur crée l'entité, l'évalue et l'inscrit au plan 2027. ----------------------
    achats = helpers.entity(client, dh, "Achats")
    evaluation = ok(
        client.post(
            f"/api/universe/entities/{achats['id']}/assessments",
            json={"notes": {"IMPACT_FIN": 4, "IMPACT_REG": 3, "PROBA": 4, "CTRL_INT": 2},
                  "date_evaluation": "2026-10-01", "commentaire": "Fraude fournisseurs signalée"},
            headers=dh,
        ),
        201,
    )  # fmt: skip
    assert evaluation["score"] > 0
    entite = ok(client.get(f"/api/universe/entities/{achats['id']}", headers=dh))
    assert entite["score_risque"] == evaluation["score"]
    plan, items = helpers.validated_plan(client, dh, [achats], annee=2027)
    assert plan["statut"] == "valide" and items[0]["entity_id"] == achats["id"]

    # 2. Le chef de mission ouvre la mission et construit la matrice. -------------------------
    mission = helpers.mission(
        client, ch, membres=[(aud.user, "auditeur")], plan_item_id=items[0]["id"],
        titre=None, date_debut=None, date_fin=None, budget_jours=None,
        objectifs="Évaluer le dispositif de contrôle des achats",
    )  # fmt: skip
    url = f"/api/engagements/{mission['id']}"
    assert mission["entity_nom"] == "Achats" and mission["statut"] == "planifiee"
    assert mission["chef_nom"] == chef.user.nom
    move(client, url, ch, "preparation")
    risk = ok(client.post(f"{url}/risks", headers=ch,
                          json={"libelle": "Fournisseurs fictifs ou doublons de paiement",
                                "cycle": "achats", "categorie": "fraude"}), 201)  # fmt: skip
    control = ok(client.post(f"{url}/controls", headers=ch,
                             json={"libelle": "Validation des créations de fournisseurs",
                                   "cycle": "achats", "type_controle": "preventif",
                                   "nature": "manuel", "frequence": "ponctuel",
                                   "risk_ids": [risk["id"]]}), 201)  # fmt: skip
    procedures = [
        ok(client.post(f"{url}/procedures", headers=ch,
                       json={"control_id": control["id"], "type_test": t, "description": d}), 201)
        for t, d in (("substantif", "Analyse du grand livre fournisseurs (doublons, Benford)"),
                     ("efficacite", "Rapprochement fournisseurs / salariés et échantillon MUS"))
    ]  # fmt: skip
    assert [p["reference"] for p in procedures] == ["P-01", "P-02"]
    for p in procedures:
        assigned = ok(
            client.put(f"{url}/procedures/{p['id']}/assignment", headers=ch,
                       json={"assigne_a": str(aud.user.id), "echeance": "2027-01-25"})
        )  # fmt: skip
        assert assigned["assigne_a"] == str(aud.user.id)
    matrix = ok(client.get(f"{url}/matrix", headers=ch))
    assert risk["id"] in str(matrix) and control["id"] in str(matrix)
    move(client, url, ch, "terrain")

    # 3. L'auditeur importe le grand livre fournisseurs. --------------------------------------
    ctx = {"url": url, "aud": aud}
    data, attendu = grand_livre()
    up = upload(client, ctx, "grand_livre_fournisseurs.csv", data)
    assert up["sha256"] == hashlib.sha256(data).hexdigest()
    options = {"format": "csv", "encodage": "utf-8", "separateur": ";", "decimal": ",",
               "format_date": "%d/%m/%Y",
               "colonnes": [{"nom": "Date", "type": "date"},
                            {"nom": "Montant TTC", "type": "decimal"}]}  # fmt: skip
    gl = run_import(client, ctx, up, options, "Grand livre fournisseurs 2026")
    assert gl["statut"] == "pret", gl["erreur"]
    assert gl["nb_lignes"] == NB_LIGNES and gl["source_sha256"] == up["sha256"]
    assert len(gl["parquet_sha256"]) == 64
    assert gl["totaux_controle"]["Montant TTC"] == {
        "somme": format(attendu["total"], "f"), "valeurs": NB_LIGNES
    }  # fmt: skip
    assert set(gl["totaux_controle"]["Date"]) == {"min", "max"}
    check = ok(client.get(f"/api/datasets/{gl['id']}/integrity", headers=ah))
    assert check["source_intacte"] is True and check["table_intacte"] is True
    up2 = upload(client, ctx, "salaries.csv", salaries())
    sal = run_import(client, ctx, up2, {"format": "csv", "separateur": ";"}, "Salariés")
    assert sal["statut"] == "pret" and sal["nb_lignes"] == len(SALARIES)

    # 4. Doublons, Benford, rapprochement fournisseurs/salariés, échantillon MUS. -------------
    dups = analyse(client, ah, gl["id"], "doublons",
                   {"cles": ["Fournisseur", "Date", "Montant TTC"]})  # fmt: skip
    assert dups["resultat"] == {
        "groupes": attendu["groupes"], "lignes_en_double": attendu["lignes_en_double"]
    }  # fmt: skip
    assert attendu["pieces_plantees"] <= set(result_df(db, dups)["Pièce"].to_list())

    benford = analyse(client, ah, gl["id"], "benford", {"champ": "Montant TTC"})
    assert benford["resultat"]["montants_retenus"] == NB_LIGNES
    assert benford["resultat"]["conformite"] in ("conformite_etroite", "conformite_acceptable")

    # Rapprochement : même IBAN (jointure) et noms voisins (recherche floue).
    meme_iban = analyse(client, ah, gl["id"], "jointure",
                        {"cles": [{"gauche": "IBAN", "droite": "IBAN"}]},
                        second_id=sal["id"])  # fmt: skip
    assert meme_iban["resultat"]["appariees"] == attendu["lignes_suspect"]
    df = result_df(db, meme_iban)
    assert set(df["Fournisseur"]) == {FOURNISSEUR_SUSPECT} and set(df["Nom"]) == {"Kouassi Jean"}
    noms = analyse(client, ah, gl["id"], "floue",
                   {"champ_gauche": "Fournisseur", "champ_droite": "Nom"},
                   second_id=sal["id"])  # fmt: skip
    assert noms["resultat"]["paires"] == attendu["lignes_suspect"]
    df = result_df(db, noms)
    assert set(df["Fournisseur"]) == {FOURNISSEUR_SUSPECT} and set(df["similarite"]) == {1.0}

    mus = analyse(client, ah, gl["id"], "echantillon",
                  {"methode": "mus", "taille": 60, "champ_montant": "Montant TTC",
                   "graine": 2027})  # fmt: skip
    sample = result_df(db, mus)
    assert mus["resultat"]["methode"] == "mus" and sample["nb_selections"].sum() == 60
    assert mus["resultat"]["taille_echantillon"] == sample.height == 60

    # 5. Papier de travail, données jointes, signatures et note de revue. ---------------------
    wp = ok(client.post(f"{url}/workpapers", headers=ah, json={
        "reference": "ACH-1", "titre": "Analyse du grand livre fournisseurs",
        "procedure_id": procedures[0]["id"],
        "travaux": from_plain_text("Doublons, Benford, rapprochement et échantillon MUS."),
        "conclusion": "Doublons de paiement et fournisseur lié à un salarié",
        "evaluation": "inefficace"}), 201)  # fmt: skip
    links_url = f"/api/workpapers/{wp['id']}/data-links"
    for res in (dups, benford, meme_iban, noms, mus):
        link = ok(client.post(links_url, json={"dataset_id": res["id"]}, headers=ah), 201)
        assert link["empreinte"] == res["parquet_sha256"]
    assert len(ok(client.get(links_url, headers=ch))) == 5

    sign_url = f"/api/workpapers/{wp['id']}/signoffs"
    ok(client.post(sign_url, json={"type": "prepare"}, headers=ah), 201)
    # Séparation des tâches : le préparateur ne revoit pas son propre papier.
    assert client.post(sign_url, json={"type": "revu"}, headers=ah).status_code == 403
    note = ok(client.post(f"/api/workpapers/{wp['id']}/review-notes", headers=ch,
                          json={"texte": "Préciser le traitement des 5 doublons",
                                "ancre": {"champ": "travaux", "citation": "Doublons"}}), 201)  # fmt: skip
    assert note["statut"] == "ouverte"
    replied = ok(client.post(f"/api/review-notes/{note['id']}/replies", headers=ah,
                             json={"texte": "Doublons repris dans le constat C-01"}), 201)  # fmt: skip
    assert replied["statut"] == "repondue"
    ok(client.post(sign_url, json={"type": "revu"}, headers=ch), 201)
    # L'approbation exige les notes clôturées.
    assert client.post(sign_url, json={"type": "approuve"}, headers=dh).status_code == 409
    assert ok(client.post(f"/api/review-notes/{note['id']}/close", headers=ch))["statut"] == (
        "cloturee"
    )
    ok(client.post(sign_url, json={"type": "approuve"}, headers=dh), 201)
    wp_now = ok(client.get(f"/api/workpapers/{wp['id']}", headers=ah))
    assert wp_now["statut_signature"] == "approuve"
    assert [(s["type"], s["user_nom"]) for s in wp_now["signatures"]] == [
        ("prepare", aud.user.nom), ("revu", chef.user.nom), ("approuve", directeur.user.nom)
    ]  # fmt: skip
    for p in procedures:
        ok(client.put(f"{url}/procedures/{p['id']}/status", json={"statut": "terminee"},
                      headers=ah))  # fmt: skip

    # 6. Une anomalie devient un constat ; l'audité répond depuis son portail. ----------------
    page = ok(client.post(f"/api/datasets/{dups['id']}/rows", json={}, headers=ah))
    lines = [dict(zip(page["colonnes"], row, strict=True)) for row in page["lignes"]]
    assert len(lines) == attendu["lignes_en_double"]
    finding = ok(client.post(f"/api/datasets/{dups['id']}/findings", headers=ah,
                             json={"titre": "Paiements en double aux fournisseurs",
                                   "criticite": "elevee", "lignes": lines,
                                   "commentaire": "Même fournisseur, même date, même montant"}),
                 201)  # fmt: skip
    assert finding["reference"] == "C-01" and finding["statut"] == "brouillon"
    f_url = f"/api/findings/{finding['id']}"
    evidence = ok(client.get(f"{f_url}/evidence", headers=ah))
    assert evidence[0]["type"] == "lignes" and evidence[0]["empreinte"] == dups["parquet_sha256"]
    ok(client.patch(f_url, headers=ah, json={
        "critere": "Chaque facture n'est payée qu'une fois (procédure ACH-04).",
        "cause": "Absence de contrôle bloquant des doublons dans le progiciel.",
        "consequence": "Paiements indus aux fournisseurs.",
        "recommandation": "Activer le contrôle des doublons et récupérer les sommes payées.",
        "risk_id": risk["id"], "control_id": control["id"], "workpaper_ids": [wp["id"]]}))  # fmt: skip
    sent = ok(client.post(f"{f_url}/send", json={"audite_id": str(audite.user.id)}, headers=ah))
    assert sent["statut"] == "envoye"

    portal = ok(client.get("/api/portal/findings", headers=audite.headers))
    assert [f["id"] for f in portal] == [finding["id"]] and portal[0]["peut_repondre"]
    reponse = {"position": "accord", "commentaire": "Contrôle à réactiver dans le progiciel",
               "plans": [{"description": "Activer le blocage des doublons et recouvrer les "
                          "paiements indus", "echeance": "2027-06-30"}]}  # fmt: skip
    answered = ok(client.post(f"/api/portal/findings/{finding['id']}/response", json=reponse,
                              headers=audite.headers))  # fmt: skip
    assert answered["statut"] == "repondu"
    detail = ok(client.get(f"/api/portal/findings/{finding['id']}", headers=audite.headers))
    assert [p["description"] for p in detail["plans"]] == [reponse["plans"][0]["description"]]
    plans = ok(client.get(f"{f_url}/action-plans", headers=ch))
    assert len(plans) == 1 and plans[0]["responsable_id"] == str(audite.user.id)
    assert ok(client.post(f"{f_url}/validate", json={}, headers=ch))["statut"] == "valide"

    # 7. Rapport de mission, diffusion, clôture et verrouillage. ------------------------------
    move(client, url, ch, "revue", "rapport")
    report_url = f"{url}/report"
    ok(client.put(report_url, headers=ch, json={
        "synthese": "Le dispositif de contrôle des paiements fournisseurs est insuffisant.",
        "conclusion": "Un plan d'action a été accepté par l'audité."}))  # fmt: skip
    pdf = client.get(f"{report_url}/document", headers=ch)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    transition = f"{report_url}/transition"
    # Le chef de mission ne revoit pas son propre rapport.
    assert client.post(transition, json={"statut": "revu"}, headers=ch).status_code == 403
    assert ok(client.post(transition, json={"statut": "revu"}, headers=dh))["statut"] == "revu"
    assert ok(client.post(transition, json={"statut": "valide"}, headers=dh))["statut"] == "valide"
    diffused = ok(client.post(transition, json={"statut": "diffuse"}, headers=ch))
    assert diffused["statut"] == "diffuse" and set(diffused["empreintes"]) == {"pdf", "docx"}
    final_pdf = client.get(f"{report_url}/document", headers=dh).content
    assert hashlib.sha256(final_pdf).hexdigest() == diffused["empreintes"]["pdf"]

    move(client, url, ch, "cloturee")
    closed = ok(client.get(url, headers=ch))
    assert closed["statut"] == "cloturee" and closed["cloturee_le"]
    assert closed["transitions"] == []
    entite = ok(client.get(f"/api/universe/entities/{achats['id']}", headers=dh))
    assert entite["date_dernier_audit"] == closed["date_fin"]
    # Verrouillage : toute écriture est refusée, la consultation reste possible.
    refused = [
        client.patch(f"/api/workpapers/{wp['id']}", json={"titre": "Modifié"}, headers=ah),
        client.post(f"{url}/workpapers", json={"reference": "ACH-2", "titre": "x"}, headers=ah),
        client.post(f"{url}/risks", headers=ch,
                    json={"libelle": "x", "cycle": "achats", "categorie": "fraude"}),
        client.post(f"{url}/status", json={"statut": "rapport"}, headers=ch),
        client.post(f"/api/datasets/{gl['id']}/analyses", headers=ah,
                    json={"operation": "benford", "parametres": {"champ": "Montant TTC"}}),
    ]  # fmt: skip
    assert [r.status_code for r in refused] == [409] * len(refused), [r.text for r in refused]
    assert client.get(f"/api/workpapers/{wp['id']}", headers=ah).status_code == 200

    # 8. Chaîne du journal intacte ; chaque étape journalisée. --------------------------------
    report = ok(client.get("/api/audit-log/verify", headers=dh))
    assert report["ok"] is True and report["first_broken_seq"] is None, report
    chain = verify_chain(db)
    assert chain.ok and chain.entries >= report["entries"]

    expected = {
        "AuditableEntity": achats["id"],
        "RiskAssessment": evaluation["id"],
        "AuditPlan": plan["id"],
        "PlanItem": items[0]["id"],
        "Engagement": mission["id"],
        "Risk": risk["id"],
        "Control": control["id"],
        "Procedure": procedures[0]["id"],
        "Upload": up["id"],
        "Dataset": gl["id"],
        "Workpaper": wp["id"],
        "WorkpaperDataLink": None,
        "Signoff": None,
        "ReviewNote": note["id"],
        "Finding": finding["id"],
        "FindingEvidence": evidence[0]["id"],
        "ActionPlan": plans[0]["id"],
        "MissionReport": diffused["id"],
    }
    for object_type, object_id in expected.items():
        entries = journal(client, dh, object_type)
        assert entries, f"aucune entrée de journal pour {object_type}"
        if object_id is not None:
            assert any(e["object_id"] == str(object_id) for e in entries), object_type
    assert len(journal(client, dh, "Signoff")) >= 3
    # Statuts de la mission, du plan et du rapport, lus dans le journal.
    mission_log = [e for e in journal(client, dh, "Engagement") if e["object_id"] == mission["id"]]
    statuts = [e["apres"]["statut"] for e in reversed(mission_log)
               if e["action"] == "update" and "statut" in (e["apres"] or {})]  # fmt: skip
    assert statuts == ["preparation", "terrain", "revue", "rapport", "cloturee"]
    history = ok(client.get(f"{url}/status-history", headers=ch))
    assert sorted((h["avant"], h["apres"]) for h in history) == sorted(
        zip(["planifiee", *statuts[:-1]], statuts, strict=True)
    )
    plan_log = journal(client, dh, "AuditPlan")
    assert any((e["apres"] or {}).get("statut") == "valide" for e in plan_log)
    report_log = [e for e in journal(client, dh, "MissionReport") if e["action"] == "transition"]
    assert len(report_log) == 3
    finding_log = [e for e in journal(client, dh, "Finding") if e["object_id"] == finding["id"]]
    assert {(e["apres"] or {}).get("statut") for e in finding_log} >= {
        "envoye", "repondu", "valide"
    }  # fmt: skip
