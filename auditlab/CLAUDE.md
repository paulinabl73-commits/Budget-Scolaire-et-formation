# AuditLab — conventions pour Claude Code

Le cahier des charges complet est dans `docs/cahier-des-charges.pdf`. Le travail avance par lots
(section 12). Ne réaliser que le lot demandé. Ne jamais modifier une exigence déjà livrée sans
le signaler. Mettre à jour ce fichier et `docs/avancement.md` en fin de lot.

## Structure

```
auditlab/
  backend/            API FastAPI (Python 3.12, SQLAlchemy 2, Alembic, PostgreSQL 16)
    app/
      api/            routes HTTP ; deps.py = authentification et contrôle d'accès
      audit/          chain.py (chaînage par hash), listeners.py (journalisation automatique)
      models/         modèles SQLAlchemy ; base.py = TrackedMixin
      security/       passwords (Argon2), totp, sessions, roles (matrice des droits)
      cli.py          commandes d'exploitation
    alembic/versions/ migrations
    tests/            pytest (base PostgreSQL réelle)
  frontend/           React 18, TypeScript, Vite, Tailwind, AG Grid
    src/i18n/fr.json  TOUS les textes de l'interface (NF-13)
  docker-compose.yml  db + backend + frontend (nginx, proxy /api)
```

## Commandes

```bash
# Base de développement locale (PostgreSQL 16) : bases auditlab et auditlab_test,
# utilisateur auditlab/auditlab (superutilisateur nécessaire pour les tests).

# Backend
cd backend
uv venv .venv -p 3.12 && uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/alembic upgrade head                      # migrer
.venv/bin/alembic revision --autogenerate -m "..."  # nouvelle migration
.venv/bin/uvicorn app.main:app --reload             # lancer (port 8000)
.venv/bin/pytest                                    # tester (couverture minimale de 80 %)
.venv/bin/ruff check . && .venv/bin/ruff format .   # linter et formatage
.venv/bin/python -m app.cli create-admin --email admin@exemple.org
.venv/bin/python -m app.cli verify-audit-chain

# Frontend
cd frontend
npm install
npm run dev          # port 5173, proxy /api vers localhost:8000
npm test             # Vitest
npm run typecheck
npm run build

# Tout lancer
docker compose up -d --build
```

## Décisions et conventions

- **Modèles métier** : tous héritent de `TrackedMixin`, qui fournit `id` (UUID), `created_*`,
  `updated_*` et `deleted_*`. Un écouteur `before_flush` (`app/audit/listeners.py`) :
  - écrit automatiquement une entrée `AuditLog` (avant/après) pour chaque création,
    modification ou suppression logique (NF-01) ;
  - remplit `created_by` et `updated_by` à partir de `session.info["actor_id"]`, posé par
    `api/deps.py` ;
  - refuse toute suppression physique (`AuditIntegrityError`, NF-03). Pour supprimer, poser
    `deleted_at` et filtrer `deleted_at IS NULL` dans les requêtes.
- **Champs sensibles** : les déclarer dans `__audit_masked__` (valeur `***` dans le journal).
- **Événements hors objet** (connexion, vérification…) : utiliser
  `record_event(db, "action", ...)`.
- **Journal d'audit (NF-02)** :
  - `seq` est continu ; `hash` est le SHA-256 du JSON canonique de l'entrée, qui inclut
    `hash_precedent`.
  - L'écriture est sérialisée par `pg_advisory_xact_lock`.
  - En base, un déclencheur refuse UPDATE, DELETE et TRUNCATE sur `audit_log`. Les tests le
    contournent avec `session_replication_role = replica`, et uniquement les tests.
- **Sessions** : jeton opaque porté par `Authorization: Bearer` ; seul son SHA-256 est stocké.
  Une session expire après 30 minutes d'inactivité ; le compte est verrouillé après 5 échecs
  et seul un administrateur peut le déverrouiller (NF-07).
- **Double authentification** : obligatoire pour les rôles Administrateur et Directeur.
  Tant qu'elle n'est pas activée, la session est limitée à l'enrôlement (`mfa_enrollment_only`).
- **Droits** : la matrice de la section 2 est dans `security/roles.py`. Chaque route vérifie ses
  droits avec `Depends(require(Perm.X))`. Côté interface, les droits ne servent qu'à
  l'affichage. Les restrictions par mission viendront avec le lot 3.
- **Séparation des tâches** : `roles.can_review(preparateur, reviseur)`, à appliquer aux
  signatures du lot 4.
- **E-mails** : validation volontairement souple, pour accepter les domaines internes (`.local`).
- **Interface** : aucun texte en dur ; passer par `t("...")`. Nombres et dates au format
  français (`lib/format.ts`). Toujours associer un `label` à chaque champ (RGAA).
- **Commits** : un commit par exigence, préfixé par son code (ex. `AUD-01: ...`).
