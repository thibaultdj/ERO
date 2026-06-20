import json
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

CHEMIN_GRAPHE = "verdun.graphml"
COUT_MAX      = None
EXPORT_JSON   = "resultat.json"

HOPITAUX_COORDS = [
    (45.495, -73.578),  # Hôpital de Verdun
]


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


_chrono = Chrono()


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

def appliquer_scenario_base(G):
    for u, v in G.edges():
        G[u][v]["priorite"] = 3


def appliquer_scenario_hopitaux(G, coords_hopitaux, nb_centres=3):
    appliquer_scenario_base(G)

    noeuds_hopitaux = [noeud_le_plus_proche(G, lat, lon) for lat, lon in coords_hopitaux]
    centres         = suggerer_depots(G, nb_centres)

    aretes_p1 = set()
    for hopital in noeuds_hopitaux:
        for centre in centres:
            chemin = _dijkstra_path(G, hopital, centre)
            if chemin:
                for u, v in zip(chemin[:-1], chemin[1:]):
                    if G.has_edge(u, v):
                        G[u][v]["priorite"] = 1
                        aretes_p1.add((u, v))

    print(f"    {len(noeuds_hopitaux)} hôpitaux → {len(centres)} centres  "
          f"|  {len(aretes_p1)} arêtes P1 marquées")


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


def subdiviser(G, aretes, nb):
    if nb <= 1 or len(aretes) <= 1:
        return [aretes]
    nb    = min(nb, len(aretes))
    lats  = [(G.nodes[u]["lat"] + G.nodes[v]["lat"]) / 2 for u, v in aretes]
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
    print(f"    Secteurs : min={mini}  moy={np.mean(tailles):.0f}  max={maxi}  ratio={ratio:.1f}x")

    _chrono.fin("partitionner")
    return secteurs


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

SCENARIOS_DEPOTS = [1, 3, 5]
SCENARIOS_TEMPS  = [12.0, 8.0, 5.0]


def lancement_scenario0(G):
    print("\n  ► Scénario 0 — Base (toutes les rues, priorité uniforme)")
    appliquer_scenario_base(G)
    lancer_scenarios(G, SCENARIOS_DEPOTS, SCENARIOS_TEMPS, tag_export="s0")


def lancement_scenario1(G):
    print("\n  ► Scénario 1 — Prioritisation des hôpitaux")
    appliquer_scenario_hopitaux(G, HOPITAUX_COORDS, nb_centres=3)
    lancer_scenarios(G, SCENARIOS_DEPOTS, SCENARIOS_TEMPS, tag_export="s1")


def main():
    T_GLOBAL = time.perf_counter()
    SEP      = "═" * 72
    SEP2     = "─" * 72

    print(f"\n{SEP}")
    print("  ÉTAPE 1 / 3  —  Chargement du graphe")
    print(SEP2)
    t = time.perf_counter()
    G = charger_graphe(CHEMIN_GRAPHE)
    _etape(f"{G.number_of_nodes()} nœuds  |  {G.number_of_edges()} arcs", t)

    # ── Choisissez les scénarios à lancer ────────────────────────────────────
    lancement_scenario0(G)
    lancement_scenario1(G)
    # ─────────────────────────────────────────────────────────────────────────

    _chrono.rapport()
    _etape("TOTAL GLOBAL", T_GLOBAL)
    print()


if __name__ == "__main__":
    main()
