"""
convergence.py — Raster-Konvergenzstudie für das Positions-Raster.

Führt eine Halbierungs-Reihe 1600 → 800 → 400 → 200 → 100 → 50 → 25 m
durch. Pro Stufe werden nur NEUE Positionen simuliert (keine Dopplungen),
da die Simulation deterministisch ist.

Konvergenzkriterium (pro Gruppe, z.B. Agentenzahl oder (num_trains, gap)):
  1. Kolmogorov-Smirnov-Distanz der kumulativen Verteilung zwischen
     zwei aufeinanderfolgenden Stufen ≤ 5 %-Punkte.
     → Deckt die gesamte Verteilungsform ab (entspricht "die CDF-Kurve
       im Diagramm ändert sich nicht mehr nennenswert").
  2. Relative Änderung von max(t_I) ≤ 5 %.
     → Fängt Ausreißer im Tail, die KS nur schwach sieht (wichtig für
       den AGBF-Erreichungsgrad in Kap. 5).

Abbruch: Sobald BEIDE Kriterien für ALLE Gruppen erfüllt sind,
gilt das gröbere Raster der vorherigen Stufe als ausreichend.

Zwei Varianten (variant=):
  "sa"  — Stationsagenten, Gruppierung nach num_agents
  "zub" — ZUB+, Gruppierung nach (num_trains, gap)
Helper (_ks_distance, _relative_delta, _check_convergence, _read_csv_grouped)
sind generisch und werden von beiden Varianten geteilt.
"""

import bisect
import csv
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from batch import run_parallel as run_parallel_sa


log = logging.getLogger(__name__)


# Raster-Halbierungsreihe, grob bis fein.
STAGES_M = [1600, 800, 400, 200, 100, 50, 25]

# Konvergenzschwellen.
KS_THRESHOLD = 0.05       # KS-Distanz ≤ 5 %-Punkte (also 0.05 als Anteil)
MAX_THRESHOLD = 0.05      # Relative Änderung von max(t_I) ≤ 5 %


# ===================================================================
# GENERISCHE HELPER
# ===================================================================

def _new_positions(stage_idx: int, max_m: int) -> list[int]:
    """Positionen, die in dieser Stufe neu hinzukommen (keine Dopplungen)."""
    step_m = STAGES_M[stage_idx]
    if stage_idx == 0:
        return list(range(0, max_m, step_m))
    prev_step = STAGES_M[stage_idx - 1]
    return list(range(step_m, max_m, prev_step))


def _read_csv_grouped(csv_path: Path,
                      group_cols: tuple[str, ...]
                      ) -> dict[tuple, list[float]]:
    """
    Liest t_intervention_total_s gruppiert nach einem Tupel von Spalten.
    None/leere Werte und Fehler-Zeilen werden übersprungen.

    group_cols=("num_agents",) → Keys sind 1-Tupel wie (3,)
    group_cols=("num_trains","gap") → Keys sind 2-Tupel wie (5, 2)
    """
    grouped: dict[tuple, list[float]] = defaultdict(list)
    if not csv_path.exists():
        return grouped
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            t = row.get("t_intervention_total_s")
            if not t or t.strip().lower() == "none":
                continue
            # gap=0-Fälle sind per MA-Definition trivial (ZUB+ bereits an
            # Bord des gestörten Zuges, t_I=0) und werden aus der Konvergenz-
            # analyse ausgeschlossen: 760 identische Nullen würden KS-Distanz
            # und Δmax künstlich verkleinern.
            if "gap" in row and row["gap"].strip() == "0":
                continue
            try:
                key = tuple(int(row[c]) for c in group_cols)
                grouped[key].append(float(t))
            except (ValueError, TypeError, KeyError):
                continue
    return grouped


def _ks_distance(a: list[float], b: list[float]) -> float:
    """
    Kolmogorov-Smirnov-Distanz zwischen zwei Stichproben.

    Größter vertikaler Abstand zwischen den empirischen CDFs.
    Ergebnis in [0, 1] — entspricht dem max. senkrechten Unterschied
    der beiden CDF-Kurven, wie man ihn im Diagramm ablesen würde
    (0.05 = 5 Prozentpunkte).
    """
    if not a or not b:
        return float("inf")

    a_sorted = sorted(a)
    b_sorted = sorted(b)
    na, nb = len(a_sorted), len(b_sorted)

    # CDF-Werte an allen Sprungstellen vergleichen (Vereinigung der Stichproben).
    d_max = 0.0
    for x in set(a_sorted) | set(b_sorted):
        ca = bisect.bisect_right(a_sorted, x) / na
        cb = bisect.bisect_right(b_sorted, x) / nb
        d = abs(ca - cb)
        if d > d_max:
            d_max = d
    return d_max


