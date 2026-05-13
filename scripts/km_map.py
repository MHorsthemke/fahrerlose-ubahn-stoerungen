"""
km_map.py — Kumulative km-Position für jede Edge der Route.

Liefert zwei Maps:
  - km_map       → nur reguläre Edges (= stations.py-Koordinatensystem)
  - km_map_full  → reguläre Edges + Junction-Edges (= reale Laufdistanz)

km_map_full wird gebraucht, damit Störungen, die auf Junction-Edges
ausgelöst werden, korrekt in disruption_full_km erfasst werden können.
"""


def build_edge_km_map(conn, vehicle_id: str) -> tuple[dict[str, float],
                                                        dict[str, float]]:
    """Kumulative km-Tabellen: edge → km-Start.

    Hinweis: route.getEdges() liefert NUR reguläre Edges (keine Junctions).
    Die Junction-Längen werden über lane.getLinks() ermittelt: Für jedes
    aufeinanderfolgende Edge-Paar wird das verbindende interne Lane
    (via-Lane) gesucht und dessen Länge addiert.
    """
    try:
        route_id = conn.vehicle.getRouteID(vehicle_id)
        route_edges = list(conn.route.getEdges(route_id))
    except Exception:
        route_edges = list(conn.route.getEdges("r_1"))

    # Route kann repeat-Wiederholungen enthalten (z.B. 47×13 = 611).
    # Nur EINEN Loop verwenden: beim zweiten Auftreten des ersten Edges abschneiden.
    first_edge = route_edges[0]
    for cut_idx in range(1, len(route_edges)):
        if route_edges[cut_idx] == first_edge:
            route_edges = route_edges[:cut_idx]
            break

    km_map: dict[str, float] = {}       # ohne Junctions
    km_map_full: dict[str, float] = {}  # mit Junctions
    cumulative = 0.0
    cumulative_full = 0.0

    for i, edge in enumerate(route_edges):
        km_map[edge] = cumulative
        km_map_full[edge] = cumulative_full

        edge_len = conn.lane.getLength(edge + "_0")
        cumulative += edge_len
        cumulative_full += edge_len

        # Junction-Länge zum nächsten Edge ermitteln.
        # SUMO 1.26 getLinks() liefert IMMER 8-Tupel:
        #   (approachedLane, hasPrio, isOpen, hasFoe, viaLane, state, direction, length)
        if i < len(route_edges) - 1:
            next_edge = route_edges[i + 1]
            via_len = 0.0
            via_edge = None
            try:
                links = conn.lane.getLinks(edge + "_0")
                for link in links:
                    target_lane = link[0]
                    if target_lane.startswith(next_edge + "_"):
                        via_lane = link[4]
                        if via_lane:
                            via_edge = via_lane.rsplit("_", 1)[0]
                        via_len = link[7]
                        break
            except Exception:
                pass
            # Junction-Edge (":nodeID_x") beginnt am Ende der aktuellen regulären Edge
            if via_edge:
                km_map_full[via_edge] = cumulative_full
            cumulative_full += via_len

    return km_map, km_map_full
