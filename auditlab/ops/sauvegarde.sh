#!/bin/sh
# Sauvegarde quotidienne (NF-12) : base PostgreSQL (pg_dump, format personnalisé), fichiers
# stockés (pièces jointes, rapports, sources) et tables Parquet (Module 2), chiffrés avec age
# (NF-06) puis conservés SAUVEGARDE_JOURS jours. Chaque archive est accompagnée de son empreinte
# SHA-256 pour contrôler son intégrité avant restauration.
#
# Variables : PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE (connexion), SAUVEGARDE_DIR (cible),
# SAUVEGARDE_CLE_PUBLIQUE (destinataire age, « age1… »), SAUVEGARDE_SOURCES (répertoires de
# fichiers, séparés par des espaces), SAUVEGARDE_JOURS (rétention, 30 par défaut).
set -eu

: "${SAUVEGARDE_DIR:?répertoire de sauvegarde attendu}"
: "${SAUVEGARDE_CLE_PUBLIQUE:?clé publique age attendue}"
JOURS="${SAUVEGARDE_JOURS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CIBLE="$SAUVEGARDE_DIR/$STAMP"
mkdir -p "$CIBLE"
umask 077

echo "[$STAMP] base de données"
pg_dump --format=custom --no-owner --compress=6 | age -r "$SAUVEGARDE_CLE_PUBLIQUE" > "$CIBLE/base.dump.age"

for source in ${SAUVEGARDE_SOURCES:-}; do
  nom="$(basename "$source")"
  echo "[$STAMP] fichiers : $source"
  tar -C "$(dirname "$source")" -czf - "$nom" | age -r "$SAUVEGARDE_CLE_PUBLIQUE" > "$CIBLE/$nom.tar.gz.age"
done

(cd "$CIBLE" && sha256sum ./*.age > SHA256SUMS)
echo "[$STAMP] terminé : $(du -sh "$CIBLE" | cut -f1)"

# Rétention : suppression des sauvegardes plus anciennes que JOURS jours.
find "$SAUVEGARDE_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+$JOURS" -exec rm -rf {} +
