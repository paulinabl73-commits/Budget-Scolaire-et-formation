# Paiements en double : même bénéficiaire, même montant, même date.
BENEFICIAIRE, MONTANT, DATE = "beneficiaire", "montant", "date_paiement"

t = audit.table(audit.tables()[0])
d = audit.duplicates(t, [BENEFICIAIRE, MONTANT, DATE])
audit.save(d, "Paiements en double")
audit.metric("doublons", d.height)
