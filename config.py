import time

COUT_FIXE_JOUR      = 500.0
COUT_PAR_KM         = 1.1
COUT_HORAIRE_NORMAL = 1.1
COUT_HORAIRE_SUPP   = 1.3
SEUIL_H             = 8.0
VITESSE_KMH         = 10.0

JOURS_SAISON_DENEIGEMENT = 120

COUT_MAX    = None
EXPORT_JSON = "resultat.json"

HOPITAUX_COORDS = {
    "verdun": [
        (45.4637363, -73.5637627),
        (45.4424837, -73.5860219),
        (45.4627389, -73.5691148),
        (45.4600730, -73.5761585),
        (45.4627800, -73.5645142),
        (45.4637974, -73.5641022),
    ],
    "outremont": [
        (45.5219,    -73.6139),
        (45.5205,    -73.6089),
    ],
    "anjou": [
        (45.6044719, -73.5474560),
        (45.6060612, -73.5887727),
        (45.6173831, -73.5477261),
        (45.5959405, -73.5574116),
        (45.6143060, -73.5461589),
        (45.6046656, -73.5526852),
        (45.6067135, -73.5849121),
        (45.6119058, -73.5548945),
    ],
    "rdp": [
        (45.6446480, -73.5858812),
        (45.6664093, -73.4934196),
        (45.6210548, -73.6092505),
        (45.6160837, -73.6039035),
        (45.6196838, -73.6051302),
        (45.6338141, -73.4928495),
        (45.6524839, -73.4884323),
        (45.6448714, -73.5747314),
    ],
}

COMMERCES_COORDS = {
    "verdun": [
        (45.4630146, -73.5693087),
        (45.4644196, -73.5670048),
        (45.4514650, -73.5724283),
        (45.4572232, -73.5719943),
        (45.4596360, -73.5674360),
        (45.4553257, -73.5760819),
        (45.4715854, -73.5623140),
        (45.4700904, -73.5634310),
        (45.4623792, -73.5641510),
    ],
    "outremont": [
        (45.5194351, -73.5949644),
        (45.5243446, -73.6116384),
        (45.5205138, -73.5986816),
        (45.5225184, -73.6025278),
        (45.5232428, -73.6049766),
        (45.5206461, -73.6078241),
    ],
    "anjou": [
        (45.6071188, -73.5848209),
        (45.6046037, -73.5515273),
        (45.6108868, -73.5776256),
        (45.6096018, -73.5833026),
        (45.5980400, -73.5676298),
        (45.5991693, -73.5597550),
    ],
    "rdp": [
        (45.6692647, -73.5069473),
        (45.6534038, -73.5093758),
        (45.6552596, -73.5116643),
        (45.6274108, -73.5979569),
        (45.6415101, -73.5025591),
        (45.6540402, -73.5130665),
    ],
}

DENSITE_COORDS = {
    "verdun": [
        (45.4662, -73.5665),
        (45.4635, -73.5700),
        (45.4600, -73.5760),
        (45.4540, -73.5770),
    ],
    "outremont": [
        (45.5220, -73.6050),
        (45.5195, -73.6020),
        (45.5160, -73.6010),
        (45.5230, -73.6130),
        (45.5100, -73.6150),
    ],
    "anjou": [
        (45.6050, -73.5600),
        (45.6100, -73.5700),
        (45.6150, -73.5500),
        (45.5980, -73.5500),
        (45.6200, -73.5700),
        (45.6080, -73.5850),
    ],
    "rdp": [
        (45.6300, -73.6050),
        (45.6400, -73.5800),
        (45.6500, -73.5600),
        (45.6600, -73.5400),
        (45.6650, -73.5100),
        (45.6750, -73.5000),
    ],
}

GRAPHES = {
    "montreal.graphml":  "montreal",
    "verdun.graphml":    "verdun",
    "outremont.graphml": "outremont",
    "anjou.graphml":     "anjou",
    "rdp.graphml":       "rdp",
}

SCENARIOS_DEPOTS = [1,2,3,5,6,7,10]
SCENARIOS_TEMPS  = [12.0]

DEPOTS_OPTIMAUX = {"verdun": 1, "outremont": 1, "anjou": 1, "rdp": 2}
TMAX_OPTIMAL    = 12.0

POPULATION_DENSITE = {
    "verdun":    [18_000, 16_000, 14_000, 21_000],
    "outremont": [ 6_000,  7_000,  5_000,  4_000,  3_000],
    "anjou":     [ 8_000,  7_000,  6_000,  8_000,  7_000,  6_000],
    "rdp":       [18_000, 20_000, 17_000, 16_000, 19_000, 16_000],
}

SCENARIO_LABELS = {
    0: "Base (aucune priorisation)",
    1: "Accès aux services de santé",
    2: "Impact économique (centres commerciaux)",
    3: "Hiérarchie routière (artères → collectrices → locales)",
}

SCENARIO_POI = {
    1: HOPITAUX_COORDS,
    2: COMMERCES_COORDS,
}


SEUIL_PERCENTILE_P1 = 88
SEUIL_PERCENTILE_P2 = 60

class Chrono:
    def __init__(self):
        self._debut_global = time.perf_counter()
        self._etapes: dict[str, float] = {}
        self._en_cours: dict[str, float] = {}
        self._appels: dict[str, int] = {}

    def debut(self, etape: str):
        self._en_cours[etape] = time.perf_counter()

    def fin(self, etape: str):
        if etape in self._en_cours:
            elapsed = time.perf_counter() - self._en_cours.pop(etape)
            self._etapes[etape] = self._etapes.get(etape, 0.0) + elapsed
            self._appels[etape] = self._appels.get(etape, 0) + 1

    def rapport(self):
        total = time.perf_counter() - self._debut_global
        print("\n" + "─" * 60)
        print(f"{'ÉTAPE':<35} {'TEMPS':>8}  {'APPELS':>7}")
        print("─" * 60)
        for etape, t in sorted(self._etapes.items(), key=lambda x: -x[1]):
            nb = self._appels.get(etape, 1)
            print(f"  {etape:<33} {t:>7.2f}s  {nb:>7}")
        print("─" * 60)
        print(f"  {'TOTAL GLOBAL':<33} {total:>7.2f}s")
        print("─" * 60 + "\n")

_chrono  = Chrono()
_VERBOSE = True

