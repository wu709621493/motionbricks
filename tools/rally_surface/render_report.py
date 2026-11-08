"""Optional plot/CSV export: requires matplotlib; never needed by the model."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--png", action="store_true", help="also write a raster preview")
    args = parser.parse_args()
    result = json.loads(args.results.read_text(encoding="utf-8"))
    if result["evidence"] != "SYNTHETIC_UNCALIBRATED":
        raise ValueError("this report layout is only for the synthetic study")
    rows = result["cases"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "rally_surface_cases.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["evidence", *rows[0]])
        writer.writeheader()
        writer.writerows({"evidence": result["evidence"], **row} for row in rows)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({"font.size": 10, "svg.hashsalt": "rally-surface-v1"})
    route = "bayinbuluke_fictional_surrogate"
    names = [s["name"] for s in result["inputs"]["surfaces"]]
    labels = ["Bare mud*", "Loose sack", "Anchored mat", "Gravel", "Buried fabric\n+ gravel", "Asphalt"]
    def select(name, passes=0, routing=0):
        return next(r for r in rows if r["route"] == route and r["surface"] == name
                    and r["weather"] == "wet" and r["previous_passes"] == passes
                    and r["protected_routing_fraction"] == routing)
    x = np.arange(len(names))
    fig, axes = plt.subplots(3, 1, figsize=(11, 11), layout="constrained")
    fig.suptitle("Rally surface screening | SYNTHETIC, UNCALIBRATED\n"
                 "Bayinbuluke-scale surrogate: wet scenario, fixed 8 m/s demand", fontsize=15)
    axes[0].bar(x-.18, [select(n)["minimum_mu"] for n in names], .36,
                label="Fresh", color="#287f8e")
    axes[0].bar(x+.18, [select(n, 100)["minimum_mu"] for n in names], .36,
                label="100 prior passes (assumed wear)", color="#cf8c42")
    axes[0].set_ylabel("Force capacity / normal load")
    axes[0].set_title("A  |  Traction limits; bearing is a separate screen", loc="left")
    axes[0].legend(loc="upper left", ncols=2)
    axes[0].set_ylim(0, 1)
    axes[1].bar(x-.18, [select(n)["unprotected_runoff_m3_per_km"] for n in names], .36,
                label="No protected routing", color="#596e9c")
    axes[1].bar(x+.18, [select(n, routing=.9)["unprotected_runoff_m3_per_km"] for n in names], .36,
                label="90% routed to assumed protected outlets", color="#77a88e")
    axes[1].set_ylabel("Unprotected runoff (m³/km/event)")
    axes[1].set_title("B  |  Water is routed, not removed from the water balance", loc="left")
    axes[1].legend(loc="upper left")
    axes[1].set_ylim(0, 220)
    axes[2].bar(x-.18, [select(n)["road_detachment_index_per_km"] for n in names], .36,
                label="Fresh", color="#287f8e")
    axes[2].bar(x+.18, [select(n, 100)["road_detachment_index_per_km"] for n in names], .36,
                label="100 prior passes", color="#cf8c42")
    axes[2].set_ylabel("Road detachment proxy / km")
    axes[2].set_title("C  |  Assumed material availability; no sediment mass calibration", loc="left")
    axes[2].legend(loc="upper right")
    for ax in axes:
        ax.set_xticks(x, labels)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
    fig.supxlabel("* Bare mud exceeds assumed bearing capacity throughout this wet scenario.\n"
                  "Parameters are illustrative; bars do not establish real material rankings or safe speeds.",
                  fontsize=10)
    fig.savefig(args.output_dir / "rally_surface_comparison.svg", metadata={"Date": None})
    if args.png:
        fig.savefig(args.output_dir / "rally_surface_comparison.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
