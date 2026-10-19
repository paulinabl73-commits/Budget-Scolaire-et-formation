# Accessibilité (NF-14, RGAA niveau AA visé)

## Audit automatique

Outil : axe-core 4.10 (règles WCAG 2.1 niveaux A et AA, sur lesquelles s'appuie le RGAA 4.1),
exécuté dans Chromium sur 28 écrans : connexion, accueil, missions et leurs onglets (synthèse,
programme, papiers, données, constats, rapport, scripts, temps), fiche d'une table de données
et sa grille, univers, carte des risques, plan, bibliothèque, tableaux de bord, modèles de
rapport, utilisateurs, journal, référentiels, marques, critères, profil, portefeuille et
dossier client (expert-comptable), portail de l'audité.

Premier passage : trois règles en échec, corrigées.

| Règle | Constat | Correction |
|---|---|---|
| color-contrast | Textes secondaires gris (#64748b) sur fond gris clair : contraste 4,34:1 (< 4,5:1) | Gris plus soutenu (#475569) pour tous les textes secondaires : contraste supérieur à 7:1 sur blanc |
| nested-interactive | Graphe de lignée : nœuds cliquables dans un SVG déclaré comme image | Le SVG est un groupe nommé (`role="group"`) ; les nœuds restent des liens atteignables au clavier |
| scrollable-region-focusable | Zone défilante des grilles AG Grid sans élément focalisable | Faux positif, voir ci-dessous |

Second passage : seule reste l'alerte sur les zones défilantes d'AG Grid.

## Grilles AG Grid

AG Grid place des « gardes de tabulation » de part et d'autre de la grille : la tabulation
entre dans la grille, puis les flèches déplacent la cellule active et font défiler la zone ;
les lignes et colonnes portent `aria-rowindex` et `aria-colindex`. axe-core ne voit pas ces
gardes, voisines de la zone défilante, d'où l'alerte. Ajouter un point de tabulation sur la
zone elle-même romprait la structure ARIA de la grille (`grid` > `rowgroup` > `row`), ce que
l'audit signale aussitôt comme erreur critique : l'alerte est donc conservée et documentée.

Vérification au clavier (Playwright) : la première tabulation atteint le lien « Aller au
contenu », une cellule de la grille est atteinte à la tabulation, et 40 appuis sur la flèche
bas amènent la ligne 42 à l'écran (zone défilée de 1 213 pixels).

## Pratiques retenues

- Lien d'évitement « Aller au contenu » en tête de page ; zone principale focalisable.
- Navigation entièrement possible au clavier ; focus visible (styles par défaut conservés).
- Champs de formulaire tous étiquetés ; messages d'erreur annoncés (`role="alert"`).
- Onglets signalés par `aria-current` ; tableaux avec en-têtes `scope` ; graphiques nommés.
- Textes en français, formats de nombre et de date français (NF-13) ; langue du document
  déclarée.

Le RGAA comporte aussi des critères non vérifiables automatiquement (pertinence des
alternatives, ordre de lecture, restitution par lecteur d'écran) : un audit manuel avec NVDA
ou VoiceOver reste à mener avant une déclaration de conformité.
