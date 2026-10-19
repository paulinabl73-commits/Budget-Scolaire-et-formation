# Factures fournisseurs en double : même fournisseur, même numéro de facture ou même montant
# à la même date. Adapter les noms de colonnes à la table d'entrée.
FOURNISSEUR, FACTURE, MONTANT, DATE = "fournisseur", "numero_facture", "montant", "date_facture"

t = audit.table(audit.tables()[0])
par_numero = audit.duplicates(t, [FOURNISSEUR, FACTURE])
par_montant = audit.duplicates(t, [FOURNISSEUR, MONTANT, DATE])
audit.save(par_numero, "Factures en double (numéro)")
audit.save(par_montant, "Factures en double (montant et date)")
audit.metric("doublons", par_numero.height + par_montant.height)
print(f"{par_numero.height} ligne(s) par numéro, {par_montant.height} par montant et date")
