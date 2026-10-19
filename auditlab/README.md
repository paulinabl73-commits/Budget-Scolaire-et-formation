# AuditLab

Plateforme web qui réunit la **gestion des missions d'audit** (à la manière de TeamMate) et
**l'analyse de données d'audit** (à la manière d'IDEA), avec la révision des comptes
SYSCOHADA / IFRS / CIPRES. Cahier des charges : [`docs/cahier-des-charges.pdf`](docs/cahier-des-charges.pdf).

> **État : lots 1 à 10 livrés** (détail dans [`docs/avancement.md`](docs/avancement.md),
> hypothèses retenues dans [`docs/hypotheses.md`](docs/hypotheses.md)).
>
> Installation en production (TLS, sauvegardes, paramétrage) :
> [`docs/installation.md`](docs/installation.md).

## Démarrage rapide (Docker)

```bash
cd auditlab
cp .env.example .env            # puis changer POSTGRES_PASSWORD
docker compose up -d --build
# Premier administrateur (le mot de passe est demandé de façon interactive)
docker compose exec backend python -m app.cli create-admin --email admin@exemple.org --nom "Administrateur"
```

Ouvrir <http://localhost:8080>. À la première connexion, l'administrateur doit activer la
double authentification : scanner le QR code avec une application TOTP (Microsoft
Authenticator, Google Authenticator, FreeOTP…).

La documentation de l'API est disponible sur <http://localhost:8080/api/docs>.

## Vérifier l'intégrité du journal d'audit

```bash
docker compose exec backend python -m app.cli verify-audit-chain
```

La commande recalcule la chaîne de hash de toutes les entrées. Elle renvoie le code 1 et
indique l'entrée concernée en cas de rupture. La même vérification est disponible dans
l'interface (*Journal d'audit* → *Vérifier l'intégrité de la chaîne*).

## Développement

Voir [`CLAUDE.md`](CLAUDE.md) pour les commandes (lancer, tester, migrer) et les conventions.
