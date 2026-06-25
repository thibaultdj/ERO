import numpy as np
import networkx as nx
from scipy.spatial import cKDTree

import config


def _dijkstra_path(G, src, dst):
    try:
        return nx.dijkstra_path(G, src, dst, weight="length")
    except nx.NetworkXNoPath:
        return None

def _ajouter_chemin(G, M, path):
    for a, b in zip(path[:-1], path[1:]):
        if a != b:
            M.add_edge(a, b,
            length=G[a][b]["length"],deadhead=G[a][b].get("deadhead",False), priorite=G[a][b].get("priorite", 3))

def _rendre_fortement_connexe(G, M, depot):
    config._chrono.debut("connexite")
    for _ in range(200):
        sccs      = list(nx.strongly_connected_components(M))
        if len(sccs) == 1:
            break
        scc_depot = next(c for c in sccs if depot in c)
        progres   = False
        for scc in sccs:
            if scc is scc_depot:
                continue
            rep = min(scc)
            for src, dst in [(depot, rep), (rep, depot)]:
                path = _dijkstra_path(G, src, dst)
                if path:
                    _ajouter_chemin(G, M, path)
                    progres = True
        if not progres:
            break
    config._chrono.fin("connexite")

def _equilibrer(G, M):
    config._chrono.debut("equilibrage")
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
    config._chrono.fin("equilibrage")

def circuit_eulerien(M, source):
    config._chrono.debut("circuit_eulerien")
    adj = {u: [] for u in M.nodes()}
    for u, v, data in M.edges(data=True):
        if u != v:
            adj[u].append((v, data.get("priorite", 3)))

    for u in adj:
        adj[u].sort(key=lambda x: x[1], reverse=True)

    stack, circuit = [source], []
    while stack:
        u = stack[-1]
        if adj[u]:
            v, _ = adj[u].pop()
            stack.append(v)
        else:
            circuit.append(stack.pop())

    circuit.reverse()
    config._chrono.fin("circuit_eulerien")
    return circuit

def cpp_oriente(G, aretes, depot):
    M = nx.MultiDiGraph()
    for u, v in aretes:
        M.add_edge(u, v, length=G[u][v]["length"],deadhead=False, priorite=G[u][v].get("priorite", 3))
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
