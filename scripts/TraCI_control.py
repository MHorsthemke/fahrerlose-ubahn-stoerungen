# Infos gibt es hier: https://sumo.dlr.de/docs/TraCI/Interfacing_TraCI_from_Python.html

### 1. Importe
import os
import sys
import csv
import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import traci
import traci.constants as tc

### 2. Daten
@dataclass
class ScenarioConfig:
    # step_length steuert den SUMO Zeitschritt. Ein Schritt =  1.0 Sekunde ist Standart -> ändert die Sumoschrittgröße in der Simulation, ampassbar wenn notwendig
    step_length_s: float = 1.0 

    # CSV-Ausgabe — Pfad wird absolut berechnet, damit es egal ist von wo man startet
    csv_out_path: Path = Path(__file__).resolve().parents[1] / "output" / "traci_log.csv"
    csv_delimiter: str = ";"

    #Lapcounter-data
    lap_start_edge_id: str ="-60734138#3"    #edge_id von der "Startlane BW"
    lap_end_edge_id: str = "60734138#3"      #Edge_id der Endedge der Lap an der BW
    lap_speed_eps: float = 0.10              # "steht" wenn v <= 0.10 m/s
    lap_cols_fallback: int = 10  # falls im route-file kein repeat steht

    #Traci Variablen die getrackt werden
    VARS_to_track: tuple = (
        tc.VAR_SPEED, 
        tc.VAR_ACCELERATION,
        tc.VAR_DISTANCE,
        tc.VAR_POSITION,
        tc.VAR_TIMELOSS,
        tc.VAR_LANE_ID,          
        tc.VAR_LANEPOSITION)

@dataclass
class ProjektConfig:
    sumocfg_path: Path = Path(__file__).resolve().parents[1] / "config" / "osm.sumocfg"
    sumo_gui_exe: Path | None = None

### 3. sumocfg lesen und Pfade auflösen
# Lädt net-file und route-files aus der sumocfg
class SumoProjekt:
    def __init__(self, projekt_cfg: ProjektConfig):
        self.sumocfg_path: Path = projekt_cfg.sumocfg_path
        self.base_dir: Path = self.sumocfg_path.parent
        self.sumo_gui_exe: Path = self._default_sumo_gui_exe()
        self.net_path, self.route_path = self._parse_sumocfg_inputs(self.sumocfg_path)

    def _default_sumo_gui_exe(self) -> Path:
        sumo_home = os.environ.get("SUMO_HOME")
        if not sumo_home:
            raise RuntimeError("SUMO_HOME ist nicht gesetzt.")

        use_gui_env = os.environ.get("SUMO_USE_GUI")
        use_gui = True if use_gui_env is None else (use_gui_env == "1")

        exe_name = "sumo-gui" if use_gui else "sumo"
        exe = Path(sumo_home) / "bin" / exe_name
        if sys.platform.startswith("win"):
            exe = exe.with_suffix(".exe")

        if not exe.exists():
            raise FileNotFoundError(f"SUMO Binary nicht gefunden: {exe}")

        return exe

    def _parse_sumocfg_inputs(self, sumocfg_path: Path) -> tuple[Path, Path]:
        tree = ET.parse(sumocfg_path)
        root = tree.getroot()

        # In sumocfg sind die Werte typischerweise relativ zur sumocfg-Datei.
        net_value = root.find("./input/net-file").attrib["value"]
        route_value = root.find("./input/route-files").attrib["value"]

        net_path = (self.base_dir / net_value).resolve()
        route_path = (self.base_dir / route_value).resolve()

        return net_path, route_path

