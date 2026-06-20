"""
Déneigement de Montréal — CPP orienté, multi-véhicules, multi-dépôts.
Version instrumentée avec chronomètres + options de performance.
"""

import json
import time
import numpy as np
import networkx as nx
from dataclasses import dataclass, field
from scipy.spatial import cKDTree

# ---------------------------------------------------------------------------
# ⚙️  OPTIONS DE PERFORMANCE — ajustez ici pour accélérer au détriment
#     de la précision du résultat CPP
# ---------------------------------------------------------------------------

# Nombre max d'itérations pour rendre le graphe fortement connexe (défaut=200)
# ↓ Réduire à 20–50 pour aller plus vite ; certains sous-graphes peuvent rester
#   déconnectés → circuit eulérien partiel (quelques rues non couvertes)
MAX_ITER_CONNEXITE = 200

# Nombre max d'itérations pour équilibrer in/out degree (défaut=50)
# ↓ Réduire à 5–15 ; des nœuds déséquilibrés subsisteront → circuit
#   moins optimal (quelques arêtes manquantes ou doublées)
MAX_ITER_EQUILIBRE = 50

# Nombre de voisins considérés dans l'appariement greedy (défaut=20)
# ↓ Réduire à 3–5 ; appariements moins bons → deadheading légèrement plus long
K_VOISINS = 20

# Si True, utilise Bellman-Ford au lieu de Dijkstra (plus robuste mais ~10x plus lent).
# Laisser False sauf graphe avec poids négatifs.
DIJKSTRA_BELLMAN = False

# ---------------------------------------------------------------------------
# Constantes métier
# ---------------------------------------------------------------------------

COUT_FIXE_JOUR      = 500.0
COUT_PAR_KM         = 1.1
COUT_HORAIRE_NORMAL = 1.1
COUT_HORAIRE_SUPP   = 1.3
SEUIL_H             = 8.0
VITESSE_KMH         = 10.0


# ---------------------------------------------------------------------------
# Chronomètre utilitaire
# ---------------------------------------------------------------------------

class Chrono:
    """Accumule du temps par étape et affiche un résumé."""
    def __init__(self):
        self._debut_global = time.perf_counter()
        self._etapes: dict[str, float] = {}
        self._en_cours: dict[str, float] = {}
        self._appels: dict[str, int] = {}

    def debut(self, etape: str):
        self._en_cours[etape] = time.perf_counter()

    def fin(self, etape: str):
        if etape in self._en_cours:
            elapsed = time.perf_counter() - self._en_cours.pop(etape)
            self._etapes[etape] = self._etapes.get(etape, 0.0) + elapsed
            self._appels[etape] = self._appels.get(etape, 0) + 1

    def rapport(self):
        total = time.perf_counter() - self._debut_global
        print("\n" + "─" * 60)
        print(f"{'ÉTAPE':<35} {'TEMPS':>8}  {'APPELS':>7}")
        print("─" * 60)
        for etape, t in sorted(self._etapes.items(), key=lambda x: -x[1]):
            nb = self._appels.get(etape, 1)
            print(f"  {etape:<33} {t:>7.2f}s  {nb:>7}")
        print("─" * 60)
        print(f"  {'TOTAL GLOBAL':<33} {total:>7.2f}s")
        print("─" * 60 + "\n")


# Instance globale partagée
_chrono = Chrono()


# ---------------------------------------------------------------------------
# Fonctions métier
# ---------------------------------------------------------------------------

def cout_tournee(distance_km):
    h    = distance_km / VITESSE_KMH
    fixe = COUT_FIXE_JOUR
    km   = distance_km * COUT_PAR_KM
    hor  = (h * COUT_HORAIRE_NORMAL if h <= SEUIL_H
            else SEUIL_H * COUT_HORAIRE_NORMAL + (h - SEUIL_H) * COUT_HORAIRE_SUPP)
    return h, fixe + km + hor, (fixe, km, hor)


def charger_graphe(chemin):
    _chrono.debut("charger_graphe")
    G = nx.read_graphml(chemin)
    if not isinstance(G, nx.DiGraph):
        G = nx.DiGraph(G)
    for n, d in G.nodes(data=True):
        G.nodes[n]["lat"] = float(d.get("lat", 0.0))
        G.nodes[n]["lon"] = float(d.get("lon", 0.0))
    for u, v, d in list(G.edges(data=True)):
        lng = float(d.get("length", 0.0))
        G[u][v]["length"] = lng
        if not G.has_edge(v, u):
            G.add_edge(v, u, length=lng)
    _chrono.fin("charger_graphe")
    return G


