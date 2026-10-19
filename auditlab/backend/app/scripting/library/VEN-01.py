# Ruptures de numérotation des factures de vente (factures manquantes ou annulées à justifier).
NUMERO = "numero_facture"

t = audit.table(audit.tables()[0])
g = audit.gaps(t, NUMERO)
audit.save(g, "Ruptures de séquence des ventes")
audit.metric("factures_manquantes", g["manquants"].sum() if g.height else 0)
