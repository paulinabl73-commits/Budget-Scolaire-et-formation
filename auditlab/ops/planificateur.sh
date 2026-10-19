#!/bin/sh
# Service de sauvegarde (NF-12) : lance sauvegarde.sh chaque jour à SAUVEGARDE_HEURE (UTC,
# « 02:00 » par défaut). Une sauvegarde en échec est signalée dans le journal du conteneur et
# retentée le lendemain ; la supervision doit surveiller ces messages.
set -u
HEURE="${SAUVEGARDE_HEURE:-02:00}"
while true; do
  maintenant=$(date -u +%s)
  cible=$(date -u -d "$(date -u +%Y-%m-%d) $HEURE" +%s)
  [ "$cible" -le "$maintenant" ] && cible=$((cible + 86400))
  sleep $((cible - maintenant))
  if ! /ops/sauvegarde.sh; then
    echo "ÉCHEC de la sauvegarde du $(date -u +%Y-%m-%d)" >&2
  fi
done
