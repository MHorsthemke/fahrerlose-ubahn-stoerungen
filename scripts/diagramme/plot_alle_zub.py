"""
plot_alle_zub.py — Erzeugt alle ZUB+-Diagramme für Kap. 5.2.

Aufbau parallel zu den SA-Plot-Skripten (plot_statistik_intervention.py,
plot_cdf_intervention.py, ...). Unterschiede:

  - Input: die rohe Konvergenz-CSV conv_zub_0050m.csv
  - Expansion auf (num_trains, num_zub, train_idx, position) via zub_expand.py
  - Hauptauswertung bei fester Zuganzahl N_TRAINS (Default 10)
  - Zusätzlich drei ZUB+-spezifische Plots: Gap-Heatmap, Matrix-Heatmap,
    AGBF-Kurvenschar

Ausgabe-Dateien in Diagramme/:
  Statistik_Interventionszeit_ZUB.{pdf,svg}
  CDF_Interventionszeit_ZUB.{pdf,svg}
  CDF_Saturation_ZUB.{pdf,svg}
  NestedLoop_ZUB.{pdf,svg}
  Trellis_CDF_ZUB.{pdf,svg}
  Parallel_Coordinates_ZUB.{pdf,svg}
  Heatmap_Interventionszeit_ZUB.{pdf,svg}
  Diminishing_Returns_ZUB.{pdf,svg}
  Delta_Allgemein_ZUB.{pdf,svg}
  Delta_Interventionszeit_ZUB.{pdf,svg}
  Heatmap_Gap_ZUB.{pdf,svg}
  Heatmap_Matrix_ZUB.{pdf,svg}
  AGBF_Kurvenschar_ZUB.{pdf,svg}

Verwendung:
    python3 plot_alle_zub.py [pfad_zur_conv_zub_csv] [num_trains=10]
"""

import sys
import csv
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import MultipleLocator
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.gridspec import GridSpec

# Eigene Module
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zub_expand import load_raw, expand, find_latest_conv_csv
from zub_verteilung import distribute_zub
from sa_distribution import distribute_agents
from stations import STATIONS, WENDEPUNKT_RECHTS

# Thesis-Style-Helper (gleiche Defaults wie die SA-Plot-Skripte)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style as ts


# ===================================================================
# STYLE (konsistent mit SA-Skripten)
# ===================================================================
rcParams['font.family'] = 'sans-serif'
rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
rcParams['font.size'] = 11
rcParams['axes.labelsize'] = 12
rcParams['axes.titlesize'] = 14
rcParams['xtick.labelsize'] = 10
rcParams['ytick.labelsize'] = 11
rcParams['pdf.fonttype'] = 42
rcParams['savefig.facecolor'] = 'white'

COLOR_BOX     = '#4472C4'
COLOR_MEDIAN  = '#ED7D31'
COLOR_MEAN    = '#2F5496'
COLOR_WHISKER = '#333333'
COLOR_FLIER   = '#A5A5A5'
COLOR_MAX     = '#C00000'
COLOR_MIN     = '#70AD47'

# Farben für 1..N ZUB+ (10 Stufen, konsistent mit CDF der SA-Plots)
COLORS_10 = [
    '#4472C4', '#ED7D31', '#A5A5A5', '#FFC000', '#5B9BD5',
    '#70AD47', '#264478', '#9B59B6', '#E74C3C', '#2F5496',
]

AGBF_MINUTES = 10
AGBF_TARGET_PCT = 90.0


# ===================================================================
# DATEN AUFBEREITEN
# ===================================================================
def group_by_num_zub(rows: list[dict]) -> dict[int, list[float]]:
    """{num_zub: [t_minutes, ...]}"""
    out = defaultdict(list)
    for r in rows:
        out[r['num_zub']].append(r['t_intervention_total_s'] / 60.0)
    return dict(out)


def group_by_pos_numzub(rows: list[dict]) -> dict[tuple[float, int], list[float]]:
    """{(position, num_zub): [t_minutes]}  (mehrere train_idx aggregiert)"""
    out = defaultdict(list)
    for r in rows:
        out[(r['disruption_position_m'], r['num_zub'])].append(r['t_intervention_total_s'] / 60.0)
    return dict(out)


def compute_stats(data: dict[int, list[float]]) -> dict:
    ks = sorted(data.keys())
    return {
        'k': ks,
        'mean':   [float(np.mean(data[k])) for k in ks],
        'median': [float(np.median(data[k])) for k in ks],
        'max':    [float(np.max(data[k])) for k in ks],
        'min':    [float(np.min(data[k])) for k in ks],
        'std':    [float(np.std(data[k], ddof=1)) if len(data[k]) > 1 else 0.0 for k in ks],
        'n':      [len(data[k]) for k in ks],
    }


# ===================================================================
# 1) BOXPLOT (Statistik_Interventionszeit_ZUB.pdf)
# ===================================================================
def plot_boxplot(data: dict[int, list[float]], stats: dict,
                 n_trains: int, output_dir: Path):
    """
    Boxplot der Interventionszeit nach Anzahl ZUB+ bei festem N_Zug.
    Stil identisch zum SA-Boxplot (plot_statistik_intervention.py), damit
    beide direkt vergleichbar sind: gleiche y-Achse, gleiche Schriftgrößen,
    gleiche Legenden-Position.
    """
    ts.apply_style()
    ks = sorted(data.keys())
    box_data = [np.array(data[k]) for k in ks]
    means = np.array(stats['mean'])
    maxs = np.array(stats['max'])
    stds = np.array(stats['std'])

    fig, ax = plt.subplots(figsize=ts.FIGSIZE_DEFAULT)

    bp = ax.boxplot(
        box_data,
        positions=range(1, len(ks) + 1),
        widths=0.55,
        patch_artist=True,
        showmeans=False,
        showfliers=False,
        whis=(0, 100),
    )

    for patch in bp['boxes']:
        patch.set_facecolor(ts.COLOR_PRIMARY_SOFT)
        patch.set_alpha(0.55)
        patch.set_edgecolor(ts.COLOR_PRIMARY)
        patch.set_linewidth(1.0)
    for line in bp['medians']:
        line.set_color(ts.COLOR_ACCENT)
        line.set_linewidth(1.6)
    for whisker in bp['whiskers']:
        whisker.set_color(ts.COLOR_NEUTRAL)
        whisker.set_linewidth(0.8)
        whisker.set_linestyle((0, (3, 2)))
    for cap in bp['caps']:
        cap.set_color(ts.COLOR_NEUTRAL)
        cap.set_linewidth(0.8)

    x_positions = list(range(1, len(ks) + 1))
    ax.scatter(x_positions, means, marker='D', s=22, color=ts.COLOR_PRIMARY,
               edgecolors='white', linewidths=0.6, zorder=5, label='Mittelwert')

    for i, k in enumerate(ks):
        ax.text(i + 1, maxs[i] + 0.6,
                rf'$\bar{{x}}{{=}}{means[i]:.1f}$' '\n' rf'$\sigma{{=}}{stds[i]:.1f}$',
                ha='center', va='bottom', fontsize=8, color=ts.COLOR_MUTED,
                linespacing=1.05)

    ts.setup_count_axis(ax, axis='x', label='Anzahl ZUB+')
    ts.setup_time_axis(ax, axis='y')
    ts.add_grid(ax, axis='y')

    legend_elements = [
        Patch(facecolor=ts.COLOR_PRIMARY_SOFT, alpha=0.55, edgecolor=ts.COLOR_PRIMARY,
              label='Q1–Q3'),
        Line2D([0], [0], color=ts.COLOR_ACCENT, linewidth=1.6, label='Median'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor=ts.COLOR_PRIMARY,
               markersize=6, label='Mittelwert', linestyle='None'),
        Line2D([0], [0], color=ts.COLOR_NEUTRAL, linewidth=0.8, linestyle=(0, (3, 2)),
               label='Min/Max'),
    ]
    ts.place_legend_below(ax, ncol=4, handles=legend_elements)

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Statistik_Interventionszeit_ZUB')
    plt.close(fig)


# ===================================================================
# 2) CDF (CDF_Interventionszeit_ZUB.pdf)
# ===================================================================
def plot_cdf(data: dict[int, list[float]], n_trains: int, output_dir: Path):
    ts.apply_style()
    fig = plt.figure(figsize=(6.3, 4.6))
    gs = GridSpec(2, 1, height_ratios=[5.0, 0.6], hspace=0.22, figure=fig)
    ax = fig.add_subplot(gs[0])
    ax_leg = fig.add_subplot(gs[1])

    ks = sorted(data.keys())
    colors = ts.cmap_categorical(len(ks))
    for i, k in enumerate(ks):
        vals = np.sort(data[k])
        n = len(vals)
        cdf_y = np.arange(1, n + 1) / n * 100
        ax.step(vals, cdf_y, where='post',
                color=colors[i], linewidth=1.4,
                label=f'{k}')

    ts.setup_time_axis(ax, axis='x')
    ts.setup_percent_axis(ax, axis='y')
    ts.add_grid(ax, axis='both')
    ts.add_agbf_marker(ax, axis='x', label=True)

    rows_legend = [
        ('Anzahl ZUB+', [
            dict(color=colors[i], linewidth=2.0)
            for i in range(len(ks))
        ]),
    ]
    ts.draw_matrix_legend(ax_leg, len(ks), rows_legend)

    ts.save_fig(fig, output_dir, 'CDF_Interventionszeit_ZUB')
    plt.close(fig)


# ===================================================================
# 2b) CDF mit Strichmuster-Codierung (CDF_Saturation_ZUB.pdf)
#     Farbe       = num_zub (1..10)      — qualitative Palette (tab10)
#     Strichmuster = num_trains (1..10)  — 10 Dash-Stufen, N=10 solid
#     Damit alle vier Dimensionen (N_Zug, N_ZUB+, Position, Train_Idx)
#     in einem Diagramm ohne Verwechslung zwischen Blautönen.
# ===================================================================
# tab10 — qualitative Palette ohne mehrere Blautöne (nur tab:blue als einziger Blauton)
COLORS_QUAL = [
    '#1f77b4',  # 1  Blau
    '#ff7f0e',  # 2  Orange
    '#2ca02c',  # 3  Grün
    '#d62728',  # 4  Rot
    '#9467bd',  # 5  Lila
    '#8c564b',  # 6  Braun
    '#e377c2',  # 7  Pink
    '#7f7f7f',  # 8  Grau
    '#bcbd22',  # 9  Oliv
    '#17becf',  # 10 Cyan
]

