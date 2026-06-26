import io
import time
import numpy as np

import config
from config import (
    VITESSE_KMH, DEPOTS_OPTIMAUX, TMAX_OPTIMAL, POPULATION_DENSITE,
    SCENARIO_LABELS, SCENARIO_POI, DENSITE_COORDS,
)
from graphe import charger_graphe, noeud_le_plus_proche
from cpp import _dijkstra_path
from scenarios import construire_corridors, construire_hierarchie_routiere
from depots import suggerer_depots
from planification import executer, cout_depot_jour
from pipeline import exporter_json
from fiche_de_tournee import generer_fiches


def _calculer_chemins_corridors(G, poi_coords, dense_coords):
    noeuds_poi   = [noeud_le_plus_proche(G, lat, lon) for lat, lon in poi_coords]
    noeuds_dense = [noeud_le_plus_proche(G, lat, lon) for lat, lon in dense_coords]

    chemins = []
    for poi in noeuds_poi:
        for dense_idx, dense in enumerate(noeuds_dense):
            chemin = _dijkstra_path(G, poi, dense)
            if chemin:
                aretes = [
                    (chemin[i], chemin[i + 1])
                    for i in range(len(chemin) - 1)
                    if G.has_edge(chemin[i], chemin[i + 1])
                ]
                if aretes:
                    chemins.append((aretes, dense_idx))

    return chemins, len(noeuds_dense)

def _simuler_clearing_times(tournees, G):
    clearing = {}
    for t in tournees:
        cumul_h = 0.0
        for u, v in zip(t.sequence[:-1], t.sequence[1:]):
            lng = G[u][v].get("length", 0.0) if G.has_edge(u, v) else 0.0
            cumul_h += (lng / 1000.0) / VITESSE_KMH
            if G.has_edge(u, v) and (u, v) not in clearing:
                clearing[(u, v)] = cumul_h
    return clearing

def _analyser_impact_population(clearing_times, chemins, n_zones, populations):
    corridor_times = []
    for aretes, dense_idx in chemins:
        t_max = max(clearing_times.get((u, v), float("inf")) for u, v in aretes)
        if t_max < float("inf"):
            corridor_times.append((t_max, dense_idx))

    zone_access = {}
    for t, dense_idx in corridor_times:
        if dense_idx not in zone_access or t < zone_access[dense_idx]:
            zone_access[dense_idx] = t

    return zone_access, corridor_times

def _afficher_impact(out, clearing_s1, clearing_s0, chemins, n_zones, populations, label_sc):
    SEP = "─" * 78

    zone_access_s1, corridor_times_s1 = _analyser_impact_population(
        clearing_s1, chemins, n_zones, populations)
    zone_access_s0, corridor_times_s0 = _analyser_impact_population(
        clearing_s0, chemins, n_zones, populations)

    pop_totale    = sum(populations)
    n_corridors   = len(corridor_times_s1)

    def p90(corridor_times):
        if not corridor_times:
            return float("inf")
        vals = sorted(t for t, _ in corridor_times)
        return float(np.percentile(vals, 90))

    p90_s1 = p90(corridor_times_s1)
    p90_s0 = p90(corridor_times_s0)

    jalons = [1, 2, 4, 6, 8, 12]

    out("")
    out(f"  [Impact population — {label_sc}]")
    out(f"  Population totale : {pop_totale:,} hab.  |  "
        f"{n_zones} zones denses  |  {n_corridors} corridors S1")
    out("")
    out(f"  {'Temps':>6}  {'Zones S1':>14}  {'Population S1':>18}  "
        f"{'Corridors S1':>14}  {'Corridors S0':>14}")
    out(f"  {SEP}")

    for h in jalons:
        zones_s1 = sum(1 for z, t in zone_access_s1.items() if t <= h)
        pop_s1   = sum(populations[z] for z, t in zone_access_s1.items() if t <= h)
        corr_s1  = sum(1 for t, _ in corridor_times_s1 if t <= h)
        corr_s0  = sum(1 for t, _ in corridor_times_s0 if t <= h)

        pct_zones = zones_s1 / n_zones * 100 if n_zones else 0
        pct_pop   = pop_s1 / pop_totale * 100 if pop_totale else 0
        pct_c_s1  = corr_s1 / n_corridors * 100 if n_corridors else 0
        pct_c_s0  = corr_s0 / n_corridors * 100 if n_corridors else 0

        out(f"  {h:>4}h  "
            f"  {zones_s1}/{n_zones} ({pct_zones:4.0f}%)  "
            f"  {pop_s1:>7,} ({pct_pop:4.0f}%)  "
            f"  {corr_s1:>4}/{n_corridors} ({pct_c_s1:4.0f}%)  "
            f"  {corr_s0:>4}/{n_corridors} ({pct_c_s0:4.0f}%)")

    out(f"  {SEP}")

    gain     = p90_s0 - p90_s1
    gain_pct = gain / p90_s0 * 100 if p90_s0 else 0
    out(f"  P90 corridors S1  : {p90_s1:.2f}h")
    out(f"  P90 corridors S0  : {p90_s0:.2f}h  (mêmes nombre de dépôts, sans priorisation)")
    gain_str = f"−{gain:.2f}h (−{gain_pct:.0f}%)" if gain > 0 else f"+{-gain:.2f}h (+{-gain_pct:.0f}%)"
    out(f"  Gain P90          : {gain_str}")

