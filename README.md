# ERO — Optimisation des tournées de déneigement (Montréal)

Projet de Recherche Opérationnelle : planifier les tournées de déneigeuses sur le
réseau routier de plusieurs arrondissements de Montréal (Verdun, Outremont, Anjou,
Rivière-des-Prairies) en minimisant le coût total, sous contrainte de durée maximale
par tournée.

Le problème est modélisé comme un **Problème du Postier Chinois orienté** (Chinese
Postman Problem) : chaque rue (arête du graphe routier) doit être parcourue au moins
une fois par une déneigeuse partant et revenant à un dépôt.

## Architecture

Le code est découpé en modules à plat (pas de sous-package), chacun correspondant à
une responsabilité du pipeline :

| Fichier | Rôle |
|---|---|
| `config.py` | Constantes de coût, coordonnées des POI/zones denses par arrondissement, mapping `GRAPHES`, paramètres des scénarios, classe `Chrono` et état partagé (`_chrono`, `_VERBOSE`) |
| `graphe.py` | Chargement du graphe routier (`charger_graphe`) et recherche du nœud le plus proche d'une coordonnée (`noeud_le_plus_proche`) |
| `scenarios.py` | Construction des priorités d'arêtes : corridors POI→zones denses (`construire_corridors`) et hiérarchie routière artères/collectrices/locales (`construire_hierarchie_routiere`) |
| `depots.py` | Placement des dépôts par k-means++ sur les arêtes de référence (`suggerer_depots`) |
| `cpp.py` | Solveur du postier chinois orienté : équilibrage des degrés, connexité forte, circuit eulérien (`cpp_oriente`) |
| `planification.py` | Découpage d'un secteur en tournées respectant la durée max, calcul des coûts, partition du graphe par dépôt (`executer`) |
| `pipeline.py` | Orchestration batch : lance tous les scénarios pour toutes les combinaisons (nb dépôts × durée max), export JSON, récapitulatif (`main`, `lancement_scenario0..3`) |
| `demo.py` | Mode démo CLI : calcule une configuration pour un secteur donné et affiche l'impact (accès population ou hiérarchie routière) du scénario priorisé vs la base (`mode_demo`) |
| `main.py` | Point d'entrée : parse les arguments CLI et dispatche vers `pipeline.py` ou `demo.py` |

