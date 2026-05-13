"""
zub_expand.py — Expansion der reduzierten ZUB+-Simulation auf das SA-kompatible Raster.

Die ZUB+-Konvergenzläufe speichern nur die eindeutigen (num_trains, gap)-Tupel,
weil die Interventionszeit unter Umlauf-Symmetrie nur vom gerichteten Versatz im
Zug-Index abhängt. Für die Auswertung (Boxplot/CDF/Heatmap/Delta) wird daraus
das volle Raster (num_zub, train_idx, position) rekonstruiert:

  - Pro (num_trains, num_zub) liefert zub_verteilung.distribute_zub die
    Minimax-Indizes der besetzten Züge.
  - Zu jedem ausfallenden Zug (0..num_trains-1) wird der minimale GERICHTETE
    Vorwärtsabstand zu einem besetzten Zug berechnet:
        gap(d, z) = (z - d) mod num_trains
    Das entspricht der Simulationskonvention (main_zub.py::run_zub_scenario:
    disrupted = u4_1 / idx=0, ZUB+ = u4_{gap+1} / idx=gap).
  - Die zugehörige Interventionszeit wird aus der (num_trains, gap)-Zeile
    der Konvergenz-CSV übernommen.
  - Trivialfall gap=0 (ZUB+ sitzt im Zug): t_I = 0.

Achtung: Vorher wurde ein symmetrischer zyklischer Abstand
  min(|d-z| mod n, |z-d| mod n)
benutzt. Das ist falsch, weil die Simulation die gerichtete Vorwärtsdistanz
misst (ZUB+ fährt mit dem Zug bis zum Stau hinter dem gestörten Zug). Die
Rohdaten zeigen entsprechend starke Asymmetrie (z.B. für n=10: gap=1 →
4.6 min, gap=9 → 32.1 min).

Verwendung:
    from zub_expand import expand_csv, load_raw
    rows = expand_csv('output/convergence_zub_20260423_230246/conv_zub_0050m.csv', num_trains=10)

    # Oder als CLI zum Schreiben einer SA-kompatiblen CSV:
    python3 scripts/zub_expand.py [roh_csv] [num_trains] [out_csv]
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zub_verteilung import distribute_zub


def load_raw(csv_path: Path) -> dict[tuple[int, int], dict[float, float]]:
    """
    Liest die Konvergenz-CSV und gibt {(num_trains, gap): {position_m: t_s}} zurück.
    Ungültige Zeilen (t_intervention_total_s leer) werden übersprungen.
    """
    data: dict[tuple[int, int], dict[float, float]] = defaultdict(dict)
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            try:
                n = int(row['num_trains'])
                g = int(row['gap'])
                p = float(row['disruption_position_m'])
                t = float(row['t_intervention_total_s'])
            except (ValueError, TypeError, KeyError):
                continue
            data[(n, g)][p] = t
    return data


def expand(raw: dict[tuple[int, int], dict[float, float]],
           num_trains: int) -> list[dict]:
    """
    Expandiert die rohen (num_trains, gap)-Daten auf alle Kombinationen
    (num_zub, train_idx, position). Gibt Liste von Dicts zurück.
    """
    rows: list[dict] = []
    for num_zub in range(1, num_trains + 1):
        besetzt = set(distribute_zub(num_trains, num_zub))
        for train_idx in range(num_trains):
            if train_idx in besetzt:
                gap = 0
            else:
                # Gerichteter Vorwärtsgap: ZUB+ muss num_trains Positionen
                # vorwärts (in Fahrtrichtung) gehen, um den gestörten Zug zu
                # erreichen. Siehe main_zub.py::run_zub_scenario L134.
                gap = min((z - train_idx) % num_trains for z in besetzt)
            positions = raw.get((num_trains, gap), {})
            for pos, t in positions.items():
                rows.append({
                    'num_trains': num_trains,
                    'num_zub': num_zub,
                    'disruption_train_idx': train_idx,
                    'gap': gap,
                    'disruption_position_m': pos,
                    't_intervention_total_s': t,
                })
    return rows


def expand_csv(csv_path: Path, num_trains: int) -> list[dict]:
    """Convenience: load_raw + expand in einem Schritt."""
    return expand(load_raw(csv_path), num_trains)


def write_expanded_csv(rows: list[dict], out_path: Path) -> None:
    """Schreibt die expandierten Zeilen als SA-kompatible CSV (mit num_agents-Spalte)."""
    fieldnames = [
        'num_trains', 'num_zub', 'num_agents', 'disruption_train_idx', 'gap',
        'disruption_position_m', 't_intervention_total_s',
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for r in rows:
            # num_agents-Alias, damit SA-Plot-Skripte ohne Anpassung funktionieren
            r2 = dict(r)
            r2['num_agents'] = r['num_zub']
            writer.writerow(r2)


def find_latest_conv_csv(base: Path) -> Path:
    """
    Findet die neueste ZUB+-Konvergenz-CSV im output-Ordner.

    Priorisiert die kumulative Datei conv_zub_all.csv (alle Rasterstufen
    kombiniert bis zur Endstufe 25 m). Fällt auf conv_zub_0050m.csv zurück,
    falls keine kumulative Datei vorhanden ist.
    """
    for pattern in ('output/convergence_zub_*/conv_zub_all.csv',
                    'output/convergence_zub_*/conv_zub_0050m.csv'):
        candidates = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime)
        if candidates:
            return candidates[-1]
    raise FileNotFoundError(f'Keine ZUB+-Konvergenz-CSV unter {base}/output/')


if __name__ == '__main__':
    base = Path(__file__).resolve().parents[1]

    if len(sys.argv) > 1:
        raw_csv = Path(sys.argv[1])
    else:
        raw_csv = find_latest_conv_csv(base)

    num_trains = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    if len(sys.argv) > 3:
        out_csv = Path(sys.argv[3])
    else:
        out_csv = base / 'output' / 'zub_expanded' / f'zub_expanded_N{num_trains}.csv'

    print(f'Lese:      {raw_csv}')
    print(f'num_trains: {num_trains}')
    print(f'Schreibe:  {out_csv}')

    raw = load_raw(raw_csv)
    rows = expand(raw, num_trains)
    write_expanded_csv(rows, out_csv)

    print(f'Zeilen geschrieben: {len(rows)}')
