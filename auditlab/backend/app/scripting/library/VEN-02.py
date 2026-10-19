# Factures de vente en double : même client, même montant, même date.
CLIENT, MONTANT, DATE = "client", "montant", "date_facture"

t = audit.table(audit.tables()[0])
d = audit.duplicates(t, [CLIENT, MONTANT, DATE])
audit.save(d, "Ventes en double")
audit.metric("doublons", d.height)