# 10 Strichmuster, mit zunehmender Dichte/Länge — N=10 als Referenz solid
DASH_PATTERNS = {
    1:  (0, (1, 3)),              # sehr gepunktet
    2:  (0, (2, 3)),              # kurz gestrichelt
    3:  (0, (4, 3)),              # mittel gestrichelt
    4:  (0, (7, 3)),              # lang gestrichelt
    5:  (0, (12, 3)),             # sehr lang gestrichelt
    6:  (0, (3, 2, 1, 2)),        # dashdot kurz
    7:  (0, (6, 2, 1, 2)),        # dashdot lang
    8:  (0, (3, 2, 1, 2, 1, 2)),  # dashdotdot
    9:  (0, (6, 2, 1, 2, 1, 2)),  # dashdotdot lang
    10: 'solid',                  # solid (Referenz)
}


def plot_cdf_saturation(raw: dict[tuple[int, int], dict[float, float]],
                        output_dir: Path):
    ts.apply_style()
    n_trains_all = sorted(set(n for (n, _) in raw.keys()))
    selected_n = n_trains_all

    fig = plt.figure(figsize=(6.3, 5.0))
    gs = GridSpec(2, 1, height_ratios=[5.0, 0.9], hspace=0.22, figure=fig)
    ax = fig.add_subplot(gs[0])
    ax_leg = fig.add_subplot(gs[1])

    max_k = max(selected_n)
    colors = ts.cmap_categorical(max_k)

    for n in selected_n:
        ls = DASH_PATTERNS.get(n, 'solid')
        rows_n = expand(raw, n)
        by_nz = group_by_num_zub(rows_n)
        for k in sorted(by_nz.keys()):
            color = colors[k - 1]
            vals = np.sort(by_nz[k])
            m = len(vals)
            if m == 0:
                continue
            cdf_y = np.arange(1, m + 1) / m * 100
            ax.step(vals, cdf_y, where='post', color=color, linestyle=ls,
                    linewidth=1.0, alpha=0.85, zorder=3)

    ts.setup_time_axis(ax, axis='x')
    ts.setup_percent_axis(ax, axis='y')
    ts.add_grid(ax, axis='both')
    ts.add_agbf_marker(ax, axis='x', label=True)

    rows_legend = [
        ('Anzahl ZUB+', [
            dict(color=colors[i], linewidth=2.0)
            for i in range(max_k)
        ]),
        ('Anzahl Züge', [
            dict(color=ts.COLOR_NEUTRAL,
                 linestyle=DASH_PATTERNS.get(i + 1, 'solid'),
                 linewidth=1.4)
            for i in range(max_k)
        ]),
    ]
    ts.draw_matrix_legend(ax_leg, max_k, rows_legend)

    ts.save_fig(fig, output_dir, 'CDF_Saturation_ZUB')
    plt.close(fig)


# ===================================================================
# 2c) NESTED LOOP PLOT (Rücker & Schwarzer 2014, BMC MRM)
#     Alle (N_Zug, N_ZUB+)-Kombinationen lexikographisch auf einer x-Achse.
#     Oberhalb: kleine Indikator-Subplots für die beiden Parameter.
#     Hauptplot: Mittelwert / Median der Interventionszeit mit p95-Band.
# ===================================================================
def plot_nested_loop(raw: dict[tuple[int, int], dict[float, float]],
                     output_dir: Path):
    ts.apply_style()

    n_trains_all = sorted(set(n for (n, _) in raw.keys()))

    # Daten pro (n, k) aggregieren
    records = []
    for n in n_trains_all:
        rows_n = expand(raw, n)
        by_nz = defaultdict(list)
        for r in rows_n:
            by_nz[r['num_zub']].append(r['t_intervention_total_s'] / 60.0)
        for k in sorted(by_nz.keys()):
            vals = np.array(by_nz[k])
            records.append({
                'n': n, 'k': k,
                'mean': float(np.mean(vals)),
                'median': float(np.median(vals)),
                'min': float(np.min(vals)),
                'max': float(np.max(vals)),
                'p95': float(np.percentile(vals, 95)),
                'p05': float(np.percentile(vals, 5)),
                'agbf_pct': 100.0 * float(np.sum(vals <= AGBF_MINUTES)) / len(vals),
            })

    # Lexikographisch sortieren: N_Zug außen, N_ZUB+ innen
    records.sort(key=lambda r: (r['n'], r['k']))
    x = np.arange(len(records))
    ns = np.array([r['n'] for r in records])
    ks = np.array([r['k'] for r in records])

    # Block-Grenzen pro N_Zug
    block_starts = [0]
    for i in range(1, len(records)):
        if records[i]['n'] != records[i - 1]['n']:
            block_starts.append(i)

    def with_breaks(y_arr):
        """NaN an Block-Übergängen einfügen, damit keine Linie zwischen
        unterschiedlichen N_Zug-Blöcken gezogen wird."""
        out_x, out_y = [], []
        for i, b in enumerate(block_starts):
            end = block_starts[i + 1] if i + 1 < len(block_starts) else len(x)
            if i > 0:
                out_x.append(np.nan)
                out_y.append(np.nan)
            out_x.extend(x[b:end])
            out_y.extend(y_arr[b:end])
        return np.array(out_x), np.array(out_y)

    fig = plt.figure(figsize=ts.FIGSIZE_NESTED)
    gs = GridSpec(4, 1, height_ratios=[0.7, 0.7, 0.7, 5.0],
                  hspace=0.18, figure=fig)
    ax_n = fig.add_subplot(gs[0])
    ax_k = fig.add_subplot(gs[1], sharex=ax_n)
    ax_a = fig.add_subplot(gs[2], sharex=ax_n)
    ax_t = fig.add_subplot(gs[3], sharex=ax_n)

    # Parameter-Indikator: N_Zug (durchgehend, weil Step-Funktion die Konfig zeigt)
    ax_n.step(x, ns, where='mid', color=ts.COLOR_PRIMARY, linewidth=1.2)
    ax_n.fill_between(x, 0, ns, step='mid', alpha=0.18,
                      color=ts.COLOR_PRIMARY)
    ax_n.set_ylabel('$N_\\text{Zug}$')
    ax_n.set_yticks([1, 5, 10])
    ax_n.set_ylim(0, 11)
    ax_n.tick_params(labelbottom=False)
    ts.add_grid(ax_n, axis='y')

    # Parameter-Indikator: N_ZUB+
    ax_k.step(x, ks, where='mid', color=ts.COLOR_ACCENT, linewidth=1.2)
    ax_k.fill_between(x, 0, ks, step='mid', alpha=0.18,
                      color=ts.COLOR_ACCENT)
    ax_k.set_ylabel('$N_\\text{ZUB+}$')
    ax_k.set_yticks([1, 5, 10])
    ax_k.set_ylim(0, 11)
    ax_k.tick_params(labelbottom=False)
    ts.add_grid(ax_k, axis='y')

    # AGBF-Erreichungsgrad (an Block-Übergängen unterbrochen)
    agbf_pct = np.array([r['agbf_pct'] for r in records])
    xb, agbf_b = with_breaks(agbf_pct)
    ax_a.plot(xb, agbf_b, 'o-', color=ts.COLOR_PRIMARY_DARK, linewidth=1.2,
              markersize=1.8)
    ax_a.axhline(AGBF_TARGET_PCT, color=ts.COLOR_NEUTRAL,
                 linewidth=0.8, linestyle=':', alpha=0.7)
    ax_a.set_ylabel('AGBF (%)')
    ax_a.set_ylim(0, 105)
    ax_a.set_yticks([0, 50, 100])
    ax_a.text(len(records) - 0.7, AGBF_TARGET_PCT - 4,
              f'{int(AGBF_TARGET_PCT)} %',
              ha='right', va='top', color=ts.COLOR_NEUTRAL, fontsize=7)
    ax_a.tick_params(labelbottom=False)
    ts.add_grid(ax_a, axis='y')

    # Hauptpanel: Interventionszeit (an Block-Übergängen unterbrochen)
    means = np.array([r['mean'] for r in records])
    mins = np.array([r['min'] for r in records])
    maxs = np.array([r['max'] for r in records])
    p95s = np.array([r['p95'] for r in records])
    xb, means_b = with_breaks(means)
    _, mins_b = with_breaks(mins)
    _, maxs_b = with_breaks(maxs)
    _, p95_b = with_breaks(p95s)

    ax_t.fill_between(xb, mins_b, maxs_b, alpha=0.12, color=ts.COLOR_PRIMARY,
                      label='Min–Max')
    ax_t.plot(xb, p95_b, '--', color=ts.COLOR_MUTED, linewidth=1.0,
              label='p95')
    ax_t.plot(xb, means_b, 'o-', color=ts.COLOR_PRIMARY, linewidth=1.4,
              markersize=1.8, label='Mittelwert')

    ts.setup_time_axis(ax_t, axis='y')
    ax_t.set_xlabel('$N_\\text{Zug}$')
    ax_t.set_xlim(-0.5, len(records) - 0.5)
    ts.add_grid(ax_t, axis='y')
    ts.add_agbf_marker(ax_t, axis='y', label=True)
    ts.place_legend_below(ax_t, ncol=3, y_offset=-0.13)

    # Block-Trennlinien
    for ax_row in (ax_n, ax_k, ax_a, ax_t):
        for bs in block_starts:
            ax_row.axvline(bs - 0.5, color=ts.COLOR_GRID,
                           linewidth=0.5, zorder=0)

    # Blocklabels unter x-Achse
    tick_positions = [(block_starts[i] + (block_starts[i + 1] - 1)) / 2
                      for i in range(len(block_starts) - 1)]
    tick_positions.append((block_starts[-1] + len(records) - 1) / 2)
    tick_labels = [str(records[bs]['n']) for bs in block_starts]
    ax_t.set_xticks(tick_positions)
    ax_t.set_xticklabels(tick_labels)


    ts.save_fig(fig, output_dir, 'NestedLoop_ZUB')
    plt.close(fig)


