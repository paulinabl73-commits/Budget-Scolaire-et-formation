# Paiements datés d'un samedi ou d'un dimanche.
DATE = "date_paiement"
import polars as pl

t = audit.table(audit.tables()[0])
w = t.filter(pl.col(DATE).cast(pl.Date, strict=False).dt.weekday() >= 6)
audit.save(w, "Paiements en fin de semaine")
audit.metric("paiements_fin_semaine", w.height)
