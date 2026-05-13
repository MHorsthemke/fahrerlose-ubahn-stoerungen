"""
measure_umlauf.py — Misst pro Simulationsschritt die Umlaufposition
des Probezuges u4_1 und erzeugt zwei Listen:

  1) STATION_UMLAUF_POS:  stop_id → lap_pos (m)
  2) UMLAUF_STEP_MAP:     [(step_t, lap_pos, edge, lane_pos), ...]
                          ein Eintrag pro Sim-Schritt für einen vollen
                          Umlauf (inkl. internal/junction edges).

Der Zug wird ab dem ersten Sim-Schritt nach seinem Spawn getrackt; die
Aufzeichnung endet, sobald getDistance() ≥ UMLAUF_LAENGE_M erreicht.

Output: scripts/data/umlauf_data.py
"""

import os
import sys
from pathlib import Path

if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    print("FEHLER: SUMO_HOME nicht gesetzt"); sys.exit(1)

import traci
from sumolib import checkBinary

VEH_ID = "u4_1"
UMLAUF_LAENGE_M = 15258.0
LAP_OVERSHOOT_M = 50.0  # nach Umlaufende noch ein paar Meter erfassen


def main():
    base_dir = Path(__file__).resolve().parent.parent
    sumocfg = base_dir / "config" / "osm.sumocfg"

    cmd = [
        checkBinary("sumo"),
        "-c", str(sumocfg),
        "--no-step-log", "true",
        "--no-warnings", "true",
        "--time-to-teleport", "-1",
        "--step-length", "1.0",
    ]
    traci.start(cmd)

    while VEH_ID not in traci.vehicle.getIDList():
        traci.simulationStep()
        if traci.simulation.getTime() > 2000:
            traci.close()
            print(f"FEHLER: {VEH_ID} nie gespawnt")
            sys.exit(1)

    step_map: list[tuple[float, float, str, float]] = []
    station_arrivals: list[tuple[float, str]] = []
    reached_stops: set[str] = set()

    print(f"Tracke {VEH_ID} für einen vollen Umlauf "
          f"({UMLAUF_LAENGE_M:.0f} m)...")

    while True:
        if VEH_ID not in traci.vehicle.getIDList():
            print("WARNUNG: Zug verschwunden")
            break

        t = traci.simulation.getTime()
        dist = traci.vehicle.getDistance(VEH_ID)
        edge = traci.vehicle.getRoadID(VEH_ID)
        lane_pos = traci.vehicle.getLanePosition(VEH_ID)

        step_map.append((t, dist, edge, lane_pos))

        # Erreichte Stops registrieren (nur bei Stop-Beginn)
        try:
            stops = traci.vehicle.getStops(VEH_ID, 0)
            for stop in stops:
                sid = stop.stoppingPlaceID
                if sid and stop.arrival > 0 and sid not in reached_stops:
                    reached_stops.add(sid)
                    station_arrivals.append((dist, sid))
                    print(f"  Stop {sid}: lap_pos={dist:8.2f}m  edge={edge}")
        except traci.TraCIException:
            pass

        if dist >= UMLAUF_LAENGE_M + LAP_OVERSHOOT_M:
            break

        traci.simulationStep()

    traci.close()

    # ---------- Output schreiben ----------
    out_dir = base_dir / "scripts" / "data"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "umlauf_data.py"

    with out_file.open("w") as f:
        f.write('"""\n')
        f.write("Auto-generiert von scripts/measure_umlauf.py — "
                "nicht manuell editieren!\n\n")
        f.write(f"Zug-ID:           {VEH_ID}\n")
        f.write(f"Umlauf-Länge:     {UMLAUF_LAENGE_M:.0f} m\n")
        f.write(f"Sim-Schritte:     {len(step_map)}\n")
        f.write(f"Stations-Stops:   {len(station_arrivals)}\n")
        f.write('"""\n\n')

        f.write("# Umlaufposition (m, ab Umlaufstart) je Stops-ID.\n")
        f.write("# Beide Bahnsteige pro Station: stop_hin und stop_rueck.\n")
        f.write("STATION_UMLAUF_POS: dict[str, float] = {\n")
        for lap_pos, sid in station_arrivals:
            f.write(f'    "{sid}": {lap_pos:.2f},\n')
        f.write("}\n\n")

        f.write("# Sim-Schritt-Mapping: (sim_time_s, lap_pos_m, "
                "edge_id, lane_pos_m).\n")
        f.write("# edge_id beginnt mit ':' bei junction-internal edges.\n")
        f.write("UMLAUF_STEP_MAP: list[tuple[float, float, str, float]] = [\n")
        for t, dist, edge, lane_pos in step_map:
            f.write(f'    ({t:.1f}, {dist:.2f}, "{edge}", '
                    f'{lane_pos:.2f}),\n')
        f.write("]\n")

    print(f"\nGespeichert: {out_file}")
    print(f"  Sim-Schritte:    {len(step_map)}")
    print(f"  Stations-Stops:  {len(station_arrivals)}")


if __name__ == "__main__":
    main()
