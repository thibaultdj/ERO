import osmnx as ox
import networkx as nx

DISTRICTS = {
    "outremont": "Outremont, Montréal, Québec, Canada",
    "verdun":    "Verdun, Montréal, Québec, Canada",
    "anjou":     "Anjou, Montréal, Québec, Canada",
    "rdp":       "Rivière-des-Prairies-Pointe-aux-Trembles, Montréal, Québec, Canada",
    "montreal":  "Montréal, Québec, Canada",
}

for name, place in DISTRICTS.items():
    print(f"Téléchargement : {name}")
    G_raw = ox.graph_from_place(place, network_type="drive")

    G = nx.DiGraph()

    for node, data in G_raw.nodes(data=True):
        G.add_node(node, lat=data["y"], lon=data["x"])
 
    for u, v, key, data in G_raw.edges(keys=True, data=True):
        G.add_edge(u, v, key=key, length=data.get("length", 0))

    total_km = sum(d["length"] for _, _, d in G.edges(data=True)) / 1000

    nx.write_graphml(G, f"{name}.graphml")

print("Terminé.")
