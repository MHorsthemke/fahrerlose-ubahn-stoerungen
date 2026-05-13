"""
route_generator.py — Erzeugt Routendateien mit variabler Zuganzahl.

SUMO braucht beim Start eine .rou.xml-Datei, in der alle Fahrzeuge
definiert sind. Für unterschiedliche Zuganzahlen (Taktfrequenzen)
brauchen wir unterschiedliche Routendateien.

Dieses Modul liest die bestehende route_u4_long.rou.xml als Template
und erzeugt neue Dateien mit n Zügen, die zeitlich versetzt starten.

Logik:
  - Die Route (Edges + Stops) bleibt identisch für alle Züge
  - Jeder Zug bekommt eine eigene Vehicle-ID: u4_1, u4_2, ..., u4_n
  - Die Depart-Zeiten sind gleichmäßig über einen Umlauf verteilt:
    depart_i = base_depart + i * (umlaufzeit / n)
  - Jeder Zug wiederholt die Route (repeat) mit derselben cycleTime

Beispiel für 3 Züge bei Umlaufzeit 1000s:
  u4_1: depart=100s
  u4_2: depart=100 + 333 = 433s
  u4_3: depart=100 + 667 = 767s

Die generierten Dateien werden unter routes/generated/ gespeichert.

Verwendung:
    from route_generator import generate_route_file

    path = generate_route_file(
        template_path=Path("routes/route_u4_long.rou.xml"),
        num_trains=5,
        output_dir=Path("routes/generated"),
    )
    # → routes/generated/route_n5.rou.xml
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from copy import deepcopy


# Umlaufzeit aus der Testfahrt (stopinfos.xml):
# Bockenheimer Warte Runde 1→2: 1595 - 133 = 1462s
# Bockenheimer Warte Runde 2→3: 3057 - 1595 = 1462s
# Konsistent: 1462s ≈ 24.4 Minuten pro Umlauf.
UMLAUFZEIT_S = 1462.0


def generate_route_file(
    template_path: Path,
    num_trains: int,
    output_dir: Path,
    base_depart: float = 100.0,
    umlaufzeit_s: float = UMLAUFZEIT_S,
) -> Path:
    """
    Erzeugt eine Routendatei mit num_trains Zügen.

    Liest die bestehende Routendatei als Template und erstellt eine
    neue Datei mit n Fahrzeugen, die zeitlich versetzt abfahren.

    Args:
        template_path: Pfad zur bestehenden route_u4_long.rou.xml
        num_trains:    Anzahl Züge (1 = nur Originalzug)
        output_dir:    Verzeichnis für die generierte Datei
        base_depart:   Abfahrtszeit des ersten Zuges (Sekunden)
        umlaufzeit_s:  Dauer eines Umlaufs in Sekunden (Default: 1462s
                       aus der Testfahrt). Wird verwendet um die
                       Abfahrtsintervalle zu berechnen.

    Returns:
        Pfad zur generierten Routendatei
    """
    # --- Sonderfall: 1 Zug = Original-Template verwenden ---
    if num_trains == 1:
        return template_path

    # --- Template parsen ---
    tree = ET.parse(template_path)
    root = tree.getroot()

    # --- vType finden (bleibt unverändert) ---
    vtype = root.find("vType")
    if vtype is None:
        raise ValueError("Kein <vType> im Template gefunden!")

    # --- Aktive Route finden ---
    # Wir suchen die Route r_1 (die aktive). Falls nicht gefunden,
    # nehmen wir die erste Route die wir finden.
    route_elem = None
    for r in root.findall("route"):
        if r.get("id") == "r_1":
            route_elem = r
            break

    if route_elem is None:
        # Fallback: erste Route nehmen
        routes = root.findall("route")
        if routes:
            route_elem = routes[0]

    if route_elem is None:
        raise ValueError("Keine <route> im Template gefunden!")

    route_id = route_elem.get("id")

    # Umlaufzeit ist jetzt als Parameter gegeben (Default: 1462s).
    # Wir verwenden NICHT die cycleTime aus der Route, weil die
    # dort eingetragene cycleTime=1000 nicht die echte Umlaufzeit ist.

    # --- Bestehende Vehicles entfernen ---
    # Wir entfernen alle <vehicle>-Elemente und erstellen neue
    for veh in root.findall("vehicle"):
        root.remove(veh)

    # --- Neue Vehicles erstellen ---
    # Zeitlicher Abstand zwischen den Zügen:
    interval_s = umlaufzeit_s / num_trains

    for i in range(num_trains):
        # Vehicle-ID: u4_1, u4_2, u4_3, ...
        veh_id = f"u4_{i + 1}"

        # Abfahrtszeit: gleichmäßig verteilt über einen Umlauf
        depart = base_depart + i * interval_s

        # <vehicle> Element erstellen
        # line="U4" ist fuer findIntermodalRoute / appendDrivingStage noetig,
        # damit SUMO die Vehicles als U4-Linie erkennt und der ZUB+ als
        # Fahrgast automatisch einen passenden Zug zugewiesen bekommt.
        veh_elem = ET.SubElement(root, "vehicle")
        veh_elem.set("id", veh_id)
        veh_elem.set("type", "SUBWAY")
        veh_elem.set("depart", f"{depart:.2f}")
        veh_elem.set("route", route_id)
        veh_elem.set("line", "U4")

    # --- Ausgabedatei schreiben ---
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"route_n{num_trains}.rou.xml"

    # XML-Header und Formatierung
    tree.write(
        output_path,
        encoding="UTF-8",
        xml_declaration=True,
    )

    # Datei nochmal lesen und hübscher formatieren
    # (ElementTree schreibt alles in eine Zeile)
    _pretty_format(output_path)

    print(f"[ROUTE] Generiert: {output_path} | "
          f"{num_trains} Züge | Intervall: {interval_s:.1f}s")

    return output_path


def _pretty_format(path: Path):
    """
    Fügt Einrückung und Zeilenumbrüche in die XML-Datei ein.

    ElementTree.write() erzeugt standardmäßig alles in einer Zeile,
    was schlecht lesbar ist. Diese Funktion macht es hübscher.
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        _indent_xml(root)
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    except Exception:
        pass  # Nicht kritisch — Datei funktioniert auch ohne Formatierung


