# Hypothèses retenues

Points laissés ouverts par le cahier des charges, tranchés selon les pratiques professionnelles
(IIA, ISA, OHADA / SYSCOHADA révisé, IFRS, CIPRES). Tous sont paramétrables sauf mention contraire.
Le document de synthèse partageable reprend ce fichier.

## Transverses

- Authentification : mot de passe de 12 caractères minimum (majuscule, minuscule, chiffre),
  Argon2id, TOTP obligatoire pour Administrateur et Directeur, sessions de 30 min d'inactivité,
  verrouillage après 5 échecs levé par un administrateur (NF-07).
- Journal d'audit : en ajout seul (déclencheur SQL), chaîné par SHA-256, valeurs avant/après,
  secrets masqués (NF-01, NF-02).
- Suppression logique uniquement (NF-03).
- Adresses e-mail : validation souple pour accepter les domaines internes (.local).
- Fichiers stockés hors base, dans un stockage compatible S3 (SeaweedFS ; MinIO n'étant plus distribué en image publique) chiffré au repos.
  Téléchargements journalisés ; liens signés valides une heure pour l'affichage des images.
- Rétention (NF-08) : données analysées (tables, fichiers importés, sorties de scripts)
  conservées 60 mois après la clôture de la mission, puis purgées ; restent le schéma, le
  nombre de lignes, l'empreinte et les totaux de contrôle (trace de la preuve). Le journal
  d'audit, les papiers de travail et les rapports ne sont jamais purgés (archives d'audit).
- Sauvegarde (NF-12) : quotidienne, chiffrée par clé publique (age), clé privée hors du
  serveur, rétention 30 jours, restauration testée chaque trimestre.
- Chiffrement en transit (NF-06) : TLS 1.2 minimum, profil « intermediate » de Mozilla, HSTS
  d'un an ; au repos : stockage S3 chiffré et disques chiffrés par l'hôte.
- Performance (NF-09 à NF-11) : mesurée sur un serveur de 4 processus d'API ; activité de
  session enregistrée une fois par minute (l'expiration est donc précise à une minute près).
- Accessibilité (NF-14) : RGAA 4 niveau AA visé, contrôlé par axe-core (WCAG 2.1 AA) et au
  clavier ; pas d'audit RGAA certifié par un tiers.

## Module 4 — reporting

### Lot 10
- Modèle de rapport livré selon la norme IIA 2400 (communication des résultats) : synthèse,
  conclusion, contexte, constats en cinq attributs (critère, faits, cause, conséquence,
  recommandation), réponse de l'audité et plans d'action, annexes. Seuls les constats validés
  figurent dans le rapport.
- Circuit : revue par le superviseur ou le Directeur (jamais par le seul chef de mission),
  validation par le Directeur, diffusion une fois la mission au statut « Rapport » ; la
  version diffusée est figée avec son empreinte. Une mission d'audit ne se clôture qu'après
  diffusion de son rapport.
- Taux de mise en œuvre des recommandations = plans vérifiés par l'audit / plans retenus
  (hors risque accepté), global et sur les plans échus ; un plan est en retard quand son
  échéance est passée et qu'il n'est ni réalisé ni clos ; il est rattaché à la direction de
  l'entité auditée (premier ancêtre de type « direction »).
- Rapport au comité d'audit : trimestre civil ; avancement du plan à la fin du trimestre.
- Tableaux de bord Direction et comité réservés au Directeur et à l'Administrateur ; tableau
  de bord Mission ouvert à l'équipe de la mission.

## Module 6 — révision comptable

### Lot 8d
- Écritures d'inventaire : chaque assistant propose une écriture « inventaire » marquée de son
  origine, remplacée tant qu'elle n'est pas décidée ; seules les écritures acceptées entrent
  dans les soldes révisés et l'export vers le logiciel du client (l'outil ne tient pas la
  comptabilité).
