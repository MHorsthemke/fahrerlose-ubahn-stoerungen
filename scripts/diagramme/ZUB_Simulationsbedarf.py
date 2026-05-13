"""
ZUB_Simulationsbedarf.py — Visualisierung: Welche ZUB+-Szenarien müssen simuliert werden?

Baut auf der Zellteilungs-Grafik (ZUB_Verteilung.py) auf, zeigt aber
pro Zug den Simulationsstatus:
  - DUNKELBLAU:   Zug mit ZUB+, Ausfall → trivial (t=0), keine Sim nötig
  - GRAU:         Zug ohne ZUB+, Ausfall → trivial weil schon simuliert (Duplikat)
  - ROT:          Zug ohne ZUB+, Ausfall → MUSS simuliert werden (neue Sim)
  - HELLBLAU:     Zug mit ZUB+, aber Ausfall eines anderen Zugs mit gleichem Gap
                  wurde schon simuliert → Duplikat

Jeder Mini-Quadrat in der Zelle repräsentiert einen AUSFALLENDEN Zug.
Die Farbe zeigt ob dessen Ausfall simuliert werden muss.

Stil und Speicherung über thesis_style.

Verwendung:
    python3 ZUB_Simulationsbedarf.py
    python3 ZUB_Simulationsbedarf.py --max-trains 8
"""

import csv
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zub_verteilung import distribute_zub
from zub_simulation_bedarf import analyze_simulation_need

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style as ts

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


COLOR_TRIVIAL_OCC   = ts.COLOR_PRIMARY_DARK
COLOR_TRIVIAL_UNOCC = ts.COLOR_GRID
COLOR_NEW_SIM       = ts.COLOR_COMPARE
COLOR_NEW_SIM_EDGE  = '#7A1018'
COLOR_NONEXIST      = '#FFFFFF'
COLOR_CELL_BG       = '#FAFAFA'
COLOR_CELL_BORDER   = '#CCCCCC'
COLOR_OVERLOAD_BG   = '#FDECEC'
COLOR_OVERLOAD_BORDER = ts.COLOR_COMPARE
COLOR_NEW_CELL_BG   = '#FFF5F0'

TOLERANCE_S = 5.0


def read_capacity_limit(csv_path: Path) -> tuple[int, float]:
    deltas: dict[int, float] = {}
    basis = None
    with open(csv_path) as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            n = int(row['num_trains'])
            delta = float(row['delta_to_basis_s'])
            if n == 1:
                basis = float(row['mean_lap_time_s'])
            if n not in deltas:
                deltas[n] = delta
    if basis is None:
        raise ValueError(f"Keine Baseline in {csv_path}")
    max_ok = max(n for n, d in deltas.items() if d <= TOLERANCE_S)
    return max_ok, basis


def find_latest_csv() -> Path:
    output_dir = Path(__file__).resolve().parents[2] / "output" / "umlaufzeit_tests"
    csvs = sorted(output_dir.glob("umlaufzeit_*.csv"))
    if not csvs:
        raise FileNotFoundError(f"Keine CSV in {output_dir}")
    return csvs[-1]


manual_max = None
csv_path = None

if '--max-trains' in sys.argv:
    idx = sys.argv.index('--max-trains')
    if idx + 1 < len(sys.argv):
        manual_max = int(sys.argv[idx + 1])

if '--csv' in sys.argv:
    idx = sys.argv.index('--csv')
    if idx + 1 < len(sys.argv):
        csv_path = Path(sys.argv[idx + 1])


if manual_max is not None:
    MAX_OK = manual_max - 1
    MAX_TRAINS = manual_max
    overload_col = None
    print(f"Manuell: MAX_TRAINS = {MAX_TRAINS}")
else:
    if csv_path is None:
        csv_path = find_latest_csv()
    MAX_OK, basis = read_capacity_limit(csv_path)
    MAX_TRAINS = MAX_OK + 1
    overload_col = MAX_TRAINS
    print(f"CSV: {csv_path.name}")
    print(f"Max. Züge ohne Überlast: {MAX_OK}")
    print(f"Erste Überlast bei: {MAX_TRAINS} Zügen")


