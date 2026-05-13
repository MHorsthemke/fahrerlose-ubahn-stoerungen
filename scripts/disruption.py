"""
disruption.py — Störungslogik: Notbremsung + Streckensperrung.

Überwacht den Zug während der Simulation und löst die Störung
(Notbremsung) aus, wenn zwei Bedingungen erfüllt sind:
  1. Der Zug ist im richtigen Umlauf (Runde) → disruption_lap
  2. Der Zug hat die konfigurierte Distanz innerhalb der Runde
     zurückgelegt → disruption_position_m

Die Rundenzählung basiert auf der bewährten Logik aus TraCI_control.py:
  - Der Zug wechselt vom letzten Edge (LAP_END_EDGE) zum ersten Edge
    (LAP_START_EDGE) der Route → neue Runde erkannt.
  - Zusätzlich muss der Zug fast stehen (speed ≤ LAP_SPEED_EPS), damit
    wir nur den echten Rundenwechsel zählen (an der Endhaltestelle).

Die "Einheitsstörung" ist immer eine Notbremsung:
  conn.vehicle.setSpeedMode(veh_id, 0)  # manuelle Kontrolle
  conn.vehicle.setSpeed(veh_id, 0.0)

Zusätzlich: Streckensperrung. Direkt beim Auslösen wird die letzte
Haltestelle vor der Störung (in Fahrtrichtung) bestimmt. Jeden Step
werden nachfolgende Züge, die diese Haltestelle in ihrer Restroute
haben, dort festgehalten (Dauer 99999 s). Alle Halte davor bleiben
normal. Weitere Züge queuen natürlich via SUMO-Fahrzeugfolge hinter
dem ersten festgehaltenen Zug.
Effekt = "als ob das Fahrzeug an der vorherigen Haltestelle einfach
hält", nur auf der aktuellen Richtung (Hin oder Rück).

Verwendung:
    disruption = DisruptionController(config, conn)
    # In der Simulationsschleife:
    disruption.update(sim_time, edge_km_map, edge_km_map_full)
    if disruption.active:
        ...
"""

import traci
from config import SimulationConfig
from stations import STATIONS
from sa_routing import ROUTE_HIN_EDGES, ROUTE_RUECK_EDGES
from data.umlauf_data import UMLAUF_STEP_MAP


# Vorab gefilterte Liste der regulären (nicht-internal) Sim-Schritte aus
# einem Probe-Umlauf: (lap_pos_m, edge_id, lane_pos_m). Sortiert nach
# lap_pos. Wird genutzt, um aus einer gegebenen Umlaufposition die
# korrekte reguläre Edge + Lane-Position zu rekonstruieren — speziell
# wenn der Zug auf einer internal Junction-Edge stoppt.
_LAP_TO_EDGE: list[tuple[float, str, float]] = sorted(
    [(lp, edge, lp_pos)
     for _t, lp, edge, lp_pos in UMLAUF_STEP_MAP
     if not edge.startswith(":")],
    key=lambda x: x[0],
)


def _lookup_regular_edge(lap_pos: float) -> tuple[str, float]:
    """
    Liefert (regular_edge, lane_pos) für eine Umlaufposition aus dem
    vermessenen Probe-Umlauf (UMLAUF_STEP_MAP). Wählt den Sim-Schritt
    mit minimalem |lp − lap_pos| unter den regulären Edges.
    """
    best_edge = ""
    best_lane_pos = 0.0
    best_diff = float("inf")
    for lp, edge, lp_pos in _LAP_TO_EDGE:
        diff = abs(lp - lap_pos)
        if diff < best_diff:
            best_diff = diff
            best_edge = edge
            best_lane_pos = lp_pos
    return best_edge, best_lane_pos


