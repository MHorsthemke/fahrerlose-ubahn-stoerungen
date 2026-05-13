"""
plot_heatmap_intervention.py — Heatmap: Interventionszeit nach Position und Agentenzahl.

Zeigt die Interventionszeit als Farbkarte auf der PHYSISCHEN Strecke:
  - X-Achse: Position auf der physischen Strecke (0 – 7,4 km)
  - Y-Achse: Anzahl Stationsagenten (1–10)
  - Farbe:   Interventionszeit (min), gemittelt über Hin- und Rückfahrt

Hin- und Rückfahrt-Daten werden auf die physische Strecke
zurückgerechnet (Rück-Position = Umlauflänge − Position) und gemittelt.

Pro Zeile werden die Agenten-Positionen mit Markern hervorgehoben,
damit sofort sichtbar ist, wo Agenten stehen.

Stil und Speicherung über thesis_style.

Verwendung:
    python3 plot_heatmap_intervention.py [pfad_zur_batch_csv]
"""

import sys
import csv
import numpy as np
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# Eigene Module
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stations import STATIONS, WENDEPUNKT_RECHTS
from sa_distribution import distribute_agents

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style as ts


UMLAUF_M = 2 * WENDEPUNKT_RECHTS  # 14776


def load_and_average(csv_path: Path, step_m: float = 250.0
                     ) -> tuple[np.ndarray, list[int], np.ndarray]:
    """Mittelt Hin/Rück pro Positionsbin auf der physischen Strecke."""
    from collections import defaultdict

    raw = defaultdict(list)
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                pos = float(row['disruption_position_m'])
                na = int(row['num_agents'])
                t = float(row['t_intervention_total_s'])
            except (ValueError, TypeError, KeyError):
                continue
            phys = pos if pos <= WENDEPUNKT_RECHTS else UMLAUF_M - pos
            raw[na].append((phys, t / 60.0))

    agents = sorted(raw.keys())
    bin_edges = np.arange(0, WENDEPUNKT_RECHTS + step_m, step_m)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    n_bins = len(bin_centers)

    matrix = np.full((len(agents), n_bins), np.nan)
    for i, na in enumerate(agents):
        sums = np.zeros(n_bins)
        counts = np.zeros(n_bins)
        for phys, t_min in raw[na]:
            b = int(phys / step_m)
            if b >= n_bins:
                b = n_bins - 1
            sums[b] += t_min
            counts[b] += 1
        mask = counts > 0
        matrix[i, mask] = sums[mask] / counts[mask]

    return matrix, agents, bin_centers


def find_latest_csv(batch_dir: Path) -> Path:
    csvs = sorted(batch_dir.glob('*.csv'), key=lambda p: p.stat().st_mtime)
    if not csvs:
        print(f'FEHLER: Keine CSV-Dateien in {batch_dir}')
        sys.exit(1)
    return csvs[-1]


def plot_heatmap(matrix: np.ndarray, agents: list[int],
                 bin_centers: np.ndarray, output_dir: Path):
    ts.apply_style()
    fig, ax = plt.subplots(figsize=ts.FIGSIZE_HEATMAP)

    cmap = plt.get_cmap(ts.CMAP_SEQUENTIAL)
    vmin = float(np.nanmin(matrix))
    vmax = float(np.nanmax(matrix))

    step = bin_centers[1] - bin_centers[0] if len(bin_centers) > 1 else 250
    pos_edges = np.append(bin_centers - step / 2, bin_centers[-1] + step / 2)
    agent_edges = np.arange(0.5, len(agents) + 1.5)

    mesh = ax.pcolormesh(
        pos_edges / 1000,
        agent_edges,
        matrix,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        shading='flat',
    )

    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, aspect=22)
    cbar.set_label('Interventionszeit (min)')
    cbar.ax.tick_params(labelsize=8)

    for s in STATIONS:
        ax.axvline(x=s.km / 1000, color='white', linewidth=0.5,
                   alpha=0.35, linestyle='--', zorder=2)

    for i, na in enumerate(agents):
        indices = distribute_agents(na)
        agent_kms = [STATIONS[idx].km / 1000 for idx in indices]
        y = na
        ax.scatter(agent_kms, [y] * len(agent_kms),
                   marker='|', color=ts.COLOR_ACCENT, s=60,
                   linewidths=1.4, zorder=5)

    ts.setup_position_axis(ax, axis='x')
    ax.set_ylabel('Anzahl Stationsagenten')
    ax.set_yticks(range(1, len(agents) + 1))
    ax.set_yticklabels([str(a) for a in agents])
    ax.set_ylim(0.5, len(agents) + 0.5)

    for i, s in enumerate(STATIONS):
        km = s.km / 1000
        if km < 0 or km > WENDEPUNKT_RECHTS / 1000:
            continue
        y_name = 1.025 if i % 2 == 0 else 1.075
        ax.text(km, y_name, s.name, ha='center', va='bottom', fontsize=7,
                transform=ax.get_xaxis_transform(), clip_on=False)
        if i % 2 == 1:
            ax.plot([km, km], [1.005, 1.07],
                    color=ts.COLOR_NEUTRAL, linewidth=0.5, zorder=1,
                    clip_on=False, transform=ax.get_xaxis_transform())

    legend_elements = [
        Line2D([0], [0], marker='|', color='w',
               markerfacecolor=ts.COLOR_ACCENT,
               markeredgecolor=ts.COLOR_ACCENT,
               markersize=8, markeredgewidth=1.4,
               label='Agentenposition', linestyle='None'),
    ]
    ax.legend(handles=legend_elements,
              loc='center right', bbox_to_anchor=(1.10, -0.085),
              frameon=False, handletextpad=0.4, borderpad=0.0)

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Heatmap_Interventionszeit')
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

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')
        positions = sorted(set(float(r['disruption_position_m'])
                               for r in reader
                               if r.get('disruption_position_m')))
    step_m = positions[1] - positions[0] if len(positions) >= 2 else 250.0
    print(f'Schrittweite: {step_m:.0f}m')

    matrix, agents, bin_centers = load_and_average(csv_path, step_m)
    if matrix.size == 0:
        print('FEHLER: Keine gültigen Daten!')
        sys.exit(1)

    print(f'Matrix: {matrix.shape} ({len(agents)} Agentengruppen × '
          f'{len(bin_centers)} Bins)')
    print(f'Wertebereich: {np.nanmin(matrix):.1f} – {np.nanmax(matrix):.1f} min')

    plot_heatmap(matrix, agents, bin_centers, output_dir)
    print('Fertig.')
