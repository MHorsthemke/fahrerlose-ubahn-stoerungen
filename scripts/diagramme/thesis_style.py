"""
thesis_style.py — Zentrale Stil-Definitionen für die Kap.-5-Plots der Masterarbeit.

Setzt einheitliche Figur-Größen, Schriftgrößen, Farbpaletten und
vereinheitlichte Achsen-Bereiche und stellt save_fig()-Helper bereit.

Designziele:

  - figsize ist so kalibriert, dass LaTeX bei \\includegraphics[width=1\\linewidth]
    die PDF NICHT verkleinern muss. Damit bleiben die hier gesetzten 9/10-pt-Schriften
    in der finalen Thesis-PDF lesbar (~ Caption-Größe einer 12-pt-Hauptschrift).
  - Achsen-Limits, Einheiten und Tick-Raster sind über Konstanten und Helper
    plotübergreifend gleich. SA, ZUB+ und Vergleichsplots können damit visuell
    1:1 verglichen werden.
  - Farbpalette: TUBraunschweig-Blau als Primärakzent, Orange als Sekundärakzent,
    viridis als Sequenz für 1..N Konfigurationen (perzeptuell gleichmäßig,
    s/w-tauglich, farbenblind-tauglich).

Verwendung:

    from thesis_style import (
        apply_style, save_fig,
        FIGSIZE_DEFAULT, FIGSIZE_TALL, FIGSIZE_WIDE, FIGSIZE_HEATMAP,
        COLOR_PRIMARY, COLOR_PRIMARY_SOFT, COLOR_ACCENT,
        COLOR_NEUTRAL, COLOR_GRID, COLOR_MUTED,
        cmap_sequence,
        setup_time_axis, setup_position_axis, setup_count_axis,
        setup_percent_axis, setup_delta_axis,
    )
"""

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import MultipleLocator


# ===================================================================
# FIGURGRÖSSEN (in inch; Thesis-Textbreite ca. 16 cm = 6,30 in)
# ===================================================================
# figsize ist so gewählt, dass LaTeX bei width=1\linewidth nicht skalieren muss.
# Damit bleiben die hier gesetzten 10/11-pt-Schriften in der finalen PDF auch
# bei 10/11 pt (~ Caption- bis Body-Text-Größe der Thesis). Höhen sind so
# bemessen, dass darunter Platz für eine Legende bleibt.
FIGSIZE_DEFAULT = (6.3, 4.2)    # Boxplot, Linien-Plots
FIGSIZE_TALL = (6.3, 5.0)       # CDF, Delta-Plots mit größerer Legende
FIGSIZE_WIDE = (6.3, 3.4)       # 1D-Streifen, Stabilität
FIGSIZE_HEATMAP = (6.3, 4.6)    # 2D-Heatmaps mit Stationsbeschriftung oben
FIGSIZE_NESTED = (6.3, 5.8)     # Nested-Loop mit Track-Stack


# ===================================================================
# FARBPALETTE
# ===================================================================
# Primärakzent: TUBraunschweig-Blau (vgl. tubscolors.sty: tubsBlue 0/112/183).
COLOR_PRIMARY = '#0070B7'        # tubsBlue, kräftig
COLOR_PRIMARY_SOFT = '#7FB6D8'   # heller Ton für Flächen
COLOR_PRIMARY_DARK = '#004B79'   # dunkler Ton für Akzente

# Sekundärakzent: warmes Orange (Median, Hervorhebung)
COLOR_ACCENT = '#E08214'
COLOR_ACCENT_SOFT = '#F2C394'

# Vergleichsfarbe: rotbraun für SA-Linien in den Vergleichsplots
COLOR_COMPARE = '#B2182B'

# Neutrale Töne
COLOR_NEUTRAL = '#333333'
COLOR_GRID = '#B0B0B0'
COLOR_MUTED = '#666666'


def cmap_sequence(n: int):
    """
    Liefert n Farben aus plasma, ohne extreme Enden.
    Plasma ist perzeptuell gleichmäßig (Smith/van der Walt 2015), druckt s/w
    lesbar und ist farbenblind-tauglich. Verwendung: wenn die Reihenfolge der
    Stufen primäre Information ist (AGBF-Kurvenschar, Diminishing Returns).
    """
    cmap = plt.cm.plasma
    return [cmap(0.05 + 0.85 * i / max(n - 1, 1)) for i in range(n)]


