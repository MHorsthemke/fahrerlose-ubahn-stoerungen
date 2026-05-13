"""
main.py — CLI-Einstiegspunkt für die Störungssimulation U4 Frankfurt.

Konfigurationsquelle: experiment.yaml (+ CLI-Overrides).

Beispiele:
  python main.py                          # GUI-Einzellauf (laut YAML)
  python main.py --pos 4625 --agents 3    # Einzellauf mit Overrides
  python main.py parallel                 # Paralleler Batch
  python main.py batch                    # Sequentieller Batch
"""

import os
import sys
import argparse
import logging
import multiprocessing as mp
from pathlib import Path

if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    print("FEHLER: SUMO_HOME ist nicht gesetzt!")
    sys.exit(1)

from parameters import load_experiment, apply_cli_overrides
from logging_setup import setup_logging
from simulation import run_scenario
from batch import run_batch, run_parallel
from convergence import run_convergence


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Störungssimulation U4 Frankfurt",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("mode", nargs="?", default="single",
                        choices=["single", "batch", "parallel", "convergence"],
                        help="single=GUI-Einzellauf, batch=sequentiell, "
                             "parallel=alle Kerne, convergence=Raster-Konvergenzstudie")
    parser.add_argument("--config", type=str, default=None,
                        help="Pfad zur experiment.yaml (Default: scripts/experiment.yaml)")

    # Einzellauf-Overrides
    parser.add_argument("--pos", type=float, help="Störposition in Metern")
    parser.add_argument("--agents", type=int, help="Anzahl Agenten (1..10)")
    parser.add_argument("--trains", type=int, help="Anzahl Züge (1..n)")
    parser.add_argument("--lap", type=int, help="Störrunde (Einzellauf + Batch)")
    parser.add_argument("--gui", action="store_true", help="GUI erzwingen (überschreibt YAML)")
    parser.add_argument("--headless", action="store_true",
                        help="Headless erzwingen (überschreibt YAML)")

    # Batch-Overrides
    parser.add_argument("--step-m", type=int, dest="step_m",
                        help="Positions-Raster in Metern")

    # Konvergenz-Varianten
    parser.add_argument("--variant", choices=["sa", "zub", "both"], default="both",
                        help="Konvergenz-Variante: sa=Stationsagenten, zub=ZUB+, both=beide")

    return parser.parse_args()


def main() -> int:
    args = parse_cli_args()

    exp = load_experiment(args.config)
    exp = apply_cli_overrides(exp, args)

    base_dir = Path(__file__).resolve().parents[1]
    setup_logging(level=exp.logging_level,
                  console=exp.logging_console,
                  file=exp.logging_file,
                  base_dir=base_dir)

    log = logging.getLogger("main")
    log.info("=== STÖRUNGSSIMULATION U4 FRANKFURT ===")
    log.info(f"SUMO: {os.environ.get('SUMO_HOME', 'NICHT GESETZT')}")
    log.info(f"CPUs: {mp.cpu_count()}")
    log.info(f"Modus: {args.mode}")

    if args.mode == "convergence":
        variants = ["sa", "zub"] if args.variant == "both" else [args.variant]
        window = None
        try:
            from convergence import STAGES_M
            from progress_window import ConvergenceProgressWindow
            window = ConvergenceProgressWindow(STAGES_M, variants)
        except Exception as e:
            log.warning(f"Konvergenz-Fenster nicht verfügbar ({e}) — "
                        f"Fortschritt erscheint nur im Terminal.")
        try:
            for v in variants:
                log.info("")
                log.info(f"### Starte Konvergenzstudie: variant={v} ###")
                run_convergence(exp, base_dir, variant=v, window=window)
        finally:
            if window is not None:
                window.done()
        return 0

    if args.mode == "parallel":
        run_parallel(
            positions_m=exp.batch_positions(),
            step_length_s=exp.batch_step_length_s,
            agent_counts=exp.batch_agent_counts,
            train_counts=exp.batch_train_counts,
            disruption_lap=exp.batch_disruption_lap,
            num_workers=exp.batch_num_workers,
            agent_walk_speed_ms=exp.agent_walk_speed_ms,
            agent_reaction_time_s=exp.agent_reaction_time_s,
        )
        return 0

    if args.mode == "batch":
        run_batch(
            positions_m=exp.batch_positions(),
            step_length_s=exp.batch_step_length_s,
            agent_counts=exp.batch_agent_counts,
            train_counts=exp.batch_train_counts,
            disruption_lap=exp.batch_disruption_lap,
            agent_walk_speed_ms=exp.agent_walk_speed_ms,
            agent_reaction_time_s=exp.agent_reaction_time_s,
        )
        return 0

    # Einzellauf
    cfg = exp.to_simulation_config()
    log.info(f"Einzellauf: pos={cfg.disruption_position_m}m | "
             f"lap={cfg.disruption_lap} | agents={cfg.num_agents} | "
             f"trains={cfg.num_trains} | step={cfg.step_length_s}s | "
             f"gui={cfg.use_gui}")

    results = run_scenario(cfg)

    fb = results.get("fallback", {})
    t_total = fb.get("t_intervention_total_s")
    if t_total is not None:
        log.info("==========================================")
        log.info(f"PRIMÄRVERSPÄTUNG: {t_total:.1f}s ({t_total/60:.1f} min)")
        log.info(f"  Reaktionszeit:  {fb.get('t_reaction_s', 0):.1f}s")
        log.info(f"  Laufzeit:       {fb.get('t_walk_s', 0):.1f}s")
        log.info(f"  Agent von:      {fb.get('nearest_station_name')}")
        log.info("==========================================")
    else:
        log.warning("KEIN ERGEBNIS — Agent nicht angekommen.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
