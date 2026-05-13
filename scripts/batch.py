"""
batch.py — Sequentielle und parallele Batch-Runs.

Batch-Parameter (Positionen, Agenten-Zahlen, Zug-Zahlen) werden aus der
zentralen experiment.yaml gelesen; siehe parameters.py / ExperimentConfig.
"""

import csv
import multiprocessing as mp
import time
import logging
from pathlib import Path
from datetime import datetime
from itertools import product as iterproduct

import traci

from config import SimulationConfig
from logging_setup import setup_logging
from route_generator import generate_route_file
from simulation import run_scenario, output_log_flags
from csv_writer import CSV_COLUMNS, results_to_row

try:
    from progress_window import ProgressWindow
except Exception:
    ProgressWindow = None  # Fallback: Terminal-Output


log = logging.getLogger(__name__)


def run_batch(positions_m: list[int], step_length_s: float,
              agent_counts: list[int], train_counts: list[int],
              disruption_lap: int,
              agent_walk_speed_ms: float = 3.33,
              agent_reaction_time_s: float = 90.0):
    """Sequentieller Batch: ein Szenario nach dem anderen."""
    base_dir = Path(__file__).resolve().parents[1]
    output_dir = base_dir / "output" / "batch_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"batch_{timestamp}.csv"

    total = len(positions_m) * len(agent_counts) * len(train_counts)
    current = 0
    failed = 0

    step_m = positions_m[1] - positions_m[0] if len(positions_m) > 1 else 0
    log.info(f"BATCH (sequentiell): {total} Szenarien, "
             f"Positionen {positions_m[0]}-{positions_m[-1]}m (Schritt {step_m}m), "
             f"Agenten {agent_counts}, Züge {train_counts}, Runde {disruption_lap}")
    log.info(f"CSV: {csv_path}")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()

        for num_trains in train_counts:
            for num_agents in agent_counts:
                for position_m in positions_m:
                    current += 1
                    log.info(f"[{current}/{total}] Position={position_m}m | "
                             f"Agenten={num_agents} | Züge={num_trains}")

                    config = SimulationConfig(
                        disruption_position_m=float(position_m),
                        disruption_lap=disruption_lap,
                        num_agents=num_agents,
                        num_trains=num_trains,
                        step_length_s=step_length_s,
                        use_gui=False,
                        agent_walk_speed_ms=agent_walk_speed_ms,
                        agent_reaction_time_s=agent_reaction_time_s,
                    )

                    try:
                        results = run_scenario(config)
                        row = results_to_row(results)
                        writer.writerow(row)
                        f.flush()

                        t = row.get("t_intervention_total_s")
                        if t is not None:
                            log.info(f"  → Primärverspätung: {t:.1f}s ({t/60:.1f} min)")
                        else:
                            log.warning(f"  → KEIN ERGEBNIS (Agent nicht angekommen)")

                    except Exception as e:
                        failed += 1
                        log.error(f"  → FEHLER: {e}")
                        error_row = {col: None for col in CSV_COLUMNS}
                        error_row["disruption_position_m"] = position_m
                        error_row["num_agents"] = num_agents
                        error_row["num_trains"] = num_trains
                        error_row["timestamp"] = f"FEHLER: {e}"
                        writer.writerow(error_row)
                        f.flush()

    log.info(f"BATCH FERTIG: {total - failed}/{total} erfolgreich — CSV: {csv_path}")
    return csv_path


