"""DAT-15 — loi de Benford : test du khi-deux, MAD et lignes suspectes.

Méthode de M. Nigrini (Benford's Law, 2012) : montants en valeur absolue, inférieurs au seuil
exclus (10 par défaut) ; statistique z avec correction de continuité ; seuils de conformité de
la MAD propres à chaque test.
"""

import math
from typing import Any

from app.analytics.operations.base import NUMERIC, Operation, OpResult, Param, register
from app.analytics.relation import Relation, evaluate
from app.analytics.statistics import chi2_sf
from app.analytics.store import quote_ident

Z_CRITICAL = 1.96  # seuil de 5 %

# Seuils MAD de Nigrini : conformité étroite, acceptable, marginale ; au-delà, non-conformité.
MAD_THRESHOLDS = {
    "premier": (0.006, 0.012, 0.015),
    "second": (0.008, 0.010, 0.012),
    "deux_premiers": (0.0012, 0.0018, 0.0022),
}


def expected(test: str) -> dict[int, float]:
    if test == "premier":
        return {d: math.log10(1 + 1 / d) for d in range(1, 10)}
    if test == "second":
        return {d: sum(math.log10(1 + 1 / (10 * k + d)) for k in range(1, 10)) for d in range(10)}
    return {d: math.log10(1 + 1 / d) for d in range(10, 100)}


def conformity(test: str, mad: float) -> str:
    close, acceptable, marginal = MAD_THRESHOLDS[test]
    if mad <= close:
        return "conformite_etroite"
    if mad <= acceptable:
        return "conformite_acceptable"
    if mad <= marginal:
        return "conformite_marginale"
    return "non_conformite"


def z_stat(observed: float, exp: float, n: int) -> float:
    diff = abs(observed - exp)
    correction = 1 / (2 * n)
    if correction < diff:
        diff -= correction
    return diff / math.sqrt(exp * (1 - exp) / n)


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    test = p["test"]
    q = quote_ident(p["champ"])
    digits = (
        f"ltrim(regexp_replace(CAST(abs(CAST({q} AS DECIMAL(38, 4))) AS VARCHAR), "
        "'[^0-9]', '', 'g'), '0')"
    )
    pick = {
        "premier": f"left({digits}, 1)",
        "second": f"substr({digits}, 2, 1)",
        "deux_premiers": f"left({digits}, 2)",
    }[test]
    where = f"{q} IS NOT NULL AND abs({q}) >= CAST(? AS DECIMAL(38, 4))"
    digit_sql = f"TRY_CAST({pick} AS INTEGER)"
    minimum = p["montant_minimum"]
    counts = dict(
        evaluate(
            rel,
            f"SELECT {digit_sql} AS d, count(*) FROM t WHERE {where} GROUP BY 1",
            [minimum],
        ).rows()
    )
    probabilities = expected(test)
    n = sum(counts.get(d, 0) for d in probabilities)
    table = []
    chi2 = mad = 0.0
    for d, pe in probabilities.items():
        o = counts.get(d, 0)
        po = o / n if n else 0.0
        z = z_stat(po, pe, n) if n else 0.0
        chi2 += (o - n * pe) ** 2 / (n * pe) if n else 0
        mad += abs(po - pe)
        table.append(
            {
                "chiffres": d,
                "observes": o,
                "attendus": round(n * pe, 4),
                "part_observee": round(po, 6),
                "part_attendue": round(pe, 6),
                "z": round(z, 4),
                "significatif": bool(n) and z > Z_CRITICAL and po > pe,
            }
        )
    mad /= len(probabilities)
    suspicious = [row["chiffres"] for row in table if row["significatif"]]
    if suspicious:
        marks = ", ".join("?" for _ in suspicious)
        df = evaluate(
            rel,
            f"SELECT *, {digit_sql} AS chiffres FROM t WHERE {where} AND {digit_sql} IN ({marks})",
            [minimum, *suspicious],
        )
    else:
        df = evaluate(rel, f"SELECT *, {digit_sql} AS chiffres FROM t WHERE FALSE")
    dof = len(probabilities) - 1
    return OpResult(
        df,
        {
            "montants_retenus": n,
            "khi2": round(chi2, 4),
            "ddl": dof,
            "p_valeur": round(chi2_sf(chi2, dof), 6) if n else None,
            "mad": round(mad, 6),
            "conformite": conformity(test, mad) if n else None,
            "chiffres_significatifs": suspicious,
            "lignes_suspectes": df.height,
            "chiffres": table,
        },
    )


register(
    Operation(
        "benford",
        "DAT-15",
        1,
        (
            Param("champ", "colonne", types_colonne=NUMERIC),
            Param("test", "choix", defaut="premier", choix=("premier", "second", "deux_premiers")),
            Param("montant_minimum", "nombre", requis=False, defaut="10", minimum=0),
        ),
        run,
    )
)
