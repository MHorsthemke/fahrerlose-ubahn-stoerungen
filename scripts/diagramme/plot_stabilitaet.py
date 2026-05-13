"""
plot_stabilitaet.py — Stabilitätsnachweis: Weg-Zeit-Diagramm über alle Runden.

Zeigt, dass die Simulation im eingeschwungenen Zustand ist (steady state),
bevor die Störung in Runde 10 ausgelöst wird.

Jede Runde wird als eigene Kurve geplottet:
  - X-Achse: Zeit innerhalb der Runde (s) → normalisiert auf 0 je Runde
  - Y-Achse: Distanz innerhalb der Runde (m)

Wenn alle Kurven übereinander liegen → stabiler Regelbetrieb nachgewiesen.

Stil und Speicherung über thesis_style.

Verwendung:
    python3 plot_stabilitaet.py [pfad_zur_traci_log_csv]

    Ohne Argument wird output/traci_log.csv verwendet.
"""

import sys
import csv
import numpy as np
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style as ts


def parse_german_float(s: str) -> float | None:
    if not s or s.strip() == '':
        return None
    return float(s.replace(',', '.'))


def load_lap_data(csv_path: Path) -> dict[int, dict]:
    laps: dict[int, dict] = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                lap = int(row['lap'])
                sim_time = parse_german_float(row['sim_time'])
                dist_in_lap = parse_german_float(row['dist_in_lap_m'])
                speed = parse_german_float(row['speed'])
            except (ValueError, TypeError, KeyError):
                continue

            if dist_in_lap is None or sim_time is None:
                continue

            if lap not in laps:
                laps[lap] = {
                    "sim_time": [],
                    "dist_in_lap": [],
                    "speed": [],
                    "start_time": sim_time,
                }

            laps[lap]["sim_time"].append(sim_time)
            laps[lap]["dist_in_lap"].append(dist_in_lap)
            laps[lap]["speed"].append(speed if speed is not None else 0.0)

    if laps:
        max_points = max(len(laps[lap]["sim_time"]) for lap in laps)
        threshold = max_points
        incomplete = [lap for lap in laps
                      if len(laps[lap]["sim_time"]) < threshold]
        for lap in incomplete:
            print(f"  Runde {lap} entfernt (unvollständig: "
                  f"{len(laps[lap]['sim_time'])}/{max_points} Punkte)")
            del laps[lap]

    for lap in laps:
        laps[lap]["sim_time"] = np.array(laps[lap]["sim_time"])
        laps[lap]["dist_in_lap"] = np.array(laps[lap]["dist_in_lap"])
        laps[lap]["speed"] = np.array(laps[lap]["speed"])
        laps[lap]["time_in_lap"] = laps[lap]["sim_time"] - laps[lap]["start_time"]

    return laps


def plot_weg_zeit(laps: dict, output_dir: Path):
    ts.apply_style()
    fig, ax = plt.subplots(figsize=ts.FIGSIZE_DEFAULT)

    sorted_laps = sorted(laps.keys())
    colors = ts.cmap_categorical(len(sorted_laps))

    t_max = 0.0
    d_max = 0.0
    for i, lap_nr in enumerate(sorted_laps):
        lap = laps[lap_nr]
        t = lap["time_in_lap"]
        d = lap["dist_in_lap"] / 1000

        alpha = 0.85 if lap_nr > 0 else 0.40
        lw = 1.2

        ax.plot(t, d, color=colors[i], alpha=alpha, linewidth=lw,
                label=f'Runde {lap_nr}',
                zorder=3 if lap_nr > 0 else 2)

        t_max = max(t_max, float(t[-1]))
        d_max = max(d_max, float(d[-1]))

    ax.set_xlabel('Zeit innerhalb der Runde (s)')
    ax.set_ylabel('Zurückgelegte Distanz (km)')
    ax.set_xlim(0, t_max)
    ax.set_ylim(0, d_max * 1.02)

    ts.add_grid(ax, axis='both')
    ts.place_legend_below(ax, ncol=len(sorted_laps), y_offset=-0.20)

    ts.save_fig(fig, output_dir, 'Stabilitaet_WegZeit')
    plt.close(fig)