- Amortissements : linéaire au prorata en jours (année de 360 jours), du jour de mise en
  service au jour de cession ; dégressif à partir du mois de mise en service, avec passage au
  linéaire ; le coefficient dégressif, propre à chaque pays, est saisi. Un composant est une
  immobilisation rattachée à son ensemble.
- Stocks : inventaire intermittent (le compte de stock porte le stock initial jusqu'à
  l'écriture de variation) ; coût moyen pondéré de la période ou PEPS ; dépréciation à la
  valeur nette de réalisation.
- Constatés d'avance : au prorata des jours postérieurs à la clôture ; la reprise est la
  contre-passation, proposée à l'ouverture de N+1, de l'écriture acceptée en N.
- Créances douteuses : calcul de la balance âgée du Module 5 (REV-18) et grille du dossier ;
  litiges et risques saisis ; comptes proposés modifiables.
- Devises : écart = montant en devise × cours de clôture − valeur comptable ; perte latente
  provisionnée sans compensation avec les gains (prudence SYSCOHADA).
- OPS : provision technique d'une branche = minimum réglementaire en mois de prestations
  (CIP-09) × prestations de l'exercice / 12 ; comptes saisis, le plan CIPRES étant propre à
  chaque organisme.
- Fiscalité : aucun taux, barème ni règle livrés ; chaque paramètre est saisi par pays et
  vaut à partir de son exercice jusqu'à son remplacement. Montants comptables tirés du grand
  livre ; déclarations importées, une ligne par mois ; écart signalé au-delà de la tolérance
  paramétrée. Impôt dû = le plus élevé de l'IS et de l'impôt minimum (borné par le plancher et
  le plafond).
- Revue : le superviseur vise sur les papiers revus, l'expert sur les papiers approuvés,
  sans note ouverte, compte signalé, écriture en attente ni anomalie de check-list, et sur des
  états produits et cohérents ; le dépôt exige le visa de l'expert.
- Documents : attestation de présentation selon ISRS 4410 (mission de compilation, sans
  assurance) ; modèles modifiables par l'administrateur ; documents marqués « PROJET » tant
  que l'attestation n'est pas signée ; une modification du dossier après signature est
  signalée par l'empreinte et impose une nouvelle signature.
- Indicateurs : formules par référentiel en données (SYSCOHADA livré) ; écart relatif non
  significatif quand N-1 est nul ; écart en points pour les taux.
- Transmission au Module 5 : l'entité du portefeuille et celle de l'univers d'audit sont
  distinctes, et l'auditeur est indépendant du cabinet qui présente les comptes. L'expert
  transmet donc le dossier à une mission désignée par sa référence, sans voir les missions
  d'audit. L'auditeur reprend une copie dans son propre dossier : balance N révisée, balance
  N-1, balances auxiliaires, affectations et justificatifs. Ses travaux ne modifient pas les
  comptes présentés ; il obtient le grand livre directement de l'entité.

### Lot 8c
- Outil de révision branché sur le logiciel du client, sans saisie comptable complète
  (hypothèse du cahier des charges) : balances et grand livre importés comme au Module 5.
- Une clôture = une mission en mode « revision_comptable » portant un dossier de révision :
  import, affectation, états et contrôles d'accès du Module 5 réutilisés ; pas de seuil de
  signification ni d'opinion (vues correspondantes masquées). Mission du jour de clôture à
  six mois après (délai d'approbation des comptes OHADA).
- Clients enregistrés comme entités de type « client », hors de l'univers d'audit.
- Expert-comptable : droits du Directeur limités à son portefeuille, double authentification ;
  il est chef de mission de ses clôtures. Collaborateur : droits de l'Auditeur sur ses
  dossiers. Ces deux rôles n'interviennent que sur les dossiers clients.
- Étapes de clôture franchies une à une ; dépôt et fin réservés à l'expert ou au
  superviseur. Dossier en retard : échéance non faite dépassée, ou échéance liée à la clôture
  passée sans dépôt.
- Calendrier : aucune échéance livrée (valeurs propres à chaque pays) ; périodicités
  mensuelle, trimestrielle, annuelle ou relative à la clôture ; alertes à J-15 et J-5
  (paramétrables), une par échéance et par délai.
- Pièces : liste type de 15 pièces selon la taille (TPE, PME, grande entreprise) ; une pièce
  déposée par le client est reçue, le collaborateur peut la rouvrir avec un motif ; relance
  automatique tous les 7 jours après la date limite.
- Dossier permanent rattaché au client ; document expiré = date de validité antérieure à
  l'ouverture de la clôture ou à la fin de l'exercice clos.
- Check-lists : 49 points sur les onze cycles, dont 4 propres aux OPS ; anomalie =
  commentaire obligatoire.
- Soldes anormaux : sens normal par racine SYSCOHADA (données adaptables) ; aucune règle
  livrée pour le plan CIPRES. Numérotation des pièces contrôlée journal par journal ; doublon
  d'écriture = même date, journal, pièce, compte, libellé et montants.
- Justification : compte justifié = montant égal au solde révisé et pièce jointe ; revue par
  l'expert ou le superviseur, valable pour le solde revu.
- Écart entre balance auxiliaire et compte collectif : avertissement à rapprocher pour une
  clôture (il reste bloquant en audit légal, où les données doivent être cohérentes).

## Module 5 — révision des comptes

### Lot 8b
- Écritures d'ajustement (ISA 450) : la décision de l'entité est enregistrée par l'équipe et
  fige l'écriture ; seules les écritures acceptées entrent dans les soldes révisés ; les
  écritures proposées ou refusées forment les anomalies non corrigées, cumulées hors
  anomalies manifestement insignifiantes, appréciées par rapport aux seuils de planification
  et de signification.
- Tableau des flux SYSCOHADA établi par différence entre bilans ; contrôle de trésorerie
  limité à N ; export des états refusé tant qu'un contrôle de cohérence est en écart.
- Tests des écritures (ISA 240) : journaux OD considérés manuels par défaut, montant rond =
  multiple de 100 000, compte ou utilisateur inhabituel = au plus 3 ou 5 lignes ; tous
  modifiables au lancement.
- Dépréciation des créances : grille par défaut 0 / 25 / 50 / 100 % à 180 jours, un an et
  deux ans, modifiable par dossier ; base hors taxes si un taux de TVA est saisi.
- Circularisation : sélection au-delà du seuil de planification par défaut ; confirmation
  positive avec solde pour les clients, demande de relevé sans montant pour les fournisseurs
  (pratique recommandée pour détecter les passifs omis) ; réponses adressées au cabinet.
- Rapprochements bancaires : suspens anciens au-delà de 90 jours (paramétrable).
- Liasse (DSF) : modèle générique OHADA livré, modèles par pays importés en Excel ; les
  informations non comptables restent à saisir.
- Opinion : rédigée par le chef de mission, suggérée par le tableau des anomalies non
  corrigées ; signée par l'associé signataire membre de la mission ou par le chef de mission ;
  points bloquants avant signature ; rapport émis archivé avec son empreinte, dossier verrouillé.
- Rôles ajoutés : Associé signataire (droits du Directeur sur ses dossiers, double
  authentification) et Inspecteur CIPRES (droits du Chef de mission, missions d'inspection
  seulement).
- IFRS : un retraitement est une écriture d'ajustement d'un type dédié, jamais reprise dans
  les états SYSCOHADA ; la table de passage est un référentiel de restitution dont les postes
  sont des formules sur les postes SYSCOHADA retraités ; comparatifs N-1 non retraités ;
  subventions d'investissement en produits différés (IAS 20). Assistants : aucune donnée
  conventionnelle supposée (taux d'actualisation, mois d'indemnité, taux d'impôt saisis).
- Check-list IFRS : normes générales toujours affichées, autres normes affichées quand un
  retraitement validé les mobilise ; information manquante = commentaire obligatoire.
- CIPRES (CIP-09) : aucune valeur réglementaire livrée ; un paramètre vaut à partir de son
  exercice jusqu'à son remplacement ; le plus précis l'emporte (branche, pays, exercice) ;
  un contrôle dont un paramètre manque est refusé avec la liste à saisir. Taux en
  pourcentage ; plafond de cotisation nul = sans plafond ; mode de majoration de retard
  (par mois entamé, mois de 30 jours, ou forfaitaire) saisi comme paramètre.
- Branches (CIP-01) : rattachement par la racine la plus longue du plan portant une branche,
  rattachement manuel possible par dossier ; comptes non rattachés signalés et exclus des
  états par branche.
- Contrôles sur fichiers (CIP-02 à CIP-05) : opérations du Module 2 (traçables, rejouables) ;
  déclarations nominatives (une ligne par salarié et par période) ; fichier des pensionnés à
  raison d'une ligne par pension servie ; noms proches recherchés entre bénéficiaires nés le
  même jour (Jaro-Winkler ≥ 0,9 par défaut, choix de l'auditeur) ; droit aux allocations
  jusqu'à la veille de l'âge limite ; enfant rattaché à plusieurs allocataires signalé ;
  critère dont la colonne n'est pas fournie non appliqué et signalé.
- Indicateurs (CIP-06, CIP-07) : agrégats lus dans des postes du référentiel aux codes
  réservés (COT, CCO, FGE, RTE, PRE, PPL, PLA_<catégorie>), à prévoir dans les états du plan
  CIPRES importé ; cotisations encaissées = émises − variation des créances sur cotisants ;
  réserves exprimées en mois de prestations ; rendement sur l'encours moyen N et N-1.
- Inspection CIPRES (CIP-08) : rapport provisoire émis quand tous les constats ont été soumis
  à l'organisme ; rapport définitif quand ils sont validés et que le suivi de chaque
  recommandation antérieure est renseigné ; destinataire par défaut « Commission de
  surveillance de la CIPRES » (modifiable) ; rapports figés et horodatés avec empreinte.

### Lot 8a
- Référentiels : données versionnées, jamais écrites dans le programme. SYSCOHADA révisé 2017
  livré pour le Système normal ; le plan CIPRES n'étant pas public, un modèle de structure est
  livré, à compléter par import Excel (question ouverte du cahier des charges).
- Un seul dossier actif par entité et par exercice ; le dossier de l'exercice précédent sert
  de N-1 : sa balance N devient la balance N-1, ses affectations manuelles sont reprises.
- Imports : reconnaissance des colonnes par synonymes propres à chaque logiciel, table de
  correspondance manuelle en dernier recours ; montants au format français ou anglais,
  négatifs entre parenthèses ou suffixés. Un nouvel import remplace le précédent du même type,
  l'historique (y compris les imports rejetés) reste consultable avec le fichier source.
- Contrôles bloquants (un écart rejette l'import) : tolérance de 0,01 unité monétaire plus
  l'écart d'arrondi de conversion ; comptes hors plan = sans racine du référentiel d'au moins
  deux chiffres ; à-nouveaux comparés compte par compte pour les classes 2 à 5 et en total
  pour les capitaux propres (le résultat N-1 a pu être affecté entre comptes de la classe 1) ;
  grand livre comparé à la balance hors journaux d'à-nouveaux (AN, RAN, ANO, ANX) ; balance
  auxiliaire comparée aux comptes collectifs indiqués. Le contrôle croisé s'exécute à l'import
  de la seconde donnée, un avertissement le signale tant qu'elle manque.
- Une balance sans à-nouveaux (intégrés aux mouvements par certains logiciels) est rejetée
  avec l'indication d'exporter les soldes d'ouverture : l'auditeur doit pouvoir vérifier les
  soldes d'ouverture (ISA 510).
- Devises : montants tenus dans la devise du dossier et arrondis à son nombre de décimales
  (zéro pour XOF, XAF, GNF) ; conversion au cours de clôture par défaut (cours de la date
  choisie, à défaut le dernier connu avant, signalé) ; cours inverse utilisé s'il est seul
  connu ; aucun cours pré-enregistré, la parité fixe EUR/XOF comprise (donnée à saisir).
- Affectation : racine la plus longue ; règle de sens appréciée sur le solde de chaque exercice
  (un même compte peut changer de poste entre N et N-1) ; l'affectation manuelle prime et peut
  prévoir un poste distinct pour un solde créditeur ; classe 9 hors états (paramétrable).
- Seuil de signification (ISA 320) : fourchettes indicatives portées par le référentiel —
  total du bilan 1 à 2 %, chiffre d'affaires 0,5 à 2 %, résultat 5 à 10 %, capitaux propres
  1 à 5 %, cotisations 0,5 à 2 % ; seuil de planification 75 % et seuil d'insignifiance 5 % du
  seuil, modifiables ; base négative refusée ; justification obligatoire ; fixé par le chef de
  mission.
- Revue analytique (ISA 520) : variation signalée au-delà du seuil de planification, ou au-delà
  de 10 % (paramétrable par dossier) et du seuil d'insignifiance ; un poste nouveau ou disparu
  compte pour 100 % ; les totaux ne sont pas signalés ; le seuil doit être fixé avant.
- Ratios : N-2 tiré de la balance N-1 du dossier précédent ; délais calculés sur 360 jours.
- Matrice des risques (ISA 315, ISA 330) : onze cycles (un cycle « Emprunts et autres tiers »
  complète la liste du cahier des charges pour couvrir tous les comptes), six assertions ;
  risque d'anomalie significative selon une grille inhérent × contrôle, un risque important
  étant toujours élevé ; seules les cellules à risque moyen ou élevé alimentent le programme,
  avec un test de détail par assertion, des tests étendus si le risque est élevé et un test
  d'efficacité des contrôles si l'auditeur s'appuie sur eux (risque lié au contrôle faible).

## Module 3 — constats et suivi

### Lot 8
- Constat en cinq volets (critère, constat, cause, conséquence, recommandation), norme IIA
  2410 ; criticité sur quatre niveaux ; constats triés par criticité décroissante (ordre du
  rapport).
- Phase contradictoire : délai de réponse de 15 jours calendaires par défaut (paramétrable) ;
  désaccord, même partiel, obligatoirement motivé ; sans réponse dans le délai, le chef de
  mission peut valider et le rapport mentionnera l'absence de réponse.
- Le texte du constat est figé pendant l'attente de la réponse ; l'équipe peut l'ajuster après
  la réponse, avant validation ; après validation, constat et preuves sont figés.
- La mission ne passe en « Rapport » que si tous ses constats sont validés.
- Plans d'action : le responsable (ou l'audité) les fait avancer jusqu'à « Réalisé » ; seul
  l'audit les vérifie (IIA 2500) ; seul le chef de mission ou le Directeur enregistre une
  acceptation de risque, avec justification. Le suivi continue après la clôture de la mission.
- Relances : J-15, échéance, puis tous les 14 jours de retard ; le chef de mission est en copie
  des retards ; un report accepté relance le calendrier.
- Report d'échéance : une demande à la fois, décidée par le chef de mission ou le Directeur.
- Portail audité : l'audité ne voit que les constats qui lui sont adressés ou dont il porte un
  plan, jamais les brouillons, ni papiers, ni données, ni preuves internes.
- Lignes d'anomalie en preuve : 200 lignes au plus par preuve ; chaque ligne est recherchée
  dans la table pour garantir qu'elle n'a pas été fabriquée.
- Export Excel limité à 1 048 575 lignes (limite d'Excel) ; au-delà, CSV. Chaque export est
  journalisé.

## Module 2 — analyse de données

### Lot 9
- Le script ne voit que les entrées choisies sur sa page (tables et fichiers de la mission),
  déposées dans son répertoire de travail : ni base de données, ni réseau, ni variables
  d'environnement de l'application. Ses résultats passent uniquement par `audit.save`
  (20 tables au plus) et `audit.metric`.
- Traçabilité : le code exécuté est figé avec son empreinte SHA-256 à chaque exécution ; les
  tables produites portent la lignée (script, exécution, entrées). Elles ne sont pas
  recalculées par le rejeu de la lignée : on réexécute le script.
- Isolement en exploitation : conteneur Docker jetable par exécution (réseau « none »,
  mémoire et swap 2 Go, 1 processeur, 256 processus, racine en lecture seule, utilisateur
  nobody, capacités retirées), runtime gVisor recommandé. L'accès du worker au démon Docker
  est sensible : Docker sans privilège ou mandataire de socket limité. Le mode local (espace
  de noms réseau vide, limites mémoire, temps de calcul et taille de fichier) est réservé au
  développement : il ne cloisonne pas le disque.
- Durée maximale mesurée en temps réel (10 minutes) ; sortie console conservée jusqu'à
  100 Ko.
- Bibliothèque : publication par le droit « data:publish_library » (data analysts) ; un test
  publié n'est jamais modifié, une nouvelle version le remplace ; la mission garde la
  référence et la version du test repris. Colonnes attendues indicatives, à adapter en tête du
  script ; seuil de fractionnement des notes de frais = règle interne de l'entité.
- Audit en continu : échéances à l'heure choisie en UTC, vérifiées chaque heure ; une
  exécution en erreur ou sans l'indicateur surveillé alerte aussi (un contrôle silencieux ne
  vaut pas contrôle satisfaisant) ; destinataires : chef de mission et auteur du script ;
  missions clôturées non exécutées.

### Lot 5
- Les données analysées restent hors de la base de gestion : fichiers Parquet compressés,
  écrits une seule fois puis en lecture seule. La base ne garde que les métadonnées.
- Le fichier source déposé est conservé tel quel avec son empreinte SHA-256 (élément probant,
  ISA 500 et norme IIA 2330). La table produite a sa propre empreinte ; les deux se vérifient à
  tout moment.
- Formats par défaut de l'assistant : encodage détecté (UTF-8 ou Windows-1252), séparateur
  « ; », virgule décimale, espace pour les milliers, dates jj/mm/aaaa, montants entre
  parenthèses lus comme négatifs. Tous sont modifiables avant import.
- Une valeur non convertible n'interrompt pas l'import : elle devient vide et le nombre de
  valeurs concernées est signalé par colonne, pour que l'auditeur l'apprécie.
- Totaux de contrôle : somme exacte (arithmétique décimale) et nombre de valeurs de chaque
  colonne numérique, première et dernière date ; ils servent au rapprochement avec la
  source (balance, journal).
- Taille maximale d'un fichier importé : 2 Go (paramétrable).
- Bases SQL : seul l'administrateur déclare une source (adresse et compte de lecture) ; les
  utilisateurs n'écrivent qu'une requête SELECT, exécutée dans une transaction en lecture
  seule. Aucun utilisateur ne saisit d'adresse de connexion.
- Relevés PDF : seuls les PDF à texte sont lus (pas de reconnaissance de caractères sur les
  scans).
- Champs calculés : syntaxe proche d'Excel en français (SI, ARRONDI, ANNEE…, arguments séparés
  par « ; »), mots-clés anglais acceptés ; une division par zéro donne une valeur vide. Pas de
  fonction « aujourd'hui », pour que le résultat soit reproductible (NF-04).
- Une vue ne contient aucune donnée : la modifier est permis, la table d'origine ne change
  jamais.
- Statistiques : écart-type d'échantillon (n − 1), comme IDEA et Excel (ECARTYPE).
- Droits : lecture des données par les rôles ayant `data:read` ; import, vues et analyses par
  les membres de la mission ayant `data:analyze` (auditeur, chef de mission, data analyst).

### Lot 6
- Chaque analyse produit une nouvelle table, jamais une modification ; ses paramètres et ses
  tables d'entrée sont conservés (piste d'audit, ISA 230).
- Extraction : le « mode SQL » est la syntaxe d'expressions (proche du SQL, en français) ; aucune
  requête SQL libre n'est acceptée (NF-05). Une condition indéterminée (valeur vide) ne retient
  pas la ligne.
- Doublons : une valeur vide est traitée comme une valeur (deux clés vides sont en double).
  Mode approché : textes normalisés, Jaro-Winkler ≥ 0,9 par défaut sur chaque champ texte,
  égalité stricte sur les autres champs, regroupement transitif.
- Ruptures de séquence : sur un champ texte, le numéro est le groupe de chiffres final
  (« FAC-2026-0042 » → 42).
- Stratification : tranches fermées à gauche [a ; b[, plus deux tranches ouvertes ; toutes les
  tranches figurent, même vides.
- Ancienneté : tranches par défaut 30, 60, 90, 180 et 365 jours (usage des balances âgées
  clients et fournisseurs) ; « non échu » si la date est postérieure à la référence.
- Benford : méthode de Nigrini (montants ≥ 10 en valeur absolue, z avec correction de
  continuité, seuils MAD propres à chaque test) ; seuil de significativité 5 % (z > 1,96).
  Les lignes suspectes sont celles dont les chiffres sont en excès significatif.
- Jointure et rapprochement : une clé vide n'apparie jamais ; deux clés de types différents sont
  comparées comme du texte. Rapprochement : montants cumulés par clé, tolérance 0 par défaut.
- Valeurs aberrantes : |z| > 3 (score z) ou méthode de Tukey avec k = 1,5 (IQR).
- Recherche floue : formes juridiques usuelles retirées des noms (SARL, SA, SUARL, ETS, GIE…),
  seuil 0,85 ; comparaison limitée à 50 millions de paires.

### Lot 7
- Références : ISA 530 et guide AICPA « Audit Sampling ». Les facteurs de confiance sont
  calculés par la loi de Poisson (3,00 à 95 %, 2,31 à 90 %) ; les facteurs d'expansion de
  l'erreur attendue sont ceux de la table AICPA (1,6 à 95 %).
- Tests de contrôles : taille par la loi binomiale, avec ⌈n × taux attendu⌉ écarts admis.
- MUS : population = montants positifs ; montants nuls ou négatifs exclus et comptés à part
  (à traiter par un autre test). Une ligne supérieure à l'intervalle peut être tirée
  plusieurs fois ; elle figure une fois avec son nombre de sélections.
- Échantillon stratifié : allocation proportionnelle à l'effectif des strates (plus forts
  restes), au moins une ligne par strate non vide.
- Graine : tirée au hasard et enregistrée si l'utilisateur ne la fixe pas (ISA 230 : le
  dossier doit permettre de refaire le tirage).
- Évaluation MUS : méthode de la cellule (AICPA). Surévaluations et sous-évaluations évaluées
  séparément ; taux d'erreur plafonné à 100 % ; la conclusion compare la limite supérieure des
  surévaluations à l'erreur tolérable.
- Lignée : une table est l'aboutissement d'opérations enregistrées ; le rejeu recalcule depuis
  les fichiers sources conservés (pour une source SQL, la requête est rejouée sur la base, dont
  le contenu a pu changer).
- Macros : partagées entre missions ; « même structure » = colonnes attendues présentes avec le
  même type, colonnes supplémentaires admises.
- Stockage S3 sous Docker : SeaweedFS, objets chiffrés (SSE-S3) avec une clé fournie à
  l'installation.

## Module 1 — gestion des audits

### Lot 4
- Rédaction des papiers par les auditeurs et le chef de la mission ; le data analyst lit les
  papiers (matrice de la section 2).
- Référence de papier : majuscules et chiffres, puis un tiret et une numérotation à points
  (B-2.3), unique dans la mission.
- Signature de préparation subordonnée à une conclusion et à une évaluation du contrôle.
- Revue par le chef de mission ou un superviseur ; approbation par le chef de mission ou le
  Directeur ; le préparateur ne revoit ni n'approuve son papier (norme IIA 2340).
- L'approbation exige que les notes de revue du papier soient clôturées ; la clôture de la
  mission exige que tous les papiers soient approuvés.
- Une modification du contenu ou des pièces jointes après signature annule toutes les
  signatures. Le réviseur et le chef de mission sont prévenus, pas l'auteur de la modification.
- Pièces jointes admises : PDF, Excel, Word, CSV, texte, images ; 100 Mo au plus ; contenu
  vérifié par ses premiers octets ; jamais réécrites (un même nom crée une nouvelle version).
- Images des travaux : uniquement des pièces jointes du papier (pas d'image externe).
- Six marques de révision par défaut, modifiables ; une marque se désactive, elle ne se
  supprime pas.
- Versions et signatures inaltérables, protégées par des déclencheurs SQL.
- À la clôture, la date du dernier audit de l'entité devient la date de fin de la mission. Elle
  alimente la note d'ancienneté du risque.
- E-mails envoyés par SMTP si un serveur est configuré ; sinon ils restent en file
  d'attente.

### Lot 3
- Les missions ne se créent depuis le plan que s'il est validé, et une ligne du plan ne lance
  qu'une mission. Les missions ponctuelles sont admises, avec ou sans entité de l'univers.
- Référence de mission : M-année de début-numéro d'ordre (M-2027-001).
- Un seul chef de mission par mission. Sans chef désigné, le créateur pilote la mission.
- Statuts : un cran à la fois ; retour d'un cran admis (par exemple de Revue à Terrain) pour
  compléter les travaux ; aucun changement après clôture.
- Temps saisis en heures, au quart d'heure ; 1 jour-homme = 8 heures (paramétrable) ; pas de
  saisie future ; chacun ne corrige que ses saisies.
- Bibliothèque : catégories de risques COSO (opérationnel, information financière,
  conformité, stratégique) plus « fraude » ; contrôles qualifiés par type (préventif,
  détectif), nature (manuel, semi-automatique, automatique) et fréquence.
- Procédures typées selon la norme IIA 2320 et l'ISA 330 : revue de conception, test
  d'efficacité, contrôle substantif.
- Bibliothèque de départ : 11 risques et 15 contrôles usuels sur les achats, les ventes, la
  paie, la trésorerie et les notes de frais. Ce sont des exemples à adapter.
- La méthodologie (bibliothèque, modèles) est tenue par le Directeur et les chefs de mission ;
  les auditeurs la consultent.
- Une procédure est confiée à un membre de l'équipe ; son échéance tombe pendant la mission.

### Lot 2
- Référentiel IIA, notes de risque de 1 à 5, score sur 100 = Σ(poids × note) / Σ(poids × 5).
- Cinq critères par défaut : impact financier (3), impact réglementaire et d'image (2),
  probabilité (3), faiblesse du contrôle interne (2), ancienneté du dernier audit (1).
- Ancienneté : 1 + années pleines depuis le dernier audit, plafonnée à 5 ; jamais audité = 5.
- Carte : case = arrondi au plus proche ; niveaux faible < 4 ≤ modéré < 8 ≤ élevé < 15 ≤ critique.
- Plan : une version par enregistrement ; seul le brouillon est modifiable ; la validation fige
  la version et remplace la précédente ; une entité au plus une fois par plan ; période dans
  l'année du plan.
- Lecture de l'univers et du plan : Administrateur, Directeur, Chef de mission.
