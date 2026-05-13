"""
plot_diminishing_returns.py — Diminishing-Returns-Diagramm.

Liniendiagramm: Agentenzahl (x) vs. Interventionszeit (y) in Minuten.
Drei Kurven: Mittelwert, Median, Maximum.
Zeigt den abnehmenden Grenznutzen zusätzlicher Agenten.

Verwendung:
    python3 plot_diminishing_returns.py [pfad_zur_batch_csv]

    Ohne Argument wird die neueste CSV in output/batch_results/ verwendet.
"""

import sys
import csv
import numpy as np
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams

# ===================================================================
# FONT & STYLE (gleich wie Agentenverteilung_U4.py)
# ===================================================================
rcParams['font.family'] = 'sans-serif'
rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
rcParams['font.size'] = 11
rcParams['axes.labelsize'] = 12
rcParams['axes.titlesize'] = 14
rcParams['xtick.labelsize'] = 10
rcParams['ytick.labelsize'] = 11
rcParams['pdf.fonttype'] = 42          # TrueType für Overleaf
rcParams['savefig.facecolor'] = 'white'

# ===================================================================
# FARBEN (konsistent mit anderen Diagrammen)
# ===================================================================
COLOR_MEAN   = '#2F5496'   # Dunkelblau — Mittelwert
COLOR_MEDIAN = '#ED7D31'   # Orange — Median
COLOR_MAX    = '#C00000'   # Rot — Maximum
COLOR_MIN    = '#70AD47'   # Grün — Minimum


# ===================================================================
# DATEN LADEN
# ===================================================================
def load_batch_csv(csv_path: Path) -> dict[int, list[float]]:
    """Liest Batch-CSV, gruppiert t_intervention_total_s nach num_agents."""
    data: dict[int, list[float]] = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                n = int(row['num_agents'])
                t = float(row['t_intervention_total_s'])
            except (ValueError, TypeError, KeyError):
                continue
            data.setdefault(n, []).append(t)
    return data


def find_latest_csv(batch_dir: Path) -> Path:
    csvs = sorted(batch_dir.glob('*.csv'), key=lambda p: p.stat().st_mtime)
    if not csvs:
        print(f"FEHLER: Keine CSV-Dateien in {batch_dir}")
        sys.exit(1)
    return csvs[-1]


# ===================================================================
# PLOT
# ===================================================================
def plot_diminishing_returns(data: dict[int, list[float]],
                              csv_name: str, output_dir: Path):
    agents = sorted(data.keys())
    mean_min = [np.mean(data[n]) / 60 for n in agents]
    median_min = [np.median(data[n]) / 60 for n in agents]
    max_min = [np.max(data[n]) / 60 for n in agents]
    min_min = [np.min(data[n]) / 60 for n in agents]

    fig, ax = plt.subplots(figsize=(10, 6))

    # --- Linien ---
    ax.plot(agents, max_min, marker='v', markersize=7, linewidth=2,
            color=COLOR_MAX, label='Maximum', zorder=4)
    ax.plot(agents, mean_min, marker='D', markersize=7, linewidth=2.5,
            color=COLOR_MEAN, label='Mittelwert', zorder=5)
    ax.plot(agents, median_min, marker='o', markersize=7, linewidth=2,
            color=COLOR_MEDIAN, label='Median', zorder=4)
    ax.plot(agents, min_min, marker='^', markersize=7, linewidth=2,
            color=COLOR_MIN, label='Minimum', zorder=4)

    # --- Werte annotieren ---
    for i, n in enumerate(agents):
        ax.annotate(f'{mean_min[i]:.1f}',
                     xy=(n, mean_min[i]),
                     xytext=(0, 10), textcoords='offset points',
                     ha='center', fontsize=8, color=COLOR_MEAN, fontweight='bold')

    # --- Bereich "Knie" hervorheben ---
    ax.axvspan(3, 5, alpha=0.08, color=COLOR_MEAN, zorder=0)
    ax.text(4, max(max_min) * 0.95, 'Kosten-Nutzen-\nOptimum',
            ha='center', va='top', fontsize=9, color=COLOR_MEAN,
            fontstyle='italic', alpha=0.7)

    # --- Achsen ---
    ax.set_xlabel('Anzahl Stationsagenten')
    ax.set_ylabel('Interventionszeit (min)')
    ax.set_xticks(agents)
    ax.set_xlim(0.5, max(agents) + 0.5)
    ax.set_ylim(0, max(max_min) * 1.15)

    # --- Gitter ---
    ax.yaxis.grid(True, linestyle='--', alpha=0.3, zorder=0)
    ax.set_axisbelow(True)

    # --- Titel ---
    ax.set_title('Diminishing Returns — Interventionszeit nach Agentenzahl',
                 fontweight='bold', pad=12)

    # --- Anmerkung ---
    ax.text(0.98, 0.97,
            f'n = {len(data[agents[0]])} Störungspositionen je Konfiguration\n'
            f'Gehgeschwindigkeit: 1,2 m/s | Reaktionszeit: 60 s',
            transform=ax.transAxes, ha='right', va='top',
            fontsize=9, color='#666666',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                      alpha=0.8, edgecolor='#CCCCCC'))

    # --- Legende ---
    ax.legend(loc='center right', framealpha=0.9)

    # --- Spines ---
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()

    # --- Speichern ---
    output_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = output_dir / 'Diminishing_Returns.pdf'
    out_svg = output_dir / 'Diminishing_Returns.svg'
    fig.savefig(str(out_pdf), format='pdf', bbox_inches='tight', dpi=300)
    fig.savefig(str(out_svg), format='svg', bbox_inches='tight')
    print(f"PDF: {out_pdf}")
    print(f"SVG: {out_svg}")

    plt.close(fig)
    return out_pdf, out_svg


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

    print(f"CSV: {csv_path}")
    data = load_batch_csv(csv_path)
    if not data:
        print("FEHLER: Keine gültigen Daten!")
        sys.exit(1)

    plot_diminishing_returns(data, csv_path.name, output_dir)
    print("\nFertig!")
