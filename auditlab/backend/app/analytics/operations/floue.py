"""DAT-19 — recherche floue : paires de noms similaires entre deux listes.

Exemple d'usage : fournisseurs dont le nom ressemble à celui d'un salarié (conflit d'intérêts,
fournisseur fictif). Les noms sont normalisés (casse, accents, ponctuation, formes juridiques
usuelles en Afrique francophone et en France) puis comparés par la similarité de Jaro-Winkler.
"""

from typing import Any

from app.analytics.operations.base import (
    TEXT,
    AnalysisError,
    Operation,
    OpResult,
    Param,
    register,
    unique_name,
)
from app.analytics.operations.jointure import output_columns
from app.analytics.relation import Relation, evaluate_many
from app.analytics.store import quote_ident

MAX_PAIRS = 50_000_000
LEGAL_FORMS = (
    "sarl|sarlu|sa|sas|sasu|suarl|eurl|sci|snc|gie|ets|etablissements|ste|societe|cie|"
    "compagnie|groupe|holding|ltd|inc|llc|gmbh"
)


def normalize(column: str) -> str:
    text = f"lower(strip_accents(CAST({column} AS VARCHAR)))"
    text = f"regexp_replace({text}, '[^a-z0-9]+', ' ', 'g')"
    text = f"regexp_replace(' ' || {text} || ' ', ' ({LEGAL_FORMS}) ', ' ', 'g')"
    text = f"regexp_replace({text}, '\\s+', ' ', 'g')"
    return f"trim({text})"


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    named = {"a": rels[0], "b": rels[1]}
    na, nb = evaluate_many(named, "SELECT (SELECT count(*) FROM a), (SELECT count(*) FROM b)").row(
        0
    )
    if na * nb > MAX_PAIRS:
        raise AnalysisError("Plus de 50 millions de paires à comparer ; filtrez les listes")
    left, right = quote_ident(p["champ_gauche"]), quote_ident(p["champ_droite"])
    taken = {c["nom"] for c in rels[0].schema} | {c["nom"] for c in rels[1].schema}
    score = quote_ident(unique_name("similarite", taken))
    cols = ", ".join(output_columns(rels))
    sql = (
        f"WITH na AS (SELECT *, {normalize(left)} AS __n FROM a), "
        f"nb AS (SELECT *, {normalize(right)} AS __n FROM b) "
        f"SELECT round(jaro_winkler_similarity(a.__n, b.__n), 4) AS {score}, {cols} "
        "FROM na a JOIN nb b ON a.__n <> '' AND b.__n <> '' "
        "AND jaro_winkler_similarity(a.__n, b.__n) >= CAST(? AS DOUBLE) "
        # Score en première colonne : tri par similarité décroissante, puis par les noms.
        "ORDER BY ALL DESC"
    )
    df = evaluate_many(named, sql, [p["seuil"]])
    return OpResult(df, {"paires": df.height, "noms_gauche": na, "noms_droite": nb})


register(
    Operation(
        "floue",
        "DAT-19",
        2,
        (
            Param("champ_gauche", "colonne", types_colonne=TEXT),
            Param("champ_droite", "colonne", table=1, types_colonne=TEXT),
            Param("seuil", "nombre", requis=False, defaut="0.85", minimum=0.5, maximum=1),
        ),
        run,
    )
)
