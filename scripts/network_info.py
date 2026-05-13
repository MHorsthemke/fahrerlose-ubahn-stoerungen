"""
network_info.py — Streckeninformationen aus SUMO-XMLs parsen.

ZWECK:
    Dieses Modul liest die drei XML-Dateien (Netz, Haltestellen, Route)
    und baut daraus ein NetworkInfo-Objekt, das die "Landkarte" der Strecke
    enthält: Umlauflänge, Haltestellenabstände, Edge-Mapping.

    Beispiel: Wenn wir wissen wollen "wo ist Meter 5000 auf dem Umlauf?",
    kann NetworkInfo.position_to_edge(5000) antworten: "Edge XY, Offset 120m".

DATENQUELLEN:
    - osm.net.xml.gz    → Netzwerk (Edges, Lanes, Connections mit Längen)
    - osm_stops.add.xml  → Haltestellen (Namen, Positionen auf Lanes)
    - route_u4_long.rou.xml → Route (Edge-Reihenfolge, CycleTime, Stops)

HERKUNFT DER LOGIK:
    Die Funktionen _read_lane_lengths() und _read_connection_vias() sind
    aus dem bestehenden RouteLengthProvider in TraCI_control.py übernommen.
"""

import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


# =============================================================================
# Datenklassen — beschreiben die Strecke
# =============================================================================

@dataclass
class StopInfo:
    """
    Eine Haltestelle mit ihrer Position auf dem Umlauf.

    Beispiel:
        StopInfo(stop_id="2682026529", name="Festhalle/Messe",
                 lane="60734091#1_0", edge="60734091#1",
                 start_pos=809.55, end_pos=919.55, center_pos=864.55,
                 dist_on_route_m=1200.0)

    dist_on_route_m ist die kumulative Distanz ab dem Startpunkt der Route.
    Das ist der wichtigste Wert — damit wissen wir WO auf dem Umlauf
    diese Haltestelle liegt.
    """
    stop_id: str            # SUMO busStop-ID (z.B. "2682026529")
    name: str               # Menschenlesbarer Name (z.B. "Festhalle/Messe")
    lane: str               # SUMO Lane-ID (z.B. "60734091#1_0")
    edge: str               # SUMO Edge-ID (= Lane ohne "_0" am Ende)
    start_pos: float        # Startposition der Haltestelle auf dem Edge (m)
    end_pos: float          # Endposition der Haltestelle auf dem Edge (m)
    center_pos: float       # Mitte der Haltestelle auf dem Edge (m)
    dist_on_route_m: float = 0.0  # Kumulative Distanz ab Routenstart (m)


@dataclass
class EdgeInfo:
    """
    Ein Edge (Streckenabschnitt) der Route mit seiner Position auf dem Umlauf.

    In SUMO besteht die Route aus vielen Edges hintereinander.
    start_m und end_m geben an, wo dieser Edge auf dem Gesamtumlauf liegt.

    Beispiel:
        EdgeInfo(edge_id="-60734138#3", length_m=150.0,
                 start_m=0.0, end_m=150.0)
        → Dieser Edge geht von Meter 0 bis Meter 150 auf dem Umlauf.
    """
    edge_id: str            # SUMO Edge-ID
    length_m: float         # Länge dieses Edges in Metern
    start_m: float = 0.0   # Kumulative Startposition auf dem Umlauf (m)
    end_m: float = 0.0     # Kumulative Endposition auf dem Umlauf (m)


