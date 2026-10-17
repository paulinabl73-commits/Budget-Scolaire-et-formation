# Avancement

| Lot | Contenu | État |
|-----|---------|------|
| 1 | Socle : dépôt, PostgreSQL, Alembic, authentification, rôles, AuditLog chaîné (NF-01, NF-02), CI | **Livré** |
| 2 | Univers et plan : AUD-01 à AUD-05 | **Livré** |
| 3 | Missions et programme : AUD-06 à AUD-12 | **Livré** |
| 4 | Papiers de travail et revue : AUD-13 à AUD-22 | **Livré** |
| 5 | Import de données : DAT-01 à DAT-08 | **Livré** |
| 6 | Analyses : DAT-09 à DAT-19 | **Livré** |
| 7 | Échantillonnage et lignée : DAT-20 à DAT-25 | **Livré** |
| 8 | Liaison audit et analyse, constats : DAT-30 à DAT-32, CON-01 à CON-09 | **Livré** |
| 8a | Référentiels et balance : REV-01 à REV-14 | À faire |
| 8b | Révision et états : REV-15 à REV-28, CIP-01 à CIP-09, IFR-01 à IFR-04 | À faire |
| 8c | Portefeuille et contrôles : RCO-01 à RCO-10 | À faire |
| 8d | Inventaire, fiscalité et livrables : RCO-11 à RCO-27 | À faire |
| 9 | Scripts et automatisation : DAT-26 à DAT-29 | À faire |
| 10 | Reporting et finitions : REP-01 à REP-08, NF-09 à NF-11 | À faire |

## Lot 8 — détail

**Livré** (un commit par exigence ; CON-01 et CON-02 ensemble, même modèle et même écran)
- **DAT-30** : table de résultat, historique et graphique joints au papier de travail.
- **DAT-31** : lignes d'anomalie cochées dans la grille → constat, avec les lignes en preuve
  (chaque ligne vérifiée dans la table).
- **DAT-32** : export Excel et CSV de la table ou de la sélection, journalisé.
- **CON-01 / CON-02** : fiche constat en cinq volets, criticité sur quatre niveaux,
  rattachement au risque, au contrôle et aux papiers sources.