result = analyze_simulation_need(MAX_TRAINS)
stats = result['stats']
print(f"\nSimulationsbedarf:")
print(f"  Gesamt:      {stats['total_failure_cases']}")
print(f"  Trivial:     {stats['trivial_cases']}")
print(f"  Einzigartig: {stats['unique_simulations']} (müssen simuliert werden)")
print(f"  Duplikate:   {stats['duplicate_cases']}")
print(f"  Einsparung:  {stats['savings_percent']:.1f}%")


def best_mini_grid(n):
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows

MINI_COLS, MINI_ROWS = best_mini_grid(MAX_TRAINS)
print(f"Mini-Raster: {MINI_COLS}×{MINI_ROWS}")


MINI_SIZE = 0.18
MINI_GAP = 0.03
CELL_PAD = 0.12

CELL_W = CELL_PAD * 2 + MINI_COLS * MINI_SIZE + (MINI_COLS - 1) * MINI_GAP
CELL_H = CELL_PAD * 2 + MINI_ROWS * MINI_SIZE + (MINI_ROWS - 1) * MINI_GAP
CELL_MARGIN = 0.08

ts.apply_style()
fig, ax = plt.subplots(figsize=(6.3, 6.0))

STEP_X = CELL_W + CELL_MARGIN
STEP_Y = CELL_H + CELL_MARGIN


