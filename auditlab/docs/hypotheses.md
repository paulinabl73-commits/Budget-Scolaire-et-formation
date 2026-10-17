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
- Fichiers stockés hors base, dans un stockage compatible S3 (MinIO) chiffré au repos.
  Téléchargements journalisés ; liens signés valides une heure pour l'affichage des images.

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