- **CON-03** : preuves (papiers, pièces jointes, résultats d'analyse) avec empreinte figée.
- **CON-04** : phase contradictoire (envoi, réponse motivée et plan proposé, validation).
- **CON-05** : plans d'action et leurs statuts.
- **CON-06** : relances à J-15, à l'échéance, puis toutes les deux semaines.
- **CON-07** : justificatifs déposés par l'audité, vérification ou rejet motivé.
- **CON-08** : reports d'échéance validés par le chef de mission, avec historique.
- **CON-09** : portail audité limité à ses constats et plans d'action.
- Changements signalés d'exigences livrées : passage en « Rapport » conditionné à la
  validation de tous les constats (AUD-07, AUD-21) ; liste des missions refusée (403) aux
  rôles sans droit de lecture des missions (AUD-06).
- Tests : 361 tests backend. Parcours lignes → constat → envoi → réponse de l'audité depuis
  son portail → validation par le chef rejoué dans un navigateur.

## Lot 7 — détail

**Livré** (un commit par exigence)
- **DAT-20** : échantillons aléatoire simple, systématique, stratifié (par champ ou par
  tranches de montant, allocation proportionnelle) et en unités monétaires.
- **DAT-21** : taille d'échantillon pour les tests de contrôles (binomiale) et pour le MUS
  (facteurs de Poisson, facteurs d'expansion AICPA), reprise dans le formulaire.
- **DAT-22** : graine tirée et enregistrée (paramètres, synthèse, journal) ; même graine, même
  empreinte.
- **DAT-23** : évaluation MUS (erreur projetée, précision de base, provision d'élargissement,
  limite supérieure, conclusion au regard de l'erreur tolérable).
- **DAT-24** : entité AnalysisOperation, graphe de lignée, rejeu depuis la source avec
  comparaison des empreintes (NF-04).
- **DAT-25** : macros tirées de l'historique, rejouées sur des tables de même structure.
- CI : MinIO remplacé par SeaweedFS (l'image MinIO n'est plus publiée).
- Tests : 334 tests backend (couverture de 98 %) ; parcours échantillon MUS, évaluation, rejeu et macro
  rejoué dans un navigateur.

## Lot 6 — détail

**Livré** (un commit par exigence)
- Cadre commun : catalogue, contrôle des paramètres, tâche de fond, table de résultat Parquet
  avec empreinte et totaux, synthèse ; même entrée → même empreinte (NF-04).
- **DAT-09** extraction (constructeur visuel ou expression), **DAT-10** doublons exacts et
  approchés (1 million de lignes en moins de 10 s, NF-10), **DAT-11** ruptures de séquence,
  **DAT-12** stratification, **DAT-13** synthèse, **DAT-14** ancienneté, **DAT-15** Benford
  (khi-deux, MAD, z, lignes suspectes, graphique), **DAT-16** jointure, **DAT-17**
  rapprochement, **DAT-18** valeurs aberrantes (z, IQR), **DAT-19** recherche floue.
- Tests : 313 tests backend (couverture de 98 %) sur des jeux de référence calculés à la main
  ou à valeurs connues (tables du khi-deux, loi de Benford). Extraction, Benford et synthèse
  rejouées dans un navigateur.

## Lot 5 — détail

**Livré** (un commit par exigence)
- **DAT-01** : import CSV, TXT à largeur fixe, Excel (.xlsx, .xls), JSON (aplati), Parquet et
  requêtes sur des bases SQL déclarées par l'administrateur ; import en tâche de fond (Celery).
- **DAT-02** : assistant d'import : détection de l'encodage (UTF-8, Windows-1252), du
  séparateur et des types, aperçu de 100 lignes, formats français (virgule décimale, espace
  des milliers, jj/mm/aaaa, montants négatifs entre parenthèses).
- **DAT-03** : relevés PDF (pdfplumber), par tableaux détectés ou par colonnes définies par
  l'utilisateur, avec choix des pages.
- **DAT-04** : empreinte SHA-256 du fichier source et de la table, nombre de lignes, totaux de
  contrôle ; vérification d'intégrité rejouable.
- **DAT-05** : tables en Parquet, écrites une fois puis en lecture seule (0444).
- **DAT-06** : champs calculés par expression (grammaire fermée, 37 fonctions françaises et
  anglaises), créés comme vue sans copie ni modification de la source.
- **DAT-07** : grille virtualisée AG Grid (blocs de 200 lignes lus par DuckDB) : tri, filtres,
  recherche, masquage de colonnes. Test de volume : page au milieu d'un tri sur 1 million de
  lignes en moins de 3 s.
- **DAT-08** : statistiques de champ sur la table ou la sélection filtrée.
- Tests : 283 tests backend (couverture de 98 %) et 21 tests frontend. Le parcours import,
  grille, recherche, tri, statistiques et champ calculé a été rejoué dans un navigateur.

## Lot 4 — détail

**Livré** (un commit par exigence)
- **AUD-13** : papiers de travail avec référence unique (B-2.3), objectif, travaux,
  conclusion et évaluation du contrôle.
- **AUD-14** : éditeur riche (titres, listes, tableaux, images jointes, liens vers les autres
  papiers), avec validation serveur du contenu.
- **AUD-15** : pièces jointes jusqu'à 100 Mo (stockage local ou S3, empreinte SHA-256,
  versions par nom de fichier, liens signés). Le lien vers les résultats d'analyse viendra au
  lot 8 (DAT-30).
- **AUD-16** : marques de révision paramétrables, insérées dans le texte et les tableaux, avec
  une légende.
- **AUD-17** : une version inaltérable par enregistrement, comparaison mot à mot de deux
  versions.
- **AUD-18** : circuit Préparé, Revu, Approuvé, signatures horodatées et liées à l'empreinte,
  séparation des tâches.
- **AUD-19** : notes de revue ancrées sur un passage (Ouverte, Répondue, Clôturée), réponses de
  l'équipe.
- **AUD-20** : une modification après signature annule les signatures et notifie le réviseur
  (dans l'application et par e-mail).
- **AUD-21** : passage en Rapport refusé tant qu'une note de revue n'est pas clôturée.
- **AUD-22** : clôture sur dossier complet, puis mission verrouillée jusque dans la couche
  d'accès aux données.
- Tests : 179 tests backend (couverture de 99 %) et 21 tests frontend. Le parcours rédaction,
  image, marque, signatures, note de revue et modification après signature a été rejoué dans un
  navigateur.

## Lot 3 — détail

**Livré** (un commit par exigence)
- **AUD-06** : missions créées depuis une ligne d'un plan validé (valeurs reprises) ou
  ponctuellement ; équipe avec rôles de mission ; référence M-AAAA-NNN ; chaque utilisateur ne
  voit que ses missions.
- **AUD-07** : cycle de vie en six statuts, contrôles de passage enregistrables, historique tiré
  du journal d'audit.
- **AUD-08** : saisie des temps (heures, activité), comparaison au budget, répartition par
  personne et par activité.
- **AUD-09** : modèles de mission tirés d'une mission ou de la bibliothèque, utilisés à la
  création.
- **AUD-10** : bibliothèque de risques et de contrôles, livrée avec une bibliothèque de départ
  (5 cycles).
- **AUD-11** : matrice risques/contrôles de la mission, import depuis la bibliothèque,
  procédures de test typées.
- **AUD-12** : affectation des procédures à un membre de l'équipe, avec échéance et
  avancement ; liste « Mes procédures » sur la page d'accueil.
- Tests : 147 tests backend (couverture de 99 %). Le scénario de recette, étape 2 (le chef
  ouvre la mission, construit la matrice et affecte les procédures), a été rejoué dans un
  navigateur.

## Lot 2 — détail

**Livré** (un commit par exigence)
- **AUD-01** : univers d'audit en arborescence (direction, filiale, processus, système) ; un
  déplacement qui créerait un cycle est refusé, la suppression est logique.
- **AUD-02** : critères paramétrables (axe, mode, poids, activation), avec cinq critères par
  défaut. Le score sur 100 est calculé automatiquement, la note d'ancienneté est déduite de la
  date du dernier audit, et l'historique des évaluations est conservé.
- **AUD-03** : carte des risques 5 × 5 cliquable, avec la liste des entités non évaluées.
- **AUD-04** : plan annuel construit en choisissant des entités (proposées par score
  décroissant), avec budget en jours-homme, période dans l'année et charge comparée à la
  capacité.
- **AUD-05** : validation par le Directeur (le plan est alors figé), nouvelles versions,
  consultation et comparaison des versions.
- Tests : 109 tests backend (couverture de 99 %, droits testés pour chaque rôle) et 18 tests
  frontend. Le scénario de recette, étape 1 (« le Directeur crée l'entité Achats, l'évalue et
  l'inscrit au plan 2027 »), a été rejoué dans un navigateur.

**Choix faits en l'absence de réponse aux questions ouvertes** (modifiables)
- Référentiel IIA ; échelle de notes de 1 à 5 ; niveaux de la carte selon impact × probabilité :
  faible < 4, modéré < 8, élevé < 15, critique ≥ 15.
- Le Chef de mission consulte l'univers et le plan. L'Auditeur et le Data analyst n'y ont pas
  accès : ils ne voient que leurs missions.

**Reste ouvert**
- La date du dernier audit est saisie à la main ; elle sera mise à jour automatiquement à la
  clôture des missions (lot 4, AUD-22).

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
- Redis, Celery et le stockage S3 sont dans le Compose depuis les lots 4 et 5.
- Les changements d'appartenance aux équipes (table d'association) ne sont pas encore
  journalisés champ à champ.
- Tests de bout en bout Playwright : à écrire au fil des lots, pour le scénario de la section 13.
- Questions ouvertes du cahier des charges (référentiel méthodologique, hébergement, SSO,
  volumétrie) : à trancher avant le lot 2.
