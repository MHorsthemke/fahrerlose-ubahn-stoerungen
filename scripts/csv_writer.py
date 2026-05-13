"""
csv_writer.py — Flache CSV-Zeile pro Szenario-Ergebnis.

Das Ergebnis-Dict aus run_scenario() ist verschachtelt
(config/disruption/fallback/validation/simulation). Hier wird es in eine
flache Zeile für die Batch-CSV geplättet.
"""


CSV_COLUMNS = [
    "disruption_position_m", "actual_dist_in_lap_m",
    "disruption_km", "disruption_full_km",
    "num_agents", "num_trains",
    "disruption_lap", "agent_walk_speed_ms", "agent_reaction_time_s",
    "disruption_time_s", "disruption_edge", "disruption_edge_pos",
    "nearest_station_idx", "nearest_station_name", "dispatched_agent_id",
    "route_cost_s", "route_length_m", "winner_station_full_km",
    "t_reaction_s", "t_walk_s", "t_intervention_total_s",
    "total_steps", "total_sim_time_s", "timestamp",
    # findIntermodalRoute-Vergleich (SUMO 1.26+)
    "intermodal_best_key", "intermodal_best_length_m", "intermodal_best_cost_s",
    "jammed_arrival_dist_m",
    # Validierung
    "v_train_moved", "v_train_max_speed", "v_min_dist_m",
    "v_min_dist_agent", "v_on_target_steps", "v_agents_dispatched",
    "v_timeout",
    "v_jammed_count", "v_collision_count",
    "v_jammed_agents", "v_collision_agents",
]


def results_to_row(results: dict) -> dict:
    """Macht aus dem verschachtelten Ergebnis-Dict eine flache CSV-Zeile."""
    cfg = results.get("config", {})
    dis = results.get("disruption", {})
    fb = results.get("fallback", {})
    sim = results.get("simulation", {})
    val = results.get("validation", {})
    return {
        "disruption_position_m": cfg.get("disruption_position_m"),
        "actual_dist_in_lap_m": dis.get("actual_dist_in_lap"),
        "disruption_km": dis.get("disruption_km"),
        "disruption_full_km": dis.get("disruption_full_km"),
        "num_agents": cfg.get("num_agents"),
        "num_trains": cfg.get("num_trains"),
        "disruption_lap": cfg.get("disruption_lap"),
        "agent_walk_speed_ms": cfg.get("agent_walk_speed_ms"),
        "agent_reaction_time_s": cfg.get("agent_reaction_time_s"),
        "disruption_time_s": dis.get("time"),
        "disruption_edge": dis.get("edge"),
        "disruption_edge_pos": dis.get("edge_pos"),
        "nearest_station_idx": fb.get("nearest_station_idx"),
        "nearest_station_name": fb.get("nearest_station_name"),
        "dispatched_agent_id": fb.get("dispatched_agent_id"),
        "route_cost_s": fb.get("route_cost_s"),
        "route_length_m": fb.get("route_length_m"),
        "winner_station_full_km": fb.get("winner_station_full_km"),
        "intermodal_best_key": fb.get("intermodal_best_key"),
        "intermodal_best_length_m": fb.get("intermodal_best_length_m"),
        "intermodal_best_cost_s": fb.get("intermodal_best_cost_s"),
        "jammed_arrival_dist_m": fb.get("jammed_arrival_dist_m"),
        "t_reaction_s": fb.get("t_reaction_s"),
        "t_walk_s": fb.get("t_walk_s"),
        "t_intervention_total_s": fb.get("t_intervention_total_s"),
        "total_steps": sim.get("total_steps"),
        "total_sim_time_s": sim.get("total_sim_time_s"),
        "timestamp": results.get("timestamp"),
        "v_train_moved": val.get("train_moved_after_disruption"),
        "v_train_max_speed": val.get("train_max_speed_after_disruption"),
        "v_min_dist_m": val.get("min_dist_to_target_m"),
        "v_min_dist_agent": val.get("min_dist_agent_id"),
        "v_on_target_steps": val.get("agent_on_target_edge_steps"),
        "v_agents_dispatched": val.get("agents_dispatched_count"),
        "v_timeout": val.get("timeout_reached"),
        "v_jammed_count": val.get("jammed_count"),
        "v_collision_count": val.get("collision_count"),
        "v_jammed_agents": val.get("jammed_agents"),
        "v_collision_agents": val.get("collision_agents"),
    }
