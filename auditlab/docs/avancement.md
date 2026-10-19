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
| 8a | Référentiels et balance : REV-01 à REV-14 | **Livré** |
| 8b | Révision et états : REV-15 à REV-28, CIP-01 à CIP-09, IFR-01 à IFR-04 | **Livré** |
| 8c | Portefeuille et contrôles : RCO-01 à RCO-10 | **Livré** |
| 8d | Inventaire, fiscalité et livrables : RCO-11 à RCO-27 | **Livré** |
| 9 | Scripts et automatisation : DAT-26 à DAT-29 | **Livré** |
| 10 | Reporting et finitions : REP-01 à REP-08, NF-06, NF-08 à NF-12, NF-14, recette | **Livré** |

## Lot 10 — détail

**Livré** (un commit par exigence ; Module 4, exigences non fonctionnelles, recette)
- **REP-01** : modèles de rapport de mission (IIA 2400) : logo, page de garde, sections et
  ordre, mention de confidentialité ; modèle par défaut ; page « Modèles de rapport ».
- **REP-02** : rapport de mission en PDF et Word : page de garde, synthèse et répartition des
  constats par criticité, conclusion, contexte, constats validés (critère, faits, cause,
  conséquence, recommandation, réponse, plans d'action), annexes ; pied de page numéroté.
- **REP-03** : circuit Projet → Revu → Validé → Diffusé, séparation des tâches, renvoi
  motivé ; version diffusée générée une fois, stockée avec son empreinte, figée.
- **REP-04 à REP-06** : tableaux de bord Direction (plan annuel, missions par statut, jours
  contre budget), Recommandations (criticité, statut, taux de mise en œuvre, retards par
  direction) et Mission (papiers par état, notes ouvertes, temps contre budget).
- **REP-07** : rapport trimestriel au comité d'audit (PDF et Word).
- **REP-08** : export Excel de chaque tableau de bord, filtres période, entité (avec ses
  sous-entités) et criticité.
- **NF-06** : TLS 1.2/1.3, HSTS, redirection HTTP (surcouche `docker-compose.tls.yml`).
- **NF-08** : registre des traitements (`docs/rgpd.md`), purge quotidienne des données
  analysées après la durée de conservation (60 mois après la clôture), simulation.
- **NF-09** : 50 utilisateurs simultanés, 95e centile de 0,13 à 0,66 s (`perf/nf09_charge.py`).
- **NF-10** : import d'un million de lignes en 0,56 s, doublons en 0,17 s (`perf/nf10_import.py`).
- **NF-11** : grille sur 10 millions de lignes, tout bloc en moins de 0,2 s, tri compris
  (`perf/nf11_grille.py`).
- **NF-12** : sauvegarde quotidienne chiffrée (age) de la base et du stockage, restauration
  testée automatiquement et par exercice (`docs/exploitation.md`).
- **NF-14** : audit axe-core (WCAG 2.1 AA) de 28 écrans, contrastes corrigés
  (`docs/accessibilite.md`).
- **DAT-27 (correctif)** : sorties du bac à sable confinées au répertoire `out/` (faille
  d'import du Parquet d'une autre mission corrigée) ; tests de sécurité (injection SQL,
  évasion du bac à sable) dans `tests/test_securite.py`.
- **Recette** : scénario de bout en bout de la section 13 automatisé (`tests/test_recette.py`).
- **Documentation** : `docs/installation.md`, `exploitation.md`, `performance.md`,
  `accessibilite.md`, `rgpd.md`.
- Changements signalés d'exigences livrées : une mission d'audit ne se clôture qu'après
  diffusion de son rapport (AUD-07) ; le verrou des missions clôturées admet la seule purge
  des données (AUD-22) ; l'inactivité de session est mesurée à une minute près (NF-07) ;
  copie triée en cache pour la grille (DAT-07) ; moteur de documents étendu (logo, page de
  garde, pied de page, REV-27).
- Tests : 518 tests backend (couverture 96 %), dont la recette de bout en bout et les tests de sécurité ; 21 tests Vitest ; mesures de performance dans `backend/perf/`.

## Lot 9 — détail

**Livré** (un commit par exigence ; Module 2, scripts et audit en continu)
- **DAT-26** : scripts Python d'une mission, éditeur Monaco (servi par l'application), API
  `audit` (table, tables, files, import_csv, duplicates, benford, gaps, save, metric) ;
  entrées choisies explicitement ; exécutions conservées (empreinte du code, sortie,
  indicateurs, tables produites avec leur lignée).