# ===================================================================
# 2d) TRELLIS / SMALL MULTIPLES (Becker, Cleveland & Shyu 1996)
#     Matrix aus CDF-Panels, Zeilen = N_Zug, Spalten = N_ZUB+.
# ===================================================================
def plot_trellis_cdf(raw: dict[tuple[int, int], dict[float, float]],
                     output_dir: Path):
    n_trains_all = sorted(set(n for (n, _) in raw.keys()))
    # 4 Zugzahlen × 4 ZUB+-Stufen — abgestimmt so, dass Stufen vorkommen können
    row_ns = [n for n in (3, 5, 7, 10) if n in n_trains_all]
    col_ks = [1, 2, 3, 5]

    nrows, ncols = len(row_ns), len(col_ks)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.2 * ncols, 2.5 * nrows),
                             sharex=True, sharey=True)

    for i, n in enumerate(row_ns):
        rows_n = expand(raw, n)
        by_nz = defaultdict(list)
        for r in rows_n:
            by_nz[r['num_zub']].append(r['t_intervention_total_s'] / 60.0)
        for j, k in enumerate(col_ks):
            ax = axes[i, j] if nrows > 1 else axes[j]
            if k > n:
                ax.text(0.5, 0.5, 'n. v.', transform=ax.transAxes,
                        ha='center', va='center', fontsize=10, color='#999999')
                ax.set_facecolor('#F5F5F5')
            else:
                vals = np.sort(by_nz.get(k, []))
                m = len(vals)
                if m:
                    cdf_y = np.arange(1, m + 1) / m * 100
                    ax.step(vals, cdf_y, where='post', color=COLORS_QUAL[0],
                            linewidth=1.8)
                    # AGBF-Schnittpunkt
                    pct_agbf = 100.0 * np.sum(vals <= AGBF_MINUTES) / m
                    ax.axvline(AGBF_MINUTES, color='#555555', linewidth=0.8, linestyle=':')
                    ax.axhline(AGBF_TARGET_PCT, color='#555555', linewidth=0.8, linestyle=':')
                    ax.text(0.97, 0.06, f'{pct_agbf:.0f}% $\\leq$ 10 min',
                            transform=ax.transAxes, ha='right', va='bottom',
                            fontsize=9, color='#333333',
                            bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                                      alpha=0.85, edgecolor='none'))
            ax.grid(True, alpha=0.3)
            if i == 0:
                ax.set_title(f'$N_\\text{{ZUB+}}={k}$')
            if j == 0:
                ax.set_ylabel(f'$N_\\text{{Zug}}={n}$\nKumulat. (%)', fontsize=10)
            if i == nrows - 1:
                ax.set_xlabel('$t_I$ (min)', fontsize=10)
            ax.set_xlim(0, 50)
            ax.set_ylim(0, 105)
            ax.set_yticks([0, 50, 90, 100])

    fig.suptitle('Trellis-Matrix der CDF: Zeilen = $N_\\text{Zug}$, Spalten = $N_\\text{ZUB+}$',
                 fontweight='bold', y=0.995)
    plt.tight_layout(rect=[0, 0, 1, 0.97])

    out_pdf = output_dir / 'Trellis_CDF_ZUB.pdf'
    out_svg = output_dir / 'Trellis_CDF_ZUB.svg'
    fig.savefig(out_pdf, format='pdf', bbox_inches='tight', dpi=300)
    fig.savefig(out_svg, format='svg', bbox_inches='tight')
    plt.close(fig)
    print(f'  → {out_pdf.name}')


# ===================================================================
# 2d) Parallel Coordinates (Parallel_Coordinates_ZUB.pdf)
#     Inselberg 1985 — eine Achse pro Dimension, eine Linie pro
#     Beobachtungseinheit. Hier: pro (N_Zug, N_ZUB+)-Kombination eine
#     Linie über die 5 Achsen N_Zug, N_ZUB+, Mittelwert t_I, p95 t_I,
#     AGBF-Erreichungsgrad. Farbe = N_Zug (tab10). Dies zeigt auf
#     einen Blick, welche Kombination AGBF-konform ist (AGBF-Achse > 90)
#     und welche Achsen die Interventionszeit dominieren.
# ===================================================================
def plot_parallel_coordinates(raw: dict[tuple[int, int], dict[float, float]],
                              output_dir: Path):
    ts.apply_style()
    n_trains_all = sorted(set(n for (n, _) in raw.keys()))

    records = []
    for n in n_trains_all:
        rows_n = expand(raw, n)
        by_nz = defaultdict(list)
        for r in rows_n:
            by_nz[r['num_zub']].append(r['t_intervention_total_s'] / 60.0)
        for k in sorted(by_nz.keys()):
            vals = np.array(by_nz[k])
            if vals.size == 0:
                continue
            records.append({
                'n': n,
                'k': k,
                'mean': float(np.mean(vals)),
                'p95': float(np.percentile(vals, 95)),
                'agbf': 100.0 * np.sum(vals <= AGBF_MINUTES) / vals.size,
            })

    if not records:
        print('  (keine Daten für Parallel Coordinates)')
        return

    axes_spec = [
        ('n',    r'$N_\text{Zug}$',         int),
        ('k',    r'$N_\text{ZUB+}$',         int),
        ('mean', r'$\bar{t}_I$ (min)',       float),
        ('p95',  r'$t_I^{95}$ (min)',        float),
        ('agbf', 'AGBF (%)',                 float),
    ]

    values = {key: np.array([r[key] for r in records], dtype=float)
              for key, _, _ in axes_spec}
    ranges = {key: (float(values[key].min()), float(values[key].max()))
              for key, _, _ in axes_spec}

    def norm(key, v):
        lo, hi = ranges[key]
        return 0.0 if hi == lo else (v - lo) / (hi - lo)

    colors = ts.cmap_categorical(len(n_trains_all))
    color_for_n = {n: colors[i] for i, n in enumerate(n_trains_all)}

    fig, ax = plt.subplots(figsize=ts.FIGSIZE_TALL)
    x_positions = np.arange(len(axes_spec))

    for r in sorted(records, key=lambda r: r['agbf'] >= AGBF_TARGET_PCT):
        y = [norm(key, r[key]) for key, _, _ in axes_spec]
        color = color_for_n[r['n']]
        agbf_ok = r['agbf'] >= AGBF_TARGET_PCT
        alpha = 0.85 if agbf_ok else 0.30
        lw = 1.4 if agbf_ok else 0.9
        ax.plot(x_positions, y, color=color, alpha=alpha,
                linewidth=lw, zorder=3 if agbf_ok else 2)

    agbf_idx = [i for i, (k, _, _) in enumerate(axes_spec) if k == 'agbf'][0]
    lo, hi = ranges['agbf']
    if lo <= AGBF_TARGET_PCT <= hi:
        y_agbf = (AGBF_TARGET_PCT - lo) / (hi - lo)
        ax.plot([agbf_idx - 0.18, agbf_idx + 0.18], [y_agbf, y_agbf],
                color=ts.COLOR_NEUTRAL, linewidth=1.0,
                linestyle=':', zorder=4)
        ax.text(agbf_idx + 0.20, y_agbf, '90 %', fontsize=8,
                color=ts.COLOR_NEUTRAL, va='center')

    for i, (key, _, typ) in enumerate(axes_spec):
        ax.axvline(i, color=ts.COLOR_NEUTRAL, linewidth=0.6, zorder=1)
        lo, hi = ranges[key]
        if typ is int:
            ticks = list(range(int(lo), int(hi) + 1))
        else:
            ticks = np.linspace(lo, hi, 5)
        for t in ticks:
            y_t = 0.0 if hi == lo else (t - lo) / (hi - lo)
            ax.plot([i - 0.02, i + 0.02], [y_t, y_t],
                    color=ts.COLOR_NEUTRAL, linewidth=0.6)
            txt = f'{int(t)}' if typ is int else f'{t:.1f}'
            ax.text(i - 0.05, y_t, txt, fontsize=7, ha='right', va='center',
                    color=ts.COLOR_NEUTRAL)

    ax.set_xticks(x_positions)
    ax.set_xticklabels([label for _, label, _ in axes_spec])
    ax.set_xlim(-0.5, len(axes_spec) - 0.5)
    ax.set_ylim(-0.05, 1.05)
    ax.set_yticks([])
    for spine in ('top', 'right', 'left', 'bottom'):
        ax.spines[spine].set_visible(False)

    n_handles = [
        Line2D([0], [0], color=color_for_n[n], linewidth=1.6,
               label=str(n))
        for n in n_trains_all
    ]
    style_handles = [
        Line2D([0], [0], color=ts.COLOR_NEUTRAL, linewidth=1.4, alpha=0.85,
               label=r'AGBF erfüllt ($\geq 90\,\%$)'),
        Line2D([0], [0], color=ts.COLOR_NEUTRAL, linewidth=0.9, alpha=0.30,
               label=r'AGBF verfehlt ($< 90\,\%$)'),
    ]

    leg1 = ax.legend(handles=n_handles, title=r'$N_\text{Zug}$',
                     loc='upper center', bbox_to_anchor=(0.5, -0.08),
                     ncol=len(n_trains_all), frameon=False,
                     handletextpad=0.5, columnspacing=0.8,
                     title_fontsize=8)
    ax.add_artist(leg1)
    ax.legend(handles=style_handles,
              loc='upper center', bbox_to_anchor=(0.5, -0.18),
              ncol=2, frameon=False, handletextpad=0.6, columnspacing=1.4)

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Parallel_Coordinates_ZUB')
    plt.close(fig)
    print('  → Parallel_Coordinates_ZUB.pdf')


