"""
zub_simulation_bedarf.py — Bestimmt welche ZUB+-Szenarien simuliert werden müssen.

Kernidee:
  Für die Interventionszeit des ZUB+ zählt:
    1. Anzahl Züge (bestimmt Headway und Abstände)
    2. Abstand (Gap) vom ausgefallenen Zug zum nächsten ZUB+-Zug DAHINTER
       (= Anzahl Züge die sich zwischen ZUB+ und Störung aufstauen)

  Wenn zwei Szenarien die GLEICHE Zuganzahl UND den GLEICHEN Gap haben,
  ergibt sich die gleiche Interventionszeit → nur einmal simulieren.

  Beispiel: 4 Züge, ZUB+=2, Verteilung B u B u (Positionen 0,2)
    - Zug 1 fällt aus (u): nächster ZUB+ dahinter = Pos 0, Gap = 1
    - Zug 3 fällt aus (u): nächster ZUB+ dahinter = Pos 2, Gap = 1
    Beide haben Gap=1 bei 4 Zügen → identische Simulation.
    Und Gap=1 bei 4 Zügen wurde schon bei ZUB+=1 (B u u u, Zug 1 fällt aus) simuliert!

Sonderfälle:
  - ZUB+ auf dem gestörten Zug (Gap=0): t_Intervention = 0, keine Simulation nötig
  - Alle Züge besetzt (Diagonale): immer Gap=0, nie Simulation nötig

Verwendung:
    from zub_simulation_bedarf import analyze_simulation_need

    result = analyze_simulation_need(max_trains=28)
    # result enthält für jedes Szenario ob es simuliert werden muss
"""

from zub_verteilung import distribute_zub


def gap_to_nearest_zub(train_idx: int, occupied: set[int], num_trains: int) -> int:
    """
    Berechnet den Gap (Abstand in Zugpositionen) vom ausgefallenen Zug
    zum nächsten ZUB+-Zug DAHINTER (in Fahrtrichtung rückwärts).

    Auf einer Rundstrecke: wir gehen von train_idx rückwärts bis wir
    einen besetzten Zug finden.

    Args:
        train_idx:  Index des ausgefallenen Zugs
        occupied:   Set der besetzten Zug-Indizes
        num_trains: Gesamtzahl der Züge

    Returns:
        Gap (0 = ZUB+ ist auf dem gestörten Zug selbst)
    """
    if train_idx in occupied:
        return 0

    for dist in range(1, num_trains):
        behind = (train_idx - dist) % num_trains
        if behind in occupied:
            return dist

    raise ValueError(f"Kein ZUB+ gefunden für Zug {train_idx} bei {num_trains} Zügen")


def analyze_scenario(num_trains: int, num_zub: int) -> dict:
    """
    Analysiert ein einzelnes Szenario (num_trains, num_zub).

    Returns:
        {
            'num_trains': int,
            'num_zub': int,
            'occupied': list[int],        # Besetzte Zug-Indizes
            'failures': [                  # Pro ausfallender Zug
                {
                    'train_idx': int,
                    'gap': int,            # Abstand zum nächsten ZUB+
                    'is_trivial': bool,    # Gap == 0 → t_Intervention = 0
                    'sim_key': tuple,      # (num_trains, gap) für Deduplizierung
                }
            ]
        }
    """
    occupied = set(distribute_zub(num_trains, num_zub))

    failures = []
    for train_idx in range(num_trains):
        gap = gap_to_nearest_zub(train_idx, occupied, num_trains)
        failures.append({
            'train_idx': train_idx,
            'gap': gap,
            'is_trivial': gap == 0,
            'sim_key': (num_trains, gap) if gap > 0 else None,
        })

    return {
        'num_trains': num_trains,
        'num_zub': num_zub,
        'occupied': sorted(occupied),
        'failures': failures,
    }


