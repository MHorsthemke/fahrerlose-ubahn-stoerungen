"""
logging_setup.py — Zentrales Python-Logging.

Ruft man einmalig beim Programmstart auf (setup_logging(cfg)), danach
überall `log = logging.getLogger(__name__)` und `log.info(...)` nutzen.

Levels:
  DEBUG   — ausführliche Schritt-Informationen (nur bei Fehlersuche)
  INFO    — normaler Lauf (Batch-Fortschritt, Sim-Zeitstempel)
  WARNING — unerwartete, aber nicht abbrechende Ereignisse
  ERROR   — Szenario-Abbruch, falscher Pfad, …
"""

import logging
import sys
from pathlib import Path


def setup_logging(level: str = "INFO",
                  console: bool = True,
                  file: str | Path | None = None,
                  base_dir: Path | None = None) -> None:
    """
    Konfiguriert das Root-Logger.

    Args:
        level:  DEBUG | INFO | WARNING | ERROR
        console: True = zusätzlich auf stdout schreiben
        file:    Pfad zur Logdatei (relativ zu base_dir). None = keine Datei.
        base_dir: Projektwurzel für relativen file-Pfad.
    """
    root = logging.getLogger()
    # Altes Handler-Setup entfernen (z.B. Pytest-Laufvarianten)
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    if file:
        path = Path(file)
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