def _relative_delta(new: float, old: float) -> float:
    """Relative Änderung |new - old| / |old|."""
    if old == 0:
        return float("inf") if new != 0 else 0.0
    return abs(new - old) / abs(old)


def _check_convergence(prev: dict[tuple, list[float]],
                       curr: dict[tuple, list[float]]
                       ) -> tuple[bool, list[dict]]:
    """
    Prüft Konvergenz pro Gruppe: KS ≤ KS_THRESHOLD UND Δmax ≤ MAX_THRESHOLD.

    Returns:
        (converged, details) — converged=True wenn beide Kriterien für
        ALLE Gruppen erfüllt sind. details ist eine Liste von Dicts mit
        Feldern: group, n_curr, ks, d_max, ok.
    """
    details = []
    all_ok = True
    for key in sorted(curr.keys()):
        curr_v = curr[key]
        prev_v = prev.get(key, [])
        if not prev_v or not curr_v:
            details.append({"group": key, "n_curr": len(curr_v),
                            "ks": float("inf"), "d_max": float("inf"),
                            "ok": False})
            all_ok = False
            continue
        ks = _ks_distance(prev_v, curr_v)
        d_max = _relative_delta(max(curr_v), max(prev_v))
        ok = ks <= KS_THRESHOLD and d_max <= MAX_THRESHOLD
        details.append({"group": key, "n_curr": len(curr_v),
                        "ks": ks, "d_max": d_max, "ok": ok})
        if not ok:
            all_ok = False
    return all_ok, details


def _format_group(key: tuple) -> str:
    """Human-lesbares Label für eine Gruppen-Tupel-Schlüssel."""
    if len(key) == 1:
        return str(key[0])
    return "(" + ",".join(str(k) for k in key) + ")"


