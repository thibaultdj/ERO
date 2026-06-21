import argparse
import io
import json
import sys
import time
import numpy as np
import networkx as nx
from dataclasses import dataclass, field
from scipy.spatial import cKDTree


# ── Constantes ────────────────────────────────────────────────────────────────

COUT_FIXE_JOUR      = 500.0
COUT_PAR_KM         = 1.1
COUT_HORAIRE_NORMAL = 1.1
COUT_HORAIRE_SUPP   = 1.3
SEUIL_H             = 8.0
VITESSE_KMH         = 10.0

COUT_MAX    = None
EXPORT_JSON = "resultat.json"

# ── POIs par arrondissement ────────────────────────────────────────────────────
# Scénario 1 — Services de santé (hôpitaux, CLSC, cliniques)
HOPITAUX_COORDS = {
    "verdun": [
        (45.4637363, -73.5637627),  # Hôpital de Verdun
        (45.4424837, -73.5860219),  # Institut Douglas
        (45.4627389, -73.5691148),  # CLSC de Verdun
        (45.4600730, -73.5761585),  # Clinique médicale du Sud-Ouest
        (45.4627800, -73.5645142),  # Clinique Médico-chirurgicale de Verdun
        (45.4637974, -73.5641022),  # Clinique universitaire CIUSSS
    ],
    "outremont": [
        (45.5219,    -73.6139),     # CLSC Côte-des-Neiges
        (45.5205,    -73.6089),     # Clinique medix
    ],
    "anjou": [
        (45.6044719, -73.5474560),  # Résidence Anjou
        (45.6060612, -73.5887727),  # Résidence Anjou sur le Lac
        (45.6173831, -73.5477261),  # Centre Le Royer
        (45.5959405, -73.5574116),  # Résidence Les Terrasses Versailles
        (45.6143060, -73.5461589),  # Manoir Anjou
        (45.6046656, -73.5526852),  # Uniprix
        (45.6067135, -73.5849121),  # Brunet
        (45.6119058, -73.5548945),  # Pharmacie Jean-Coutu
    ],
    "rdp": [
        (45.6446480, -73.5858812),  # CLSC de Rivière-des-Prairies
        (45.6664093, -73.4934196),  # CLSC de l'Est-de-Montréal
        (45.6210548, -73.6092505),  # Maison alternative RDP
        (45.6160837, -73.6039035),  # Centre d'hébergement Marie-Victorin
        (45.6196838, -73.6051302),  # Pavillon Montfort
        (45.6338141, -73.4928495),  # CHSLD Bourget
        (45.6524839, -73.4884323),  # Centre Le Cardinal
        (45.6448714, -73.5747314),  # Résidence Lionel-Bourdon
    ],
}

# Scénario 2 — Centres commerciaux et supermarchés
COMMERCES_COORDS = {
    "verdun": [
        (45.4630146, -73.5693087),  # Fruiterie Soleil
        (45.4644196, -73.5670048),  # Bulk Barn
        (45.4514650, -73.5724283),  # Marché Tondreau
        (45.4572232, -73.5719943),  # Marché C&C
        (45.4596360, -73.5674360),  # Épicerie LOCO
        (45.4553257, -73.5760819),  # IGA
        (45.4715854, -73.5623140),  # Maxi
        (45.4700904, -73.5634310),  # Canadian Tire
        (45.4623792, -73.5641510),  # Metro
    ],
    "outremont": [
        (45.5194351, -73.5949644),  # PA Nature Supermarché
        (45.5243446, -73.6116384),  # Motty's
        (45.5205138, -73.5986816),  # Supermarché PA du Parc
        (45.5225184, -73.6025278),  # Lipa's
        (45.5232428, -73.6049766),  # Épicerie Mile-End
        (45.5206461, -73.6078241),  # Maxi
    ],
    "anjou": [
        (45.6071188, -73.5848209),  # Metro
        (45.6046037, -73.5515273),  # Metro
        (45.6108868, -73.5776256),  # Mayrand Entrepôt
        (45.6096018, -73.5833026),  # Giant Tiger
        (45.5980400, -73.5676298),  # Halles d'Anjou
        (45.5991693, -73.5597550),  # Marché Adonis
    ],
    "rdp": [
        (45.6692647, -73.5069473),  # Metro
        (45.6534038, -73.5093758),  # Maxi
        (45.6552596, -73.5116643),  # Super C
        (45.6274108, -73.5979569),  # Maxi
        (45.6415101, -73.5025591),  # Metro
        (45.6540402, -73.5130665),  # Walmart
    ],
}