# ===================================================================
# 3) HEATMAP Position x num_zub (Heatmap_Interventionszeit_ZUB.pdf)
# ===================================================================
def plot_heatmap_position(pos_numzub: dict[tuple[float, int], list[float]],
                          n_trains: int, output_dir: Path,
                          wendepunkt_m: float = 7388.0, step_m: float = 250.0):
    """Heatmap: Position (auf physischer Strecke) × num_zub. Hin/Rück gespiegelt & gemittelt."""
    ts.apply_style()
    umlauf_m = 2 * wendepunkt_m
    bin_edges = np.arange(0, wendepunkt_m + step_m, step_m)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    n_bins = len(bin_centers)

    zubs = sorted(set(k for (_, k) in pos_numzub.keys()))
    matrix = np.full((len(zubs), n_bins), np.nan)
    counts = np.zeros((len(zubs), n_bins))
    sums = np.zeros((len(zubs), n_bins))

    for (pos, k), tlist in pos_numzub.items():
        phys = pos if pos <= wendepunkt_m else umlauf_m - pos
        b = int(phys / step_m)
        if b >= n_bins:
            b = n_bins - 1
        i = zubs.index(k)
        for t in tlist:
            sums[i, b] += t
            counts[i, b] += 1

    mask = counts > 0
    matrix[mask] = sums[mask] / counts[mask]

    fig, ax = plt.subplots(figsize=ts.FIGSIZE_HEATMAP)
    cmap = plt.get_cmap(ts.CMAP_SEQUENTIAL)
    vmin = float(np.nanmin(matrix)) if np.any(~np.isnan(matrix)) else 0.0
    vmax = float(np.nanmax(matrix)) if np.any(~np.isnan(matrix)) else 1.0

    pos_edges = np.append(bin_centers - step_m / 2, bin_centers[-1] + step_m / 2)
    zub_edges = np.arange(0.5, len(zubs) + 1.5)
    mesh = ax.pcolormesh(pos_edges / 1000, zub_edges, matrix, cmap=cmap,
                         vmin=vmin, vmax=vmax, shading='flat')
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, aspect=22)
    cbar.set_label('Interventionszeit (min)')
    cbar.ax.tick_params(labelsize=8)

    ts.setup_position_axis(ax, axis='x')
    ax.set_ylabel('Anzahl ZUB+ $N_\\text{ZUB+}$')
    ax.set_yticks(range(1, len(zubs) + 1))
    ax.set_yticklabels([str(k) for k in zubs])
    ax.set_ylim(0.5, len(zubs) + 0.5)

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Heatmap_Interventionszeit_ZUB')
    plt.close(fig)
    print('  → Heatmap_Interventionszeit_ZUB.pdf')


# ===================================================================
# 4) DIMINISHING RETURNS (Diminishing_Returns_ZUB.pdf)
# ===================================================================
def plot_diminishing_returns(stats: dict, n_trains: int, output_dir: Path):
    ks = stats['k']
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(ks, stats['max'], marker='v', markersize=7, linewidth=2, color=COLOR_MAX, label='Maximum', zorder=4)
    ax.plot(ks, stats['mean'], marker='D', markersize=7, linewidth=2.5, color=COLOR_MEAN, label='Mittelwert', zorder=5)
    ax.plot(ks, stats['median'], marker='o', markersize=7, linewidth=2, color=COLOR_MEDIAN, label='Median', zorder=4)
    ax.plot(ks, stats['min'], marker='^', markersize=7, linewidth=2, color=COLOR_MIN, label='Minimum', zorder=4)

    for i, k in enumerate(ks):
        ax.annotate(f'{stats["mean"][i]:.1f}', xy=(k, stats['mean'][i]),
                    xytext=(0, 10), textcoords='offset points',
                    ha='center', fontsize=8, color=COLOR_MEAN, fontweight='bold')

    ax.axhline(AGBF_MINUTES, color='#999999', linewidth=1, linestyle=':', zorder=1)
    ax.text(ks[0], AGBF_MINUTES + 0.2, f'AGBF {AGBF_MINUTES} min', fontsize=8, color='#666666')

    ax.set_xlabel('Anzahl ZUB+')
    ax.set_ylabel('Interventionszeit (min)')
    ax.set_xticks(ks)
    ax.set_xlim(0.5, max(ks) + 0.5)
    ax.set_ylim(0, max(stats['max']) * 1.15 if max(stats['max']) > 0 else 5)
    ax.yaxis.grid(True, linestyle='--', alpha=0.3, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title(f'Grenznutzen zusätzlicher ZUB+ (N = {n_trains} Züge)',
                 fontweight='bold', pad=12)
    ax.text(0.98, 0.97,
            f'n = {stats["n"][0]} Ausfall-Zug/Positions-Kombinationen je Konfiguration\n'
            f'Gehgeschwindigkeit: 3,33 m/s | Reaktionszeit: 90 s',
            transform=ax.transAxes, ha='right', va='top', fontsize=9, color='#666666',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.8, edgecolor='#CCCCCC'))
    ax.legend(loc='center right', framealpha=0.9)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout()

    out_pdf = output_dir / 'Diminishing_Returns_ZUB.pdf'
    out_svg = output_dir / 'Diminishing_Returns_ZUB.svg'
    fig.savefig(out_pdf, format='pdf', bbox_inches='tight', dpi=300)
    fig.savefig(out_svg, format='svg', bbox_inches='tight')
    plt.close(fig)
    print(f'  → {out_pdf.name}')


# ===================================================================
# 5) DELTA ALLGEMEIN (Delta_Allgemein_ZUB.pdf) — quantilweise sortierte Differenz
# ===================================================================
def plot_delta_allgemein(data: dict[int, list[float]], n_trains: int, output_dir: Path):
    ts.apply_style()
    ks = sorted(data.keys())
    deltas = {}
    for i in range(len(ks) - 1):
        a, b = ks[i], ks[i + 1]
        vals_a = np.sort(data[a])
        vals_b = np.sort(data[b])
        n = min(len(vals_a), len(vals_b))
        q = np.linspace(0, 1, n)
        deltas[rf'${a}{{\to}}{b}$'] = np.quantile(vals_a, q) - np.quantile(vals_b, q)

    transitions = list(deltas.keys())
    box_data = [deltas[t] for t in transitions]

    fig, ax = plt.subplots(figsize=ts.FIGSIZE_DEFAULT)
    bp = ax.boxplot(box_data, positions=range(1, len(transitions) + 1), widths=0.55,
                    patch_artist=True, showmeans=False, showfliers=False, whis=(0, 100))
    for p in bp['boxes']:
        p.set_facecolor(ts.COLOR_PRIMARY_SOFT); p.set_alpha(0.55)
        p.set_edgecolor(ts.COLOR_PRIMARY); p.set_linewidth(1.0)
    for m in bp['medians']:
        m.set_color(ts.COLOR_ACCENT); m.set_linewidth(1.6)
    for w in bp['whiskers']:
        w.set_color(ts.COLOR_NEUTRAL); w.set_linewidth(0.8); w.set_linestyle((0, (3, 2)))
    for c in bp['caps']:
        c.set_color(ts.COLOR_NEUTRAL); c.set_linewidth(0.8)

    means = [float(np.mean(deltas[t])) for t in transitions]
    x_positions = list(range(1, len(transitions) + 1))
    ax.scatter(x_positions, means, marker='D', s=22, color=ts.COLOR_PRIMARY,
               edgecolors='white', linewidths=0.6, zorder=5, label='Mittelwert')

    for i, t in enumerate(transitions):
        s = float(np.std(deltas[t], ddof=1)) if len(deltas[t]) > 1 else 0.0
        y_top = float(np.max(deltas[t]))
        ax.text(i + 1, y_top + 0.2,
                rf'$\bar{{x}}{{=}}{means[i]:.1f}$' '\n' rf'$\sigma{{=}}{s:.1f}$',
                ha='center', va='bottom', fontsize=8, color=ts.COLOR_MUTED,
                linespacing=1.05)

    ax.axhline(y=0, color=ts.COLOR_NEUTRAL, linewidth=0.8, linestyle='-',
               zorder=1, alpha=0.6)

    ax.set_xticks(x_positions)
    ax.set_xticklabels(transitions)
    ax.set_xlim(0.4, len(transitions) + 0.6)
    ax.set_xlabel('Übergang (Anzahl ZUB+)')
    ts.setup_delta_axis(ax, axis='y', lim=(0, 16))
    from matplotlib.ticker import MultipleLocator
    ax.yaxis.set_major_locator(MultipleLocator(2))
    ax.yaxis.set_minor_locator(MultipleLocator(1))
    ts.add_grid(ax, axis='y')

    legend_elements = [
        Patch(facecolor=ts.COLOR_PRIMARY_SOFT, alpha=0.55, edgecolor=ts.COLOR_PRIMARY,
              label='Q1–Q3'),
        Line2D([0], [0], color=ts.COLOR_ACCENT, linewidth=1.6, label='Median'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor=ts.COLOR_PRIMARY,
               markersize=6, label='Mittelwert', linestyle='None'),
        Line2D([0], [0], color=ts.COLOR_NEUTRAL, linewidth=0.8, linestyle=(0, (3, 2)),
               label='Min/Max'),
    ]
    ts.place_legend_below(ax, ncol=4, handles=legend_elements)

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Delta_Allgemein_ZUB')
    plt.close(fig)


