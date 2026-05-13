"""
validate_intervention.py — Analytische Validierung der Simulationsergebnisse.

Vergleicht die simulierte Interventionszeit mit einer analytisch berechneten
Erwartung basierend auf Stationspositionen, Gehgeschwindigkeit und Reaktionszeit.

Zwei Validierungsmodi:
  A) Legacy (SUMO_POS): Nutzt hardcodierte Odometer-Positionen und
     disruption_position_m.  Braucht einen globalen Geometriefaktor.
  B) km-korrigiert: Wenn die CSV disruption_km enthält, wird für Hin-Strecken
     direkt station.km (aus stations.py) vs disruption_km verglichen.
     Der Junction-Edge-Offset ist eliminiert → Geometriefaktor ≈ 1.0.

Methode:
    1. Für jedes erfolgreiche Szenario wird aus dem dispatched_agent_id die
       Gewinner-Station und Laufrichtung bestimmt.
    2. Die analytische Laufdistanz wird aus der Differenz zwischen
       Stationsposition und Störungsposition berechnet.
    3. Die erwartete Interventionszeit = Reaktionszeit + Distanz / Gehgeschwindigkeit.
    4. Vergleich mit der simulierten Interventionszeit (t_intervention_total_s).

Verwendung:
    python3 validate_intervention.py [pfad_zur_batch_csv]
"""

import csv
import re
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stations import STATIONS
from sa_distribution import distribute_agents

# ===================================================================
# PARAMETER
# ===================================================================
WALK_SPEED = 3.33      # m/s (AGBF-Hilfsfrist-Analogie, einheitlich SA + ZUB+)
REACTION_TIME = 90.0   # s (AGBF-Analogie, vorher 60 s)

# Tatsächliche SUMO-Positionen der Stationen auf dem Loop.
# Werte stammen aus stations.lap_pos_hin/rueck (gemessen via measure_umlauf.py).
SUMO_POS = {
    s_idx: (s.lap_pos_hin, s.lap_pos_rueck)
    for s_idx, s in enumerate(STATIONS)
}

# Wende-Bereiche: Positionen, an denen die analytische Berechnung nicht
# zuverlässig ist, weil die Gleisgeometrie stark abweicht.
WENDE_ZONES = [(0, 300), (7200, 8100), (14800, 15200)]

# Agent-ID Pattern: z.B. "station_agent_4_hin"
AGENT_PATTERN = re.compile(
    r'station_agent_(\d+)_(hin|rueck)'
)


# ===================================================================
# DATEN LADEN
# ===================================================================
def find_latest_csv(batch_dir: Path) -> Path:
    csvs = sorted(batch_dir.glob('*.csv'), key=lambda p: p.stat().st_mtime)
    if not csvs:
        print(f"FEHLER: Keine CSV in {batch_dir}")
        sys.exit(1)
    return csvs[-1]


