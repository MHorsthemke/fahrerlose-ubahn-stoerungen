"""
main_zub.py — ZUB+-Störungssimulation.

Simuliert nur die EINZIGARTIGEN Szenarien: (num_trains, gap)-Kombinationen.
Alle anderen Szenarien sind entweder trivial (Gap=0, t=0) oder Duplikate.

Modi:
  python main_zub.py              → Einzeltest (GUI): 2 Züge, Gap=1
  python main_zub.py --batch      → Sequentieller Batch (alle Szenarien)
  python main_zub.py --parallel   → Paralleler Batch (alle CPU-Kerne)
  python main_zub.py --gui N G    → GUI-Test: N Züge, Gap G

Ergebnisse:  output/zub_results/zub_<timestamp>.csv
"""

import os
import sys
import csv
import time
import multiprocessing as mp
from pathlib import Path
from datetime import datetime

# Plattformunabhängig: /dev/null (Unix) oder nul (Windows)
DEVNULL = os.devnull

# --- SUMO-Pfad einrichten ---
if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    print("FEHLER: SUMO_HOME ist nicht gesetzt!")
    sys.exit(1)

import traci

from config import SimulationConfig
from logging_setup import setup_logging
from disruption import DisruptionController
from zub_routing import ZubFallback
from route_generator import generate_route_file
from zub_distribution import select_zub_vehicle_id, build_scenarios as _build_scenarios


# ===================================================================
# PARAMETER
# ===================================================================

DISRUPTION_LAP = 5               # In welchem Umlauf die Störung ausgelöst wird
DISRUPTION_POSITION_M = 5000.0   # Feste Position (Rundstrecke → Position egal)
DISRUPTION_VEHICLE = "u4_1"      # Immer der erste Zug

# Umlaufzeit aus den Tests (SUMO 1.26.0, Mac + Windows identisch)
UMLAUFZEIT_S = 1561.6


# ===================================================================
# SUMO OUTPUT: Per-Szenario-Logs
# ===================================================================

def _output_log_flags(num_trains: int, gap: int,
                      position_m: float | None = None) -> list[str]:
    """
    Gibt SUMO-Flags zurück, die alle Ausgabedateien in ein
    szenariospezifisches Verzeichnis umleiten.

    Ohne position_m: output/zub_logs/n{N}_g{G}/...
    Mit position_m:  output/zub_logs/n{N}_g{G}_p{POS}/...

    So überschreiben sich parallele Instanzen nicht mehr — auch beim
    Positions-Batch (Konvergenzstudie), wo dieselbe (N,G)-Kombination
    an mehreren Positionen läuft.
    """
    base_dir = Path(__file__).resolve().parents[1]
    subdir = f"n{num_trains}_g{gap}"
    if position_m is not None:
        subdir = f"{subdir}_p{int(position_m)}"
    log_dir = base_dir / "output" / "zub_logs" / subdir
    log_dir.mkdir(parents=True, exist_ok=True)
    return [
        "--tripinfo-output", str(log_dir / "tripinfos.xml"),
        "--stop-output", str(log_dir / "stopinfos.xml"),
        "--statistic-output", str(log_dir / "stats.xml"),
        "--message-log", str(log_dir / "sumo_messages.txt"),
        "--error-log", str(log_dir / "sumo_errors.txt"),
    ]


# ===================================================================
# CSV
# ===================================================================

CSV_COLUMNS = [
    "num_trains", "gap", "path", "headway_s",
    "zub_vehicle_id", "disruption_vehicle_id",
    "disruption_position_m", "disruption_lap",
    "disruption_time_s", "disruption_edge", "disruption_edge_pos",
    "zub_exit_edge", "zub_exit_pos",
    "route_cost_s", "route_length_m",
    "t_queue_s", "t_walk_s", "t_intervention_total_s",
    "total_steps", "total_sim_time_s", "timestamp",
]


# ===================================================================
# EINZEL-SZENARIO
# ===================================================================

