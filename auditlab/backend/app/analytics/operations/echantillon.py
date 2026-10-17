"""DAT-20 — échantillonnage : aléatoire simple, systématique, stratifié, unité monétaire (MUS).

La population est la table dans son ordre ; `ligne` donne le rang (à partir de 1) de chaque
ligne tirée, ce qui permet de la retrouver dans la population.
"""

from decimal import Decimal
from typing import Any

import polars as pl

from app.analytics.operations.base import (
    NUMERIC,
    AnalysisError,
    Operation,
    OpResult,
    Param,
    register,
    unique_name,
)
from app.analytics.relation import Relation, evaluate
from app.analytics.sampling import (
    SamplingError,
    monetary_unit,
    simple_random,
    stratified,
    systematic,
)

MAX_POPULATION = 20_000_000


def _strata(df: pl.DataFrame, p: dict[str, Any]) -> tuple[list[list[int]], list[str]]:
    if p.get("champ_strate"):
        keys = df[p["champ_strate"]].cast(pl.Utf8).fill_null("(vide)")
        labels = sorted(set(keys.to_list()))
        index = {k: i for i, k in enumerate(labels)}
        strata: list[list[int]] = [[] for _ in labels]
        for row, key in enumerate(keys.to_list()):
            strata[index[key]].append(row)
        return strata, labels
    if not p.get("champ_montant") or not p.get("bornes"):
        raise AnalysisError("Échantillon stratifié : champ de strate, ou champ montant et bornes")
    bounds = [Decimal(b) for b in p["bornes"]]
    labels = [f"< {bounds[0]}"] + [f"{a} à < {b}" for a, b in zip(bounds, bounds[1:], strict=False)]
    labels.append(f">= {bounds[-1]}")
    strata = [[] for _ in labels]
    for row, value in enumerate(df[p["champ_montant"]].to_list()):
        if value is None:
            continue
        strata[sum(1 for b in bounds if Decimal(str(value)) >= b)].append(row)
    return strata, labels


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    population = evaluate(rel, "SELECT count(*) FROM t").item()
    if population > MAX_POPULATION:
        raise AnalysisError("Population trop volumineuse : filtrez-la avant de l'échantillonner")
    df = evaluate(rel, "SELECT * FROM t")
    size, seed, method = int(p["taille"]), int(p["graine"]), p["methode"]
    taken = set(df.columns)
    ligne = unique_name("ligne", taken)
    info: dict[str, Any] = {
        "methode": method,
        "graine": seed,
        "taille_population": population,
    }
    extra: dict[str, list[Any]] = {}
    try:
        if method == "aleatoire":
            rows = simple_random(population, size, seed)
        elif method == "systematique":
            rows, step, start = systematic(population, size, seed)
            info.update(intervalle=round(step, 6), depart=round(start, 6))
        elif method == "stratifie":
            strata, labels = _strata(df, p)
            picked = stratified(strata, size, seed)
            rows = [r for _, r in picked]
            extra[unique_name("strate", taken)] = [labels[k] for k, _ in picked]
            info["strates"] = [
                {
                    "strate": labels[k],
                    "population": len(s),
                    "echantillon": sum(1 for x, _ in picked if x == k),
                }
                for k, s in enumerate(strata)
            ]
        else:
            if not p.get("champ_montant"):
                raise AnalysisError("Échantillon MUS : champ montant obligatoire")
            amounts = [
                Decimal(str(v)) if v is not None else Decimal(0) for v in df[p["champ_montant"]]
            ]
            selection = monetary_unit(amounts, size, seed)
            rows = sorted(selection.hits)
            extra[unique_name("point_selection", taken)] = [
                format(selection.hits[r][0], "f") for r in rows
            ]
            extra[unique_name("nb_selections", taken)] = [len(selection.hits[r]) for r in rows]
            positive = sum((a for a in amounts if a > 0), Decimal(0))
            info.update(
                intervalle=format(selection.interval, "f"),
                depart=format(selection.start, "f"),
                montant_population=format(positive, "f"),
                lignes_non_positives=sum(1 for a in amounts if a <= 0),
            )
    except SamplingError as exc:
        raise AnalysisError(str(exc)) from exc
    sample = df[rows]
    head = pl.DataFrame({ligne: [r + 1 for r in rows], **extra})
    out = pl.concat([head, sample], how="horizontal")
    info["taille_echantillon"] = out.height
    if p.get("champ_montant") and out.height:
        total = out[p["champ_montant"]].sum()
        info["montant_echantillon"] = format(total, "f") if isinstance(total, Decimal) else total
    return OpResult(out, info)


register(
    Operation(
        "echantillon",
        "DAT-20",
        1,
        (
            Param(
                "methode",
                "choix",
                defaut="aleatoire",
                choix=("aleatoire", "systematique", "stratifie", "mus"),
            ),  # fmt: skip
            Param("taille", "entier", minimum=1, maximum=100_000),
            Param("graine", "graine", requis=False, minimum=0, maximum=2**31 - 1),
            Param("champ_montant", "colonne", requis=False, types_colonne=NUMERIC),
            Param("champ_strate", "colonne", requis=False),
            Param("bornes", "nombres", requis=False),
        ),
        run,
    )
)