# Kräftige 10er-Palette mit max. paarweiser Unterscheidbarkeit.
# Basis: Paul Tol's "Bright" (7 sehr kräftige CVD-sichere Farben), erweitert
# um 3 zusätzliche kontraststarke Töne (Schwarz, Olivgrün, Magenta-Pink),
# damit alle 10 Linien auf Bildschirm und Papier deutlich auseinander liegen.
# Anders als Tol Muted bewusst kräftig statt gedämpft — Priorität ist
# Bildschirm-/Beamer-Lesbarkeit für die Verteidigung.
_QUAL_10 = [
    '#4477AA',  # blau (Tol Bright)
    '#EE6677',  # rose (Tol Bright)
    '#228833',  # grün (Tol Bright)
    '#CCBB44',  # gelb (Tol Bright)
    '#66CCEE',  # cyan (Tol Bright)
    '#AA3377',  # purpur (Tol Bright)
    '#332288',  # indigo (statt schwarz, kollidiert sonst mit SA-Linien)
    '#EE7733',  # orange
    '#882255',  # wein
    '#117733',  # dunkelgrün
]


def cmap_categorical(n: int):
    """
    Liefert n kategoriale Farben mit max. paarweiser Unterscheidbarkeit.
    Verwendung: wenn die Linien voneinander unterscheidbar sein müssen
    (CDFs, Trellis-Subplots) und die Ordnung über die Legende klar ist.
    Basis Tol Bright + Hochkontrast-Ergänzungen.
    """
    if n <= len(_QUAL_10):
        return list(_QUAL_10[:n])
    cmap = plt.cm.tab20
    return [cmap(i / 20.0) for i in range(n)]


# Diverging-Map für Delta-/Symmetrie-Heatmaps (Mittelpunkt = 0)
CMAP_DIVERGING = 'RdBu_r'
# Sequenzielle Map für Heatmaps (klein = gut, groß = schlecht)
CMAP_SEQUENTIAL = 'viridis'


# ===================================================================
# VEREINHEITLICHTE ACHSEN-BEREICHE
# ===================================================================
# Zeit-Achse Interventionszeit: deckt SA-Max (~24 min) und ZUB+-Max (~32 min)
# mit etwas Kopfraum ab. Damit sind SA-, ZUB+- und Vergleichsplots direkt
# überlagerbar.
T_INTERVENTION_LIM_MIN = (0.0, 30.0)
T_INTERVENTION_MAJOR = 5.0
T_INTERVENTION_MINOR = 1.0
T_INTERVENTION_LABEL = 'Interventionszeit (min)'

# Konfigurationszahl-Achse (1..10 für SA, ZUB+, Züge)
COUNT_LIM = (0.4, 10.6)
COUNT_TICKS = list(range(1, 11))

# Physische Strecke (0..Wendepunkt rechts ~7,4 km)
POSITION_LIM_KM = (0.0, 7.4)
POSITION_MAJOR_KM = 1.0
POSITION_MINOR_KM = 0.5
POSITION_LABEL = 'Störungsposition (km)'

# Kumulativer Anteil
PERCENT_LIM = (0.0, 105.0)
PERCENT_MAJOR = 10.0
PERCENT_MINOR = 5.0
PERCENT_LABEL = 'Kumulativer Anteil (%)'

# Delta Interventionszeit (Verbesserung pro zusätzlicher Einheit;
# negative Werte = Monotonie-Verletzung).
DELTA_LIM_MIN = (-13.0, 6.0)
DELTA_MAJOR = 2.0
DELTA_MINOR = 1.0
DELTA_LABEL = '$\\Delta$ Interventionszeit (min)'

# AGBF-Hilfsfrist (Referenzlinie bei 10 min)
AGBF_THRESHOLD_MIN = 10.0
AGBF_THRESHOLD_PCT = 90.0


# ===================================================================
# rcParams
# ===================================================================
def apply_style() -> None:
    """
    Setzt rcParams für alle Plots der Masterarbeit.

    Schriftgrößen sind so gewählt, dass sie bei figsize = Textbreite und
    \\includegraphics[width=1\\linewidth] in der finalen Thesis-PDF
    bei ihrer Nominalgröße landen (~ Caption- bis Body-Text-Kaliber einer
    12-pt-Thesis). Damit ist die Plot-Schrift visuell ungefähr so groß wie
    der umgebende Fließtext.
    """
    rcParams['font.family'] = 'sans-serif'
    rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
    rcParams['font.size'] = 8
    rcParams['axes.labelsize'] = 9
    rcParams['axes.titlesize'] = 10
    rcParams['xtick.labelsize'] = 8
    rcParams['ytick.labelsize'] = 8
    rcParams['legend.fontsize'] = 8
    rcParams['legend.frameon'] = False
    rcParams['axes.spines.top'] = False
    rcParams['axes.spines.right'] = False
    rcParams['axes.linewidth'] = 0.8
    rcParams['xtick.major.width'] = 0.8
    rcParams['ytick.major.width'] = 0.8
    rcParams['xtick.major.size'] = 3.0
    rcParams['ytick.major.size'] = 3.0
    rcParams['xtick.minor.size'] = 1.8
    rcParams['ytick.minor.size'] = 1.8
    rcParams['xtick.minor.width'] = 0.6
    rcParams['ytick.minor.width'] = 0.6
    rcParams['grid.color'] = COLOR_GRID
    rcParams['grid.linewidth'] = 0.5
    rcParams['grid.alpha'] = 0.2
    rcParams['axes.axisbelow'] = True
    rcParams['lines.linewidth'] = 1.4
    rcParams['pdf.fonttype'] = 42
    rcParams['ps.fonttype'] = 42