def load_and_validate(csv_path: Path) -> dict:
    """
    Lädt die Batch-CSV, berechnet für jedes Szenario die analytische
    Erwartung und vergleicht mit der Simulation.

    Returns:
        Dict mit allen Ergebnissen und Statistiken.
    """
    with open(csv_path) as f:
        rows = list(csv.DictReader(f, delimiter=';'))

    total = len(rows)
    ok_rows = [r for r in rows if r['v_timeout'] == 'False'
               and r.get('dispatched_agent_id', '').strip()]

    results_all = []       # Alle auswertbaren Szenarien
    results_normal = []    # Nur Normalstrecke (kein Wende, dist ≥ 100m)
    results_wende = []     # Nur Wende-Bereiche
    errors = []

    results_km = []        # Full-km-Ergebnisse (mit Junction-Edges)

    for r in ok_rows:
        m = AGENT_PATTERN.match(r['dispatched_agent_id'])
        if not m:
            continue

        agent_idx = int(m.group(1))
        direction = m.group(2)
        num_agents = int(r['num_agents'])
        pos = float(r['disruption_position_m'])
        t_actual = float(r['t_intervention_total_s'])
        route_actual = float(r['route_length_m'])

        indices = distribute_agents(num_agents)
        if agent_idx >= len(indices):
            errors.append(f'agent_idx {agent_idx} out of range')
            continue
        station_idx = indices[agent_idx]
        station = STATIONS[station_idx]
        hin_pos, rueck_pos = SUMO_POS[station_idx]

        # Analytische Distanz: Betrag der Differenz zur Bahnsteigposition.
        # Mit findRoute-Routing kann der Agent in beide Richtungen laufen,
        # daher kein Vorzeichen-basierter rechts/links-Unterschied mehr.
        if direction == 'hin':
            expected_dist = abs(pos - hin_pos)
        elif direction == 'rueck':
            expected_dist = abs(pos - rueck_pos)
        else:
            continue

        if expected_dist < 0:
            errors.append(f'neg dist: pos={pos}, station={station.name}, '
                          f'dir={direction}, d={expected_dist:.0f}')
            continue

        expected_walk_time = expected_dist / WALK_SPEED
        expected_intervention = REACTION_TIME + expected_walk_time

        deviation_pct = ((t_actual - expected_intervention)
                         / expected_intervention * 100
                         if expected_intervention > 0 else 0.0)

        entry = {
            'pos': pos,
            'num_agents': num_agents,
            'station': station.name,
            'station_idx': station_idx,
            'direction': direction,
            'dist_expected': expected_dist,
            'dist_actual': route_actual,
            't_expected': expected_intervention,
            't_actual': t_actual,
            'deviation_pct': deviation_pct,
        }
        results_all.append(entry)

        # Wende-Bereich?
        is_wende = any(lo <= pos <= hi for lo, hi in WENDE_ZONES)
        if is_wende:
            results_wende.append(entry)
        elif expected_dist >= 100:
            results_normal.append(entry)

        # --- Full-km-Analyse (MIT Junction-Edges → exakte Laufdistanz) ---
        # Nutzt disruption_full_km und winner_station_full_km aus der CSV.
        raw_full_km = r.get('disruption_full_km', '')
        raw_station_fkm = r.get('winner_station_full_km', '')
        if (raw_full_km and raw_full_km.strip()
                and raw_station_fkm and raw_station_fkm.strip()):
            try:
                d_full_km = float(raw_full_km)
                s_full_km = float(raw_station_fkm)
            except ValueError:
                pass
            else:
                # Erwartete Laufdistanz inkl. Junction-Edges (Betrag).
                full_dist = abs(d_full_km - s_full_km)

                if full_dist > 0:
                    full_expected_t = REACTION_TIME + full_dist / WALK_SPEED
                    full_dev_pct = ((t_actual - full_expected_t) / full_expected_t * 100
                                   if full_expected_t > 0 else 0.0)
                    results_km.append({
                        'pos': pos,
                        'disruption_full_km': d_full_km,
                        'winner_station_full_km': s_full_km,
                        'num_agents': num_agents,
                        'station': station.name,
                        'station_idx': station_idx,
                        'direction': direction,
                        'dist_full': full_dist,
                        'dist_actual': route_actual,
                        't_expected_full': full_expected_t,
                        't_actual': t_actual,
                        'deviation_full_pct': full_dev_pct,
                        'is_wende': is_wende,
                    })

    # --- Korrekturfaktor (Geometrie) ---
    if results_normal:
        ratios = np.array([r['dist_actual'] / r['dist_expected']
                           for r in results_normal])
        correction = float(np.median(ratios))
    else:
        correction = 1.0

    # Korrigierte Abweichungen berechnen
    for r in results_all + results_normal + results_wende:
        corrected_dist = r['dist_expected'] * correction
        corrected_t = REACTION_TIME + corrected_dist / WALK_SPEED
        r['t_corrected'] = corrected_t
        r['dev_corrected_pct'] = ((r['t_actual'] - corrected_t)
                                  / corrected_t * 100
                                  if corrected_t > 0 else 0.0)

    # --- Winner-Validierung & Jammed-Winner-Analyse ---
    winner_checks = []
    jammed_winners = []

    for r in ok_rows:
        m = AGENT_PATTERN.match(r['dispatched_agent_id'])
        if not m:
            continue

        agent_idx = int(m.group(1))
        direction = m.group(2)
        num_agents = int(r['num_agents'])
        pos = float(r['disruption_position_m'])

        try:
            t_actual = float(r['t_intervention_total_s'])
            t_walk = float(r.get('t_walk_s', '0') or '0')
        except ValueError:
            continue

        indices = distribute_agents(num_agents)
        if agent_idx >= len(indices):
            continue
        actual_station_idx = indices[agent_idx]

        # Erwarteten Gewinner bestimmen: kürzeste analytische Distanz
        # zur Bahnsteigposition (Betrag, da findRoute beide Richtungen kann).
        best_dist = float('inf')
        best_station_idx = -1
        best_direction = ''

        for idx in indices:
            hin_p, rueck_p = SUMO_POS[idx]
            for d_name, d_pos in [('hin', hin_p), ('rueck', rueck_p)]:
                dist = abs(pos - d_pos)
                if dist < best_dist:
                    best_dist = dist
                    best_station_idx = idx
                    best_direction = d_name

        winner_correct = (actual_station_idx == best_station_idx)

        # Erwartete Laufzeit (mit Geometriefaktor)
        hin_p, rueck_p = SUMO_POS[actual_station_idx]
        if direction == 'hin':
            act_dist = abs(pos - hin_p)
        elif direction == 'rueck':
            act_dist = abs(pos - rueck_p)
        else:
            act_dist = 0

        if act_dist > 0:
            expected_walk = act_dist * correction / WALK_SPEED
            walk_ratio = t_walk / expected_walk if expected_walk > 0 else 1.0
        else:
            expected_walk = 0
            walk_ratio = 1.0

        # Prüfen ob Gewinner-Agent gejammt war
        jammed_list_str = r.get('v_jammed_agents', '')
        winner_jammed = r['dispatched_agent_id'] in jammed_list_str

        entry = {
            'pos': pos,
            'num_agents': num_agents,
            'winner_id': r['dispatched_agent_id'],
            'winner_station': STATIONS[actual_station_idx].name,
            'expected_station': (STATIONS[best_station_idx].name
                                 if best_station_idx >= 0 else '?'),
            'winner_correct': winner_correct,
            'direction': direction,
            't_actual': t_actual,
            't_walk': t_walk,
            'expected_walk': expected_walk,
            'walk_ratio': walk_ratio,
            'winner_jammed': winner_jammed,
            'jammed_count': int(r.get('v_jammed_count', '0') or '0'),
        }
        winner_checks.append(entry)
        if winner_jammed:
            jammed_winners.append(entry)

    return {
        'total_scenarios': total,
        'successful': len(ok_rows),
        'evaluated': len(results_all),
        'normal': results_normal,
        'wende': results_wende,
        'all': results_all,
        'errors': errors,
        'correction_factor': correction,
        'winner_checks': winner_checks,
        'jammed_winners': jammed_winners,
        'km_corrected': results_km,
    }


