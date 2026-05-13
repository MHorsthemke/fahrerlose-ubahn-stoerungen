"""
run_all_parallel.py — Startet alle Simulationen unabhängig voneinander.

  python run_all_parallel.py

Ablauf:
  1. Station-Agent Parallel-Batch         (main.py --parallel)
  2. ZUB+ Parallel-Batch                  (main_zub.py --parallel)
  3. ZUB+ Positionsinvarianz-Validierung  (validate_position_invariance.py)

Alle laufen nacheinander (nicht gleichzeitig), damit jeder Batch
alle CPU-Kerne nutzen kann. Wenn einer fehlschlägt, werden die anderen
trotzdem gestartet.

Ergebnisse:
  output/batch_results/parallel_<timestamp>.csv          (Station-Agent)
  output/zub_results/zub_parallel_<timestamp>.csv         (ZUB+)
  output/validation/position_invariance_<timestamp>.csv   (Validierung)
  output/agent_logs/pos{P}_ag{A}_tr{T}/                   (SUMO-Logs Station-Agent)
  output/zub_logs/n{N}_g{G}/                               (SUMO-Logs ZUB+)
"""

import subprocess
import sys
import time
import os


def run_batch(name: str, cmd: list[str]) -> dict:
    """Startet einen Batch als Subprozess."""
    print(f"\n{'#' * 60}")
    print(f"  STARTE: {name}")
    print(f"  Befehl: {' '.join(cmd)}")
    print(f"{'#' * 60}\n")

    start = time.time()
    try:
        result = subprocess.run(cmd, check=True)
        elapsed = time.time() - start
        return {
            "name": name,
            "status": "OK",
            "elapsed_s": elapsed,
            "returncode": 0,
        }
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        print(f"\n⚠ {name} fehlgeschlagen (Code {e.returncode})")
        return {
            "name": name,
            "status": "FEHLER",
            "elapsed_s": elapsed,
            "returncode": e.returncode,
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n⚠ {name} Ausnahme: {e}")
        return {
            "name": name,
            "status": f"AUSNAHME: {e}",
            "elapsed_s": elapsed,
            "returncode": -1,
        }


def main():
    """Startet beide Batches nacheinander mit Fehler-Isolation."""
    print("=" * 60)
    print("  GESAMTLAUF: Station-Agent + ZUB+ + Validierung")
    print("=" * 60)

    total_start = time.time()

    # CLI-Argumente durchreichen (z.B. --max 15)
    extra_args = sys.argv[1:]

    batches = [
        ("Station-Agent", [sys.executable, "main.py", "--parallel"] + extra_args),
        ("ZUB+", [sys.executable, "main_zub.py", "--parallel"] + extra_args),
        ("Validierung (Positionsinvarianz)",
         [sys.executable, "validate_position_invariance.py"]),
    ]

    results = []
    for name, cmd in batches:
        r = run_batch(name, cmd)
        results.append(r)

    # Zusammenfassung
    total_elapsed = time.time() - total_start
    print(f"\n{'=' * 60}")
    print(f"  ZUSAMMENFASSUNG")
    print(f"{'=' * 60}")
    for r in results:
        elapsed_min = r["elapsed_s"] / 60
        print(f"  {r['name']:20} → {r['status']:10} ({elapsed_min:.1f} min)")
    print(f"  {'─' * 40}")
    print(f"  {'Gesamtzeit':20} → {total_elapsed / 60:.1f} min "
          f"({total_elapsed / 3600:.1f} h)")

    # Exitcode: 0 nur wenn beide OK
    if all(r["returncode"] == 0 for r in results):
        print(f"\n  Alle Batches erfolgreich!")
        sys.exit(0)
    else:
        failed = [r["name"] for r in results if r["returncode"] != 0]
        print(f"\n  Fehlgeschlagen: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