### 4. Routenlängen berechnen
class RouteLengthProvider:
    def __init__(self, net_path: Path, route_path: Path):
        self.net_path = net_path
        self.route_path = route_path

    def build(self) -> dict[str, float]:
        lane_len_m = self._read_lane_lengths_from_net(self.net_path)
        conn_via_lane = self._read_connections_via_from_net(self.net_path)
        routes_edges = self._read_routes_from_rou(self.route_path)
        route_len_m = self._compute_route_lengths(routes_edges, lane_len_m, conn_via_lane)
        return route_len_m

    def _open_maybe_gzip(self, path: Path):
        if path.suffix == ".gz":
            return gzip.open(path, "rb")
        return open(path, "rb")

    def _read_lane_lengths_from_net(self, net_path: Path) -> dict[str, float]:
        lane_len: dict[str, float] = {}
        with self._open_maybe_gzip(net_path) as f:
            context = ET.iterparse(f, events=("end",))
            for _, elem in context:
                if elem.tag == "lane":
                    lane_id = elem.attrib.get("id")
                    length_str = elem.attrib.get("length")
                    if lane_id and length_str:
                        lane_len[lane_id] = float(length_str)
                elem.clear()
        return lane_len

    def _read_connections_via_from_net(self, net_path: Path) -> dict[tuple[str, str], str]:
        best: dict[tuple[str, str], tuple[int, str]] = {}
        with self._open_maybe_gzip(net_path) as f:
            context = ET.iterparse(f, events=("end",))
            for _, elem in context:
                if elem.tag == "connection":
                    fr = elem.attrib.get("from")
                    to = elem.attrib.get("to")
                    via = elem.attrib.get("via")
                    if fr and to and via:
                        from_lane = elem.attrib.get("fromLane")
                        to_lane = elem.attrib.get("toLane")

                        score = 0
                        if from_lane == "0":
                            score += 1
                        if to_lane == "0":
                            score += 1

                        key = (fr, to)
                        if key not in best or score > best[key][0]:
                            best[key] = (score, via)
                elem.clear()
        return {k: v[1] for k, v in best.items()}

    def _read_routes_from_rou(self, route_path: Path) -> dict[str, list[str]]:
        tree = ET.parse(route_path)
        root = tree.getroot()

        routes: dict[str, list[str]] = {}
        for r in root.findall(".//route"):
            route_id = r.attrib.get("id")
            edges_str = r.attrib.get("edges")
            if route_id and edges_str:
                routes[route_id] = edges_str.strip().split()
        return routes

    def _compute_route_lengths(
        self,
        routes_edges: dict[str, list[str]],
        lane_len_m: dict[str, float],
        conn_via_lane: dict[tuple[str, str], str],
    ) -> dict[str, float]:
        out: dict[str, float] = {}

        for route_id, edges in routes_edges.items():
            s = 0.0
            missing = 0

            for i, e in enumerate(edges):
                lane0 = f"{e}_0"
                le = lane_len_m.get(lane0)
                if le is None:
                    missing += 1
                else:
                    s += le

                if i < len(edges) - 1:
                    key = (e, edges[i + 1])
                    via_lane = conn_via_lane.get(key)
                    if via_lane:
                        lv = lane_len_m.get(via_lane)
                        if lv is not None:
                            s += lv

            out[route_id] = s

            if missing:
                print(f"Warnung: Route {route_id}: {missing} Edges hatten keine Lane _0 im net (als 0 behandelt).")

        return out
    
    def get_max_repeat_from_routes(self) -> int:
        tree = ET.parse(self.route_path)
        root = tree.getroot()

        reps: list[int] = []
        for r in root.findall(".//route"):
            rep = r.attrib.get("repeat")
            if rep:
                try:
                    reps.append(int(float(rep)))
                except ValueError:
                    pass

        return max(reps) if reps else 0

### 5. CSV-Writer
class CsvWriter:
    def __init__(self, out_path: Path, delimiter: str, lap_cols: int):
        self.out_path = out_path
        self.delimiter = delimiter
        self.lap_cols = lap_cols
        self.file = None
        self.writer = None

    def __enter__(self):
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.out_path, mode="w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file, delimiter=self.delimiter)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.file:
            self.file.close()

    @staticmethod
    def fmt(x):
        if x is None:
            return ""
        return str(x).replace(".", ",")

    def write_header(self):
        header = [
            "step", "sim_time", "veh_id",
            "speed", "accel",
            "route_id", "route_len_m",
            "lap", "dist_total_m", "dist_in_lap_m",
            "lane_id", "lane_pos_m",
            "pos_x", "pos_y",
            "timeLoss_s",
            "lap_time_s",
        ]

        header += [f"lap_{i}_len_m" for i in range(self.lap_cols)]
        header += [f"lap_{i}_time_s" for i in range(self.lap_cols)]

        self.writer.writerow(header)

    def write_row(self, row: list):
        self.writer.writerow(row)

### 6. Vehicle Logger (TraCI Daten sammeln)
""" VehicleLogger ist verantwortlich für:
    - neue Fahrzeuge subscriben
    - route_id pro Fahrzeug merken
    - route_len_m pro Fahrzeug aus dem RouteLengthProvider holen
    - lap und dist_in_lap berechnen
    - CSV-Zeilen schreiben"""

