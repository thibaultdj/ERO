import numpy as np
from scipy.spatial import cKDTree


def _aretes_reference(G):
    aretes_p1 = [(u, v) for u, v in G.edges() if G.edges[u, v].get("priorite", 3) == 1]
    if aretes_p1:
        return aretes_p1

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

