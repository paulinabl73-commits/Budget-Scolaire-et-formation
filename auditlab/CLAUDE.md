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
                      universe.py, risk.py, plans.py = lot 2
                      engagements.py, engagement_status.py, timesheets.py, library.py,
                      program.py, templates.py, mission_access.py = lot 3
                      workpapers.py, attachments.py, tickmarks.py, signoffs.py,
                      review_notes.py, notifications.py = lot 4
                      datasets.py, imports.py, views.py = lot 5 ; analyses.py = lot 6
      analytics/      Module 2 : store.py (Parquet, DuckDB), formats.py, detect.py, pdf.py,
                      sql_source.py, jobs.py (tâches Celery), expr.py (expressions),
                      relation.py (relation SQL d'une table ou d'une vue), grid.py,
                      statistics.py, operations/ (une analyse par module, lot 6)
      audit/          chain.py (chaînage par hash), listeners.py (journalisation automatique)
      models/         modèles SQLAlchemy ; base.py = TrackedMixin
      security/       passwords (Argon2), totp, sessions, roles (matrice des droits)
      risk_scoring.py calcul du score de risque (fonctions pures, testées seules)
      schemas_plan.py schémas Pydantic du lot 2 ; schemas_mission.py (lot 3) ; schemas_workpaper.py (lot 4)
      richtext.py     documents riches (validation, texte brut) ; workpaper_versions.py (versions, diff)
      storage.py      stockage des fichiers (local ou S3/MinIO) ; signing.py (liens signés)
      notify.py       notifications et file d'e-mails
      cli.py          commandes d'exploitation
    alembic/versions/ migrations
    tests/            pytest (base PostgreSQL réelle)
  frontend/           React 18, TypeScript, Vite, Tailwind, AG Grid
    src/i18n/fr.json  TOUS les textes de l'interface (NF-13)
  docker-compose.yml  db + minio + redis + backend + worker (Celery) + frontend (nginx, proxy /api)
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
  droits avec `Depends(require(Perm.X))` ; `require(Perm.A, Perm.B)` accepte l'un ou l'autre. Côté interface, les droits ne servent qu'à
  l'affichage. Les restrictions par mission sont dans `api/mission_access.py` (lot 3).
- **Séparation des tâches** : `roles.can_review(preparateur, reviseur)`, à appliquer aux
  signatures du lot 4.
- **E-mails** : validation volontairement souple, pour accepter les domaines internes (`.local`).
- **Interface** : aucun texte en dur ; passer par `t("...")`. Nombres et dates au format
  français (`lib/format.ts`). Toujours associer un `label` à chaque champ (RGAA).
- **Commits** : un commit par exigence, préfixé par son code (ex. `AUD-01: ...`).

### Lot 2 — univers d'audit et plan annuel

- **Droit `plan:read`** (ajouté au lot 2) : lecture de l'univers, de la carte et du plan par
  l'Administrateur, le Directeur et le Chef de mission. Écriture : `plan:manage`
  (Directeur). Validation : `plan:validate` (Directeur). Critères de risque :
  `settings:manage` (Administrateur) ou `plan:manage`.
- **Score de risque** (`risk_scoring.py`) :
  - notes de 1 à 5 ;
  - score sur 100 = Σ(poids × note) / Σ(poids × 5) ;
  - impact et probabilité = moyennes pondérées des critères de leur axe ;
  - critère « ancienneté » = 1 + années pleines depuis le dernier audit, plafonné à 5 ;
    une entité jamais auditée vaut 5.
  - Chaque évaluation fige ses critères dans `criteres` (JSON) : modifier un critère ne
    réécrit pas l'historique. L'entité recopie les résultats de son évaluation la plus récente.
  - La carte place une entité dans la case la plus proche (2,5 → 3).
- **Critères par défaut** : installés par la migration 0003. Les tests utilisent la fixture
  `criteria`, car le nettoyage vide toutes les tables entre deux tests.
- **Plan** :
  - un enregistrement `AuditPlan` par version, (année, version) unique ;
  - seul un brouillon est modifiable ;
  - la validation fige le plan et fait passer la version validée précédente à « remplacé » ;
  - une nouvelle version ne part que de la dernière version et en copie les missions.
  - Les missions (`PlanItem`) ont une période comprise dans l'année du plan, et une entité n'y
    figure qu'une fois. Le lot 3 créera les missions (Engagement) à partir de ces lignes.

### Lot 3 — missions et programme de travail

