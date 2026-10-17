"""REV-17 — tests des écritures de journal (ISA 240) sur un grand livre.

Chaque ligne d'écriture est examinée selon sept critères ; la table produite contient les
lignes qui en remplissent au moins un, avec la liste des critères et leur nombre (les plus
suspectes en tête). Un critère dont la colonne n'est pas fournie n'est pas appliqué, ce que la
synthèse indique.

- manuelle : journal de la liste des journaux d'opérations diverses ;
- week_end : écriture datée (ou saisie, si la date de saisie est fournie) un samedi ou un
  dimanche ;
- apres_cloture : saisie après la date de clôture des comptes ;
- montant_rond : montant multiple du pas choisi, au moins égal à ce pas ;
- compte_inhabituel : compte mouvementé par au plus N lignes du grand livre ;
- utilisateur_inhabituel : utilisateur auteur d'au plus N lignes ;
- libelle_vide : libellé absent ou blanc.
"""

from typing import Any

from app.analytics.operations.base import DATES, NUMERIC, Operation, OpResult, Param, register
from app.analytics.relation import Relation, evaluate
from app.analytics.store import quote_ident

CRITERIA = (
    "manuelle",
    "week_end",
    "apres_cloture",
    "montant_rond",
    "compte_inhabituel",
    "utilisateur_inhabituel",
    "libelle_vide",
)


def run(rels: list[Relation], p: dict[str, Any]) -> OpResult:
    rel = rels[0]
    q = {
        k: quote_ident(p[k]) for k in ("champ_date", "champ_compte", "champ_debit", "champ_credit")
    }
    opt = {
        k: quote_ident(p[k]) if p.get(k) else None
        for k in ("champ_journal", "champ_utilisateur", "champ_libelle", "champ_date_saisie")
    }
    amount = f"(coalesce({q['champ_debit']}, 0) + coalesce({q['champ_credit']}, 0))"
    entered = opt["champ_date_saisie"] or q["champ_date"]
    params: list[Any] = []
    tests: dict[str, str] = {}
    if opt["champ_journal"]:
        journals = [j.strip().upper() for j in str(p["journaux_manuels"]).split(",") if j.strip()]
        marks = ", ".join("?" for _ in journals) or "NULL"
        tests["manuelle"] = f"upper(trim(CAST({opt['champ_journal']} AS VARCHAR))) IN ({marks})"
        params += journals
    tests["week_end"] = f"isodow(CAST({entered} AS DATE)) IN (6, 7)"
    if opt["champ_date_saisie"]:
        tests["apres_cloture"] = f"CAST({opt['champ_date_saisie']} AS DATE) > CAST(? AS DATE)"
        params.append(p["date_cloture"])
    step = float(p["pas_montant_rond"])
    tests["montant_rond"] = f"{amount} >= ? AND {amount} % ? = 0"
    params += [step, step]
    tests["compte_inhabituel"] = f"count(*) OVER (PARTITION BY {q['champ_compte']}) <= ?"
    params.append(int(p["lignes_max_compte"]))
    if opt["champ_utilisateur"]:
        tests["utilisateur_inhabituel"] = (
            f"{opt['champ_utilisateur']} IS NOT NULL AND "
            f"count(*) OVER (PARTITION BY {opt['champ_utilisateur']}) <= ?"
        )
        params.append(int(p["lignes_max_utilisateur"]))
    if opt["champ_libelle"]:
        tests["libelle_vide"] = f"coalesce(trim(CAST({opt['champ_libelle']} AS VARCHAR)), '') = ''"
    flags = ", ".join(f'coalesce({sql}, FALSE) AS "__{name}"' for name, sql in tests.items())
    names = list(tests)
    listed = " || ".join(f"CASE WHEN \"__{n}\" THEN '{n}, ' ELSE '' END" for n in names)
    count = " + ".join(f'CAST("__{n}" AS INTEGER)' for n in names)
    exclude = ", ".join(f'"__{n}"' for n in names)
    df = evaluate(
        rel,
        f"WITH marked AS (SELECT row_number() OVER () AS __rang, *, {flags} FROM t) "  # noqa: S608
        f"SELECT * EXCLUDE (__rang, {exclude}), rtrim({listed}, ', ') AS criteres, "
        f"{count} AS nb_criteres FROM marked WHERE {count} > 0 "
        f"ORDER BY nb_criteres DESC, {q['champ_date']}, __rang",
        params,
    )
    total = evaluate(rel, "SELECT count(*) FROM t").item()
    by_criterion = {n: 0 for n in CRITERIA}
    for value in df["criteres"].to_list():
        for name in value.split(", "):
            by_criterion[name] += 1
    return OpResult(
        df,
        {
            "lignes_source": total,
            "lignes_retenues": df.height,
            "par_critere": by_criterion,
            "criteres_non_appliques": [n for n in CRITERIA if n not in tests],
        },
    )


register(
    Operation(
        "ecritures_journal",
        "REV-17",
        1,
        (
            Param("champ_date", "colonne", types_colonne=DATES),
            Param("champ_compte", "colonne"),
            Param("champ_debit", "colonne", types_colonne=NUMERIC),
            Param("champ_credit", "colonne", types_colonne=NUMERIC),
            Param("date_cloture", "date"),
            Param("champ_journal", "colonne", requis=False),
            Param("journaux_manuels", "texte", requis=False, defaut="OD"),
            Param("champ_utilisateur", "colonne", requis=False),
            Param("champ_libelle", "colonne", requis=False),
            Param("champ_date_saisie", "colonne", requis=False, types_colonne=DATES),
            Param("pas_montant_rond", "nombre", requis=False, defaut="100000", minimum=1),
            Param("lignes_max_compte", "entier", requis=False, defaut=3, minimum=1),
            Param("lignes_max_utilisateur", "entier", requis=False, defaut=5, minimum=1),
        ),
        run,
    )
)
