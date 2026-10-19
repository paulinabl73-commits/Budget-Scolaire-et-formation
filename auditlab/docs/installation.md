# Installation et exploitation d'AuditLab

Ce guide installe AuditLab sur un serveur Linux avec Docker Compose : PostgreSQL 16, stockage
S3 chiffré (SeaweedFS), Redis, API (FastAPI), worker (imports, analyses, scripts, tâches
planifiées), interface (nginx) et service de sauvegarde.

## 1. Prérequis

| Élément | Minimum | Recommandé (50 utilisateurs, NF-09) |
|---|---|---|
| Processeur | 4 vCPU | 8 vCPU (4 pour l'API, le reste pour PostgreSQL et le worker) |
| Mémoire | 8 Go | 16 Go (les scripts disposent de 2 Go chacun, DuckDB de 2 Go) |
| Disque | 50 Go SSD | Selon le volume analysé : prévoir 3 fois la taille des fichiers importés |
| Système | Linux x86_64, Docker 24+, Docker Compose 2.24+ | Disques chiffrés (LUKS) pour la base et les volumes |

Ports : 80 et 443 (interface et API derrière nginx). Aucun autre port n'est à exposer.

## 2. Récupérer l'application et préparer la configuration

```bash
git clone <dépôt> auditlab && cd auditlab/auditlab
cp .env.example .env
```

Compléter `.env` ; chaque secret doit être tiré au hasard :

| Variable | Rôle | Génération |
|---|---|---|
| `POSTGRES_PASSWORD` | Mot de passe de la base | `openssl rand -base64 24` |
| `AUDITLAB_SECRET_KEY` | Signature des liens de téléchargement | `openssl rand -hex 32` |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Compte de l'application sur le stockage | `openssl rand -hex 16` |
| `S3_SSE_KEK` | Clé de chiffrement au repos des fichiers (NF-06) | `openssl rand -hex 32` |
| `S3_SIGNING_KEY` | Signature interne du stockage | `openssl rand -base64 32` |
| `SAUVEGARDE_CLE_PUBLIQUE` | Destinataire des sauvegardes chiffrées (NF-12) | `age-keygen -o cle-sauvegarde.txt` (garder la clé privée hors du serveur) |
| `SAUVEGARDE_HOTE`, `SAUVEGARDE_HEURE`, `SAUVEGARDE_JOURS` | Cible, heure (UTC) et rétention des sauvegardes | `/srv/sauvegardes`, `02:00`, `30` |
| `AUDITLAB_SCRIPTS_HOST_DIR` | Répertoire de travail des scripts sur l'hôte (DAT-27) | `/var/lib/auditlab/scripts` |
| `DOCKER_GID` | Groupe propriétaire de `/var/run/docker.sock` | `stat -c %g /var/run/docker.sock` |
| `AUDITLAB_PUBLIC_URL` | Adresse publique (liens des e-mails, CORS) | `https://audit.exemple.org` |

Messagerie (facultatif, sinon les e-mails restent en file et sont journalisés) :
`AUDITLAB_SMTP_HOST`, `AUDITLAB_SMTP_PORT`, `AUDITLAB_SMTP_USER`, `AUDITLAB_SMTP_PASSWORD`,
`AUDITLAB_MAIL_FROM`, à déclarer pour les services `backend` et `worker`.

Autres paramètres (préfixe `AUDITLAB_`, valeurs par défaut adaptées) : durée de session
(`SESSION_IDLE_MINUTES`, 30), échecs avant verrouillage (`MAX_FAILED_LOGINS`, 5), conservation
des données analysées (`CONSERVATION_DONNEES_MOIS`, 60, NF-08), taille maximale d'un import
(`MAX_IMPORT_MB`, 2048), processus de l'API (`WEB_CONCURRENCY`, 4), connexions par processus
(`DB_POOL_SIZE` 15 + `DB_MAX_OVERFLOW` 5, à garder sous `max_connections` de PostgreSQL),
bac à sable des scripts (`SCRIPTS_MEMORY_MB` 2048, `SCRIPTS_TIMEOUT_S` 600,
`SCRIPTS_DOCKER_RUNTIME` = `runsc` si gVisor est installé), nom et adresse du cabinet pour les
lettres (`NOM_CABINET`, `ADRESSE_CABINET`). La liste complète est dans
`backend/app/config.py`.

## 3. Certificats TLS (NF-06)

Placer `fullchain.pem` et `privkey.pem` dans `./certs` (ou le chemin de `AUDITLAB_CERTS`),
par exemple délivrés par Let's Encrypt (certbot) ou par l'autorité de l'organisme.

## 4. Démarrer

```bash
sudo mkdir -p /var/lib/auditlab/scripts /srv/sauvegardes
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
docker compose ps        # tous les services « healthy » ou « running »
```

Les migrations de la base sont appliquées au démarrage de l'API ; les référentiels livrés
(SYSCOHADA révisé, modèle CIPRES, IFRS, cadres normatifs, programmes types, modèles de
rapports et de documents, bibliothèque de tests) sont installés par ces migrations.

Premier administrateur (mot de passe demandé de façon interactive) :

```bash
docker compose exec backend python -m app.cli create-admin --email admin@exemple.org --nom "Administrateur"
```

À la première connexion, l'administrateur active la double authentification (application
TOTP). Il crée ensuite les comptes (Directeur, chefs de mission, auditeurs, data analysts,
audités, experts-comptables…).

