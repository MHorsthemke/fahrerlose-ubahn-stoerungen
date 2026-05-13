"""
ZUB_Verteilung.py — Visualisierung der ZUB+-Verteilung auf Züge.

Liest automatisch die neueste Umlaufzeit-CSV aus output/umlaufzeit_tests/
und bestimmt daraus die maximale Zuganzahl ohne Überlast (n) sowie die
erste überlastete Kombination (n+1).

Layout: Jede Zelle der (Zuganzahl × ZUB+)-Matrix wird in ein einheitliches
Mini-Raster (z.B. 7×4 = 28 Positionen) unterteilt. Jede Position = 1 Zug.
Blau = ZUB+ an Bord, grau = ohne ZUB+, weiß = Zug existiert nicht.

Verwendung:
    python3 ZUB_Verteilung.py
    python3 ZUB_Verteilung.py --max-trains 8
    python3 ZUB_Verteilung.py --csv path/to/file.csv
"""

import csv
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zub_verteilung import distribute_zub

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams

# ===================================================================
# FONT
# ===================================================================
rcParams['font.family'] = 'sans-serif'
rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
rcParams['font.size'] = 11
rcParams['axes.labelsize'] = 12
rcParams['axes.titlesize'] = 14

# ===================================================================
# FARBEN
# ===================================================================
COLOR_OCCUPIED = '#2F5496'
COLOR_EMPTY = '#D9D9D9'
COLOR_NONEXIST = '#FFFFFF'
COLOR_TRIVIAL_BG = '#E8F0E8'
COLOR_OVERLOAD_BG = '#FDECEC'
COLOR_OVERLOAD_BORDER = '#E06060'
COLOR_CELL_BORDER = '#CCCCCC'

TOLERANCE_S = 5.0


# ===================================================================
# UMLAUFZEIT-CSV EINLESEN
# ===================================================================
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
        raise ValueError(f"Keine Baseline (1 Zug) in {csv_path}")
    max_ok = max(n for n, d in deltas.items() if d <= TOLERANCE_S)
    return max_ok, basis


def find_latest_csv() -> Path:
    output_dir = Path(__file__).resolve().parents[2] / "output" / "umlaufzeit_tests"
    csvs = sorted(output_dir.glob("umlaufzeit_*.csv"))
    if not csvs:
        raise FileNotFoundError(f"Keine CSV in {output_dir}")
    return csvs[-1]


# ===================================================================
# CLI
# ===================================================================
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

# ===================================================================
# KAPAZITÄTSGRENZE BESTIMMEN
# ===================================================================
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
    print(f"Basis-Umlaufzeit: {basis:.1f}s")
    print(f"Max. Züge ohne Überlast: {MAX_OK}")
    print(f"Erste Überlast bei: {MAX_TRAINS} Zügen")

# ===================================================================
# MINI-RASTER BERECHNEN
# ===================================================================
# Optimale Aufteilung: möglichst quadratisch, aber Spalten >= Zeilen
def best_mini_grid(n):
    """Berechne (cols, rows) für n Positionen, möglichst quadratisch."""
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows

MINI_COLS, MINI_ROWS = best_mini_grid(MAX_TRAINS)
print(f"Mini-Raster: {MINI_COLS} Spalten × {MINI_ROWS} Zeilen = {MINI_COLS * MINI_ROWS} Positionen (für {MAX_TRAINS} Züge)")

# ===================================================================
# ABMESSUNGEN
# ===================================================================
# Größe einer Mini-Zelle (ein Zug)
MINI_SIZE = 0.18        # Seitenlänge eines Mini-Quadrats
MINI_GAP = 0.03         # Abstand zwischen Mini-Quadraten
CELL_PAD = 0.12         # Padding innerhalb der Hauptzelle

# Hauptzell-Größe (berechnet)
CELL_W = CELL_PAD * 2 + MINI_COLS * MINI_SIZE + (MINI_COLS - 1) * MINI_GAP
CELL_H = CELL_PAD * 2 + MINI_ROWS * MINI_SIZE + (MINI_ROWS - 1) * MINI_GAP
CELL_MARGIN = 0.08      # Abstand zwischen Hauptzellen

# Figsize
total_w = MAX_TRAINS * (CELL_W + CELL_MARGIN) + 4.0
total_h = MAX_TRAINS * (CELL_H + CELL_MARGIN) + 3.0
# Begrenzung
total_w = min(total_w, 60)
total_h = min(total_h, 45)

print(f"Zellgröße: {CELL_W:.2f} × {CELL_H:.2f}")
print(f"Figsize: {total_w:.1f} × {total_h:.1f}")

fig, ax = plt.subplots(figsize=(total_w, total_h))

# ===================================================================
# ZEICHNEN
# ===================================================================
STEP_X = CELL_W + CELL_MARGIN
STEP_Y = CELL_H + CELL_MARGIN