def _indent_xml(elem, level=0):
    """Rekursive Einrückung für XML-Elemente."""
    indent = "\n" + "    " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent
    if not level:
        elem.tail = "\n"


def generate_all_route_files(
    template_path: Path,
    output_dir: Path,
    max_trains: int = 10,
    umlaufzeit_s: float = None,
) -> dict[int, Path]:
    """
    Erzeugt Routendateien für 1 bis max_trains Züge.

    Gibt ein Dictionary zurück: {num_trains: pfad_zur_datei}

    Args:
        template_path: Pfad zur Template-Route
        output_dir:    Ausgabe-Verzeichnis
        max_trains:    Maximale Zuganzahl (Default: 10)
        umlaufzeit_s:  Umlaufzeit in Sekunden (optional)

    Returns:
        Dict {1: Path("route_u4_long.rou.xml"), 2: Path("route_n2.rou.xml"), ...}
    """
    routes = {}

    for n in range(1, max_trains + 1):
        path = generate_route_file(
            template_path=template_path,
            num_trains=n,
            output_dir=output_dir,
            umlaufzeit_s=umlaufzeit_s,
        )
        routes[n] = path

    print(f"\n[ROUTE] {len(routes)} Routendateien generiert in {output_dir}")
    return routes


# ===================================================================
# QUICK-TEST
# ===================================================================
if __name__ == "__main__":
    # Test: Generiere Routen für 1-5 Züge
    base_dir = Path(__file__).resolve().parents[1]
    template = base_dir / "routes" / "route_u4_long.rou.xml"
    out_dir = base_dir / "routes" / "generated"

    print("=== Route Generator Test ===\n")
    print(f"Template: {template}")
    print(f"Output:   {out_dir}\n")

    routes = generate_all_route_files(
        template_path=template,
        output_dir=out_dir,
        max_trains=5,
        # umlaufzeit_s wird aus cycleTime der Route gelesen
    )

    print("\nGenerierte Dateien:")
    for n, path in routes.items():
        print(f"  {n} Zug/Züge → {path}")
