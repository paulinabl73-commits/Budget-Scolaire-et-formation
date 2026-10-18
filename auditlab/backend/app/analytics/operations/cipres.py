"""CIP-02 à CIP-05 — contrôles des organismes de prévoyance sociale sur leurs fichiers.

Les taux, plafonds, délais, âges et barèmes sont des paramètres de l'opération : lancée depuis
un dossier CIPRES, ils sont lus dans le référentiel (CIP-09) et ne sont pas modifiables.

- cip_cotisations (CIP-02) : déclarations nominatives des salaires (une ligne par salarié et
  par période) et cotisations émises et encaissées par employeur. Cotisation théorique par
  branche = Σ min(salaire, plafond × mois de la période) × taux ; un plafond nul signifie
  « sans plafond ». Une ligne par employeur, anomalie indiquée.
- cip_recouvrement (CIP-03) : déclarations et registre des employeurs ; une ligne par
  anomalie : employeur actif sans déclaration pour une période attendue (non_declarant),
  déclaration déposée après la fin de la période augmentée du délai (declaration_tardive),
  majoration de retard inférieure à la majoration due (majoration_non_appliquee), déclarant
  absent du registre (non_immatricule). Majoration due = cotisations × taux, multipliée par le
  nombre de mois de retard entamés (mois de 30 jours) si le régime l'applique par mois.
- cip_creances (CIP-03) : créances sur cotisants exigibles depuis au moins l'ancienneté fixée
  et dépréciées à moins du taux exigé.
- cip_prestations (CIP-04) : fichier des bénéficiaires (une ligne par pension servie) ; lignes
  remplissant au moins un critère : identifiant en double, nom proche d'un autre bénéficiaire
  né le même jour (similarité de Jaro-Winkler, noms sans accents), compte bancaire partagé
  par plusieurs bénéficiaires, âge hors des bornes à la date de référence, paiement postérieur
  au décès, certificat de vie absent ou périmé (bénéficiaire non décédé), montant hors barème.
  Un critère dont la colonne n'est pas fournie n'est pas appliqué.
"""

from decimal import Decimal
from typing import Any

from app.analytics.operations.base import (
    DATES,
    NUMERIC,
    Operation,
    OpResult,
    Param,
    register,
)
from app.analytics.relation import Relation, evaluate, evaluate_many
from app.analytics.store import quote_ident

AMOUNT = "DECIMAL(18,2)"


def _amount(column: str) -> str:
    return f"coalesce(CAST({column} AS {AMOUNT}), 0)"