def run_zub_scenario(num_trains: int, gap: int,
                     use_gui: bool = False,
                     step_length_s: float = 1.0,
                     conn=None,
                     disruption_position_m: float = None) -> dict:
    """
    Führt ein einzelnes ZUB+-Szenario durch.

    Args:
        num_trains:            Anzahl Züge auf der Strecke
        gap:                   Abstand (in Zugpositionen) vom gestörten Zug zum ZUB+
        use_gui:               True = sumo-gui
        step_length_s:         SUMO-Zeitschritt
        conn:                  TraCI-Verbindung (None = Default)
        disruption_position_m: Störungsposition in Metern (None = DISRUPTION_POSITION_M)

    Returns:
        Ergebnis-Dict (flach, für CSV)
    """
    if disruption_position_m is None:
        disruption_position_m = DISRUPTION_POSITION_M

    if conn is None:
        conn = traci

    # ZUB+-Zug bestimmen — Logik in zub_distribution.py.
    zub_vehicle_id = select_zub_vehicle_id(gap, DISRUPTION_VEHICLE)

    # Config für SUMO-Start
    config = SimulationConfig(
        disruption_position_m=disruption_position_m,
        disruption_lap=DISRUPTION_LAP,
        disruption_vehicle_id=DISRUPTION_VEHICLE,
        num_agents=1,        # Wird nicht verwendet, aber Config braucht es
        num_trains=num_trains,
        step_length_s=step_length_s,
        use_gui=use_gui,
    )

    # Route generieren — aber NICHT im Worker-Modus (conn != traci), sonst
    # Race Condition, wenn mehrere Worker dieselbe Datei gleichzeitig schreiben.
    # Im Worker-Modus verlassen wir uns auf die VORAB-Generierung in
    # run_parallel() (siehe dort: "Route-Dateien VORAB generieren").
    actual_route_path = config.route_path
    if num_trains > 1:
        gen_dir = config.base_dir / "routes" / "generated"
        if conn is traci:
            actual_route_path = generate_route_file(
                template_path=config.route_path,
                num_trains=num_trains,
                output_dir=gen_dir,
                umlaufzeit_s=UMLAUFZEIT_S,
            )
        else:
            actual_route_path = gen_dir / f"route_n{num_trains}.rou.xml"

    # SUMO starten (nur wenn keine externe Verbindung)
    if conn is traci:
        sumo_cmd = [
            config.sumo_binary,
            "-c", str(config.sumocfg_path),
            "--step-length", str(step_length_s),
            "--time-to-teleport", "-1",
        ]
        if not use_gui:
            sumo_cmd += ["--start", "--no-warnings"]
        else:
            # GUI: view-file mit Person-Exaggeration laden, sonst ist der
            # ZUB+ im 15 km-Netz als Ein-Pixel-Punkt unsichtbar.
            view_file = config.base_dir / "config" / "zub_gui.view.xml"
            if view_file.exists():
                sumo_cmd += ["--gui-settings-file", str(view_file)]
        sumo_cmd += _output_log_flags(num_trains, gap)
        if num_trains > 1:
            sumo_cmd += ["--route-files", str(actual_route_path)]

        traci.start(sumo_cmd, numRetries=60)

    # Controller (conn weiterreichen, damit Parallel-Worker die richtige
    # TraCI-Verbindung nutzen und die Streckensperrung greift)
    disruption = DisruptionController(config, conn=conn)
    fallback = ZubFallback(config, zub_vehicle_id, gap, num_trains=num_trains)

    # ZUB+-Person erstellen: steigt bei BW in den Zug ein
    fallback.create_zub_person(conn)

    # Simulationsschleife
    step = 0
    sim_time = 0.0

    try:
        while step < 500_000:
            conn.simulationStep()
            sim_time = conn.simulation.getTime()
            step += 1

            if conn.simulation.getMinExpectedNumber() <= 0:
                break

            # --- Störung prüfen + Streckensperrung durchsetzen ---
            disruption.update(sim_time)

            # --- Störung aktivieren → Fallback starten ---
            if disruption.active and not fallback.activated:
                fallback.activate(
                    disruption.disruption_edge,
                    disruption.disruption_edge_pos,
                    sim_time,
                    internal_edge=disruption.disruption_internal_edge,
                    closure_stop_ids=(disruption.prev_stop_id,
                                      disruption.opp_stop_id),
                )
                # Zug wird bereits in disruption.update gestoppt

            # --- Fallback-Update ---
            if fallback.activated:
                if fallback.update(conn, sim_time):
                    break
                # Timeout: 3600s Sim-Zeit nach Aktivierung ohne Ankunft
                # → Szenario abbrechen, damit Worker nicht stundenlang hängt.
                # Reguläre Ankünfte liegen bei < 1000s; 3600s fängt nur
                # echte Hänger (z.B. blockierte Pfad-A-Routen).
                if sim_time - fallback.activation_time > 3600.0:
                    print(f"[TIMEOUT] Szenario abgebrochen "
                          f"(t_intervention > 3600s ohne Ankunft) | "
                          f"sim_time={sim_time:.0f}s")
                    break
    finally:
        conn.close()

    # Ergebnisse
    fb = fallback.get_results()
    headway_s = UMLAUFZEIT_S / num_trains

    return {
        "num_trains": num_trains,
        "gap": gap,
        "path": fb.get("path"),
        "headway_s": round(headway_s, 1),
        "zub_vehicle_id": zub_vehicle_id,
        "disruption_vehicle_id": DISRUPTION_VEHICLE,
        "disruption_position_m": disruption_position_m,
        "disruption_lap": DISRUPTION_LAP,
        "disruption_time_s": disruption.disruption_time,
        "disruption_edge": disruption.disruption_edge,
        "disruption_edge_pos": disruption.disruption_edge_pos,
        "zub_exit_edge": fb.get("zub_exit_edge"),
        "zub_exit_pos": fb.get("zub_exit_pos"),
        "route_cost_s": fb.get("route_cost_s"),
        "route_length_m": fb.get("route_length_m"),
        "t_queue_s": fb.get("t_queue_s"),
        "t_walk_s": fb.get("t_walk_s"),
        "t_intervention_total_s": fb.get("t_intervention_total_s"),
        "total_steps": step,
        "total_sim_time_s": sim_time,
        "timestamp": datetime.now().isoformat(),
    }


