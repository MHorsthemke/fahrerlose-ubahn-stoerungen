"""
simulation.py — Kernfunktion run_scenario: Ein einzelner Simulationslauf.

Orchestriert:
  1. SUMO starten (GUI oder headless)
  2. km-Maps aufbauen
  3. DisruptionController + StationAgentFallback erzeugen
  4. Simulationsschleife: update(), Trace-Log
  5. Ergebnis-Dict zurückgeben
"""

import os
import sys
import time
import re
import logging
from pathlib import Path
from datetime import datetime

if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    raise RuntimeError("SUMO_HOME ist nicht gesetzt!")

import traci

from config import SimulationConfig
from stations import STATIONS
from sa_distribution import distribute_agents
from disruption import DisruptionController
from sa_routing import StationAgentFallback
from route_generator import generate_route_file
from km_map import build_edge_km_map
from tracing import (trace_log_path, write_trace_step,
                     flush_trace_log, parse_sumo_warnings)


log = logging.getLogger(__name__)


def output_log_flags(position_m: float, num_agents: int, num_trains: int) -> list[str]:
    """
    SUMO-Flags für szenariospezifische Output-Dateien.

    Jede (position, agents, trains)-Kombination bekommt einen eigenen Ordner:
        output/agent_logs/pos{P}_ag{A}_tr{T}/tripinfos.xml
                                              /stopinfos.xml
                                              /stats.xml
                                              /sumo_messages.txt
                                              /sumo_errors.txt
    So überschreiben sich parallele Instanzen nicht mehr.
    """
    base_dir = Path(__file__).resolve().parents[1]
    log_dir = (base_dir / "output" / "agent_logs"
               / f"pos{int(position_m)}_ag{num_agents}_tr{num_trains}")
    log_dir.mkdir(parents=True, exist_ok=True)
    return [
        "--tripinfo-output", str(log_dir / "tripinfos.xml"),
        "--stop-output", str(log_dir / "stopinfos.xml"),
        "--statistic-output", str(log_dir / "stats.xml"),
        "--message-log", str(log_dir / "sumo_messages.txt"),
        "--error-log", str(log_dir / "sumo_errors.txt"),
    ]