def _worker_run(args: tuple) -> dict:
    """Worker für multiprocessing.Pool mit eigenem TraCI-Label."""
    scenario, worker_id = args

    # Worker läuft bei spawn-Start-Mode (macOS) in frischem Interpreter
    # → Logger-Handler aus main.py werden nicht vererbt. Setup pro Worker,
    # damit log.warning(...) aus fallback_station_agent etc. in run.log landet.
    base_dir = Path(__file__).resolve().parents[1]
    setup_logging(level="INFO", console=False,
                  file="output/log/run.log", base_dir=base_dir)

    config = SimulationConfig(
        disruption_position_m=float(scenario["position_m"]),
        disruption_lap=scenario["disruption_lap"],
        num_agents=scenario["num_agents"],
        num_trains=scenario["num_trains"],
        step_length_s=scenario["step_length_s"],
        use_gui=False,
        agent_walk_speed_ms=scenario["agent_walk_speed_ms"],
        agent_reaction_time_s=scenario["agent_reaction_time_s"],
    )

    label = f"w{worker_id}_{scenario['position_m']}_{scenario['num_agents']}"

    sumo_cmd = [
        config.sumo_binary,
        "-c", str(config.sumocfg_path),
        "--step-length", str(config.step_length_s),
        "--time-to-teleport", "-1",
        "--start", "--no-warnings",
    ] + output_log_flags(float(scenario["position_m"]),
                          scenario["num_agents"], scenario["num_trains"])
    if config.num_trains > 1:
        gen_dir = config.base_dir / "routes" / "generated"
        route_path = generate_route_file(
            template_path=config.route_path,
            num_trains=config.num_trains,
            output_dir=gen_dir,
        )
        sumo_cmd += ["--route-files", str(route_path)]

    try:
        traci.start(sumo_cmd, label=label, numRetries=120)
        conn = traci.getConnection(label)
    except Exception as e:
        row = {col: None for col in CSV_COLUMNS}
        row["disruption_position_m"] = scenario["position_m"]
        row["num_agents"] = scenario["num_agents"]
        row["num_trains"] = scenario["num_trains"]
        row["timestamp"] = f"FEHLER: {e}"
        return row

    try:
        results = run_scenario(config, conn=conn)
        return results_to_row(results)
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        row = {col: None for col in CSV_COLUMNS}
        row["disruption_position_m"] = scenario["position_m"]
        row["num_agents"] = scenario["num_agents"]
        row["num_trains"] = scenario["num_trains"]
        row["timestamp"] = f"FEHLER: {e}"
        return row