# Zones à forte densité de population (recensement StatCan 2021)
DENSITE_COORDS = {
    "verdun": [
        (45.4662, -73.5665),  # Boul. Wellington / centre commercial
        (45.4635, -73.5700),  # Rue Wellington / Verdun centre
        (45.4600, -73.5760),  # Ave Monk / quartier dense
        (45.4540, -73.5770),  # Rue Dupuis / sud Verdun
    ],
    "outremont": [
        (45.5220, -73.6050),  # Ave Laurier Outremont
        (45.5195, -73.6020),  # Ave Bernard / cœur Outremont
        (45.5160, -73.6010),  # Ave Van Horne
        (45.5230, -73.6130),  # Chemin Côte-Sainte-Catherine
        (45.5100, -73.6150),  # Ave Ducharme / sud Outremont
    ],
    "anjou": [
        (45.6050, -73.5600),  # Boul. des Roseraies / centre Anjou
        (45.6100, -73.5700),  # Boul. Joseph-Renaud
        (45.6150, -73.5500),  # Boul. Métropolitain / nord Anjou
        (45.5980, -73.5500),  # Ave Beaumont / sud Anjou
        (45.6200, -73.5700),  # Boul. Maurice-Duplessis
        (45.6080, -73.5850),  # Boul. Ray-Lawson
    ],
    "rdp": [
        (45.6300, -73.6050),  # Boul. Perras / RDP ouest dense
        (45.6400, -73.5800),  # Boul. Lacordaire / RDP centre
        (45.6500, -73.5600),  # Boul. Maurice-Duplessis
        (45.6600, -73.5400),  # Rue Sherbrooke Est
        (45.6650, -73.5100),  # Boul. Saint-Jean-Baptiste / PAT
        (45.6750, -73.5000),  # Ave Dubuisson / Pointe-aux-Trembles
    ],
}

# Mapping graphml → clé POI
GRAPHES = {
    "montreal.graphml":  "montreal",
 #   "verdun.graphml":    "verdun",
  #  "outremont.graphml": "outremont",
   # "anjou.graphml":     "anjou",
   # "rdp.graphml":       "rdp",
}


# ── Chronomètre ───────────────────────────────────────────────────────────────

class Chrono:
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


_chrono  = Chrono()
_VERBOSE = True


# ── Dataclasses ───────────────────────────────────────────────────────────────

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


@dataclass
class Resultat:
    tournees: list
    nb_deneigeuses: int
    cout_total: float
    duree_max_h: float
    distance_totale_km: float
    ok: bool
    messages: list = field(default_factory=list)


# ── Graphe ────────────────────────────────────────────────────────────────────

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


