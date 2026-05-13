"""
add_access_to_stops.py — Ergänzt <access>-Elemente an allen U4-busStops.

Für jede U4-Station (10 Stück) werden an Hin- UND Rück-Stop je zwei
Access-Einträge ergänzt:
  - Eigene Seite (lane _1 desselben Edges, Länge 2m)   — direkter Ausstieg
  - Gegenseite (lane _1 des anderen Edges, Länge 30m)  — Unterführung

Idempotent: Läuft er zweimal, werden Duplikate verhindert (Skript prüft
ob schon <access> im busStop vorhanden ist).

Aufruf:
  python3 add_access_to_stops.py
"""
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stations import STATIONS

STOPS_XML = Path(__file__).resolve().parents[1] / "network" / "osm_stops.add.xml"


def lane_1(lane_0: str) -> str:
    """'1238346189_0' → '1238346189_1' (Parallelweg-Lane)."""
    edge, _ = lane_0.rsplit("_", 1)
    return f"{edge}_1"


def main() -> int:
    if not STOPS_XML.is_file():
        print(f"FEHLER: {STOPS_XML} nicht gefunden.")
        return 1

    tree = ET.parse(STOPS_XML)
    root = tree.getroot()

    # busStop-Elemente nach ID indizieren
    stops = {}
    for stop in root.findall("busStop"):
        stops[stop.get("id")] = stop

    print(f"Gefunden: {len(stops)} busStops in {STOPS_XML.name}")

    added = skipped = 0
    for station in STATIONS:
        print(f"\n{station.name}:")
        for side, stop_id, own_lane_0, own_pos, other_lane_0, other_pos in [
            ("Hin", station.stop_hin,
             station.lane_hin,   station.stop_pos_hin,
             station.lane_rueck, station.stop_pos_rueck),
            ("Rück", station.stop_rueck,
             station.lane_rueck, station.stop_pos_rueck,
             station.lane_hin,   station.stop_pos_hin),
        ]:
            stop = stops.get(stop_id)
            if stop is None:
                print(f"  {side} ({stop_id}): NICHT GEFUNDEN — übersprungen")
                continue
            existing = stop.findall("access")
            if existing:
                print(f"  {side} ({stop_id}): hat bereits "
                      f"{len(existing)} <access> — übersprungen")
                skipped += 1
                continue
            own_lane = lane_1(own_lane_0)
            other_lane = lane_1(other_lane_0)
            ET.SubElement(stop, "access", {
                "lane": own_lane,
                "pos": f"{own_pos:.2f}",
                "length": "2",
            })
            ET.SubElement(stop, "access", {
                "lane": other_lane,
                "pos": f"{other_pos:.2f}",
                "length": "30",
            })
            print(f"  {side} ({stop_id}): +access(own={own_lane}@{own_pos:.1f}, "
                  f"other={other_lane}@{other_pos:.1f})")
            added += 2

    ET.indent(tree, space="    ")
    tree.write(STOPS_XML, encoding="UTF-8", xml_declaration=True)
    print(f"\n=== Fertig ===")
    print(f"  Neue <access>-Elemente: {added}")
    print(f"  Übersprungen (schon vorhanden): {skipped} Stops")
    print(f"  Datei gespeichert: {STOPS_XML}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