def partitionner(G, depots):
    _chrono.debut("partitionner")
    for d in depots:
        if d not in G.nodes:
            raise ValueError(f"Dépôt '{d}' introuvable.")
    nodes  = list(G.nodes())
    coords = np.array([[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in nodes])
    dc     = np.array([[G.nodes[d]["lat"], G.nodes[d]["lon"]] for d in depots])
    dists, idxs = cKDTree(dc).query(coords)
    nd   = {n: depots[idxs[i]] for i, n in enumerate(nodes)}
    dist = {n: float(dists[i])  for i, n in enumerate(nodes)}

    secteurs = {d: [] for d in depots}
    for u, v in G.edges():
        d = nd[u] if dist.get(u, float("inf")) <= dist.get(v, float("inf")) else nd[v]
        secteurs[d].append((u, v))

    # Statistiques d'équilibre
    tailles = [len(v) for v in secteurs.values()]
    if tailles:
        moy  = np.mean(tailles)
        mini = min(tailles)
        maxi = max(tailles)
        ratio = maxi / mini if mini > 0 else float("inf")
        print(f"    Secteurs : min={mini}  moy={moy:.0f}  max={maxi}  "
              f"ratio={ratio:.1f}x  (idéal ≈ 1.0x)")

    _chrono.fin("partitionner")
    return secteurs


def circuit_eulerien(M, source):
    _chrono.debut("circuit_eulerien")
    adj = {u: [] for u in M.nodes()}
    for u, v, data in M.edges(data=True):
        if u != v:  # ignorer les self-loops qui causent les boucles infinies
            adj[u].append((v, data.get("length", 0.0)))

    stack   = [source]
    circuit = []

    while stack:
        u = stack[-1]
        if adj[u]:
            v, _ = adj[u].pop()
            stack.append(v)
        else:
            circuit.append(stack.pop())

    circuit.reverse()
    _chrono.fin("circuit_eulerien")
    return circuit


def _dijkstra_path(G, src, dst):
    try:
        algo = nx.bellman_ford_path if DIJKSTRA_BELLMAN else nx.dijkstra_path
        return algo(G, src, dst, weight="length")
    except nx.NetworkXNoPath:
        return None


def _ajouter_chemin(G, M, path):
    for a, b in zip(path[:-1], path[1:]):
        if a != b:  # jamais de self-loop
            M.add_edge(a, b, length=G[a][b]["length"])


def _rendre_fortement_connexe(G, M, depot):
    _chrono.debut("connexite")
    for iteration in range(MAX_ITER_CONNEXITE):
        sccs = list(nx.strongly_connected_components(M))
        if len(sccs) == 1:
            break
        scc_depot = next(c for c in sccs if depot in c)
        progres = False
        for scc in sccs:
            if scc is scc_depot:
                continue
            rep = next(iter(scc))
            for src, dst in [(depot, rep), (rep, depot)]:
                path = _dijkstra_path(G, src, dst)
                if path:
                    _ajouter_chemin(G, M, path)
                    progres = True
        if not progres:
            break
    _chrono.fin("connexite")


def _equilibrer(G, M):
    _chrono.debut("equilibrage")
    noeuds_M = set(M.nodes())

    for _ in range(MAX_ITER_EQUILIBRE):
        exc, dfc = [], []
        for n in M.nodes():
            delta = M.out_degree(n) - M.in_degree(n)
            if delta > 0:
                exc.extend([n] * delta)
            elif delta < 0:
                dfc.extend([n] * (-delta))

        if not exc:
            break

        coords_dfc = np.array([[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in dfc])
        tree = cKDTree(coords_dfc)

        utilises = set()
        for src in exc:
            coord = np.array([G.nodes[src]["lat"], G.nodes[src]["lon"]])
            k = min(len(dfc), K_VOISINS)
            _, voisins = tree.query(coord, k=k)
            if isinstance(voisins, (int, np.integer)):
                voisins = [voisins]
            for j in voisins:
                if j in utilises:
                    continue
                dst = dfc[j]
                if dst not in noeuds_M:
                    continue
                if dst == src:  # éviter les self-loops
                    continue
                path = _dijkstra_path(G, src, dst)
                if path:
                    _ajouter_chemin(G, M, path)
                    utilises.add(j)
                    break

    _chrono.fin("equilibrage")


def cpp_oriente(G, aretes, depot):
    M = nx.MultiDiGraph()
    for u, v in aretes:
        M.add_edge(u, v, length=G[u][v]["length"])
    if M.number_of_edges() == 0:
        return [depot], 0.0
    if depot not in M.nodes:
        M.add_node(depot)

    _rendre_fortement_connexe(G, M, depot)
    _equilibrer(G, M)

    circuit = circuit_eulerien(M, depot)
    dist = sum(
        G[circuit[i]][circuit[i+1]]["length"]
        for i in range(len(circuit) - 1)
        if G.has_edge(circuit[i], circuit[i+1])
    )
    return circuit, dist


def subdiviser(G, aretes, nb):
    if nb <= 1 or len(aretes) <= 1:
        return [aretes]
    nb = min(nb, len(aretes))
    lats = [((G.nodes[u]["lat"] + G.nodes[v]["lat"]) / 2) for u, v in aretes]
    ordre = np.argsort(lats)
    taille = max(1, len(aretes) // nb)
    groupes = []
    for k in range(nb):
        debut = k * taille
        fin   = debut + taille if k < nb - 1 else len(aretes)
        g     = [aretes[ordre[i]] for i in range(debut, fin)]
        if g:
            groupes.append(g)
    return groupes


@dataclass
class Tournee:
    depot: str
    id: int
    aretes: list
    sequence: list
    distance_km: float
    duree_h: float
    cout_total: float
    detail_cout: tuple


def planifier_secteur(G, depot, aretes, temps_max):
    if not aretes:
        return []
    resultats = []
    compteur  = [0]

    def traiter(groupe, profondeur):
        # ── Estimation sans lancer le CPP ──────────────────────────────────
        dist_estimee_km = sum(G[u][v]["length"] for u, v in groupe) / 1000
        h_estime = dist_estimee_km / VITESSE_KMH

        # Nombre de véhicules nécessaires pour respecter temps_max
        # On ajoute +30% pour le deadheading (retours à vide, détours CPP)
        if temps_max and h_estime > 0:
            n_vehicules = int(np.ceil((h_estime * 1.3) / temps_max))
        else:
            n_vehicules = 1

        # Si on a besoin de plusieurs véhicules et qu'on peut encore subdiviser
        if n_vehicules > 1 and len(groupe) > 1 and profondeur < 8:
            sous = subdiviser(G, groupe, n_vehicules)
            if len(sous) > 1:
                for s in sous:
                    traiter(s, profondeur + 1)
                return

        # ── On lance le CPP sur ce groupe ──────────────────────────────────
        _chrono.debut("cpp_oriente (appel)")
        seq, dist_m = cpp_oriente(G, groupe, depot)
        _chrono.fin("cpp_oriente (appel)")
        km = dist_m / 1000
        h, cout, detail = cout_tournee(km)

        # Si malgré tout le CPP dépasse (deadheading > 30%), on re-subdivise
        if temps_max and h > temps_max and len(groupe) > 1 and profondeur < 8:
            facteur = int(np.ceil(h / temps_max))
            sous = subdiviser(G, groupe, facteur)
            if len(sous) > 1:
                for s in sous:
                    traiter(s, profondeur + 1)
                return

        resultats.append(Tournee(depot, compteur[0], groupe, seq, km, h, cout, detail))
        compteur[0] += 1

    _chrono.debut("planifier_secteur")
    traiter(aretes, 0)
    _chrono.fin("planifier_secteur")
    return resultats


@dataclass
class Resultat:
    tournees: list
    nb_deneigeuses: int
    cout_total: float
    duree_max_h: float
    distance_totale_km: float
    ok: bool
    messages: list = field(default_factory=list)


def executer(G, depots, temps_max=None, cout_max=None):
    _chrono.debut("partitionner (executer)")
    secteurs = partitionner(G, depots)
    _chrono.fin("partitionner (executer)")

    tournees = []
    for depot, aretes in secteurs.items():
        print(f"  → Secteur {depot} : {len(aretes)} arêtes…")
        tournees.extend(planifier_secteur(G, depot, aretes, temps_max))

    cout  = sum(t.cout_total for t in tournees)
    duree = max((t.duree_h for t in tournees), default=0.0)
    dist  = sum(t.distance_km for t in tournees)
    msgs, ok = [], True

    if temps_max and duree > temps_max:
        ok = False
        msgs.append(f"[NON RESPECTÉ] durée {duree:.2f} h > {temps_max:.2f} h")
    if cout_max and cout > cout_max:
        ok = False
        msgs.append(f"[NON RESPECTÉ] coût {cout:.2f} $ > {cout_max:.2f} $")

    return Resultat(tournees, len(tournees), cout, duree, dist, ok, msgs)


def afficher_rapport(r):
    print("=" * 70)
    print(f"Déneigeuseuses : {r.nb_deneigeuses}   |   "
          f"Distance : {r.distance_totale_km:.1f} km   |   "
          f"Durée max : {r.duree_max_h:.2f} h   |   "
          f"Coût total : {r.cout_total:.2f} $")
    print(f"Contraintes : {'✓' if r.ok else '✗'}")
    for m in r.messages:
        print(m)
    print("-" * 70)
    print(f"{'Dépôt':<15}{'ID':<6}{'km':<10}{'h':<8}{'coût $':<10}")
    for t in sorted(r.tournees, key=lambda t: (t.depot, t.id)):
        print(f"{t.depot:<15}{t.id:<6}{t.distance_km:<10.2f}{t.duree_h:<8.2f}{t.cout_total:<10.2f}")
    print("=" * 70)


def exporter_json(r, chemin):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump({
            "nb_deneigeuses":     r.nb_deneigeuses,
            "cout_total":         r.cout_total,
            "duree_max_h":        r.duree_max_h,
            "distance_totale_km": r.distance_totale_km,
            "ok":                 r.ok,
            "messages":           r.messages,
            "tournees": [{
                "depot":        t.depot,
                "id":           t.id,
                "nb_rues":      len(t.aretes),
                "distance_km":  t.distance_km,
                "duree_h":      t.duree_h,
                "cout_total":   t.cout_total,
                "cout_fixe":    t.detail_cout[0],
                "cout_km":      t.detail_cout[1],
                "cout_horaire": t.detail_cout[2],
                "sequence":     t.sequence,
            } for t in r.tournees]
        }, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Config & main
# ---------------------------------------------------------------------------

CHEMIN_GRAPHE = "verdun.graphml"
COUT_MAX      = None
EXPORT_JSON   = "resultat.json"


def suggerer_depots(G, n, max_iter=30):
    """
    Trouve N dépôts qui équilibrent le nombre d'arêtes par secteur.

    Algorithme : k-means pondéré par les arêtes (coordonnées = milieu de chaque arête).
    Chaque centroïde est recalculé comme le barycentre des arêtes de son cluster,
    puis snapé sur le nœud du graphe le plus proche — ce qui garantit
    ~E/N arêtes par dépôt plutôt qu'une simple répartition spatiale.

    Paramètres
    ----------
    G        : nx.DiGraph
    n        : int   — nombre de dépôts souhaités
    max_iter : int   — iterations k-means (30 suffisent en pratique)

    Retourne
    --------
    list[str]  — node_id des N dépôts sélectionnés
    """
    if n <= 0:
        return []

    nodes  = list(G.nodes())
    coords = np.array([[G.nodes[nd]["lat"], G.nodes[nd]["lon"]] for nd in nodes])
    node_tree = cKDTree(coords)

    aretes_p1 = [(u, v) for u, v in G.edges() if G.edges[u, v].get("priorite", 3) == 1]
    
    # Fallback de sécurité : si aucune arête P1 n'est trouvée (ex: bug de tag), on prend tout
    if not aretes_p1:
        print("    [Alerte] Aucune arête P1 trouvée, placement des dépôts sur l'ensemble du graphe.")
        aretes_p1 = list(G.edges())

    milieux = np.array([
        [(G.nodes[u]["lat"] + G.nodes[v]["lat"]) / 2,
         (G.nodes[u]["lon"] + G.nodes[v]["lon"]) / 2]
        for u, v in aretes_p1
    ])

    # Initialisation : k-means++ pour éviter les clusters déséquilibrés dès le départ
    rng = np.random.default_rng(42)
    centres = [milieux[rng.integers(len(milieux))]]
    for _ in range(n - 1):
        d2 = np.min(
            np.linalg.norm(milieux[:, None] - np.array(centres)[None, :], axis=2),
            axis=1
        ) ** 2
        proba = d2 / d2.sum()
        if proba.sum() == 0:
            centres.append(milieux[rng.choice(rng.integers(len(milieux)), p=proba)])
        else:
            centres.append(milieux[rng.choice(len(milieux), p=proba)])
    centres = np.array(centres)

    # Itérations k-means
    labels = np.zeros(len(milieux), dtype=int)
    for _ in range(max_iter):
        # Assignation : chaque arête → centroïde le plus proche
        dists = np.linalg.norm(milieux[:, None] - centres[None, :], axis=2)
        new_labels = np.argmin(dists, axis=1)

        if np.all(new_labels == labels):
            break
        labels = new_labels

        # Mise à jour : nouveau centroïde = barycentre des arêtes du cluster
        for k in range(n):
            masque = labels == k
            if masque.any():
                centres[k] = milieux[masque].mean(axis=0)

    # Snap chaque centroïde sur le nœud du graphe le plus proche
    depots = []
    utilises = set()
    for k in range(n):
        _, voisins = node_tree.query(centres[k], k=min(20, len(nodes)))
        if isinstance(voisins, (int, np.integer)):
            voisins = [voisins]
        for j in voisins:
            if j not in utilises:
                utilises.add(j)
                depots.append(nodes[j])
                break

    return depots


def estimer_depot(G, lat, lon):
    """
    Retourne le nœud du graphe le plus proche des coordonnées (lat, lon) données,
    ainsi que la distance en degrés (approximation rapide) et en mètres (haversine).

    Paramètres
    ----------
    G   : nx.DiGraph — graphe chargé par charger_graphe()
    lat : float      — latitude du point de référence
    lon : float      — longitude du point de référence

    Retourne
    --------
    dict avec les clés :
        node_id     — identifiant du nœud candidat
        lat, lon    — coordonnées de ce nœud
        dist_deg    — distance euclidienne en degrés
        dist_m      — distance haversine en mètres (plus précise)
    """
    nodes  = list(G.nodes())
    coords = np.array([[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in nodes])

    # Recherche du plus proche voisin (espace lat/lon, rapide)
    tree = cKDTree(coords)
    dist_deg, idx = tree.query([lat, lon])
    node_id = nodes[idx]
    n_lat   = G.nodes[node_id]["lat"]
    n_lon   = G.nodes[node_id]["lon"]

    # Distance haversine pour une valeur en mètres
    R = 6_371_000  # rayon terrestre en mètres
    phi1, phi2 = np.radians(lat),   np.radians(n_lat)
    dphi       = np.radians(n_lat - lat)
    dlam       = np.radians(n_lon  - lon)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    dist_m = 2 * R * np.arcsin(np.sqrt(a))

    return {
        "node_id":  node_id,
        "lat":      n_lat,
        "lon":      n_lon,
        "dist_deg": float(dist_deg),
        "dist_m":   float(dist_m),
    }


def _etape(label, t0):
    """Affiche une ligne de log formatée avec le temps écoulé."""
    dt = time.perf_counter() - t0
    print(f"  [{dt:6.2f}s]  {label}")


def construire_scenario_geometrique(G, coords_hopitaux, nb_quartiers_denses=3):
    """
    Crée un scénario 1 basé sur la géométrie : relie des POIs manuels
    aux quartiers les plus denses du graphe.
    """
    print("\n  [Génération] Construction géométrique du Scénario 1...")
    
    # Étape 1 : Initialiser tout le graphe en Priorité 3 (résidentiel par défaut)
    for u, v in G.edges():
        G[u][v]["priorite"] = 3

    # Étape 2 : Snapper les hôpitaux sur le graphe
    noeuds_hopitaux = []
    for lat, lon in coords_hopitaux:
        noeud = estimer_depot(G, lat, lon)["node_id"]
        noeuds_hopitaux.append(noeud)
        
    # Étape 3 : Trouver les centres des "quartiers denses" 
    # On réutilise ton algorithme K-means qui converge vers les zones denses en arêtes
    centres_denses = suggerer_depots(G, nb_quartiers_denses)
    
    # Étape 4 : Tracer les routes vitales (Priorité 1) via Dijkstra
    aretes_p1 = set()
    for hopital in noeuds_hopitaux:
        for centre in centres_denses:
            # Dijkstra_path est déjà dans ton code
            chemin = _dijkstra_path(G, hopital, centre)
            if chemin:
                # Marquer chaque segment du chemin en Priorité 1
                for i in range(len(chemin) - 1):
                    u, v = chemin[i], chemin[i+1]
                    if G.has_edge(u, v):
                        G[u][v]["priorite"] = 1
                        aretes_p1.add((u, v))
                        
    print(f"  -> {len(noeuds_hopitaux)} hôpitaux reliés à {len(centres_denses)} centres denses.")
    print(f"  -> {len(aretes_p1)} arêtes marquées en Priorité 1.")

def main():
    T_GLOBAL = time.perf_counter()
    SEP  = "═" * 72
    SEP2 = "─" * 72

    # ── 1. Chargement ──────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  ÉTAPE 1 / 3  —  Chargement du graphe")
    print(SEP2)
    t = time.perf_counter()
    G = charger_graphe(CHEMIN_GRAPHE)
    
    hopitaux_coords = [(45.495, -73.578)]  # Hôpital de Verdun
    construire_scenario_geometrique(G, hopitaux_coords, nb_quartiers_denses=3)
    
    _etape(f"{G.number_of_nodes()} nœuds  |  {G.number_of_edges()} arcs", t)

    # ── 2. Sélection des dépôts (scénarios 1 / 3 / 10) ────────────────────
    print(f"\n{SEP}")
    print("  ÉTAPE 2 / 3  —  Sélection optimale des dépôts (k-center greedy)")
    print(SEP2)

    scenarios_depots = [1, 3, 5]
    depots_par_n = {}

    

    for n in scenarios_depots:
        t = time.perf_counter()
        depots = suggerer_depots(G, n)
        depots_par_n[n] = depots
        _etape(f"{n} dépôt(s)  →  {depots}", t)

    # ── 3. Solveur CPP — croisement (N dépôts) × (temps max) ──────────────
    print(f"\n{SEP}")
    print("  ÉTAPE 3 / 3  —  Solveur CPP  ×  scénarios")
    print(SEP2)

    scenarios_temps = [12.0, 8.0, 5.0]

    # Tableau des résultats : clé = (n_depots, tmax)
    tous_resultats = {}

    for n, depots in depots_par_n.items():
        for tmax in scenarios_temps:
            label = f"{n} dépôt(s), tmax={tmax:.0f}h"
            print(f"\n  ┌─ {label} {'─' * max(0, 50 - len(label))}┐")
            t = time.perf_counter()

            r = executer(G, depots, temps_max=tmax, cout_max=COUT_MAX)
            tous_resultats[(n, tmax)] = r

            ok_str = "✓ OK" if r.ok else "✗ NON RESPECTÉ"
            _etape(
                f"{r.nb_deneigeuses} tournées  |  {r.distance_totale_km:.1f} km  "
                f"|  {r.duree_max_h:.2f} h  |  {r.cout_total:.2f} $  |  {ok_str}",
                t,
            )

            if EXPORT_JSON:
                chemin = EXPORT_JSON.replace(".json", f"_{n}depots_{int(tmax)}h.json")
                exporter_json(r, chemin)
                print(f"          → export : {chemin}")

    # ── Tableau comparatif final ───────────────────────────────────────────
    print(f"\n{SEP}")
    print("  RÉCAPITULATIF GLOBAL")
    print(SEP2)
    print(f"  {'Dépôts':>7}  {'Tmax h':>7}  {'Tournées':>9}  {'Dist km':>9}  "
          f"{'Durée h':>8}  {'Coût $':>10}  {'OK':>4}")
    print(f"  {SEP2}")
    for (n, tmax), r in sorted(tous_resultats.items()):
        ok_str = "✓" if r.ok else "✗"
        print(
            f"  {n:>7}  {tmax:>7.0f}  {r.nb_deneigeuses:>9}  "
            f"{r.distance_totale_km:>9.1f}  {r.duree_max_h:>8.2f}  "
            f"{r.cout_total:>10.2f}  {ok_str:>4}"
        )

    # ── Rapport de performance interne ────────────────────────────────────
    _chrono.rapport()

    _etape("TOTAL GLOBAL", T_GLOBAL)
    print()


if __name__ == "__main__":
    main()