def _cumulative_stats(csv_paths: list[Path], variant: str) -> dict:
    """
    Liest alle bislang erzeugten Stufen-CSVs und gibt die kumulativen
    Maxima (t_I, t_walk, route_length) plus den Worst-Case-Datensatz zurück.

    Wird nach jedem Stufenende aufgerufen, damit das Konvergenzfenster
    eine Zeile mit dem aktuellen Stand anzeigen kann.
    """
    n_total = 0
    t_i_max = 0.0
    t_walk_max = 0.0
    walk_max_m = 0.0
    wc_row: dict | None = None
    wc_t = -1.0
    for p in csv_paths:
        if not p.exists():
            continue
        with open(p, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                t = row.get("t_intervention_total_s")
                if not t or t.strip().lower() == "none":
                    continue
                if "gap" in row and row["gap"].strip() == "0":
                    continue
                try:
                    ti = float(t)
                except ValueError:
                    continue
                n_total += 1
                if ti > wc_t:
                    wc_t = ti
                    wc_row = row
                if ti > t_i_max:
                    t_i_max = ti
                tw = row.get("t_walk_s", "")
                if tw:
                    try:
                        t_walk_max = max(t_walk_max, float(tw))
                    except ValueError:
                        pass
                rl = row.get("route_length_m", "")
                if rl:
                    try:
                        walk_max_m = max(walk_max_m, float(rl))
                    except ValueError:
                        pass

    if wc_row is None:
        wc_str = "—"
    elif variant == "sa":
        pid = wc_row.get("dispatched_agent_id", "")
        pid_short = pid.replace("station_agent_", "") if pid else ""
        wc_str = (f"Pos={float(wc_row['disruption_position_m']):>7.1f} "
                  f"Ag={wc_row['num_agents']} ({pid_short})")
    else:
        wc_str = (f"Pos={float(wc_row['disruption_position_m']):>7.1f} "
                  f"(n={wc_row['num_trains']},g={wc_row.get('gap','?')})")

    return {
        "n_total": n_total,
        "t_i_max": t_i_max,
        "t_walk_max": t_walk_max,
        "walk_max_m": walk_max_m,
        "wc_str": wc_str,
    }


# ===================================================================
# RUNNER-ABSTRAKTION
# ===================================================================

def _runner_sa(exp, new_pos: list[int], csv_path: Path,
               progress_callback=None) -> None:
    """Simuliert eine Stufe des SA-Batches (run_parallel aus batch.py)."""
    run_parallel_sa(
        positions_m=new_pos,
        step_length_s=exp.batch_step_length_s,
        agent_counts=exp.batch_agent_counts,
        train_counts=exp.batch_train_counts,
        disruption_lap=exp.batch_disruption_lap,
        num_workers=exp.batch_num_workers,
        agent_walk_speed_ms=exp.agent_walk_speed_ms,
        agent_reaction_time_s=exp.agent_reaction_time_s,
        csv_path=csv_path,
        use_gui=False,
        progress_callback=progress_callback,
    )


def _runner_zub(exp, new_pos: list[int], csv_path: Path,
                progress_callback=None) -> None:
    """Simuliert eine Stufe des ZUB+-Batches (run_parallel aus main_zub.py)."""
    # Late import, damit SA-Läufe nicht von main_zub abhängen.
    from main_zub import run_parallel as run_parallel_zub
    max_trains = getattr(exp, "batch_zub_max_trains", 10)
    run_parallel_zub(
        max_trains=max_trains,
        positions_m=new_pos,
        csv_path=csv_path,
        progress_callback=progress_callback,
    )


# (variant) → (Beschreibung, CSV-Präfix, Runner, Gruppenspalten)
_VARIANTS = {
    "sa": {
        "label": "Stationsagenten",
        "prefix": "sa",
        "runner": _runner_sa,
        "group_cols": ("num_agents",),
        "group_hdr": "Ag",
    },
    "zub": {
        "label": "ZUB+",
        "prefix": "zub",
        "runner": _runner_zub,
        "group_cols": ("num_trains", "gap"),
        "group_hdr": "(n,g)",
    },
}


# ===================================================================
# HAUPTABLAUF
# ===================================================================

def run_convergence(exp, base_dir: Path, variant: str = "sa",
                    window=None) -> Path:
    """
    Führt die Raster-Konvergenzstudie durch und schreibt den Report ins Log.

    variant:
      "sa"  — Stationsagenten, Gruppierung nach num_agents
      "zub" — ZUB+, Gruppierung nach (num_trains, gap)
    window: optionales ConvergenceProgressWindow für Live-Fortschritt.
    """
    if variant not in _VARIANTS:
        raise ValueError(f"Unbekannte Variante: {variant} "
                         f"(erlaubt: {list(_VARIANTS.keys())})")
    v = _VARIANTS[variant]
    group_cols = v["group_cols"]
    runner = v["runner"]

    max_m = exp.batch_positions_max_m
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = base_dir / "output" / f"convergence_{variant}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 70)
    log.info(f"RASTER-KONVERGENZSTUDIE ({v['label']})")
    log.info(f"Stufen: {STAGES_M} m")
    if variant == "sa":
        log.info(f"Agenten: {exp.batch_agent_counts}")
        log.info(f"Züge:    {exp.batch_train_counts}")
    else:
        log.info(f"max_trains: {getattr(exp, 'batch_zub_max_trains', 10)}  "
                 f"(alle (n, gap) mit 2 ≤ n ≤ max_trains, 1 ≤ gap ≤ n-1)")
    log.info(f"Abbruch-Schwellen: KS ≤ {KS_THRESHOLD*100:.0f} %-Punkte "
             f"UND Δmax ≤ {MAX_THRESHOLD*100:.0f} % "
             f"(für ALLE Gruppen)")
    log.info(f"Ausgabe-Ordner: {out_dir}")
    log.info("=" * 70)

    history: list[dict] = []
    prev_by_group: dict[tuple, list[float]] = {}
    csv_paths_so_far: list[Path] = []

    converged_step_m: int | None = None
    last_step_m: int | None = None
    for i, step_m in enumerate(STAGES_M):
        new_pos = _new_positions(i, max_m)

        log.info("")
        log.info(f"--- Stufe {i+1}/{len(STAGES_M)}: {step_m} m — "
                 f"{len(new_pos)} neue Positionen ---")

        csv_path = out_dir / f"conv_{v['prefix']}_{step_m:04d}m.csv"

        def _cb(done, total, ok, failed, anomaly, t_values,
                _i=i, _step_m=step_m):
            if window is None:
                return
            if done == 0:
                window.set_stage(variant, _i + 1, _step_m, total)
            else:
                window.update_scenarios(done)

        runner(exp, new_pos, csv_path,
               progress_callback=_cb if window is not None else None)
        last_step_m = step_m
        csv_paths_so_far.append(csv_path)

        # Neue Werte einlesen und auf bisherige aufaddieren → Stand nach dieser Stufe.
        stage_by_group = _read_csv_grouped(csv_path, group_cols)
        curr_by_group: dict[tuple, list[float]] = {}
        for key in set(prev_by_group.keys()) | set(stage_by_group.keys()):
            curr_by_group[key] = prev_by_group.get(key, []) \
                + stage_by_group.get(key, [])

        cum = _cumulative_stats(csv_paths_so_far, variant)

        if i == 0:
            log.info(f"  Stufe {step_m} m: Basis gesetzt "
                     f"(noch kein Vergleich mit Vorgänger möglich).")
            history.append({"step_m": step_m, "details": None})
            if window is not None and hasattr(window, "add_stage_result"):
                window.add_stage_result(
                    step_m, cum["n_total"], None, None,
                    cum["t_i_max"], cum["t_walk_max"], cum["walk_max_m"],
                    cum["wc_str"])
            prev_by_group = curr_by_group
            continue

        converged, details = _check_convergence(prev_by_group, curr_by_group)
        history.append({"step_m": step_m, "details": details})
        max_ks = max(d["ks"] for d in details)
        max_dmax = max(d["d_max"] for d in details)
        log.info(f"  max KS: {max_ks*100:5.2f} %-Punkte  |  "
                 f"max Δmax: {max_dmax*100:5.2f} %")

        if window is not None and hasattr(window, "add_stage_result"):
            window.add_stage_result(
                step_m, cum["n_total"], max_ks, max_dmax,
                cum["t_i_max"], cum["t_walk_max"], cum["walk_max_m"],
                cum["wc_str"])

        if converged:
            log.info(f"*** KONVERGENZ erreicht bei Raster {step_m} m ***")
            log.info(f"Empfehlung: Raster {STAGES_M[i-1]} m reicht aus "
                     f"(Verfeinerung auf {step_m} m änderte CDF und "
                     f"max(t_I) je Gruppe um ≤ {KS_THRESHOLD*100:.0f} %).")
            prev_by_group = curr_by_group
            converged_step_m = STAGES_M[i-1]
            break

        prev_by_group = curr_by_group

    if window is not None:
        window.mark_variant_done(variant,
                                 converged_at=converged_step_m or last_step_m)

    _print_report(history, out_dir, v["group_hdr"])
    return out_dir


def _print_report(history: list[dict], out_dir: Path,
                  group_hdr: str) -> None:
    log.info("")
    log.info("=" * 70)
    log.info("KONVERGENZ-REPORT")
    log.info("=" * 70)
    log.info(f"{'Raster':>8} | {group_hdr:>7} | {'n':>5} | "
             f"{'KS':>9} | {'Δmax':>8} | {'OK':>4}")
    log.info("-" * 70)
    for h in history:
        step_m = h["step_m"]
        details = h["details"]
        if details is None:
            log.info(f"{step_m:>6} m | {'—':>7} | {'—':>5} | "
                     f"{'(Basis)':>9} | {'—':>8} | {'—':>4}")
            continue
        for d in details:
            ks_str = (f"{d['ks']*100:>6.2f} %" if d['ks'] != float('inf')
                      else "   inf  ")
            dm_str = (f"{d['d_max']*100:>5.2f} %" if d['d_max'] != float('inf')
                      else "  inf  ")
            ok_str = "OK" if d["ok"] else "FAIL"
            log.info(f"{step_m:>6} m | {_format_group(d['group']):>7} | "
                     f"{d['n_curr']:>5} | "
                     f"{ks_str:>9} | {dm_str:>8} | {ok_str:>4}")
    log.info("=" * 70)
    log.info(f"CSVs: {out_dir}")
