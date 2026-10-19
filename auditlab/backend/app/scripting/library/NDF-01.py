# Notes de frais présentées deux fois : même salarié, même date, même montant.
SALARIE, DATE, MONTANT = "salarie", "date_depense", "montant"

t = audit.table(audit.tables()[0])
d = audit.duplicates(t, [SALARIE, DATE, MONTANT])
audit.save(d, "Notes de frais en double")
audit.metric("doublons", d.height)
