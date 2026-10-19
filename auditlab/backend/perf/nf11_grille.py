"""NF-11 : grille fluide sur 10 millions de lignes par chargement paginé côté serveur.

La grille (AG Grid, modèle « infinite ») demande des blocs de 100 lignes au serveur ; chaque
bloc est une requête DuckDB sur le Parquet avec LIMIT/OFFSET, tri et filtres traduits en SQL
(DAT-07). Le script mesure le temps d'un bloc au début, au milieu et à la fin de la table,
trié (le premier bloc trié prépare en arrière-plan une copie triée que les blocs suivants
lisent par position), filtré et avec recherche.

    AUDITLAB_DATA_DIR=/tmp/perf python perf/nf11_grille.py --lignes 10000000
"""

import argparse
import time
import uuid

import polars as pl

from app.analytics.grid import read_page
from app.analytics.relation import Relation
from app.analytics.store import parquet_ref, write_table

SORT = [{"colonne": "montant", "sens": "desc"}]
EQUALS = {"fournisseur": {"filterType": "text", "type": "equals", "filter": "42"}}
CASES = {
    "début, avec total": {"offset": 0, "total": True},
    "milieu": {"offset": 5_000_000},
    "fin": {"offset": 9_999_900},
    "tri, premier bloc (prépare)": {"offset": 0, "sort": SORT, "total": True},
    "tri, saut au milieu après 3 s": {"offset": 5_000_000, "sort": SORT, "pause": 3},
    "tri, bloc suivant": {"offset": 5_000_100, "sort": SORT},
    "tri, fin": {"offset": 9_999_900, "sort": SORT},
    "tri, saut au quart": {"offset": 2_500_000, "sort": SORT},
    "filtre égal, avec total": {"offset": 0, "total": True, "filters": EQUALS},
    "recherche plein texte": {"offset": 0, "search": "4242"},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lignes", type=int, default=10_000_000)
    args = parser.parse_args()
    n = args.lignes
    ids = pl.int_range(0, n, eager=True)
    df = pl.DataFrame({
        "piece": ids.cast(pl.Utf8).str.zfill(8),
        "fournisseur": (ids % 5000).cast(pl.Utf8),
        "montant": (ids * 7919 % 10_000_000) / 100,
    })  # fmt: skip
    start = time.perf_counter()
    written = write_table(df, uuid.uuid4())
    print(f"Table de {n} lignes écrite en {time.perf_counter() - start:.1f} s")
    rel = Relation(f"SELECT * FROM {parquet_ref(written.chemin)}", [], written.schema)  # noqa: S608
    worst = 0.0
    for label, case in CASES.items():
        case = {"sort": [], "filters": {}, "search": None, **case}
        offset = min(case.pop("offset"), max(n - 100, 0))
        total = case.pop("total", False)
        time.sleep(case.pop("pause", 0))  # temps de lecture de l'écran
        start = time.perf_counter()
        page = read_page(rel, offset=offset, limit=100, columns=None, with_total=total, **case)
        elapsed = time.perf_counter() - start
        worst = max(worst, elapsed)
        print(f"{label:28s} {elapsed:6.3f} s  {len(page['lignes'])} lignes  total={page['total']}")
    print(f"Bloc le plus lent : {worst:.3f} s")


if __name__ == "__main__":
    main()
