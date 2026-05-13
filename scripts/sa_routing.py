"""
sa_routing.py — Rückfallebene Stationsagent: Routing & Walk-Tracking.

Simuliert Stationsagenten, die bei einer Störung von ihren Haltestellen
über den parallelen Fußweg (Lane 1 auf allen Subway-Edges) zum
gestörten Zug laufen.

Jede Station hat ZWEI Bahnsteige (Hin- und Rückrichtung). Pro Station
werden ZWEI Personen erstellt — eine pro Bahnsteig. Die Laufrichtung
(rechts/links) wird nicht mehr explizit modelliert; SUMO's findRoute
auf der Fußgänger-Lane bestimmt selbst die kürzeste Route zum Zug.

Bei Störung laufen ALLE Agenten ALLER Stationen gleichzeitig los.
Routing über traci.simulation.findRoute(vType="DEFAULT_PEDTYPE") —
SUMO findet die kürzeste Fußgängerroute auf dem Netz, die Zug-Route
(route_u4_long.rou.xml) wird dabei NICHT genutzt.

Der erste Agent innerhalb EDGE_ARRIVAL_TOLERANCE_M vom Zug gewinnt.

Mit dem Parallelweg-Netz (Fußweg auf eigener Lane) entfällt die alte
mehrstufige Jammed-Detection: Agent und Zug teilen sich keine Lane mehr,
der Agent kann nicht vom Zug blockiert werden. Nur noch Stufe 1 (primär).
"""

import logging

import traci
from config import SimulationConfig
from stations import STATIONS, Station

log = logging.getLogger(__name__)

# Toleranz (m) für die Edge-basierte Arrival-Detection.
# Agent muss auf demselben Edge wie der Zug sein UND innerhalb dieser
# Distanz (längs der Edge) zum Zug stehen.
EDGE_ARRIVAL_TOLERANCE_M = 15.0

# Micro-Edges (unter diesem Schwellwert): eine 2,54 m-Edge wie 60734138#1
# wird bei 3,33 m/s + 1 s Step in einem Simulationsschritt "übersprungen"
# — die Edge-basierte Detection sieht den Agenten dort nie.
# Lösung: Bei Target-Edges unter dieser Länge werden Vorgänger- und
# Nachfolger-Edge (aus ROUTE_*_EDGES) als zusätzliche Ankunfts-Zonen
# akzeptiert, wenn der Agent dort nahe am Übergang zur Target-Edge steht.
MICRO_EDGE_THRESHOLD_M = 5.0

# Komplette Edge-Sequenzen der Route r_1 — werden nur noch für die
# Micro-Edge-Nachbar-Toleranz benutzt (siehe activate()), nicht mehr
# für das Routing der Agenten selbst.
ROUTE_HIN_EDGES = [
    "-60734138#3", "-60734139", "-60734096#0", "1238346189", "60734091#1",
    "60734103#1", "60734103#2", "60540209#1", "60734100", "262540236",
    "262540239#0", "262540239#1", "262540239#2", "60734109", "60734112#1",
    "60734124", "1414296215#0", "1414296215#1", "1414296215#2", "5062172",
    "60752821#0", "60752826#0", "60752826#1", "60752829#2",
]
ROUTE_RUECK_EDGES = [
    "-60752829#2", "-60752829#1", "-60752829#0", "60752827",
    "409986816#1", "60698617#0", "60698617#1", "560679910#1",
    "60734119#1", "60698616#1", "60698616#2", "262540233", "262540234",
    "262540235", "262540237#0", "262540237#1", "262540237#2",
    "440748774#1", "440748774#2", "60734138#0", "60734138#1",
    "60734138#2", "60734138#3",
]


def _compute_walk_route(agent_edge: str, direction: str,
                        target_edge: str | None = None) -> list[str]:
    """
    Edge-Liste für einen Agenten in einer bestimmten Wende-Richtung.

    Wird von SA selbst nicht mehr genutzt (SA nutzt findRoute auf der
    Fußgänger-Lane), bleibt aber als Helper für ZUB+ erhalten — dort
    sind rechts/links semantisch eindeutig definiert (zugbezogene
    Laufrichtung relativ zur Zugposition).

    Falls target_edge gesetzt und in der Route enthalten: Liste wird
    dort abgeschnitten.
    """
    edges: list[str] = []
    try:
        if direction == "hin_rechts":
            idx = ROUTE_HIN_EDGES.index(agent_edge)
            edges = ROUTE_HIN_EDGES[idx:]
        elif direction == "hin_links":
            idx = ROUTE_HIN_EDGES.index(agent_edge)
            edges = list(reversed(ROUTE_HIN_EDGES[:idx + 1]))
        elif direction == "rueck_links":
            idx = ROUTE_RUECK_EDGES.index(agent_edge)
            edges = ROUTE_RUECK_EDGES[idx:]
        elif direction == "rueck_rechts":
            idx = ROUTE_RUECK_EDGES.index(agent_edge)
            edges = list(reversed(ROUTE_RUECK_EDGES[:idx + 1]))
    except ValueError:
        return []

    if target_edge and target_edge in edges:
        t_idx = edges.index(target_edge)
        edges = edges[:t_idx + 1]
    return edges