# ===================================================================
# ACHSEN-HELPER
# ===================================================================
def setup_time_axis(ax, axis: str = 'y') -> None:
    """Setzt vereinheitlichte Interventionszeit-Achse mit Einheit."""
    if axis == 'y':
        ax.set_ylim(T_INTERVENTION_LIM_MIN)
        ax.yaxis.set_major_locator(MultipleLocator(T_INTERVENTION_MAJOR))
        ax.yaxis.set_minor_locator(MultipleLocator(T_INTERVENTION_MINOR))
        ax.set_ylabel(T_INTERVENTION_LABEL)
    else:
        ax.set_xlim(T_INTERVENTION_LIM_MIN)
        ax.xaxis.set_major_locator(MultipleLocator(T_INTERVENTION_MAJOR))
        ax.xaxis.set_minor_locator(MultipleLocator(T_INTERVENTION_MINOR))
        ax.set_xlabel(T_INTERVENTION_LABEL)


def setup_count_axis(ax, axis: str = 'x', label: str = 'Anzahl') -> None:
    """Setzt vereinheitlichte 1..10-Achse mit ganzzahligen Ticks."""
    if axis == 'x':
        ax.set_xlim(COUNT_LIM)
        ax.set_xticks(COUNT_TICKS)
        ax.set_xticklabels([str(t) for t in COUNT_TICKS])
        ax.set_xlabel(label)
    else:
        ax.set_ylim(COUNT_LIM)
        ax.set_yticks(COUNT_TICKS)
        ax.set_yticklabels([str(t) for t in COUNT_TICKS])
        ax.set_ylabel(label)


def setup_position_axis(ax, axis: str = 'x') -> None:
    """Setzt vereinheitlichte Strecken-Achse in km."""
    if axis == 'x':
        ax.set_xlim(POSITION_LIM_KM)
        ax.xaxis.set_major_locator(MultipleLocator(POSITION_MAJOR_KM))
        ax.xaxis.set_minor_locator(MultipleLocator(POSITION_MINOR_KM))
        ax.set_xlabel(POSITION_LABEL)
    else:
        ax.set_ylim(POSITION_LIM_KM)
        ax.yaxis.set_major_locator(MultipleLocator(POSITION_MAJOR_KM))
        ax.yaxis.set_minor_locator(MultipleLocator(POSITION_MINOR_KM))
        ax.set_ylabel(POSITION_LABEL)


def setup_percent_axis(ax, axis: str = 'y') -> None:
    """Setzt vereinheitlichte Prozent-Achse 0..100 (mit Kopfraum bis 105)."""
    if axis == 'y':
        ax.set_ylim(PERCENT_LIM)
        ax.yaxis.set_major_locator(MultipleLocator(PERCENT_MAJOR))
        ax.yaxis.set_minor_locator(MultipleLocator(PERCENT_MINOR))
        ax.set_ylabel(PERCENT_LABEL)
    else:
        ax.set_xlim(PERCENT_LIM)
        ax.xaxis.set_major_locator(MultipleLocator(PERCENT_MAJOR))
        ax.xaxis.set_minor_locator(MultipleLocator(PERCENT_MINOR))
        ax.set_xlabel(PERCENT_LABEL)


def setup_delta_axis(ax, axis: str = 'y', lim=DELTA_LIM_MIN) -> None:
    """Setzt vereinheitlichte Delta-Interventionszeit-Achse mit Einheit.

    `lim`: Tupel (min,max) oder None (Auto-Scaling, Achse wächst mit Daten).
    """
    if axis == 'y':
        if lim is not None:
            ax.set_ylim(lim)
        ax.yaxis.set_major_locator(MultipleLocator(DELTA_MAJOR))
        ax.yaxis.set_minor_locator(MultipleLocator(DELTA_MINOR))
        ax.set_ylabel(DELTA_LABEL)
    else:
        if lim is not None:
            ax.set_xlim(lim)
        ax.xaxis.set_major_locator(MultipleLocator(DELTA_MAJOR))
        ax.xaxis.set_minor_locator(MultipleLocator(DELTA_MINOR))
        ax.set_xlabel(DELTA_LABEL)