for n_trains in range(1, MAX_TRAINS + 1):
    col = n_trains - 1
    cx = col * STEP_X   # linke Kante der Hauptzelle

    for n_zub in range(1, n_trains + 1):
        row = n_zub - 1
        cy = row * STEP_Y

        is_trivial = (n_zub == n_trains)
        is_overload = (n_trains == overload_col)

        # Hauptzell-Hintergrund
        if is_overload:
            bg_color = COLOR_OVERLOAD_BG
            border_color = COLOR_OVERLOAD_BORDER
            border_lw = 1.2
            border_ls = '--'
        elif is_trivial:
            bg_color = COLOR_TRIVIAL_BG
            border_color = '#AAAAAA'
            border_lw = 0.6
            border_ls = '-'
        else:
            bg_color = '#FAFAFA'
            border_color = COLOR_CELL_BORDER
            border_lw = 0.5
            border_ls = '-'

        rect = mpatches.FancyBboxPatch(
            (cx, cy), CELL_W, CELL_H,
            boxstyle='round,pad=0.02',
            facecolor=bg_color, edgecolor=border_color,
            linewidth=border_lw, linestyle=border_ls,
            zorder=1
        )
        ax.add_patch(rect)

        # ZUB+-Verteilung
        occupied = set(distribute_zub(n_trains, n_zub))

        # Mini-Quadrate zeichnen
        for train_idx in range(MINI_COLS * MINI_ROWS):
            mini_col = train_idx % MINI_COLS
            mini_row = MINI_ROWS - 1 - (train_idx // MINI_COLS)  # von oben nach unten

            mx = cx + CELL_PAD + mini_col * (MINI_SIZE + MINI_GAP)
            my = cy + CELL_PAD + mini_row * (MINI_SIZE + MINI_GAP)

            if train_idx >= n_trains:
                # Zug existiert nicht
                color = COLOR_NONEXIST
                ec = '#EEEEEE'
                lw = 0.3
            elif train_idx in occupied:
                color = COLOR_OCCUPIED
                ec = COLOR_OCCUPIED
                lw = 0.5
            else:
                color = COLOR_EMPTY
                ec = '#BBBBBB'
                lw = 0.5

            sq = mpatches.FancyBboxPatch(
                (mx, my), MINI_SIZE, MINI_SIZE,
                boxstyle='round,pad=0.01',
                facecolor=color, edgecolor=ec, linewidth=lw,
                zorder=3
            )
            ax.add_patch(sq)

# --- Nicht-gültige Zellen (num_zub > num_trains): leicht markieren ---
for n_trains in range(1, MAX_TRAINS + 1):
    col = n_trains - 1
    cx = col * STEP_X
    for n_zub in range(n_trains + 1, MAX_TRAINS + 1):
        row = n_zub - 1
        cy = row * STEP_Y
        rect = mpatches.FancyBboxPatch(
            (cx, cy), CELL_W, CELL_H,
            boxstyle='round,pad=0.02',
            facecolor='#F8F8F8', edgecolor='#EEEEEE',
            linewidth=0.3, zorder=0
        )
        ax.add_patch(rect)

# ===================================================================
# ACHSEN
# ===================================================================
# X-Achse: Zuganzahl
tick_step = 1 if MAX_TRAINS <= 15 else (2 if MAX_TRAINS <= 30 else 5)
tick_fs = 10 if MAX_TRAINS <= 15 else (8 if MAX_TRAINS <= 30 else 7)

x_ticks = [i * STEP_X + CELL_W / 2 for i in range(0, MAX_TRAINS, tick_step)]
x_labels = [f'{i + 1}' for i in range(0, MAX_TRAINS, tick_step)]
ax.set_xticks(x_ticks)
ax.set_xticklabels(x_labels, fontsize=tick_fs)
ax.set_xlabel('Anzahl Züge auf der Strecke', fontsize=12, fontweight='bold', labelpad=10)

# Y-Achse: ZUB+-Anzahl
y_ticks = [i * STEP_Y + CELL_H / 2 for i in range(0, MAX_TRAINS, tick_step)]
y_labels = [f'{i + 1}' for i in range(0, MAX_TRAINS, tick_step)]
ax.set_yticks(y_ticks)
ax.set_yticklabels(y_labels, fontsize=tick_fs)
ax.set_ylabel('Anzahl ZUB+', fontsize=12, fontweight='bold', labelpad=10)

# Limits
ax.set_xlim(-0.3, MAX_TRAINS * STEP_X)
ax.set_ylim(-0.3, MAX_TRAINS * STEP_Y + 0.5)
ax.set_aspect('equal')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# Titel
ax.set_title(
    f'ZUB+-Verteilung — 1 bis {MAX_OK} Züge + Überlast ({MAX_TRAINS})\n'
    f'Jede Zelle: {MINI_COLS}×{MINI_ROWS} Raster, 1 Feld = 1 Zug',
    fontsize=14, fontweight='bold', pad=15
)

# ===================================================================
# LEGENDE
# ===================================================================
legend_elements = [
    mpatches.Patch(facecolor=COLOR_OCCUPIED, edgecolor=COLOR_OCCUPIED,
                   label='Zug mit ZUB+'),
    mpatches.Patch(facecolor=COLOR_EMPTY, edgecolor='#BBBBBB',
                   label='Zug ohne ZUB+'),
    mpatches.Patch(facecolor=COLOR_NONEXIST, edgecolor='#EEEEEE',
                   label='Zug existiert nicht'),
    mpatches.Patch(facecolor=COLOR_TRIVIAL_BG, edgecolor='#AAAAAA',
                   label='Trivialfall ($t_{Intervention}$ = 0)'),
]
if overload_col is not None:
    legend_elements.append(
        mpatches.Patch(facecolor=COLOR_OVERLOAD_BG, edgecolor=COLOR_OVERLOAD_BORDER,
                       linestyle='--', label=f'Überlast (ab {overload_col} Zügen)')
    )

ax.legend(handles=legend_elements, loc='upper left', fontsize=10,
          framealpha=0.95, edgecolor='#CCCCCC')

plt.tight_layout()

# ===================================================================
# SPEICHERN
# ===================================================================
output_dir = Path(__file__).resolve().parents[2] / "Diagramme"
output_dir.mkdir(parents=True, exist_ok=True)
out_pdf = output_dir / "ZUB_Verteilung.pdf"
out_svg = output_dir / "ZUB_Verteilung.svg"
fig.savefig(str(out_pdf), format='pdf', bbox_inches='tight', dpi=300)
fig.savefig(str(out_svg), format='svg', bbox_inches='tight')
print(f"\nPDF: {out_pdf}")
print(f"SVG: {out_svg}")
