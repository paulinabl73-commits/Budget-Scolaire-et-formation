# Performance (NF-09 à NF-11)

Mesures reproductibles avec les scripts de `backend/perf/`. Environnement de mesure : un
conteneur de développement à 4 vCPU et 16 Go partagés entre PostgreSQL 16, l'API, le
générateur de charge et le serveur de développement du frontend. C'est une configuration
défavorable : en exploitation, PostgreSQL et l'API ont chacun leurs processeurs et le
générateur de charge tourne sur un autre poste.

## NF-09 — pages métier en moins d'une seconde pour 50 utilisateurs simultanés

Script : `perf/nf09_charge.py`. Chaque utilisateur virtuel ouvre en boucle une page métier
(accueil, mission, constats, temps, données, grille) ; une page = les appels que l'écran lance
en parallèle ; durée mesurée du premier appel à la dernière réponse ; 15 s d'échauffement non
mesurées ; temps de lecture d'un écran tiré entre 0,5 et 1,5 fois la valeur `--pause`.

API : 4 processus (`--workers 4`), keep-alive 75 s, journal JSON au niveau INFO.

| Temps de lecture moyen | Débit | Médiane | 95e centile | Maximum | Erreurs |
|---|---|---|---|---|---|
| 5 s (usage réaliste) | 9,9 pages/s | 0,059 s | 0,129 s | 0,293 s | 0 |
| 2 s | 23,8 pages/s | 0,067 s | 0,160 s | 0,354 s | 0 |
| 1 s (charge extrême) | 39,6 pages/s | 0,204 s | 0,657 s | 1,485 s | 0 |

**Objectif atteint** dans les trois régimes (95e centile < 1 s).

Optimisations apportées par l'exigence :

- **Session** : l'activité n'est réécrite en base qu'une fois par minute
  (`session_touch_seconds`) au lieu d'une écriture et d'un `commit` à chaque requête ;
  l'utilisateur est chargé avec la session (une requête au lieu de deux). Coût d'une requête
  authentifiée : 16,7 ms → 6,3 ms.
- **Pool de connexions** : 15 connexions par processus (+5 de débordement) au lieu de 5 ; sous
  charge, les connexions excédentaires étaient ouvertes et fermées à chaque requête.
  Dimensionnement : (pool + débordement) × processus < `max_connections` de PostgreSQL (100).
- **Exploitation** : 4 processus uvicorn (`WEB_CONCURRENCY`), keep-alive 75 s ; nginx garde des
  connexions persistantes vers l'API, compresse les réponses JSON et met en cache les
  ressources versionnées.

Avant ces réglages (1 écriture de session par requête, pool de 5, keep-alive 5 s), le 95e
centile à 1 s de lecture était de 2,2 s.

Commande :

```
python perf/nf09_charge.py --url http://127.0.0.1:8000 --utilisateurs 50 --duree 60 \
    --pause 5 --compte <adresse>:<mot de passe> --mission <id> --table <id de table>
```

## NF-10 — import d'un million de lignes en moins de 30 s, doublons en moins de 10 s

Script : `perf/nf10_import.py`. Fichier généré de façon déterministe : 1 000 000 de lignes,
4 colonnes (pièce, fournisseur, date jj/mm/aaaa, montant à virgule décimale), 46 Mo. L'import
suit la chaîne de la tâche d'import : lecture (Polars), typage des dates et des montants,
écriture Parquet en lecture seule, totaux de contrôle et empreinte SHA-256 (DAT-04).

| Mesure | Résultat (machine au repos) | Objectif |
|---|---|---|
| Import complet | 0,56 s | < 30 s |
| Doublons exacts sur (fournisseur, montant) | 0,17 s | < 10 s |

**Objectif atteint** avec une marge d'un facteur 50. La recherche approchée (DAT-10, mode
« approchée ») compare des paires de noms et reste bornée à 50 millions de paires : elle est
destinée aux tables de tiers, pas au million de lignes d'écritures.

```
AUDITLAB_DATA_DIR=/tmp/perf python perf/nf10_import.py --dossier /tmp/perf --lignes 1000000
```

## NF-11 — grille fluide sur 10 millions de lignes

La grille (AG Grid, modèle « infinite ») demande des blocs de 100 lignes ; chaque bloc est une
requête DuckDB sur le Parquet (LIMIT/OFFSET, tri et filtres traduits en SQL paramétré). Script :
`perf/nf11_grille.py` (table de 10 millions de lignes, 3 colonnes).

Premier constat : sans tri, tout bloc est servi en moins de 0,1 s ; avec un tri, un bloc loin
du début coûtait 1,1 à 1,5 s, car DuckDB doit trier tout ce qui le précède. D'où l'optimisation
de l'exigence : au-delà du rang 50 000 (`grille_cache_rang`), la table filtrée et triée est
écrite une fois en Parquet (cache par requête, filtres et tri ; purgé après 2 heures) et les
blocs sont lus par position. Cette copie est préparée en arrière-plan dès le premier bloc trié
d'une grande table, pendant que l'utilisateur lit l'écran. Effet secondaire utile : l'ordre des
lignes à valeurs égales est le même d'un bloc à l'autre.

| Bloc demandé (100 lignes) | Durée |
|---|---|
| Début, avec le total | 0,100 s |
| Milieu / fin, sans tri | 0,042 s / 0,058 s |
| Tri, premier bloc (prépare la copie triée) | 0,194 s |
| Tri, saut au milieu 3 s plus tard | 0,058 s |
| Tri, bloc suivant / fin / saut au quart | 0,046 s / 0,055 s / 0,048 s |
| Filtre « égal », avec total | 0,109 s |
| Recherche plein texte | 0,093 s |

**Objectif atteint** : tous les blocs en moins de 0,2 s, défilement sans attente perceptible.
Sans la préparation (saut immédiat, avant la fin de l'écriture de la copie), le premier bloc
profond attend la copie, soit 2,5 s une fois par tri et par filtre.

```
AUDITLAB_DATA_DIR=/tmp/perf python perf/nf11_grille.py --lignes 10000000
```
