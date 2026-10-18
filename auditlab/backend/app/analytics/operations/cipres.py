"""CIP-02 à CIP-05 — contrôles des organismes de prévoyance sociale sur leurs fichiers.

Les taux, plafonds, délais, âges et barèmes sont des paramètres de l'opération : lancée depuis
un dossier CIPRES, ils sont lus dans le référentiel (CIP-09) et ne sont pas modifiables.

- cip_cotisations (CIP-02) : déclarations nominatives des salaires (une ligne par salarié et
  par période) et cotisations émises et encaissées par employeur. Cotisation théorique par
  branche = Σ min(salaire, plafond × mois de la période) × taux ; un plafond nul signifie
  « sans plafond ». Une ligne par employeur, anomalie indiquée.
"""

from decimal import Decimal
from typing import Any

from app.analytics.operations.base import NUMERIC, Operation, OpResult, Param, register
from app.analytics.relation import Relation, evaluate_many
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