- **DAT-27** : exécution isolée : conteneur Docker jetable sans réseau, 2 Go, 10 minutes,
  racine en lecture seule, utilisateur sans privilège ; en développement, processus local
  sans réseau (espace de noms vide) avec limites du noyau. Jamais d'exécution sans bac à sable.
- **DAT-28** : bibliothèque de 10 tests livrés sur 5 cycles (achats, ventes, paie,
  trésorerie, notes de frais), publiée et versionnée par les data analysts ; reprise dans une
  mission.
- **DAT-29** : planification quotidienne ou mensuelle, tâche horaire, alerte (notification et
  e-mail) quand l'indicateur franchit le seuil, n'est pas produit ou que l'exécution échoue.
- Changements signalés d'exigences livrées : une table produite par un script n'est pas
  rejouée par la lignée (DAT-24) ni convertible en macro (DAT-25) ; liste des fichiers
  déposés d'une mission (DAT-01).
- Tests : 488 tests backend, couverture 96 %. Parcours navigateur : onglet Scripts et
  bibliothèque, création, édition dans Monaco, exécution, planification.

## Lot 8d — détail

**Livré** (un commit par exigence ; Module 6, travaux d'inventaire, fiscalité et livrables)
- **RCO-11** : tableau des immobilisations (acquisitions, cessions, composants),
  amortissements linéaire et dégressif, écriture de dotation.
- **RCO-12** : stocks (inventaire physique importé, coût moyen pondéré ou PEPS, dépréciation
  à la valeur nette de réalisation, écriture de variation).
- **RCO-13** : charges à payer, produits à recevoir, charges et produits constatés d'avance ;
  contre-passation proposée à l'ouverture de N+1.
- **RCO-14** : provisions pour créances douteuses (balance âgée, grille du dossier), litiges
  et risques ; dotations et reprises.
- **RCO-15** : écarts de conversion au cours de clôture et provision pour perte de change.
- **RCO-16** : clôture d'un OPS (cotisations à recevoir, prestations à payer, provisions
  techniques par branche selon le paramètre CIP-09).
- **RCO-17** : export des écritures acceptées au format du logiciel du client (Sage, Odoo,
  générique).
- **RCO-18 / RCO-19** : rapprochement mensuel du chiffre d'affaires et de la TVA
  (collectée, déductible, crédit) avec les déclarations ; TVA théorique.
