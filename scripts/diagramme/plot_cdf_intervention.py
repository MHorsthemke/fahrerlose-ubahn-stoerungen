"""
plot_cdf_intervention.py — CDF der Interventionszeit pro Stationsagenten-Konfiguration.

Zeigt die kumulative Verteilungsfunktion der Interventionszeit für 1..10 Agenten.
Die AGBF-Hilfsfrist ist als Referenzlinie eingezeichnet.

Stil und Speicherung über thesis_style.

Verwendung:
    python3 plot_cdf_intervention.py [pfad_zur_batch_csv]
"""

import sys
import csv
import numpy as np
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, str(Path(__file__).resolve().parent))
from thesis_style import (
    apply_style, save_fig, add_grid,
    setup_time_axis, setup_percent_axis, add_agbf_marker,
    cmap_categorical, draw_matrix_legend,
)


def load_batch_csv(csv_path: Path) -> dict[int, list[float]]:
    """Liest die Batch-CSV und gibt {num_agents: [t_min, ...]} zurück."""
    data = defaultdict(list)
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                na = int(row['num_agents'])
                t = float(row['t_intervention_total_s'])
                data[na].append(t / 60.0)
            except (ValueError, TypeError, KeyError):
                continue
    return dict(data)


def find_latest_csv(batch_dir: Path) -> Path:
    csvs = sorted(batch_dir.glob('*.csv'), key=lambda p: p.stat().st_mtime)
    if not csvs:
        print(f'FEHLER: Keine CSV-Dateien in {batch_dir}')
        sys.exit(1)
    return csvs[-1]


def plot_cdf(data: dict[int, list[float]], output_dir: Path):
    apply_style()
    fig = plt.figure(figsize=(6.3, 4.6))
    gs = GridSpec(2, 1, height_ratios=[5.0, 0.6], hspace=0.22, figure=fig)
    ax = fig.add_subplot(gs[0])
    ax_leg = fig.add_subplot(gs[1])

    agents_sorted = sorted(data.keys())
    colors = cmap_categorical(len(agents_sorted))

    for i, na in enumerate(agents_sorted):
        values = sorted(data[na])
        n = len(values)
        cdf_y = np.arange(1, n + 1) / n * 100
        ax.step(values, cdf_y, where='post',
                color=colors[i], linewidth=1.4,
                label=f'{na}')

    setup_time_axis(ax, axis='x')
    setup_percent_axis(ax, axis='y')
    add_grid(ax, axis='both')
    add_agbf_marker(ax, axis='x', label=True)

    rows_legend = [
        ('Anzahl SA', [
            dict(color=colors[i], linewidth=2.0)
            for i in range(len(agents_sorted))
        ]),
    ]
    draw_matrix_legend(ax_leg, len(agents_sorted), rows_legend)

    save_fig(fig, output_dir, 'CDF_Interventionszeit')
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

    plot_cdf(data, output_dir)
    print('Fertig.')
