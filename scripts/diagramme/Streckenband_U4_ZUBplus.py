"""
Streckenband_U4_ZUBplus.py — Konzept-Schema der Rückfallebene ZUB+.

Momentaufnahme mit 5 Zügen auf einem schematischen Gleis:
    - Zug 1 (vorderster) ist notgebremst
    - Zug 3 ist mit ZUB+ besetzt und holt auf
Ein Pfeil verbindet Zug 3 mit Zug 1 und zeigt den Aufholweg. Der
Zug-Gap (Abstand in der Zugfolge, hier = 2) visualisiert, dass die
physische Störposition für die Interventionszeit zweitrangig ist —
entscheidend ist der Abstand zwischen gestörtem Zug und nächstem
ZUB+ in der Fahrtfolge.

Stil und Speicherung über thesis_style.

Verwendung:
    python3 Streckenband_U4_ZUBplus.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style as ts

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon


X_LEFT  = 0
X_RIGHT = 7388

LINE_Y       =  0.00
TRAIN_LENGTH = 900
TRAIN_H      = 0.20
Y_TRAIN_CENT = TRAIN_H / 2
Y_ARROW      =  0.32
Y_GAP_LABEL  =  0.35

LINE_COLOR  = ts.COLOR_NEUTRAL
LINE_LW     = 1.4
COLOR_DISRUPTED = ts.COLOR_PRIMARY
COLOR_ZUBPLUS   = ts.COLOR_ACCENT
COLOR_OTHER     = ts.COLOR_MUTED
COLOR_ARROW     = ts.COLOR_NEUTRAL


def sumo_train(x_tip, y_center, length, height,
               facecolor, edgecolor='black', lw=1.0):
    half_h = height / 2
    taper = length * 0.18
    pts = [
        (x_tip - length,  y_center - half_h),
        (x_tip - length,  y_center + half_h),
        (x_tip - taper,   y_center + half_h),
        (x_tip,           y_center),
        (x_tip - taper,   y_center - half_h),
    ]
    return Polygon(pts, closed=True, facecolor=facecolor,
                   edgecolor=edgecolor, linewidth=lw, zorder=10)


ts.apply_style()
fig, ax = plt.subplots(figsize=(6.3, 1.3))

ax.plot([X_LEFT, X_RIGHT], [LINE_Y, LINE_Y],
        color=LINE_COLOR, linewidth=LINE_LW,
        solid_capstyle='butt', zorder=2)

ax.annotate('', xy=(X_RIGHT + 350, LINE_Y),
            xytext=(X_RIGHT, LINE_Y),
            arrowprops=dict(arrowstyle='->', color=LINE_COLOR,
                            lw=LINE_LW, shrinkA=0, shrinkB=0),
            zorder=3)
ax.text(X_LEFT, LINE_Y - 0.04, 'Fahrtrichtung',
        ha='left', va='top', fontsize=7, fontstyle='italic',
        color=ts.COLOR_MUTED)

train_tip_positions = [7119, 5719, 4319, 2919, 1519]
train_states = ['disrupted', 'normal', 'zubplus', 'normal', 'normal']

for i, (x_tip, state) in enumerate(zip(train_tip_positions, train_states)):
    if state == 'disrupted':
        fc, ec, lw = COLOR_DISRUPTED, '#5a0000', 1.2
        label_color = COLOR_DISRUPTED
        header = 'Notbremsung'
    elif state == 'zubplus':
        fc, ec, lw = COLOR_ZUBPLUS, '#143d1f', 1.2
        label_color = COLOR_ZUBPLUS
        header = 'ZUB+'
    else:
        fc, ec, lw = COLOR_OTHER, ts.COLOR_NEUTRAL, 0.7
        label_color = ts.COLOR_MUTED
        header = None

    ax.add_patch(sumo_train(x_tip, Y_TRAIN_CENT,
                            TRAIN_LENGTH, TRAIN_H,
                            facecolor=fc, edgecolor=ec, lw=lw))

    body_center = x_tip - (TRAIN_LENGTH + TRAIN_LENGTH * 0.18) / 2
    ax.text(body_center, Y_TRAIN_CENT, f'Zug {i+1}',
            ha='center', va='center', fontsize=8, fontweight='bold',
            color='white', zorder=15)

    if header is not None:
        ax.text(body_center, LINE_Y - 0.04,
                header,
                ha='center', va='top',
                fontsize=8, fontweight='bold',
                color=label_color, zorder=15)

x_zub_tip = train_tip_positions[2]
x_gest_tip = train_tip_positions[0]

pfeil_start = x_zub_tip
pfeil_ende  = x_gest_tip

ax.annotate('', xy=(pfeil_ende, Y_ARROW), xytext=(pfeil_start, Y_ARROW),
            arrowprops=dict(arrowstyle='->', color=COLOR_ARROW,
                            lw=1.4, shrinkA=0, shrinkB=0),
            zorder=6)

gap_mid = (pfeil_start + pfeil_ende) / 2
ax.text(gap_mid, Y_GAP_LABEL, r'$g = 2$',
        ha='center', va='bottom', fontsize=9, fontweight='bold',
        color=COLOR_ARROW, zorder=15)

ax.plot([pfeil_start, pfeil_start],
        [Y_TRAIN_CENT, Y_ARROW],
        color=COLOR_ARROW, lw=0.6, linestyle=':', zorder=5)
ax.plot([pfeil_ende, pfeil_ende],
        [Y_TRAIN_CENT, Y_ARROW],
        color=COLOR_ARROW, lw=0.6, linestyle=':', zorder=5)

ax.set_xlim(X_LEFT - 200, X_RIGHT + 1100)
ax.set_ylim(-0.18, 0.55)
ax.set_yticks([])
ax.set_xticks([])
for side in ('left', 'right', 'top', 'bottom'):
    ax.spines[side].set_visible(False)

out_dir = Path(__file__).resolve().parents[2] / 'Diagramme'
ts.save_fig(fig, out_dir, 'Streckenband_U4_ZUBplus')
plt.close(fig)
