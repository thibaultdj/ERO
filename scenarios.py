import numpy as np
import networkx as nx

import config
from graphe import noeud_le_plus_proche
from cpp import _dijkstra_path


def construire_corridors(G, poi_coords, dense_coords):
    for u, v in G.edges():
        G[u][v]["priorite"] = 3

    if not poi_coords or not dense_coords:
        print(f"    [Alerte] Listes vides — toutes les arêtes restent P3")
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

    if config._VERBOSE:
        print(f"    {len(noeuds_poi)} POIs × {len(noeuds_dense)} zones denses "
              f"→ {len(aretes_p1)} arêtes P1 marquées")

def _centralite_aretes(G):
    n = G.number_of_nodes()
    k = min(300, n) if n > 1500 else None
    config._chrono.debut("centralite_aretes")
    bet = nx.edge_betweenness_centrality(G, k=k, weight="length", seed=42)
    config._chrono.fin("centralite_aretes")
    return bet

def construire_hierarchie_routiere(G):
    degres  = dict(G.degree())
    deg_max = max(degres.values()) if degres else 1

    bet     = _centralite_aretes(G)
    bet_max = max(bet.values()) if bet else 0.0

    scores = {}
    for u, v in G.edges():
        deg_score = ((degres[u] + degres[v]) / 2) / deg_max if deg_max else 0.0
        bet_score = (bet.get((u, v), 0.0) / bet_max) if bet_max else 0.0
        scores[(u, v)] = 0.5 * bet_score + 0.5 * deg_score

    valeurs  = np.array(list(scores.values()))
    seuil_p1 = np.percentile(valeurs, config.SEUIL_PERCENTILE_P1)
    seuil_p2 = np.percentile(valeurs, config.SEUIL_PERCENTILE_P2)

    n1 = n2 = n3 = 0
    for (u, v), s in scores.items():
        if s >= seuil_p1:
            G[u][v]["priorite"] = 1
            n1 += 1
        elif s >= seuil_p2:
            G[u][v]["priorite"] = 2
            n2 += 1
        else:
            G[u][v]["priorite"] = 3
            n3 += 1

    if config._VERBOSE:
        print(f"    Hiérarchie routière : {n1} artères (P1) | "
              f"{n2} collectrices (P2) | {n3} locales (P3)")