class VehicleLogger:
    def __init__(
        self,
        VARS_to_track: tuple,
        route_len_by_route: dict[str, float],
        csv_writer: CsvWriter,
        scenario: ScenarioConfig,
        lap_cols: int,
    ):
        self.VARS_to_track = VARS_to_track
        self.route_len_by_route = route_len_by_route
        self.csv = csv_writer
        self.scenario = scenario
        self.lap_cols = lap_cols

        self.route_id_by_veh: dict[str, str] = {}
        self.route_len_by_veh: dict[str, float | None] = {}

        self.lap_by_veh: dict[str, int] = {}
        self.lap_start_dist_by_veh: dict[str, float] = {}
        self.prev_edge_by_veh: dict[str, str | None] = {}
        self.prev_speed_by_veh: dict[str, float | None] = {}

        # Distanz pro Lap
        self.lap_dist_max_by_veh: dict[str, float] = {}
        self.lap_lengths_by_veh: dict[str, list[float | None]] = {}

        # Zeit pro Lap
        self.lap_start_time_by_veh: dict[str, float] = {}
        self.lap_times_by_veh: dict[str, list[float | None]] = {}

    def _ensure_vehicle_state(self, veh_id: str, now_sim_time: float):
        if veh_id not in self.lap_by_veh:
            self.lap_by_veh[veh_id] = 0
            self.lap_start_dist_by_veh[veh_id] = 0.0
            self.prev_edge_by_veh[veh_id] = None
            self.prev_speed_by_veh[veh_id] = None

            self.lap_dist_max_by_veh[veh_id] = 0.0
            self.lap_lengths_by_veh[veh_id] = [None] * self.lap_cols

            self.lap_start_time_by_veh[veh_id] = now_sim_time
            self.lap_times_by_veh[veh_id] = [None] * self.lap_cols

    def on_departed(self):
        now = traci.simulation.getTime()
        for veh_id in traci.simulation.getDepartedIDList():
            traci.vehicle.subscribe(veh_id, self.VARS_to_track)

            route_id = traci.vehicle.getRouteID(veh_id)
            self.route_id_by_veh[veh_id] = route_id
            self.route_len_by_veh[veh_id] = self.route_len_by_route.get(route_id)

            self._ensure_vehicle_state(veh_id, now)

    def ensure_known_routes_for_active(self):
        now = traci.simulation.getTime()
        for veh_id in traci.vehicle.getIDList():
            if veh_id not in self.route_id_by_veh:
                route_id = traci.vehicle.getRouteID(veh_id)
                self.route_id_by_veh[veh_id] = route_id
                self.route_len_by_veh[veh_id] = self.route_len_by_route.get(route_id)

            self._ensure_vehicle_state(veh_id, now)

    def log_step(self, step: int, sim_time: float):
        for veh_id in traci.vehicle.getIDList():
            res = traci.vehicle.getSubscriptionResults(veh_id)
            if res is None:
                continue

            speed = res.get(tc.VAR_SPEED)
            accel = res.get(tc.VAR_ACCELERATION)
            dist_total_m = res.get(tc.VAR_DISTANCE)
            pos = res.get(tc.VAR_POSITION)
            timeLoss_s = res.get(tc.VAR_TIMELOSS)
            lane_id = res.get(tc.VAR_LANE_ID)
            lane_pos_m = res.get(tc.VAR_LANEPOSITION)

            if pos is None:
                pos_x, pos_y = None, None
            else:
                pos_x, pos_y = pos[0], pos[1]

            route_id = self.route_id_by_veh.get(veh_id)
            route_len_m = self.route_len_by_veh.get(veh_id)

            if lane_id is None or "_" not in lane_id:
                curr_edge = None
            else:
                curr_edge = lane_id.rsplit("_", 1)[0]

            prev_edge = self.prev_edge_by_veh.get(veh_id)
            lap = self.lap_by_veh.get(veh_id, 0)

            # laufende Lap-Zeit
            lap_start_time = self.lap_start_time_by_veh.get(veh_id, sim_time)
            lap_time_s = sim_time - lap_start_time

            # laufende Lap-Distanz
            dist_in_lap_m = None
            if dist_total_m is not None:
                lap_start_dist = self.lap_start_dist_by_veh.get(veh_id, 0.0)
                dist_in_lap_m = dist_total_m - lap_start_dist

                if dist_in_lap_m is not None:
                    prev_max = self.lap_dist_max_by_veh.get(veh_id, 0.0)
                    if dist_in_lap_m > prev_max:
                        self.lap_dist_max_by_veh[veh_id] = dist_in_lap_m

            lap_switch = (
                prev_edge == self.scenario.lap_end_edge_id
                and curr_edge == self.scenario.lap_start_edge_id
                and speed is not None
                and speed <= self.scenario.lap_speed_eps
                and dist_total_m is not None
            )

            if lap_switch:
                finished_idx = lap

                finished_len = self.lap_dist_max_by_veh.get(veh_id, dist_in_lap_m or 0.0)
                finished_time = lap_time_s

                if 0 <= finished_idx < self.lap_cols:
                    self.lap_lengths_by_veh[veh_id][finished_idx] = finished_len
                    self.lap_times_by_veh[veh_id][finished_idx] = finished_time
                else:
                    print(
                        f"Warnung: Lap-Index {finished_idx} außerhalb lap_cols={self.lap_cols} "
                        f"(veh={veh_id})."
                    )

                # nächste Lap starten
                lap += 1
                self.lap_by_veh[veh_id] = lap

                self.lap_start_dist_by_veh[veh_id] = dist_total_m
                self.lap_dist_max_by_veh[veh_id] = 0.0
                dist_in_lap_m = 0.0

                self.lap_start_time_by_veh[veh_id] = sim_time
                lap_time_s = 0.0

            self.prev_edge_by_veh[veh_id] = curr_edge
            self.prev_speed_by_veh[veh_id] = speed

            row = [
                step,
                self.csv.fmt(sim_time),
                veh_id,
                self.csv.fmt(speed),
                self.csv.fmt(accel),
                route_id if route_id is not None else "",
                self.csv.fmt(route_len_m),
                lap,
                self.csv.fmt(dist_total_m),
                self.csv.fmt(dist_in_lap_m),
                lane_id if lane_id is not None else "",
                self.csv.fmt(lane_pos_m),
                self.csv.fmt(pos_x),
                self.csv.fmt(pos_y),
                self.csv.fmt(timeLoss_s),
                self.csv.fmt(lap_time_s),
            ]

            for v in self.lap_lengths_by_veh.get(veh_id, [None] * self.lap_cols):
                row.append(self.csv.fmt(v))

            for v in self.lap_times_by_veh.get(veh_id, [None] * self.lap_cols):
                row.append(self.csv.fmt(v))

            self.csv.write_row(row)