@dataclass
class NetworkInfo:
    """
    Hauptobjekt: Enthält alle Streckeninformationen.

    Wird einmal am Anfang gebaut (durch build_network_info()) und dann
    von allen anderen Modulen verwendet.
    """
    route_id: str                   # ID der Route (z.B. "r_0" oder "r_1")
    route_edges: list[str]          # Liste aller Edge-IDs in Reihenfolge
    route_length_m: float           # Gesamtlänge des Umlaufs in Metern
    cycle_time_s: float             # Umlaufzeit in Sekunden (aus cycleTime)
    repeat: int                     # Wie oft wird der Umlauf wiederholt

    edges: list[EdgeInfo]           # Alle Edges mit Positionen
    stops: list[StopInfo]           # Alle Haltestellen in Reihenfolge

    # Schnellzugriff per ID (werden automatisch befüllt)
    edge_by_id: dict[str, EdgeInfo] = field(default_factory=dict, repr=False)
    stop_by_id: dict[str, StopInfo] = field(default_factory=dict, repr=False)

    def position_to_edge(self, distance_m: float) -> tuple[str, float]:
        """
        Rechnet eine Position auf dem Umlauf (in Metern) in (edge_id, offset) um.

        Beispiel:
            position_to_edge(5000.0) → ("-60734138#3", 120.0)
            Bedeutet: Meter 5000 liegt auf Edge "-60734138#3", 120m nach dessen Anfang.

        Das brauchen wir um die Störungsposition (z.B. "5000m") in SUMO-Koordinaten
        umzurechnen.
        """
        for e in self.edges:
            if e.start_m <= distance_m < e.end_m:
                return e.edge_id, distance_m - e.start_m
        # Falls exakt am Ende des letzten Edges
        last = self.edges[-1]
        return last.edge_id, last.length_m

    def nearest_stop(self, distance_m: float) -> StopInfo:
        """
        Findet die nächste Haltestelle zu einer gegebenen Position auf dem Umlauf.

        Berücksichtigt auch den Wrap-Around (Umlauf ist ein Kreis):
        Wenn die Störung bei Meter 100 ist und die letzte Haltestelle bei Meter 18000,
        könnte diese trotzdem die nächste sein (über den Wrap-Around).
        """
        best = None
        best_dist = float("inf")
        for s in self.stops:
            # Direkte Distanz
            d = abs(s.dist_on_route_m - distance_m)
            # Distanz über den Umlauf-Wrap (Rundkurs!)
            d_wrap = self.route_length_m - d
            d_min = min(d, d_wrap)
            if d_min < best_dist:
                best_dist = d_min
                best = s
        return best

    def print_summary(self):
        """Gibt eine Zusammenfassung der Strecke auf der Konsole aus."""
        print(f"Route:           {self.route_id}")
        print(f"Umlauflänge:     {self.route_length_m:.1f} m")
        print(f"Cycle Time:      {self.cycle_time_s:.1f} s")
        print(f"Repeat:          {self.repeat}")
        print(f"Edges:           {len(self.edges)}")
        print(f"Haltestellen:    {len(self.stops)}")
        print()
        print("Haltestellen:")
        for i, s in enumerate(self.stops):
            dist_to_next = ""
            if i < len(self.stops) - 1:
                d = self.stops[i + 1].dist_on_route_m - s.dist_on_route_m
                dist_to_next = f"  → nächste: {d:.0f} m"
            print(f"  {s.name:30s}  {s.dist_on_route_m:8.1f} m{dist_to_next}")


# =============================================================================
# Interne Hilfsfunktionen — lesen die XML-Dateien
# =============================================================================

def _open_maybe_gzip(path: Path):
    """Öffnet eine Datei, egal ob .gz komprimiert oder nicht."""
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return open(path, "rb")


def _read_lane_lengths(net_path: Path) -> dict[str, float]:
    """
    Liest ALLE Lane-Längen aus dem Netzwerk.

    SUMO-Netzwerke bestehen aus Edges, und jeder Edge hat eine oder mehrere Lanes.
    Jede Lane hat eine Länge in Metern. Wir brauchen die Länge von Lane _0
    (der ersten Lane) jedes Edges, um die Routenlänge zu berechnen.

    Herkunft: Übernommen aus RouteLengthProvider._read_lane_lengths_from_net()

    Returns:
        Dict: lane_id → Länge in Metern
        Beispiel: {"60734091#1_0": 920.5, "60734091#1_1": 920.5, ...}
    """
    lane_len: dict[str, float] = {}
    with _open_maybe_gzip(net_path) as f:
        # iterparse liest die XML Stück für Stück (speicherschonend für große Netze)
        for _, elem in ET.iterparse(f, events=("end",)):
            if elem.tag == "lane":
                lane_id = elem.attrib.get("id")
                length_str = elem.attrib.get("length")
                if lane_id and length_str:
                    lane_len[lane_id] = float(length_str)
            elem.clear()  # Speicher freigeben
    return lane_len