- **Accès par mission** (`api/mission_access.py`) :
  - `visible_engagements(user)` : tout pour `missions:read_all` (Directeur, Administrateur),
    sinon les missions dont l'utilisateur est membre ;
  - `can_manage` : Directeur partout, Chef de mission sur les missions qu'il pilote ;
  - `ensure_open` refuse toute écriture sur une mission clôturée.
  Toute nouvelle route rattachée à une mission passe par `get_engagement` (404 si invisible).
- **Rôles dans la mission** : chef (Chef de mission ou Directeur), superviseur, auditeur
  (Auditeur ou Chef de mission), data analyst. Un seul chef par mission.
- **Statuts** (`engagement_status.py`) : un cran à la fois, retour d'un cran possible sauf après
  clôture. Les contrôles de passage s'ajoutent dans `GUARDS[statut_cible]`, les actions à
  l'entrée d'un statut dans `ON_ENTER[statut]`. L'historique est lu dans `AuditLog`.
- **Temps** : saisie en heures (pas de 0,25 h), convertie en jours avec
  `AUDITLAB_HEURES_PAR_JOUR` (8 par défaut). Jamais de date future ; chacun corrige ses saisies.
- **Bibliothèque et matrice** :
  - `Risk`, `Control` et `Procedure` servent à la fois à la bibliothèque (`bibliotheque=True`,
    `engagement_id` vide) et aux missions (copies avec `source_id`) ;
  - un contrôle de bibliothèque n'est copié qu'une fois par mission ;
  - les procédures de mission sont numérotées P-01, P-02… sans réutiliser un numéro.
- **Modèles** (`EngagementTemplate`) : contenu figé en JSON. `templates.instantiate` recrée la
  matrice dans une nouvelle mission.
- **Données de départ** : la migration 0008 installe la bibliothèque (11 risques, 15 contrôles)
  et la migration 0009 ses 16 procédures types. Les tests partent d'une base vide (troncature
  avant chaque test) ; `test_migrations.py` vérifie les données de départ.
- **Tests** : `tests/helpers.py` fournit `entity`, `validated_plan` et `mission`.

### Lot 4 — papiers de travail et revue

- **Rédaction** : membres de la mission avec le rôle auditeur ou chef. Les autres membres, le
  Directeur et l'Administrateur lisent.
- **Contenu riche** :
  - format ProseMirror/TipTap en JSON, validé par liste blanche (`richtext.validate_doc`) ;
  - images uniquement sous la forme `attachment:<id>` d'une pièce jointe du même papier ;
  - liens limités au web, aux e-mails et à `/missions/…` ;
  - nœud `tickmark` pour les marques de révision.
  Côté interface, `resolveImages` et `unresolveImages` passent de la référence au lien signé.
- **TipTap** : tous les paquets `@tiptap/*` sont à la même version exacte. Mélanger les
  versions casse le build Vite.
- **Fichiers** : `storage.get_storage()` renvoie le disque local (développement, tests) ou un
  stockage S3 (MinIO sous Docker, chiffrement SSE). Les clés ne sont jamais réutilisées.
  `AUDITLAB_SECRET_KEY` signe les liens de téléchargement (valides 1 h).
- **Versions** : `workpaper_versions` est en ajout seul (déclencheurs SQL). La version et son
  empreinte servent aux signatures.
- **Signatures** : Préparé → Revu → Approuvé, avec séparation des tâches. Des contrôles
  supplémentaires s'ajoutent dans `SIGNOFF_GUARDS` ; l'approbation exige que les notes de revue
  du papier soient clôturées. Toute modification du contenu ou des pièces jointes appelle
  `signoffs.invalidate`, qui annule les signatures et notifie le réviseur.
- **Notifications** : `notify.notify` crée la notification dans l'application et un e-mail en
  file. `python -m app.cli send-emails` les envoie si SMTP est configuré (`AUDITLAB_SMTP_*`).
- **Clôture** :
  - le passage en Rapport exige toutes les notes de revue clôturées ;
  - la clôture exige en plus tous les papiers approuvés ;
  - à la clôture, la date du dernier audit de l'entité est mise à jour ;
  - l'écouteur `_refuse_closed_engagements` refuse toute écriture sur un objet portant
    l'`engagement_id` d'une mission clôturée. Toute nouvelle table rattachée à une mission doit
    donc porter `engagement_id`.

### Lot 5 — import de données