def noeud_le_plus_proche(G, lat, lon):
    nodes  = list(G.nodes())
    coords = np.array([[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in nodes])
    _, idx = cKDTree(coords).query([lat, lon])
    return nodes[idx]


# ── Scénarios ─────────────────────────────────────────────────────────────────

def construire_corridors(G, poi_coords, dense_coords):
    """
    Marque en P1 les arêtes sur les plus courts chemins entre chaque POI
    (hôpital, commerce) et chaque zone à forte densité de population.

    Étapes :
      1. Remet toutes les arêtes en priorité 3 (reset propre entre scénarios)
      2. Snappe chaque coordonnée sur le nœud routier le plus proche
      3. Trace le chemin Dijkstra POI → zone dense et marque en P1

    poi_coords   : list[(lat, lon)] — services de santé ou commerces
    dense_coords : list[(lat, lon)] — zones à forte densité de population
    label        : nom affiché dans les logs
    """
    # Reset priorités
    for u, v in G.edges():
        G[u][v]["priorite"] = 3

    if not poi_coords or not dense_coords:
        print(f"    [Alerte] Liste vide pour {label} — toutes les arêtes restent P3")
        return

    noeuds_poi   = [noeud_le_plus_proche(G, lat, lon) for lat, lon in poi_coords]
    noeuds_dense = [noeud_le_plus_proche(G, lat, lon) for lat, lon in dense_coords]

    aretes_p1 = set()
    for poi in noeuds_poi:
        for dense in noeuds_dense:
            chemin = _dijkstra_path(G, poi, dense)
            if chemin:
                for u, v in zip(chemin[:-1], chemin[1:]):
                    if G.has_edge(u, v):
                        G[u][v]["priorite"] = 1
                        aretes_p1.add((u, v))

    if _VERBOSE:
        print(f"    {len(noeuds_poi)} POIs × {len(noeuds_dense)} zones denses "
              f"→ {len(aretes_p1)} arêtes P1 marquées")


# ── Dépôts ────────────────────────────────────────────────────────────────────

def _aretes_reference(G):
    aretes_p1 = [(u, v) for u, v in G.edges() if G.edges[u, v].get("priorite", 3) == 1]
    if aretes_p1:
        return aretes_p1

    # Pas de P1 : on garde seulement les arêtes sur des nœuds bien connectés
    # (degré >= percentile 75) pour éviter que les dépôts tombent en périphérie
    degrees   = dict(G.degree())
    seuil_deg = np.percentile(list(degrees.values()), 75)
    aretes_ax = [(u, v) for u, v in G.edges() if degrees[u] >= seuil_deg and degrees[v] >= seuil_deg]
    return aretes_ax if aretes_ax else list(G.edges())


def suggerer_depots(G, n, max_iter=30):
    if n <= 0:
        return []

    nodes     = list(G.nodes())
    coords    = np.array([[G.nodes[nd]["lat"], G.nodes[nd]["lon"]] for nd in nodes])
    node_tree = cKDTree(coords)

    aretes_ref = _aretes_reference(G)

    milieux = np.array([
        [(G.nodes[u]["lat"] + G.nodes[v]["lat"]) / 2,
         (G.nodes[u]["lon"] + G.nodes[v]["lon"]) / 2]
        for u, v in aretes_ref
    ])

    rng     = np.random.default_rng(42)
    centres = [milieux[rng.integers(len(milieux))]]
    for _ in range(n - 1):
        d2    = np.min(np.linalg.norm(milieux[:, None] - np.array(centres)[None, :], axis=2), axis=1) ** 2
        proba = d2 / d2.sum() if d2.sum() > 0 else None
        centres.append(milieux[rng.choice(len(milieux), p=proba)])
    centres = np.array(centres)

    labels = np.zeros(len(milieux), dtype=int)
    for _ in range(max_iter):
        dists      = np.linalg.norm(milieux[:, None] - centres[None, :], axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.all(new_labels == labels):
            break
        labels = new_labels
        for k in range(n):
            masque = labels == k
            if masque.any():
                centres[k] = milieux[masque].mean(axis=0)

    depots, utilises = [], set()
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


# ── CPP ───────────────────────────────────────────────────────────────────────

def _dijkstra_path(G, src, dst):
    try:
        return nx.dijkstra_path(G, src, dst, weight="length")
    except nx.NetworkXNoPath:
        return None


def _ajouter_chemin(G, M, path):
    for a, b in zip(path[:-1], path[1:]):
        if a != b:
            M.add_edge(a, b, length=G[a][b]["length"])


def _rendre_fortement_connexe(G, M, depot):
    _chrono.debut("connexite")
    for _ in range(200):
        sccs      = list(nx.strongly_connected_components(M))
        if len(sccs) == 1:
            break
        scc_depot = next(c for c in sccs if depot in c)
        progres   = False
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
    for _ in range(50):
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
        tree       = cKDTree(coords_dfc)
        utilises   = set()

        for src in exc:
            coord = np.array([G.nodes[src]["lat"], G.nodes[src]["lon"]])
            _, voisins = tree.query(coord, k=min(len(dfc), 20))
            if isinstance(voisins, (int, np.integer)):
                voisins = [voisins]
            for j in voisins:
                if j in utilises:
                    continue
                dst = dfc[j]
                if dst not in noeuds_M or dst == src:
                    continue
                path = _dijkstra_path(G, src, dst)
                if path:
                    _ajouter_chemin(G, M, path)
                    utilises.add(j)
                    break
    _chrono.fin("equilibrage")


def circuit_eulerien(M, source):
    _chrono.debut("circuit_eulerien")
    adj = {u: [] for u in M.nodes()}
    for u, v, data in M.edges(data=True):
        if u != v:
            adj[u].append((v, data.get("length", 0.0)))

    stack, circuit = [source], []
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
    dist    = sum(
        G[circuit[i]][circuit[i + 1]]["length"]
        for i in range(len(circuit) - 1)
        if G.has_edge(circuit[i], circuit[i + 1])
    )
    return circuit, dist


# ── Planification ─────────────────────────────────────────────────────────────

def cout_tournee(distance_km):
    h   = distance_km / VITESSE_KMH
    km  = distance_km * COUT_PAR_KM
    hor = (h * COUT_HORAIRE_NORMAL if h <= SEUIL_H
           else SEUIL_H * COUT_HORAIRE_NORMAL + (h - SEUIL_H) * COUT_HORAIRE_SUPP)
    return h, COUT_FIXE_JOUR + km + hor, (COUT_FIXE_JOUR, km, hor)


def subdiviser(G, aretes, nb, max_iter=15):
    if nb <= 1 or len(aretes) <= 1:
        return [aretes]
    nb = min(nb, len(aretes))

    milieux = np.array([
        [(G.nodes[u]["lat"] + G.nodes[v]["lat"]) / 2,
         (G.nodes[u]["lon"] + G.nodes[v]["lon"]) / 2]
        for u, v in aretes
    ])

    # Init k-means++ pour des clusters compacts dès le départ
    rng     = np.random.default_rng(0)
    centres = [milieux[rng.integers(len(milieux))]]
    for _ in range(nb - 1):
        d2    = np.min(np.linalg.norm(milieux[:, None] - np.array(centres)[None, :], axis=2), axis=1) ** 2
        total = d2.sum()
        proba = d2 / total if total > 0 else None
        centres.append(milieux[rng.choice(len(milieux), p=proba)])
    centres = np.array(centres)

    labels = np.zeros(len(milieux), dtype=int)
    for _ in range(max_iter):
        dists      = np.linalg.norm(milieux[:, None] - centres[None, :], axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.all(new_labels == labels):
            break
        labels = new_labels
        for k in range(nb):
            masque = labels == k
            if masque.any():
                centres[k] = milieux[masque].mean(axis=0)

    groupes = []
    for k in range(nb):
        g = [aretes[i] for i, l in enumerate(labels) if l == k]
        if g:
            groupes.append(g)
    return groupes if len(groupes) > 1 else [aretes]


def planifier_secteur(G, depot, aretes, temps_max):
    if not aretes:
        return []
    resultats = []
    compteur  = [0]

    def traiter(groupe, profondeur):
        dist_km  = sum(G[u][v]["length"] for u, v in groupe) / 1000
        h_estime = dist_km / VITESSE_KMH
        n_veh    = int(np.ceil((h_estime * 1.3) / temps_max)) if temps_max and h_estime > 0 else 1

        if n_veh > 1 and len(groupe) > 1 and profondeur < 8:
            sous = subdiviser(G, groupe, n_veh)
            if len(sous) > 1:
                for s in sous:
                    traiter(s, profondeur + 1)
                return

        _chrono.debut("cpp_oriente (appel)")
        seq, dist_m = cpp_oriente(G, groupe, depot)
        _chrono.fin("cpp_oriente (appel)")
        km = dist_m / 1000
        h, cout, detail = cout_tournee(km)

        if temps_max and h > temps_max and len(groupe) > 1 and profondeur < 8:
            sous = subdiviser(G, groupe, int(np.ceil(h / temps_max)))
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


def partitionner(G, depots):
    _chrono.debut("partitionner")
    for d in depots:
        if d not in G.nodes:
            raise ValueError(f"Dépôt '{d}' introuvable.")

    nodes        = list(G.nodes())
    coords       = np.array([[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in nodes])
    dc           = np.array([[G.nodes[d]["lat"], G.nodes[d]["lon"]] for d in depots])
    dists, idxs  = cKDTree(dc).query(coords)
    nd           = {n: depots[idxs[i]] for i, n in enumerate(nodes)}
    dist         = {n: float(dists[i])  for i, n in enumerate(nodes)}

    secteurs = {d: [] for d in depots}
    for u, v in G.edges():
        d = nd[u] if dist.get(u, float("inf")) <= dist.get(v, float("inf")) else nd[v]
        secteurs[d].append((u, v))

    tailles = [len(v) for v in secteurs.values()]
    mini, maxi = min(tailles), max(tailles)
    ratio = maxi / mini if mini > 0 else float("inf")
    if _VERBOSE:
        print(f"    Secteurs : min={mini}  moy={np.mean(tailles):.0f}  max={maxi}  ratio={ratio:.1f}x")

    _chrono.fin("partitionner")
    return secteurs


def executer(G, depots, temps_max=None, cout_max=None):
    _chrono.debut("partitionner (executer)")
    secteurs = partitionner(G, depots)
    _chrono.fin("partitionner (executer)")

    tournees = []
    for depot, aretes in secteurs.items():
        if _VERBOSE:
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


# ── Affichage & export ────────────────────────────────────────────────────────

def _etape(label, t0):
    print(f"  [{time.perf_counter() - t0:6.2f}s]  {label}")


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


def afficher_recap(tous_resultats):
    SEP  = "═" * 72
    SEP2 = "─" * 72
    print(f"\n{SEP}")
    print("  RÉCAPITULATIF GLOBAL")
    print(SEP2)
    print(f"  {'Dépôts':>7}  {'Tmax h':>7}  {'Tournées':>9}  {'Dist km':>9}  "
          f"{'Durée h':>8}  {'Coût $':>10}  {'OK':>4}")
    print(f"  {SEP2}")
    for (n, tmax), r in sorted(tous_resultats.items()):
        ok_str = "✓" if r.ok else "✗"
        print(f"  {n:>7}  {tmax:>7.0f}  {r.nb_deneigeuses:>9}  "
              f"{r.distance_totale_km:>9.1f}  {r.duree_max_h:>8.2f}  "
              f"{r.cout_total:>10.2f}  {ok_str:>4}")


def lancer_scenarios(G, scenarios_depots, scenarios_temps, tag_export):
    SEP  = "═" * 72
    SEP2 = "─" * 72

    print(f"\n{SEP}")
    print("  ÉTAPE 2 / 3  —  Sélection des dépôts")
    print(SEP2)

    depots_par_n = {}
    for n in scenarios_depots:
        t      = time.perf_counter()
        depots = suggerer_depots(G, n)
        depots_par_n[n] = depots
        _etape(f"{n} dépôt(s)  →  {depots}", t)

    print(f"\n{SEP}")
    print("  ÉTAPE 3 / 3  —  Solveur CPP")
    print(SEP2)

    tous_resultats = {}
    for n, depots in depots_par_n.items():
        for tmax in scenarios_temps:
            label = f"{n} dépôt(s), tmax={tmax:.0f}h"
            print(f"\n  ┌─ {label} {'─' * max(0, 50 - len(label))}┐")
            t = time.perf_counter()
            r = executer(G, depots, temps_max=tmax, cout_max=COUT_MAX)
            tous_resultats[(n, tmax)] = r
            ok_str = "✓ OK" if r.ok else "✗ NON RESPECTÉ"
            _etape(f"{r.nb_deneigeuses} tournées  |  {r.distance_totale_km:.1f} km  "
                   f"|  {r.duree_max_h:.2f} h  |  {r.cout_total:.2f} $  |  {ok_str}", t)
            if EXPORT_JSON:
                chemin = EXPORT_JSON.replace(".json", f"_{tag_export}_{n}depots_{int(tmax)}h.json")
                exporter_json(r, chemin)
                print(f"          → export : {chemin}")

    afficher_recap(tous_resultats)


# ── Main ──────────────────────────────────────────────────────────────────────

SCENARIOS_DEPOTS = [1,3,5,7,10,15,20,30,50, 100]
SCENARIOS_TEMPS  = [12.0, 10.0, 8.0]


def lancement_scenario0(G, cle):
    print(f"\n  ► Scénario 0 — Base (aucune priorisation, référence)")
    # Reset : toutes les arêtes en P3
    for u, v in G.edges():
        G[u][v]["priorite"] = 3
    lancer_scenarios(G, SCENARIOS_DEPOTS, SCENARIOS_TEMPS, tag_export=f"{cle}_s0")


def lancement_scenario1(G, cle):
    print(f"\n  ► Scénario 1 — Accès aux services de santé")
    construire_corridors(
        G,
        poi_coords   = HOPITAUX_COORDS.get(cle, []),
        dense_coords = DENSITE_COORDS.get(cle, []),
    )
    lancer_scenarios(G, SCENARIOS_DEPOTS, SCENARIOS_TEMPS, tag_export=f"{cle}_s1")


def lancement_scenario2(G, cle):
    print(f"\n  ► Scénario 2 — Impact économique (centres commerciaux)")
    construire_corridors(
        G,
        poi_coords   = COMMERCES_COORDS.get(cle, []),
        dense_coords = DENSITE_COORDS.get(cle, []),
    )
    lancer_scenarios(G, SCENARIOS_DEPOTS, SCENARIOS_TEMPS, tag_export=f"{cle}_s2")


def main():
    T_GLOBAL = time.perf_counter()
    SEP      = "═" * 72
    SEP2     = "─" * 72

    for graphml, cle in GRAPHES.items():
        print(f"\n{SEP}")
        print(f"  ARRONDISSEMENT : {cle.upper()}")
        print(SEP2)

        t = time.perf_counter()
        G = charger_graphe(graphml)
        _etape(f"{G.number_of_nodes()} nœuds  |  {G.number_of_edges()} arcs", t)

        lancement_scenario0(G, cle)
#        lancement_scenario1(G, cle)
#        lancement_scenario2(G, cle)

    _chrono.rapport()
    _etape("TOTAL GLOBAL", T_GLOBAL)
    print()


# ── Mode démo CLI ─────────────────────────────────────────────────────────────

DEPOTS_OPTIMAUX = {"verdun": 3, "outremont": 3, "anjou": 3, "rdp": 5}
TMAX_OPTIMAL    = 8.0

SCENARIO_LABELS = {
    1: "Accès aux services de santé",
    2: "Impact économique (centres commerciaux)",
}

SCENARIO_POI = {
    1: HOPITAUX_COORDS,
    2: COMMERCES_COORDS,
}


def _percentile_timing(tournees, G, priorite_cible):
    """Retourne les temps (h) auxquels chaque arête de priorité donnée est déneigée,
    toutes tournées tournant en parallèle depuis t=0."""
    temps_list = []
    for t in tournees:
        seq = t.sequence
        cumul_s = 0.0
        for u, v in zip(seq[:-1], seq[1:]):
            lng = G[u][v].get("length", 0.0) if G.has_edge(u, v) else 0.0
            cumul_s += (lng / 1000.0) / VITESSE_KMH * 3600
            if G.has_edge(u, v) and G[u][v].get("priorite", 3) == priorite_cible:
                temps_list.append(cumul_s / 3600)
    return sorted(temps_list)


def _fmt_pct(vals, nb_aretes):
    if not vals:
        return "—"
    p50 = np.percentile(vals, 50)
    p90 = np.percentile(vals, 90)
    p100 = vals[-1]
    return f"P50={p50:.2f}h, P90={p90:.2f}h, P100={p100:.2f}h  ({nb_aretes} arcs)"


def mode_demo(sector, scenario_num):
    T0     = time.perf_counter()
    SEP1   = "=" * 60
    SEP2   = "─" * 60

    buf = io.StringIO()

    def out(line=""):
        print(line)
        buf.write(line + "\n")

    graphml = f"{sector}.graphml"
    cle     = sector

    out(SEP1)
    out(f"Secteur : {sector.capitalize()}")
    out(SEP1)

    G = charger_graphe(graphml)
    nb_noeuds = G.number_of_nodes()
    nb_arcs   = G.number_of_edges()
    dist_tot  = sum(d.get("length", 0.0) for _, _, d in G.edges(data=True)) / 1000
    noeuds_impairs = sum(
        1 for n in G.nodes()
        if G.out_degree(n) != G.in_degree(n)
    )
    out(f"  Statistiques {sector.capitalize()}: {nb_noeuds} nœuds, {nb_arcs} arcs, "
        f"{dist_tot:.1f} km, {noeuds_impairs} nœuds impairs")

    # Corridors prioritaires + CPP (silencieux)
    global _VERBOSE
    _VERBOSE = False
    poi_dict = SCENARIO_POI[scenario_num]
    construire_corridors(
        G,
        poi_coords   = poi_dict.get(cle, []),
        dense_coords = DENSITE_COORDS.get(cle, []),
    )

    nb_p1 = sum(1 for _, _, d in G.edges(data=True) if d.get("priorite", 3) == 1)
    nb_p3 = nb_arcs - nb_p1

    n_depots  = DEPOTS_OPTIMAUX[cle]
    depots    = suggerer_depots(G, n_depots)
    r         = executer(G, depots, temps_max=TMAX_OPTIMAL)
    _VERBOSE  = True

    dist_circuit = r.distance_totale_km

    out(f"  Véhicules déployés  : {r.nb_deneigeuses}")
    out(f"  Distance totale     : {dist_circuit:.1f} km")
    out(f"  Distance/véhicule   : {dist_circuit / r.nb_deneigeuses:.1f} km")
    duree_moy = sum(t.duree_h for t in r.tournees) / len(r.tournees)
    out(f"  Durée/véhicule      : {duree_moy:.2f} h")

    cout_fixe_tot = sum(t.detail_cout[0] for t in r.tournees)
    cout_km_tot   = sum(t.detail_cout[1] for t in r.tournees)
    cout_hor_tot  = sum(t.detail_cout[2] for t in r.tournees)
    out(f"  Coût fixe           : {cout_fixe_tot:.0f} $")
    out(f"  Coût kilométrique   : {cout_km_tot:.0f} $")
    out(f"  Coût horaire        : {cout_hor_tot:.0f} $")
    out(f"  COÛT TOTAL          : {r.cout_total:.0f} $")

    # Distribution priorités & percentiles
    label_sc = SCENARIO_LABELS[scenario_num]
    out(f"\n[Scénario {scenario_num}] {label_sc}")
    out(f"  Distribution des priorités : P1={nb_p1}, P3={nb_p3}")

    t_p1 = _percentile_timing(r.tournees, G, 1)
    t_p3 = _percentile_timing(r.tournees, G, 3)

    out(f"    P1: {_fmt_pct(t_p1, len(t_p1))}")
    out(f"    P3: {_fmt_pct(t_p3, len(t_p3))}")

    ok_str  = "✓ OK" if r.ok else "✗ NON RESPECTÉ"
    elapsed = time.perf_counter() - T0
    out(f"\n  Contrainte 8h     : {ok_str}")
    out(f"  Temps d'exécution : {elapsed:.1f}s")

    # Sauvegarde txt
    nom_txt = f"demo_{sector}_s{scenario_num}.txt"
    with open(nom_txt, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    print(f"\n  → Résultat sauvegardé : {nom_txt}")

    # Export JSON
    nom_json = f"demo_{sector}_s{scenario_num}.json"
    exporter_json(r, nom_json)
    print(f"  → JSON sauvegardé    : {nom_json}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimisation hivernale Montréal")
    parser.add_argument("--sector",   choices=["verdun", "outremont", "anjou",
                                               "rdp"])
    parser.add_argument("--scenario", type=int, choices=[1, 2])
    args = parser.parse_args()

    if args.sector and args.scenario:
        mode_demo(args.sector, args.scenario)
    else:
        main()