### 7. Runner
class SimulationRunner:
    def __init__(self, projekt: SumoProjekt, scenario: ScenarioConfig):
        self.projekt = projekt
        self.scenario = scenario

    def run(self):
        sumo_cmd = [
            str(self.projekt.sumo_gui_exe),
            "-c", str(self.projekt.sumocfg_path),
            "--step-length", str(self.scenario.step_length_s),
            "--log", "output/sumo.log",
            "--message-log", "output/sumo_message.log",
        ]

        route_len_provider = RouteLengthProvider(self.projekt.net_path, self.projekt.route_path)
        route_len_by_route = route_len_provider.build()
        print("Routenlängen (m) aus Dateien:", route_len_by_route)

        max_repeat = route_len_provider.get_max_repeat_from_routes()
        lap_cols = max_repeat if max_repeat > 0 else self.scenario.lap_cols_fallback
        if lap_cols <= 0:
            lap_cols = 1

        with CsvWriter(self.scenario.csv_out_path, self.scenario.csv_delimiter, lap_cols) as csvw:
            csvw.write_header()
            print("SUMO CMD:", sumo_cmd)
            traci.start(sumo_cmd, numRetries=60)
            
            logger = VehicleLogger(
                self.scenario.VARS_to_track,
                route_len_by_route,
                csvw,
                self.scenario,
                lap_cols,
            )

            while traci.simulation.getMinExpectedNumber() > 0:
                traci.simulationStep()

                sim_time = traci.simulation.getTime()
                dt = traci.simulation.getDeltaT()
                step = int(sim_time / dt) if dt else int(sim_time)

                logger.on_departed()
                logger.ensure_known_routes_for_active()
                logger.log_step(step, sim_time)

            traci.close()

        print("CSV geschrieben nach:", self.scenario.csv_out_path)
 
### 8. Main
def main():
    base_dir = Path(__file__).resolve().parents[1]  # .../Basis_Scenario_U4_running

    projekt_cfg = ProjektConfig(
        sumocfg_path=base_dir / "config" / "osm.sumocfg"
    )

    scenario_cfg = ScenarioConfig(
        step_length_s = 1.0,
        csv_out_path = base_dir / "output" / "traci_log.csv",
    )

    projekt = SumoProjekt(projekt_cfg)
    runner = SimulationRunner(projekt, scenario_cfg)
    runner.run()

if __name__ == "__main__":
    main()