- **Stockage** : les lignes ne sont jamais en PostgreSQL. `Dataset` porte les métadonnées ; la
  table est un fichier Parquet neuf (`store.write_table` ou `write_duckdb_query`) sous
  `AUDITLAB_DATA_DIR/<mission>/<uuid>.parquet`, en droits 0444. Aucune route ne réécrit une
  table : toute transformation crée une nouvelle table (lignée au lot 7).
- **Import** : dépôt (`Upload`, fichier conservé dans le stockage comme preuve), détection
  (`detect.suggest`), aperçu, puis tâche Celery `auditlab.import_dataset`
  (`AUDITLAB_TASKS_EAGER=true` l'exécute dans le processus, comme dans les tests). Les fichiers
  texte sont lus en chaînes puis convertis colonne par colonne aux formats français ; une valeur
  non convertible devient vide et est comptée dans `options.avertissements`.
- **Sources SQL** : déclarées par l'administrateur (`DataSource`, adresse masquée dans le
  journal) ; requête en lecture seule contrôlée par `sql_source.check_query`.
- **Empreintes** : `source_sha256` (fichier d'origine), `parquet_sha256` (table produite),
  `totaux_controle` (somme exacte et nombre de valeurs par colonne numérique, bornes des dates).
  `GET /datasets/{id}/integrity` les recalcule.
- **Expressions** (`analytics/expr.py`) : grammaire fermée, compilée en SQL DuckDB. Colonnes
  vérifiées dans le schéma puis citées (`quote_ident`), textes et dates en paramètres `?`,
  nombres réécrits depuis leur valeur. Ajouter une fonction : `_fn("nom_fr nom_en", min, max,
  "gabarit {0} {1:int}")`. À réutiliser pour l'extraction (DAT-09).
- **Vues** (kind `vue`) : pas de fichier ; `definition.champs` = liste `{nom, expression}`.
  `relation.relation(db, ds)` renvoie le SQL et les paramètres de n'importe quelle table (vues
  imbriquées comprises) ; `relation.evaluate(rel, "SELECT … FROM t")` l'interroge. Toute
  lecture (grille, statistiques, analyses) passe par là.
- **Grille** : `POST /datasets/{id}/rows` traduit le modèle de filtres AG Grid en SQL paramétré
  (`grid.where_clause`) ; `POST /datasets/{id}/stats` réutilise la même sélection.
- **Tests** : `tests/data_helpers.make_dataset(db, mission_id, polars_df)` crée une table de
  référence sans passer par l'import ; `tests/data_files.py` contient les fichiers d'exemple.

### Lot 6 — analyses

- **Ajouter une analyse** : un module dans `app/analytics/operations/` qui appelle
  `register(Operation(code, exigence, entrees, params, run))`, importé dans `__init__.py`.
  `run(relations, parametres) -> OpResult(df, resultat)`. Les paramètres sont déclarés par
  `Param(nom, type, …)` et contrôlés par `base.validate` avant le lancement (422 immédiat) :
  colonnes existantes et de bon type, nombres bornés, listes croissantes.
- **Interface générique** : `AnalysisPanel.tsx` construit le formulaire depuis `GET /analyses`.
  Les libellés sont dans `fr.json` (`analyses.<code>.titre`, `.description`, `.params.<nom>`,
  `analyses.choix.<valeur>`, `resultats.<clé>`). Une nouvelle analyse demande donc ses textes.
- **Exécution** : `POST /datasets/{id}/analyses` crée une table `kind="analyse"` en cours, puis
  la tâche `auditlab.run_analysis` écrit le Parquet et `resultat`. `definition` garde
  `operation`, `parametres` et `entrees` (ids) : c'est la base de la lignée (DAT-24).
- **Reproductibilité (NF-04)** : chaque opération trie sa sortie (`ORDER BY ALL` ou clés
  explicites). Le test `test_dat09_reproductible` vérifie l'égalité des empreintes.
- **SQL** : `relation.evaluate_many({"a": rel1, "b": rel2}, sql, params)` pour deux tables. Une
  requête qui commence par `WITH` prolonge les tables nommées. Dans `operations/`, la règle S608
  est désactivée : identifiants toujours cités par `quote_ident`, valeurs toujours en `?`.
- **Tests** : `tests/analysis_helpers.analyse(...)` lance une analyse ; `result_df(db, res)` lit
  sa table. Une analyse refusée à l'exécution renvoie 202 avec `statut="erreur"`.
