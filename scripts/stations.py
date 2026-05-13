"""
stations.py — Hardcodierte Stationsdaten der U4 Frankfurt (Route r_1).

Dieses Modul enthält alle 10 Stationen der Route r_1
(Bockenheimer Warte – Seckbacher Landstraße und zurück).

Jede Station hat:
  - Hin- und Rück-Stop-IDs (aus osm_stops.add.xml)
  - Hin- und Rück-Lane-IDs
  - Streckenkilometer (Hin-Richtung, ab Rundenbeginn)
  - Stop-Positionen auf dem Edge (Mitte des busStops)

Verteilung der Agenten: siehe sa_distribution.py.

Warum hardcodiert?
    - Die U4-Strecke ändert sich nicht
    - Kein fehleranfälliges XML-Parsing nötig
    - Einfacher zu verstehen und zu debuggen
"""

from dataclasses import dataclass


@dataclass
class Station:
    """
    Ein Stationspaar auf der U4-Strecke.

    Attributes:
        name:           Haltestellenname
        stop_hin:       busStop-ID Hinfahrt
        stop_rueck:     busStop-ID Rückfahrt
        lane_hin:       Lane-ID Hinfahrt
        lane_rueck:     Lane-ID Rückfahrt
        km:             Streckenkilometer (Hin-Richtung, ab Rundenbeginn)
        stop_pos_hin:   Mitte des busStops auf dem Hin-Edge (Meter)
        stop_pos_rueck: Mitte des busStops auf dem Rück-Edge (Meter)
        lap_pos_hin:    Umlaufposition Hin-Bahnsteig (m, ab Umlaufstart)
        lap_pos_rueck:  Umlaufposition Rück-Bahnsteig (m, ab Umlaufstart)

    lap_pos_hin/rueck wurden via scripts/measure_umlauf.py aus einem
    Probe-Umlauf des Zuges u4_1 gemessen (siehe scripts/data/umlauf_data.py).
    """
    name: str
    stop_hin: str
    stop_rueck: str
    lane_hin: str
    lane_rueck: str
    km: float              # Streckenkilometer (Hin-Richtung)
    stop_pos_hin: float    # Mitte des Hin-Stops auf dem Edge
    stop_pos_rueck: float  # Mitte des Rück-Stops auf dem Edge
    lap_pos_hin: float     # gemessene Umlaufposition Hin-Bahnsteig
    lap_pos_rueck: float   # gemessene Umlaufposition Rück-Bahnsteig

    @property
    def edge_hin(self) -> str:
        """Edge-ID der Hinfahrt (= Lane-ID ohne den '_0' Suffix)."""
        return self.lane_hin.rsplit("_", 1)[0]

    @property
    def edge_rueck(self) -> str:
        """Edge-ID der Rückfahrt (= Lane-ID ohne den '_0' Suffix)."""
        return self.lane_rueck.rsplit("_", 1)[0]


# ===================================================================
# DIE 10 STATIONEN DER ROUTE r_1
# ===================================================================
# Reihenfolge: Hinfahrt von Bockenheimer Warte → Seckbacher Landstraße
#
# km = Streckenkilometer ab Rundenbeginn (Hin-Richtung)
#      Berechnet aus den Edge-Längen der Route r_1.
#
# stop_pos_hin/rueck = Mittelpunkt des busStops auf dem Edge
#      Berechnet als (startPos + endPos) / 2 aus osm_stops.add.xml
#
# "Hin" = Richtung Seckbacher Landstraße (Osten)
# "Rück" = Richtung Bockenheimer Warte (Westen)

