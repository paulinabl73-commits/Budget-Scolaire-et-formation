# Salariés fictifs : un même compte bancaire pour plusieurs matricules.
MATRICULE, COMPTE = "matricule", "compte_bancaire"

t = audit.table(audit.tables()[0])
comptes = t.select(MATRICULE, COMPTE).unique()
d = audit.duplicates(comptes, [COMPTE])
audit.save(d, "Comptes bancaires partagés")
audit.metric("matricules_concernes", d.height)
