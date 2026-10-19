#!/bin/sh
# Restauration (NF-12) d'une sauvegarde produite par sauvegarde.sh : contrôle des empreintes,
# déchiffrement avec la clé privée age, restauration de la base (dans une base vide ou
# remplacée) et des répertoires de fichiers, puis vérification de la chaîne du journal
# d'audit par l'application.
#
#   restauration.sh <répertoire de la sauvegarde> <fichier de clé privée age> [cible des fichiers]
#
# Variables de connexion : PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE (base de destination).
set -eu

SOURCE="${1:?répertoire de la sauvegarde attendu}"
CLE="${2:?fichier de clé privée age attendu}"
FICHIERS="${3:-}"

echo "Contrôle des empreintes"
(cd "$SOURCE" && sha256sum -c SHA256SUMS)

echo "Restauration de la base $PGDATABASE"
age -d -i "$CLE" "$SOURCE/base.dump.age" | pg_restore --clean --if-exists --no-owner --exit-on-error -d "$PGDATABASE"

if [ -n "$FICHIERS" ]; then
  for archive in "$SOURCE"/*.tar.gz.age; do
    [ -e "$archive" ] || continue
    echo "Restauration des fichiers : $(basename "$archive")"
    mkdir -p "$FICHIERS"
    age -d -i "$CLE" "$archive" | tar -C "$FICHIERS" -xzf -
  done
fi
echo "Restauration terminée : vérifier ensuite « python -m app.cli verify-audit-chain »."
