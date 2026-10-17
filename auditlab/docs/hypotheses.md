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

## Module 2 — analyse de données

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
