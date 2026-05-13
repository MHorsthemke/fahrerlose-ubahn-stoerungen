"""
plot_agentenverteilung.py — Grafik der Agentenverteilung auf der U4-Strecke.

Verwendung:
    python3 plot_agentenverteilung.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stations import STATIONS, STRECKE_START_KM, STRECKE_ENDE_KM
from sa_distribution import distribute_agents

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
rcParams['xtick.labelsize'] = 10
rcParams['ytick.labelsize'] = 11

# ===================================================================
# STRECKEN-PARAMETER
# ===================================================================
WENDEPUNKT_LINKS = 0
WENDEPUNKT_RECHTS = 7388
WENDE_LINKS_DIST = STRECKE_START_KM - WENDEPUNKT_LINKS   # 283m
WENDE_RECHTS_DIST = WENDEPUNKT_RECHTS - STRECKE_ENDE_KM  # 382m

station_kms = [s.km for s in STATIONS]
station_names = [s.name for s in STATIONS]

all_kms = [WENDEPUNKT_LINKS] + station_kms + [WENDEPUNKT_RECHTS]
all_names = ['Wendep. BW'] + station_names + ['Wendep. Seckb.L.']

# ===================================================================
# DARSTELLUNGSPARAMETER
# ===================================================================
FIGSIZE = (18, 10)
COLORS_LEFT = '#4472C4'
COLORS_RIGHT = '#ED7D31'
AGENT_COLOR = '#2F5496'
STATION_LINE_COLOR = '#C0C0C0'
WENDE_COLOR = '#555555'
WENDE_ZONE_COLOR = '#EEEEEE'
ROW_SPACING = 0.55                        # Enger zusammen
ARROW_LW = 1.3
BAR_ALPHA = 0.3
DIST_LABEL_SIZE = 9         # Laufweg-Labels auf den Agenten-Pfeilen
STATION_DIST_SIZE = 10      # Haltestellenabstände

# ===================================================================
# GRAFIK
# ===================================================================
n_variants = 10

# Berechne Y-Positionen
y_positions = [(n_variants - i) * ROW_SPACING + ROW_SPACING for i in range(1, n_variants + 1)]
# Distanzzeile: 0.25x so dick wie eine Agentenzeile
DIST_ROW_GAP = ROW_SPACING * 0.25
DIST_ROW_Y = y_positions[-1] - ROW_SPACING * 0.5 - DIST_ROW_GAP * 0.5

fig, ax = plt.subplots(figsize=FIGSIZE)

# Wendegleis-Bereiche
ax.axvspan(WENDEPUNKT_LINKS, STRECKE_START_KM, color=WENDE_ZONE_COLOR, zorder=0)
ax.axvspan(STRECKE_ENDE_KM, WENDEPUNKT_RECHTS, color=WENDE_ZONE_COLOR, zorder=0)

# Wendepunkte
ax.axvline(x=WENDEPUNKT_LINKS, color=WENDE_COLOR, linewidth=1.5, zorder=2)
ax.axvline(x=WENDEPUNKT_RECHTS, color=WENDE_COLOR, linewidth=1.5, zorder=2)

# Stationslinien
for km in station_kms:
    ax.axvline(x=km, color=STATION_LINE_COLOR, linewidth=0.4, linestyle='--', zorder=1)

# --- Stationsabstände: auf der Abszisse (transform=xaxis) ---
# Wird unten gezeichnet, nach den Achsenlimits

# --- Agenten-Zeilen ---
for num_agents in range(1, n_variants + 1):
    y = y_positions[num_agents - 1]
    indices = distribute_agents(num_agents)
    kms = [STATIONS[i].km for i in indices]

    bereiche = []
    for j in range(len(kms)):
        links = WENDEPUNKT_LINKS if j == 0 else (kms[j-1] + kms[j]) / 2
        rechts = WENDEPUNKT_RECHTS if j == len(kms)-1 else (kms[j] + kms[j+1]) / 2
        bereiche.append((links, rechts))

    bar_h = ROW_SPACING * 0.75

    for j, idx in enumerate(indices):
        km = kms[j]
        links, rechts = bereiche[j]
        lw_links = km - links
        lw_rechts = rechts - km

        # Balken
        ax.barh(y, lw_links, left=links, height=bar_h,
                color=COLORS_LEFT, alpha=BAR_ALPHA, edgecolor='none', zorder=3)
        ax.barh(y, lw_rechts, left=km, height=bar_h,
                color=COLORS_RIGHT, alpha=BAR_ALPHA, edgecolor='none', zorder=3)

        # Grenzlinien
        ax.plot([links, links], [y - bar_h/2, y + bar_h/2],
                color='#999999', linewidth=0.6, zorder=4)
        ax.plot([rechts, rechts], [y - bar_h/2, y + bar_h/2],
                color='#999999', linewidth=0.6, zorder=4)

        # Agent-Punkt
        ax.plot(km, y, 'o', color=AGENT_COLOR, markersize=5, zorder=6)

        # Pfeile + Beschriftung AUF dem Pfeil
        if lw_links > 80:
            ax.annotate('', xy=(links, y), xytext=(km, y),
                        arrowprops=dict(arrowstyle='->', color=COLORS_LEFT, lw=ARROW_LW), zorder=5)
            ax.text((links + km) / 2, y, f'{lw_links:.0f}m', ha='center', va='center',
                    fontsize=DIST_LABEL_SIZE, color='white', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.12', facecolor=COLORS_LEFT, alpha=0.85,
                              edgecolor='none'), zorder=7)

        if lw_rechts > 80:
            ax.annotate('', xy=(rechts, y), xytext=(km, y),
                        arrowprops=dict(arrowstyle='->', color=COLORS_RIGHT, lw=ARROW_LW), zorder=5)
            ax.text((km + rechts) / 2, y, f'{lw_rechts:.0f}m', ha='center', va='center',
                    fontsize=DIST_LABEL_SIZE, color='white', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.12', facecolor=COLORS_RIGHT, alpha=0.85,
                              edgecolor='none'), zorder=7)

    # Max. Laufweg rechts
    max_lw = max(max(kms[j] - bereiche[j][0], bereiche[j][1] - kms[j]) for j in range(len(kms)))
    ax.text(WENDEPUNKT_RECHTS + 120, y, f'{max_lw:.0f}m',
            fontsize=10, va='center', fontweight='bold', color='#333333')

# --- Y-Achse ---
ax.set_yticks(y_positions)
ax.set_yticklabels([f'{i} Agent{"en" if i > 1 else ""}' for i in range(1, n_variants + 1)])

# --- Achsenlimits ---
ax.set_xlim(WENDEPUNKT_LINKS - 200, WENDEPUNKT_RECHTS + 750)
# Knapper Rand unter der Distanzzeile
ax.set_ylim(DIST_ROW_Y - DIST_ROW_GAP, y_positions[0] + ROW_SPACING * 0.6)

# --- X-Achse: Tick-Labels leer, wir machen eigene ---
ax.set_xticks(all_kms)
ax.set_xticklabels([''] * len(all_kms))

# --- Stationsabstände: Zeile unter den 10 Agenten ---
for i in range(len(all_kms) - 1):
    dist = all_kms[i+1] - all_kms[i]
    mid = (all_kms[i] + all_kms[i+1]) / 2
    ax.annotate('', xy=(all_kms[i], DIST_ROW_Y), xytext=(all_kms[i+1], DIST_ROW_Y),
                arrowprops=dict(arrowstyle='<->', color='#888888', lw=0.7))
    ax.text(mid, DIST_ROW_Y, f'{dist:.0f}m', ha='center', va='center',
            fontsize=STATION_DIST_SIZE, color='#444444',
            bbox=dict(boxstyle='round,pad=0.1', facecolor='white', alpha=0.9,
                      edgecolor='none'))

# --- Stationsnamen mit km-Angabe in einer Zeile, versetzt auf zwei Höhen ---
for i, (km, name) in enumerate(zip(all_kms, all_names)):
    km_str = f'{km/1000:.1f}'.replace('.', ',')
    label = f'{name} ({km_str} km)'

    if i % 2 == 0:
        y_name = -0.02
    else:
        y_name = -0.055

    ax.text(km, y_name, label, ha='center', va='top', fontsize=9.5,
            transform=ax.get_xaxis_transform(), clip_on=False)

    # Verbindungsstrich von Abszisse zur 2. Zeile (schwarz, für ungerade Indizes)
    if i % 2 == 1:
        ax.plot([km, km], [-0.005, -0.05],
                color='black', linewidth=0.7, zorder=1, clip_on=False,
                transform=ax.get_xaxis_transform())

# Max. Laufweg Header
ax.text(WENDEPUNKT_RECHTS + 120, y_positions[0] + ROW_SPACING * 0.5, 'Max.\nLaufweg',
        fontsize=10, va='center', ha='left', fontweight='bold', color='#333333')

ax.set_title('Agentenverteilung und Abdeckungsbereiche — U4 Frankfurt',
             fontsize=14, fontweight='bold', pad=10)

ax.spines['top'].set_visible(False)

# Legende — eine Zeile, zentriert unter den Stationsnamen
legend_elements = [
    mpatches.Patch(facecolor=COLORS_LEFT, alpha=BAR_ALPHA, label='Laufweg links'),
    mpatches.Patch(facecolor=COLORS_RIGHT, alpha=BAR_ALPHA, label='Laufweg rechts'),
    plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=AGENT_COLOR,
               markersize=8, label='Stationsagent'),
    mpatches.Patch(facecolor=WENDE_ZONE_COLOR, edgecolor='#999999', label='Wendegleis'),
]
ax.legend(handles=legend_elements, loc='upper center', fontsize=9, framealpha=0.9,
          ncol=4, bbox_to_anchor=(0.5, -0.09))

plt.tight_layout()
plt.subplots_adjust(bottom=0.22)

# ===================================================================
# SPEICHERN
# ===================================================================
output_dir = Path(__file__).resolve().parents[2] / "Diagramme"
output_dir.mkdir(parents=True, exist_ok=True)
out_pdf = output_dir / "Agentenverteilung_U4.pdf"
out_svg = output_dir / "Agentenverteilung_U4.svg"
fig.savefig(str(out_pdf), format='pdf', bbox_inches='tight', dpi=300)
fig.savefig(str(out_svg), format='svg', bbox_inches='tight')
print(f"PDF: {out_pdf}")
print(f"SVG: {out_svg}")