- **RCO-20** : tableau de passage au résultat fiscal, impôt sur les sociétés et impôt minimum.
- **RCO-21** : rapprochement des salaires avec les déclarations sociales et fiscales.
- **RCO-22** : paramètres fiscaux par pays et par exercice (aucune valeur livrée).
- **RCO-23** : revue du dossier (visa du superviseur puis de l'expert-comptable) ; le dépôt
  exige le visa de l'expert.
- **RCO-24** : états financiers et liasse du Module 5 sur les soldes révisés ; visa de
  l'expert subordonné à des états produits et cohérents.
- **RCO-25** : attestation de présentation (ISRS 4410), lettre de mission, lettre de
  recommandations, note de synthèse ; modèles modifiables, PDF et Word ; attestation signée
  par l'expert, empreinte du contenu signé.
- **RCO-26** : comparatif N/N-1 des états révisés et indicateurs de gestion (chiffre
  d'affaires, marges, EBE, fonds de roulement, BFR, trésorerie nette, endettement), export.
- **RCO-27** : transmission du dossier à une mission d'audit désignée par sa référence ;
  reprise de la balance révisée, de la balance N-1, des affectations et des justificatifs dans
  un dossier d'audit distinct.
- Changements signalés d'exigences livrées : séquences groupées et valeurs distinctes
  (DAT-11) ; dépôt soumis au visa de l'expert (RCO-02) ; visa de l'expert non retirable tant
  que l'attestation est signée (RCO-23) ; modèles de rapports élargis aux documents de
  clôture (REV-27).
- Tests : 475 tests backend, couverture 97 %.

## Lot 8c — détail

**Livré** (un commit par exigence ; Module 6, révision comptable)
- **RCO-01** : portefeuille de dossiers clients (forme juridique, régime fiscal,
  référentiel, clôture, taille, expert, collaborateur, superviseur, contact) ; clôture d'un
  exercice = mission « revision_comptable » + dossier de révision du Module 5 ; rôles
  Expert-comptable et Collaborateur comptable.
- **RCO-02** : étapes de la clôture (pièces → terminé) et tableau de bord du portefeuille
  (avancement, échéances à 30 jours, dossiers en retard).
- **RCO-03** : calendrier fiscal et social par pays (aucune échéance livrée), échéances par
  client, alertes à J-15 et J-5.
- **RCO-04** : pièces demandées par le portail (liste type selon la taille), dépôt par le
  client, suivi, relances manuelles et automatiques.
- **RCO-05 / RCO-06** : dossier permanent repris d'un exercice à l'autre ; documents
  expirés signalés à l'ouverture de l'exercice.
- **RCO-07** : check-lists de révision par cycle (49 points) selon taille et référentiel.
- **RCO-08** : soldes anormaux, tiers non lettrés, écritures sans pièce, ruptures de
  numérotation par journal et doublons (Module 2).
- **RCO-09** : justification de chaque compte de bilan, signalé jusqu'à la revue.
- **RCO-10** : rapprochement des balances auxiliaires avec les comptes collectifs et des
  banques avec les relevés (REV-20).
- Changements signalés d'exigences livrées : type d'entité « client » hors univers
  (AUD-01) ; clôtures hors de la liste des missions (AUD-06) ; deux rôles ajoutés ;
  séquence groupée et valeurs distinctes (DAT-11) ; écart auxiliaire non bloquant pour une
  clôture (REV-06) ; vues d'audit légal masquées pour une clôture.
- Tests : 456 tests backend, couverture 98 %. Parcours navigateur : portefeuille et tableau
  de bord, dossier client (check-list, pièces, échéances, dossier permanent, étapes),
  contrôles comptables, justification, rapprochements, portail du client.

## Lot 8b — détail

**Livré** (un commit par exigence ; REV-23/24 et IFR-01/03 ensemble : mêmes états)
- **REV-15** : feuilles maîtresses par cycle (N-1, N, ajustements, révisé, papiers liés).
- **REV-16** : programmes de travail types par cycle (50 procédures), propres au référentiel.
- **REV-17** : tests des écritures de journal (ISA 240), analyse du Module 2 lancée sur le
  grand livre N.
- **REV-18** : lettrage, justification des tiers, balance âgée et dépréciation proposée.
- **REV-19** : circularisation (banques, clients, fournisseurs, avocats) en PDF et Word,
  suivi des réponses, rapprochement automatique des écarts.
- **REV-20** : rapprochements bancaires importés et contrôlés.
- **REV-21 / REV-22** : écritures d'ajustement, décision de l'entité, soldes révisés ;
  tableau des anomalies non corrigées (ISA 450).
- **REV-23 / REV-24** : états financiers révisés (dont tableau des flux), contrôles de
  cohérence, exports Excel et PDF.
- **REV-25** : aide à la liasse (DSF) par pays, modèle générique OHADA, export Excel.
- **REV-26** : note de synthèse générée, points en suspens renvoyant à leur écran.
- **REV-27** : modèles de rapports (opinion ISA 700/705/706, rapport spécial, lettre
  d'affirmation) ; rôles Associé signataire et Inspecteur CIPRES.
- **REV-28** : signature, émission, archivage et verrouillage du dossier.
- **IFR-01 / IFR-03** : retraitements IFRS, table de passage, états IFRS et réconciliations.
- **IFR-02** : six assistants de calcul (IFRS 16, IAS 19, IFRS 9, IAS 16, IAS 12, IFRS 15).
- **IFR-04** : check-list des informations à fournir en annexe (48 points, 13 normes).
- **CIP-01** : suivi par branche (comptes, contrôles, états et ratios par branche).
- **CIP-02 à CIP-05** : contrôles sur les fichiers des organismes (cotisations, recouvrement
  et créances, prestations et pensions, allocations familiales), opérations du Module 2
  lancées depuis le dossier avec les paramètres du référentiel.
- **CIP-06 / CIP-07** : frais de gestion, réserves techniques par branche, placements et
  rendement, sur les soldes révisés.
- **CIP-08** : mission d'inspection CIPRES (rapports provisoire et définitif figés, réponses
  de l'organisme, suivi des recommandations d'une inspection à l'autre).
- **CIP-09** : paramètres réglementaires par pays, exercice et branche ; aucune valeur livrée.
- Changements signalés d'exigences livrées : programme généré depuis la matrice des risques
  enrichi des procédures types (REV-14) ; deux rôles ajoutés à la matrice des droits ;
  colonne `Control.branche` (Module 1, migration 0053) ; colonne `Engagement.mode`
  (AUD-06, migration 0054), « audit » par défaut.
- Correctifs : nombre de postes du référentiel livré dans le test REV-01 ; style d'un bouton
  (CIP-02) et libellé du choix de branche (CIP-01) relevés au parcours navigateur.
- Tests : 444 tests backend, couverture 98 %. Parcours navigateur rejoués : ajustements,
  feuilles maîtresses, états, tiers, circularisation, synthèse, opinion et signature, IFRS ;
  pour un organisme de prévoyance sociale : branches, indicateurs, contrôle CIP-05 lancé
  depuis l'écran, inspection jusqu'au rapport provisoire.

## Lot 8a — détail

**Livré** (un commit par exigence ; REV-02 à REV-04 ensemble, REV-08 à REV-10 ensemble :
même modèle et même écran)
- **REV-01** : référentiels versionnés (SYSCOHADA révisé 2017 livré : plan, postes du Système
  normal, ratios, bases de seuil, règles de contrôle ; modèle de structure CIPRES), import et
  export Excel, publication par l'administrateur.
- **REV-02 / REV-03 / REV-04** : dossier de révision par entité et par exercice rattaché à une
  mission, référentiel principal, restitution IFRS et cadre normatif ; dossier N-1 relié,
  balance N et affectations manuelles reprises.
- **REV-05** : import des balances N et N-1, du grand livre (versé comme table du Module 2) et
  des balances auxiliaires ; Sage, Odoo, Perfecto, SAARI, export générique, CSV ou Excel.
- **REV-06** : contrôles bloquants (équilibre, cohérence des lignes, comptes hors plan,
  à-nouveaux, grand livre / balance, auxiliaire / collectif), quel que soit l'ordre d'import.
- **REV-07** : devises et cours par date, conversion à l'import, FCFA sans décimales.
- **REV-08 / REV-09 / REV-10** : affectation automatique par racine la plus longue, comptes à
  double sens selon leur solde, affectation manuelle, bandeau permanent des comptes non
  affectés ; aperçu des états N / N-1 refusé tant que la liste n'est pas vide.
- **REV-11** : seuil de signification, de planification et d'insignifiance.
- **REV-12** : revue analytique N/N-1 par poste et par compte, justification obligatoire.
- **REV-13** : ratios sur trois exercices.
- **REV-14** : matrice des risques par cycle et par assertion, qui alimente le programme de
  travail de la mission.
- Correctifs signalés : valeurs JSON des référentiels livrés (migration 0033) ; unicité du
  dossier par entité et par exercice rétablie (index supprimé par la migration 0035).
- Changements signalés d'exigences livrées : devise d'un nouveau dossier obligatoirement
  définie (REV-04) ; totaux en FCFA sans décimales (REV-05).
- Tests : 405 tests backend. Parcours import Sage et Odoo → contrôles → affectation →
  aperçu des états → seuil → revue analytique → ratios → matrice et programme rejoué dans un
  navigateur.

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