# ===================================================================
# SZENARIEN GENERIEREN (nur einzigartige!)
# ===================================================================

def build_scenarios(max_trains: int,
                    positions_m: list[int] | None = None) -> list[dict]:
    """
    Wrapper um zub_distribution.build_scenarios mit Konsolen-Statistik.

    Die reine Kombinatorik liegt in zub_distribution.py — hier nur die
    Print-Ausgabe für den Batch-Lauf.
    """
    scenarios = _build_scenarios(max_trains, positions_m=positions_m)
    total = len(scenarios)
    if positions_m is None:
        print(f"Einzigartige Szenarien: {total} "
              f"(+ {max_trains} triviale Gap=0-Fälle)")
        print(f"  (Zuganzahl 2..{max_trains}, pro Zuganzahl n: Gaps 1..n-1)")
    else:
        print(f"Einzigartige Szenarien: {total} "
              f"(+ {max_trains * len(positions_m)} triviale Gap=0-Fälle)")
        print(f"  (Zuganzahl 2..{max_trains}, Gaps 1..n-1, "
              f"{len(positions_m)} Positionen)")
    return scenarios


def _trivial_rows(max_trains: int,
                  positions_m: list[int] | None = None) -> list[dict]:
    """
    Erzeugt triviale CSV-Zeilen für Gap=0 (ZUB+ auf dem gestörten Zug).

    Bei Gap=0 ist der ZUB+ direkt am Ort der Störung → Interventionszeit = 0.
    Ohne positions_m: eine Zeile pro Zuganzahl (Position=DISRUPTION_POSITION_M).
    Mit positions_m: eine Zeile pro (Zuganzahl, Position) — konsistent mit dem
    Positions-Batch, damit die Konvergenzauswertung alle Zellen findet.
    """
    positions = ([float(p) for p in positions_m] if positions_m
                 else [DISRUPTION_POSITION_M])
    rows = []
    for n in range(1, max_trains + 1):
        headway_s = UMLAUFZEIT_S / n
        for pos in positions:
            rows.append({
                "num_trains": n,
                "gap": 0,
                "path": "A",
                "headway_s": round(headway_s, 1),
                "zub_vehicle_id": DISRUPTION_VEHICLE,  # ZUB+ = gestörter Zug
                "disruption_vehicle_id": DISRUPTION_VEHICLE,
                "disruption_position_m": pos,
                "disruption_lap": DISRUPTION_LAP,
                "disruption_time_s": None,
                "disruption_edge": None,
                "disruption_edge_pos": None,
                "zub_exit_edge": None,
                "zub_exit_pos": None,
                "route_cost_s": 0.0,
                "route_length_m": 0.0,
                "t_queue_s": 0.0,
                "t_walk_s": 0.0,
                "t_intervention_total_s": 0.0,
                "total_steps": 0,
                "total_sim_time_s": 0.0,
                "timestamp": datetime.now().isoformat(),
            })
    return rows


