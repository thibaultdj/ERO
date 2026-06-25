import json
import time

import config
from config import (
    COUT_MAX, EXPORT_JSON, GRAPHES, SCENARIOS_DEPOTS, SCENARIOS_TEMPS,
    HOPITAUX_COORDS, COMMERCES_COORDS, DENSITE_COORDS,
)
from graphe import charger_graphe
from scenarios import construire_corridors, construire_hierarchie_routiere
from depots import suggerer_depots
from planification import executer


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

def lancement_scenario0(G, cle):
    print(f"\n  ► Scénario 0 — Base (aucune priorisation, référence)")

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

def lancement_scenario3(G, cle):
    print(f"\n  ► Scénario 3 — Hiérarchie routière (artères → collectrices → locales)")
    construire_hierarchie_routiere(G)
    lancer_scenarios(G, SCENARIOS_DEPOTS, SCENARIOS_TEMPS, tag_export=f"{cle}_s3")

def main(graphdemo=None):
    T_GLOBAL = time.perf_counter()
    SEP      = "═" * 72
    SEP2     = "─" * 72

    if graphdemo == None:
        for graphml, cle in GRAPHES.items():
            print(f"\n{SEP}")
            print(f"  ARRONDISSEMENT : {cle.upper()}")
            print(SEP2)

            t = time.perf_counter()
            G = charger_graphe(graphml)
            _etape(f"{G.number_of_nodes()} nœuds  |  {G.number_of_edges()} arcs", t)

            lancement_scenario0(G, cle)
    else:
        print(f"\n{SEP}")
        print(f"  ARRONDISSEMENT : {graphdemo.upper()}")
        print(SEP2)

        t = time.perf_counter()
        G = charger_graphe(graphdemo + ".graphml")
        _etape(f"{G.number_of_nodes()} nœuds  |  {G.number_of_edges()} arcs", t)

        cle = GRAPHES.get(graphdemo, "demo")
        lancement_scenario0(G, cle)

    config._chrono.rapport()
    _etape("TOTAL GLOBAL", T_GLOBAL)
    print()
