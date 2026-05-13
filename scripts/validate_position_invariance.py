"""
validate_position_invariance.py — Beweis: Störungsposition ist für ZUB+ irrelevant.

Führt das einfachste ZUB+-Szenario (2 Züge, Gap=1) an verschiedenen
Störungspositionen durch und vergleicht die Interventionszeiten.

Hypothese:
    Auf einer Rundstrecke hängt die Interventionszeit des ZUB+ nur
    vom Gap (Abstand in Zugpositionen) und der Zuganzahl ab — NICHT
    von der absoluten Position der Störung auf der Strecke.

Begründung:
    - Der ZUB+ sitzt in einem fahrenden Zug (nicht an einer festen Station)
    - Der Headway (zeitlich und räumlich) ist auf der Rundstrecke überall gleich
    - Bei Störung staut sich der ZUB+-Zug IMMER im gleichen Abstand auf
    - Die Laufdistanz vom aufgestauten Zug zum gestörten Zug ist daher
      unabhängig von der Position

Erwartung:
    Alle Positionen liefern (nahezu) identische t_intervention_total_s.
    Kleine Abweichungen durch Haltestellenstopps sind möglich.

Aufruf:
    python validate_position_invariance.py              (parallel, alle Kerne)
    python validate_position_invariance.py --gui        (GUI, eine Position)
    python validate_position_invariance.py --trains 4 --gap 2
"""

import csv
import multiprocessing as mp
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    print("FEHLER: SUMO_HOME ist nicht gesetzt!")
    sys.exit(1)

import traci
from main_zub import (
    run_zub_scenario, UMLAUFZEIT_S, DISRUPTION_LAP, DISRUPTION_VEHICLE,
    CSV_COLUMNS, SimulationConfig, generate_route_file,
)

# Positionen entlang der Strecke (in Metern ab Rundenbeginn)
# Gleiche Schrittweite wie beim Station-Agent: alle 25m, 0–16.000m
POSITIONS_MAX_M = 16_000
POSITIONS_STEP_M = 25
TEST_POSITIONS_M = list(range(0, POSITIONS_MAX_M, POSITIONS_STEP_M))

CSV_FIELDS = [
    "position_m", "t_intervention_total_s", "t_queue_s", "t_walk_s",
    "route_length_m", "disruption_edge", "zub_exit_edge",
    "runtime_s", "status",
]


# ===================================================================
# WORKER FÜR PARALLELEN MODUS
# ===================================================================

def _worker_run(args: tuple) -> dict:
    """Worker für multiprocessing.Pool."""
    pos_m, num_trains, gap, worker_id = args

    label = f"val_w{worker_id}_p{pos_m}"

    config = SimulationConfig(
        disruption_position_m=float(pos_m),
        disruption_lap=DISRUPTION_LAP,
        disruption_vehicle_id=DISRUPTION_VEHICLE,
        num_agents=1,
        num_trains=num_trains,
        step_length_s=1.0,
        use_gui=False,
    )

    # Route (vorab generiert — nur Pfad ermitteln)
    actual_route_path = config.route_path
    if num_trains > 1:
        gen_dir = config.base_dir / "routes" / "generated"
        actual_route_path = gen_dir / f"route_n{num_trains}.rou.xml"

    sumo_cmd = [
        config.sumo_binary,
        "-c", str(config.sumocfg_path),
        "--step-length", "1.0",
        "--time-to-teleport", "-1",
        "--start", "--no-warnings",
    ]
    if num_trains > 1:
        sumo_cmd += ["--route-files", str(actual_route_path)]

    start = time.time()

    try:
        traci.start(sumo_cmd, label=label, numRetries=120)
        conn = traci.getConnection(label)
    except Exception as e:
        return {
            "position_m": pos_m,
            "t_intervention_total_s": None,
            "t_queue_s": None,
            "t_walk_s": None,
            "route_length_m": None,
            "disruption_edge": None,
            "zub_exit_edge": None,
            "runtime_s": round(time.time() - start, 1),
            "status": f"FEHLER: {e}",
        }

    try:
        row = run_zub_scenario(
            num_trains=num_trains,
            gap=gap,
            use_gui=False,
            step_length_s=1.0,
            disruption_position_m=float(pos_m),
            conn=conn,
        )
        elapsed = time.time() - start

        return {
            "position_m": pos_m,
            "t_intervention_total_s": row.get("t_intervention_total_s"),
            "t_queue_s": row.get("t_queue_s"),
            "t_walk_s": row.get("t_walk_s"),
            "route_length_m": row.get("route_length_m"),
            "disruption_edge": row.get("disruption_edge"),
            "zub_exit_edge": row.get("zub_exit_edge"),
            "runtime_s": round(elapsed, 1),
            "status": "OK",
        }
    except Exception as e:
        try:
            conn.close()
        except:
            pass
        return {
            "position_m": pos_m,
            "t_intervention_total_s": None,
            "t_queue_s": None,
            "t_walk_s": None,
            "route_length_m": None,
            "disruption_edge": None,
            "zub_exit_edge": None,
            "runtime_s": round(time.time() - start, 1),
            "status": f"FEHLER: {e}",
        }


