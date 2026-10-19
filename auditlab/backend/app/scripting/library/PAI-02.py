# Salaires versés après la date de sortie du salarié.
MATRICULE, PAIEMENT, SORTIE = "matricule", "date_paiement", "date_sortie"
import polars as pl

t = audit.table(audit.tables()[0])
apres = t.filter(pl.col(SORTIE).is_not_null() & (pl.col(PAIEMENT) > pl.col(SORTIE)))
audit.save(apres, "Paiements après la sortie")
audit.metric("paiements_apres_sortie", apres.height)
