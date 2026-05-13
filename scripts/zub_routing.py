"""
zub_routing.py — Rückfallebene ZUB+: Routing, Dispatch & Walk-Tracking.

Verteilung (welcher Zug) liegt in zub_distribution.py.

Haltestellenmodell (MA Kap. 3.3.2):

Der ZUB+ sitzt an Bord eines Zuges. Bei einer Störung gibt es zwei
Grundfälle:

  Fall 1: ZUB+ ist auf dem gestörten Zug
    → Interventionszeit = 0 (trivial, keine Simulation nötig)

  Fall 2: ZUB+ ist auf einem anderen Zug
    → Strecke wird beidseitig gesperrt (Störungsseite + Gegenseite).
    → ZUB+-Zug fährt bis zur ersten Closure-Haltestelle in der
      Restroute und hält dort an (setBusStop 99999 s). Welche der
      beiden Closures (Störungsseite oder Gegenseite) zuerst kommt,
      hängt automatisch an der aktuellen Fahrtrichtung des ZUB+-Zugs.
    → ZUB+ steigt aus. Wenn die Closure auf der Gegenseite liegt,
      wechselt er via <access> die Bahnsteigseite (sonst nicht).
    → Anschließend läuft er entlang des Gleiskörpers (Störungsseite)
      zum gestörten Zug.

Es gibt KEINEN Zugumstieg. Der ZUB+ steigt einmal aus und läuft den
Rest zu Fuß.

Reaktionszeit: Der ZUB+ benötigt agent_reaction_time_s Sekunden nach
der Störung, um zu reagieren (Informationszeit). Erst danach steigt er
aus und läuft los. Wenn der Zug schon vor Ablauf der 90 s steht,
wartet der ZUB+ on-board; läuft der Zug noch, gilt
max(queue_time, activation + 90 s) als Start.
"""

from config import SimulationConfig
from stations import STATIONS
from sa_routing import (
    ROUTE_HIN_EDGES,
    ROUTE_RUECK_EDGES,
    _compute_walk_route,
)


