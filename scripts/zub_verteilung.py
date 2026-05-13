"""
zub_verteilung.py — Verteilung der ZUB+ auf Züge.

Der ZUB+ (Zugbegleiter Plus) ist ein Mitarbeiter, der an Bord eines
Zuges mitfährt. Bei einer Störung gibt es zwei Fälle:

  1. ZUB+ ist auf dem gestörten Zug → Interventionszeit = 0
     (er bemerkt die Störung sofort und kann direkt handeln)

  2. ZUB+ ist auf einem anderen Zug → Der Zug fährt normal weiter,
     staut sich hinter dem gestörten Zug auf, der ZUB+ steigt aus
     und läuft zu Fuß zum Störungsort.

Die Verteilung erfolgt möglichst gleichmäßig auf die vorhandenen
Züge. Bei k ZUB+ auf n Zügen werden die besetzten Züge so gewählt,
dass der maximale Abstand (in Zug-Positionen) zwischen zwei besetzten
Zügen minimal ist.

Beispiele (5 Züge, Züge als Index 0-4):
  1 ZUB+: [0]                    → 1 besetzt, 4 unbesetzt
  2 ZUB+: [0, 2]                 → gleichmäßig verteilt
  3 ZUB+: [0, 1, 3]  oder [0, 2, 3] → bestmöglich
  4 ZUB+: [0, 1, 2, 3]           → 1 unbesetzt
  5 ZUB+: [0, 1, 2, 3, 4]        → alle besetzt

Verwendung:
    from zub_verteilung import distribute_zub, get_all_zub_scenarios

    # Welche Züge bekommen einen ZUB+?
    besetzt = distribute_zub(num_trains=5, num_zub=2)
    # → [0, 2]

    # Alle Szenarien für eine gegebene Zuganzahl:
    szenarien = get_all_zub_scenarios(num_trains=5)
    # → {1: [0], 2: [0, 2], 3: [0, 1, 3], 4: [0, 1, 2, 3], 5: [0, 1, 2, 3, 4]}
"""


def distribute_zub(num_trains: int, num_zub: int) -> list[int]:
    """
    Verteilt num_zub ZUB+ gleichmäßig auf num_trains Züge.

    Die Züge fahren auf einer Rundstrecke mit gleichmäßigem Headway.
    Die ZUB+ werden so verteilt, dass der maximale Abstand zwischen
    zwei besetzten Zügen (auf der Rundstrecke) minimal ist.

    Args:
        num_trains: Anzahl Züge auf der Strecke (>= 1)
        num_zub:    Anzahl ZUB+ (1 bis num_trains)

    Returns:
        Sortierte Liste von Zug-Indizes (0-basiert), die einen ZUB+ haben.
    """
    if num_zub < 1:
        raise ValueError(f"Mindestens 1 ZUB+ erforderlich, ist aber {num_zub}")
    if num_zub > num_trains:
        raise ValueError(
            f"Mehr ZUB+ ({num_zub}) als Züge ({num_trains}) nicht möglich"
        )

    # Sonderfall: alle besetzt
    if num_zub == num_trains:
        return list(range(num_trains))

    # Gleichmäßige Verteilung auf der Rundstrecke:
    # Jeder ZUB+ wird in die Mitte seines "Slots" platziert.
    # Formel: index_i = floor((2i+1) * n / (2k))
    # Dadurch werden auch die LÜCKEN gleichmäßig verteilt.
    # Anschließend wird auf Index 0 verschoben (Konvention).
    raw = [(2 * i + 1) * num_trains // (2 * num_zub) for i in range(num_zub)]
    shift = raw[0]  # auf 0 normieren
    return sorted((idx - shift) % num_trains for idx in raw)


def get_all_zub_scenarios(num_trains: int) -> dict[int, list[int]]:
    """
    Erzeugt alle ZUB+-Szenarien für eine gegebene Zuganzahl.

    Für jede mögliche Anzahl ZUB+ (1 bis num_trains) wird die
    optimale Verteilung berechnet.

    Args:
        num_trains: Anzahl Züge auf der Strecke

    Returns:
        Dict {num_zub: [zug_indizes]}
        Beispiel für 5 Züge:
        {
            1: [0],
            2: [0, 2],
            3: [0, 2, 3],
            4: [0, 1, 2, 4],
            5: [0, 1, 2, 3, 4]
        }
    """
    return {
        k: distribute_zub(num_trains, k)
        for k in range(1, num_trains + 1)
    }


def print_zub_scenarios(num_trains: int):
    """Gibt alle ZUB+-Szenarien übersichtlich aus."""
    szenarien = get_all_zub_scenarios(num_trains)
    print(f"\nZUB+-Verteilung für {num_trains} Züge:")
    print(f"{'ZUB+':>5} | {'Besetzte Züge':<30} | {'Unbesetzt':>10} | Bemerkung")
    print(f"{'-'*5}-+-{'-'*30}-+-{'-'*10}-+-{'-'*30}")

    for num_zub, zuege in szenarien.items():
        zug_namen = [f"u4_{i+1}" for i in zuege]
        unbesetzt = num_trains - num_zub
        bemerkung = ""
        if num_zub == num_trains:
            bemerkung = "Alle besetzt → Interventionszeit immer 0"
        elif num_zub == 1:
            bemerkung = "Worst case: max. Anfahrtsweg"

        print(f"{num_zub:>5} | {', '.join(zug_namen):<30} | {unbesetzt:>10} | {bemerkung}")


# ===================================================================
# QUICK-TEST
# ===================================================================
if __name__ == "__main__":
    print("=== ZUB+-Verteilung ===")

    for n_trains in [1, 2, 3, 4, 5, 6, 8, 10]:
        print_zub_scenarios(n_trains)
        print()
