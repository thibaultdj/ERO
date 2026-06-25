import json
import xml.etree.ElementTree as ET
import requests
from collections import defaultdict

GRAPHML_PATH = "Montreal.graphml"
RESULTAT_PATH = "resultat.json"
OUTPUT_PATH = "fiches.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

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

def fetch_street_names(node_ids):
    ids_str = ",".join(node_ids)
    query = f"""
[out:json][timeout:60];
node(id:{ids_str});
way(bn)["highway"]["name"];
out body;
"""
    r = requests.post(OVERPASS_URL, data={"data": query},
                      headers={"User-Agent": "snow-route/1.0"}, timeout=90)
    r.raise_for_status()
    data = r.json()

    node_to_streets = defaultdict(set)
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
    main()