def run_parallel(positions_m: list[int], step_length_s: float,
                 agent_counts: list[int], train_counts: list[int],
                 disruption_lap: int, num_workers: int | None = None,
                 agent_walk_speed_ms: float = 3.33,
                 agent_reaction_time_s: float = 90.0,
                 csv_path: Path | None = None,
                 use_gui: bool = True,
                 progress_callback=None):
    """Paralleler Batch: alle CPU-Kerne."""
    if num_workers is None:
        num_workers = mp.cpu_count()

    scenarios = []
    for num_trains, num_agents, pos in iterproduct(
            train_counts, agent_counts, positions_m):
        scenarios.append({
            "position_m": pos,
            "num_agents": num_agents,
            "num_trains": num_trains,
            "disruption_lap": disruption_lap,
            "step_length_s": step_length_s,
            "agent_walk_speed_ms": agent_walk_speed_ms,
            "agent_reaction_time_s": agent_reaction_time_s,
        })

    total = len(scenarios)
    worker_args = [(s, i % num_workers) for i, s in enumerate(scenarios)]

    if csv_path is None:
        base_dir = Path(__file__).resolve().parents[1]
        output_dir = base_dir / "output" / "batch_results"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = output_dir / f"parallel_{timestamp}.csv"
    else:
        csv_path.parent.mkdir(parents=True, exist_ok=True)

    step_m = positions_m[1] - positions_m[0] if len(positions_m) > 1 else 0
    log.info(f"PARALLEL-BATCH: {total} Szenarien auf {num_workers} Workern")
    log.info(f"Positionen {positions_m[0]}-{positions_m[-1]}m (Schritt {step_m}m), "
             f"Agenten {agent_counts}, Züge {train_counts}, Runde {disruption_lap}")
    log.info(f"CSV: {csv_path}")

    ok = 0
    failed = 0
    anomaly = 0
    t_values: list[float] = []
    start_time = time.time()
    done = 0

    win = None
    if progress_callback is None and use_gui and ProgressWindow is not None:
        try:
            win = ProgressWindow(total)
        except Exception as e:
            log.warning(f"GUI-Fenster nicht verfügbar ({e}) — "
                        f"Fortschritt erscheint im Terminal.")
            win = None

    if progress_callback is not None:
        try:
            progress_callback(0, total, 0, 0, 0, [])
        except Exception:
            pass

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()

        with mp.Pool(processes=num_workers) as pool:
            for row in pool.imap_unordered(_worker_run, worker_args):
                done += 1
                is_error = "FEHLER" in str(row.get("timestamp", ""))
                t = row.get("t_intervention_total_s")
                pos = row.get("disruption_position_m")
                ag = row.get("num_agents")

                if is_error:
                    failed += 1
                    anomaly += 1
                    log.warning(f"  ⚠ FEHLER      pos={pos} ag={ag}")
                else:
                    ok += 1
                    if _is_anomaly(row):
                        anomaly += 1
                        reason = _anomaly_reason(row)
                        log.warning(f"  ⚠ {reason:10s} pos={pos} ag={ag}")
                    if t is not None:
                        t_values.append(float(t))

                if progress_callback is not None:
                    try:
                        progress_callback(done, total, ok, failed, anomaly, t_values)
                    except Exception:
                        pass
                elif win is not None:
                    win.update(done, ok, failed, anomaly, t_values)
                elif done % max(1, total // 20) == 0 or done == total:
                    pct = 100 * done / total
                    log.info(f"[{done}/{total}  {pct:.0f}%] "
                             f"OK={ok} FAIL={failed} AUFF={anomaly}")

                writer.writerow(row)
                f.flush()

    total_time = time.time() - start_time
    _log_summary(log, ok, failed, anomaly, t_values, total, total_time, csv_path)

    if win is not None:
        win.finish(_summary_text(ok, failed, anomaly, t_values, total, total_time))
    return csv_path


def _summary_text(ok: int, failed: int, anomaly: int, t_values: list[float],
                  total: int, total_time: float) -> str:
    """Mehrzeiliger Summary-Block für das Fenster nach Abschluss."""
    lines = [f"FERTIG: {ok}/{total} OK  |  {failed} FEHLER  |  {anomaly} auffällig",
             f"Zeit gesamt: {total_time/60:.1f} min"]
    if t_values:
        import statistics
        vals = sorted(t_values)
        t_min = vals[0] / 60
        t_max = vals[-1] / 60
        t_med = statistics.median(vals) / 60
        t_mean = statistics.mean(vals) / 60
        over_30 = sum(1 for v in vals if v > 1800)
        lines.append(f"t_I [min]: min={t_min:.1f}  med={t_med:.1f}  "
                     f"mean={t_mean:.1f}  max={t_max:.1f}")
        lines.append(f"{over_30}/{len(vals)} Szenarien > 30 min "
                     f"({100*over_30/len(vals):.1f} %)")
    return "\n".join(lines)


def _log_summary(log_: logging.Logger, ok: int, failed: int, anomaly: int,
                 t_values: list[float], total: int, total_time: float,
                 csv_path: Path) -> None:
    """Strukturierte End-Zusammenfassung mit Verteilungskennwerten."""
    log_.info("=" * 70)
    log_.info(f"FERTIG: {ok}/{total} OK | {failed} FEHLER | "
              f"{anomaly} auffällig | Zeit {total_time/60:.1f} min")
    if t_values:
        import statistics
        vals = sorted(t_values)
        t_min = vals[0]
        t_max = vals[-1]
        t_med = statistics.median(vals)
        t_mean = statistics.mean(vals)
        t_std = statistics.stdev(vals) if len(vals) > 1 else 0.0
        over_30 = sum(1 for v in vals if v > 1800)
        log_.info(f"t_I [min]:  min={t_min/60:.1f}  med={t_med/60:.1f}  "
                  f"mean={t_mean/60:.1f}  max={t_max/60:.1f}  "
                  f"std={t_std/60:.1f}")
        log_.info(f"{over_30}/{len(vals)} Szenarien mit t_I > 30 min "
                  f"({100*over_30/len(vals):.1f}%)")
    log_.info(f"CSV: {csv_path}")
    log_.info("=" * 70)


def _is_anomaly(row: dict) -> bool:
    """
    Auffällige Simulationen: Verdacht, dass das Ergebnis nicht verwertbar ist.

    Kriterien:
      - kein Ergebnis (t_intervention_total_s fehlt)
      - Wallclock-Timeout (Simulation abgebrochen, bevor Agent ankam)
      - Collision / jammed count > 0 (Fußgänger-Blockade)
    """
    if row.get("t_intervention_total_s") is None:
        return True
    if row.get("v_timeout"):
        return True
    if (row.get("v_jammed_count") or 0) > 0:
        return True
    if (row.get("v_collision_count") or 0) > 0:
        return True
    return False


def _anomaly_reason(row: dict) -> str:
    """Kurzer Grund-Marker für die auffällige Zeile."""
    if row.get("t_intervention_total_s") is None:
        return "KEIN ERG."
    if row.get("v_timeout"):
        return "TIMEOUT"
    if (row.get("v_jammed_count") or 0) > 0:
        return "JAMMED"
    if (row.get("v_collision_count") or 0) > 0:
        return "COLLISION"
    return "?"
