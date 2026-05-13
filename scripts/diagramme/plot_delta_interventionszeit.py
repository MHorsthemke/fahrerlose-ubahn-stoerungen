"""
plot_delta_interventionszeit.py — Positionsweise Verbesserung der Interventionszeit pro Agent.

Boxplot: Pro Übergang (1→2, 2→3, ...) wird je Störungsposition die Differenz
der Interventionszeit gebildet. Die Boxplots zeigen die Verteilung dieser
positionsgebundenen Verbesserungen.

Stil und Speicherung über thesis_style.

Verwendung:
    python3 plot_delta_interventionszeit.py [pfad_zur_batch_csv]
"""

import sys
import csv
import numpy as np
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from thesis_style import (
    apply_style, save_fig, add_grid, place_legend_below,
    setup_delta_axis,
    FIGSIZE_DEFAULT,
    COLOR_PRIMARY, COLOR_PRIMARY_SOFT, COLOR_ACCENT, COLOR_NEUTRAL, COLOR_MUTED,
)


def load_batch_csv(csv_path: Path) -> dict[tuple[float, int], float]:
    data: dict[tuple[float, int], float] = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                pos = float(row['disruption_position_m'])
                n = int(row['num_agents'])
                t = float(row['t_intervention_total_s'])
            except (ValueError, TypeError, KeyError):
                continue
            data[(pos, n)] = t
    return data


def find_latest_csv(batch_dir: Path) -> Path:
    csvs = sorted(batch_dir.glob('*.csv'), key=lambda p: p.stat().st_mtime)
    if not csvs:
        print(f'FEHLER: Keine CSV-Dateien in {batch_dir}')
        sys.exit(1)
    return csvs[-1]


def compute_deltas(data: dict[tuple[float, int], float]) -> dict[str, list[float]]:
    agents = sorted(set(n for _, n in data.keys()))
    positions = sorted(set(pos for pos, _ in data.keys()))
    deltas: dict[str, list[float]] = {}
    for i in range(len(agents) - 1):
        n_from = agents[i]
        n_to = agents[i + 1]
        label = rf'${n_from}{{\to}}{n_to}$'
        delta_list = []
        for pos in positions:
            t_from = data.get((pos, n_from))
            t_to = data.get((pos, n_to))
            if t_from is not None and t_to is not None:
                delta_list.append((t_from - t_to) / 60.0)
        deltas[label] = delta_list
    return deltas


def plot_delta_boxplot(deltas: dict[str, list[float]], output_dir: Path):
    apply_style()
    transitions = list(deltas.keys())
    box_data = [np.array(deltas[t]) for t in transitions]

    fig, ax = plt.subplots(figsize=FIGSIZE_DEFAULT)

    bp = ax.boxplot(
        box_data,
        positions=range(1, len(transitions) + 1),
        widths=0.55,
        patch_artist=True,
        showmeans=False,
        showfliers=False,
        whis=(0, 100),
    )

    for patch in bp['boxes']:
        patch.set_facecolor(COLOR_PRIMARY_SOFT)
        patch.set_alpha(0.55)
        patch.set_edgecolor(COLOR_PRIMARY)
        patch.set_linewidth(1.0)
    for line in bp['medians']:
        line.set_color(COLOR_ACCENT)
        line.set_linewidth(1.6)
    for whisker in bp['whiskers']:
        whisker.set_color(COLOR_NEUTRAL)
        whisker.set_linewidth(0.8)
        whisker.set_linestyle((0, (3, 2)))
    for cap in bp['caps']:
        cap.set_color(COLOR_NEUTRAL)
        cap.set_linewidth(0.8)

    means = [float(np.mean(deltas[t])) for t in transitions]
    x_positions = list(range(1, len(transitions) + 1))
    ax.scatter(x_positions, means, marker='D', s=22, color=COLOR_PRIMARY,
               edgecolors='white', linewidths=0.6, zorder=5, label='Mittelwert')

    for i, t in enumerate(transitions):
        m = means[i]
        s = float(np.std(deltas[t], ddof=1)) if len(deltas[t]) > 1 else 0.0
        y_top = float(np.max(deltas[t]))
        ax.text(i + 1, y_top + 0.4,
                rf'$\bar{{x}}{{=}}{m:.1f}$' '\n' rf'$\sigma{{=}}{s:.1f}$',
                ha='center', va='bottom', fontsize=8, color=COLOR_MUTED,
                linespacing=1.05)

    ax.axhline(y=0, color=COLOR_NEUTRAL, linewidth=0.8, linestyle='-',
               zorder=1, alpha=0.6)

    ax.set_xticks(x_positions)
    ax.set_xticklabels(transitions)
    ax.set_xlim(0.4, len(transitions) + 0.6)
    ax.set_xlabel('Übergang (Anzahl Stationsagenten)')
    setup_delta_axis(ax, axis='y', lim=(-10, 15))
    ax.yaxis.set_major_locator(MultipleLocator(5))
    ax.yaxis.set_minor_locator(MultipleLocator(1))
    add_grid(ax, axis='y')

    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=COLOR_PRIMARY_SOFT, alpha=0.55, edgecolor=COLOR_PRIMARY,
              label='Q1–Q3'),
        Line2D([0], [0], color=COLOR_ACCENT, linewidth=1.6, label='Median'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor=COLOR_PRIMARY,
               markersize=6, label='Mittelwert', linestyle='None'),
        Line2D([0], [0], color=COLOR_NEUTRAL, linewidth=0.8, linestyle=(0, (3, 2)),
               label='Min/Max'),
    ]
    place_legend_below(ax, ncol=4, handles=legend_elements)

    fig.tight_layout()
    save_fig(fig, output_dir, 'Delta_Interventionszeit')
    plt.close(fig)


if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parents[2]
    batch_dir = base_dir / 'output' / 'batch_results'
    output_dir = base_dir / 'Diagramme'

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = find_latest_csv(batch_dir)

    print(f'CSV: {csv_path}')
    data = load_batch_csv(csv_path)
    if not data:
        print('FEHLER: Keine gültigen Daten!')
        sys.exit(1)

    deltas = compute_deltas(data)
    for t, vals in deltas.items():
        arr = np.array(vals)
        neg = int(np.sum(arr < 0))
        print(f'  {t}: Mittel={np.mean(arr):.1f} min, '
              f'Median={np.median(arr):.1f} min, '
              f'σ={np.std(arr, ddof=1):.1f} min, '
              f'Verschlechterungen: {neg}/{len(arr)}')

    plot_delta_boxplot(deltas, output_dir)
    print('Fertig.')