def analyze_simulation_need(max_trains: int) -> dict:
    """
    Vollständige Analyse aller Szenarien.

    Geht spaltenweise (num_trains) vor, innerhalb jeder Spalte
    zeilenweise (num_zub von 1 aufsteigend). Markiert für jede
    (num_trains, gap)-Kombination ob sie NEU oder DUPLIKAT ist.

    Returns:
        {
            'max_trains': int,
            'unique_sims': set[tuple],     # Alle einzigartigen (num_trains, gap)
            'scenarios': {
                (num_trains, num_zub): {
                    ... (wie analyze_scenario),
                    'failures': [
                        {
                            ...,
                            'needs_sim': bool,    # True = muss simuliert werden
                            'first_seen_at': tuple | None,  # (num_trains, num_zub) wo zuerst
                        }
                    ],
                    'new_sims': int,           # Anzahl neue Simulationen
                    'duplicate_sims': int,     # Anzahl Duplikate
                    'trivial_count': int,      # Anzahl triviale (Gap=0)
                }
            },
            'stats': {
                'total_failure_cases': int,
                'trivial_cases': int,
                'unique_simulations': int,
                'duplicate_cases': int,
                'savings_percent': float,
            }
        }
    """
    seen_keys: dict[tuple, tuple] = {}  # sim_key → (num_trains, num_zub) wo zuerst gesehen
    scenarios = {}

    total_failures = 0
    total_trivial = 0
    total_new = 0
    total_duplicate = 0

    for n_trains in range(1, max_trains + 1):
        for n_zub in range(1, n_trains + 1):
            scenario = analyze_scenario(n_trains, n_zub)

            new_sims = 0
            duplicate_sims = 0
            trivial_count = 0

            for failure in scenario['failures']:
                total_failures += 1

                if failure['is_trivial']:
                    failure['needs_sim'] = False
                    failure['first_seen_at'] = None
                    trivial_count += 1
                    total_trivial += 1
                elif failure['sim_key'] in seen_keys:
                    failure['needs_sim'] = False
                    failure['first_seen_at'] = seen_keys[failure['sim_key']]
                    duplicate_sims += 1
                    total_duplicate += 1
                else:
                    failure['needs_sim'] = True
                    failure['first_seen_at'] = (n_trains, n_zub)
                    seen_keys[failure['sim_key']] = (n_trains, n_zub)
                    new_sims += 1
                    total_new += 1

            scenario['new_sims'] = new_sims
            scenario['duplicate_sims'] = duplicate_sims
            scenario['trivial_count'] = trivial_count
            scenarios[(n_trains, n_zub)] = scenario

    non_trivial = total_failures - total_trivial
    savings = (total_duplicate / non_trivial * 100) if non_trivial > 0 else 0

    return {
        'max_trains': max_trains,
        'unique_sims': set(seen_keys.keys()),
        'scenarios': scenarios,
        'stats': {
            'total_failure_cases': total_failures,
            'trivial_cases': total_trivial,
            'unique_simulations': total_new,
            'duplicate_cases': total_duplicate,
            'savings_percent': savings,
        }
    }


def print_analysis(max_trains: int):
    """Gibt die Analyse übersichtlich aus."""
    result = analyze_simulation_need(max_trains)
    stats = result['stats']

    print(f"\n{'='*70}")
    print(f"ZUB+-Simulationsbedarf — {max_trains} Züge")
    print(f"{'='*70}")
    print(f"Ausfallszenarien gesamt:     {stats['total_failure_cases']:>6}")
    print(f"  davon trivial (Gap=0):     {stats['trivial_cases']:>6}")
    print(f"  davon einzigartig:         {stats['unique_simulations']:>6}  ← müssen simuliert werden")
    print(f"  davon Duplikate:           {stats['duplicate_cases']:>6}  ← aus vorherigen übernehmen")
    print(f"Einsparung (nicht-trivial):  {stats['savings_percent']:>5.1f}%")
    print()

    # Einzigartige Simulationen pro Zuganzahl
    print(f"Einzigartige Simulationen pro Zuganzahl:")
    print(f"{'Züge':>5} | {'Unique':>6} | {'Keys (num_trains, gap)'}")
    print(f"{'-'*5}-+-{'-'*6}-+-{'-'*40}")

    for n_trains in range(1, max_trains + 1):
        keys = [(nt, g) for (nt, g) in result['unique_sims'] if nt == n_trains]
        keys.sort(key=lambda x: x[1])
        gaps = [str(g) for _, g in keys]
        print(f"{n_trains:>5} | {len(keys):>6} | Gaps: {', '.join(gaps) if gaps else '—'}")

    # Detail für kleine Zuganzahlen
    if max_trains <= 8:
        print(f"\n{'='*70}")
        print("Detail pro Szenario:")
        print(f"{'='*70}")
        for n_trains in range(1, max_trains + 1):
            for n_zub in range(1, n_trains + 1):
                sc = result['scenarios'][(n_trains, n_zub)]
                occ = sc['occupied']
                pattern = ''.join('B' if i in set(occ) else 'u' for i in range(n_trains))
                print(f"\n  {n_trains} Züge, {n_zub} ZUB+ [{pattern}]:")
                print(f"    Neu: {sc['new_sims']}, Duplikat: {sc['duplicate_sims']}, Trivial: {sc['trivial_count']}")
                for f in sc['failures']:
                    status = "TRIVIAL" if f['is_trivial'] else ("NEU" if f['needs_sim'] else f"DUPLIKAT von {f['first_seen_at']}")
                    fail_pattern = list(pattern)
                    fail_pattern[f['train_idx']] = fail_pattern[f['train_idx']].upper()
                    fail_str = ''.join(fail_pattern)
                    print(f"      Zug {f['train_idx']} fällt aus [{fail_str}]: Gap={f['gap']} → {status}")


# ===================================================================
# QUICK-TEST
# ===================================================================
if __name__ == "__main__":
    import sys
    max_t = 28
    if len(sys.argv) > 1:
        max_t = int(sys.argv[1])
    print_analysis(max_t)