# ===================================================================
# 6) DELTA POSITIONSWEISE (Delta_Interventionszeit_ZUB.pdf)
# ===================================================================
def plot_delta_positionsweise(rows: list[dict], n_trains: int, output_dir: Path):
    # pro (train_idx, position, num_zub) Wert auslesen
    lookup = {}
    for r in rows:
        lookup[(r['disruption_train_idx'], r['disruption_position_m'], r['num_zub'])] = r['t_intervention_total_s'] / 60.0

    keys = set((ti, p) for (ti, p, _) in lookup.keys())
    ks = sorted(set(k for (_, _, k) in lookup.keys()))
    deltas = {}
    for i in range(len(ks) - 1):
        a, b = ks[i], ks[i + 1]
        label = rf'${a}{{\to}}{b}$'
        ds = []
        for (ti, p) in keys:
            va = lookup.get((ti, p, a))
            vb = lookup.get((ti, p, b))
            if va is not None and vb is not None:
                ds.append(va - vb)
        deltas[label] = np.array(ds)

    transitions = list(deltas.keys())
    box_data = [deltas[t] for t in transitions]

    ts.apply_style()
    fig, ax = plt.subplots(figsize=ts.FIGSIZE_DEFAULT)
    bp = ax.boxplot(box_data, positions=range(1, len(transitions) + 1), widths=0.55,
                    patch_artist=True, showmeans=False, showfliers=False, whis=(0, 100))
    for p in bp['boxes']:
        p.set_facecolor(ts.COLOR_PRIMARY_SOFT); p.set_alpha(0.55)
        p.set_edgecolor(ts.COLOR_PRIMARY); p.set_linewidth(1.0)
    for m in bp['medians']:
        m.set_color(ts.COLOR_ACCENT); m.set_linewidth(1.6)
    for w in bp['whiskers']:
        w.set_color(ts.COLOR_NEUTRAL); w.set_linewidth(0.8); w.set_linestyle((0, (3, 2)))
    for c in bp['caps']:
        c.set_color(ts.COLOR_NEUTRAL); c.set_linewidth(0.8)

    means = [float(np.mean(deltas[t])) for t in transitions]
    x_positions = list(range(1, len(transitions) + 1))
    ax.scatter(x_positions, means, marker='D', s=22, color=ts.COLOR_PRIMARY,
               edgecolors='white', linewidths=0.6, zorder=5, label='Mittelwert')

    for i, t in enumerate(transitions):
        s = float(np.std(deltas[t], ddof=1)) if len(deltas[t]) > 1 else 0.0
        y_top = float(np.max(deltas[t])) if len(deltas[t]) else 0.0
        ax.text(i + 1, y_top + 0.2,
                rf'$\bar{{x}}{{=}}{means[i]:.1f}$' '\n' rf'$\sigma{{=}}{s:.1f}$',
                ha='center', va='bottom', fontsize=8, color=ts.COLOR_MUTED,
                linespacing=1.05)

    ax.axhline(y=0, color=ts.COLOR_NEUTRAL, linewidth=0.8, linestyle='-',
               zorder=1, alpha=0.6)

    ax.set_xticks(x_positions)
    ax.set_xticklabels(transitions)
    ax.set_xlim(0.4, len(transitions) + 0.6)
    ax.set_xlabel('Übergang (Anzahl ZUB+)')
    ts.setup_delta_axis(ax, axis='y', lim=(-15, 20))
    from matplotlib.ticker import MultipleLocator
    ax.yaxis.set_major_locator(MultipleLocator(5))
    ax.yaxis.set_minor_locator(MultipleLocator(1))
    ts.add_grid(ax, axis='y')

    legend_elements = [
        Patch(facecolor=ts.COLOR_PRIMARY_SOFT, alpha=0.55, edgecolor=ts.COLOR_PRIMARY,
              label='Q1–Q3'),
        Line2D([0], [0], color=ts.COLOR_ACCENT, linewidth=1.6, label='Median'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor=ts.COLOR_PRIMARY,
               markersize=6, label='Mittelwert', linestyle='None'),
        Line2D([0], [0], color=ts.COLOR_NEUTRAL, linewidth=0.8, linestyle=(0, (3, 2)),
               label='Min/Max'),
    ]
    ts.place_legend_below(ax, ncol=4, handles=legend_elements)

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Delta_Interventionszeit_ZUB')
    plt.close(fig)


# ===================================================================
# 7) GAP-HEATMAP (Heatmap_Gap_ZUB.pdf) — aus ROH-Daten, über alle num_trains
# ===================================================================
def plot_heatmap_gap(raw: dict[tuple[int, int], dict[float, float]], output_dir: Path):
    ts.apply_style()
    n_trains_all = sorted(set(n for (n, _) in raw.keys()))
    gap_max = max(g for (_, g) in raw.keys())

    matrix = np.full((len(n_trains_all), gap_max + 1), np.nan)
    for (n, g), positions in raw.items():
        if not positions:
            continue
        i = n_trains_all.index(n)
        matrix[i, g] = float(np.median(list(positions.values()))) / 60.0

    fig, ax = plt.subplots(figsize=ts.FIGSIZE_HEATMAP)
    cmap = plt.get_cmap(ts.CMAP_SEQUENTIAL)
    vmax = float(np.nanmax(matrix))
    mesh = ax.pcolormesh(
        np.arange(-0.5, gap_max + 1.5),
        np.arange(0.5, len(n_trains_all) + 1.5),
        matrix, cmap=cmap, vmin=0, vmax=vmax, shading='flat',
    )
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, aspect=22)
    cbar.set_label('Median Interventionszeit (min)')
    cbar.ax.tick_params(labelsize=8)

    for i in range(len(n_trains_all)):
        for j in range(gap_max + 1):
            v = matrix[i, j]
            if not np.isnan(v):
                color = 'white' if v < vmax * 0.5 else 'black'
                ax.text(j, i + 1, f'{v:.1f}', ha='center', va='center',
                        fontsize=7, color=color)

    ax.set_xlabel('Umlauf-Gap zum nächsten ZUB+')
    ax.set_ylabel('Anzahl Züge $N_\\text{Zug}$')
    ax.set_xticks(range(gap_max + 1))
    ax.set_yticks(range(1, len(n_trains_all) + 1))
    ax.set_yticklabels([str(n) for n in n_trains_all])

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Heatmap_Gap_ZUB')
    plt.close(fig)
    print('  → Heatmap_Gap_ZUB.pdf')


# ===================================================================
# 8) MATRIX-HEATMAP num_trains × num_zub (Heatmap_Matrix_ZUB.pdf)
# ===================================================================
def plot_heatmap_matrix(raw: dict[tuple[int, int], dict[float, float]], output_dir: Path):
    """Für jedes (num_trains, num_zub)-Paar: AGBF-Erreichungsgrad aus der Expansion."""
    ts.apply_style()
    n_trains_all = sorted(set(n for (n, _) in raw.keys()))

    max_nz = max(n_trains_all)
    matrix = np.full((len(n_trains_all), max_nz), np.nan)

    for i, n in enumerate(n_trains_all):
        for k in range(1, n + 1):
            besetzt = set(distribute_zub(n, k))
            vals = []
            for train_idx in range(n):
                if train_idx in besetzt:
                    vals.extend([0.0] * 153)
                else:
                    g = min(min((train_idx - z) % n, (z - train_idx) % n) for z in besetzt)
                    positions = raw.get((n, g), {})
                    vals.extend(positions.values())
            if vals:
                arr = np.array(vals) / 60.0
                matrix[i, k - 1] = 100.0 * np.sum(arr <= AGBF_MINUTES) / len(arr)

    fig, ax = plt.subplots(figsize=ts.FIGSIZE_HEATMAP)
    cmap = plt.get_cmap(ts.CMAP_SEQUENTIAL)
    vmin = 0.0
    vmax = 100.0
    mesh = ax.pcolormesh(
        np.arange(0.5, max_nz + 1.5),
        np.arange(0.5, len(n_trains_all) + 1.5),
        matrix, cmap=cmap, vmin=vmin, vmax=vmax, shading='flat',
    )
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, aspect=22)
    cbar.set_label(f'AGBF-Erreichungsgrad (%, $t_I \\leq {AGBF_MINUTES}$ min)')
    cbar.ax.tick_params(labelsize=8)

    for i, n in enumerate(n_trains_all):
        for k in range(max_nz):
            v = matrix[i, k]
            if not np.isnan(v):
                color = 'white' if v < vmax * 0.5 else 'black'
                ax.text(k + 1, i + 1, f'{v:.0f}', ha='center', va='center',
                        fontsize=7, color=color)

    ax.set_xlabel('Anzahl ZUB+ $N_\\text{ZUB+}$')
    ax.set_ylabel('Anzahl Züge $N_\\text{Zug}$')
    ax.set_xticks(range(1, max_nz + 1))
    ax.set_yticks(range(1, len(n_trains_all) + 1))
    ax.set_yticklabels([str(n) for n in n_trains_all])

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Heatmap_Matrix_ZUB')
    plt.close(fig)
    print('  → Heatmap_Matrix_ZUB.pdf')


# ===================================================================
# 9) AGBF-KURVENSCHAR (AGBF_Kurvenschar_ZUB.pdf)
# ===================================================================
def plot_agbf_kurvenschar(raw: dict[tuple[int, int], dict[float, float]],
                          output_dir: Path, threshold_min: float = AGBF_MINUTES):
    """Anteil der Ausfälle mit t_I <= threshold pro (num_trains, num_zub)."""
    n_trains_all = sorted(set(n for (n, _) in raw.keys()))

    fig, ax = plt.subplots(figsize=(12, 7))
    for idx, n in enumerate(n_trains_all):
        xs, ys = [], []
        for k in range(1, n + 1):
            besetzt = set(distribute_zub(n, k))
            vals = []
            for train_idx in range(n):
                if train_idx in besetzt:
                    vals.extend([0.0] * 153)
                else:
                    g = min(min((train_idx - z) % n, (z - train_idx) % n) for z in besetzt)
                    vals.extend(raw.get((n, g), {}).values())
            if vals:
                arr = np.array(vals) / 60.0
                pct = 100.0 * np.sum(arr <= threshold_min) / len(arr)
                xs.append(k); ys.append(pct)
        color = COLORS_10[idx % len(COLORS_10)]
        ax.plot(xs, ys, marker='o', markersize=5, linewidth=1.8,
                color=color, label=f'{n} Züge')

    ax.axhline(AGBF_TARGET_PCT, color='#999999', linewidth=1, linestyle=':', zorder=1)
    ax.text(0.02, AGBF_TARGET_PCT + 1, f'AGBF-Erreichungsgrad {AGBF_TARGET_PCT:.0f} %',
            transform=ax.get_yaxis_transform(), fontsize=8, color='#666666')

    ax.set_xlabel('Anzahl ZUB+ $N_\\text{ZUB+}$')
    ax.set_ylabel(f'Anteil Ausfälle mit $t_I \\leq {int(threshold_min)}$ min (%)')
    ax.set_xticks(range(1, max(n_trains_all) + 1))
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.yaxis.set_minor_locator(MultipleLocator(5))
    ax.set_xlim(0.5, max(n_trains_all) + 0.5)
    ax.set_ylim(0, 105)
    ax.grid(True, which='major', alpha=0.3, linewidth=0.8)
    ax.grid(True, which='minor', alpha=0.15, linewidth=0.5)
    ax.set_title(f'AGBF-Erreichungsgrad nach ZUB+-Anzahl (Schwelle {int(threshold_min)} min)',
                 fontweight='bold', pad=12)
    ax.legend(loc='lower right', fontsize=9, ncol=2, framealpha=0.9, title='Fahrplantakt')
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    plt.tight_layout()

    out_pdf = output_dir / 'AGBF_Kurvenschar_ZUB.pdf'
    out_svg = output_dir / 'AGBF_Kurvenschar_ZUB.svg'
    fig.savefig(out_pdf, format='pdf', bbox_inches='tight', dpi=300)
    fig.savefig(out_svg, format='svg', bbox_inches='tight')
    plt.close(fig)
    print(f'  → {out_pdf.name}')


