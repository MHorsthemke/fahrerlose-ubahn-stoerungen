"""
alle_diagramme.py — Regeneriert alle Diagramme auf einmal.

Verwendung:
    python3 alle_diagramme.py [pfad_zur_batch_csv]

    Ohne Argument wird die neueste CSV in output/batch_results/ verwendet.
    Die Agentenverteilungen und Stabilitätsdiagramme brauchen keine CSV.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parents[1]

# Alle Diagramm-Scripts in Ausführungsreihenfolge
SCRIPTS = [
    # Ohne CSV-Abhängigkeit
    ("Agentenverteilung_Laufzeiten.py", False),
    ("plot_stabilitaet.py", False),
    # Mit CSV-Abhängigkeit
    ("plot_statistik_intervention.py", True),
    ("plot_cdf_intervention.py", True),
    ("plot_heatmap_intervention.py", True),
    ("plot_delta_interventionszeit.py", True),
    ("plot_delta_allgemein.py", True),
    # Validierung
    ("detect_faulty_results.py", True),
]


def main():
    csv_arg = sys.argv[1] if len(sys.argv) > 1 else None

    print("=" * 60)
    print("  Alle Diagramme regenerieren")
    print("=" * 60)

    erfolge = 0
    fehler = 0

    for script_name, needs_csv in SCRIPTS:
        script_path = SCRIPT_DIR / script_name
        if not script_path.exists():
            print(f"\n⚠  {script_name} nicht gefunden — übersprungen")
            fehler += 1
            continue

        print(f"\n--- {script_name} ---")
        cmd = [sys.executable, str(script_path)]
        if needs_csv and csv_arg:
            cmd.append(csv_arg)

        result = subprocess.run(cmd, cwd=str(REPO_DIR),
                                capture_output=True, text=True)

        if result.returncode == 0:
            # Nur die letzten paar Zeilen der Ausgabe zeigen
            lines = result.stdout.strip().split('\n')
            for line in lines[-3:]:
                print(f"  {line}")
            erfolge += 1
        else:
            print(f"  FEHLER (Exit {result.returncode}):")
            err = result.stderr.strip().split('\n')
            for line in err[-5:]:
                print(f"  {line}")
            fehler += 1

    print(f"\n{'=' * 60}")
    print(f"  Fertig: {erfolge} erfolgreich, {fehler} fehlgeschlagen")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
