# Dépenses juste sous le seuil d'approbation (fractionnement) : SEUIL est la règle interne de
# l'entité, MARGE la fraction du seuil retenue (10 % sous le seuil par défaut).
MONTANT, SEUIL, MARGE = "montant", 100_000, 0.10
import polars as pl

t = audit.table(audit.tables()[0])
proches = t.filter((pl.col(MONTANT) < SEUIL) & (pl.col(MONTANT) >= SEUIL * (1 - MARGE)))
audit.save(proches, "Dépenses juste sous le seuil")
audit.metric("depenses_sous_seuil", proches.height)