Données : `Montreal.graphml`, `verdun.graphml`, `outremont.graphml`, `anjou.graphml`,
`rdp.graphml` — graphes routiers (nœuds = intersections avec `lat`/`lon`, arêtes =
segments de rue avec `length` en mètres), avec les vrais identifiants de nœuds OSM.

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install networkx numpy scipy
```

(le `.venv/` et les fichiers générés sont ignorés via `.gitignore`)

## Utilisation

### Mode batch (`--scenario 0` ou sans argument)

Lance le scénario de base sur un secteur, en testant toutes les combinaisons de
`SCENARIOS_DEPOTS` (1, 2, 3, 5, 6, 7, 10 dépôts) × `SCENARIOS_TEMPS` (12h) :

```bash
.venv/bin/python3 main.py --sector verdun --scenario 0
```

Sans argument, tourne sur tous les graphes listés dans `config.GRAPHES` (Montréal +
les 4 arrondissements) :

```bash
.venv/bin/python3 main.py
```

### Mode démo (`--scenario 1`, `2` ou `3`)

Calcule la configuration optimale (`config.DEPOTS_OPTIMAUX`, `Tmax = 12h`) pour un
secteur et affiche un tableau coût/durée + l'impact du scénario priorisé comparé à
la base (sans priorisation, mêmes dépôts) :

```bash
.venv/bin/python3 main.py --sector outremont --scenario 1
.venv/bin/python3 main.py --sector anjou     --scenario 2
.venv/bin/python3 main.py --sector rdp       --scenario 3
```

Secteurs disponibles : `verdun`, `outremont`, `anjou`, `rdp`, `montreal` (le scénario
0 seulement, les autres scénarios ont des coordonnées POI propres aux 4 secteurs).

Chaque run génère `demo_<secteur>_s<scenario>.txt` (rapport texte) et
`demo_<secteur>_s<scenario>.json` (export structuré des tournées).

## Les 4 scénarios

Chaque scénario marque les arêtes du graphe avec une `priorite` (1 = haute, 3 =
basse) qui influence le placement des dépôts (`depots.py`) et l'ordre de passage à
l'intérieur d'une tournée (`cpp.circuit_eulerien` traite les arêtes P1 en premier).

- **Scénario 0 — Base** : aucune priorisation, toutes les arêtes en P3. Référence
  pour mesurer le gain des autres scénarios.
- **Scénario 1 — Accès aux services de santé** : marque en P1 les plus courts
  chemins entre chaque hôpital/CLSC/clinique (`config.HOPITAUX_COORDS`) et chaque
  zone à forte densité de population (`config.DENSITE_COORDS`).
- **Scénario 2 — Impact économique** : même logique que le scénario 1, mais avec
  les centres commerciaux/supermarchés (`config.COMMERCES_COORDS`).
- **Scénario 3 — Hiérarchie routière** : classe chaque rue en artère principale
  (P1), collectrice (P2) ou locale/résidentielle (P3), à partir de la seule
  topologie du graphe (le réseau ne porte aucun tag OSM `highway=...`). Le score
  combine la centralité d'intermédiarité de l'arête (50%, approximée par
  échantillonnage de pivots sur les grands graphes) et le degré moyen de ses deux
  extrémités (50%). Seuils : top 12% (percentile ≥ 88) → artères, 60e-88e
  percentile → collectrices (~28%), sous le 60e percentile → locales (~60%)
  (`config.SEUIL_PERCENTILE_P1/P2`).

Les scénarios 1/2/3 affichent en mode démo un tableau comparant, à 1h/2h/4h/6h/8h/12h,
le % de corridors/artères/collectrices dégagés avec priorisation (S1/S2/S3) contre
sans priorisation (S0, mêmes dépôts).

## Pipeline de résolution

1. **Chargement** (`graphe.charger_graphe`) : lit le `.graphml`, force un graphe
   orienté, ajoute les arêtes retour manquantes (marquées `deadhead=True`).
2. **Priorisation** (`scenarios.py`) : marque les arêtes en P1/P2/P3 selon le
   scénario choisi.
3. **Placement des dépôts** (`depots.suggerer_depots`) : k-means++ sur les milieux
   des arêtes de référence (P1 si elles existent, sinon arêtes entre nœuds de degré
   élevé), puis snap au nœud routier le plus proche de chaque centroïde.
4. **Partition** (`planification.partitionner`) : chaque arête est assignée au
   dépôt le plus proche (k-d tree sur les coordonnées).
5. **Planification par secteur** (`planification.planifier_secteur`) : subdivise
   récursivement (k-means sur les milieux d'arêtes) si la durée estimée dépasse
   `temps_max`, jusqu'à 8 niveaux de profondeur.
6. **Résolution CPP** (`cpp.cpp_oriente`) pour chaque tournée :
   - rend le sous-graphe fortement connexe en ajoutant des plus courts chemins
     vers/depuis le dépôt (`_rendre_fortement_connexe`) ;
   - équilibre les degrés entrant/sortant de chaque nœud (`_equilibrer`) ;
   - construit un circuit eulérien par l'algorithme de Hierholzer, en explorant les
     arêtes par priorité décroissante (`circuit_eulerien`).
7. **Coût** (`planification.cout_tournee`) :
   - `coût = COUT_FIXE_JOUR + distance_km × COUT_PAR_KM + coût_horaire`
   - `coût_horaire` = heures × `COUT_HORAIRE_NORMAL` (1.1 $/h) jusqu'à `SEUIL_H` (8h),
     puis `COUT_HORAIRE_SUPP` (1.3 $/h) au-delà.
   - vitesse de référence : `VITESSE_KMH` = 10 km/h.
8. **Export** (`pipeline.exporter_json`) : écrit `resultat_<tag>_<n>depots_<h>h.json`
   avec le détail de chaque tournée (séquence de nœuds, distance, durée, coût).

## Modèle de coût (dépôts, mode démo)

`demo._cout_depot_jour(n)` ajoute un coût d'infrastructure amorti sur 30 ans pour
`n` dépôts (surface ≈ `30n + 15√n` m², construction à 1050 $/m², + 500 $/an de
maintenance par dépôt), additionné au coût opérationnel pour obtenir le coût total
affiché en mode démo.
