import math
import numpy as np
from dataclasses import dataclass, field
from scipy.spatial import cKDTree

import config
from config import (
    VITESSE_KMH, COUT_PAR_KM, COUT_HORAIRE_NORMAL, COUT_HORAIRE_SUPP,
    SEUIL_H, COUT_FIXE_JOUR, JOURS_SAISON_DENEIGEMENT,
)
from cpp import cpp_oriente


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

def cout_tournee(distance_km):
    h   = distance_km / VITESSE_KMH
    km  = distance_km * COUT_PAR_KM
    hor = (h * COUT_HORAIRE_NORMAL if h <= SEUIL_H
           else SEUIL_H * COUT_HORAIRE_NORMAL + (h - SEUIL_H) * COUT_HORAIRE_SUPP)
    return h, COUT_FIXE_JOUR + km + hor, (COUT_FIXE_JOUR, km, hor)

def cout_depot_jour(n):
    surface      = 30 * n + 15 * math.sqrt(n)
    construction = surface * 1050
    amort        = construction / (30 * JOURS_SAISON_DENEIGEMENT)
    maintenance  = 500 / JOURS_SAISON_DENEIGEMENT
    return amort + maintenance * n

def subdiviser(G, aretes, nb, max_iter=15):
    if nb <= 1 or len(aretes) <= 1:
        return [aretes]
    nb = min(nb, len(aretes))

    milieux = np.array([
        [(G.nodes[u]["lat"] + G.nodes[v]["lat"]) / 2,
         (G.nodes[u]["lon"] + G.nodes[v]["lon"]) / 2]
        for u, v in aretes
    ])

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

        config._chrono.debut("cpp_oriente (appel)")
        seq, dist_m = cpp_oriente(G, groupe, depot)
        config._chrono.fin("cpp_oriente (appel)")
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

    config._chrono.debut("planifier_secteur")
    traiter(aretes, 0)
    config._chrono.fin("planifier_secteur")
    return resultats

def partitionner(G, depots):
    config._chrono.debut("partitionner")
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
    if config._VERBOSE:
        print(f"    Secteurs : min={mini}  moy={np.mean(tailles):.0f}  max={maxi}  ratio={ratio:.1f}x")

    config._chrono.fin("partitionner")
    return secteurs

def executer(G, depots, temps_max=None, cout_max=None):
    config._chrono.debut("partitionner (executer)")
    secteurs = partitionner(G, depots)
    config._chrono.fin("partitionner (executer)")

    tournees = []
    for depot, aretes in secteurs.items():
        if config._VERBOSE:
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
