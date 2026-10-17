# Avancement

| Lot | Contenu | État |
|-----|---------|------|
| 1 | Socle : dépôt, PostgreSQL, Alembic, authentification, rôles, AuditLog chaîné (NF-01, NF-02), CI | **Livré** |
| 2 | Univers et plan : AUD-01 à AUD-05 | À faire |
| 3 | Missions et programme : AUD-06 à AUD-12 | À faire |
| 4 | Papiers de travail et revue : AUD-13 à AUD-22 | À faire |
| 5 | Import de données : DAT-01 à DAT-08 | À faire |
| 6 | Analyses : DAT-09 à DAT-19 | À faire |
| 7 | Échantillonnage et lignée : DAT-20 à DAT-25 | À faire |
| 8 | Liaison audit et analyse, constats : DAT-30 à DAT-32, CON-01 à CON-09 | À faire |
| 8a | Référentiels et balance : REV-01 à REV-14 | À faire |
| 8b | Révision et états : REV-15 à REV-28, CIP-01 à CIP-09, IFR-01 à IFR-04 | À faire |
| 8c | Portefeuille et contrôles : RCO-01 à RCO-10 | À faire |
| 8d | Inventaire, fiscalité et livrables : RCO-11 à RCO-27 | À faire |
| 9 | Scripts et automatisation : DAT-26 à DAT-29 | À faire |
| 10 | Reporting et finitions : REP-01 à REP-08, NF-09 à NF-11 | À faire |

## Lot 1 — détail

**Livré**
- Authentification par e-mail et mot de passe haché en Argon2id, avec politique de mot de passe.
- Double authentification TOTP obligatoire pour les rôles Administrateur et Directeur, enrôlement
  par QR code.
- Sessions serveur expirées après 30 minutes d'inactivité ; verrouillage après 5 échecs ;
  déverrouillage et réinitialisation du TOTP par un administrateur (NF-07).
- Six rôles et matrice des droits de la section 2, contrôlés côté serveur sur chaque requête.
- Utilisateurs et équipes : création, modification, désactivation, suppression logique (NF-03).
- AuditLog :
  - journalisation automatique avant/après de chaque création, modification et suppression,
    ainsi que des connexions et des échecs (NF-01) ;
  - ajout seul garanti par un déclencheur SQL, chaînage SHA-256 et vérification par la commande
    `verify-audit-chain` ou par l'interface (NF-02).
- Journalisation applicative JSON (NF-15).
- Interface en français avec textes externalisés (NF-13), grilles AG Grid, journal paginé côté
  serveur.
- Docker Compose (PostgreSQL, API, nginx) et CI GitHub Actions (lint, tests, build, démarrage
  Docker).
- Tests : 57 tests backend (couverture de 99 %, refus d'accès testés pour chaque rôle) et
  11 tests frontend.

**Reste ouvert**
- SSO OIDC (Azure AD, Keycloak), optionnel, pas encore branché.
- Redis, Celery et MinIO : à ajouter au Compose à partir des lots 5 et 9, quand ils servent.
- Les changements d'appartenance aux équipes (table d'association) ne sont pas encore
  journalisés champ à champ.
- Tests de bout en bout Playwright : à écrire au fil des lots, pour le scénario de la section 13.
- Questions ouvertes du cahier des charges (référentiel méthodologique, hébergement, SSO,
  volumétrie) : à trancher avant le lot 2.