def add_grid(ax, axis: str = 'y') -> None:
    """Dezentes horizontales Hintergrund-Gitter (Major + Minor)."""
    ax.grid(True, axis=axis, which='major', linewidth=0.5, alpha=0.40)
    ax.grid(True, axis=axis, which='minor', linewidth=0.3, alpha=0.15)


def place_legend_below(ax, ncol: int = 4,
                       y_offset: float = -0.13,
                       handletextpad: float = 0.6,
                       columnspacing: float = 1.4,
                       **kwargs):
    """
    Plaziert die Legende einheitlich unterhalb des Plots.

    Verwendet bbox_to_anchor=(0.5, y_offset) und loc='upper center', sodass
    die Legende mittig direkt unter dem x-Achsen-Label sitzt. y_offset
    ist so gewählt, dass der Abstand zwischen x-Achsenbeschriftung und
    Legende klein, aber nicht beklemmend ist (~ halber Zeilenabstand).
    """
    return ax.legend(
        loc='upper center',
        bbox_to_anchor=(0.5, y_offset),
        ncol=ncol,
        frameon=False,
        handletextpad=handletextpad,
        columnspacing=columnspacing,
        **kwargs,
    )


def draw_matrix_legend(ax_leg, n_cols: int, rows, fontsize: int = 8) -> None:
    """Zeichnet eine Matrix-Legende auf einem leeren Achsen-Subplot.

    Header oben (1..n_cols), darunter eine Zeile pro Eintrag in `rows`.
    Jeder Eintrag ist `(label, [line2d_kw, ...])` mit n_cols Stück
    Line2D-Konfigurationen. Vertikal/horizontal kompakt — der xlim-/ylim-Bereich
    wird so gewählt, dass der Plot-Bereich oberhalb wenig vertikalen Luft braucht.
    """
    from matplotlib.lines import Line2D as _Line2D
    ax_leg.set_axis_off()
    n_rows = len(rows)
    x_left = -2.0
    line_dx = 0.36
    row_step = 0.72  # vertikaler Zeilenabstand (1.0 wäre Standardabstand)
    y_header = (n_rows - 1) * row_step + 0.55
    for i in range(n_cols):
        ax_leg.text(i + 0.5, y_header, str(i + 1),
                    ha='center', va='center', fontsize=fontsize)
    for r, (label, line_kws) in enumerate(rows):
        y = (n_rows - 1 - r) * row_step
        ax_leg.text(x_left + 0.1, y, label, ha='left', va='center',
                    fontsize=fontsize)
        for i in range(n_cols):
            if i >= len(line_kws):
                continue
            kw = dict(line_kws[i])
            kw.setdefault('linewidth', 1.6)
            x0 = i + 0.5 - line_dx
            x1 = i + 0.5 + line_dx
            ax_leg.add_line(_Line2D((x0, x1), (y, y), **kw))
    ax_leg.set_xlim(x_left, n_cols)
    ax_leg.set_ylim(-0.4, y_header + 0.3)


def add_agbf_marker(ax, axis: str = 'x', label: bool = True) -> None:
    """Referenzlinie bei AGBF-Hilfsfrist (10 min) im Plot."""
    kw = dict(color=COLOR_NEUTRAL, linewidth=0.8, linestyle=':',
              alpha=0.7, zorder=1)
    if axis == 'x':
        ax.axvline(AGBF_THRESHOLD_MIN, **kw)
        if label:
            ax.text(AGBF_THRESHOLD_MIN + 0.3, ax.get_ylim()[1] * 0.02,
                    'AGBF', color=COLOR_NEUTRAL, fontsize=8,
                    ha='left', va='bottom')
    else:
        ax.axhline(AGBF_THRESHOLD_MIN, **kw)
        if label:
            ax.text(ax.get_xlim()[1] * 0.99, AGBF_THRESHOLD_MIN + 0.4,
                    'AGBF', color=COLOR_NEUTRAL, fontsize=8,
                    ha='right', va='bottom')


# ===================================================================
# SAVE
# ===================================================================
def save_fig(fig, output_dir: Path, basename: str,
             also_svg: bool = True) -> Path:
    """Speichert die Figur als PDF (und SVG) in output_dir/basename.{pdf,svg}."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = output_dir / f'{basename}.pdf'
    fig.savefig(str(out_pdf), format='pdf', bbox_inches='tight', pad_inches=0.02)
    print(f'PDF: {out_pdf}')
    if also_svg:
        out_svg = output_dir / f'{basename}.svg'
        fig.savefig(str(out_svg), format='svg', bbox_inches='tight', pad_inches=0.02)
        print(f'SVG: {out_svg}')
    return out_pdf