# ===================================================================
# AUSWERTUNG
# ===================================================================

def _print_statistics(results: list, total_positions: int, csv_path: Path):
    """Gibt Statistik und Bewertung aus."""
    valid_totals = [r["t_intervention_total_s"] for r in results
                    if r["t_intervention_total_s"] is not None]
    valid_queues = [r["t_queue_s"] for r in results
                    if r["t_queue_s"] is not None]
    valid_walks = [r["t_walk_s"] for r in results
                   if r["t_walk_s"] is not None]
    valid_routes = [r["route_length_m"] for r in results
                    if r["route_length_m"] is not None]

    print(f"\n\n{'=' * 70}")
    print(f"  ERGEBNISSE  ({len(valid_totals)} gueltige von {total_positions} Positionen)")
    print(f"{'=' * 70}\n")
    print(f"  CSV mit allen Einzelwerten: {csv_path}\n")

    if len(valid_totals) >= 2:
        mean_t = statistics.mean(valid_totals)
        stdev_t = statistics.stdev(valid_totals) if len(valid_totals) > 1 else 0
        min_t = min(valid_totals)
        max_t = max(valid_totals)
        spread = max_t - min_t

        mean_q = statistics.mean(valid_queues) if valid_queues else 0
        stdev_q = statistics.stdev(valid_queues) if len(valid_queues) > 1 else 0

        mean_w = statistics.mean(valid_walks) if valid_walks else 0
        stdev_w = statistics.stdev(valid_walks) if len(valid_walks) > 1 else 0

        mean_r = statistics.mean(valid_routes) if valid_routes else 0
        stdev_r = statistics.stdev(valid_routes) if len(valid_routes) > 1 else 0

        print(f"  t_intervention_total:")
        print(f"    Mittelwert:        {mean_t:.1f}s")
        print(f"    Standardabw.:      {stdev_t:.1f}s")
        print(f"    Min/Max:           {min_t:.1f}s / {max_t:.1f}s")
        print(f"    Spannweite:        {spread:.1f}s")
        print(f"    Rel. Abweichung:   {stdev_t / mean_t * 100:.2f}%")
        print(f"")
        print(f"  t_queue:")
        print(f"    Mittelwert:        {mean_q:.1f}s")
        print(f"    Standardabw.:      {stdev_q:.1f}s")
        print(f"")
        print(f"  t_walk:")
        print(f"    Mittelwert:        {mean_w:.1f}s")
        print(f"    Standardabw.:      {stdev_w:.1f}s")
        print(f"")
        print(f"  Laufdistanz:")
        print(f"    Mittelwert:        {mean_r:.1f}m")
        print(f"    Standardabw.:      {stdev_r:.1f}m")

        # Bewertung
        print(f"\n  {'─' * 70}")
        if spread < 5.0:
            print(f"  BESTAETIGT: Spannweite = {spread:.1f}s < 5s")
            print(f"    -> Stoerungsposition hat KEINEN relevanten Einfluss.")
            print(f"    -> Die feste Position (5000m) in der Simulation ist valide.")
        elif spread < 30.0:
            print(f"  BEDINGT: Spannweite = {spread:.1f}s")
            print(f"    -> Geringe Abweichungen, vermutlich durch Haltestellenstopps.")
            print(f"    -> Position hat nur marginalen Einfluss.")
        else:
            print(f"  WIDERLEGT: Spannweite = {spread:.1f}s >= 30s")
            print(f"    -> Stoerungsposition hat relevanten Einfluss!")
            print(f"    -> ZUB+-Simulation muss ueber Positionen iterieren.")
        print(f"  {'─' * 70}")

    else:
        print(f"\n  Zu wenige gueltige Ergebnisse ({len(valid_totals)}) fuer Statistik.")

    print(f"\n{'=' * 70}\n")