# ===================================================================
# REPORT
# ===================================================================
def print_report(data: dict, csv_name: str):
    """Gibt einen ausführlichen Validierungsbericht aus."""

    print("=" * 75)
    print("  ANALYTISCHE VALIDIERUNG DER SIMULATIONSERGEBNISSE")
    print(f"  Datenquelle: {csv_name}")
    print("=" * 75)

    print(f"\n1. ÜBERSICHT")
    print(f"   Szenarien gesamt:      {data['total_scenarios']}")
    print(f"   Davon erfolgreich:     {data['successful']}")
    print(f"   Auswertbar:            {data['evaluated']}")
    print(f"   Normalstrecke:         {len(data['normal'])}")
    print(f"   Wende-Bereiche:        {len(data['wende'])}")
    print(f"   Übersprungen (Fehler): {len(data['errors'])}")

    # Geometriefaktor
    cf = data['correction_factor']
    print(f"\n2. GEOMETRIEFAKTOR")
    print(f"   Median(dist_sim / dist_analytisch) = {cf:.4f}")
    print(f"   → Die SUMO-Strecke ist im Median {(cf - 1) * 100:.1f}% länger")
    print(f"     als die analytische Luftlinie zwischen Stationen.")
    print(f"   Ursache: Kurven, Bögen und Weichen im SUMO-Netzwerk,")
    print(f"   die die reale Tunnelgeometrie der U4 abbilden.")

    # Ergebnisse ohne Korrektur
    def stats(label, results, key='deviation_pct'):
        if not results:
            print(f"\n   {label}: keine Daten")
            return
        arr = np.array([r[key] for r in results])
        a = np.abs(arr)
        n = len(results)
        print(f"\n   {label} (n={n}):")
        print(f"     Mittelwert:   {np.mean(arr):+.2f}%")
        print(f"     Median:       {np.median(arr):+.2f}%")
        print(f"     Std.Abw.:     {np.std(arr):.2f}%")
        print(f"     Min/Max:      {np.min(arr):+.2f}% / {np.max(arr):+.2f}%")
        print(f"     Innerhalb ±1%:   {np.sum(a <= 1):5d} / {n} "
              f"({100 * np.sum(a <= 1) / n:.1f}%)")
        print(f"     Innerhalb ±5%:   {np.sum(a <= 5):5d} / {n} "
              f"({100 * np.sum(a <= 5) / n:.1f}%)")
        print(f"     Innerhalb ±10%:  {np.sum(a <= 10):5d} / {n} "
              f"({100 * np.sum(a <= 10) / n:.1f}%)")

    print(f"\n3. ERGEBNISSE OHNE GEOMETRIE-KORREKTUR")
    stats("Normalstrecke", data['normal'], 'deviation_pct')
    stats("Wende-Bereiche", data['wende'], 'deviation_pct')

    print(f"\n4. ERGEBNISSE MIT GEOMETRIE-KORREKTUR (×{cf:.4f})")
    stats("Normalstrecke", data['normal'], 'dev_corrected_pct')
    stats("Wende-Bereiche", data['wende'], 'dev_corrected_pct')

    # Top-10 Abweichungen
    print(f"\n5. TOP 10 GRÖSSTE ABWEICHUNGEN (Normalstrecke, korrigiert)")
    sorted_r = sorted(data['normal'],
                       key=lambda x: abs(x['dev_corrected_pct']),
                       reverse=True)
    for r in sorted_r[:10]:
        print(f"   pos={r['pos']:7.0f}m  ag={r['num_agents']:2d}  "
              f"{r['station']:22s}  {r['direction']:14s}  "
              f"d_exp={r['dist_expected']:6.0f}m  d_sim={r['dist_actual']:6.0f}m  "
              f"Δ={r['dev_corrected_pct']:+.1f}%")

    # --- 6. Winner-Validierung ---
    wc = data.get('winner_checks', [])
    if wc:
        correct = sum(1 for w in wc if w['winner_correct'])
        wrong = [w for w in wc if not w['winner_correct']]
        print(f"\n6. WINNER-VALIDIERUNG (richtiger Agent am Zug?)")
        print(f"   Auswertbar:         {len(wc)}")
        print(f"   Richtiger Gewinner: {correct} ({100 * correct / len(wc):.1f}%)")
        print(f"   Falscher Gewinner:  {len(wrong)} ({100 * len(wrong) / len(wc):.1f}%)")
        if wrong:
            print(f"\n   Top 10 falsche Gewinner:")
            wrong_sorted = sorted(wrong, key=lambda w: w['walk_ratio'], reverse=True)
            for w in wrong_sorted[:10]:
                print(f"     pos={w['pos']:7.0f}m  ag={w['num_agents']:2d}  "
                      f"Gewinner: {w['winner_station']:20s} ({w['direction']})  "
                      f"Erwartet: {w['expected_station']:20s}  "
                      f"Laufzeit-Ratio: {w['walk_ratio']:.2f}×")

    # --- 7. Laufzeit-Plausibilität ---
    if wc:
        # Nur Szenarien mit >100m Laufdistanz betrachten
        long_walks = [w for w in wc if w['expected_walk'] > 100]
        if long_walks:
            ratios = np.array([w['walk_ratio'] for w in long_walks])
            print(f"\n7. LAUFZEIT-PLAUSIBILITÄT (Laufzeit_sim / Laufzeit_erwartet)")
            print(f"   Auswertbar (Laufdist > 100m): {len(long_walks)}")
            print(f"   Median:     {np.median(ratios):.4f}×")
            print(f"   Mittelwert: {np.mean(ratios):.4f}×")
            print(f"   Min/Max:    {np.min(ratios):.4f}× / {np.max(ratios):.4f}×")
            print(f"   Std.Abw.:   {np.std(ratios):.4f}")
            print(f"   Innerhalb 0.95–1.05×: {np.sum((ratios >= 0.95) & (ratios <= 1.05)):5d} "
                  f"({100 * np.sum((ratios >= 0.95) & (ratios <= 1.05)) / len(long_walks):.1f}%)")
            print(f"   Innerhalb 0.90–1.10×: {np.sum((ratios >= 0.90) & (ratios <= 1.10)):5d} "
                  f"({100 * np.sum((ratios >= 0.90) & (ratios <= 1.10)) / len(long_walks):.1f}%)")

            slow = [w for w in long_walks if w['walk_ratio'] > 1.15]
            if slow:
                print(f"\n   Auffällig langsam (>1.15×): {len(slow)}")
                slow.sort(key=lambda w: w['walk_ratio'], reverse=True)
                for w in slow[:10]:
                    jam_txt = " ⚠ JAMMED" if w['winner_jammed'] else ""
                    print(f"     pos={w['pos']:7.0f}m  ag={w['num_agents']:2d}  "
                          f"{w['winner_station']:20s}  walk={w['t_walk']:.0f}s  "
                          f"erw={w['expected_walk']:.0f}s  "
                          f"ratio={w['walk_ratio']:.2f}×{jam_txt}")

    # --- 8. Jammed-Winner-Analyse ---
    jw = data.get('jammed_winners', [])
    if wc:
        print(f"\n8. JAMMED-WINNER-ANALYSE")
        print(f"   Gewinner-Agent gejammt: {len(jw)} / {len(wc)} "
              f"({100 * len(jw) / len(wc):.1f}%)")
        if jw:
            jw_times = np.array([w['t_actual'] for w in jw])
            nj = [w for w in wc if not w['winner_jammed']]
            nj_times = np.array([w['t_actual'] for w in nj]) if nj else np.array([0])
            print(f"   Jammed-Winner:     Mean={np.mean(jw_times):7.0f}s  "
                  f"Median={np.median(jw_times):7.0f}s  "
                  f"Max={np.max(jw_times):7.0f}s")
            if nj:
                print(f"   Nicht-Jammed:      Mean={np.mean(nj_times):7.0f}s  "
                      f"Median={np.median(nj_times):7.0f}s  "
                      f"Max={np.max(nj_times):7.0f}s")
                print(f"   Verzögerung (Median): "
                      f"+{np.median(jw_times) - np.median(nj_times):.0f}s")

            # Nach Agentenzahl aufschlüsseln
            print(f"\n   Jammed-Winner nach Agentenzahl:")
            for n in sorted(set(w['num_agents'] for w in jw)):
                subset = [w for w in jw if w['num_agents'] == n]
                total_n = sum(1 for w in wc if w['num_agents'] == n)
                times_n = [w['t_actual'] for w in subset]
                print(f"     {n:2d} Agent(en): {len(subset):3d} / {total_n} "
                      f"({100 * len(subset) / total_n:.1f}%)  "
                      f"Mean={np.mean(times_n):.0f}s  Max={max(times_n):.0f}s")

    # --- 9. FULL-km-ANALYSE (MIT Junction-Edges → exakte Laufdistanz) ---
    km_results = data.get('km_corrected', [])
    if km_results:
        # Nur Nicht-Wende, dist >= 100m
        km_normal = [r for r in km_results
                     if not r['is_wende'] and r['dist_full'] >= 100]
        km_wende = [r for r in km_results if r['is_wende']]
        print(f"\n9. FULL-km-ANALYSE (disruption_full_km vs winner_station_full_km)")
        print(f"   Auswertbar:      {len(km_results)} (alle Richtungen)")
        print(f"   Normalstrecke:   {len(km_normal)}")
        print(f"   Wende-Bereiche:  {len(km_wende)}")

        if km_normal:
            # Residual-Geometriefaktor (sollte jetzt ≈ 1.0 sein)
            km_ratios = np.array([r['dist_actual'] / r['dist_full']
                                  for r in km_normal if r['dist_full'] > 0])
            km_cf = float(np.median(km_ratios)) if len(km_ratios) > 0 else 1.0
            print(f"   Residual-Geometriefaktor: {km_cf:.4f} "
                  f"(Legacy: {cf:.4f})")
            print(f"   → Verbesserung: {(cf - km_cf) * 100:.2f} Prozentpunkte")

            # Abweichungen (kein Korrekturfaktor nötig!)
            km_devs = np.array([r['deviation_full_pct'] for r in km_normal])
            km_abs = np.abs(km_devs)
            print(f"\n   Abweichung (OHNE Korrekturfaktor):")
            print(f"     Mittelwert:  {np.mean(km_devs):+.2f}%")
            print(f"     Median:      {np.median(km_devs):+.2f}%")
            print(f"     Std.Abw.:    {np.std(km_devs):.2f}%")
            print(f"     Min/Max:     {np.min(km_devs):+.2f}% / {np.max(km_devs):+.2f}%")
            print(f"     ±1%:   {np.sum(km_abs <= 1):5d} / {len(km_normal)} "
                  f"({100 * np.sum(km_abs <= 1) / len(km_normal):.1f}%)")
            print(f"     ±5%:   {np.sum(km_abs <= 5):5d} / {len(km_normal)} "
                  f"({100 * np.sum(km_abs <= 5) / len(km_normal):.1f}%)")
            print(f"     ±10%:  {np.sum(km_abs <= 10):5d} / {len(km_normal)} "
                  f"({100 * np.sum(km_abs <= 10) / len(km_normal):.1f}%)")

            # Top Abweichungen
            sorted_km = sorted(km_normal,
                               key=lambda x: abs(x['deviation_full_pct']),
                               reverse=True)
            if sorted_km:
                print(f"\n   Top 5 Abweichungen:")
                for r in sorted_km[:5]:
                    print(f"     pos={r['pos']:7.0f}m  ag={r['num_agents']:2d}  "
                          f"{r['station']:22s}  {r['direction']:14s}  "
                          f"d_exp={r['dist_full']:6.0f}m  d_sim={r['dist_actual']:6.0f}m  "
                          f"Δ={r['deviation_full_pct']:+.1f}%")

    # Fazit
    normal = data['normal']
    if normal:
        arr_c = np.abs(np.array([r['dev_corrected_pct'] for r in normal]))
        pct10 = 100 * np.sum(arr_c <= 10) / len(normal)
        pct5 = 100 * np.sum(arr_c <= 5) / len(normal)
        print(f"\n{'=' * 75}")
        print(f"  FAZIT")
        print(f"{'=' * 75}")
        print(f"   Legacy (SUMO_POS + Geometriefaktor {cf:.4f}):")
        print(f"   → {pct10:.1f}% innerhalb ±10%, {pct5:.1f}% innerhalb ±5%")
        if jw:
            print(f"   → {len(jw)} Gewinner-Agenten gejammt (höhere Interventionszeiten).")

    if km_results:
        km_n = [r for r in km_results
                if not r['is_wende'] and r['dist_full'] >= 100]
        if km_n:
            km_a = np.abs(np.array([r['deviation_full_pct'] for r in km_n]))
            print(f"\n   Full-km-Analyse (mit Junction-Edges, OHNE Korrekturfaktor):")
            print(f"   → {100 * np.sum(km_a <= 5) / len(km_n):.1f}% innerhalb ±5%")
            print(f"   → {100 * np.sum(km_a <= 10) / len(km_n):.1f}% innerhalb ±10%")
            print(f"   → Kein Geometriefaktor mehr nötig.")

    print(f"\n{'=' * 75}")


# ===================================================================
# HAUPTPROGRAMM
# ===================================================================
if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parents[2]
    batch_dir = base_dir / 'output' / 'batch_results'

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = find_latest_csv(batch_dir)

    data = load_and_validate(csv_path)
    print_report(data, csv_path.name)
