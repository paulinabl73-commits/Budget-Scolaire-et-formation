"""DAT-09 — extraction des lignes qui satisfont une expression logique."""

from typing import Any

from app.analytics.expr import ExprError, compile_expression
from app.analytics.operations.base import AnalysisError, Operation, OpResult, Param, register
from app.analytics.relation import Relation, evaluate


def condition(rel: Relation, expression: str) -> tuple[str, list[Any]]:
    """Compile une condition et vérifie qu'elle donne vrai ou faux."""
    try:
        compiled = compile_expression(expression, rel.types)
    except ExprError as exc:
        raise AnalysisError(f"Expression : {exc} (caractère {exc.position + 1})") from exc
    probe = evaluate(rel, f"SELECT {compiled.sql} AS v FROM t LIMIT 0", compiled.params)  # noqa: S608
    if str(probe.schema["v"]) != "Boolean":
        raise AnalysisError("L'expression doit être une condition (vrai ou faux)")
    return compiled.sql, compiled.params


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    sql, params = condition(rel, p["expression"])
    # Ordre de la table d'origine conservé ; une condition vide (NULL) n'est pas retenue.
    df = evaluate(rel, f"SELECT * FROM t WHERE coalesce({sql}, FALSE)", params)  # noqa: S608
    total = evaluate(rel, "SELECT count(*) FROM t").item()
    return OpResult(
        df,
        {
            "lignes_source": total,
            "lignes_retenues": df.height,
            "pourcentage": round(100 * df.height / total, 2) if total else 0,
        },
    )


register(Operation("extraction", "DAT-09", 1, (Param("expression", "expression"),), run))