STATIONS: list[Station] = [
    Station(
        name="Bockenheimer Warte",
        stop_hin="2682026582",       # lane: 1238346189_0
        stop_rueck="3385060043",     # lane: 440748774#2_0
        lane_hin="1238346189_0",
        lane_rueck="440748774#2_0",
        km=283,
        stop_pos_hin=76.6,           # (21.64 + 131.64) / 2
        stop_pos_rueck=108.9,        # (53.87 + 163.87) / 2
        lap_pos_hin=333.26,
        lap_pos_rueck=14935.92,
    ),
    Station(
        name="Festhalle/Messe",
        stop_hin="2682026529",       # lane: 60734091#1_0
        stop_rueck="2682026530",     # lane: 262540237#2_0
        lane_hin="60734091#1_0",
        lane_rueck="262540237#2_0",
        km=1224,
        stop_pos_hin=864.6,          # (809.55 + 919.55) / 2
        stop_pos_rueck=77.2,         # (22.24 + 132.24) / 2
        lap_pos_hin=1307.35,
        lap_pos_rueck=14013.24,
    ),
    Station(
        name="Hauptbahnhof",
        stop_hin="760309241",        # lane: 262540239#1_0
        stop_rueck="29271560",       # lane: 60698616#1_0
        lane_hin="262540239#1_0",
        lane_rueck="60698616#1_0",
        km=1864,
        stop_pos_hin=61.1,           # (6.06 + 116.06) / 2
        stop_pos_rueck=94.1,         # (39.09 + 149.09) / 2
        lap_pos_hin=2026.04,
        lap_pos_rueck=13280.65,
    ),
    Station(
        name="Willy-Brandt-Platz",
        stop_hin="2683735885",       # lane: 60734109_0
        stop_rueck="2683735886",     # lane: 560679910#1_0
        lane_hin="60734109_0",
        lane_rueck="560679910#1_0",
        km=2773,
        stop_pos_hin=772.1,          # (717.12 + 827.12) / 2
        stop_pos_rueck=641.6,        # (586.58 + 696.58) / 2
        lap_pos_hin=2957.06,
        lap_pos_rueck=12354.79,
    ),
    Station(
        name="Dom/Römer",
        stop_hin="2683735889",       # lane: 60734112#1_0
        stop_rueck="2683735890",     # lane: 60698617#1_0
        lane_hin="60734112#1_0",
        lane_rueck="60698617#1_0",
        km=3481,
        stop_pos_hin=649.4,          # (594.35 + 704.35) / 2
        stop_pos_rueck=419.7,        # (364.73 + 474.73) / 2
        lap_pos_hin=3682.17,
        lap_pos_rueck=11639.30,
    ),
    Station(
        name="Konstablerwache",
        stop_hin="760309227",        # lane: 1414296215#1_0
        stop_rueck="759424469",      # lane: 60752827_0
        lane_hin="1414296215#1_0",
        lane_rueck="60752827_0",
        km=4071,
        stop_pos_hin=62.0,           # (6.96 + 116.95) / 2
        stop_pos_rueck=3112.4,       # (3057.35 + 3167.35) / 2
        lap_pos_hin=4296.22,
        lap_pos_rueck=11039.68,
    ),
    Station(
        name="Merianplatz",
        stop_hin="5295358548",       # lane: 5062172_0
        stop_rueck="760458315",      # lane: 60752827_0
        lane_hin="5062172_0",
        lane_rueck="60752827_0",
        km=4966,
        stop_pos_hin=569.7,          # (514.65 + 624.65) / 2
        stop_pos_rueck=2199.7,       # (2144.69 + 2254.69) / 2
        lap_pos_hin=5208.07,
        lap_pos_rueck=10127.02,
    ),
    Station(
        name="Höhenstraße",
        stop_hin="29271742",         # lane: 5062172_0
        stop_rueck="760458235",      # lane: 60752827_0
        lane_hin="5062172_0",
        lane_rueck="60752827_0",
        km=5534,
        stop_pos_hin=1138.5,         # (1083.51 + 1193.51) / 2
        stop_pos_rueck=1630.7,       # (1575.71 + 1685.71) / 2
        lap_pos_hin=5776.93,
        lap_pos_rueck=9558.04,
    ),
    Station(
        name="Bornheim Mitte",
        stop_hin="29271744",         # lane: 5062172_0
        stop_rueck="760458240",      # lane: 60752827_0
        lane_hin="5062172_0",
        lane_rueck="60752827_0",
        km=6109,
        stop_pos_hin=1712.7,         # (1657.65 + 1767.65) / 2
        stop_pos_rueck=1056.6,       # (1001.56 + 1111.56) / 2
        lap_pos_hin=6351.07,
        lap_pos_rueck=8983.89,
    ),
    Station(
        name="Seckbacher Landstraße",
        stop_hin="2683736305",       # lane: 5062172_0
        stop_rueck="2683736306",     # lane: 60752827_0
        lane_hin="5062172_0",
        lane_rueck="60752827_0",
        km=7006,
        stop_pos_hin=2609.8,         # (2554.82 + 2664.82) / 2
        stop_pos_rueck=161.6,        # (106.63 + 216.63) / 2
        lap_pos_hin=7248.24,
        lap_pos_rueck=8088.96,
    ),
]

# Anzahl Stationen (Konstante für Übersichtlichkeit)
NUM_STATIONS = len(STATIONS)  # = 10

# Streckenanfang und -ende (nur die Stationen)
STRECKE_START_KM = STATIONS[0].km       # 283m (BW)
STRECKE_ENDE_KM = STATIONS[-1].km       # 7006m (Seckb. Landstr.)
STRECKE_LAENGE = STRECKE_ENDE_KM - STRECKE_START_KM  # 6723m

# Wendepunkte (echte Streckenenden inkl. Wendegleise)
# BW-Wende: 283m vor Station BW → km 0
# Seckb.L.-Wende: 382m nach Seckb.L. → km 7388
WENDEPUNKT_LINKS = 0
WENDEPUNKT_RECHTS = 7388


def get_station_by_stop_id(stop_id: str) -> Station | None:
    """
    Findet eine Station anhand einer busStop-ID (hin oder rück).
    """
    for station in STATIONS:
        if station.stop_hin == stop_id or station.stop_rueck == stop_id:
            return station
    return None


# ===================================================================
# QUICK-TEST: Wenn dieses Modul direkt ausgeführt wird
# ===================================================================
if __name__ == "__main__":
    print("=== U4 Stationen (Route r_1) ===\n")
    print(f"  Strecke: {STRECKE_START_KM}m – {STRECKE_ENDE_KM}m "
          f"({STRECKE_LAENGE}m)")
    print(f"  Streckenmitte: {STRECKE_START_KM + STRECKE_LAENGE / 2:.0f}m\n")

    for i, s in enumerate(STATIONS):
        print(f"  {i:2d}. {s.name:25} km={s.km:5d}m  "
              f"Hin: {s.edge_hin} pos={s.stop_pos_hin:.0f}m  "
              f"Rück: {s.edge_rueck} pos={s.stop_pos_rueck:.0f}m")

    print("\n(Verteilung siehe sa_distribution.py)")
