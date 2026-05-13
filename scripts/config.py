"""
config.py — Zentrale Konfiguration für die Störungssimulation.

Enthält eine Dataclass (SimulationConfig) die ALLE Parameter für einen
einzelnen Simulationslauf bündelt. Beim Batch-Run (2.000+ Szenarien)
wird pro Lauf ein neues Config-Objekt mit den geänderten Werten erstellt.

Verwendung:
    from config import SimulationConfig

    # Einfachster Fall (alle Defaults):
    cfg = SimulationConfig()

    # Bestimmtes Szenario:
    cfg = SimulationConfig(
        disruption_position_m=5000.0,
        num_agents=3,
        num_trains=5,
    )
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SimulationConfig:
    """
    Parameter für einen einzelnen Simulationslauf.

    Gruppen:
      1. Störung          – wo/wann tritt die Störung auf?
      2. Stationsagenten  – wie viele, wie schnell?
      3. Betrieb          – Zuganzahl, Taktfrequenz
      4. SUMO             – GUI, Zeitschritt
      5. Pfade            – wo liegen die Dateien?
      6. Output           – wo werden Ergebnisse gespeichert?
    """

    # ===================================================================
    # 1. STÖRUNG
    # ===================================================================

    disruption_position_m: float = 5000.0
    """
    Position der Störung in Metern, gemessen ab dem Routenstart.
    Wird im Batch-Run variiert (alle 1.000m, später alle 250m).
    """

    disruption_lap: int = 5
    """
    In welchem Umlauf die Störung ausgelöst wird.
    Lap 5 = stabiler Regelbetrieb nach Einlaufphase (vgl. MA Kap. 3.5).
    Zum Testen: lap=2 setzen (geht schneller).
    """

    disruption_vehicle_id: str = "u4_1"
    """
    ID des gestörten Zuges. Muss mit der Vehicle-ID
    in der route_u4_long.rou.xml übereinstimmen.
    """

    # ===================================================================
    # 2. STATIONSAGENTEN
    # ===================================================================

    num_agents: int = 1
    """
    Anzahl Stationsagenten auf der Strecke (1 bis 10).
    Die Verteilung berechnet stations.distribute_agents().
    """

    agent_walk_speed_ms: float = 3.33
    """
    Laufgeschwindigkeit des Agenten/ZUB+ auf den Gleisen in m/s.
    MA Kap. 3.3.1: 3.33 m/s für SA und ZUB+.
    """

    agent_reaction_time_s: float = 90.0
    """
    Zeit in Sekunden zwischen Störungsmeldung und Losmarschieren.
    Enthält: Benachrichtigung, Situationsbewertung, Vorbereitung.
    MA Kap. 3.3.1: 90 s (AGBF-Hilfsfrist-Analogie).
    """

    # ===================================================================
    # 3. BETRIEB
    # ===================================================================

    num_trains: int = 1
    """
    Anzahl Züge auf der Strecke. Bestimmt die Taktfrequenz.
    Wird im Batch-Run variiert (1 bis 10, später höher).
    Für num_trains > 1 muss eine generierte Routendatei
    verwendet werden (siehe route_generator.py).
    """

    step_length_s: float = 1.0
    """SUMO-Zeitschrittlänge in Sekunden."""

    # ===================================================================
    # 4. SUMO
    # ===================================================================

    use_gui: bool = True
    """
    True  = sumo-gui (mit Fenster, zum Prüfen)
    False = sumo (ohne Fenster, für Batch-Läufe)
    """

    # ===================================================================
    # 5. PFADE
    # ===================================================================

    base_dir: Path = None
    """Projektverzeichnis (sumo-masterarbeit/). Wird automatisch erkannt."""

    sumocfg_path: Path = None
    """Pfad zur SUMO-Konfigurationsdatei."""

    route_path: Path = None
    """
    Pfad zur Routendatei. Bei num_trains=1: route_u4_long.rou.xml.
    Bei num_trains>1: generierte Datei unter routes/generated/.
    """

    # ===================================================================
    # 6. OUTPUT
    # ===================================================================

    output_dir: Path = None
    """Verzeichnis für Ergebnis-Dateien."""

    # ===================================================================
    # AUTOMATISCHE PFAD-BERECHNUNG
    # ===================================================================

    def __post_init__(self):
        """
        Berechnet Pfade automatisch aus dem Projektverzeichnis.
        config.py liegt in scripts/, also ist parents[1] = sumo-masterarbeit/.
        """
        if self.base_dir is None:
            self.base_dir = Path(__file__).resolve().parents[1]
        if self.sumocfg_path is None:
            self.sumocfg_path = self.base_dir / "config" / "osm.sumocfg"
        if self.route_path is None:
            self.route_path = self.base_dir / "routes" / "route_u4_long.rou.xml"
        if self.output_dir is None:
            self.output_dir = self.base_dir / "output" / "results"

    # ===================================================================
    # BERECHNETE EIGENSCHAFTEN
    # ===================================================================

    @property
    def sumo_binary(self) -> str:
        """Voller Pfad zur SUMO-Binary (sumo-gui oder sumo)."""
        import os, sys
        sumo_home = os.environ.get("SUMO_HOME", "")
        exe_name = "sumo-gui" if self.use_gui else "sumo"
        exe = Path(sumo_home) / "bin" / exe_name
        if sys.platform.startswith("win"):
            exe = exe.with_suffix(".exe")
        # Fallback: wenn Binary nicht existiert, hoffe dass es im PATH ist
        if exe.exists():
            return str(exe)
        return exe_name