def run_scenario(config: SimulationConfig, conn=None) -> dict:
    """
    Führt einen einzelnen Simulationslauf durch.

    Args:
        config: Simulationsparameter
        conn:   TraCI-Verbindung (None = Default-Verbindung über traci)
                Im Parallel-Modus bekommt jeder Worker seine eigene.
    """
    if conn is None:
        conn = traci

    agent_indices = distribute_agents(config.num_agents)

    actual_route_path = config.route_path
    if config.num_trains > 1:
        gen_dir = config.base_dir / "routes" / "generated"
        actual_route_path = generate_route_file(
            template_path=config.route_path,
            num_trains=config.num_trains,
            output_dir=gen_dir,
        )

    sumo_cmd = [
        config.sumo_binary,
        "-c", str(config.sumocfg_path),
        "--step-length", str(config.step_length_s),
        "--time-to-teleport", "-1",
    ]
    if not config.use_gui:
        sumo_cmd += ["--start", "--no-warnings"]
    else:
        view_file = config.base_dir / "config" / "osm.view.xml"
        if view_file.exists():
            sumo_cmd += ["--gui-settings-file", str(view_file)]
    sumo_cmd += output_log_flags(config.disruption_position_m,
                                 config.num_agents, config.num_trains)
    if config.num_trains > 1:
        sumo_cmd += ["--route-files", str(actual_route_path)]

    if conn is traci:
        traci.start(sumo_cmd, numRetries=60)

    disruption = DisruptionController(config, conn=conn)
    fallback = StationAgentFallback(config, agent_indices, conn=conn)

    edge_km_map, edge_km_map_full = build_edge_km_map(
        conn, config.disruption_vehicle_id)

    if config.use_gui:
        print("[km-Map Verifikation] Edge → km_map + stop_pos vs station.km:")
        for s in STATIONS:
            edge = s.edge_hin
            if edge in edge_km_map:
                computed = edge_km_map[edge] + s.stop_pos_hin
                diff = computed - s.km
                full_km = edge_km_map_full[edge] + s.stop_pos_hin
                jct_offset = full_km - computed
                print(f"  {s.name:26s}  km={computed:7.1f}  "
                      f"station.km={s.km:7.1f}  Δ={diff:+.1f}m  "
                      f"full_km={full_km:7.1f}  jct={jct_offset:+.1f}m")

    # Station-Positionen auf Full-km-Skala (Gewinner-Station)
    station_full_km_hin: dict[int, float] = {}
    station_full_km_rueck: dict[int, float] = {}
    for i, s in enumerate(STATIONS):
        if s.edge_hin in edge_km_map_full:
            station_full_km_hin[i] = edge_km_map_full[s.edge_hin] + s.stop_pos_hin
        if s.edge_rueck in edge_km_map_full:
            station_full_km_rueck[i] = edge_km_map_full[s.edge_rueck] + s.stop_pos_rueck

    fallback.create_agents()

    log_path = trace_log_path(config)
    trace_rows = []

    validation = {
        "train_moved_after_disruption": False,
        "train_max_speed_after_disruption": 0.0,
        "min_dist_to_target": float("inf"),
        "min_dist_agent_id": None,
        "agent_on_target_edge_count": 0,
        "agents_dispatched_count": 0,
        "timeout_reached": False,
        "jammed_count": 0,
        "collision_count": 0,
        "jammed_agents": [],
        "collision_agents": [],
    }

    step = 0
    sim_time = 0.0
    wall_start = time.time()
    WALL_TIMEOUT_S = 90
    _post_arrival_remaining = 500

    try:
        while step < 20_000:
            conn.simulationStep()
            sim_time = conn.simulation.getTime()
            step += 1

            if conn.simulation.getMinExpectedNumber() <= 0:
                break

            if not config.use_gui and time.time() - wall_start > WALL_TIMEOUT_S:
                validation["timeout_reached"] = True
                break

            disruption.update(sim_time, edge_km_map, edge_km_map_full)

            if disruption.active and not fallback.activated:
                fallback.activate(
                    disruption.disruption_edge,
                    disruption.disruption_edge_pos,
                    sim_time,
                    internal_edge=disruption.disruption_internal_edge,
                )

            if fallback.activated:
                if not fallback.agent_arrived:
                    if fallback.update(sim_time):
                        disruption.resolve(sim_time)
                        _post_arrival_remaining = 500

                if fallback.agent_arrived:
                    if _post_arrival_remaining <= 0:
                        write_trace_step(trace_rows, conn, config, disruption,
                                         fallback, sim_time, step, validation)
                        break
                    _post_arrival_remaining -= 1

            if disruption.active or fallback.agent_arrived:
                write_trace_step(trace_rows, conn, config, disruption,
                                 fallback, sim_time, step, validation)

    finally:
        flush_trace_log(log_path, trace_rows)
        conn.close()

    parse_sumo_warnings(log_path.parent / "sumo_errors.txt", validation)

    min_dist = validation["min_dist_to_target"]
    if min_dist == float("inf"):
        min_dist = None

    # Full-km der Gewinner-Station (für Validierung der Laufdistanz)
    winner_station_full_km = None
    agent_id = fallback.dispatched_agent_id or ""
    _m = re.match(r'station_agent_(\d+)_(hin|rueck)', agent_id)
    if _m:
        _agent_idx = int(_m.group(1))
        _hin_or_rueck = _m.group(2)
        if _agent_idx < len(agent_indices):
            _station_idx = agent_indices[_agent_idx]
            if _hin_or_rueck == 'hin':
                winner_station_full_km = station_full_km_hin.get(_station_idx)
            else:
                winner_station_full_km = station_full_km_rueck.get(_station_idx)

    fb_results = fallback.get_results()

    return {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "disruption_position_m": config.disruption_position_m,
            "disruption_lap": config.disruption_lap,
            "num_agents": config.num_agents,
            "num_trains": config.num_trains,
            "agent_walk_speed_ms": config.agent_walk_speed_ms,
            "agent_reaction_time_s": config.agent_reaction_time_s,
        },
        "agent_stations": [STATIONS[i].name for i in agent_indices],
        "disruption": disruption.get_results(),
        "fallback": {
            **fb_results,
            "winner_station_full_km": winner_station_full_km,
        },
        "validation": {
            "train_moved_after_disruption": validation["train_moved_after_disruption"],
            "train_max_speed_after_disruption": validation["train_max_speed_after_disruption"],
            "min_dist_to_target_m": min_dist,
            "min_dist_agent_id": validation["min_dist_agent_id"],
            "agent_on_target_edge_steps": validation["agent_on_target_edge_count"],
            "agents_dispatched_count": validation["agents_dispatched_count"],
            "timeout_reached": validation["timeout_reached"],
            "jammed_count": validation["jammed_count"],
            "collision_count": validation["collision_count"],
            "jammed_agents": ",".join(validation["jammed_agents"]),
            "collision_agents": ",".join(validation["collision_agents"]),
        },
        "simulation": {
            "total_steps": step,
            "total_sim_time_s": sim_time,
            "trace_log": str(log_path),
        },
    }
