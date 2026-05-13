"""
sa_distribution.py — Stationsagenten-Verteilung über die U4-Strecke.

Verteilt k Stationsagenten (SA) auf die 10 U4-Stationen so, dass die
maximale Abdeckungsstrecke pro Agent möglichst klein wird (Minimax).

Strategie: Brute-Force über alle C(10,k)-Kombinationen. Bei k=5 sind
das 252 Kombinationen — geht blitzschnell.

Diese Datei kümmert sich AUSSCHLIESSLICH um die Verteilung. Routing,
Dispatch und Walk-Tracking liegen in sa_routing.py.
"""

from itertools import combinations

from stations import (STATIONS, NUM_STATIONS,
                      WENDEPUNKT_LINKS, WENDEPUNKT_RECHTS)


def distribute_agents(num_agents: int) -> list[int]:
    """
    Verteilt num_agents Agenten so, dass die maximale Abweichung
    der Abdeckungsbereiche möglichst gering ist.

    Basiert auf den ECHTEN Streckenkilometern.

    Strategie (Brute-Force):
      Alle möglichen Kombinationen von num_agents Stationen durchprobieren
      und die wählen, bei der der maximale Abstand zum nächsten Agenten
      (inkl. Streckenenden) am kleinsten ist.

      Jeder Agent "deckt" den Bereich bis zur Mitte zum Nachbarn ab.
      Die äußeren Agenten decken zusätzlich bis zum Streckenende ab.
      → Wir minimieren den größten dieser Abdeckungsbereiche.

    Args:
        num_agents: Anzahl der Agenten (1 bis 10)

    Returns:
        Liste von Stationsindizes (0-9), sortiert
    """
    if num_agents < 1 or num_agents > NUM_STATIONS:
        raise ValueError(
            f"num_agents muss zwischen 1 und {NUM_STATIONS} liegen, "
            f"ist aber {num_agents}"
        )

    if num_agents == NUM_STATIONS:
        return list(range(NUM_STATIONS))

    strecke_start = WENDEPUNKT_LINKS
    strecke_ende = WENDEPUNKT_RECHTS

    best_combo = None
    best_max_laufweg = float("inf")

    for combo in combinations(range(NUM_STATIONS), num_agents):
        kms = [STATIONS[i].km for i in combo]

        max_laufwege = []
        for j in range(len(kms)):
            links = strecke_start if j == 0 else (kms[j-1] + kms[j]) / 2
            rechts = strecke_ende if j == len(kms)-1 else (kms[j] + kms[j+1]) / 2
            laufweg = max(kms[j] - links, rechts - kms[j])
            max_laufwege.append(laufweg)

        max_laufweg = max(max_laufwege)

        if max_laufweg < best_max_laufweg:
            best_max_laufweg = max_laufweg
            best_combo = combo

    return list(best_combo)


if __name__ == "__main__":
    print("=== Stationsagenten-Verteilung (Minimax) ===\n")
    for k in range(1, NUM_STATIONS + 1):
        indices = distribute_agents(k)
        kms = [STATIONS[i].km for i in indices]

        abdeckungen = []
        for j in range(len(kms)):
            links = WENDEPUNKT_LINKS if j == 0 else (kms[j-1] + kms[j]) / 2
            rechts = WENDEPUNKT_RECHTS if j == len(kms)-1 else (kms[j] + kms[j+1]) / 2
            abdeckungen.append(rechts - links)

        names = [STATIONS[i].name for i in indices]
        max_abd = max(abdeckungen)
        print(f"  {k:2d} Agent(en): {names}")
        print(f"     Abdeckung: {['%.0f' % a for a in abdeckungen]}m")
        print(f"     Max: {max_abd:.0f}m\n")