def _read_connection_vias(net_path: Path) -> dict[tuple[str, str], str]:
    """
    Liest die internen Verbindungs-Lanes zwischen Edges.

    In SUMO gibt es an Kreuzungen/Weichen "interne Lanes" (via-Lanes),
    die zwei Edges verbinden. Diese haben auch eine Länge, die zur
    Gesamtroutenlänge beiträgt.

    Herkunft: Übernommen aus RouteLengthProvider._read_connections_via_from_net()

    Returns:
        Dict: (from_edge, to_edge) → via_lane_id
        Beispiel: {("-60734138#3", "-60734139"): ":cluster_123_0"}
    """
    best: dict[tuple[str, str], tuple[int, str]] = {}
    with _open_maybe_gzip(net_path) as f:
        for _, elem in ET.iterparse(f, events=("end",)):
            if elem.tag == "connection":
                fr = elem.attrib.get("from")
                to = elem.attrib.get("to")
                via = elem.attrib.get("via")
                if fr and to and via:
                    from_lane = elem.attrib.get("fromLane", "")
                    to_lane = elem.attrib.get("toLane", "")
                    # Bevorzuge Lane 0 (Hauptfahrspur)
                    score = (1 if from_lane == "0" else 0) + (1 if to_lane == "0" else 0)
                    key = (fr, to)
                    if key not in best or score > best[key][0]:
                        best[key] = (score, via)
            elem.clear()
    return {k: v[1] for k, v in best.items()}


def _read_stops(stops_path: Path) -> dict[str, StopInfo]:
    """
    Liest alle Haltestellen aus der additional-Datei (osm_stops.add.xml).

    Jede Haltestelle hat eine ID, einen Namen, eine Lane und eine Start-/Endposition
    auf dieser Lane. Wir berechnen daraus die Mitte (center_pos).

    Returns:
        Dict: stop_id → StopInfo
    """
    stops: dict[str, StopInfo] = {}
    tree = ET.parse(stops_path)
    root = tree.getroot()
    for bs in root.findall(".//busStop"):
        stop_id = bs.attrib["id"]
        name = bs.attrib.get("name", stop_id)
        lane = bs.attrib["lane"]
        # Edge-ID = Lane-ID ohne den letzten Teil ("_0", "_1" etc.)
        edge = lane.rsplit("_", 1)[0]
        start_pos = float(bs.attrib.get("startPos", 0))
        end_pos = float(bs.attrib.get("endPos", 0))
        center_pos = (start_pos + end_pos) / 2.0
        stops[stop_id] = StopInfo(
            stop_id=stop_id, name=name, lane=lane, edge=edge,
            start_pos=start_pos, end_pos=end_pos, center_pos=center_pos,
        )
    return stops


def _read_route(route_path: Path, route_id: str = None) -> tuple[str, list[str], float, int, list[str]]:
    """
    Liest eine Route aus der rou.xml-Datei.

    Eine Route besteht aus:
    - edges: Liste der Edges die der Zug durchfährt (der Fahrweg)
    - cycleTime: Umlaufzeit in Sekunden
    - repeat: Wie oft wird der Umlauf wiederholt
    - stops: An welchen Haltestellen hält der Zug (in Reihenfolge)

    Args:
        route_path: Pfad zur rou.xml
        route_id: Falls mehrere Routen existieren, welche soll gelesen werden.
                  None = nimmt die erste.

    Returns:
        Tuple: (route_id, edge_list, cycle_time, repeat, stop_ids_in_order)
    """
    tree = ET.parse(route_path)
    root = tree.getroot()

    for r in root.findall(".//route"):
        rid = r.attrib.get("id")
        # Falls eine bestimmte Route gewünscht: andere überspringen
        if route_id is not None and rid != route_id:
            continue

        edges_str = r.attrib.get("edges", "")
        edges = edges_str.strip().split()
        cycle_time = float(r.attrib.get("cycleTime", 0))
        repeat = int(float(r.attrib.get("repeat", 0)))

        # Haltestellenreihenfolge: in welcher Reihenfolge hält der Zug?
        stop_ids = []
        for stop in r.findall("stop"):
            stop_ids.append(stop.attrib["busStop"])

        return rid, edges, cycle_time, repeat, stop_ids

    raise ValueError(f"Route '{route_id}' nicht gefunden in {route_path}")


# =============================================================================
# Hauptfunktion — baut das NetworkInfo-Objekt zusammen
# =============================================================================