for n_trains in range(1, MAX_TRAINS + 1):
    col = n_trains - 1
    cx = col * STEP_X

    for n_zub in range(1, n_trains + 1):
        row = n_zub - 1
        cy = row * STEP_Y

        scenario = result['scenarios'][(n_trains, n_zub)]
        is_overload = (n_trains == overload_col)
        has_new = scenario['new_sims'] > 0

        if is_overload:
            bg = COLOR_OVERLOAD_BG
            bc = COLOR_OVERLOAD_BORDER
            blw = 1.2
            bls = '--'
        elif has_new:
            bg = COLOR_NEW_CELL_BG
            bc = COLOR_NEW_SIM
            blw = 0.8
            bls = '-'
        else:
            bg = COLOR_CELL_BG
            bc = COLOR_CELL_BORDER
            blw = 0.5
            bls = '-'

        rect = mpatches.FancyBboxPatch(
            (cx, cy), CELL_W, CELL_H,
            boxstyle='round,pad=0.02',
            facecolor=bg, edgecolor=bc,
            linewidth=blw, linestyle=bls,
            zorder=1
        )
        ax.add_patch(rect)

        if has_new and MAX_TRAINS <= 15:
            ax.text(cx + CELL_W / 2, cy - 0.02,
                    f'{scenario["new_sims"]}',
                    ha='center', va='top', fontsize=6,
                    fontweight='bold', color=COLOR_NEW_SIM, zorder=10)

        failures = scenario['failures']

        for train_idx in range(MINI_COLS * MINI_ROWS):
            mini_col = train_idx % MINI_COLS
            mini_row = MINI_ROWS - 1 - (train_idx // MINI_COLS)

            mx = cx + CELL_PAD + mini_col * (MINI_SIZE + MINI_GAP)
            my = cy + CELL_PAD + mini_row * (MINI_SIZE + MINI_GAP)

            if train_idx >= n_trains:
                color = COLOR_NONEXIST
                ec = '#EEEEEE'
                lw = 0.3
            else:
                failure = failures[train_idx]
                if failure['is_trivial']:
                    color = COLOR_TRIVIAL_OCC
                    ec = COLOR_TRIVIAL_OCC
                    lw = 0.5
                elif failure['needs_sim']:
                    color = COLOR_NEW_SIM
                    ec = COLOR_NEW_SIM_EDGE
                    lw = 0.8
                else:
                    color = COLOR_TRIVIAL_UNOCC
                    ec = '#999999'
                    lw = 0.5

            sq = mpatches.FancyBboxPatch(
                (mx, my), MINI_SIZE, MINI_SIZE,
                boxstyle='round,pad=0.01',
                facecolor=color, edgecolor=ec, linewidth=lw,
                zorder=3
            )
            ax.add_patch(sq)

            if (train_idx < n_trains and not failures[train_idx]['is_trivial']
                    and failures[train_idx]['needs_sim'] and MAX_TRAINS <= 10):
                ax.text(mx + MINI_SIZE / 2, my + MINI_SIZE / 2,
                        str(failures[train_idx]['gap']),
                        ha='center', va='center', fontsize=5,
                        fontweight='bold', color='white', zorder=5)


for n_trains in range(1, MAX_TRAINS + 1):
    cx = (n_trains - 1) * STEP_X
    for n_zub in range(n_trains + 1, MAX_TRAINS + 1):
        cy = (n_zub - 1) * STEP_Y
        rect = mpatches.FancyBboxPatch(
            (cx, cy), CELL_W, CELL_H,
            boxstyle='round,pad=0.02',
            facecolor='#F8F8F8', edgecolor='#EEEEEE',
            linewidth=0.3, zorder=0
        )
        ax.add_patch(rect)


tick_step = 1 if MAX_TRAINS <= 15 else (2 if MAX_TRAINS <= 30 else 5)

ax.set_xticks([i * STEP_X + CELL_W / 2 for i in range(0, MAX_TRAINS, tick_step)])
ax.set_xticklabels([f'{i + 1}' for i in range(0, MAX_TRAINS, tick_step)])
ax.set_xlabel('Anzahl Züge auf der Strecke')

ax.set_yticks([i * STEP_Y + CELL_H / 2 for i in range(0, MAX_TRAINS, tick_step)])
ax.set_yticklabels([f'{i + 1}' for i in range(0, MAX_TRAINS, tick_step)])
ax.set_ylabel('Anzahl ZUB+')

ax.set_xlim(-0.3, MAX_TRAINS * STEP_X)
ax.set_ylim(-0.3, MAX_TRAINS * STEP_Y + 0.2)
ax.set_aspect('equal')


legend_elements = [
    mpatches.Patch(facecolor=COLOR_NEW_SIM, edgecolor=COLOR_NEW_SIM_EDGE,
                   label='Neue Simulation nötig'),
    mpatches.Patch(facecolor=COLOR_TRIVIAL_OCC, edgecolor=COLOR_TRIVIAL_OCC,
                   label=r'ZUB+ an Bord ($t_{\mathrm{I}} = 0$)'),
    mpatches.Patch(facecolor=COLOR_TRIVIAL_UNOCC, edgecolor='#999999',
                   label='Duplikat (gleicher Gap)'),
    mpatches.Patch(facecolor=COLOR_NONEXIST, edgecolor='#EEEEEE',
                   label='Zug existiert nicht'),
]
if overload_col is not None:
    legend_elements.append(
        mpatches.Patch(facecolor=COLOR_OVERLOAD_BG, edgecolor=COLOR_OVERLOAD_BORDER,
                       linestyle='--', label=f'Überlast (ab {overload_col} Zügen)')
    )
legend_elements.append(
    mpatches.Patch(facecolor=COLOR_NEW_CELL_BG, edgecolor=COLOR_NEW_SIM,
                   label='Zelle enthält neue Simulationen')
)

leg = ax.legend(handles=legend_elements, loc='upper left',
                frameon=True, facecolor='white',
                framealpha=1.0, edgecolor=ts.COLOR_GRID,
                ncol=1, handletextpad=0.6, borderpad=0.6)
leg.get_frame().set_linewidth(0.6)


output_dir = Path(__file__).resolve().parents[2] / "Diagramme"
ts.save_fig(fig, output_dir, "ZUB_Simulationsbedarf")
plt.close(fig)