class ZubFallback:
    """
    Verwaltet das Verhalten des ZUB+ bei einer Störung (Haltestellenmodell).

    Der ZUB+ sitzt auf einem bestimmten Zug (zub_vehicle_id).
    Er wird bei Sim-Start als Person erstellt und fährt im Zug mit.
    Bei Störung wird die letzte Haltestelle vor der Störung als Ziel
    gesetzt. Der Zug hält dort (oder staut sich davor auf), der ZUB+
    steigt aus und läuft zum gestörten Zug.
    """

    # Ab wann gilt ein Zug als stehend (Geschwindigkeit < Schwelle)
    QUEUE_SPEED_THRESHOLD = 0.5  # m/s

    # Wie viele Schritte muss Speed < Schwelle sein bevor wir aussteigen
    # Wichtig: Reguläre Fahrplan-Halte dauern bis zu 30s + Beschleunigung
    # → mindestens 60 Schritte (60s) warten, bevor wir "Stau" sagen.
    QUEUE_STABLE_STEPS = 60

    # Cascade-Aufstau: Lookahead, in dem ein stehender Vorderzug als
    # Schlangen-Indikator gilt. Bei Aufstau hängen die Züge typisch im
    # Bremsabstand (5-30m); 100m deckt das ab, ohne Vorderzüge auf der
    # nächsten Edge zu erfassen.
    LEADER_LOOKAHEAD_M = 100.0

    # Dauer des Ziel-Stopps (sehr lange → Zug bleibt stehen bis Sim-Ende)
    LONG_STOP_DURATION = 99999.0

    # Toleranz: wie nah muss die Zug-Position am Ziel-Stop-Zentrum sein,
    # damit "am Ziel" gilt (in Metern auf der Lane)
    TARGET_POS_TOL_M = 80.0

    # === Einstiegsort: Bockenheimer Warte Hin (erster Halt der Route r_1) ===
    BOARDING_EDGE = "1238346189"
    BOARDING_POS = 76.6
    BOARDING_STOP = "2682026582"

    # === Ziel der Fahrt: BW Rück (letzter Halt vor Routenwiederholung) ===
    # Person fährt pro Driving-Stage von BW Hin bis BW Rück (≈ 1 Umlauf)
    ALIGHTING_EDGE = "440748774#2"
    ALIGHTING_STOP = "3385060043"

    # Anzahl Fahr-Stages (1 Stage ≈ 1 Umlauf ≈ 1562s)
    # 20 Stages reichen für jede realistische Simulationsdauer
    NUM_RIDING_STAGES = 20

    # === Cross-Side-Seitenwechsel via <access> ===
    # Welcher busStop verbindet die Hin-/Rück-Seite per Access?
    # Phase 1 (Prototyp): nur BW hat <access>. Phase 2: alle U4-Stationen.
    # Bei mehreren Access-Stops wählt findIntermodalRoute automatisch den
    # günstigsten.  Mapping: Zielseite → (busStop-ID, busStop-Edge).
    CROSS_STOP_FOR_SIDE = {
        "hin":   ("2682026582", "1238346189"),   # BW Hin
        "rueck": ("3385060043", "440748774#2"),  # BW Rück
    }

    def __init__(self, config: SimulationConfig,
                 zub_vehicle_id: str, gap: int,
                 num_trains: int = 1):
        """
        Args:
            config:          Simulationsparameter
            zub_vehicle_id:  ID des Zugs auf dem der ZUB+ sitzt (z.B. "u4_3")
            gap:             Abstand zum gestörten Zug in Zugpositionen
            num_trains:      Gesamtanzahl Züge im Umlauf
        """
        self.config = config
        self.zub_vehicle_id = zub_vehicle_id
        self.gap = gap
        self.num_trains = num_trains

        # === Zustand ===
        self.activated = False        # Störung erkannt
        self.target_set = False       # Ziel-Haltestelle + setBusStop gesetzt
        self.zub_queued = False       # ZUB+-Zug steht (am Ziel oder im Stau)
        self.zub_dispatched = False   # ZUB+ ausgestiegen und losgelaufen
        self.zub_arrived = False      # ZUB+ am gestörten Zug angekommen
        self._dispatch_failed = False # Cross-Side-Route unroutbar → Szenario abbrechen

        # === Zeitstempel ===
        self.activation_time: float | None = None    # Störungszeitpunkt
        self.queue_time: float | None = None         # ZUB+-Zug steht
        self.dispatch_time: float | None = None      # ZUB+ losgelaufen
        self.arrival_time: float | None = None       # ZUB+ angekommen

        # === Positionsdaten ===
        # _target_edge ist IMMER eine reguläre Edge (siehe disruption.py).
        # Wenn der Zug auf einer Junction gestoppt wurde, ist
        # _target_internal_edge die originale internal edge — wird in der
        # Ankunftserkennung zusätzlich akzeptiert (Zug steht dort wirklich).
        self._target_edge: str | None = None         # Edge des gestörten Zugs (regulär)
        self._target_pos: float | None = None        # Position auf dem Edge
        self._target_internal_edge: str | None = None
        self._target_stop_id: str | None = None      # busStop-ID der Ziel-Haltestelle
        self._target_stop_edge: str | None = None    # Edge der Ziel-Haltestelle
        self._target_stop_pos: float | None = None   # Mittelpunkt auf Edge
        self._zub_exit_edge: str | None = None       # Edge wo ZUB+ aussteigt
        self._zub_exit_pos: float | None = None      # Position wo ZUB+ aussteigt
        self._arrival_edge: str | None = None        # Tatsächliches Ankunfts-Edge
        self._arrival_pos: float | None = None

        # === Closure-IDs (Streckensperrung) ===
        # Wird bei activate() von disruption.py mitgegeben:
        # (prev_stop_id auf Störungsseite, opp_stop_id auf Gegenseite).
        # _set_target_stop nimmt die ERSTE der beiden, die in der
        # Restroute des ZUB+-Zuges liegt — passt automatisch zur
        # aktuellen Fahrtrichtung des Zuges (Hin oder Rück).
        self._closure_stop_ids: tuple[str, ...] = ()

        # === Person-ID ===
        self.person_id: str = "zub_plus"

        # Debug: pruefe Person-Existenz einen Step nach Dispatch
        self._verify_person_next_step = False

        # === Queue-Erkennung ===
        self._queue_counter = 0  # Zählt Steps mit Speed < Threshold

        # === Route-Info (für CSV) ===
        self.route_cost_s: float | None = None
        self.route_length_m: float | None = None

    # ==================================================================
    # PERSON ERSTELLEN (bei Sim-Start)
    # ==================================================================

    def create_zub_person(self, conn):
        """
        No-op — die ZUB+-Person wird erst bei Dispatch an der aktuellen
        Position des ZUB+-Zuges auf der Parallelweg-Lane erzeugt.

        Hintergrund: Die frühere Lösung mit 20 Driving-Stages (Einstieg
        BW Hin, Ausstieg BW Rück, Wiederholung) führte dazu, dass die
        Person zwischen den Stages ~1460 s auf dem BW-Rück-Bahnsteig
        wartete, bis der ZUB+-Zug den nächsten Umlauf schloss. In der
        GUI war das als "ZUB+ steigt vor der Störung aus" sichtbar und
        schwer nachvollziehbar. Da SUMO Personen in Fahrzeugen nicht
        rendert, hat das lazy-create identisches visuelles Ergebnis
        ("ZUB+ fährt unsichtbar im Zug mit"), vermeidet aber die
        falschen Ausstiege.
        """
        print(f"[ZUB+] Person wird bei Dispatch erzeugt | "
              f"Zug: {self.zub_vehicle_id}")

    # ==================================================================
    # AKTIVIERUNG (bei Störung)
    # ==================================================================

    def activate(self, disruption_edge: str, disruption_edge_pos: float,
                 sim_time: float,
                 internal_edge: str | None = None,
                 closure_stop_ids: tuple[str | None, ...] = ()):
        """
        Wird aufgerufen wenn die Störung eintritt.

        Die Ziel-Haltestelle + setBusStop wird erst im nächsten update()
        gesetzt, weil wir dort Zugriff auf `conn` haben.

        internal_edge: originale internal edge falls der Zug auf einer
        Junction gestoppt wurde — sonst None.

        closure_stop_ids: Closure-Haltestellen aus disruption.py
        (prev_stop_id, opp_stop_id). _set_target_stop wählt daraus die
        erste, die in der Restroute des ZUB+-Zuges vorkommt — passt
        automatisch zur aktuellen Fahrtrichtung.
        """
        self.activated = True
        self.activation_time = sim_time
        self._target_edge = disruption_edge
        self._target_pos = disruption_edge_pos
        self._target_internal_edge = internal_edge
        self._closure_stop_ids = tuple(s for s in closure_stop_ids if s)

    # ==================================================================
    # UPDATE (jeden Simulationsschritt)
    # ==================================================================

    def update(self, conn, sim_time: float) -> bool:
        """
        Wird jeden Simulationsschritt aufgerufen.

        Returns:
            True wenn ZUB+ am gestörten Zug angekommen ist.
        """
        if not self.activated or self.zub_arrived:
            return self.zub_arrived

        # Dispatch-Fail (unroutbare Cross-Side) → Szenario sauber beenden
        # (kein t_walk/Route-Eintrag, damit Runner den Fall als Fehler loggt).
        if self._dispatch_failed:
            return True

        # Verify-Check einen Step nach Dispatch: Person tatsaechlich aktiv?
        if self._verify_person_next_step:
            self._verify_person_next_step = False
            try:
                in_list = self.person_id in conn.person.getIDList()
                if in_list:
                    lane = conn.person.getLaneID(self.person_id)
                    xy = conn.person.getPosition(self.person_id)
                    stage = conn.person.getStage(self.person_id).type
                    print(f"[ZUB+ DEBUG] Person aktiv t={sim_time:.0f}s | "
                          f"lane={lane} | pos_xy=({xy[0]:.1f},{xy[1]:.1f}) | "
                          f"stage_type={stage}")
                else:
                    print(f"[ZUB+ DEBUG] FEHLER: Person nicht in SUMO "
                          f"t={sim_time:.0f}s (getIDList leer)!")
            except Exception as e:
                print(f"[ZUB+ DEBUG] Verify-Check Fehler: {e}")

        # =============================================================
        # PHASE 0: Ziel-Haltestelle bestimmen (einmalig nach Activate)
        # =============================================================
        if not self.target_set:
            self._set_target_stop(conn)
            if not self.target_set:
                return False  # Bestimmung gescheitert — später erneut versuchen

        # =============================================================
        # PHASE 1: Warten bis ZUB+-Zug steht (Ziel oder Stau)
        # =============================================================
        if not self.zub_queued:
            return self._check_queue(conn, sim_time)

        # =============================================================
        # PHASE 2: ZUB+ aussteigen lassen und losschicken (einmalig)
        # Reaktions-/Informationszeit: agent_reaction_time_s Sekunden
        # nach der Störung bevor der Agent losläuft (MA Kap. 3.3.1 /
        # AGBF-Analogie = 90 s).
        # =============================================================
        if not self.zub_dispatched:
            reaction_end = (self.activation_time
                            + self.config.agent_reaction_time_s)
            if sim_time < reaction_end:
                return False
            self._dispatch_zub(conn, sim_time)
            return False

        # =============================================================
        # PHASE 3: Ankunft prüfen
        # =============================================================
        return self._check_arrival(conn, sim_time)

    # ==================================================================
    # ZIEL-HALTESTELLE BESTIMMEN
    # ==================================================================

    def _set_target_stop(self, conn):
        """
        Bestimmt die letzte upcoming Haltestelle vor der Störung und
        setzt einen langen busStop darauf.

        Algorithmus:
          1. Hole verbleibende Route-Edges des ZUB+-Zuges.
          2. Finde Index des Störungs-Edges in dieser Liste.
          3. Iteriere upcoming Stops (getNextStops):
             wähle den LETZTEN, dessen Edge vor dem Störungs-Index liegt.
          4. setBusStop(zub_vehicle_id, stopID, duration=LONG_STOP_DURATION).
        """
        veh_id = self.zub_vehicle_id
        if veh_id not in conn.vehicle.getIDList():
            return

        # 1. Verbleibende Route-Edges + aktueller Edge-Index
        try:
            route_edges = list(conn.vehicle.getRoute(veh_id))
            curr_idx = conn.vehicle.getRouteIndex(veh_id)
        except Exception as e:
            print(f"[ZUB+] FEHLER getRoute/RouteIndex: {e}")
            return

        remaining = route_edges[curr_idx:]

        # 2. Index des Störungs-Edges im verbleibenden Pfad
        try:
            disrupt_idx = remaining.index(self._target_edge)
        except ValueError:
            # Störungs-Edge liegt nicht in der restlichen Route
            # (kann bei Route-Wiederholung vorkommen). Versuche nächste
            # Iteration — nicht jetzt setzen.
            print(f"[ZUB+] Störungs-Edge '{self._target_edge}' nicht in "
                  f"verbleibender Route ({len(remaining)} Edges). "
                  f"Versuche später.")
            return

        # 3. Upcoming Stops durchgehen
        try:
            next_stops = conn.vehicle.getStops(veh_id, 15)  # nur nächste 15
        except Exception as e:
            print(f"[ZUB+] FEHLER getStops: {e}")
            return

        # Felder: s.lane, s.endPos, s.stoppingPlaceID (neue API getStops)
        target_stop_id = None
        target_stop_edge = None
        target_stop_pos = None

        # ERSTE Closure-Haltestelle in der Restroute.
        # Die Closure-IDs decken beide Sperren ab (Störungsseite +
        # Gegenseite). Damit landet ein ZUB+-Zug, der auf der
        # Störungsseite hinter der Störung herfährt, automatisch an
        # der prev-Haltestelle (z.B. Höhenstraße Rück); ein ZUB+-Zug
        # auf dem Gegengleis landet an der opp-Haltestelle (z.B.
        # Merianplatz Hin) und kann von dort via Cross-Side-Walk auf
        # die Störungsseite wechseln.
        closure_set = set(self._closure_stop_ids)
        for s in next_stops:
            lane_id = s.lane
            end_pos = s.endPos
            stop_id = s.stoppingPlaceID
            if not lane_id or "_" not in lane_id or not stop_id:
                continue
            if closure_set and stop_id not in closure_set:
                continue
            edge = lane_id.rsplit("_", 1)[0]
            target_stop_id = stop_id
            target_stop_edge = edge
            target_stop_pos = end_pos
            break

        # Fallback (keine Closure-IDs gesetzt — z.B. wenn
        # _setup_track_closure nichts gefunden hat): alte Heuristik
        # "letzte Haltestelle vor disruption_edge in Restroute".
        if target_stop_id is None and not closure_set:
            for s in next_stops:
                lane_id = s.lane
                end_pos = s.endPos
                stop_id = s.stoppingPlaceID
                if not lane_id or "_" not in lane_id:
                    continue
                edge = lane_id.rsplit("_", 1)[0]
                try:
                    edge_idx = remaining.index(edge)
                except ValueError:
                    continue
                if edge_idx < disrupt_idx:
                    if stop_id:
                        target_stop_id = stop_id
                        target_stop_edge = edge
                        target_stop_pos = end_pos
                elif edge_idx >= disrupt_idx:
                    break

        if target_stop_id is None:
            print(f"[ZUB+] Keine geeignete Haltestelle gefunden — "
                  f"fallback: Aufstau.")
            # Als letzte Rettung: keine Haltestelle setzen, reiner Aufstau
            self.target_set = True
            return

        # 4. setBusStop mit langer Dauer
        try:
            conn.vehicle.setBusStop(
                vehID=veh_id,
                stopID=target_stop_id,
                duration=self.LONG_STOP_DURATION,
            )
        except Exception as e:
            print(f"[ZUB+] FEHLER setBusStop {target_stop_id}: {e}")
            return

        self._target_stop_id = target_stop_id
        self._target_stop_edge = target_stop_edge
        self._target_stop_pos = target_stop_pos
        self.target_set = True

        # Station-Name für Log
        stop_name = "?"
        for s in STATIONS:
            if s.stop_hin == target_stop_id or s.stop_rueck == target_stop_id:
                stop_name = s.name
                direction = "Hin" if s.stop_hin == target_stop_id else "Rück"
                stop_name = f"{s.name} ({direction})"
                break

        print(f"[ZUB+] Ziel-Haltestelle: {stop_name} "
              f"[stop={target_stop_id}, edge={target_stop_edge}, "
              f"pos={target_stop_pos:.1f}m] | setBusStop gesetzt")

    # ==================================================================
    # QUEUE-ERKENNUNG
    # ==================================================================

    def _check_queue(self, conn, sim_time: float) -> bool:
        """
        Prüft ob der ZUB+-Zug stehenbleibt — am Ziel, an einer Kaskaden-
        Sperrung (Haltestelle VOR dem Ziel mit 99999s-Halt) oder im Stau.

        Logik (Threshold-Auswahl):
          - Am Ziel (target_stop_edge erreicht): Threshold = 1 (sofort).
          - Cascade-Aufstau positiv erkannt (stehender Vorderzug innerhalb
            LEADER_LOOKAHEAD_M): Threshold = 1 (sofort).
          - Sonst: Threshold = QUEUE_STABLE_STEPS (60). Deckt Fahrplan-
            Halte (≤ 30 s) und Block-Halte ohne Vorderzug ab. Reguläre
            Halte zählen sich hoch, werden aber bei Wiederanfahrt
            zurückgesetzt.

        Cascade-Erkennung positiv statt negativ: ein stehender Zug ohne
        scheduled stop ist NICHT automatisch Aufstau (kann auch
        Bahnsteig-Einfahrt oder Block-Halt vor dem scheduled stop sein).
        Erst der stehende Vorderzug macht es zu echtem Aufstau.
        """
        veh_id = self.zub_vehicle_id

        if veh_id not in conn.vehicle.getIDList():
            return False

        speed = conn.vehicle.getSpeed(veh_id)
        if speed is None or speed >= self.QUEUE_SPEED_THRESHOLD:
            self._queue_counter = 0
            return False

        # Zug steht
        lane_id = conn.vehicle.getLaneID(veh_id)
        curr_edge = lane_id.rsplit("_", 1)[0] if lane_id and "_" in lane_id else None
        curr_pos = conn.vehicle.getLanePosition(veh_id)

        at_target = False
        if (self._target_stop_edge is not None
                and curr_edge == self._target_stop_edge
                and self._target_stop_pos is not None
                and abs(curr_pos - self._target_stop_pos) < self.TARGET_POS_TOL_M):
            at_target = True

        # Cascade-Erkennung positiv: stehender Vorderzug innerhalb
        # LEADER_LOOKAHEAD_M ist der direkte Stau-Indikator.
        cascade_detected = False
        leader_dbg: tuple[str, float] | None = None
        try:
            leader = conn.vehicle.getLeader(veh_id, self.LEADER_LOOKAHEAD_M)
        except Exception:
            leader = None
        if leader is not None:
            leader_id, leader_dist = leader
            if leader_id and leader_dist <= self.LEADER_LOOKAHEAD_M:
                try:
                    leader_speed = conn.vehicle.getSpeed(leader_id)
                except Exception:
                    leader_speed = None
                if (leader_speed is not None
                        and leader_speed < self.QUEUE_SPEED_THRESHOLD):
                    cascade_detected = True
                    leader_dbg = (leader_id, leader_dist)

        self._queue_counter += 1
        if at_target or cascade_detected:
            threshold = 1
        else:
            threshold = self.QUEUE_STABLE_STEPS

        if self._queue_counter < threshold:
            return False

        self.zub_queued = True
        self.queue_time = sim_time
        self._zub_exit_edge = curr_edge
        self._zub_exit_pos = curr_pos

        stop_state = conn.vehicle.getStopState(veh_id)
        at_scheduled_stop = (stop_state & 1) != 0
        if at_target:
            mode = "Ziel-Haltestelle"
        elif cascade_detected:
            lid, ldist = leader_dbg
            mode = f"Stau (cascade, Vorderzug {lid} @ {ldist:.1f}m)"
        elif at_scheduled_stop:
            mode = "Strecken-Halt (Sperrung)"
        else:
            mode = "Stau (Block-Halt)"

        t_queue = sim_time - self.activation_time
        print(f"[ZUB+] Zug {veh_id} steht ({mode}) nach {t_queue:.1f}s "
              f"| Edge: {curr_edge} | Pos: {curr_pos:.1f}m")

        return False

    # ==================================================================
    # AUSSTIEG + LAUF-ROUTE
    # ==================================================================

    @staticmethod
    def _side_of(edge: str) -> str | None:
        """Liefert 'hin' / 'rueck' / None je nachdem, in welcher Route-Liste
        der Edge liegt."""
        if edge in ROUTE_HIN_EDGES:
            return "hin"
        if edge in ROUTE_RUECK_EDGES:
            return "rueck"
        return None

    @staticmethod
    def _same_side_walk(from_edge: str, target_edge: str,
                        side: str) -> tuple[list[str] | None, str | None]:
        """Wählt für einen Same-Side-Walk die Richtung, die eine gültige
        Edge-Liste liefert (target_edge enthalten). Probiert beide Richtungen.

        Returns (walk_edges, direction) oder (None, None) wenn unmöglich.
        """
        for direction in (f"{side}_rechts", f"{side}_links"):
            walk = _compute_walk_route(from_edge, direction,
                                       target_edge=target_edge)
            if walk and target_edge in walk:
                return walk, direction
        return None, None

    @staticmethod
    def _walk_length_m(conn, walk_edges: list[str],
                       start_pos: float, arrival_pos: float,
                       is_reversed: bool = False) -> float:
        """Länge eines Walks entlang walk_edges von start_pos auf dem ersten
        Edge bis arrival_pos auf dem letzten Edge.

        is_reversed=True: Person läuft gegen die Edge-Richtung (pos fällt
        length→0 auf jedem Edge). Betrifft direction ∈
        {hin_links, rueck_rechts} — also die Fälle, in denen
        _compute_walk_route die Edge-Liste umkehrt.
        """
        if not walk_edges:
            return 0.0
        try:
            if len(walk_edges) == 1:
                if arrival_pos is not None and arrival_pos >= 0:
                    return max(0.0, abs(arrival_pos - (start_pos or 0.0)))
                return 0.0
            first_len = conn.lane.getLength(walk_edges[0] + "_0")
            if is_reversed:
                length = (start_pos or 0.0)
            else:
                length = first_len - (start_pos or 0.0)
            for e in walk_edges[1:-1]:
                length += conn.lane.getLength(e + "_0")
            last_len = conn.lane.getLength(walk_edges[-1] + "_0")
            if arrival_pos is not None and arrival_pos >= 0:
                if is_reversed:
                    length += max(0.0, last_len - arrival_pos)
                else:
                    length += arrival_pos
            else:
                length += last_len
            return max(length, 0.0)
        except Exception:
            return 0.0

    def _dispatch_zub(self, conn, sim_time: float):
        """ZUB+ aussteigen lassen, ggf. Seite wechseln und losschicken.

        ZUB+ bleibt im Startzug bis zur Closure-Haltestelle in
        Fahrtrichtung. Anschließend entweder Same-Side-Walk (Closure
        liegt auf Störungsseite) oder Cross-Side mit Bahnsteig-
        seitenwechsel via <access> (Closure liegt auf Gegenseite).

          * Same-Side (from_side == to_side) → statische Edge-Liste,
            Richtung wird automatisch gewählt (rechts oder links).
          * Cross-Side (from_side != to_side) → findIntermodalRoute auf
            den Cross-Stop überquert die Bahnsteig-Unterführung
            (<access>), danach Same-Side-Walk auf der Störungsseite bis
            zum gestörten Zug.

        Person wird hier frisch an der aktuellen Zug-Position auf der
        Parallelweg-Lane erzeugt (vorher existiert keine Person — siehe
        create_zub_person). Danach werden die Walk-Stages angehängt.
        """
        self.zub_dispatched = True
        self.dispatch_time = sim_time
        from_edge = self._zub_exit_edge
        from_pos = self._zub_exit_pos
        target_edge = self._target_edge
        target_pos = self._target_pos

        if from_edge is None:
            print(f"[ZUB+] FEHLER: Kein Edge für ZUB+-Position!")
            return

        # Clamp: findIntermodalRoute / appendWalkingStage akzeptieren departPos
        # nur strikt kleiner als die Edge-Länge. Steht der Zug exakt am Edge-Ende
        # (z.B. Bus-Stop endPos == edge_length wie BW Rück 159.03m), liefert
        # getLanePosition den Edge-Längenwert und SUMO weist die Route ab.
        try:
            edge_len = conn.lane.getLength(from_edge + "_0")
            if from_pos is not None and from_pos >= edge_len:
                from_pos = max(0.0, edge_len - 0.01)
                self._zub_exit_pos = from_pos
        except Exception:
            pass

        from_side = self._side_of(from_edge)
        to_side = self._side_of(target_edge)

        if from_side is None:
            print(f"[ZUB+] FEHLER: Start-Edge {from_edge} nicht in Route-Listen!")
            return
        if to_side is None:
            print(f"[ZUB+] FEHLER: Ziel-Edge {target_edge} nicht in Route-Listen!")
            return

        # Person frisch an Zug-Position erzeugen (Parallelweg-Lane wird
        # von SUMO automatisch gewählt, da Lane 0 dem Zug gehört).
        # depart=sim_time: explizit jetzt. Default (-3) steht in TraCI fuer
        # TRIGGERED und laesst die Person stumm verschwinden, wenn danach
        # nur Walk-Stages angehaengt werden (kein Fahrzeug-Trigger).
        try:
            conn.person.add(
                personID=self.person_id,
                edgeID=from_edge,
                pos=from_pos,
                depart=sim_time,
                typeID="ZUB_PED",
            )
        except Exception as e:
            print(f"[ZUB+] FEHLER person.add {from_edge}@{from_pos:.1f}: "
                  f"{type(e).__name__}: {e}")
            self._dispatch_failed = True
            return

        stages_info: list[tuple[list[str], float]] = []  # (edges, arrival_pos)
        route_length_m = 0.0
        direction_log = "?"

        if from_side == to_side:
            # ------------------------------------------------------------------
            # SAME SIDE — statische Route-Liste, Direction auto-detect
            # ------------------------------------------------------------------
            walk_edges, direction = self._same_side_walk(from_edge, target_edge, from_side)
            if not walk_edges:
                print(f"[ZUB+] FEHLER: Keine Same-Side-Walk-Route "
                      f"{from_edge} → {target_edge} (side={from_side})!")
                return
            direction_log = direction
            arrival_pos = target_pos
            route_length_m = self._walk_length_m(
                conn, walk_edges, from_pos, arrival_pos,
                is_reversed=direction in ("hin_links", "rueck_rechts"))
            stages_info.append((walk_edges, arrival_pos))

        else:
            # ------------------------------------------------------------------
            # CROSS SIDE — Zwei Phasen:
            # Phase A: findIntermodalRoute(from_edge → Target-Seite der
            #          Cross-Station), nutzt <access>-Brücke am aktuellen
            #          Stop. Liefert Walk+Access bis zum Target-Bahnsteig.
            # Phase B: Same-Side-Walk vom Cross-Edge (Target-Seite) zum
            #          target_edge entlang des Gleiskörpers.
            #
            # Grund: findIntermodalRoute(Hin→Rück über große Distanz) liefert
            # oft keinen Access-Walk, sondern eine disconnect Edge-Kette.
            # Phase A begrenzt den Intermodal-Teil auf den Access-Hop an
            # einer einzelnen Station.
            # ------------------------------------------------------------------
            cross_station = None
            if self._target_stop_id:
                for st in STATIONS:
                    if self._target_stop_id in (st.stop_hin, st.stop_rueck):
                        cross_station = st
                        break
            else:
                # Reiner Aufstau ohne gesetztes target_stop_id: Cross-Station
                # mit MINIMALEM Gesamtweg wählen (Phase A on from_side +
                # Phase B on to_side). from_edge-Match alleine ist falsch,
                # weil u4_10 zwischen zwei Stationen aufstauen kann und
                # der Match dann die geometrisch nächste Station liefert,
                # nicht die zielnächste.
                best_total = float("inf")
                for st in STATIONS:
                    if from_side == "hin":
                        a_to_edge = st.edge_hin
                        a_to_pos = st.stop_pos_hin
                    else:
                        a_to_edge = st.edge_rueck
                        a_to_pos = st.stop_pos_rueck
                    a_edges, a_dir = self._same_side_walk(
                        from_edge, a_to_edge, from_side)
                    if not a_edges:
                        continue
                    a_len = self._walk_length_m(
                        conn, a_edges, from_pos, a_to_pos,
                        is_reversed=a_dir in ("hin_links", "rueck_rechts"))
                    if to_side == "hin":
                        b_from_edge = st.edge_hin
                        b_from_pos = st.stop_pos_hin
                    else:
                        b_from_edge = st.edge_rueck
                        b_from_pos = st.stop_pos_rueck
                    b_edges, b_dir = self._same_side_walk(
                        b_from_edge, target_edge, to_side)
                    if not b_edges:
                        continue
                    b_len = self._walk_length_m(
                        conn, b_edges, b_from_pos, target_pos,
                        is_reversed=b_dir in ("hin_links", "rueck_rechts"))
                    total = a_len + b_len
                    if total < best_total:
                        best_total = total
                        cross_station = st
                if cross_station is not None:
                    print(f"[ZUB+] Aufstau-Fallback: Cross-Station per "
                          f"minimalem Gesamtweg "
                          f"({best_total:.0f}m) → {cross_station.name}")
            if cross_station is None:
                print(f"[ZUB+] FEHLER: Keine Cross-Station für target_stop_id="
                      f"{self._target_stop_id}, from_edge={from_edge}")
                self._dispatch_failed = True
                return

            if to_side == "rueck":
                cross_edge_ts = cross_station.edge_rueck
                cross_pos_ts = cross_station.stop_pos_rueck
            else:
                cross_edge_ts = cross_station.edge_hin
                cross_pos_ts = cross_station.stop_pos_hin

            # Phase A: Access-Hop an der Cross-Station
            try:
                cross_stages = conn.simulation.findIntermodalRoute(
                    fromEdge=from_edge, toEdge=cross_edge_ts,
                    depart=0.0, departPos=from_pos, arrivalPos=cross_pos_ts,
                    walkFactor=1.0,
                    speed=self.config.agent_walk_speed_ms,
                    modes="",
                )
            except Exception as e:
                print(f"[ZUB+] FEHLER findIntermodalRoute Phase A: {e}")
                self._dispatch_failed = True
                return

            # findIntermodalRoute liefert Access implizit als destStop-Walk
            # (Stage-type=2, NICHT type=4). Wir erkennen gültigen Access-Hop
            # an: mindestens eine Walking-Stage mit gesetztem destStop
            # (== Ziel-Haltestelle mit <access>-Element).
            has_deststop = any(getattr(s, "destStop", "") for s in cross_stages)
            if not cross_stages or not has_deststop:
                stage_info = [
                    f"type={getattr(s, 'type', '?')} "
                    f"len={getattr(s, 'length', 0):.1f} "
                    f"destStop={getattr(s, 'destStop', '')!r} "
                    f"n_edges={len(getattr(s, 'edges', []))}"
                    for s in (cross_stages or [])
                ]
                print(f"[ZUB+] FEHLER: Phase A ohne destStop-Walk "
                      f"(stages={len(cross_stages) if cross_stages else 0}: "
                      f"{stage_info}) — Szenario unroutbar.")
                self._dispatch_failed = True
                return

            # Phase B: Same-Side-Walk auf Target-Seite
            phase_b_edges, direction = self._same_side_walk(
                cross_edge_ts, target_edge, to_side)
            if not phase_b_edges:
                print(f"[ZUB+] FEHLER: Phase B Same-Side-Walk "
                      f"{cross_edge_ts} → {target_edge} (side={to_side}) "
                      f"fehlgeschlagen.")
                self._dispatch_failed = True
                return

            direction_log = f"cross via {cross_station.name} ({direction})"
            self._cross_stages = cross_stages
            route_length_m = sum(getattr(s, "length", 0.0) for s in cross_stages)
            route_length_m += self._walk_length_m(
                conn, phase_b_edges, cross_pos_ts, target_pos,
                is_reversed=direction in ("hin_links", "rueck_rechts"))
            stages_info.append((phase_b_edges, target_pos))

        is_cross = (from_side != to_side)
        if not is_cross and not stages_info:
            print(f"[ZUB+] FEHLER: Keine Walk-Stages ermittelt.")
            return

        # Stages an die frisch erzeugte Person anhängen.
        # Cross-Side: Phase A (Walk+Access) voranstellen; Phase B
        # (Same-Side-Walk) kommt anschließend aus stages_info.
        n_stages_appended = 0
        if is_cross:
            for cs in cross_stages:
                conn.person.appendStage(self.person_id, cs)
                n_stages_appended += 1
        for edges, arr_pos in stages_info:
            conn.person.appendWalkingStage(
                personID=self.person_id,
                edges=edges,
                arrivalPos=arr_pos,
            )
            n_stages_appended += 1

        conn.person.setSpeed(self.person_id, self.config.agent_walk_speed_ms)

        last_edges, last_arr = stages_info[-1]
        self._arrival_edge = last_edges[-1]
        self._arrival_pos = last_arr
        self.route_length_m = route_length_m
        self.route_cost_s = route_length_m / self.config.agent_walk_speed_ms

        print(f"[ZUB+] Ausgestiegen & losgelaufen | "
              f"Von: {from_edge}@{from_pos:.1f}m "
              f"→ {target_edge}@{target_pos:.1f}m "
              f"| sides: {from_side}→{to_side} ({direction_log}) "
              f"| stages: {n_stages_appended} "
              f"| Route: {self.route_length_m:.1f}m "
              f"({self.route_cost_s:.1f}s) "
              f"| v = {self.config.agent_walk_speed_ms:.2f} m/s")
        self._verify_person_next_step = True

        # GUI-Tracking: Kamera folgt dem ZUB+ (nur wenn GUI aktiv und
        # traci.gui verfuegbar). Damit ist er automatisch im Bild.
        try:
            view_id = conn.gui.DEFAULT_VIEW  # 'View #0'
            conn.gui.trackVehicle(view_id, "")  # Tracking loesen
            # Zoom auf 50 m Sichtfeld — Person (5 m breit) ~10 % der Breite
            x, y = conn.simulation.convert2D(from_edge, from_pos)
            conn.gui.setOffset(view_id, x, y)
            conn.gui.setZoom(view_id, 3500)
            print(f"[ZUB+ GUI] Kamera auf ({x:.0f},{y:.0f}), Zoom=3500")
        except Exception as e:
            pass  # Kein GUI (headless) → ignorieren

    # ==================================================================
    # ENTFERNT: Pfad B (Zugumstieg)
    #
    # Frühere MA-Erweiterung "Variante O" mit appendDrivingStage. ZUB+
    # darf laut MA-Definition nicht in einen anderen Zug einsteigen,
    # daher gibt es nur noch das einfache Verhalten in _dispatch_zub:
    # an Closure-Station aussteigen → ggf. Seite wechseln → laufen.
    # ==================================================================

    def _check_arrival(self, conn, sim_time: float) -> bool:
        """Prüft ob die ZUB+-Person am gestörten Zug angekommen ist."""
        if self.person_id not in conn.person.getIDList():
            # Person ist aus der Sim — Walking-Stage abgeschlossen, keine
            # weiteren Stages (siehe removeStage-Aufrufe in _dispatch_zub).
            # Da wir nur nach Dispatch hier landen, werten wir das als
            # Ankunft am Ziel (Fallback für Edge-Fälle wie internal edges
            # oder Position direkt am Walk-Ende, die der Positions-Check
            # darunter sonst verpasst).
            if self.zub_dispatched and not self.zub_arrived:
                self.zub_arrived = True
                self.arrival_time = sim_time
                t_queue = self.queue_time - self.activation_time
                t_walk = sim_time - self.dispatch_time
                t_total = sim_time - self.activation_time
                print(f"[ZUB+] Angekommen (Person-Stage beendet)! "
                      f"| t_queue: {t_queue:.1f}s "
                      f"| t_walk: {t_walk:.1f}s "
                      f"| t_total: {t_total:.1f}s")
                return True
            return False

        edge = conn.person.getRoadID(self.person_id)
        pos = conn.person.getLanePosition(self.person_id)

        check_edge = self._arrival_edge or self._target_edge
        check_pos = (self._arrival_pos
                     if self._arrival_pos is not None
                     else self._target_pos)

        # Ankunft: (a) reguläre Ziel-Edge mit Positions-Check, ODER
        # (b) beim Junction-Fall die originale internal edge — dort steht
        # der Zug tatsächlich, der Agent durchquert sie auf dem Walk.
        arrived = False
        if check_edge and edge == check_edge:
            if check_pos == -1 or abs(pos - check_pos) < 5.0:
                arrived = True
        elif self._target_internal_edge and edge == self._target_internal_edge:
            arrived = True

        if arrived:
            self.zub_arrived = True
            self.arrival_time = sim_time

            t_queue = self.queue_time - self.activation_time
            t_walk = sim_time - self.dispatch_time
            t_total = sim_time - self.activation_time

            print(f"[ZUB+] Angekommen! "
                  f"| t_queue: {t_queue:.1f}s "
                  f"| t_walk: {t_walk:.1f}s "
                  f"| t_total: {t_total:.1f}s")
            return True

        return False

    # ==================================================================
    # ERGEBNISSE
    # ==================================================================

    def get_results(self) -> dict:
        """Gibt Messergebnisse als Dictionary zurück."""
        t_queue = t_walk = t_total = None

        if self.queue_time and self.activation_time:
            t_queue = self.queue_time - self.activation_time
        if self.arrival_time and self.dispatch_time:
            t_walk = self.arrival_time - self.dispatch_time
        if self.arrival_time and self.activation_time:
            t_total = self.arrival_time - self.activation_time

        return {
            "zub_vehicle_id": self.zub_vehicle_id,
            "gap": self.gap,
            # CSV-Spalte "path" ist konstant "A" — das ehemalige Pfad-B
            # (Zugumstieg) ist nicht mehr Teil des Modells. Spalte bleibt
            # nur aus Backwards-Compat-Gründen erhalten.
            "path": "A",
            "t_queue_s": t_queue,
            "t_walk_s": t_walk,
            "t_intervention_total_s": t_total,
            "zub_exit_edge": self._zub_exit_edge,
            "zub_exit_pos": self._zub_exit_pos,
            "target_stop_id": self._target_stop_id,
            "target_stop_edge": self._target_stop_edge,
            "target_stop_pos": self._target_stop_pos,
            "route_cost_s": self.route_cost_s,
            "route_length_m": self.route_length_m,
        }
