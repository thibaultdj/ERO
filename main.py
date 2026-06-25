import argparse

from pipeline import main as lancer_pipeline
from demo import mode_demo

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimisation hivernale Montréal")
    parser.add_argument("--sector",   choices=["verdun", "outremont", "anjou",
                                               "rdp","montreal"])
    parser.add_argument("--scenario", type=int, choices=[0, 1, 2, 3])
    args = parser.parse_args()

    if args.sector and args.scenario is not None:
        if args.scenario == 0:
            lancer_pipeline(graphdemo=args.sector)
        else:
            mode_demo(args.sector, args.scenario)
    else:
        lancer_pipeline()