# ===================================================================
# SEQUENTIELLER BATCH
# ===================================================================

def run_batch(max_trains: int, step_length_s: float = 1.0):
    """Sequentieller Batch über alle einzigartigen Szenarien."""
    scenarios = build_scenarios(max_trains)
    total = len(scenarios)

    base_dir = Path(__file__).resolve().parents[1]
    output_dir = base_dir / "output" / "zub_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"zub_{timestamp}.csv"

    trivials = _trivial_rows(max_trains)

    print(f"\n{'#'*60}")
    print(f"ZUB+-BATCH (sequentiell): {total} Szenarien + {len(trivials)} triviale")
    print(f"Züge: 1..{max_trains} | Störung: Lap {DISRUPTION_LAP}, {DISRUPTION_POSITION_M}m")
    print(f"Step-Length: {step_length_s}s")
    print(f"CSV: {csv_path}")
    print(f"{'#'*60}\n")

    completed = 0
    failed = 0

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()

        # Triviale Fälle (Gap=0): ZUB+ auf gestörtem Zug → t=0
        for row in trivials:
            writer.writerow(row)
        f.flush()
        print(f"[TRIVIAL] {len(trivials)} Gap=0-Fälle geschrieben (t=0)")

        for sc in scenarios:
            completed += 1
            n = sc["num_trains"]
            g = sc["gap"]
            print(f"\n[{completed}/{total}] {n} Züge, Gap={g}")

            try:
                row = run_zub_scenario(n, g, use_gui=False,
                                       step_length_s=step_length_s)
                writer.writerow(row)
                f.flush()

                t = row.get("t_intervention_total_s")
                if t is not None:
                    print(f"  → t_intervention: {t:.1f}s ({t/60:.1f} min)")
                else:
                    print(f"  → KEIN ERGEBNIS")
            except Exception as e:
                failed += 1
                print(f"  → FEHLER: {e}")
                error_row = {col: None for col in CSV_COLUMNS}
                error_row["num_trains"] = n
                error_row["gap"] = g
                error_row["timestamp"] = f"FEHLER: {e}"
                writer.writerow(error_row)
                f.flush()

    print(f"\n{'#'*60}")
    print(f"BATCH FERTIG! {total - failed}/{total} erfolgreich")
    print(f"CSV: {csv_path}")
    print(f"{'#'*60}")


# ===================================================================
# PARALLELER BATCH
# ===================================================================

