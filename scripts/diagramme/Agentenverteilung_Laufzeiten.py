"""
Agentenverteilung_Laufzeiten.py — Agentenverteilung mit Laufweg und Laufzeit pro Strecke.

Stil und Speicherung über thesis_style.

Verwendung:
    python3 Agentenverteilung_Laufzeiten.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stations import STATIONS, STRECKE_START_KM, STRECKE_ENDE_KM
from sa_distribution import distribute_agents

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style as ts

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D


WALK_SPEED_MS = 3.33

WENDEPUNKT_LINKS = 0
WENDEPUNKT_RECHTS = 7388
WENDE_LINKS_DIST = STRECKE_START_KM - WENDEPUNKT_LINKS
WENDE_RECHTS_DIST = WENDEPUNKT_RECHTS - STRECKE_ENDE_KM

station_kms = [s.km for s in STATIONS]
station_names = [s.name for s in STATIONS]

all_kms = [WENDEPUNKT_LINKS] + station_kms + [WENDEPUNKT_RECHTS]
all_names = ['Wendep. BW'] + station_names + ['Wendep. Seckb.L.']

COLOR_LEFT = ts.COLOR_PRIMARY
COLOR_RIGHT = ts.COLOR_ACCENT
AGENT_COLOR = ts.COLOR_PRIMARY_DARK
STATION_LINE_COLOR = ts.COLOR_GRID
WENDE_COLOR = ts.COLOR_NEUTRAL
WENDE_ZONE_COLOR = '#EEEEEE'

ROW_SPACING = 0.65
ARROW_LW = 0.9
BAR_ALPHA = 0.30
DIST_LABEL_SIZE = 6
TIME_LABEL_SIZE = 6
STATION_DIST_SIZE = 7
LABEL_OFFSET = 0.13


def walk_time_min(distance_m: float) -> float:
    return (distance_m / WALK_SPEED_MS) / 60.0


ts.apply_style()

n_variants = 10
y_positions = [(n_variants - i) * ROW_SPACING + ROW_SPACING for i in range(1, n_variants + 1)]
DIST_ROW_GAP = ROW_SPACING * 0.25
DIST_ROW_Y = y_positions[-1] - ROW_SPACING * 0.5 - DIST_ROW_GAP * 0.5

fig, ax = plt.subplots(figsize=(6.3, 5.0))
fig.subplots_adjust(left=0.06, right=0.99, top=0.99, bottom=0.15)

ax.axvspan(WENDEPUNKT_LINKS, STRECKE_START_KM, color=WENDE_ZONE_COLOR, zorder=0)
ax.axvspan(STRECKE_ENDE_KM, WENDEPUNKT_RECHTS, color=WENDE_ZONE_COLOR, zorder=0)

ax.axvline(x=WENDEPUNKT_LINKS, color=WENDE_COLOR, linewidth=0.8, zorder=2)
ax.axvline(x=WENDEPUNKT_RECHTS, color=WENDE_COLOR, linewidth=0.8, zorder=2)

for km in station_kms:
    ax.axvline(x=km, color=STATION_LINE_COLOR, linewidth=0.3, linestyle='--', zorder=1)

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

        ax.barh(y, lw_links, left=links, height=bar_h,
                color=COLOR_LEFT, alpha=BAR_ALPHA, edgecolor='none', zorder=3)
        ax.barh(y, lw_rechts, left=km, height=bar_h,
                color=COLOR_RIGHT, alpha=BAR_ALPHA, edgecolor='none', zorder=3)

        ax.plot([links, links], [y - bar_h/2, y + bar_h/2],
                color=ts.COLOR_GRID, linewidth=0.4, zorder=4)
        ax.plot([rechts, rechts], [y - bar_h/2, y + bar_h/2],
                color=ts.COLOR_GRID, linewidth=0.4, zorder=4)

        ax.plot(km, y, 'o', color=AGENT_COLOR, markersize=3, zorder=6)

        if lw_links > 200:
            ax.annotate('', xy=(links, y), xytext=(km, y),
                        arrowprops=dict(arrowstyle='->', color=COLOR_LEFT,
                                        lw=ARROW_LW, shrinkA=0, shrinkB=0),
                        zorder=5)
            ax.text((links + km) / 2, y + LABEL_OFFSET, f'{lw_links:.0f}',
                    ha='center', va='center',
                    fontsize=DIST_LABEL_SIZE, color='white', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.10', facecolor=COLOR_LEFT,
                              alpha=0.85, edgecolor='none'), zorder=7)
            t_min = walk_time_min(lw_links)
            ax.text((links + km) / 2, y - LABEL_OFFSET, f'{t_min:.1f}',
                    ha='center', va='center',
                    fontsize=TIME_LABEL_SIZE, color='white', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.10', facecolor=COLOR_LEFT,
                              alpha=0.55, edgecolor='none'), zorder=7)

        if lw_rechts > 200:
            ax.annotate('', xy=(rechts, y), xytext=(km, y),
                        arrowprops=dict(arrowstyle='->', color=COLOR_RIGHT,
                                        lw=ARROW_LW, shrinkA=0, shrinkB=0),
                        zorder=5)
            ax.text((km + rechts) / 2, y + LABEL_OFFSET, f'{lw_rechts:.0f}',
                    ha='center', va='center',
                    fontsize=DIST_LABEL_SIZE, color='white', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.10', facecolor=COLOR_RIGHT,
                              alpha=0.85, edgecolor='none'), zorder=7)
            t_min = walk_time_min(lw_rechts)
            ax.text((km + rechts) / 2, y - LABEL_OFFSET, f'{t_min:.1f}',
                    ha='center', va='center',
                    fontsize=TIME_LABEL_SIZE, color='white', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.10', facecolor=COLOR_RIGHT,
                              alpha=0.55, edgecolor='none'), zorder=7)

    max_lw = max(max(kms[j] - bereiche[j][0], bereiche[j][1] - kms[j])
                 for j in range(len(kms)))
    max_t = walk_time_min(max_lw)
    ax.text(WENDEPUNKT_RECHTS + 80, y + 0.07,
            f'{max_lw:.0f} m', fontsize=7, va='center',
            fontweight='bold', color=ts.COLOR_NEUTRAL)
    ax.text(WENDEPUNKT_RECHTS + 80, y - 0.12,
            f'{max_t:.1f} min', fontsize=6.5, va='center',
            color=ts.COLOR_MUTED, fontstyle='italic')

ax.set_yticks(y_positions)
ax.set_yticklabels([f'{i}' for i in range(1, n_variants + 1)])
ax.set_ylabel('Anzahl Stationsagenten')

ax.set_xlim(WENDEPUNKT_LINKS, WENDEPUNKT_RECHTS + 350)
ax.set_ylim(DIST_ROW_Y - DIST_ROW_GAP, y_positions[0] + ROW_SPACING * 0.6)

ax.set_xticks(all_kms)
ax.set_xticklabels([''] * len(all_kms))

for i in range(len(all_kms) - 1):
    dist = all_kms[i+1] - all_kms[i]
    mid = (all_kms[i] + all_kms[i+1]) / 2
    ax.annotate('', xy=(all_kms[i], DIST_ROW_Y), xytext=(all_kms[i+1], DIST_ROW_Y),
                arrowprops=dict(arrowstyle='<->', color=ts.COLOR_GRID, lw=0.5))
    ax.text(mid, DIST_ROW_Y, f'{dist:.0f}m', ha='center', va='center',
            fontsize=STATION_DIST_SIZE, color=ts.COLOR_MUTED,
            bbox=dict(boxstyle='round,pad=0.08', facecolor='white', alpha=0.9,
                      edgecolor='none'))

for i, (km, name) in enumerate(zip(all_kms, all_names)):
    if i % 2 == 0:
        y_name = -0.02
    else:
        y_name = -0.06

    ax.text(km, y_name, name, ha='center', va='top', fontsize=7,
            transform=ax.get_xaxis_transform(), clip_on=False)

    if i % 2 == 1:
        is_near_wende = (i == 1) or (i == len(all_kms) - 1)
        if is_near_wende:
            ax.plot([km, km], [-0.005, -0.018],
                    color=ts.COLOR_NEUTRAL, linewidth=0.5, zorder=1, clip_on=False,
                    transform=ax.get_xaxis_transform())
            ax.plot([km, km], [-0.043, -0.055],
                    color=ts.COLOR_NEUTRAL, linewidth=0.5, zorder=1, clip_on=False,
                    transform=ax.get_xaxis_transform())
        else:
            ax.plot([km, km], [-0.005, -0.055],
                    color=ts.COLOR_NEUTRAL, linewidth=0.5, zorder=1, clip_on=False,
                    transform=ax.get_xaxis_transform())

ax.text(WENDEPUNKT_RECHTS + 80, y_positions[0] + ROW_SPACING * 0.5,
        'Max.\nLaufweg', fontsize=7, va='center', ha='left',
        fontweight='bold', color=ts.COLOR_NEUTRAL)

legend_elements = [
    mpatches.Patch(facecolor=COLOR_LEFT, alpha=BAR_ALPHA, label='Laufweg links'),
    mpatches.Patch(facecolor=COLOR_RIGHT, alpha=BAR_ALPHA, label='Laufweg rechts'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor=AGENT_COLOR,
           markersize=5, label='Stationsagent', linestyle='None'),
    mpatches.Patch(facecolor=WENDE_ZONE_COLOR, edgecolor=ts.COLOR_GRID,
                   label='Wendegleis'),
    Line2D([], [], color='none',
           label=f'$v_\\text{{geh}} = {WALK_SPEED_MS}$ m/s'),
]
ts.place_legend_below(ax, ncol=5, y_offset=-0.13, handles=legend_elements)

output_dir = Path(__file__).resolve().parents[2] / 'Diagramme'
ts.save_fig(fig, output_dir, 'Agentenverteilung_Laufzeiten')
plt.close(fig)
