"""
Streckenband_U4.py — Schematische Streckendarstellung der U4 Frankfurt.

Darstellung als Umlauf mit Rechtsverkehr in drei Ebenen:
  - Untere Ebene:  Hinfahrt → (Bockenheimer Warte → Seckbacher Landstr.)
  - Obere Ebene:   ← Rückfahrt (Seckbacher Landstr. → Bockenheimer Warte)
  - Mittlere Ebene: nur Wendegleise an den Rändern (< und > mit Stumpfgleis)

Haltestellen als maßstabsgetreue Rechtecke (110 m).
Laufweg [m] an der Ausfahrtsposition jeder Haltestelle.
Abstände als Pfeile von Ausfahrt zu Ausfahrt.

Hin-Distanzen aus station.km (Edge-km in stations.py).
Rück-Distanzen und -Umlaufpositionen aus SUMO-Messung
(STATIONS[i].lap_pos_rueck in stations.py).

Stil und Speicherung über thesis_style.

Verwendung:
    python3 Streckenband_U4.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stations import STATIONS

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style as ts

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


SHORT_NAMES = {
    "Bockenheimer Warte":     "Bock. Warte",
    "Festhalle/Messe":        "Festh./Messe",
    "Hauptbahnhof":           "Hbf",
    "Willy-Brandt-Platz":     "W.-Brandt-Pl.",
    "Dom/Römer":              "Dom/Römer",
    "Konstablerwache":        "Konstablerw.",
    "Merianplatz":            "Merianpl.",
    "Höhenstraße":            "Höhenstr.",
    "Bornheim Mitte":         "Bornh. Mitte",
    "Seckbacher Landstraße":  "Seckb. Landstr.",
}

station_names = [SHORT_NAMES.get(s.name, s.name) for s in STATIONS]
station_kms = [s.km for s in STATIONS]
N_STATIONS = len(station_kms)
HALTESTELLENLAENGE = 110  # m
HALF_HS = HALTESTELLENLAENGE / 2

STUMPF_LINKS = 0
STUMPF_RECHTS = 7388
UMLAUF_GESAMT = 15238  # m, gemessen aus SUMO Umlauf

# Rück-Umlaufposition direkt aus SUMO-Messung in stations.py (lap_pos_rueck,
# Bahnsteigmitte der Rückrichtung in Umlaufkoordinaten):
rueck_lap_kms = [int(round(s.lap_pos_rueck)) for s in reversed(STATIONS)]

hin_ausfahrt = [km + HALF_HS for km in station_kms]
rueck_ausfahrt = [km - HALF_HS for km in reversed(station_kms)]

rueck_x_positions = list(reversed(station_kms))
rueck_names = list(reversed(station_names))


TRACK_COLOR = ts.COLOR_NEUTRAL
TRACK_LW = 1.6
WENDE_LW = 1.2

HIN_COLOR = ts.COLOR_PRIMARY
RUECK_COLOR = ts.COLOR_ACCENT
WENDE_COLOR = ts.COLOR_MUTED
STATION_ALPHA = 0.85
STATION_H = 0.18
NAME_COLOR = ts.COLOR_NEUTRAL

Y_HIN = 0.0
Y_MID = 0.7
Y_RUECK = 1.4

NAME_GAP = 0.13
Y_HIN_NAME_A = Y_HIN - 0.08
Y_HIN_NAME_B = Y_HIN_NAME_A - NAME_GAP
Y_HIN_KM = Y_HIN_NAME_B - 0.13

Y_RUECK_NAME_A = Y_RUECK + 0.08
Y_RUECK_NAME_B = Y_RUECK_NAME_A + NAME_GAP
Y_RUECK_KM = Y_RUECK_NAME_B + 0.13

DIST_ARROW_COLOR = ts.COLOR_GRID
DIST_COLOR = ts.COLOR_MUTED
DIST_FONT_SIZE = 6.5
KM_COLOR = ts.COLOR_MUTED
KM_FONT_SIZE = 6


ts.apply_style()
fig, ax = plt.subplots(figsize=(6.3, 2.5))

ax.plot([station_kms[0] - HALF_HS, station_kms[-1] + HALF_HS], [Y_HIN, Y_HIN],
        color=TRACK_COLOR, linewidth=TRACK_LW, solid_capstyle='butt', zorder=2)
ax.plot([station_kms[0] - HALF_HS, station_kms[-1] + HALF_HS], [Y_RUECK, Y_RUECK],
        color=TRACK_COLOR, linewidth=TRACK_LW, solid_capstyle='butt', zorder=2)

wende_r_x = station_kms[-1] + HALF_HS
stumpf_r_x = STUMPF_RECHTS

ax.plot([wende_r_x, stumpf_r_x], [Y_HIN, Y_MID],
        color=WENDE_COLOR, linewidth=WENDE_LW, zorder=2)
ax.plot([stumpf_r_x, wende_r_x], [Y_MID, Y_RUECK],
        color=WENDE_COLOR, linewidth=WENDE_LW, zorder=2)
stumpf_r_end = stumpf_r_x + 200
ax.plot([stumpf_r_x, stumpf_r_end], [Y_MID, Y_MID],
        color=WENDE_COLOR, linewidth=TRACK_LW, zorder=2)
ax.plot([stumpf_r_end, stumpf_r_end], [Y_MID - 0.10, Y_MID + 0.10],
        color=WENDE_COLOR, linewidth=2.8, solid_capstyle='butt', zorder=3)

wende_l_x = station_kms[0] - HALF_HS

ax.plot([wende_l_x, STUMPF_LINKS], [Y_RUECK, Y_MID],
        color=WENDE_COLOR, linewidth=WENDE_LW, zorder=2)
ax.plot([STUMPF_LINKS, wende_l_x], [Y_MID, Y_HIN],
        color=WENDE_COLOR, linewidth=WENDE_LW, zorder=2)
stumpf_l_end = STUMPF_LINKS - 200
ax.plot([STUMPF_LINKS, stumpf_l_end], [Y_MID, Y_MID],
        color=WENDE_COLOR, linewidth=TRACK_LW, zorder=2)
ax.plot([stumpf_l_end, stumpf_l_end], [Y_MID - 0.10, Y_MID + 0.10],
        color=WENDE_COLOR, linewidth=2.8, solid_capstyle='butt', zorder=3)

ax.text(stumpf_l_end - 60, Y_MID, 'Stumpfgleis',
        ha='right', va='center', fontsize=6.5, color=ts.COLOR_MUTED,
        fontstyle='italic', zorder=5)

for i, km in enumerate(station_kms):
    x_left = km - HALF_HS
    rect = Rectangle((x_left, Y_HIN), HALTESTELLENLAENGE, STATION_H,
                      facecolor=HIN_COLOR, alpha=STATION_ALPHA,
                      edgecolor='none', linewidth=0, zorder=4)
    ax.add_patch(rect)

for i, km in enumerate(rueck_x_positions):
    x_left = km - HALF_HS
    rect = Rectangle((x_left, Y_RUECK - STATION_H), HALTESTELLENLAENGE, STATION_H,
                      facecolor=RUECK_COLOR, alpha=STATION_ALPHA,
                      edgecolor='none', linewidth=0, zorder=4)
    ax.add_patch(rect)

for i, (km, name) in enumerate(zip(station_kms, station_names)):
    y_hin = Y_HIN_NAME_A if i % 2 == 0 else Y_HIN_NAME_B
    y_rueck = Y_RUECK_NAME_A if i % 2 == 0 else Y_RUECK_NAME_B
    ax.text(km, y_hin, name,
            ha='center', va='center', fontsize=7, fontweight='bold',
            color=NAME_COLOR, zorder=5)
    ax.text(km, y_rueck, name,
            ha='center', va='center', fontsize=7, fontweight='bold',
            color=NAME_COLOR, zorder=5)

for i, km in enumerate(station_kms):
    ausfahrt_km = km + HALF_HS
    ax.text(ausfahrt_km, Y_HIN_KM, f'{ausfahrt_km:.0f} m',
            ha='center', va='center', fontsize=KM_FONT_SIZE,
            color=KM_COLOR, zorder=5)

    umlauf_km = rueck_lap_kms[N_STATIONS - 1 - i]
    ausfahrt_x = km - HALF_HS
    ax.text(ausfahrt_x, Y_RUECK_KM, f'{umlauf_km} m',
            ha='center', va='center', fontsize=KM_FONT_SIZE,
            color=KM_COLOR, zorder=5)

ax.text(stumpf_l_end - 60, Y_HIN_KM, 'Umlaufposition',
        ha='right', va='center', fontsize=6.5, color=ts.COLOR_MUTED,
        fontstyle='italic', zorder=5)
ax.text(stumpf_l_end - 60, Y_RUECK_KM, 'Umlaufposition',
        ha='right', va='center', fontsize=6.5, color=ts.COLOR_MUTED,
        fontstyle='italic', zorder=5)

y_arr_hin = Y_HIN + STATION_H + 0.06
for i in range(N_STATIONS - 1):
    x_start = station_kms[i] + HALF_HS
    x_end = station_kms[i + 1] + HALF_HS
    dist = x_end - x_start
    mid = (x_start + x_end) / 2

    ax.annotate('', xy=(x_end, y_arr_hin), xytext=(x_start, y_arr_hin),
                arrowprops=dict(arrowstyle='->', color=DIST_ARROW_COLOR,
                                lw=0.7), zorder=3)
    ax.text(mid, y_arr_hin + 0.03, f'{dist:.0f} m',
            ha='center', va='bottom', fontsize=DIST_FONT_SIZE,
            color=DIST_COLOR, zorder=5)

y_arr_rueck = Y_RUECK - STATION_H - 0.06
for i in range(N_STATIONS - 1):
    x_start = rueck_x_positions[i] - HALF_HS
    x_end = rueck_x_positions[i + 1] - HALF_HS
    dist_umlauf = rueck_lap_kms[i + 1] - rueck_lap_kms[i]
    mid = (x_start + x_end) / 2

    ax.annotate('', xy=(x_end, y_arr_rueck), xytext=(x_start, y_arr_rueck),
                arrowprops=dict(arrowstyle='->', color=DIST_ARROW_COLOR,
                                lw=0.7), zorder=3)
    ax.text(mid, y_arr_rueck - 0.03, f'{dist_umlauf} m',
            ha='center', va='top', fontsize=DIST_FONT_SIZE,
            color=DIST_COLOR, zorder=5)


ax.set_xlim(stumpf_l_end - 700, stumpf_r_end + 100)
ax.set_ylim(Y_HIN_KM - 0.08, Y_RUECK_KM + 0.08)

ax.set_yticks([])
ax.set_xticks([])
for side in ('left', 'right', 'top', 'bottom'):
    ax.spines[side].set_visible(False)


out_dir = Path(__file__).resolve().parents[2] / 'Diagramme'
ts.save_fig(fig, out_dir, 'Streckenband_U4')
plt.close(fig)