def _worker_run(args: tuple) -> dict:
    """Worker für multiprocessing.Pool."""
    scenario, worker_id = args

    # Worker läuft bei spawn-Start-Mode (macOS) in frischem Interpreter
    # → Logger-Handler aus main.py werden nicht vererbt. Setup pro Worker,
    # damit log.warning(...) aus fallback_*-Modulen in run.log landet.
    base_dir = Path(__file__).resolve().parents[1]
    setup_logging(level="INFO", console=False,
                  file="output/log/run.log", base_dir=base_dir)

    n = scenario["num_trains"]
    g = scenario["gap"]
    pos_m = scenario.get("position_m", DISRUPTION_POSITION_M)
    has_pos = "position_m" in scenario

    label = f"zub_w{worker_id}_n{n}_g{g}"
    if has_pos:
        label = f"{label}_p{int(pos_m)}"

    config = SimulationConfig(
        disruption_position_m=float(pos_m),
        disruption_lap=DISRUPTION_LAP,
        disruption_vehicle_id=DISRUPTION_VEHICLE,
        num_agents=1,
        num_trains=n,
        step_length_s=1.0,
        use_gui=False,
    )

    # Route (vorab generiert — nur Pfad ermitteln, nicht neu schreiben)
    actual_route_path = config.route_path
    if n > 1:
        gen_dir = config.base_dir / "routes" / "generated"
        actual_route_path = gen_dir / f"route_n{n}.rou.xml"

    sumo_cmd = [
        config.sumo_binary,
        "-c", str(config.sumocfg_path),
        "--step-length", "1.0",
        "--time-to-teleport", "-1",
        "--start", "--no-warnings",
    ] + _output_log_flags(n, g, pos_m if has_pos else None)
    if n > 1:
        sumo_cmd += ["--route-files", str(actual_route_path)]

    try:
        traci.start(sumo_cmd, label=label, numRetries=120)
        conn = traci.getConnection(label)
    except Exception as e:
        row = {col: None for col in CSV_COLUMNS}
        row["num_trains"] = n
        row["gap"] = g
        row["disruption_position_m"] = pos_m
        row["timestamp"] = f"FEHLER: {e}"
        return row

    try:
        return run_zub_scenario(n, g, use_gui=False, step_length_s=1.0,
                                conn=conn, disruption_position_m=float(pos_m))
    except Exception as e:
        try:
            conn.close()
        except:
            pass
        row = {col: None for col in CSV_COLUMNS}
        row["num_trains"] = n
        row["gap"] = g
        row["disruption_position_m"] = pos_m
        row["timestamp"] = f"FEHLER: {e}"
        return row


