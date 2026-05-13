"""
zub_distribution.py — ZUB+-Verteilung über die U4-Strecke.

Der ZUB+ ist im Gegensatz zu den Stationsagenten (sa_distribution.py)
ZUGGEBUNDEN, nicht stationsgebunden. "Verteilung" heißt hier:

  1. Auf welchem Zug sitzt der ZUB+?             → select_zub_vehicle_id()
  2. Welche (n, gap)-Kombinationen sind sinnvoll → build_scenarios()

Diese Datei kümmert sich AUSSCHLIESSLICH um die Verteilung. Routing,
Dispatch und Walk-Tracking liegen in zub_routing.py.

Es gibt NUR EIN Verhalten (kein "Pfad A" / "Pfad B"): der ZUB+ bleibt
im Startzug bis zur ersten Closure-Haltestelle in der Restroute, steigt
dort aus, wechselt bei Bedarf via <access> die Bahnsteigseite und läuft
entlang des Gleiskörpers zum gestörten Zug. Es findet kein Zugumstieg
statt.
"""


def select_zub_vehicle_id(gap: int, disruption_vehicle_id: str = "u4_1") -> str:
    """
    Bestimmt die SUMO-vehicle-ID des ZUB+-Zuges.

    Konvention der Routendatei: u4_1 ist der gestörte Zug, u4_2 sitzt
    eine gap=1-Position dahinter, u4_3 zwei Positionen dahinter, usw.
    Der ZUB+ sitzt auf dem Zug mit Index gap+1.

    Args:
        gap:                    Abstand in Zugpositionen (1..n-1)
        disruption_vehicle_id:  ID des gestörten Zuges (Default "u4_1")

    Returns:
        SUMO vehicle-ID des ZUB+-Zuges, z.B. "u4_3" für gap=2.
    """
    if not disruption_vehicle_id.startswith("u4_"):
        raise ValueError(
            f"disruption_vehicle_id muss 'u4_<N>' sein, ist: "
            f"{disruption_vehicle_id}"
        )
    base_index = int(disruption_vehicle_id.split("_")[1])
    return f"u4_{base_index + gap}"


def build_scenarios(max_trains: int,
                    positions_m: list[int] | None = None) -> list[dict]:
    """
    Erzeugt die Liste aller einzigartigen (num_trains, gap[, position_m])-Kombinationen.

    Pro Zuganzahl n: Gaps 1 bis n-1 (Gap=0 ist trivial → wird separat erfasst).
    Wenn positions_m übergeben wird, wird jedes (n, gap) zusätzlich über alle
    Positionen aufgespannt → Kreuzprodukt für die Positions-Konvergenzstudie.

    Args:
        max_trains:  Maximale Zuganzahl im Umlauf
        positions_m: Optional Liste von Störpositionen (Meter)

    Returns:
        Liste von dicts mit num_trains, gap und ggf. position_m.
    """
    scenarios: list[dict] = []
    for n_trains in range(2, max_trains + 1):
        for gap in range(1, n_trains):
            if positions_m is None:
                scenarios.append({
                    "num_trains": n_trains,
                    "gap": gap,
                })
            else:
                for pos in positions_m:
                    scenarios.append({
                        "num_trains": n_trains,
                        "gap": gap,
                        "position_m": float(pos),
                    })
    return scenarios


if __name__ == "__main__":
    print("=== ZUB+-Verteilung Quick-Test ===\n")
    for n in range(2, 6):
        for g in range(1, n):
            vid = select_zub_vehicle_id(g)
            print(f"  n={n:2d} gap={g:2d}  →  {vid:6s}")
        print()
    sc = build_scenarios(max_trains=10)
    triv = 10  # +10 triviale Gap=0-Fälle
    print(f"build_scenarios(max_trains=10): {len(sc)} unique  (+ {triv} triviale)")
