import numpy as np
import networkx as nx
from scipy.spatial import cKDTree

import config


def charger_graphe(chemin):
    config._chrono.debut("charger_graphe")
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
            G.add_edge(v, u, length=lng,deadhead=True)
    config._chrono.fin("charger_graphe")
    return G

def noeud_le_plus_proche(G, lat, lon):
    nodes  = list(G.nodes())
    coords = np.array([[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in nodes])
    _, idx = cKDTree(coords).query([lat, lon])
    return nodes[idx]