## 5. Premiers paramétrages

- **Univers et critères de risque** : à vérifier par le Directeur (Univers d'audit, Critères).
- **Modèles de rapport** : logo, page de garde et sections (menu « Modèles de rapport »).
- **Module 5** : paramètres réglementaires CIPRES par pays, modèles de liasse (DSF).
- **Module 6** : calendrier fiscal et social par pays, paramètres fiscaux (taux, barèmes) ;
  aucune valeur réglementaire n'est livrée.
- **Scripts** : vérifier que le worker lance bien un conteneur sans réseau (exécuter un script
  `import socket; socket.create_connection(("1.1.1.1", 80))` : il doit échouer).

## 6. Vérifier

```bash
curl -fsS https://audit.exemple.org/api/health                     # {"status":"ok"}
docker compose exec backend python -m app.cli verify-audit-chain    # chaîne du journal intègre
docker compose exec sauvegarde /ops/sauvegarde.sh                   # première sauvegarde
```

## 7. Exploitation courante

- **Journaux** : JSON sur la sortie standard de chaque conteneur (`docker compose logs`),
  un objet par requête avec durée, statut et utilisateur (NF-15) ; à collecter par la
  supervision de l'organisme.
- **Tâches planifiées** (worker avec `--beat`) : relances, alertes d'échéances, purge des
  données expirées (chaque jour à 6 h UTC), scripts planifiés (chaque heure).
- **Sauvegarde et restauration** : voir [`exploitation.md`](exploitation.md).
- **Données personnelles** : registre et purge, voir [`rgpd.md`](rgpd.md).
- **Mise à jour** : sauvegarde immédiate, puis `git pull` et
  `docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build` (migrations
  automatiques), puis `verify-audit-chain`.
- **Performance** : mesures et réglages dans [`performance.md`](performance.md) ; les scripts
  de mesure (`backend/perf/`) servent de test de réception sur l'infrastructure cible.
- **Accessibilité** : audit et pratiques dans [`accessibilite.md`](accessibilite.md).

## 8. Sécurité : points d'attention

- Ne jamais conserver les valeurs par défaut des secrets de `.env.example`.
- Le worker accède au démon Docker pour lancer le bac à sable des scripts : préférer Docker
  sans privilège (rootless) ou un mandataire de socket limité, et le runtime gVisor.
- La clé privée des sauvegardes reste hors du serveur ; tester une restauration chaque
  trimestre.
- L'API n'est exposée qu'à travers nginx ; PostgreSQL, Redis et le stockage ne sont pas
  publiés.

## 9. Développement local

Voir [`CLAUDE.md`](../CLAUDE.md) : lancement sans Docker (PostgreSQL local, `uvicorn`, `vite`),
tests (`pytest`, `vitest`), conventions.