def _afficher_impact_hierarchie(out, clearing_s3, clearing_s0, priorite_orig, km_par_priorite, G, label_sc):
    SEP = "─" * 78

    def km_degage(clearing, priorite, h):
        return sum(
            G[u][v]["length"] / 1000
            for (u, v), t in clearing.items()
            if t <= h and priorite_orig.get((u, v), 3) == priorite
        )

    jalons = [1, 2, 4, 6, 8, 12]

    out("")
    out(f"  [Impact hiérarchie routière — {label_sc}]")
    out(f"  Artères : {km_par_priorite[1]:.1f} km  |  "
        f"Collectrices : {km_par_priorite[2]:.1f} km  |  "
        f"Locales : {km_par_priorite[3]:.1f} km")
    out("")
    out(f"  {'Temps':>6}  {'Artères S3':>12}  {'Artères S0':>12}  "
        f"{'Collect. S3':>12}  {'Collect. S0':>12}")
    out(f"  {SEP}")

    for h in jalons:
        tot1, tot2 = km_par_priorite[1], km_par_priorite[2]
        pct1_s3 = km_degage(clearing_s3, 1, h) / tot1 * 100 if tot1 else 0
        pct1_s0 = km_degage(clearing_s0, 1, h) / tot1 * 100 if tot1 else 0
        pct2_s3 = km_degage(clearing_s3, 2, h) / tot2 * 100 if tot2 else 0
        pct2_s0 = km_degage(clearing_s0, 2, h) / tot2 * 100 if tot2 else 0
        out(f"  {h:>4}h  "
            f"  {pct1_s3:>10.0f}%  "
            f"  {pct1_s0:>10.0f}%  "
            f"  {pct2_s3:>10.0f}%  "
            f"  {pct2_s0:>10.0f}%")

    out(f"  {SEP}")

    def p90(clearing, priorite):
        vals = sorted(t for (u, v), t in clearing.items() if priorite_orig.get((u, v), 3) == priorite)
        return float(np.percentile(vals, 90)) if vals else float("inf")

    p90_s3 = p90(clearing_s3, 1)
    p90_s0 = p90(clearing_s0, 1)
    gain     = p90_s0 - p90_s3
    gain_pct = gain / p90_s0 * 100 if p90_s0 else 0
    gain_str = f"−{gain:.2f}h (−{gain_pct:.0f}%)" if gain > 0 else f"+{-gain:.2f}h (+{-gain_pct:.0f}%)"
    out(f"  P90 artères S3    : {p90_s3:.2f}h")
    out(f"  P90 artères S0    : {p90_s0:.2f}h  (mêmes nombre de dépôts, sans priorisation)")
    out(f"  Gain P90          : {gain_str}")

def _fmt_config_vehicules(tournees, n_depots):
    from collections import Counter
    veh_par_depot = Counter(t.depot for t in tournees)
    freq = Counter(veh_par_depot.values())
    parties = [f"{nb_dep}x{nb_veh}" for nb_veh, nb_dep in sorted(freq.items(), reverse=True)]
    return " / ".join(parties)

