"""Export the stoichiometric cathode screen as standalone PNG and SVG figures."""

import argparse
import csv
import json
from fractions import Fraction
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path(__file__).parent / "results")
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.hashsalt": "materials-agent-toolkit-oxyfluoride-screen-v1",
        }
    )
    summary = json.loads((args.results / "summary.json").read_text())
    with (args.results / "candidates.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    nomination = summary["nominated_candidate"]
    if nomination is None:
        raise ValueError("This figure requires a nominated screening candidate")
    selected = nomination["nominal"]
    best_margin = summary["highest_nominal_margin_candidate"]
    controls = summary["controls"]
    nb_control = next(
        row for row in controls if row["ti_grid_count"] == 0 and row["nb_grid_count"] == 20
    )
    ti_control = next(
        row for row in controls if row["ti_grid_count"] == 30 and row["nb_grid_count"] == 0
    )
    capacity_field = "ideal_capacity_mAh_g"
    capacity_gate = summary["screen"]["ideal_capacity_min_mAh_g"]
    nb_gate = 100 * summary["screen"]["nb_mass_fraction_max"]
    nb_percent = [100 * float(row["mass_fraction_Nb"]) for row in rows]
    capacities = [float(row[capacity_field]) for row in rows]
    feasible = [row for row in rows if row["feasible"] == "True"]

    figure, (left, right) = plt.subplots(
        1, 2, figsize=(14.2, 6.2), gridspec_kw={"width_ratios": [1.5, 1]}, layout="constrained"
    )
    left.add_patch(
        Rectangle((0, capacity_gate), nb_gate, 40, color="#e8f3eb", alpha=0.85, zorder=0)
    )
    scatter = left.scatter(
        nb_percent,
        capacities,
        c=[float(row["ti_fraction"]) for row in rows],
        cmap="viridis",
        vmin=0,
        vmax=0.5,
        s=20,
        linewidths=0,
        alpha=0.85,
        label=f"All {summary['candidate_count']} formal-valence-compatible recipes",
    )
    left.scatter(
        [100 * float(row["mass_fraction_Nb"]) for row in feasible],
        [float(row[capacity_field]) for row in feasible],
        facecolors="none",
        edgecolors="#172b4d",
        s=36,
        linewidths=0.8,
        label=f"Passes both ideal-inventory gates ({len(feasible)})",
    )
    left.axvline(nb_gate, color="#477658", linestyle="--", linewidth=1)
    left.axhline(capacity_gate, color="#477658", linestyle="--", linewidth=1)

    def formula_label(row):
        parts = ["Li_2"]
        for element, field in (("Mn", "mn"), ("Ti", "ti"), ("Nb", "nb")):
            coefficient = Fraction(row[f"{field}_grid_count"], row["grid_denominator"])
            if coefficient == 0:
                continue
            if coefficient == 1:
                parts.append(element)
            elif coefficient.denominator == 1:
                parts.append(f"{element}_{{{coefficient.numerator}}}")
            else:
                parts.append(f"{element}_{{{coefficient.numerator}/{coefficient.denominator}}}")
        return "$" + "".join(parts) + "O_2F$"

    def annotate(row, label, position, marker, color, size):
        coordinates = (100 * row["mass_fraction_Nb"], row[capacity_field])
        left.scatter(*coordinates, marker=marker, s=size, color=color, zorder=4)
        left.annotate(
            label,
            coordinates,
            xytext=position,
            fontsize=8.5,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 2},
            arrowprops={"arrowstyle": "->", "color": color},
        )

    capacity_margin = 100 * (selected[capacity_field] / capacity_gate - 1)
    annotate(
        selected,
        f"Nominee: {formula_label(selected)}\n"
        f"{selected[capacity_field]:.3f} mAh/g; +{capacity_margin:.3f}% capacity margin",
        (2.7, 243),
        "*",
        "#cc453b",
        210,
    )
    annotate(
        best_margin,
        f"Largest minimum gate margin\n{formula_label(best_margin)}\n"
        f"{best_margin[capacity_field]:.2f} mAh/g",
        (17, 238),
        "D",
        "#c06a20",
        60,
    )
    annotate(
        nb_control,
        f"Prior-art Nb control\n{formula_label(nb_control)}\n"
        f"{nb_control[capacity_field]:.2f} mAh/g",
        (16, 274),
        "s",
        "#172b4d",
        55,
    )
    annotate(
        ti_control,
        f"Prior-art Ti control\n{formula_label(ti_control)}\n"
        f"{ti_control[capacity_field]:.2f} mAh/g",
        (3, 229),
        "s",
        "#172b4d",
        55,
    )
    left.set(
        xlabel="Niobium content [wt%]",
        ylabel="Theoretical Mn-only capacity [mAh/g]",
        xlim=(-0.8, 25.5),
        ylim=(220, 283),
        title="Composition inventory tradeoff",
    )
    left.legend(loc="lower right", fontsize=8, frameon=False)
    figure.colorbar(
        scatter,
        ax=left,
        label="Ti coefficient in $Li_2Mn_{1-t-n}Ti_tNb_nO_2F$",
        fraction=0.025,
        pad=0.02,
    )

    scenarios = summary["scenarios"]
    scenario_ids = [scenario["id"] for scenario in scenarios]
    under_nb = [row for row in rows if float(row["mass_fraction_Nb"]) <= nb_gate / 100]
    maxima_under_nb = [
        max(float(row[f"{scenario_id}_capacity_mAh_g"]) for row in under_nb)
        for scenario_id in scenario_ids
    ]
    global_maxima = [
        max(float(row[f"{scenario_id}_capacity_mAh_g"]) for row in rows)
        for scenario_id in scenario_ids
    ]
    counts = [summary["feasible_counts_by_scenario"][scenario_id] for scenario_id in scenario_ids]
    bars = right.bar(
        range(len(scenarios)),
        maxima_under_nb,
        width=0.62,
        color=["#356d9c"] + ["#b7845c"] * (len(scenarios) - 1),
        label=f"Maximum within {nb_gate:g} wt% Nb limit",
    )
    right.plot(
        range(len(scenarios)),
        global_maxima,
        "o:",
        color="#66717e",
        label="Maximum across full composition grid",
        markersize=5,
        linewidth=1.3,
    )
    right.axhline(capacity_gate, color="#477658", linestyle="--", linewidth=1)
    for bar, maximum, count in zip(bars, maxima_under_nb, counts, strict=True):
        right.text(
            bar.get_x() + bar.get_width() / 2,
            maximum - 14,
            f"{maximum:.1f}\n{count} pass",
            ha="center",
            va="top",
            fontsize=9,
            color="white",
        )
    right.set_xticks(
        range(len(scenarios)),
        [
            f"{100 * scenario['utilization_numerator'] / scenario['utilization_denominator']:g}%"
            for scenario in scenarios
        ],
    )
    right.set(
        xlabel="Hypothetical fraction of Mn electron inventory used",
        ylabel="Maximum Mn-only capacity [mAh/g]",
        ylim=(0, 292),
        title="Sensitivity to assumed accessible Mn redox",
    )
    right.legend(loc="lower left", fontsize=8, frameon=False)
    right.text(
        0.98,
        0.96,
        "Counts pass capacity + Nb gates.\nUtilization cases are hypothetical,\nnot measurements or probabilities.",
        transform=right.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
    )
    figure.suptitle(
        "Mn-rich oxyfluoride battery cathode hypotheses | stoichiometric inventory screen",
        fontsize=13,
    )
    figure.supxlabel(
        "Assumes Mn oxidizes to Mn⁴⁺ with fixed Ti⁴⁺ / Nb⁵⁺; capacities are calculated, not measured.",
        fontsize=9,
    )
    figure.savefig(args.results / "tradeoffs.png", dpi=180)
    svg_path = args.results / "tradeoffs.svg"
    figure.savefig(svg_path, metadata={"Date": None})
    # Normalize Matplotlib's path-data trailing spaces without changing geometry.
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_path.read_text().splitlines()) + "\n"
    )
    plt.close(figure)
    print("Wrote tradeoffs.png and tradeoffs.svg")


if __name__ == "__main__":
    main()
