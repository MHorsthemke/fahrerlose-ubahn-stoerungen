"""
detect_faulty_results.py — Heuristische Fehlererkennung für Batch-Ergebnisse.

Prüft drei unabhängige Heuristiken:
  H1: CDF-Linearität      — Sättigung nahe 100% = Fehler
  H2: Theoretisches Maximum — Laufzeit über analytischem Max = Fehler
  H3: Monotonie            — Mehr Agenten dürfen max. Zeit nicht erhöhen

Verwendung:
    python3 detect_faulty_results.py [pfad_zur_batch_csv]

    Ohne Argument wird die neueste CSV in output/batch_results/ verwendet.
"""

import sys
import csv
import numpy as np
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stations import STATIONS, WENDEPUNKT_LINKS, WENDEPUNKT_RECHTS
from sa_distribution import distribute_agents

# ===================================================================
# KONSTANTEN
# ===================================================================
WALK_SPEED_MS = 3.33    # AGBF-Hilfsfrist-Analogie, einheitlich SA + ZUB+
REACTION_TIME_S = 90.0  # AGBF-Analogie (vorher 60 s)

# Schwellwerte (konfigurierbar)
THEORETICAL_MAX_TOLERANCE = 1.10     # 10% Toleranz für Geometriefaktor
CDF_R2_THRESHOLD = 0.95             # Mindest-R² für Linearität
CDF_TAIL_RATIO_THRESHOLD = 3.0      # Max. Tail-Streckung
MONOTONICITY_TOLERANCE_S = 0.0      # 0 = strikt

# Wendebereiche (Positionen mit bekannten Routing-Anomalien)
WENDE_ZONES = [(0, 300), (7200, 8100), (14800, 15200)]


