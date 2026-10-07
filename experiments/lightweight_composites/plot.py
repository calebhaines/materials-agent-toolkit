"""Export the experiment's scientific tradeoffs as standalone PNG and SVG figures."""

import argparse
import csv
import json
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
            "svg.hashsalt": "materials-agent-toolkit-composite-screen-v1",
        }
    )
    summary = json.loads((args.results / "summary.json").read_text())
    with (args.results / "candidates.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    nominal = [row for row in rows if row["scenario_id"] == "nominal"]
    feasible = [row for row in nominal if row["feasible"] == "True"]
    rejected = [row for row in nominal if row["feasible"] != "True"]
    nomination = summary["nominated_candidate"]
    if nomination is None:
        raise ValueError("This figure requires a nominated screening candidate")
    selected = nomination["nominal"]
    controls = [row for row in summary["controls"] if row["scenario_id"] == "nominal"]
    baseline = next(row for row in controls if row["ceramic_vol_percent"] == 0)
    binary = min(
        (
            row
            for row in feasible
            if sum(int(row[f"{phase}_vol_percent"]) > 0 for phase in ("SiC", "AlN", "Al2O3")) == 1
        ),
        key=lambda row: (int(row["ceramic_vol_percent"]), -float(row["conductivity_reuss_W_m_K"])),
    )
    x_field = "conductivity_reuss_W_m_K"
    y_field = "specific_modulus_reuss_GPa_per_g_cm3"
    x_gate = summary["screen"]["conductivity_min_W_m_K"]
    y_gate = summary["screen"]["specific_modulus_min_GPa_per_g_cm3"]
    figure, (left, right) = plt.subplots(
        1, 2, figsize=(13.5, 5.7), gridspec_kw={"width_ratios": [1.55, 1]}, layout="constrained"
    )
    left.add_patch(Rectangle((x_gate, y_gate), 60, 8, color="#e8f3eb", alpha=0.8, zorder=0))
    left.scatter(
        [float(row[x_field]) for row in rejected],
        [float(row[y_field]) for row in rejected],
        s=8,
        color="#acb6c0",
        alpha=0.28,
        linewidths=0,
        rasterized=True,
        label="Fails at least one nominal gate",
    )
    scatter = left.scatter(
        [float(row[x_field]) for row in feasible],
        [float(row[y_field]) for row in feasible],
        c=[int(row["ceramic_vol_percent"]) for row in feasible],
        cmap="viridis",
        vmin=5,
        vmax=35,
        s=28,
        linewidths=0,
        label=f"Passes all nominal gates ({len(feasible)})",
    )
    left.axvline(x_gate, color="#477658", linestyle="--", linewidth=1)
    left.axhline(y_gate, color="#477658", linestyle="--", linewidth=1)
    left.scatter(selected[x_field], selected[y_field], marker="*", s=220, color="#cc453b", zorder=4)
    recipe_label = " / ".join(
        f"{value}% {phase}"
        for phase, value in nomination["phase_volume_percent"].items()
        if value > 0
    )
    stiffness_margin_percent = (selected[y_field] / y_gate - 1) * 100
    left.annotate(
        f"Nominee: {recipe_label}\n{stiffness_margin_percent:.3f}% specific-stiffness gate margin",
        (selected[x_field], selected[y_field]),
        xytext=(150, 35.1),
        ha="center",
        fontsize=9,
        arrowprops={"arrowstyle": "->", "color": "#cc453b"},
    )
    left.scatter(
        float(binary[x_field]),
        float(binary[y_field]),
        s=65,
        facecolors="none",
        edgecolors="#172b4d",
        linewidths=1.5,
        label=(
            "First feasible binary: "
            + " / ".join(
                f"{binary[f'{phase}_vol_percent']}% {phase}"
                for phase in ("SiC", "AlN", "Al2O3")
                if int(binary[f"{phase}_vol_percent"]) > 0
            )
        ),
        zorder=3,
    )
    left.scatter(
        baseline[x_field], baseline[y_field], marker="s", s=50, color="#b66d20", label="Pure Al"
    )
    left.set(
        xlabel="Ideal harmonic conductivity [W/(m·K)]",
        ylabel="Ideal Reuss specific modulus [GPa/(g/cm³)]",
        xlim=(55, 245),
        ylim=(24.5, 36),
        title=f"{summary['candidate_count']:,} recipes: mechanical / thermal tradeoff",
    )
    left.legend(loc="lower left", fontsize=8, frameon=False)
    figure.colorbar(
        scatter, ax=left, label="Total ceramic loading [vol%]", fraction=0.025, pad=0.02
    )

    counts = summary["feasible_counts_by_scenario"]
    scenario_labels = {
        "nominal": "Baseline",
        "source_high_moduli": "Source\nhigh E",
        "matrix_5pct_softer": "Al E\n−5%",
        "conductivity_10pct_lower": "κ\n−10%",
        "density_2pct_higher": "ρ\n+2%",
        "cte_proxies_10pct_higher": "CTE\n+10%",
        "combined_stress": "Joint\nstress",
    }
    scenario_ids = [scenario["id"] for scenario in summary["curated_inputs"]["scenarios"]]
    labels = [scenario_labels.get(key, key) for key in scenario_ids]
    # Canonical JSON sorts keys; use the input scenario ordering for a consistent narrative.
    values = [counts[key] for key in scenario_ids]
    bars = right.bar(
        range(len(values)),
        values,
        color=[
            "#356d9c"
            if key == "nominal"
            else "#7697b2"
            if key == "source_high_moduli"
            else "#b7845c"
            for key in scenario_ids
        ],
    )
    for bar, value in zip(bars, values, strict=True):
        right.text(
            bar.get_x() + bar.get_width() / 2, value + 2, str(value), ha="center", fontsize=10
        )
    right.set_xticks(range(len(values)), labels, fontsize=8)
    right.set(
        ylabel="Recipes passing all four gates",
        ylim=(0, max(1, max(values)) * 1.24),
        title="Deterministic sensitivity checks",
    )
    right.text(
        0.98,
        0.88,
        f"{summary['all_scenarios_feasible_count']} recipes pass every scenario.\n"
        "Stress cases are hypothetical,\nnot statistical confidence intervals.",
        transform=right.transAxes,
        ha="right",
        va="top",
        fontsize=9,
    )
    figure.suptitle(
        "Aluminum–ceramic heat-spreader hypotheses | ideal mixture models, not measurements",
        fontsize=13,
    )
    figure.savefig(args.results / "tradeoffs.png", dpi=180)
    figure.savefig(args.results / "tradeoffs.svg", metadata={"Date": None})
    plt.close(figure)
    print("Wrote tradeoffs.png and tradeoffs.svg")


if __name__ == "__main__":
    main()
