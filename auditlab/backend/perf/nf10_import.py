"""NF-10 : import d'un CSV d'un million de lignes en moins de 30 s ; doublons sur un million de
lignes en moins de 10 s.

Le fichier (séparateur « ; », virgule décimale, dates jj/mm/aaaa, comme un export comptable)
est généré une fois, de façon déterministe. L'import suit la chaîne de la tâche d'import :
lecture, typage, écriture Parquet en lecture seule, totaux de contrôle et empreinte (DAT-04).

    AUDITLAB_DATA_DIR=/tmp/perf python perf/nf10_import.py --dossier /tmp/perf --lignes 1000000
"""

import argparse
import random
import time
import uuid
from pathlib import Path

from app.analytics.formats import ColumnSpec, ReadOptions, apply_types, read_source
from app.analytics.operations.doublons import exact
from app.analytics.relation import Relation
from app.analytics.store import control_totals, file_sha256, parquet_ref, write_table


def generate(path: Path, rows: int) -> None:
    rnd = random.Random(2026)
    with path.open("w", encoding="utf-8") as f:
        f.write("N° pièce;Fournisseur;Date;Montant TTC\n")
        for i in range(rows):
            amount = f"{rnd.randint(1, 10**7) / 100:.2f}".replace(".", ",")
            day, month = rnd.randint(1, 28), rnd.randint(1, 12)
            f.write(
                f"P{i:07d};Fournisseur {rnd.randint(1, 5000)};{day:02d}/{month:02d}/2026;{amount}\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--lignes", type=int, default=1_000_000)
    args = parser.parse_args()
    source = args.dossier / f"nf10_{args.lignes}.csv"
    if not source.exists():
        args.dossier.mkdir(parents=True, exist_ok=True)
        generate(source, args.lignes)
    types = {"Date": "date", "Montant TTC": "decimal"}
    opts = ReadOptions(format="csv", colonnes=[ColumnSpec(nom=k, type=v) for k, v in types.items()])
    start = time.perf_counter()
    df = read_source(source, opts)
    converted = apply_types(df, types, opts)
    written = write_table(converted.df, uuid.uuid4())
    control_totals(written.chemin, written.schema)
    file_sha256(written.chemin)
    imported = time.perf_counter() - start
    print(f"Import de {written.nb_lignes} lignes : {imported:.2f} s (objectif < 30 s)")
    rel = Relation(f"SELECT * FROM {parquet_ref(written.chemin)}", [], written.schema)  # noqa: S608
    start = time.perf_counter()
    result = exact(rel, ["Fournisseur", "Montant TTC"])
    duplicates = time.perf_counter() - start
    print(f"Doublons exacts (fournisseur, montant) : {duplicates:.2f} s (objectif < 10 s) ; "
          f"{result.resultat}")  # fmt: skip
    print("OBJECTIF ATTEINT" if imported < 30 and duplicates < 10 else "OBJECTIF NON ATTEINT")


if __name__ == "__main__":
    main()
