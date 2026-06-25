import json
import time
import xml.etree.ElementTree as ET
import requests
from collections import defaultdict
import argparse


OUTPUT_PATH = "fiches.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
CHUNK_SIZE = 400
MAX_ESSAIS = 4

def load_nodes(path):
    NS = "{http://graphml.graphdrawing.org/xmlns}"
    tree = ET.parse(path)
    root = tree.getroot()
    nodes = {}
    for node in root.iter(NS + "node"):
        nid = node.get("id")
        lat = lon = None
        for d in node:
            if d.get("key") == "d0": lat = float(d.text)
            if d.get("key") == "d1": lon = float(d.text)
        nodes[nid] = (lat, lon)
    return nodes

def _interroger_overpass(ids_chunk):
    ids_str = ",".join(ids_chunk)
    query = f"""
[out:json][timeout:60];
node(id:{ids_str});
way(bn)["highway"]["name"];
out body;
"""
    derniere_erreur = None
    for essai in range(MAX_ESSAIS):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query},
                              headers={"User-Agent": "snow-route/1.0"}, timeout=90)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} {r.reason}", response=r)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            derniere_erreur = e
            if essai < MAX_ESSAIS - 1:
                time.sleep(3 * (essai + 1))
    print(f"    [Alerte] Overpass indisponible pour {len(ids_chunk)} nœuds "
          f"après {MAX_ESSAIS} essais ({derniere_erreur}) — noms laissés à '(inconnue)'")
    return {"elements": []}

def fetch_street_names(node_ids):
    node_to_streets = defaultdict(set)

    for i in range(0, len(node_ids), CHUNK_SIZE):
        chunk = node_ids[i:i + CHUNK_SIZE]
        data = _interroger_overpass(chunk)
        for elem in data.get("elements", []):
            if elem["type"] == "way":
                name = elem.get("tags", {}).get("name")
                if name:
                    for nid in elem.get("nodes", []):
                        node_to_streets[str(nid)].add(name)

    return {nid: sorted(node_to_streets.get(nid, {"(inconnue)"})) for nid in node_ids}

def street_for_edge(u, v, cache):
    common = set(cache.get(u, [])) & set(cache.get(v, []))
    if common:
        return sorted(common)[0]
    return cache.get(u, ["(inconnue)"])[0]

def get_ordered_streets(sequence, cache):
    streets = []
    for i in range(len(sequence) - 1):
        rue = street_for_edge(sequence[i], sequence[i+1], cache)
        if not streets or streets[-1] != rue:
            streets.append(rue)
    return streets

def generer_fiches(G, resultat, chemin_sortie=None):
    """Construit les fiches de tournée (avec noms de rues) directement depuis
    un graphe networkx déjà chargé et un objet Resultat déjà calculé,
    sans repasser par les fichiers JSON/GraphML sur disque."""
    all_node_ids = set()
    for t in resultat.tournees:
        all_node_ids.update(t.sequence)

    cache = fetch_street_names([str(n) for n in all_node_ids])

    fiches = []
    for t in resultat.tournees:
        seq = t.sequence
        depart_lat = G.nodes[seq[0]]["lat"] if seq else None
        depart_lon = G.nodes[seq[0]]["lon"] if seq else None
        fiches.append({
            "vehicule": t.id + 1,
            "depart": {
                "lat": depart_lat,
                "lon": depart_lon
            },
            "nb_rues": len(t.aretes),
            "distance_km": round(t.distance_km, 2),
            "duree_h": round(t.duree_h, 2),
            "rues": get_ordered_streets(seq, cache)
        })

    if chemin_sortie:
        with open(chemin_sortie, "w", encoding="utf-8") as f:
            json.dump(fiches, f, ensure_ascii=False, indent=2)

    return fiches

def main():
    nodes = load_nodes(GRAPHML_PATH)

    with open(RESULTAT_PATH) as f:
        data = json.load(f)

    all_node_ids = set()
    for t in data["tournees"]:
        all_node_ids.update(t["sequence"])

    print(f"Récupération des noms pour {len(all_node_ids)} nœuds...")
    cache = fetch_street_names(list(all_node_ids))

    fiches = []
    for t in data["tournees"]:
        seq = t["sequence"]
        depart_coords = nodes.get(seq[0], (None, None))
        fiches.append({
            "vehicule": t["id"] + 1,
            "depart": {
                "lat": depart_coords[0],
                "lon": depart_coords[1]
            },
            "nb_rues": t["nb_rues"],
            "distance_km": round(t["distance_km"], 2),
            "duree_h": round(t["duree_h"], 2),
            "rues": get_ordered_streets(seq, cache)
        })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fiches, f, ensure_ascii=False, indent=2)

    print(f"Fiches enregistrées dans {OUTPUT_PATH}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Génération des fiches de tournée")
    parser.add_argument("--graphml", type=str, help="Chemin vers le fichier GraphML")
    parser.add_argument("--resultat", type=str, help="Chemin vers le fichier JSON des résultats")
    if parser.parse_args().resultat is not None and parser.parse_args().resultat != "":
        RESULTAT_PATH = parser.parse_args().resultat
        GRAPHML_PATH = parser.parse_args().graphml
        main()
    else:
        print("Erreur : le chemin vers le fichier JSON des résultats doit être fourni avec --resultat")