# ===================================================================
# DATENLADEN
# ===================================================================
def find_latest_csv(batch_dir: Path) -> Path:
    csvs = sorted(batch_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not csvs:
        print(f"FEHLER: Keine CSV-Dateien in {batch_dir}")
        sys.exit(1)
    return csvs[-1]


def load_batch_data(csv_path: Path) -> tuple[
    dict[tuple[float, int], float],   # {(pos, n_agents): t_intervention_s}
    int,                               # total rows
    int,                               # timeouts
    int,                               # ohne agent
]:
    """Liest CSV und gibt Dict + Statistiken zurück."""
    data: dict[tuple[float, int], float] = {}
    total = 0
    timeouts = 0
    no_agent = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            total += 1
            if row.get("v_timeout", "").strip() == "True":
                timeouts += 1
                continue
            agent_id = row.get("dispatched_agent_id", "").strip()
            if not agent_id:
                no_agent += 1
                continue
            try:
                pos = float(row["disruption_position_m"])
                n = int(row["num_agents"])
                t = float(row["t_intervention_total_s"])
            except (ValueError, TypeError, KeyError):
                continue
            data[(pos, n)] = t

    return data, total, timeouts, no_agent


# ===================================================================
# HEURISTIK 2: THEORETISCHES MAXIMUM
# ===================================================================
def compute_theoretical_max() -> dict[int, float]:
    """Berechnet max. Interventionszeit pro Agentenzahl (analytisch)."""
    result: dict[int, float] = {}
    for num_agents in range(1, 11):
        indices = distribute_agents(num_agents)
        kms = [STATIONS[i].km for i in indices]
        max_dist = 0.0
        for j in range(len(kms)):
            links = WENDEPUNKT_LINKS if j == 0 else (kms[j - 1] + kms[j]) / 2
            rechts = WENDEPUNKT_RECHTS if j == len(kms) - 1 else (kms[j] + kms[j + 1]) / 2
            max_dist = max(max_dist, kms[j] - links, rechts - kms[j])
        result[num_agents] = REACTION_TIME_S + max_dist / WALK_SPEED_MS
    return result


def check_theoretical_max(
    data: dict[tuple[float, int], float],
    theo_max: dict[int, float],
) -> tuple[list[dict], dict[int, int]]:
    """Prüft ob Interventionszeiten das theoretische Maximum überschreiten.

    Returns:
        violations: Liste von Dicts mit pos, n, t_actual, t_max, excess_pct
        counts_per_n: Dict n_agents → Anzahl Verletzungen
    """
    violations: list[dict] = []
    counts: dict[int, int] = defaultdict(int)

    for (pos, n), t in sorted(data.items()):
        t_max = theo_max[n] * THEORETICAL_MAX_TOLERANCE
        if t > t_max:
            violations.append({
                "pos": pos, "n": n, "t_actual": t,
                "t_max_raw": theo_max[n], "t_max_tol": t_max,
                "excess_pct": (t - theo_max[n]) / theo_max[n] * 100,
            })
            counts[n] += 1

    return violations, dict(counts)


# ===================================================================
# HEURISTIK 3: MONOTONIE
# ===================================================================
def _is_wende(pos: float) -> bool:
    return any(lo <= pos <= hi for lo, hi in WENDE_ZONES)


def check_monotonicity(
    data: dict[tuple[float, int], float],
) -> tuple[list[dict], dict[str, int], dict[str, int], list[tuple[int, float]]]:
    """Prüft ob mehr Agenten die Interventionszeit erhöhen.

    Returns:
        violations:      Liste von Dicts mit pos, n_from, n_to, t_from, t_to, delta
        counts_normal:   Dict "n→n+1" → Anzahl Verletzungen (Normalstrecke)
        counts_wende:    Dict "n→n+1" → Anzahl Verletzungen (Wendebereiche)
        global_max:      Liste (n, max_t) sortiert nach n
    """
    positions = sorted(set(pos for pos, _ in data.keys()))
    agents = sorted(set(n for _, n in data.keys()))

    violations: list[dict] = []
    counts_normal: dict[str, int] = defaultdict(int)
    counts_wende: dict[str, int] = defaultdict(int)

    for i in range(len(agents) - 1):
        n_from = agents[i]
        n_to = agents[i + 1]
        label = f"{n_from}\u2192{n_to}"

        for pos in positions:
            t_from = data.get((pos, n_from))
            t_to = data.get((pos, n_to))
            if t_from is None or t_to is None:
                continue
            delta = t_to - t_from
            if delta > MONOTONICITY_TOLERANCE_S:
                entry = {
                    "pos": pos, "n_from": n_from, "n_to": n_to,
                    "t_from": t_from, "t_to": t_to, "delta": delta,
                    "wende": _is_wende(pos),
                }
                violations.append(entry)
                if entry["wende"]:
                    counts_wende[label] += 1
                else:
                    counts_normal[label] += 1

    # Globale Max-Zeiten pro Agentenzahl
    global_max: list[tuple[int, float]] = []
    for n in agents:
        times = [t for (p, na), t in data.items() if na == n]
        if times:
            global_max.append((n, max(times)))

    return violations, dict(counts_normal), dict(counts_wende), global_max


# ===================================================================
# HEURISTIK 1: CDF-LINEARITÄT
# ===================================================================
def check_cdf_linearity(
    data: dict[tuple[float, int], float],
) -> list[dict]:
    """Prüft CDF-Linearität pro Agentenzahl.

    Returns:
        Liste von Dicts mit n, r2, tail_ratio, flag, n_samples
    """
    # Gruppieren nach Agentenzahl
    by_agents: dict[int, list[float]] = defaultdict(list)
    for (_, n), t in data.items():
        by_agents[n].append(t)

    results: list[dict] = []

    for n in sorted(by_agents.keys()):
        times = sorted(by_agents[n])
        count = len(times)
        if count < 10:
            results.append({"n": n, "r2": 0.0, "tail_ratio": 0.0,
                            "flag": True, "n_samples": count, "reason": "zu wenig Daten"})
            continue

        arr = np.array(times)
        cdf_y = np.arange(1, count + 1) / count

        # R² der linearen Regression (x=Interventionszeit, y=CDF)
        coeffs = np.polyfit(arr, cdf_y, 1)
        fitted = np.polyval(coeffs, arr)
        ss_res = np.sum((cdf_y - fitted) ** 2)
        ss_tot = np.sum((cdf_y - np.mean(cdf_y)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # Tail-Ratio (Sättigungserkennung)
        p25 = np.percentile(arr, 25)
        p75 = np.percentile(arr, 75)
        p90 = np.percentile(arr, 90)
        p100 = np.max(arr)

        main_range = p75 - p25
        tail_range = p100 - p90
        expected_tail = main_range * (10.0 / 50.0) if main_range > 0 else 1.0
        tail_ratio = tail_range / expected_tail if expected_tail > 0 else 0.0

        flag = r2 < CDF_R2_THRESHOLD or tail_ratio > CDF_TAIL_RATIO_THRESHOLD
        reason = ""
        if r2 < CDF_R2_THRESHOLD:
            reason += f"R²={r2:.3f}<{CDF_R2_THRESHOLD}"
        if tail_ratio > CDF_TAIL_RATIO_THRESHOLD:
            if reason:
                reason += ", "
            reason += f"Tail={tail_ratio:.1f}>{CDF_TAIL_RATIO_THRESHOLD}"

        results.append({
            "n": n, "r2": r2, "tail_ratio": tail_ratio,
            "flag": flag, "n_samples": count, "reason": reason,
        })

    return results


# ===================================================================
# REPORT
# ===================================================================
SEP = "=" * 73


def print_report(
    csv_name: str,
    total: int, timeouts: int, no_agent: int,
    data: dict[tuple[float, int], float],
    theo_max: dict[int, float],
    h2_violations: list[dict], h2_counts: dict[int, int],
    h3_violations: list[dict], h3_normal: dict[str, int],
    h3_wende: dict[str, int], h3_global_max: list[tuple[int, float]],
    h1_results: list[dict],
):
    auswertbar = len(data)
    positions = len(set(pos for pos, _ in data.keys()))
    agents = sorted(set(n for _, n in data.keys()))

    print(f"\n{SEP}")
    print(f"  HEURISTISCHE FEHLERERKENNUNG \u2014 BATCH-VALIDIERUNG")
    print(f"  Datenquelle: {csv_name}")
    print(f"  Szenarien: {total} | Positionen: {positions} | "
          f"Agentenzahlen: {', '.join(map(str, agents))}")
    print(SEP)

    # --- 1. Vorfilter ---
    print(f"\n1. VORFILTER")
    print(f"   Gesamt:       {total}")
    print(f"   Timeouts:     {timeouts}")
    print(f"   Ohne Agent:   {no_agent}")
    print(f"   Auswertbar:   {auswertbar}")

    # --- 2. Theoretisches Maximum (H2) ---
    print(f"\n2. THEORETISCHES MAXIMUM (Heuristik 2)")
    print(f"   Toleranz: {THEORETICAL_MAX_TOLERANCE:.0%}")
    print()
    for n in sorted(theo_max.keys()):
        t_raw = theo_max[n]
        t_tol = t_raw * THEORETICAL_MAX_TOLERANCE
        verletzt = h2_counts.get(n, 0)
        flag = f"  \u2717 {verletzt} Verletzungen" if verletzt > 0 else ""
        print(f"   n={n:2d}: Max={t_raw:7.1f}s ({t_raw/60:5.1f} min) "
              f"  mit Toleranz={t_tol:7.1f}s{flag}")

    total_h2 = len(h2_violations)
    print(f"\n   Verletzungen: {total_h2} / {auswertbar}"
          f" ({total_h2/auswertbar*100:.1f}%)" if auswertbar > 0 else "")

    if h2_violations:
        print(f"\n   Top 10 Verletzungen:")
        for v in sorted(h2_violations, key=lambda x: -x["excess_pct"])[:10]:
            print(f"     pos={v['pos']:8.0f}m  n={v['n']:2d}  "
                  f"t={v['t_actual']:7.1f}s  max={v['t_max_raw']:7.1f}s  "
                  f"excess={v['excess_pct']:+.1f}%")

    # --- 3. Monotonie (H3) ---
    print(f"\n3. MONOTONIE (Heuristik 3)")
    print(f"   Globale Max-Zeiten pro Agentenzahl:")
    prev_max = None
    for n, max_t in h3_global_max:
        flag = ""
        if prev_max is not None and max_t > prev_max:
            flag = f"  \u2717 STEIGT (+{max_t - prev_max:.1f}s)"
        print(f"     n={n:2d}: {max_t:7.1f}s ({max_t/60:5.1f} min){flag}")
        prev_max = max_t

    total_h3 = len(h3_violations)
    total_normal = sum(h3_normal.values())
    total_wende = sum(h3_wende.values())
    print(f"\n   Per-Position-Verletzungen: {total_h3}")
    print(f"     Normalstrecke:  {total_normal}")
    print(f"     Wendebereiche:  {total_wende}")

    if h3_normal or h3_wende:
        print(f"\n   Aufschlüsselung nach Übergang:")
        all_labels = sorted(set(list(h3_normal.keys()) + list(h3_wende.keys())))
        for label in all_labels:
            nn = h3_normal.get(label, 0)
            nw = h3_wende.get(label, 0)
            print(f"     {label}: {nn + nw} (Normal: {nn}, Wende: {nw})")

    if h3_violations:
        top = sorted(
            [v for v in h3_violations if not v["wende"]],
            key=lambda x: -x["delta"],
        )[:10]
        if top:
            print(f"\n   Top 10 Verletzungen (Normalstrecke):")
            for v in top:
                print(f"     pos={v['pos']:8.0f}m  {v['n_from']}\u2192{v['n_to']}  "
                      f"t({v['n_from']})={v['t_from']:7.1f}s  "
                      f"t({v['n_to']})={v['t_to']:7.1f}s  "
                      f"\u0394={v['delta']:+.1f}s")

    # --- 4. CDF-Linearität (H1) ---
    print(f"\n4. CDF-LINEARIT\u00c4T (Heuristik 1)")
    print(f"   Schwellen: R\u00b2 \u2265 {CDF_R2_THRESHOLD}, "
          f"Tail-Ratio \u2264 {CDF_TAIL_RATIO_THRESHOLD}")
    print()
    n_flagged = 0
    for r in h1_results:
        status = "\u2717 AUFF\u00c4LLIG" if r["flag"] else "\u2713 OK"
        if r["flag"]:
            n_flagged += 1
        print(f"   n={r['n']:2d}: R\u00b2={r['r2']:.4f}  "
              f"Tail-Ratio={r['tail_ratio']:5.2f}  "
              f"n={r['n_samples']:4d}  {status}"
              + (f"  ({r['reason']})" if r["reason"] else ""))

    print(f"\n   Auff\u00e4llig: {n_flagged} / {len(h1_results)} Agentenkonfigurationen")

    # --- Zusammenfassung ---
    print(f"\n{SEP}")
    print(f"  ZUSAMMENFASSUNG")
    print(f"{SEP}")

    h1_ok = n_flagged == 0
    h2_ok = total_h2 == 0
    h3_ok = total_normal == 0  # Wende-Verletzungen separat

    h1_str = "\u2713 BESTANDEN" if h1_ok else f"\u2717 {n_flagged} AUFF\u00c4LLIG"
    h2_str = "\u2713 BESTANDEN" if h2_ok else f"\u2717 {total_h2} VERLETZUNGEN"
    h3_str = "\u2713 BESTANDEN" if h3_ok else f"\u2717 {total_normal} VERLETZUNGEN (Normal)"
    if total_wende > 0:
        h3_str += f" + {total_wende} Wende"

    print(f"   Heuristik 1 (CDF):       {h1_str}")
    print(f"   Heuristik 2 (Maximum):   {h2_str}")
    print(f"   Heuristik 3 (Monotonie): {h3_str}")

    all_ok = h1_ok and h2_ok and h3_ok
    if all_ok:
        print(f"\n   \u2192 Batch sieht PLAUSIBEL aus.")
    else:
        print(f"\n   \u2192 Batch enth\u00e4lt AUFF\u00c4LLIGE Ergebnisse \u2014 manuelle Pr\u00fcfung empfohlen.")

    print(SEP)


# ===================================================================
# HAUPTPROGRAMM
# ===================================================================
if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[2]
    batch_dir = base_dir / "output" / "batch_results"

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = find_latest_csv(batch_dir)

    print(f"CSV: {csv_path}")

    # Daten laden
    data, total, timeouts, no_agent = load_batch_data(csv_path)
    if not data:
        print("FEHLER: Keine auswertbaren Daten!")
        sys.exit(1)

    # Heuristiken ausführen
    theo_max = compute_theoretical_max()
    h2_violations, h2_counts = check_theoretical_max(data, theo_max)
    h3_violations, h3_normal, h3_wende, h3_global_max = check_monotonicity(data)
    h1_results = check_cdf_linearity(data)

    # Report
    print_report(
        csv_path.name,
        total, timeouts, no_agent,
        data, theo_max,
        h2_violations, h2_counts,
        h3_violations, h3_normal, h3_wende, h3_global_max,
        h1_results,
    )
