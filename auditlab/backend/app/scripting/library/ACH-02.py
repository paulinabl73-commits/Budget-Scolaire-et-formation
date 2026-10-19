# Loi de Benford sur les montants d'achats : un écart absolu moyen élevé appelle un examen
# des montants les plus sur-représentés.
MONTANT = "montant"

t = audit.table(audit.tables()[0])
b = audit.benford(t, MONTANT)
audit.save(b, "Benford achats")
mad = b.filter(b["chiffre"] == 0)["ecart"][0]
audit.metric("ecart_moyen_benford", mad)
print(f"Écart absolu moyen : {mad:.4f}")