def cotisations(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    emp, sal = quote_ident(p["champ_employeur"]), _amount(quote_ident(p["champ_salaire"]))
    emp2 = quote_ident(p["champ_employeur_emission"])
    emis, enc = _amount(quote_ident(p["champ_emis"])), _amount(quote_ident(p["champ_encaisse"]))
    plafonds = p.get("plafonds") or {}
    params: list[Any] = []
    per_branch = []
    for code, rate in sorted(p["taux"].items()):
        base = sal
        ceiling = Decimal(plafonds.get(code, "0"))
        if ceiling > 0:
            base = f"least({sal}, CAST(? AS DECIMAL(18,2)) * ?)"
            params += [str(ceiling), int(p["mois_par_ligne"])]
        name = quote_ident("theorique_" + code.lower())
        per_branch.append(f"round(sum({base}) * CAST(? AS DECIMAL(9,4)) / 100, 2) AS {name}")
        params.append(rate)
    branches = [quote_ident("theorique_" + c.lower()) for c in sorted(p["taux"])]
    total = " + ".join(f"coalesce(d.{b}, 0)" for b in branches)
    tolerance = p["tolerance"]
    sql = (
        f"WITH d AS (SELECT CAST(a.{emp} AS VARCHAR) AS employeur, sum({sal}) AS masse_salariale, "
        f"{', '.join(per_branch)} FROM a WHERE a.{emp} IS NOT NULL GROUP BY 1), "
        f"e AS (SELECT CAST(b.{emp2} AS VARCHAR) AS employeur, sum({emis}) AS emis, "
        f"sum({enc}) AS encaisse FROM b WHERE b.{emp2} IS NOT NULL GROUP BY 1), "
        f"j AS (SELECT coalesce(d.employeur, e.employeur) AS employeur, "
        f"CAST(coalesce(d.masse_salariale, 0) AS {AMOUNT}) AS masse_salariale, "
        + ", ".join(f"CAST(coalesce(d.{b}, 0) AS {AMOUNT}) AS {b}" for b in branches)
        + f", CAST({total} AS {AMOUNT}) AS cotisation_theorique, "
        f"CAST(coalesce(e.emis, 0) AS {AMOUNT}) AS emis, "
        f"CAST(coalesce(e.encaisse, 0) AS {AMOUNT}) AS encaisse, "
        f"d.employeur IS NULL AS sans_declaration, e.employeur IS NULL AS sans_emission "
        f"FROM d FULL JOIN e ON d.employeur = e.employeur) "
        f"SELECT employeur, masse_salariale, {', '.join(branches)}, cotisation_theorique, emis, "
        f"encaisse, CAST(emis - cotisation_theorique AS {AMOUNT}) AS ecart_emission, "
        f"CAST(emis - encaisse AS {AMOUNT}) AS reste_a_recouvrer, "
        f"CASE WHEN sans_declaration THEN 'emission_sans_declaration' "
        f"WHEN sans_emission THEN 'declaration_sans_emission' "
        f"WHEN abs(emis - cotisation_theorique) > CAST(? AS DECIMAL(18,2)) "
        f"THEN 'ecart_emission' END AS anomalie "
        f"FROM j ORDER BY abs(emis - cotisation_theorique) DESC, employeur"
    )
    df = evaluate_many({"a": rels[0], "b": rels[1]}, sql, [*params, tolerance])
    anomalies = df["anomalie"].drop_nulls().value_counts(sort=True)
    return OpResult(
        df,
        {
            "employeurs": df.height,
            "en_anomalie": int(df["anomalie"].is_not_null().sum()),
            "par_anomalie": dict(zip(anomalies["anomalie"], anomalies["count"], strict=True)),
            "totaux": {
                c: str(df[c].sum() if df.height else Decimal(0))
                for c in ("masse_salariale", "cotisation_theorique", "emis", "encaisse")
            },
            "taux": p["taux"],
            "plafonds": plafonds,
        },
    )


register(
    Operation(
        "cip_cotisations",
        "CIP-02",
        2,
        (
            Param("champ_employeur", "colonne"),
            Param("champ_salaire", "colonne", types_colonne=NUMERIC),
            Param("champ_employeur_emission", "colonne", table=1),
            Param("champ_emis", "colonne", table=1, types_colonne=NUMERIC),
            Param("champ_encaisse", "colonne", table=1, types_colonne=NUMERIC),
            Param("taux", "bareme", minimum=0, maximum=100),
            Param("plafonds", "bareme", requis=False, minimum=0),
            Param("mois_par_ligne", "entier", requis=False, defaut=1, minimum=1, maximum=12),
            Param("tolerance", "nombre", requis=False, defaut="0", minimum=0),
        ),
        cotisations,
    )
)


UNITS = {"mensuelle": ("month", 1), "trimestrielle": ("quarter", 3)}


def recouvrement(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    q = {k: quote_ident(p[k]) for k in ("champ_employeur", "champ_periode", "champ_date_depot")}
    reg = quote_ident(p["champ_employeur_registre"])
    unit, months = UNITS[p["periodicite"]]
    aff = (
        f"CAST(b.{quote_ident(p['champ_date_affiliation'])} AS DATE)"
        if p.get("champ_date_affiliation")
        else "NULL"
    )
    ces = (
        f"CAST(b.{quote_ident(p['champ_date_cessation'])} AS DATE)"
        if p.get("champ_date_cessation")
        else "NULL"
    )
    cot = _amount(f"a.{quote_ident(p['champ_cotisations'])}")
    applied = (
        _amount(f"a.{quote_ident(p['champ_majoration'])}") if p.get("champ_majoration") else None
    )
    start = f"CAST(date_trunc('{unit}', CAST(a.{q['champ_periode']} AS DATE)) AS DATE)"
    late_days = (
        f"date_diff('day', CAST(d.debut_periode + INTERVAL {months} MONTH - INTERVAL 1 DAY "
        f"+ INTERVAL (CAST(? AS INTEGER)) DAY AS DATE), d.date_depot)"
    )
    factor = "ceil(d.jours_retard / 30.0)" if int(p["par_mois"]) else "1"
    sql = (
        f"WITH d AS (SELECT CAST(a.{q['champ_employeur']} AS VARCHAR) AS employeur, "
        f"{start} AS debut_periode, CAST(a.{q['champ_date_depot']} AS DATE) AS date_depot, "
        f"{cot} AS cotisations, {applied or 'NULL'} AS majoration_appliquee FROM a "
        f"WHERE a.{q['champ_employeur']} IS NOT NULL AND a.{q['champ_periode']} IS NOT NULL), "
        f"r AS (SELECT DISTINCT CAST(b.{reg} AS VARCHAR) AS employeur, {aff} AS affiliation, "
        f"{ces} AS cessation FROM b WHERE b.{reg} IS NOT NULL), "
        f"periodes AS (SELECT CAST(x AS DATE) AS debut_periode FROM generate_series("
        f"CAST(date_trunc('{unit}', CAST(? AS DATE)) AS TIMESTAMP), CAST(? AS TIMESTAMP), "
        f"INTERVAL {months} MONTH) g(x)), "
        f"dd AS (SELECT *, {late_days} AS jours_retard FROM d "
        f"WHERE d.debut_periode BETWEEN CAST(date_trunc('{unit}', CAST(? AS DATE)) AS DATE) "
        f"AND CAST(? AS DATE)), "
        f"dm AS (SELECT *, CAST(round(cotisations * CAST(? AS DECIMAL(9,4)) / 100 * {factor}, 2) "
        f"AS {AMOUNT}) AS majoration_due FROM dd d WHERE jours_retard > 0), "
        f"anomalies AS ("
        f"SELECT r.employeur, p.debut_periode, 'non_declarant' AS anomalie, "
        f"NULL::DATE AS date_depot, "
        f"NULL::BIGINT AS jours_retard, NULL::{AMOUNT} AS cotisations, "
        f"NULL::{AMOUNT} AS majoration_due, NULL::{AMOUNT} AS majoration_appliquee "
        f"FROM r CROSS JOIN periodes p "
        f"WHERE (r.affiliation IS NULL "
        f"OR r.affiliation < p.debut_periode + INTERVAL {months} MONTH) "
        f"AND (r.cessation IS NULL OR r.cessation >= p.debut_periode) "
        f"AND NOT EXISTS (SELECT 1 FROM d WHERE d.employeur = r.employeur "
        f"AND d.debut_periode = p.debut_periode) "
        f"UNION ALL SELECT employeur, debut_periode, 'declaration_tardive', date_depot, "
        f"jours_retard, cotisations, majoration_due, majoration_appliquee FROM dm "
    )
    # Dans l'ordre des « ? » : périodes attendues, retard, déclarations de l'exercice, taux.
    params: list[Any] = [p["debut"], p["fin"], p["delai_jours"], p["debut"], p["fin"]]
    params.append(p["taux_majoration"])
    if applied:
        sql += (
            "UNION ALL SELECT employeur, debut_periode, 'majoration_non_appliquee', date_depot, "
            "jours_retard, cotisations, majoration_due, majoration_appliquee FROM dm "
            f"WHERE coalesce(majoration_appliquee, 0) < majoration_due - CAST(? AS {AMOUNT}) "
        )
        params.append(p["tolerance"])
    sql += (
        "UNION ALL SELECT DISTINCT employeur, NULL, 'non_immatricule', NULL, NULL, NULL, NULL, "
        "NULL FROM d WHERE employeur NOT IN (SELECT employeur FROM r)) "
        "SELECT employeur, debut_periode AS periode, anomalie, date_depot, jours_retard, "
        "cotisations, majoration_due, majoration_appliquee FROM anomalies "
        "ORDER BY anomalie, employeur, periode NULLS FIRST"
    )
    df = evaluate_many({"a": rels[0], "b": rels[1]}, sql, params)
    counts = df["anomalie"].value_counts(sort=True)
    return OpResult(
        df,
        {
            "anomalies": df.height,
            "par_anomalie": dict(zip(counts["anomalie"], counts["count"], strict=True)),
            "employeurs_concernes": df["employeur"].n_unique(),
            "criteres_non_appliques": [] if applied else ["majoration_non_appliquee"],
        },
    )


register(
    Operation(
        "cip_recouvrement",
        "CIP-03",
        2,
        (
            Param("champ_employeur", "colonne"),
            Param("champ_periode", "colonne", types_colonne=DATES),
            Param("champ_date_depot", "colonne", types_colonne=DATES),
            Param("champ_cotisations", "colonne", types_colonne=NUMERIC),
            Param("champ_majoration", "colonne", requis=False, types_colonne=NUMERIC),
            Param("champ_employeur_registre", "colonne", table=1),
            Param("champ_date_affiliation", "colonne", requis=False, table=1, types_colonne=DATES),
            Param("champ_date_cessation", "colonne", requis=False, table=1, types_colonne=DATES),
            Param("debut", "date"),
            Param("fin", "date"),
            Param("periodicite", "choix", requis=False, defaut="mensuelle", choix=tuple(UNITS)),
            Param("delai_jours", "entier", minimum=0),
            Param("taux_majoration", "nombre", minimum=0, maximum=100),
            Param("par_mois", "entier", minimum=0, maximum=1),
            Param("tolerance", "nombre", requis=False, defaut="0", minimum=0),
        ),
        recouvrement,
    )
)


def creances(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    montant = _amount(quote_ident(p["champ_montant"]))
    due = f"CAST({quote_ident(p['champ_date_exigibilite'])} AS DATE)"
    dep = _amount(quote_ident(p["champ_depreciation"])) if p.get("champ_depreciation") else "0"
    ref = "CAST(? AS DATE)"
    expected = f"CAST(round({montant} * CAST(? AS DECIMAL(9,4)) / 100, 2) AS {AMOUNT})"
    sql = (
        f"WITH c AS (SELECT *, date_diff('day', {due}, {ref}) AS anciennete_jours, "
        f"{expected} AS depreciation_exigee, CAST({dep} AS {AMOUNT}) AS depreciation_constatee "
        f"FROM t WHERE {due} + INTERVAL (CAST(? AS INTEGER)) MONTH <= {ref}) "
        f"SELECT *, CAST(depreciation_exigee - depreciation_constatee AS {AMOUNT}) "
        f"AS insuffisance FROM c "
        f"WHERE depreciation_constatee < depreciation_exigee - CAST(? AS {AMOUNT}) "
        f"ORDER BY insuffisance DESC, anciennete_jours DESC"
    )
    ref_date = p["date_reference"]
    params = [ref_date, p["taux_depreciation"], p["anciennete_mois"], ref_date]
    params.append(p["tolerance"])
    df = evaluate(rels[0], sql, params)
    return OpResult(
        df,
        {
            "creances_retenues": df.height,
            "insuffisance_totale": str(df["insuffisance"].sum() if df.height else Decimal(0)),
            "creances_source": evaluate(rels[0], "SELECT count(*) FROM t").item(),
        },
    )


register(
    Operation(
        "cip_creances",
        "CIP-03",
        1,
        (
            Param("champ_montant", "colonne", types_colonne=NUMERIC),
            Param("champ_date_exigibilite", "colonne", types_colonne=DATES),
            Param("champ_depreciation", "colonne", requis=False, types_colonne=NUMERIC),
            Param("date_reference", "date"),
            Param("anciennete_mois", "entier", minimum=0),
            Param("taux_depreciation", "nombre", minimum=0, maximum=100),
            Param("tolerance", "nombre", requis=False, defaut="0", minimum=0),
        ),
        creances,
    )
)


BENEFICIARY_CRITERIA = (
    "doublon_identifiant",
    "nom_proche",
    "meme_compte",
    "age_anormal",
    "paye_apres_deces",
    "certificat_vie",
    "hors_bareme",
)


def _flags(rel: Relation, tests: dict[str, str], params: list[Any], order: str) -> Any:
    """Lignes remplissant au moins un critère, avec la liste et le nombre de critères."""
    flags = ", ".join(f'coalesce({sql}, FALSE) AS "__{name}"' for name, sql in tests.items())
    names = list(tests)
    listed = " || ".join(f"CASE WHEN \"__{n}\" THEN '{n}, ' ELSE '' END" for n in names)
    count = " + ".join(f'CAST("__{n}" AS INTEGER)' for n in names)
    exclude = ", ".join(f'"__{n}"' for n in names)
    return evaluate(
        rel,
        f"WITH base AS (SELECT row_number() OVER () AS __rang, * FROM t), "  # noqa: S608
        f"marked AS (SELECT *, {flags} FROM base) "
        f"SELECT * EXCLUDE (__rang, {exclude}), rtrim({listed}, ', ') AS criteres, "
        f"{count} AS nb_criteres FROM marked WHERE {count} > 0 "
        f"ORDER BY nb_criteres DESC, {order}, __rang",
        params,
    )


def _by_criterion(df: Any, criteria: tuple[str, ...]) -> dict[str, int]:
    out = {n: 0 for n in criteria}
    for value in df["criteres"].to_list():
        for name in value.split(", "):
            out[name] += 1
    return out


def prestations(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    ident = quote_ident(p["champ_identifiant"])
    col = {
        k: quote_ident(p[k]) if p.get(k) else None
        for k in (
            "champ_date_naissance",
            "champ_compte_bancaire",
            "champ_date_deces",
            "champ_dernier_paiement",
            "champ_certificat_vie",
            "champ_montant",
        )
    }
    ref = "CAST(? AS DATE)"
    tests: dict[str, str] = {"doublon_identifiant": f"count(*) OVER (PARTITION BY {ident}) > 1"}
    params: list[Any] = []
    birth = f"CAST({col['champ_date_naissance']} AS DATE)" if col["champ_date_naissance"] else None
    if birth:
        # Références qualifiées : dans la sous-requête, un nom nu désignerait la ligne « o ».
        def norm(alias: str) -> str:
            nom = quote_ident(p["champ_nom"])
            return f"lower(strip_accents(trim(CAST({alias}.{nom} AS VARCHAR))))"

        dob = col["champ_date_naissance"]
        tests["nom_proche"] = (
            f"EXISTS (SELECT 1 FROM base o WHERE CAST(o.{dob} AS DATE) = CAST(base.{dob} AS DATE) "
            f"AND o.{ident} IS DISTINCT FROM base.{ident} "
            f"AND jaro_winkler_similarity({norm('o')}, {norm('base')}) >= CAST(? AS DOUBLE))"
        )
        params.append(p["seuil_similarite"])
    if col["champ_compte_bancaire"]:
        account = f"nullif(trim(CAST({col['champ_compte_bancaire']} AS VARCHAR)), '')"
        tests["meme_compte"] = (
            f"{account} IS NOT NULL AND count(DISTINCT {ident}) OVER (PARTITION BY {account}) > 1"
        )
    if birth:
        tests["age_anormal"] = (
            f"date_sub('year', {birth}, {ref}) "
            f"NOT BETWEEN CAST(? AS INTEGER) AND CAST(? AS INTEGER)"
        )
        params += [p["date_reference"], p["age_minimum"], p["age_maximum"]]
    death = f"CAST({col['champ_date_deces']} AS DATE)" if col["champ_date_deces"] else None
    if death and col["champ_dernier_paiement"]:
        tests["paye_apres_deces"] = f"CAST({col['champ_dernier_paiement']} AS DATE) > {death}"
    if col["champ_certificat_vie"]:
        alive = f"{death} IS NULL AND " if death else ""
        tests["certificat_vie"] = (
            f"{alive}(CAST({col['champ_certificat_vie']} AS DATE) IS NULL OR "
            f"CAST({col['champ_certificat_vie']} AS DATE) + INTERVAL (CAST(? AS INTEGER)) MONTH "
            f"< {ref})"
        )
        params += [p["validite_certificat_mois"], p["date_reference"]]
    if col["champ_montant"]:
        amount = f"CAST({col['champ_montant']} AS {AMOUNT})"
        tests["hors_bareme"] = f"{amount} < CAST(? AS {AMOUNT}) OR {amount} > CAST(? AS {AMOUNT})"
        params += [p["montant_minimum"], p["montant_maximum"]]
    df = _flags(rels[0], tests, params, ident)
    return OpResult(
        df,
        {
            "lignes_source": evaluate(rels[0], "SELECT count(*) FROM t").item(),
            "lignes_retenues": df.height,
            "par_critere": _by_criterion(df, BENEFICIARY_CRITERIA),
            "criteres_non_appliques": [n for n in BENEFICIARY_CRITERIA if n not in tests],
        },
    )


register(
    Operation(
        "cip_prestations",
        "CIP-04",
        1,
        (
            Param("champ_identifiant", "colonne"),
            Param("champ_nom", "colonne"),
            Param("champ_date_naissance", "colonne", requis=False, types_colonne=DATES),
            Param("champ_compte_bancaire", "colonne", requis=False),
            Param("champ_date_deces", "colonne", requis=False, types_colonne=DATES),
            Param("champ_dernier_paiement", "colonne", requis=False, types_colonne=DATES),
            Param("champ_certificat_vie", "colonne", requis=False, types_colonne=DATES),
            Param("champ_montant", "colonne", requis=False, types_colonne=NUMERIC),
            Param("date_reference", "date"),
            Param("age_minimum", "entier", minimum=0, maximum=150),
            Param("age_maximum", "entier", minimum=0, maximum=150),
            Param("validite_certificat_mois", "entier", minimum=1),
            Param("montant_minimum", "nombre", minimum=0),
            Param("montant_maximum", "nombre", minimum=0),
            Param("seuil_similarite", "nombre", requis=False, defaut="0.9", minimum=0.5, maximum=1),
        ),
        prestations,
    )
)