def plot_speed_zeit(laps: dict, output_dir: Path):
    ts.apply_style()
    fig, ax = plt.subplots(figsize=ts.FIGSIZE_WIDE)

    sorted_laps = sorted(laps.keys())
    colors = ts.cmap_categorical(len(sorted_laps))

    v_max = 0.0
    for i, lap_nr in enumerate(sorted_laps):
        lap = laps[lap_nr]
        t = lap["time_in_lap"]
        v = lap["speed"] * 3.6

        alpha = 0.80 if lap_nr > 0 else 0.35
        lw = 1.0

        ax.plot(t, v, color=colors[i], alpha=alpha, linewidth=lw,
                label=f'Runde {lap_nr}',
                zorder=3 if lap_nr > 0 else 2)

        v_max = max(v_max, float(v.max()) if len(v) else 0.0)

    ax.set_xlabel('Zeit innerhalb der Runde (s)')
    ax.set_ylabel('Geschwindigkeit (km/h)')
    ax.set_xlim(0, 1600)
    ax.set_xticks([0, 200, 400, 600, 800, 1000, 1200, 1400, 1600])
    ax.set_ylim(0, v_max * 1.05)

    ts.add_grid(ax, axis='y')
    ts.place_legend_below(ax, ncol=len(sorted_laps), y_offset=-0.13)

    ts.save_fig(fig, output_dir, 'Stabilitaet_Geschwindigkeit')
    plt.close(fig)


def plot_rundendauer(laps: dict, output_dir: Path):
    ts.apply_style()
    fig, ax = plt.subplots(figsize=ts.FIGSIZE_DEFAULT)

    lap_nrs = sorted(laps.keys())
    durations = []
    for lap_nr in lap_nrs:
        t = laps[lap_nr]["time_in_lap"]
        durations.append(t[-1] - t[0])

    mean_dur = np.mean(durations)
    std_dur = np.std(durations, ddof=1) if len(durations) > 1 else 0.0

    ax.bar(lap_nrs, durations, color=ts.COLOR_PRIMARY, alpha=0.85,
           edgecolor='white', width=0.6, zorder=3)
    ax.axhline(y=mean_dur, color=ts.COLOR_ACCENT, linewidth=1.4,
               linestyle='--', zorder=4,
               label=rf'Mittelwert: {mean_dur:.0f} s ($\sigma$={std_dur:.1f} s)')

    for lap_nr, dur in zip(lap_nrs, durations):
        ax.text(lap_nr, dur + max(durations) * 0.015,
                f'{dur:.0f} s',
                ha='center', va='bottom', fontsize=8,
                fontweight='bold', color=ts.COLOR_PRIMARY_DARK)

    ax.set_xlabel('Runde')
    ax.set_ylabel('Rundendauer (s)')
    ax.set_xticks(lap_nrs)
    ax.set_xlim(min(lap_nrs) - 0.6, max(lap_nrs) + 0.6)
    ax.set_ylim(0, max(durations) * 1.15)

    ts.add_grid(ax, axis='y')
    ts.place_legend_below(ax, ncol=1, y_offset=-0.18)

    ts.save_fig(fig, output_dir, 'Stabilitaet_Rundendauer')
    plt.close(fig)


if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parents[2]
    output_dir = base_dir / 'Diagramme'

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = base_dir / 'output' / 'traci_log.csv'

    print(f"CSV: {csv_path}")

    laps = load_lap_data(csv_path)
    if not laps:
        print("FEHLER: Keine Rundendaten gefunden!")
        sys.exit(1)

    MAX_LAP = 4
    laps = {k: v for k, v in laps.items() if k <= MAX_LAP}

    print(f"Runden gefunden: {sorted(laps.keys())}")
    for lap_nr in sorted(laps.keys()):
        n = len(laps[lap_nr]["time_in_lap"])
        dur = laps[lap_nr]["time_in_lap"][-1]
        print(f"  Runde {lap_nr}: {n} Datenpunkte, {dur:.0f}s Dauer")

    plot_weg_zeit(laps, output_dir)
    plot_speed_zeit(laps, output_dir)
    plot_rundendauer(laps, output_dir)

    print(f"\nFertig! Alle Diagramme in {output_dir}")
