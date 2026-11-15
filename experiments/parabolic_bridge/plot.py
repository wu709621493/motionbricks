"""Rebuild the scientific SVG; optional matplotlib, no runtime dependency change."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from model import ParabolicBridge


def main():
    output = Path(__file__).resolve().parents[2]/"docs/research/parabolic_bridge/energy_profiles.svg"
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.8), sharex=True)
    fields = ("epsilon_over_Q", "p_radial_over_Q", "radial_NEC_over_Q")
    titles = (r"Energy density $\varepsilon/Q$", r"Radial pressure $p_r/Q$",
              r"Radial NEC $(\varepsilon+p_r)/Q$")
    colors = ("#9e3b5a", "#cb8030", "#287a93", "#493ca0")
    for ratio, color in zip((0.25, 0.5, 1, 2), colors):
        rows = ParabolicBridge(1, ratio).sample(count=241)
        for ax, field in zip(axes, fields):
            ax.plot([r["r_over_a"] for r in rows], [r[field] for r in rows],
                    color=color, lw=2, label=f"f/a = {ratio:g}")
    for ax, title in zip(axes, titles):
        ax.set_title(title, fontsize=11)
        ax.set_xlabel(r"Areal radius $r/a$")
        ax.axhline(0, color="#535b65", lw=0.7)
        ax.grid(alpha=0.18)
        ax.set_xlim(1, 5)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle("Parabolic bridge: exact static GR source", fontsize=14, y=0.98)
    fig.text(0.5, 0.02, "Q = c^4/(8 pi G a^2). Prescribed geometry; formation and matter realization untested.",
             ha="center", fontsize=9, color="#535b65")
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    with matplotlib.rc_context({"svg.hashsalt": "parabolic-bridge-v1"}):
        fig.savefig(output, metadata={"Date": None})
    # Scratch review image; the repository deliverable is the reproducible SVG.
    fig.savefig("/tmp/parabolic_bridge_review.png", dpi=150)
    plt.close(fig)
    print(output)


if __name__ == "__main__":
    main()