class DisruptionController:
    """
    Steuert die Auslösung einer Störung (Notbremsung).

    Zustandsautomat:
      WARTEN → (Runde + Position erreicht) → AKTIV → (resolve) → BESEITIGT
    """

    # Edge-IDs für die Rundenerkennung (Übergang Bockenheimer Warte).
    LAP_START_EDGE = "-60734138#3"   # Erstes Edge nach dem Rundenwechsel
    LAP_END_EDGE = "60734138#3"      # Letztes Edge vor dem Rundenwechsel
    LAP_SPEED_EPS = 0.10             # "steht" wenn v ≤ 0.10 m/s

    # Dauer des Langzeit-Stopps für festgehaltene Züge (Streckensperrung).
    CLOSURE_STOP_DURATION = 99999.0

    def __init__(self, config: SimulationConfig, conn=None):
        self.config = config
        # conn ermöglicht parallele Simulationen mit separaten TraCI-Verbindungen.
        # None = Default-Verbindung über globales traci-Modul.
        self.conn = conn if conn is not None else traci

        # Zustand
        self.active = False
        self.resolved = False
        self.disruption_time: float | None = None

        # Position des gestörten Zuges (für den Agenten).
        # disruption_edge ist IMMER eine reguläre Edge; wenn der Zug auf einer
        # Junction (internal edge) gestoppt wurde, wird hier die erste reguläre
        # Edge nach der Junction mit pos=0 eingetragen. Die originale internal
        # edge landet separat in disruption_internal_edge.
        self.disruption_edge: str | None = None
        self.disruption_edge_pos: float | None = None
        self.disruption_internal_edge: str | None = None  # nur gesetzt, wenn Trigger auf Junction
        self.actual_dist_in_lap: float | None = None
        self.disruption_km: float | None = None         # ohne Junction-Edges
        self.disruption_full_km: float | None = None    # mit Junction-Edges

        # Rundenzählung
        self.current_lap = 0
        self._prev_edge: str | None = None
        self._lap_start_dist: float = 0.0

        # Streckensperrung — beidseitig.
        # Auf Störungsseite: prev_stop_id = letzte Haltestelle, die der
        # gestörte Zug VOR der Störung passiert hat (in Fahrtrichtung).
        # Auf Gegenseite:    opp_stop_id  = die Station, die in
        # Störungsrichtung NACH der Störung käme — auf der GEGENSEITE
        # (also Hin↔Rück getauscht). Begründung: Sperrt man die Strecke
        # zwischen zwei benachbarten Stationen A (niedrigerer km) und
        # B (höherer km), dann hält Hin-Verkehr an A_hin (vor der Sperre
        # in Hin-Richtung), Rück-Verkehr an B_rück (vor der Sperre in
        # Rück-Richtung). Pro Zug wird die ERSTE der beiden Closure-IDs
        # in der Restroute genutzt — so passt der Halt zur jeweiligen
        # Fahrtrichtung des Zuges.
        self.direction: str | None = None
        self.prev_stop_id: str | None = None
        self.prev_stop_name: str | None = None
        self.opp_stop_id: str | None = None
        self.opp_stop_name: str | None = None
        self._closure_set: set[str] = set()        # Züge, die schon festgehalten sind

    def update(self, sim_time: float,
               edge_km_map: dict[str, float] | None = None,
               edge_km_map_full: dict[str, float] | None = None) -> None:
        """
        Wird JEDEN Simulationsschritt aufgerufen.

        Prüft Rundenwechsel, trackt Distanz, löst ggf. Störung aus.

        Args:
            sim_time: Aktuelle Simulationszeit in Sekunden
            edge_km_map: edge → km (ohne Junction-Edges, für disruption_km)
            edge_km_map_full: edge → km (mit Junction-Edges, für disruption_full_km)
        """
        if self.active or self.resolved:
            # Zug JEDEN Step auf 0 halten (setSpeed wirkt nur einen Step).
            # Auch nach resolve(): der gestörte Zug fährt im Modell nicht
            # weiter — t_intervention ist die Messgröße, die Räumung danach
            # ist nicht Teil des Modells.
            self.conn.vehicle.setSpeed(self.config.disruption_vehicle_id, 0.0)
            if self.active:
                self._enforce_track_closure()
            return

        veh_id = self.config.disruption_vehicle_id
        if veh_id not in self.conn.vehicle.getIDList():
            return

        speed = self.conn.vehicle.getSpeed(veh_id)
        dist_total = self.conn.vehicle.getDistance(veh_id)
        lane_id = self.conn.vehicle.getLaneID(veh_id)

        curr_edge = None
        if lane_id and "_" in lane_id:
            curr_edge = lane_id.rsplit("_", 1)[0]

        # Rundenwechsel erkennen
        lap_switch = (
            self._prev_edge == self.LAP_END_EDGE
            and curr_edge == self.LAP_START_EDGE
            and speed is not None
            and speed <= self.LAP_SPEED_EPS
            and dist_total is not None
        )

        if lap_switch:
            self.current_lap += 1
            self._lap_start_dist = dist_total
            print(f"[RUNDE] Neue Runde: {self.current_lap} | "
                  f"t={sim_time:.1f}s | dist_total={dist_total:.1f}m")

        self._prev_edge = curr_edge

        if self.current_lap < self.config.disruption_lap:
            return

        if dist_total is None:
            return

        dist_in_lap = dist_total - self._lap_start_dist
        if dist_in_lap >= self.config.disruption_position_m:
            self._trigger(veh_id, sim_time, curr_edge, dist_in_lap,
                          edge_km_map, edge_km_map_full)

    def _trigger(self, veh_id: str, sim_time: float, edge: str,
                 dist_in_lap: float,
                 edge_km_map: dict[str, float] | None,
                 edge_km_map_full: dict[str, float] | None) -> None:
        """
        Löst die Notbremsung aus.

        Junction-Edges (interne Edges, IDs mit führendem ':') sind zulässig:
        Der Zug kann dort mit setSpeedMode(0) + setSpeed(0) halten. Für die
        Fallback-Agenten wird aber eine *reguläre* Edge gebraucht, weil die
        Walk-Routen-Konstruktion (ROUTE_HIN_EDGES/RUECK_EDGES) nur reguläre
        Edges kennt. Deshalb normalisieren wir:
          - disruption_internal_edge = originale internal edge
          - disruption_edge / _edge_pos = aus UMLAUF_STEP_MAP nachgeschlagen
            anhand der Umlaufposition (dist_in_lap). Das ist robust gegen
            getRouteIndex-Anomalien und liefert die geometrisch korrekte
            Edge + Position auch in Wendepunkt-Bereichen.
        Die Junction ist typisch 2–5 m lang; die Fallback-Agenten erkennen
        die Ankunft sowohl via reguläre Edge (Eintritt) als auch via
        internal edge (Durchquerung).
        """
        lane_pos = self.conn.vehicle.getLanePosition(veh_id)
        internal_edge = None
        regular_edge = edge
        regular_pos = lane_pos

        if edge.startswith(":"):
            internal_edge = edge
            # Umlaufposition (dist_in_lap) → nähestliegende reguläre Edge
            # aus dem vermessenen Probe-Umlauf nachschlagen.
            regular_edge, regular_pos = _lookup_regular_edge(dist_in_lap)

        # SUMO-Quirk: auf Mikro-Edges (z.B. 60734138#2 mit 1,55 m) liefert
        # getLanePosition manchmal Werte deutlich größer als die Edge-Länge,
        # weil die Train-Front bereits auf der Nachfolge-Edge ist, getRoadID
        # aber noch die Vorgänger-Edge meldet. Ohne Clamp lehnt SUMO
        # appendWalkingStage / findIntermodalRoute die arrivalPos ab.
        try:
            edge_len = self.conn.lane.getLength(regular_edge + "_0")
        except Exception:
            edge_len = None
        if edge_len is not None and regular_pos > edge_len:
            regular_pos = max(0.0, edge_len - 0.01)

        self.active = True
        self.disruption_time = sim_time
        self.disruption_edge = regular_edge
        self.disruption_edge_pos = regular_pos
        self.disruption_internal_edge = internal_edge
        self.actual_dist_in_lap = dist_in_lap

        # km-Maps nutzen die ORIGINAL-Edge (mit Junction), damit die
        # Position des gestörten Zugs im km-Band korrekt bleibt.
        if edge_km_map and edge in edge_km_map:
            self.disruption_km = edge_km_map[edge] + lane_pos
        else:
            self.disruption_km = None

        if edge_km_map_full and edge in edge_km_map_full:
            self.disruption_full_km = edge_km_map_full[edge] + lane_pos
        else:
            self.disruption_full_km = None

        # Speed-Modus auf volle manuelle Kontrolle setzen (Bit 0-4 aus),
        # damit SUMO den setSpeed(0) nicht durch Haltestellenlogik
        # oder Fahrzeugfolge-Modell überschreibt. Ohne das kann der Zug
        # nicht auf Junction-Edges halten.
        self.conn.vehicle.setSpeedMode(veh_id, 0)
        self.conn.vehicle.setSpeed(veh_id, 0.0)

        print(f"[STÖRUNG] t={sim_time:.1f}s | Runde {self.current_lap} | "
              f"Edge: {edge} | Lane-Pos: {self.disruption_edge_pos:.1f}m | "
              f"Sollposition: {self.config.disruption_position_m:.0f}m | "
              f"Ist: {dist_in_lap:.1f}m")

        # Streckensperrung vorbereiten (vorherige Haltestelle + Richtung)
        self._setup_track_closure(veh_id)

    def resolve(self, sim_time: float) -> None:
        """
        Wird aufgerufen wenn die Rückfallebene die Störung beseitigt hat.
        """
        self.resolved = True
        self.active = False
        duration = sim_time - self.disruption_time if self.disruption_time else 0
        print(f"[STÖRUNG BESEITIGT] t={sim_time:.1f}s | Dauer: {duration:.1f}s")

    # ===================================================================
    # STRECKENSPERRUNG
    # ===================================================================

    def _setup_track_closure(self, veh_id: str) -> None:
        """
        Bestimmt Richtung der Störung + die zwei Closure-Haltestellen
        (Störungsseite und Gegenseite). Einmalig beim Auslösen der
        Störung aufgerufen.

        Liegt die Störung im Streckenabschnitt zwischen zwei aufeinander
        folgenden Stationen A (niedrigere km) und B (höhere km), dann
        ist die Closure-Logik wie folgt (Beispiel: Störung Rück zwischen
        Höhenstraße und Merianplatz):
          - Rück-Strecke: Sperre an Höhenstraße Rück (= prev_stop in
            Fahrtrichtung Rück, gerade passiert).
          - Hin-Strecke:  Sperre an Merianplatz Hin (= dieselbe Station,
            die in Störungsrichtung NACH der Störung käme,
            Bahnsteigseite Hin).
        """
        edge = self.disruption_edge

        # Richtung bestimmen + die zugehörige statische Route-Liste auswählen.
        # Die statische Liste ist Lap-agnostisch — anders als getRoute(), das
        # eine über alle Laps expandierte Edge-Sequenz liefert. Iteriert man
        # über getRoute() rückwärts, springt die Suche bei Disruption am
        # Lap-Anfang über die Wende in die VORHERIGE Lap und liefert eine
        # geometrisch falsche prev-Station (z.B. Seckbacher Hin in Lap n-1
        # bei Disruption auf -60734138#3 in Lap n).
        if edge in ROUTE_HIN_EDGES:
            self.direction = "hin"
            route_list = ROUTE_HIN_EDGES
        elif edge in ROUTE_RUECK_EDGES:
            self.direction = "rueck"
            route_list = ROUTE_RUECK_EDGES
        else:
            print(f"[SPERRUNG] Richtung für Edge {edge} unbekannt — keine Sperrung")
            return

        disruption_pos = self.disruption_edge_pos or 0.0
        disrupt_idx = route_list.index(edge)
        disrupt_key = (disrupt_idx, disruption_pos)

        # Alle Stationen der aktuellen Richtung mit (route_idx, stop_pos) als
        # Sortierschlüssel. Auf geteilten Edges (5062172/60752827) liegen
        # mehrere Stops auf derselben Edge — die Position disambiguiert.
        station_keys: list[tuple[int, float, "Station"]] = []
        for s in STATIONS:
            if self.direction == "hin":
                s_edge, s_pos = s.edge_hin, s.stop_pos_hin
            else:
                s_edge, s_pos = s.edge_rueck, s.stop_pos_rueck
            if s_edge in route_list:
                s_idx = route_list.index(s_edge)
                station_keys.append((s_idx, s_pos, s))
        station_keys.sort()

        # PREV = letzte Station mit (idx, pos) < disrupt_key
        # NEXT = erste Station mit (idx, pos) > disrupt_key
        prev = None
        nxt = None
        for s_idx, s_pos, s in station_keys:
            if (s_idx, s_pos) < disrupt_key:
                prev = s
            elif (s_idx, s_pos) > disrupt_key and nxt is None:
                nxt = s

        # Sonderfall Wendezone (Eingang): Störung liegt zwischen einem
        # Wendepunkt und der ersten regulären Station in Fahrtrichtung
        # (z.B. -60734138#3 vor BW Hin). Dann fehlt prev — nxt-Station ist
        # die einzig sinnvolle Closure auf der Störungsseite.
        if prev is None and nxt is not None:
            prev = nxt

        # Sonderfall Wendezone (Ausgang): Störung liegt zwischen der
        # letzten regulären Station in Fahrtrichtung und dem Wendepunkt
        # (z.B. 60752829#2 hinter SL Hin vor SL-Wende). Dann fehlt nxt —
        # prev-Station liefert auch die Gegenseite (selbe Station, andere
        # Richtung), weil Verkehr aus der Gegenrichtung diese Wendezone
        # über genau diesen Bahnsteig erreicht.
        if nxt is None and prev is not None:
            nxt = prev

        if prev is None and nxt is None:
            print("[SPERRUNG] Keine Closure-Haltestelle gefunden — keine Sperrung")
            return

        if prev is not None:
            self.prev_stop_id = (prev.stop_hin if self.direction == "hin"
                                 else prev.stop_rueck)
            self.prev_stop_name = prev.name

        if nxt is not None:
            # Gegenseite: Hin↔Rück tauschen
            self.opp_stop_id = (nxt.stop_rueck if self.direction == "hin"
                                else nxt.stop_hin)
            self.opp_stop_name = nxt.name

        dir_label = "Hin" if self.direction == "hin" else "Rück"
        opp_label = "Rück" if self.direction == "hin" else "Hin"
        print(f"[SPERRUNG] Störung {dir_label} | "
              f"{dir_label}-Sperre: "
              f"{self.prev_stop_name or '—'} ({dir_label}, "
              f"stop={self.prev_stop_id or '—'}) | "
              f"{opp_label}-Sperre: "
              f"{self.opp_stop_name or '—'} ({opp_label}, "
              f"stop={self.opp_stop_id or '—'})")

    def _enforce_track_closure(self) -> None:
        """
        Hält nachfolgende Züge an der jeweils passenden Closure-Haltestelle
        fest — Störungsseite (prev_stop_id) ODER Gegenseite (opp_stop_id),
        je nachdem welche der beiden zuerst in der Restroute des Zuges liegt.

        Pro Step durchgeführt, solange die Störung aktiv ist. Pro Zug:
          1. Gestörter Zug + schon festgehaltene Züge werden übersprungen.
          2. Erste Closure-ID in den nächsten Stops bestimmt die Halt-Seite
             (Hin oder Rück). Stop-Dauer dort wird auf 99999 s gesetzt.
          3. Reguläre Halte DAVOR (Willy-Brandt, Dom/Römer etc.) bleiben
             unverändert — der Zug fährt normal weiter bis zur Closure.
          4. Der erste Zug pro Seite hält dort, weitere queuen via
             SUMO-Fahrzeugfolge- und Haltestellen-Logik.
        """
        closure_ids = {sid for sid in (self.prev_stop_id, self.opp_stop_id)
                       if sid is not None}
        if not closure_ids:
            return

        disrupted_veh = self.config.disruption_vehicle_id

        for veh_id in self.conn.vehicle.getIDList():
            if veh_id == disrupted_veh:
                continue
            if veh_id in self._closure_set:
                continue

            try:
                stops = self.conn.vehicle.getStops(veh_id, 5)
            except Exception:
                continue

            # ERSTE Closure-Haltestelle in der Restroute → die richtige Seite.
            target_id = None
            for s in stops:
                if s.stoppingPlaceID in closure_ids:
                    target_id = s.stoppingPlaceID
                    break
            if target_id is None:
                continue

            try:
                self.conn.vehicle.setBusStop(
                    vehID=veh_id,
                    stopID=target_id,
                    duration=self.CLOSURE_STOP_DURATION,
                )
                self._closure_set.add(veh_id)
                print(f"[SPERRUNG] Zug {veh_id} wird an "
                      f"{self._stop_name(target_id)} festgehalten "
                      f"(stop={target_id}, 99999 s)")
            except Exception as e:
                print(f"[SPERRUNG] FEHLER setBusStop {veh_id}: {e}")

    def _stop_name(self, stop_id: str) -> str:
        """Gibt einen menschenlesbaren Namen für eine busStop-ID zurück."""
        for s in STATIONS:
            if s.stop_hin == stop_id:
                return f"{s.name} (Hin)"
            if s.stop_rueck == stop_id:
                return f"{s.name} (Rück)"
        return stop_id

    def get_results(self) -> dict:
        """Messergebnisse als Dictionary."""
        return {
            "lap": self.current_lap,
            "time": self.disruption_time,
            "edge": self.disruption_edge,
            "edge_pos": self.disruption_edge_pos,
            "actual_dist_in_lap": self.actual_dist_in_lap,
            "disruption_km": self.disruption_km,
            "disruption_full_km": self.disruption_full_km,
        }
