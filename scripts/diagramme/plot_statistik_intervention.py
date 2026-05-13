"""
plot_statistik_intervention.py — Boxplot der Interventionszeit nach Anzahl Stationsagenten.

Liest die Batch-CSV und erzeugt einen thesis-konformen Boxplot:
  - Abszisse: Anzahl Stationsagenten (1–10)
  - Ordinate: Interventionszeit in Minuten
  - Box: Q1–Q3, Whisker: Min/Max, Median als Linie, Mittelwert als Raute
  - $\\bar{x}$ und $\\sigma$ kompakt über jeder Box

Stil und Speicherung über thesis_style. Achsen-Bereiche, Schriftgrößen und
Legenden-Position sind plotübergreifend einheitlich (siehe thesis_style.py).
Plot-Titel und Parameter-Annotationen bewusst weggelassen — die Caption
in chapter5.tex liefert den Kontext (Reaktionszeit, Gehgeschwindigkeit, n).

Verwendung:
    python3 plot_statistik_intervention.py [pfad_zur_batch_csv]
"""

import sys
import csv
import numpy as np
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from thesis_style import (
    apply_style, save_fig, add_grid, place_legend_below,
    setup_time_axis, setup_count_axis,
    FIGSIZE_DEFAULT,
    COLOR_PRIMARY, COLOR_PRIMARY_SOFT, COLOR_ACCENT, COLOR_NEUTRAL, COLOR_MUTED,
)


# ===================================================================
# DATEN LADEN
# ===================================================================
def load_batch_csv(csv_path: Path) -> dict[int, list[float]]:
    """Liest die Batch-CSV und gruppiert t_intervention_total_s nach num_agents."""
    data: dict[int, list[float]] = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                num_agents = int(row['num_agents'])
                t_intervention = float(row['t_intervention_total_s'])
            except (ValueError, TypeError, KeyError):
                continue
            data.setdefault(num_agents, []).append(t_intervention)
    return data


def find_latest_csv(batch_dir: Path) -> Path:
    csvs = sorted(batch_dir.glob('*.csv'), key=lambda p: p.stat().st_mtime)
    if not csvs:
        print(f'FEHLER: Keine CSV-Dateien in {batch_dir}')
        sys.exit(1)
    return csvs[-1]


# ===================================================================
# STATISTIK
# ===================================================================
def compute_stats(data: dict[int, list[float]]) -> dict:
    agents = sorted(data.keys())
    stats = {'agents': agents, 'mean': [], 'std': [], 'max': [],
             'median': [], 'min': [], 'n_samples': []}
    for n in agents:
        values = np.array(data[n])
        stats['mean'].append(np.mean(values))
        stats['std'].append(np.std(values, ddof=1) if len(values) > 1 else 0.0)
        stats['max'].append(np.max(values))
        stats['median'].append(np.median(values))
        stats['min'].append(np.min(values))
        stats['n_samples'].append(len(values))
    return stats


# ===================================================================
# BOXPLOT
# ===================================================================
def plot_boxplot(data: dict[int, list[float]], stats: dict,
                 output_dir: Path):
    apply_style()

    agents = sorted(data.keys())
    box_data = [np.array(data[n]) / 60.0 for n in agents]
    mean_min = np.array(stats['mean']) / 60.0
    max_min = np.array(stats['max']) / 60.0
    std_min = np.array(stats['std']) / 60.0

    fig, ax = plt.subplots(figsize=FIGSIZE_DEFAULT)

    bp = ax.boxplot(
        box_data,
        positions=range(1, len(agents) + 1),
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

    x_positions = list(range(1, len(agents) + 1))
    ax.scatter(x_positions, mean_min, marker='D', s=22, color=COLOR_PRIMARY,
               edgecolors='white', linewidths=0.6, zorder=5, label='Mittelwert')

    # Kompakte $\bar x$/$\sigma$-Annotation oberhalb der Box
    for i, (m, s, mx) in enumerate(zip(mean_min, std_min, max_min)):
        ax.text(i + 1, mx + 0.6,
                rf'$\bar{{x}}{{=}}{m:.1f}$' '\n' rf'$\sigma{{=}}{s:.1f}$',
                ha='center', va='bottom', fontsize=8, color=COLOR_MUTED,
                linespacing=1.05)

    setup_count_axis(ax, axis='x', label='Anzahl Stationsagenten')
    setup_time_axis(ax, axis='y')
    add_grid(ax, axis='y')

    # Legende einheitlich unten
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
    save_fig(fig, output_dir, 'Statistik_Interventionszeit')
    plt.close(fig)


# ===================================================================
# KONSOLEN-ZUSAMMENFASSUNG
# ===================================================================
def print_summary(stats: dict):
    print(f'\n{"=" * 70}')
    print(f'{"Agenten":>8} {"n":>4} {"Mittel":>10} {"Std.Abw.":>10} '
          f'{"Median":>10} {"Min":>10} {"Max":>10}')
    print(f'{"":>8} {"":>4} {"(min)":>10} {"(min)":>10} '
          f'{"(min)":>10} {"(min)":>10} {"(min)":>10}')
    print(f'{"-" * 70}')
    for i, n_agents in enumerate(stats['agents']):
        print(f'{n_agents:>8} {stats["n_samples"][i]:>4} '
              f'{stats["mean"][i] / 60:>10.1f} {stats["std"][i] / 60:>10.1f} '
              f'{stats["median"][i] / 60:>10.1f} {stats["min"][i] / 60:>10.1f} '
              f'{stats["max"][i] / 60:>10.1f}')
    print(f'{"=" * 70}\n')


# ===================================================================
# HAUPTPROGRAMM
# ===================================================================
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
        print('FEHLER: Keine gültigen Daten in der CSV!')
        sys.exit(1)

    stats = compute_stats(data)
    print_summary(stats)
    plot_boxplot(data, stats, output_dir)
    print('Fertig.')
