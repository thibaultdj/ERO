import argparse

from pipeline import main as lancer_pipeline
from demo import mode_demo

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimisation hivernale Montréal")
    parser.add_argument("--sector",   choices=["verdun", "outremont", "anjou",
                                               "rdp","montreal"])
    parser.add_argument("--scenario", type=int, choices=[0, 1, 2, 3])
    parser.add_argument("--nb_depots", type=int, help="Nombre de dépôts à considérer")
    parser.add_argument("--fiches", action="store_true",
                         help="Génère aussi un JSON des tournées avec les noms de rues "
                              "(requiert une connexion internet, API Overpass)")
    args = parser.parse_args()

    if args.sector and args.scenario is not None:
        if args.scenario == 0:
            lancer_pipeline(graphdemo=args.sector, nb_depots=args.nb_depots, avec_fiches=args.fiches)
        else:
            mode_demo(args.sector, args.scenario, nb_depots=args.nb_depots, avec_fiches=args.fiches)
    else:
        lancer_pipeline(avec_fiches=args.fiches)
