# Registre des données personnelles (NF-08, RGPD art. 30)

Registre des traitements d'AuditLab, à compléter par le responsable de traitement (l'organisme
qui exploite l'outil) : identité du responsable, du délégué à la protection des données, pays
d'hébergement. Les durées sont des valeurs par défaut paramétrables.

| Traitement | Personnes concernées | Données | Finalité et base légale | Durée de conservation | Destinataires |
|---|---|---|---|---|---|
| Comptes utilisateurs | Auditeurs, chefs de mission, directeurs, data analysts, experts-comptables, collaborateurs, audités | Nom, adresse e-mail, rôle, équipe, empreinte du mot de passe (Argon2id), secret TOTP chiffré | Contrôle d'accès ; intérêt légitime (sécurité du système) | Durée de l'emploi ou de la mission, puis désactivation ; jamais de suppression physique (NF-03) | Administrateurs |
| Journal d'audit et journal applicatif | Utilisateurs | Actions, horodatage, adresse IP, valeurs avant/après (secrets masqués) | Traçabilité et preuve (NF-01, NF-02) ; obligation légale et intérêt légitime | Durée de conservation des dossiers d'audit (10 ans par défaut, alignée sur l'archivage comptable OHADA) | Administrateurs, Direction de l'audit |
| Dossiers de mission | Responsables et salariés des entités auditées, audités | Noms et fonctions cités dans les papiers de travail, constats, réponses, plans d'action | Mission d'audit ; intérêt légitime ou mission d'intérêt public selon l'organisme | 10 ans après la clôture (dossier de travail, ISA 230 / normes IIA) | Équipe de mission, Direction, audités pour leurs constats |
| Données analysées (Module 2) | Salariés, tiers, clients, fournisseurs des entités auditées | Extractions de paie, de tiers, de notes de frais, de grand livre (selon la mission) | Tests d'audit ; intérêt légitime | **`conservation_donnees_mois` (60 mois) après la clôture de la mission**, puis purge automatique des lignes et des fichiers sources | Équipe de mission |
| Portefeuille du cabinet (Module 6) | Dirigeants et contacts des clients | Nom, fonction, adresse e-mail, documents permanents | Exécution de la lettre de mission ; contrat | Durée de la relation, puis 10 ans (archivage comptable) | Expert-comptable, collaborateurs du dossier |
| Notifications et e-mails | Utilisateurs | Adresse e-mail, contenu des alertes | Information des utilisateurs ; intérêt légitime | 1 an | Destinataire |

## Purge automatique des données analysées

- Chaque jour, la tâche planifiée (`auditlab.daily_followup`) purge les tables du Module 2 et
  les fichiers sources importés des missions clôturées depuis plus de
  `AUDITLAB_CONSERVATION_DONNEES_MOIS` mois (60 par défaut) ; la sortie console des scripts est
  effacée.
- Restent, comme trace de la preuve : le nom de la table, son schéma, son nombre de lignes, son
  empreinte SHA-256, ses totaux de contrôle et sa lignée ; la grille affiche « Lignes purgées le
  … ».
- Chaque purge est inscrite au journal d'audit (`purge_conservation`, avec le nombre de tables
  et de fichiers). Simulation préalable : `python -m app.cli purge-donnees --simulation`.
- Le verrou des missions clôturées (AUD-22) n'est levé que pour ces colonnes de purge.

## Mesures de sécurité

Authentification forte (TOTP obligatoire pour les rôles sensibles), sessions expirant après
30 minutes d'inactivité, contrôle d'accès vérifié côté serveur à chaque requête, journal
d'audit chaîné et non modifiable, chiffrement en transit (TLS) et au repos (stockage S3 avec
SSE, sauvegardes chiffrées avec age), bac à sable isolé pour les scripts, minimisation : seules
les entrées choisies sont exposées à un script.

## Droits des personnes

Accès et rectification : par l'administrateur (comptes) ou l'équipe de mission (dossiers). La
limitation et l'effacement s'apprécient au regard de l'obligation de conservation des dossiers
d'audit ; une demande est tracée dans le journal d'audit.