# ===================================================================
# VERGLEICHS-PLOTS SA vs. ZUB+ (für Kap. 5.3)
# Alle bei N_Zug = n_trains_fixed (Default 10) — konsistent mit 5.3-Tabellen.
# SA ist positionsbasiert und hängt nicht von N_Zug ab, daher eine CSV reicht.
# ===================================================================
def load_sa_data(sa_csv: Path) -> dict[int, list[float]]:
    """Liest parallel_*_SA.csv und gruppiert Interventionszeiten nach num_agents."""
    data: dict[int, list[float]] = defaultdict(list)
    with open(sa_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                na = int(row['num_agents'])
                t = float(row['t_intervention_total_s'])
                data[na].append(t / 60.0)
            except (ValueError, TypeError, KeyError):
                continue
    return dict(data)


def plot_vergleich_cdf(raw: dict[tuple[int, int], dict[float, float]],
                       sa_csv: Path, output_dir: Path, n_trains_fixed: int = 10):
    """CDF-Overlay SA vs. ZUB+ über alle Gruppen.
    ZUB+: Farbe = N_ZUB+ (viridis), Strichmuster = N_Zug.
    SA: schwarz, Strichmuster nach N_SA.
    """
    ts.apply_style()
    sa_data = load_sa_data(sa_csv)
    n_trains_all = sorted(set(n for (n, _) in raw.keys()))

    all_k = set()
    expanded = {}
    for n in n_trains_all:
        rows_n = expand(raw, n)
        by_nz: dict[int, list[float]] = defaultdict(list)
        for r in rows_n:
            by_nz[r['num_zub']].append(r['t_intervention_total_s'] / 60.0)
        expanded[n] = by_nz
        all_k |= set(by_nz.keys())
    max_k_zub = max(all_k) if all_k else 0
    colors = ts.cmap_categorical(max_k_zub) if max_k_zub else []

    fig = plt.figure(figsize=(6.3, 5.4))
    gs = GridSpec(2, 1, height_ratios=[5.0, 1.2], hspace=0.22, figure=fig)
    ax = fig.add_subplot(gs[0])
    ax_leg = fig.add_subplot(gs[1])

    for n in n_trains_all:
        ls = DASH_PATTERNS.get(n, 'solid')
        by_nz = expanded[n]
        for k in sorted(by_nz.keys()):
            vals = np.sort(by_nz[k])
            m = len(vals)
            if m == 0:
                continue
            cdf_y = np.arange(1, m + 1) / m * 100
            ax.step(vals, cdf_y, where='post', color=colors[k - 1],
                    linestyle=ls, linewidth=1.0, alpha=0.85, zorder=3)

    for k in sorted(sa_data.keys()):
        vals = np.sort(sa_data[k])
        m = len(vals)
        if m == 0:
            continue
        cdf_y = np.arange(1, m + 1) / m * 100
        ls = DASH_PATTERNS.get(k, 'solid')
        ax.step(vals, cdf_y, where='post', color='black', linestyle=ls,
                linewidth=1.2, alpha=0.95, zorder=4)

    ts.setup_time_axis(ax, axis='x')
    ts.setup_percent_axis(ax, axis='y')
    ts.add_grid(ax, axis='both')
    ts.add_agbf_marker(ax, axis='x', label=True)

    n_cols = max_k_zub
    rows_legend = [
        ('Anzahl ZUB+', [
            dict(color=colors[i], linewidth=2.0)
            for i in range(n_cols)
        ]),
        ('Anzahl Züge', [
            dict(color=ts.COLOR_NEUTRAL,
                 linestyle=DASH_PATTERNS.get(i + 1, 'solid'),
                 linewidth=1.4)
            for i in range(n_cols)
        ]),
        ('Anzahl SA', [
            dict(color='black',
                 linestyle=DASH_PATTERNS.get(i + 1, 'solid'),
                 linewidth=1.4)
            for i in range(n_cols)
        ]),
    ]
    ts.draw_matrix_legend(ax_leg, n_cols, rows_legend)

    ts.save_fig(fig, output_dir, 'Vergleich_CDF_SA_ZUB')
    plt.close(fig)


def plot_vergleich_agbf(raw: dict[tuple[int, int], dict[float, float]],
                        sa_csv: Path, output_dir: Path, n_trains_fixed: int = 10,
                        threshold_min: float = AGBF_MINUTES):
    """AGBF-Erreichungsgrad über Personalzahl: zwei Linien SA vs. ZUB+."""
    sa_data = load_sa_data(sa_csv)

    rows_n = expand(raw, n_trains_fixed)
    zub_data: dict[int, list[float]] = defaultdict(list)
    for r in rows_n:
        zub_data[r['num_zub']].append(r['t_intervention_total_s'] / 60.0)

    def agbf_pct(values: list[float]) -> float:
        arr = np.asarray(values)
        return 100.0 * float(np.sum(arr <= threshold_min)) / len(arr) if arr.size else np.nan

    ks = sorted(set(sa_data.keys()) | set(zub_data.keys()))
    sa_pct = [agbf_pct(sa_data.get(k, [])) for k in ks]
    zub_pct = [agbf_pct(zub_data.get(k, [])) for k in ks]

    fig, ax = plt.subplots(figsize=(11, 6.5))

    ax.plot(ks, sa_pct, marker='s', markersize=7, linewidth=2.0,
            color='black', label='SA (Stationsagenten)')
    ax.plot(ks, zub_pct, marker='o', markersize=7, linewidth=2.0,
            color=COLORS_QUAL[0], label=f'ZUB+ bei $N_\\text{{Zug}}={n_trains_fixed}$')

    ax.axhline(AGBF_TARGET_PCT, color='#888888', linewidth=1.0, linestyle=':', zorder=1)
    ax.text(0.99, AGBF_TARGET_PCT + 1.2, f'AGBF {AGBF_TARGET_PCT:.0f}%',
            transform=ax.get_yaxis_transform(), ha='right',
            fontsize=8, color='#555555')

    ax.set_xlabel('Anzahl Personal $N$')
    ax.set_ylabel(f'Anteil Ausfälle mit $t_I \\leq {int(threshold_min)}$ min (%)')
    ax.set_xticks(ks)
    ax.set_xlim(min(ks) - 0.3, max(ks) + 0.3)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.yaxis.set_minor_locator(MultipleLocator(5))
    ax.set_ylim(0, 105)
    ax.grid(True, which='major', alpha=0.3, linewidth=0.8)
    ax.grid(True, which='minor', alpha=0.15, linewidth=0.5)
    ax.set_title('AGBF-Erreichungsgrad nach Personalzahl — SA vs. ZUB+',
                 fontweight='bold', pad=12)
    ax.legend(loc='lower right', framealpha=0.95)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    for k, s, z in zip(ks, sa_pct, zub_pct):
        if not np.isnan(s):
            ax.annotate(f'{s:.1f}', (k, s), textcoords='offset points',
                        xytext=(0, -14), ha='center', fontsize=8, color='#333333')
        if not np.isnan(z):
            ax.annotate(f'{z:.1f}', (k, z), textcoords='offset points',
                        xytext=(0, 8), ha='center', fontsize=8, color=COLORS_QUAL[0])

    plt.tight_layout()
    out_pdf = output_dir / 'Vergleich_AGBF_SA_ZUB.pdf'
    out_svg = output_dir / 'Vergleich_AGBF_SA_ZUB.svg'
    fig.savefig(out_pdf, format='pdf', bbox_inches='tight', dpi=300)
    fig.savefig(out_svg, format='svg', bbox_inches='tight')
    plt.close(fig)
    print(f'  → {out_pdf.name}')


def plot_vergleich_nested_loop(raw: dict[tuple[int, int], dict[float, float]],
                               sa_csv: Path, output_dir: Path):
    """Nested Loop mit SA-Overlay. SA hängt nicht von N_Zug ab — wird in jedem
    N_Zug-Block für die passenden k-Werte wiederholt.
    """
    ts.apply_style()

    sa_data = load_sa_data(sa_csv)

    def sa_stats(k: int) -> dict | None:
        if k not in sa_data or not sa_data[k]:
            return None
        vals = np.asarray(sa_data[k])
        return {
            'mean': float(np.mean(vals)),
            'min': float(np.min(vals)),
            'max': float(np.max(vals)),
            'p95': float(np.percentile(vals, 95)),
            'agbf_pct': 100.0 * float(np.sum(vals <= AGBF_MINUTES)) / len(vals),
        }

    n_trains_all = sorted(set(n for (n, _) in raw.keys()))

    records = []
    for n in n_trains_all:
        rows_n = expand(raw, n)
        by_nz: dict[int, list[float]] = defaultdict(list)
        for r in rows_n:
            by_nz[r['num_zub']].append(r['t_intervention_total_s'] / 60.0)
        for k in sorted(by_nz.keys()):
            vals = np.array(by_nz[k])
            s = sa_stats(k)
            records.append({
                'n': n, 'k': k,
                'zub_mean': float(np.mean(vals)),
                'zub_min': float(np.min(vals)),
                'zub_max': float(np.max(vals)),
                'zub_p95': float(np.percentile(vals, 95)),
                'zub_agbf_pct': 100.0 * float(np.sum(vals <= AGBF_MINUTES)) / len(vals),
                'sa_mean': s['mean'] if s else np.nan,
                'sa_min': s['min'] if s else np.nan,
                'sa_max': s['max'] if s else np.nan,
                'sa_p95': s['p95'] if s else np.nan,
                'sa_agbf_pct': s['agbf_pct'] if s else np.nan,
            })

    records.sort(key=lambda r: (r['n'], r['k']))
    x = np.arange(len(records))
    ns = np.array([r['n'] for r in records])
    ks = np.array([r['k'] for r in records])

    block_starts = [0]
    for i in range(1, len(records)):
        if records[i]['n'] != records[i - 1]['n']:
            block_starts.append(i)

    def with_breaks(y_arr):
        out_x, out_y = [], []
        for i, b in enumerate(block_starts):
            end = block_starts[i + 1] if i + 1 < len(block_starts) else len(x)
            if i > 0:
                out_x.append(np.nan)
                out_y.append(np.nan)
            out_x.extend(x[b:end])
            out_y.extend(y_arr[b:end])
        return np.array(out_x), np.array(out_y)

    fig = plt.figure(figsize=ts.FIGSIZE_NESTED)
    gs = GridSpec(4, 1, height_ratios=[0.7, 0.7, 0.7, 5.0],
                  hspace=0.18, figure=fig)
    ax_n = fig.add_subplot(gs[0])
    ax_k = fig.add_subplot(gs[1], sharex=ax_n)
    ax_a = fig.add_subplot(gs[2], sharex=ax_n)
    ax_t = fig.add_subplot(gs[3], sharex=ax_n)

    ax_n.step(x, ns, where='mid', color=ts.COLOR_PRIMARY, linewidth=1.2)
    ax_n.fill_between(x, 0, ns, step='mid', alpha=0.18,
                      color=ts.COLOR_PRIMARY)
    ax_n.set_ylabel('$N_\\text{Zug}$')
    ax_n.set_yticks([1, 5, 10]); ax_n.set_ylim(0, 11)
    ax_n.tick_params(labelbottom=False)
    ts.add_grid(ax_n, axis='y')

    ax_k.step(x, ks, where='mid', color=ts.COLOR_ACCENT, linewidth=1.2)
    ax_k.fill_between(x, 0, ks, step='mid', alpha=0.18,
                      color=ts.COLOR_ACCENT)
    ax_k.set_ylabel('$N$')
    ax_k.set_yticks([1, 5, 10]); ax_k.set_ylim(0, 11)
    ax_k.tick_params(labelbottom=False)
    ts.add_grid(ax_k, axis='y')

    zub_agbf = np.array([r['zub_agbf_pct'] for r in records])
    sa_agbf = np.array([r['sa_agbf_pct'] for r in records])
    xb, zub_agbf_b = with_breaks(zub_agbf)
    _, sa_agbf_b = with_breaks(sa_agbf)
    ax_a.plot(xb, zub_agbf_b, 'o-', color=ts.COLOR_PRIMARY, linewidth=1.2,
              markersize=1.8)
    ax_a.plot(xb, sa_agbf_b, 's-', color=ts.COLOR_COMPARE, linewidth=1.2,
              markersize=1.8)
    ax_a.axhline(AGBF_TARGET_PCT, color=ts.COLOR_NEUTRAL,
                 linewidth=0.8, linestyle=':', alpha=0.7)
    ax_a.set_ylabel('AGBF (%)')
    ax_a.set_ylim(0, 105)
    ax_a.set_yticks([0, 50, 100])
    ax_a.text(len(records) - 0.7, AGBF_TARGET_PCT - 4,
              f'{int(AGBF_TARGET_PCT)} %',
              ha='right', va='top', color=ts.COLOR_NEUTRAL, fontsize=7)
    ax_a.tick_params(labelbottom=False)
    ts.add_grid(ax_a, axis='y')

    zub_means = np.array([r['zub_mean'] for r in records])
    zub_mins = np.array([r['zub_min'] for r in records])
    zub_maxs = np.array([r['zub_max'] for r in records])
    zub_p95 = np.array([r['zub_p95'] for r in records])
    sa_means = np.array([r['sa_mean'] for r in records])
    sa_mins = np.array([r['sa_min'] for r in records])
    sa_maxs = np.array([r['sa_max'] for r in records])
    sa_p95 = np.array([r['sa_p95'] for r in records])
    _, zub_means_b = with_breaks(zub_means)
    _, zub_mins_b = with_breaks(zub_mins)
    _, zub_maxs_b = with_breaks(zub_maxs)
    _, zub_p95_b = with_breaks(zub_p95)
    _, sa_means_b = with_breaks(sa_means)
    _, sa_mins_b = with_breaks(sa_mins)
    _, sa_maxs_b = with_breaks(sa_maxs)
    _, sa_p95_b = with_breaks(sa_p95)

    h_zub_max = ax_t.fill_between(xb, zub_mins_b, zub_maxs_b, alpha=0.08,
                                  color=ts.COLOR_PRIMARY,
                                  label='ZUB+ Min–Max')
    h_sa_max = ax_t.fill_between(xb, sa_mins_b, sa_maxs_b, alpha=0.08,
                                 color=ts.COLOR_COMPARE,
                                 label='SA Min–Max')
    h_zub_p95, = ax_t.plot(xb, zub_p95_b, '--', color=ts.COLOR_PRIMARY,
                           linewidth=1.0, alpha=0.7, label='ZUB+ p95')
    h_zub_mean, = ax_t.plot(xb, zub_means_b, 'o-', color=ts.COLOR_PRIMARY,
                            linewidth=1.4, markersize=1.8,
                            label='ZUB+ Mittelwert')
    h_sa_p95, = ax_t.plot(xb, sa_p95_b, '--', color=ts.COLOR_COMPARE,
                          linewidth=1.0, alpha=0.7, label='SA p95')
    h_sa_mean, = ax_t.plot(xb, sa_means_b, 's-', color=ts.COLOR_COMPARE,
                           linewidth=1.4, markersize=1.8,
                           label='SA Mittelwert')

    ts.setup_time_axis(ax_t, axis='y')
    ax_t.set_xlabel('$N_\\text{Zug}$')
    ax_t.set_xlim(-0.5, len(records) - 0.5)
    ts.add_grid(ax_t, axis='y')
    ts.add_agbf_marker(ax_t, axis='y', label=True)
    # matplotlib füllt Spalten top-to-bottom: für Zeilen-Layout
    # (Zeile 1 = ZUB+, Zeile 2 = SA) Handles spaltenweise interleaven
    legend_handles = [h_zub_max, h_sa_max,
                      h_zub_p95, h_sa_p95,
                      h_zub_mean, h_sa_mean]
    legend_labels = ['ZUB+ Min–Max', 'SA Min–Max',
                     'ZUB+ p95', 'SA p95',
                     'ZUB+ Mittelwert', 'SA Mittelwert']
    ts.place_legend_below(ax_t, ncol=3, y_offset=-0.13,
                          handles=legend_handles, labels=legend_labels)

    for ax_row in (ax_n, ax_k, ax_a, ax_t):
        for bs in block_starts:
            ax_row.axvline(bs - 0.5, color=ts.COLOR_GRID,
                           linewidth=0.5, zorder=0)

    tick_positions = [(block_starts[i] + (block_starts[i + 1] - 1)) / 2
                      for i in range(len(block_starts) - 1)]
    tick_positions.append((block_starts[-1] + len(records) - 1) / 2)
    tick_labels = [str(records[bs]['n']) for bs in block_starts]
    ax_t.set_xticks(tick_positions)
    ax_t.set_xticklabels(tick_labels)

    ts.save_fig(fig, output_dir, 'Vergleich_NestedLoop_SA_ZUB')
    plt.close(fig)


# ===================================================================
# VERGLEICHS-HEATMAP: SA & ZUB+ in einer Heatmap
# Pro Zelle (N, Position): oben-links = SA, unten-rechts = ZUB+
# ===================================================================
def plot_heatmap_compare_intervention(
        pos_numzub: dict[tuple[float, int], list[float]],
        sa_csv: Path, output_dir: Path, n_trains: int = 10,
        wendepunkt_m: float = 7388.0, step_m: float = 250.0):
    """Geteilte Heatmap: jede Zelle zeigt SA (oben links) und ZUB+ (unten rechts).

    Beide Konfigurationen teilen sich Achsen, Bin-Raster und Farbskala, damit
    die Performance bei gleicher Anzahl direkt vergleichbar ist.
    """
    ts.apply_style()
    umlauf_m = 2 * wendepunkt_m
    bin_edges = np.arange(0, wendepunkt_m + step_m, step_m)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    n_bins = len(bin_centers)

    sa_raw = defaultdict(list)
    with open(sa_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                pos = float(row['disruption_position_m'])
                na = int(row['num_agents'])
                t = float(row['t_intervention_total_s'])
            except (ValueError, TypeError, KeyError):
                continue
            phys = pos if pos <= wendepunkt_m else umlauf_m - pos
            sa_raw[na].append((phys, t / 60.0))

    sa_agents = sorted(sa_raw.keys())
    sa_matrix = np.full((len(sa_agents), n_bins), np.nan)
    for i, na in enumerate(sa_agents):
        sums = np.zeros(n_bins); counts = np.zeros(n_bins)
        for phys, t_min in sa_raw[na]:
            b = int(phys / step_m)
            if b >= n_bins: b = n_bins - 1
            sums[b] += t_min; counts[b] += 1
        mask = counts > 0
        sa_matrix[i, mask] = sums[mask] / counts[mask]

    zubs = sorted(set(k for (_, k) in pos_numzub.keys()))
    zub_matrix = np.full((len(zubs), n_bins), np.nan)
    sums_z = np.zeros((len(zubs), n_bins))
    counts_z = np.zeros((len(zubs), n_bins))
    for (pos, k), tlist in pos_numzub.items():
        phys = pos if pos <= wendepunkt_m else umlauf_m - pos
        b = int(phys / step_m)
        if b >= n_bins: b = n_bins - 1
        i = zubs.index(k)
        for t in tlist:
            sums_z[i, b] += t; counts_z[i, b] += 1
    mask = counts_z > 0
    zub_matrix[mask] = sums_z[mask] / counts_z[mask]

    n_rows = max(len(sa_agents), len(zubs))

    all_vals = np.concatenate([
        sa_matrix[~np.isnan(sa_matrix)],
        zub_matrix[~np.isnan(zub_matrix)],
    ])
    vmin = float(np.min(all_vals))
    vmax = float(np.max(all_vals))

    fig, ax = plt.subplots(figsize=ts.FIGSIZE_HEATMAP)
    cmap = plt.get_cmap(ts.CMAP_SEQUENTIAL)
    norm = plt.Normalize(vmin=vmin, vmax=vmax)

    from matplotlib.patches import Polygon as MplPolygon
    from matplotlib.collections import PatchCollection

    sa_patches = []; sa_colors = []
    zub_patches = []; zub_colors = []
    for i in range(n_rows):
        y0 = i + 0.5; y1 = i + 1.5
        for j in range(n_bins):
            x0 = (bin_centers[j] - step_m / 2) / 1000
            x1 = (bin_centers[j] + step_m / 2) / 1000
            if i < len(sa_agents) and not np.isnan(sa_matrix[i, j]):
                sa_patches.append(MplPolygon(
                    [(x0, y0), (x0, y1), (x1, y1)], closed=True))
                sa_colors.append(cmap(norm(sa_matrix[i, j])))
            if i < len(zubs) and not np.isnan(zub_matrix[i, j]):
                zub_patches.append(MplPolygon(
                    [(x0, y0), (x1, y0), (x1, y1)], closed=True))
                zub_colors.append(cmap(norm(zub_matrix[i, j])))

    pc_sa = PatchCollection(sa_patches, facecolors=sa_colors, edgecolors='none')
    pc_zub = PatchCollection(zub_patches, facecolors=zub_colors, edgecolors='none')
    ax.add_collection(pc_sa)
    ax.add_collection(pc_zub)

    for i, na in enumerate(sa_agents):
        indices = distribute_agents(na)
        agent_kms = [STATIONS[idx].km / 1000 for idx in indices]
        y = na
        ax.scatter(agent_kms, [y] * len(agent_kms),
                   marker='|', color=ts.COLOR_ACCENT, s=60,
                   linewidths=1.4, zorder=5)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, aspect=22)
    cbar.set_label('Mittlere Interventionszeit (min)')
    cbar.ax.tick_params(labelsize=8)

    ts.setup_position_axis(ax, axis='x')
    ax.set_ylabel(rf'Anzahl Stationsagenten / ZUB+ $N$  '
                  rf'($N_\text{{Zug}} = {n_trains}$)')
    ax.set_yticks(range(1, n_rows + 1))
    ax.set_yticklabels([str(a) for a in range(1, n_rows + 1)])
    ax.set_ylim(0.5, n_rows + 0.5)

    for i, s in enumerate(STATIONS):
        km = s.km / 1000
        if km < 0 or km > wendepunkt_m / 1000:
            continue
        y_name = 1.025 if i % 2 == 0 else 1.075
        ax.text(km, y_name, s.name, ha='center', va='bottom', fontsize=7,
                transform=ax.get_xaxis_transform(), clip_on=False)
        if i % 2 == 1:
            ax.plot([km, km], [1.005, 1.07],
                    color=ts.COLOR_NEUTRAL, linewidth=0.5, zorder=1,
                    clip_on=False, transform=ax.get_xaxis_transform())

    from matplotlib.legend_handler import HandlerPatch

    def _make_upper(legend, orig_handle, xdescent, ydescent, width, height, fontsize):
        verts = [(-xdescent, -ydescent),
                 (-xdescent, -ydescent + height),
                 (-xdescent + width, -ydescent + height)]
        return MplPolygon(verts, closed=True)

    def _make_lower(legend, orig_handle, xdescent, ydescent, width, height, fontsize):
        verts = [(-xdescent, -ydescent),
                 (-xdescent + width, -ydescent),
                 (-xdescent + width, -ydescent + height)]
        return MplPolygon(verts, closed=True)

    sa_proxy = MplPolygon([(0, 0), (1, 0), (1, 1)],
                          facecolor='#bbbbbb', edgecolor=ts.COLOR_NEUTRAL,
                          linewidth=0.6)
    zub_proxy = MplPolygon([(0, 0), (1, 0), (1, 1)],
                           facecolor='#bbbbbb', edgecolor=ts.COLOR_NEUTRAL,
                           linewidth=0.6)
    agent_proxy = Line2D([0], [0], marker='|', color=ts.COLOR_ACCENT,
                         markersize=8, markeredgewidth=1.4, linestyle='None')

    ax.legend(
        handles=[sa_proxy, zub_proxy, agent_proxy],
        labels=['SA (oben links)', 'ZUB+ (unten rechts)', 'Agentenposition'],
        handler_map={
            sa_proxy: HandlerPatch(patch_func=_make_upper),
            zub_proxy: HandlerPatch(patch_func=_make_lower),
        },
        loc='upper center', bbox_to_anchor=(0.5, -0.13),
        ncol=3, frameon=False, handletextpad=0.6, columnspacing=1.6,
    )

    fig.tight_layout()
    ts.save_fig(fig, output_dir, 'Vergleich_Heatmap_Intervention_SA_ZUB')
    plt.close(fig)


# ===================================================================
# HAUPTPROGRAMM
# ===================================================================
if __name__ == '__main__':
    base = Path(__file__).resolve().parents[2]
    output_dir = base / 'Diagramme'
    output_dir.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1:
        raw_csv = Path(sys.argv[1])
    else:
        raw_csv = find_latest_conv_csv(base)

    n_trains = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    print(f'ROH-CSV:   {raw_csv}')
    print(f'N_TRAINS:  {n_trains}')
    print(f'Ausgabe:   {output_dir}')
    print()

    raw = load_raw(raw_csv)
    rows = expand(raw, n_trains)
    by_nz = group_by_num_zub(rows)
    pos_nz = group_by_pos_numzub(rows)
    stats = compute_stats(by_nz)

    print(f'Hauptauswertung N_TRAINS = {n_trains} ({len(rows)} Zeilen)')
    print()

    print('[1/16] Statistik (Boxplot)')
    plot_boxplot(by_nz, stats, n_trains, output_dir)
    print('[2/16] CDF')
    plot_cdf(by_nz, n_trains, output_dir)
    print('[3/16] CDF-Sättigung (alle N_Zug in einem Diagramm)')
    plot_cdf_saturation(raw, output_dir)
    print('[4/16] Nested Loop Plot (Rücker & Schwarzer 2014)')
    plot_nested_loop(raw, output_dir)
    print('[5/16] Trellis CDF (Becker, Cleveland & Shyu 1996)')
    plot_trellis_cdf(raw, output_dir)
    print('[6/16] Parallel Coordinates (Inselberg 1985)')
    plot_parallel_coordinates(raw, output_dir)
    print('[7/16] Heatmap Position × num_zub')
    plot_heatmap_position(pos_nz, n_trains, output_dir)
    print('[8/16] Diminishing Returns')
    plot_diminishing_returns(stats, n_trains, output_dir)
    print('[9/16] Delta allgemein (quantilweise)')
    plot_delta_allgemein(by_nz, n_trains, output_dir)
    print('[10/16] Delta positionsweise')
    plot_delta_positionsweise(rows, n_trains, output_dir)
    print('[11/16] Gap-Heatmap (num_trains × gap)')
    plot_heatmap_gap(raw, output_dir)
    print('[12/16] Matrix-Heatmap (num_trains × num_zub)')
    plot_heatmap_matrix(raw, output_dir)
    print('[13/16] AGBF-Kurvenschar')
    plot_agbf_kurvenschar(raw, output_dir)

    # --- Vergleichs-Plots SA vs. ZUB+ für Kap. 5.3 ---
    # Neueste SA-Konvergenz-CSV verwenden (gleiches Schema wie parallel_*_SA.csv).
    # Priorisiert die kumulative SA-Datei (alle Stufen bis zur Endstufe 50 m).
    sa_csv = None
    for pattern in ('output/convergence_sa_*/conv_sa_all.csv',
                    'output/convergence_sa_*/conv_sa_0050m.csv'):
        sa_candidates = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime)
        if sa_candidates:
            sa_csv = sa_candidates[-1]
            break
    if sa_csv is None:
        sa_csv = base / 'output' / 'batch_results' / 'parallel_20260424_SA.csv'
    if sa_csv.exists():
        print(f'\nSA-CSV:    {sa_csv}')
        print('[14/16] Vergleich CDF SA vs. ZUB+')
        plot_vergleich_cdf(raw, sa_csv, output_dir, n_trains_fixed=n_trains)
        print('[15/16] Vergleich AGBF-Linien SA vs. ZUB+')
        plot_vergleich_agbf(raw, sa_csv, output_dir, n_trains_fixed=n_trains)
        print('[16/17] Vergleich Nested Loop mit SA-Overlay')
        plot_vergleich_nested_loop(raw, sa_csv, output_dir)
        print('[17/17] Vergleich Heatmap Interventionszeit (SA & ZUB+)')
        plot_heatmap_compare_intervention(pos_nz, sa_csv, output_dir, n_trains)
    else:
        print(f'\nHINWEIS: SA-CSV {sa_csv} nicht gefunden — Vergleichsplots übersprungen.')

    print()
    print('Fertig.')