class StationAgentFallback:
    """
    Stationsagent-Rückfallebene mit paralleler Fußweg-Lane.

    Pro Station 2 Personen (Hin/Rück). Bei Störung laufen alle
    gleichzeitig los. Erster Agent in Zugnähe gewinnt.
    """

    def __init__(self, config: SimulationConfig, agent_indices: list[int],
                 conn=None):
        self.config = config
        self.agent_indices = agent_indices
        # conn ermöglicht parallele Simulationen mit separaten TraCI-Verbindungen.
        # None = Default-Verbindung über globales traci-Modul.
        self.conn = conn if conn is not None else traci

        # Zustand
        self.activated = False
        self.agent_dispatched = False
        self.agent_arrived = False

        # Zeitstempel
        self.activation_time: float | None = None
        self.dispatch_time: float | None = None
        self.arrival_time: float | None = None

        # Ergebnis (wird bei Ankunft gesetzt)
        self.nearest_station: Station | None = None
        self.nearest_station_idx: int | None = None
        self.dispatched_agent_id: str | None = None
        self.route_cost_s: float | None = None
        self.route_length_m: float | None = None
        self.jammed_arrival_dist_m: float | None = None  # None = kein Jammed-Fall

        # Zielposition (= Zug-Position bei Störung).
        # _target_edge ist IMMER eine reguläre Edge; wenn der Zug auf einer
        # Junction gestoppt wurde, ist _target_internal_edge die originale
        # internal edge (für Ankunftserkennung während der Junction-Durchquerung).
        self._target_edge: str | None = None
        self._target_pos: float | None = None
        self._target_internal_edge: str | None = None

        # Losgeschickte Agenten: {person_id: {"station_idx", "start_pos", "edge"}}
        self._dispatched_agents: dict[str, dict] = {}

        # Person-IDs pro Station: {station_idx: {"hin": pid, "rueck": pid}}
        self._agent_persons: dict[int, dict[str, str]] = {}

        # findIntermodalRoute-Vergleichswerte (nur Info)
        self._intermodal_routes: dict[str, dict] = {}

        # Arrival-Erweiterung für Micro-Edges (siehe MICRO_EDGE_THRESHOLD_M).
        # Mapping edge_id → "before"/"after":
        #   "before" = Agent auf Vorgänger-Edge nahe Edge-Ende zählt als Arrival
        #   "after"  = Agent auf Nachfolger-Edge nahe Edge-Anfang zählt als Arrival
        self._arrival_neighbor_edges: dict[str, str] = {}

    # ==================================================================
    # SIM-START: Agenten erstellen (2 pro Station)
    # ==================================================================

    def create_agents(self) -> None:
        """Pro Station 2 wartende SUMO-Personen spawnen (hin, rueck)."""
        for i, station_idx in enumerate(self.agent_indices):
            station = STATIONS[station_idx]
            for side, edge, pos, stop_id in [
                ("hin",   station.edge_hin,   station.stop_pos_hin,   station.stop_hin),
                ("rueck", station.edge_rueck, station.stop_pos_rueck, station.stop_rueck),
            ]:
                pid = f"station_agent_{i}_{side}"
                self.conn.person.add(personID=pid, edgeID=edge, pos=pos, depart=0)
                self.conn.person.appendWaitingStage(
                    personID=pid, duration=86400,
                    description=f"Wartet an {station.name} ({side})",
                    stopID=stop_id,
                )
                self._agent_persons.setdefault(station_idx, {})[side] = pid

    # ==================================================================
    # AKTIVIERUNG (bei Störung)
    # ==================================================================

    def activate(self, disruption_edge: str, disruption_edge_pos: float,
                 sim_time: float,
                 internal_edge: str | None = None) -> None:
        """Speichert Störungsposition als Ziel für alle Agenten.

        disruption_edge ist die (reguläre) Ziel-Edge. internal_edge ist
        optional die originale internal edge, falls der Zug auf einer
        Junction gestoppt wurde — wird zusätzlich für die Ankunftserkennung
        während der Junction-Durchquerung akzeptiert.
        """
        self.activated = True
        self.activation_time = sim_time
        self._target_edge = disruption_edge
        self._target_pos = disruption_edge_pos
        self._target_internal_edge = internal_edge

        # Arrival-Toleranz an Edge-Grenzen: Nachbar-Edges als Ankunfts-
        # Zonen registrieren, wenn (a) Target-Edge sehr kurz ist (Micro)
        # oder (b) target_pos sehr nahe am Edge-Anfang/-Ende liegt.
        # Grund: appendWalkingStage mit arrivalPos≈0 bzw. ≈edge_len wird
        # von SUMO nicht sauber erreicht — der Fußgänger bleibt auf der
        # Nachbar-Edge hängen und wird ohne Toleranz nie detektiert.
        try:
            target_length = self.conn.lane.getLength(disruption_edge + "_0")
        except Exception:
            target_length = MICRO_EDGE_THRESHOLD_M + 1.0
        is_micro = target_length < MICRO_EDGE_THRESHOLD_M
        near_start = disruption_edge_pos < EDGE_ARRIVAL_TOLERANCE_M
        near_end = (target_length > 0
                    and disruption_edge_pos > target_length
                                             - EDGE_ARRIVAL_TOLERANCE_M)
        if is_micro or near_start or near_end:
            for route in (ROUTE_HIN_EDGES, ROUTE_RUECK_EDGES):
                if disruption_edge in route:
                    idx = route.index(disruption_edge)
                    if idx > 0 and (is_micro or near_start):
                        self._arrival_neighbor_edges[route[idx - 1]] = "before"
                    if idx < len(route) - 1 and (is_micro or near_end):
                        self._arrival_neighbor_edges[route[idx + 1]] = "after"
            if self._arrival_neighbor_edges:
                log.info(
                    "Arrival-Toleranz: target %s@%.2f (len=%.2fm, "
                    "micro=%s near_start=%s near_end=%s) → Nachbarn: %s",
                    disruption_edge, disruption_edge_pos, target_length,
                    is_micro, near_start, near_end,
                    self._arrival_neighbor_edges,
                )

    # ==================================================================
    # UPDATE (jeden Simulationsschritt nach Aktivierung)
    # ==================================================================

    def update(self, sim_time: float) -> bool:
        """
        Prüft Reaktionszeit → Dispatch, danach Arrival-Detection.

        Returns True, sobald ein Agent angekommen ist (erster Arrival
        beendet die Simulation).

        Arrival-Detection (mit Parallelweg-Netz nur noch einstufig):
          Agent auf der gleichen Edge wie der Zug UND Längs-Distanz
          < EDGE_ARRIVAL_TOLERANCE_M → angekommen.
        """
        if not self.activated or self.agent_arrived:
            return self.agent_arrived

        # Phase 1: Reaktionszeit abwarten
        if not self.agent_dispatched:
            elapsed = sim_time - self.activation_time
            if elapsed >= self.config.agent_reaction_time_s:
                self._dispatch_all(sim_time)
            return False

        # Phase 2: Arrival-Detection
        target_edge = self._target_edge
        target_pos = self._target_pos
        internal_edge = self._target_internal_edge
        person_ids = self.conn.person.getIDList()

        for person_id, info in self._dispatched_agents.items():
            # Persona ist aus der Sim verschwunden = Walking-Stage beendet.
            # Ankunft bestätigen, wenn entweder
            #   (a) die zuletzt beobachtete Position im Ziel-Korridor lag,
            # ODER
            #   (b) die Walking-Stage explizit zum target_edge mit
            #       arrival_pos == target_pos geplant war.
            # Fall (b) deckt Walker ab, deren letzte beobachtete Edge eine
            # interne Walking-Area-Edge war (last_edge startet mit ':') —
            # SUMO entfernt die Person beim Abschluss der Walking-Stage in
            # einem Step, sodass last_edge nie auf target_edge wechselt.
            # Eine Walking-Stage endet nur durch Erreichen der arrivalPos,
            # daher gilt verschwunden + Walk-Plan zum target = arrived.
            # Vorbeiläufer scheitern weiterhin: ihre Walk-Edges enden nicht
            # auf target_edge.
            if person_id not in person_ids:
                last_edge = info.get("last_edge")
                last_pos = info.get("last_pos")
                walk_last_edge = info.get("walk_last_edge")
                walk_arrival_pos = info.get("walk_arrival_pos")
                arrived = False
                if (last_edge == target_edge
                        and last_pos is not None
                        and abs(last_pos - target_pos)
                        < EDGE_ARRIVAL_TOLERANCE_M):
                    arrived = True
                elif (walk_last_edge == target_edge
                      and walk_arrival_pos is not None
                      and abs(walk_arrival_pos - target_pos)
                      < EDGE_ARRIVAL_TOLERANCE_M):
                    arrived = True
                if arrived:
                    self._on_arrival(sim_time, person_id, info)
                    return True
                continue

            edge = self.conn.person.getRoadID(person_id)
            pos = (self.conn.person.getLanePosition(person_id)
                   if edge else None)
            info["last_edge"] = edge
            info["last_pos"] = pos

            # Ankunft, wenn Agent (a) auf der regulären Ziel-Edge nahe der
            # Ziel-Position ist, ODER (b) beim Junction-Fall auf der internal
            # edge ist (Durchquerung — dort steht der Zug tatsächlich), ODER
            # (c) bei Micro-Target-Edges auf Vorgänger/Nachfolger-Edge nahe
            # dem Übergang zur Target-Edge.
            if edge == target_edge:
                if abs(pos - target_pos) < EDGE_ARRIVAL_TOLERANCE_M:
                    self._on_arrival(sim_time, person_id, info)
                    return True
            elif internal_edge and edge == internal_edge:
                self._on_arrival(sim_time, person_id, info)
                return True
            elif edge in self._arrival_neighbor_edges:
                side = self._arrival_neighbor_edges[edge]
                if side == "before":
                    try:
                        edge_len = self.conn.lane.getLength(edge + "_0")
                    except Exception:
                        continue
                    if edge_len - pos < EDGE_ARRIVAL_TOLERANCE_M:
                        self._on_arrival(sim_time, person_id, info)
                        return True
                elif side == "after":
                    if pos < EDGE_ARRIVAL_TOLERANCE_M:
                        self._on_arrival(sim_time, person_id, info)
                        return True

        return False

    # ==================================================================
    # INTERNE METHODEN
    # ==================================================================

    def _dispatch_all(self, sim_time: float) -> None:
        """Alle 2 Agenten aller besetzten Stationen gleichzeitig losschicken.

        Routing über traci.simulation.findIntermodalRoute(modes="",
        vType="DEFAULT_PEDTYPE") mit departPos/arrivalPos. Anders als
        findRoute() berücksichtigt findIntermodalRoute die Bahnsteig-Position
        und liefert die echte kürzeste Fußgängerroute, auch wenn sie
        bidirektional über Reverse-Lanes oder Walking-Areas verläuft.
        """
        self.agent_dispatched = True
        self.dispatch_time = sim_time

        for idx in self.agent_indices:
            station = STATIONS[idx]
            persons = self._agent_persons[idx]

            for side, edge, pos in [
                ("hin",   station.edge_hin,   station.stop_pos_hin),
                ("rueck", station.edge_rueck, station.stop_pos_rueck),
            ]:
                person_id = persons[side]

                try:
                    stages = self.conn.simulation.findIntermodalRoute(
                        fromEdge=edge, toEdge=self._target_edge,
                        modes="", depart=sim_time,
                        walkFactor=1.0, departPos=pos,
                        arrivalPos=self._target_pos, vType="DEFAULT_PEDTYPE",
                    )
                except Exception as exc:
                    log.warning(
                        "findIntermodalRoute FEHLER station_%d_%s "
                        "(%s@%.2f) → %s@%.2f: %s",
                        idx, side, edge, pos,
                        self._target_edge, self._target_pos, exc,
                    )
                    continue

                if not stages:
                    log.warning(
                        "findIntermodalRoute leer: station_%d_%s "
                        "(%s@%.2f) → %s@%.2f",
                        idx, side, edge, pos,
                        self._target_edge, self._target_pos,
                    )
                    continue

                self._intermodal_routes[f"station_{idx}_{side}"] = {
                    "cost_s": sum(s.cost for s in stages),
                    "length_m": sum(s.length for s in stages),
                    "n_edges": sum(len(s.edges) for s in stages),
                    "n_stages": len(stages),
                }

                stage_edges: list[list[str]] = []
                for st in stages:
                    edges_list = list(st.edges)
                    if edges_list:
                        stage_edges.append(edges_list)

                if not stage_edges:
                    log.warning(
                        "findIntermodalRoute Stages ohne Edges: "
                        "station_%d_%s", idx, side,
                    )
                    continue

                last_edges = stage_edges[-1]
                if last_edges[-1] == self._target_edge:
                    arrival_pos = self._target_pos
                else:
                    arrival_pos = self.conn.lane.getLength(last_edges[-1] + "_0")

                try:
                    self.conn.person.removeStage(person_id, 0)
                    for i, edges_i in enumerate(stage_edges):
                        is_last = (i == len(stage_edges) - 1)
                        ap = arrival_pos if is_last else self.conn.lane.getLength(edges_i[-1] + "_0")
                        self.conn.person.appendWalkingStage(
                            personID=person_id,
                            edges=edges_i,
                            arrivalPos=ap,
                        )
                    self.conn.person.setSpeed(person_id,
                                              self.config.agent_walk_speed_ms)
                    self._dispatched_agents[person_id] = {
                        "station_idx": idx,
                        "start_pos": pos,
                        "edge": edge,
                        "walk_last_edge": last_edges[-1],
                        "walk_arrival_pos": arrival_pos,
                    }
                    flat = [e for sub in stage_edges for e in sub]
                    log.info(
                        "[DISPATCH] %s: %s@%.1f → %s@%.1f | %d stages, %d edges: %s",
                        person_id, edge, pos,
                        self._target_edge, arrival_pos,
                        len(stage_edges), len(flat),
                        flat if len(flat) <= 6
                        else f"{flat[:3]}..{flat[-2:]}",
                    )
                except Exception as exc:
                    log.warning(
                        "appendWalkingStage FEHLER %s: "
                        "%d stages %s..%s arrivalPos=%.2f target=%s@%.2f: %s",
                        person_id, len(stage_edges),
                        stage_edges[0][0], last_edges[-1],
                        arrival_pos, self._target_edge,
                        self._target_pos, exc,
                    )

    def _on_arrival(self, sim_time: float, winner_id: str,
                    winner_info: dict) -> None:
        """Registriert Ankunft — gewinnender Agent + Messwerte."""
        self.agent_arrived = True
        self.arrival_time = sim_time
        self.dispatched_agent_id = winner_id
        self.nearest_station_idx = winner_info["station_idx"]
        self.nearest_station = STATIONS[winner_info["station_idx"]]
        self.route_cost_s = sim_time - self.dispatch_time
        self.route_length_m = (
            self.route_cost_s * self.config.agent_walk_speed_ms
        )
        t_reaction = self.dispatch_time - self.activation_time
        t_walk = self.arrival_time - self.dispatch_time
        t_total = self.arrival_time - self.activation_time
        print(f"[SA ANKUNFT] {winner_id} | t={sim_time:.1f}s | "
              f"Station={self.nearest_station.name} | "
              f"t_reaction={t_reaction:.1f}s | t_walk={t_walk:.1f}s | "
              f"t_intervention={t_total:.1f}s")

    # ==================================================================
    # ERGEBNIS
    # ==================================================================

    def get_results(self) -> dict:
        """Messergebnisse als Dictionary."""
        t_reaction = t_walk = t_total = None
        if self.dispatch_time and self.activation_time:
            t_reaction = self.dispatch_time - self.activation_time
        if self.arrival_time and self.dispatch_time:
            t_walk = self.arrival_time - self.dispatch_time
        if self.arrival_time and self.activation_time:
            t_total = self.arrival_time - self.activation_time

        # Kürzeste findIntermodalRoute-Referenz
        best_key = best_len = best_cost = None
        for key, info in self._intermodal_routes.items():
            if best_cost is None or info["cost_s"] < best_cost:
                best_cost = info["cost_s"]
                best_len = info["length_m"]
                best_key = key

        return {
            "t_activation": self.activation_time,
            "t_dispatch": self.dispatch_time,
            "t_arrival": self.arrival_time,
            "t_reaction_s": t_reaction,
            "t_walk_s": t_walk,
            "t_intervention_total_s": t_total,
            "nearest_station_idx": self.nearest_station_idx,
            "nearest_station_name": (self.nearest_station.name
                                     if self.nearest_station else None),
            "dispatched_agent_id": self.dispatched_agent_id,
            "route_cost_s": self.route_cost_s,
            "route_length_m": self.route_length_m,
            "disruption_edge": self._target_edge,
            "disruption_edge_pos": self._target_pos,
            "intermodal_best_key": best_key,
            "intermodal_best_length_m": best_len,
            "intermodal_best_cost_s": best_cost,
            "jammed_arrival_dist_m": self.jammed_arrival_dist_m,
        }