def build_network_info(
    net_path: Path,
    stops_path: Path,
    route_path: Path,
    route_id: str = None,
) -> NetworkInfo:
    """
    Hauptfunktion: Baut ein NetworkInfo-Objekt aus den SUMO-XMLs.

    Ablauf:
    1. Route lesen (Edge-Liste, CycleTime, Stops)
    2. Lane-Längen und Connections aus dem Netz lesen
    3. Für jeden Edge: kumulative Distanz berechnen (inkl. Via-Lanes)
    4. Für jede Haltestelle: Position auf dem Umlauf berechnen
    5. Alles in ein NetworkInfo-Objekt packen

    Args:
        net_path: Pfad zum Netzwerk (osm.net.xml.gz)
        stops_path: Pfad zu den Haltestellen (osm_stops.add.xml)
        route_path: Pfad zur Route (route_u4_long.rou.xml)
        route_id: Optional — welche Route (falls mehrere existieren)

    Returns:
        NetworkInfo-Objekt mit allen Streckeninformationen
    """
    # 1. Route lesen
    rid, route_edges, cycle_time, repeat, stop_ids_in_order = _read_route(route_path, route_id)

    # 2. Lane-Längen und Connections aus Netz
    lane_len = _read_lane_lengths(net_path)
    conn_via = _read_connection_vias(net_path)

    # 3. Edge-Infos mit kumulativer Distanz berechnen
    #    Wir gehen Edge für Edge durch und addieren die Längen auf.
    #    Zwischen zwei Edges gibt es oft eine Via-Lane (interne Verbindung),
    #    deren Länge auch dazukommt.
    edges: list[EdgeInfo] = []
    cumulative = 0.0
    for i, edge_id in enumerate(route_edges):
        # Lane _0 ist die Hauptfahrspur — deren Länge nehmen wir
        lane0 = f"{edge_id}_0"
        length = lane_len.get(lane0, 0.0)

        ei = EdgeInfo(edge_id=edge_id, length_m=length,
                      start_m=cumulative, end_m=cumulative + length)
        edges.append(ei)
        cumulative += length

        # Via-Lane zum nächsten Edge (interne Verbindung an Weichen/Kreuzungen)
        if i < len(route_edges) - 1:
            via_key = (edge_id, route_edges[i + 1])
            via_lane = conn_via.get(via_key)
            if via_lane:
                via_len = lane_len.get(via_lane, 0.0)
                cumulative += via_len

    route_length_m = cumulative

    # 4. Haltestellen: Position auf dem Umlauf berechnen
    #    Jede Haltestelle liegt auf einem bestimmten Edge.
    #    Ihre Position auf dem Umlauf = Start des Edges + Position auf dem Edge.
    all_stops = _read_stops(stops_path)
    edge_info_by_id = {e.edge_id: e for e in edges}

    stops_on_route: list[StopInfo] = []
    for stop_id in stop_ids_in_order:
        if stop_id not in all_stops:
            print(f"Warnung: Haltestelle {stop_id} nicht in stops-Datei gefunden")
            continue
        s = all_stops[stop_id]
        ei = edge_info_by_id.get(s.edge)
        if ei is not None:
            # Position auf Umlauf = Wo der Edge anfängt + Wo die Haltestelle auf dem Edge liegt
            s.dist_on_route_m = ei.start_m + s.center_pos
        else:
            print(f"Warnung: Edge {s.edge} von Haltestelle {s.name} nicht in Route")
        stops_on_route.append(s)

    # 5. NetworkInfo zusammenbauen
    info = NetworkInfo(
        route_id=rid,
        route_edges=route_edges,
        route_length_m=route_length_m,
        cycle_time_s=cycle_time,
        repeat=repeat,
        edges=edges,
        stops=stops_on_route,
        edge_by_id=edge_info_by_id,
        stop_by_id={s.stop_id: s for s in stops_on_route},
    )

    return info


# =============================================================================
# Standalone-Ausführung: Basisdaten auf der Konsole ausgeben
# =============================================================================
# Kannst du ausführen mit: python network_info.py
# Braucht kein laufendes SUMO — liest nur die XML-Dateien.

if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1]  # sumo-masterarbeit/

    info = build_network_info(
        net_path=base / "network" / "osm.net.xml.gz",
        stops_path=base / "network" / "osm_stops.add.xml",
        route_path=base / "routes" / "route_u4_long.rou.xml",
    )

    info.print_summary()
