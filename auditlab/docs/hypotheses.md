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

## Module 1 — gestion des audits

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