def mode_demo(sector, scenario_num, nb_depots=None, avec_fiches=False):
    T0 = time.perf_counter()

    buf = io.StringIO()

    def out(line=""):
        print(line)
        buf.write(line + "\n")

    SEP  = "=" * 70
    SEP2 = "─" * 70

    label_sc = SCENARIO_LABELS[scenario_num]
    out(SEP)
    out(f"  Scénario {scenario_num} — {label_sc}")
    out(f"  Secteur : {sector.capitalize()}   |   Tmax = {TMAX_OPTIMAL:.0f}h")
    out(SEP)

    config._VERBOSE = False

    G = charger_graphe(f"{sector}.graphml")
    if scenario_num == 3:
        construire_hierarchie_routiere(G)
    else:
        construire_corridors(
            G,
            poi_coords   = SCENARIO_POI[scenario_num].get(sector, []),
            dense_coords = DENSITE_COORDS.get(sector, []),
        )

    n_depots = nb_depots if nb_depots is not None else DEPOTS_OPTIMAUX[sector]
    depots   = suggerer_depots(G, n_depots)
    r        = executer(G, depots, temps_max=TMAX_OPTIMAL)
    config._VERBOSE = True

    cout_ope   = r.cout_total
    cout_depot = cout_depot_jour(n_depots)
    cout_total = cout_ope + cout_depot
    config_veh = _fmt_config_vehicules(r.tournees, n_depots)

    COL = [18, 10, 22, 14, 18, 18]
    header = ["Arrondissement", "Dépôts", "Dépôts×Déneigeuses", "Durée max", "Prix opé ($)", "Prix total ($)"]
    sep_row = "  " + "  ".join("─" * c for c in COL)

    out("")
    out("  " + "  ".join(h.ljust(COL[i]) for i, h in enumerate(header)))
    out(sep_row)

    arr_label   = sector.capitalize()
    duree_str   = f"{r.duree_max_h:.2f}h"
    prix_ope    = f"{cout_ope:,.2f} $".replace(",", " ")
    prix_total  = f"{cout_total:,.2f} $".replace(",", " ")

    row = [arr_label, str(n_depots), config_veh, duree_str, prix_ope, prix_total]
    out("  " + "  ".join(v.ljust(COL[i]) for i, v in enumerate(row)))
    out(sep_row)

    if scenario_num == 3:
        priorite_orig   = {(u, v): G[u][v].get("priorite", 3) for u, v in G.edges()}
        km_par_priorite = {1: 0.0, 2: 0.0, 3: 0.0}
        for (u, v), p in priorite_orig.items():
            km_par_priorite[p] += G[u][v]["length"] / 1000

        clearing_s3 = _simuler_clearing_times(r.tournees, G)

        config._VERBOSE = False
        for u, v in G.edges():
            G[u][v]["priorite"] = 3
        depots_s0 = suggerer_depots(G, n_depots)
        r_s0      = executer(G, depots_s0, temps_max=TMAX_OPTIMAL)
        config._VERBOSE = True
        clearing_s0 = _simuler_clearing_times(r_s0.tournees, G)

        _afficher_impact_hierarchie(out, clearing_s3, clearing_s0, priorite_orig, km_par_priorite, G, label_sc)
    else:
        poi_coords   = SCENARIO_POI[scenario_num].get(sector, [])
        dense_coords = DENSITE_COORDS.get(sector, [])
        populations  = POPULATION_DENSITE.get(sector, [])

        chemins, n_zones = _calculer_chemins_corridors(G, poi_coords, dense_coords)

        clearing_s1 = _simuler_clearing_times(r.tournees, G)

        config._VERBOSE = False
        for u, v in G.edges():
            G[u][v]["priorite"] = 3
        depots_s0 = suggerer_depots(G, n_depots)
        r_s0      = executer(G, depots_s0, temps_max=TMAX_OPTIMAL)
        config._VERBOSE = True
        clearing_s0 = _simuler_clearing_times(r_s0.tournees, G)

        _afficher_impact(out, clearing_s1, clearing_s0, chemins, n_zones, populations, label_sc)

    elapsed = time.perf_counter() - T0
    out(f"\n  Temps d'exécution : {elapsed:.1f}s")

    nom_txt  = f"demo_{sector}_s{scenario_num}.txt"
    nom_json = f"demo_{sector}_s{scenario_num}.json"

    with open(nom_txt, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    print(f"  → Résultat sauvegardé : {nom_txt}")

    exporter_json(r, nom_json)
    print(f"  → JSON sauvegardé    : {nom_json}")

    if avec_fiches:
        nom_fiches = nom_json.replace(".json", "_fiches.json")
        print(f"  → récupération des noms de rues (Overpass)...")
        generer_fiches(G, r, nom_fiches)
        print(f"  → Fiches sauvegardées : {nom_fiches}")