# ===================================================================
# HAUPTFUNKTIONEN
# ===================================================================

def run_validation(num_trains: int = 2, gap: int = 1, use_gui: bool = False):
    """
    Führt die Validierung durch — parallel mit allen CPU-Kernen.
    """
    headway_s = UMLAUFZEIT_S / num_trains
    total_positions = len(TEST_POSITIONS_M)
    num_workers = mp.cpu_count()

    print(f"\n{'=' * 70}")
    print(f"  VALIDIERUNG: Stoerungsposition ist irrelevant fuer ZUB+")
    print(f"{'=' * 70}")
    print(f"  Zuege: {num_trains} | Gap: {gap} | Headway: {headway_s:.1f}s")
    print(f"  Positionen: {total_positions} (0m – {TEST_POSITIONS_M[-1]}m, "
          f"Schritt {POSITIONS_STEP_M}m)")
    print(f"  Worker: {num_workers} CPU-Kerne")
    print(f"  GUI: {use_gui}")
    print(f"{'=' * 70}\n")

    # CSV vorbereiten
    base_dir = Path(__file__).resolve().parents[1]
    output_dir = base_dir / "output" / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"position_invariance_{timestamp}.csv"

    print(f"  CSV: {csv_path}\n")

    # Route-Datei VORAB generieren (verhindert Race Conditions)
    if num_trains > 1:
        gen_dir = base_dir / "routes" / "generated"
        template_path = base_dir / "routes" / "route_u4_long.rou.xml"
        print(f"  [ROUTE] Generiere Route fuer {num_trains} Zuege vorab...")
        generate_route_file(
            template_path=template_path,
            num_trains=num_trains,
            output_dir=gen_dir,
            umlaufzeit_s=UMLAUFZEIT_S,
        )

    if use_gui:
        # GUI-Modus: nur eine Position, sequenziell
        pos_m = TEST_POSITIONS_M[len(TEST_POSITIONS_M) // 2]  # Mitte
        print(f"  GUI-Modus: nur Position {pos_m}m")
        row = run_zub_scenario(
            num_trains=num_trains,
            gap=gap,
            use_gui=True,
            step_length_s=1.0,
            disruption_position_m=float(pos_m),
        )
        t = row.get("t_intervention_total_s")
        print(f"  -> t_total: {t}s")
        return

    # Paralleler Modus
    worker_args = [
        (pos_m, num_trains, gap, i % num_workers)
        for i, pos_m in enumerate(TEST_POSITIONS_M)
    ]

    completed = 0
    ok_count = 0
    fail_count = 0
    results = []
    start_time = time.time()

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()

        with mp.Pool(processes=num_workers) as pool:
            for row in pool.imap_unordered(_worker_run, worker_args):
                completed += 1
                elapsed = time.time() - start_time

                is_ok = row["status"] == "OK"
                if is_ok:
                    ok_count += 1
                else:
                    fail_count += 1

                results.append(row)
                writer.writerow(row)
                f.flush()

                # Fortschritt alle 25 Ergebnisse
                if completed % 25 == 0 or completed == total_positions:
                    pct = completed / total_positions * 100
                    eta = (elapsed / completed) * (total_positions - completed)
                    print(f"[{completed}/{total_positions} {pct:.0f}%] "
                          f"OK={ok_count} FAIL={fail_count} | "
                          f"{elapsed:.0f}s elapsed, ETA {eta:.0f}s")

    total_time = time.time() - start_time
    print(f"\n{'#' * 60}")
    print(f"VALIDIERUNG FERTIG! {ok_count}/{total_positions} erfolgreich")
    print(f"Dauer: {total_time:.0f}s ({total_time / 60:.1f} min)")
    print(f"{'#' * 60}")

    _print_statistics(results, total_positions, csv_path)


if __name__ == "__main__":
    num_trains = 2
    gap = 1
    use_gui = False

    # CLI-Argumente
    if "--gui" in sys.argv:
        use_gui = True
    if "--trains" in sys.argv:
        idx = sys.argv.index("--trains")
        num_trains = int(sys.argv[idx + 1])
    if "--gap" in sys.argv:
        idx = sys.argv.index("--gap")
        gap = int(sys.argv[idx + 1])

    run_validation(num_trains=num_trains, gap=gap, use_gui=use_gui)