def run_parallel(max_trains: int,
                 positions_m: list[int] | None = None,
                 csv_path: Path | None = None,
                 progress_callback=None):
    """
    Paralleler Batch mit allen CPU-Kernen.

    Ohne positions_m: wie bisher (feste Position 5000 m, nur (n, gap) variiert).
    Mit positions_m:  Kreuzprodukt (n, gap, Position) — für die
                      Positions-Konvergenzstudie.
    """
    scenarios = build_scenarios(max_trains, positions_m)
    total = len(scenarios)
    num_workers = mp.cpu_count()

    worker_args = [(s, i % num_workers) for i, s in enumerate(scenarios)]
    trivials = _trivial_rows(max_trains, positions_m)

    base_dir = Path(__file__).resolve().parents[1]
    if csv_path is None:
        output_dir = base_dir / "output" / "zub_results"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = output_dir / f"zub_parallel_{timestamp}.csv"
    else:
        csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Route-Dateien VORAB generieren (verhindert Race Conditions)
    gen_dir = base_dir / "routes" / "generated"
    template_path = base_dir / "routes" / "route_u4_long.rou.xml"
    print(f"[ROUTE] Generiere Route-Dateien für 2..{max_trains} Züge vorab...")
    for n in range(2, max_trains + 1):
        generate_route_file(
            template_path=template_path,
            num_trains=n,
            output_dir=gen_dir,
            umlaufzeit_s=UMLAUFZEIT_S,
        )
    print(f"[ROUTE] {max_trains - 1} Route-Dateien fertig.\n")

    pos_label = (f"{len(positions_m)} Positionen" if positions_m
                 else f"feste Position {DISRUPTION_POSITION_M}m")
    print(f"\n{'#'*60}")
    print(f"ZUB+-PARALLEL-BATCH: {total} Szenarien + {len(trivials)} triviale"
          f" auf {num_workers} Workern")
    print(f"Züge: 1..{max_trains} | Störung: Lap {DISRUPTION_LAP}, {pos_label}")
    print(f"CSV: {csv_path}")
    print(f"{'#'*60}\n")

    completed = 0
    failed = 0
    start_time = time.time()

    if progress_callback is not None:
        try:
            progress_callback(0, total, 0, 0, 0, [])
        except Exception:
            pass

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()

        # Triviale Fälle (Gap=0): ZUB+ auf gestörtem Zug → t=0
        for row in trivials:
            writer.writerow(row)
        f.flush()
        print(f"[TRIVIAL] {len(trivials)} Gap=0-Fälle geschrieben (t=0)")

        with mp.Pool(processes=num_workers) as pool:
            for row in pool.imap_unordered(_worker_run, worker_args):
                completed += 1
                elapsed = time.time() - start_time

                is_error = "FEHLER" in str(row.get("timestamp", ""))
                if is_error:
                    failed += 1

                writer.writerow(row)
                f.flush()

                # Fortschritt
                pct = completed / total * 100
                eta = (elapsed / completed) * (total - completed) if completed > 0 else 0
                n = row.get("num_trains", "?")
                g = row.get("gap", "?")
                t = row.get("t_intervention_total_s")
                t_str = f"{t:.1f}s" if t else "FEHLER"

                print(f"[{completed}/{total} {pct:.0f}%] "
                      f"n={n} gap={g} → {t_str} "
                      f"| {elapsed:.0f}s elapsed, ETA {eta:.0f}s")

                if progress_callback is not None:
                    try:
                        progress_callback(completed, total,
                                          completed - failed, failed, 0, [])
                    except Exception:
                        pass

    total_time = time.time() - start_time
    print(f"\n{'#'*60}")
    print(f"PARALLEL-BATCH FERTIG! {total - failed}/{total} erfolgreich")
    print(f"Dauer: {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"CSV: {csv_path}")
    print(f"{'#'*60}")


# ===================================================================
# CLI
# ===================================================================

if __name__ == "__main__":
    # Max Zuganzahl aus Umlaufzeit-Test
    MAX_TRAINS_DEFAULT = 28

    if "--parallel" in sys.argv:
        max_t = MAX_TRAINS_DEFAULT
        if "--max" in sys.argv:
            idx = sys.argv.index("--max")
            max_t = int(sys.argv[idx + 1])
        run_parallel(max_t)

    elif "--batch" in sys.argv:
        max_t = MAX_TRAINS_DEFAULT
        if "--max" in sys.argv:
            idx = sys.argv.index("--max")
            max_t = int(sys.argv[idx + 1])
        run_batch(max_t, step_length_s=1.0)

    elif "--gui" in sys.argv:
        idx = sys.argv.index("--gui")
        n_trains = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 2
        gap = int(sys.argv[idx + 2]) if idx + 2 < len(sys.argv) else 1
        pos_m = (float(sys.argv[idx + 3])
                 if idx + 3 < len(sys.argv)
                 and sys.argv[idx + 3].replace(".", "", 1).isdigit()
                 else None)
        print(f"GUI-Test: {n_trains} Züge, Gap={gap}, "
              f"Pos={pos_m if pos_m is not None else DISRUPTION_POSITION_M}m")
        result = run_zub_scenario(n_trains, gap, use_gui=True, step_length_s=1.0,
                                  disruption_position_m=pos_m)
        print(f"\nErgebnis:")
        for k, v in result.items():
            print(f"  {k}: {v}")

    else:
        # Default: Einzeltest ohne GUI
        print("ZUB+-Einzeltest: 3 Züge, Gap=1")
        result = run_zub_scenario(3, 1, use_gui=False, step_length_s=1.0)
        print(f"\nErgebnis:")
        for k, v in result.items():
            print(f"  {k}: {v}")
