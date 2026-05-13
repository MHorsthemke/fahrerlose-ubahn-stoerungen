# Fahrerlose U-Bahn: Reaktion auf Störungen

Simulationscode zur Masterarbeit *Entwicklung und Analyse einer Störungssimulation
zur Abbildung einer Beispielstörung im U-Bahn-Betrieb mit SUMO* (Horsthemke, 2026).

Quantitative Gegenüberstellung zweier physischer Rückfallebenen für den Übergang
von GoA 2 nach GoA 4 (UTO):

- **Stationsagenten** — ortsgebundenes Personal an Haltestellen
- **Zugbegleiter-Plus (ZUB+)** — zuggebundenes Personal an Bord

Als Fallstudie dient die Frankfurter U4 mit 10 Stationen (Bockenheimer Warte bis
Seckbacher Landstraße, Umlauf 15.259 m). Die Einheitsstörung ist ein ungeplanter
Halt eines Zugs auf freier Strecke (Kategorie A nach VDV 336). Als zentrale
Kennzahl wird die Interventionszeit $t_I$ bestimmt — vom Eintritt der Störung
bis zum Eintreffen einer Eingriffsperson am ausgefallenen Zug.

## Zitation

```
Horsthemke, M. (2026). Entwicklung und Analyse einer Störungssimulation
zur Abbildung einer Beispielstörung im U-Bahn-Betrieb mit SUMO.
Masterarbeit, Technische Universität Braunschweig.
```

Die Masterarbeit liegt diesem Repository als PDF bei: [`thesis/Masterarbeit_Horsthemke_2026.pdf`](thesis/Masterarbeit_Horsthemke_2026.pdf).

Sobald die Code-Veröffentlichung über Zenodo archiviert ist, wird hier
zusätzlich eine DOI ergänzt.

## Voraussetzungen

- **Python** 3.10 oder neuer
- **SUMO** 1.26.0 (Simulation of Urban Mobility) — https://eclipse.dev/sumo/
- Python-Pakete aus `requirements.txt`

SUMO muss separat installiert sein und über die Umgebungsvariable `SUMO_HOME`
auffindbar sein. Die Pakete `traci` und `sumolib` werden mit SUMO mitgeliefert
und müssen über den `SUMO_HOME/tools`-Pfad importierbar sein.

## Installation

```bash
# Repository klonen
git clone https://github.com/MHorsthemke/fahrerlose-ubahn-stoerungen.git
cd fahrerlose-ubahn-stoerungen

# Virtuelle Umgebung (empfohlen)
python3 -m venv .venv
source .venv/bin/activate

# Pakete installieren
pip install -r requirements.txt
```

Plus SUMO-Pakete sichtbar machen (einmalig in der Shell):

```bash
export SUMO_HOME=/path/to/sumo
export PYTHONPATH=$PYTHONPATH:$SUMO_HOME/tools
```

## Verwendung

### Vollständiger Produktionslauf

```bash
python3 scripts/run_all_parallel.py
```

Der Orchestrator führt nacheinander die beiden Batch-Skripte aus:

- `scripts/main.py --parallel` — Stationsagenten-Simulation
- `scripts/main_zub.py --parallel` — Zugbegleiter-Plus-Simulation

Jeder Batch öffnet ein eigenes `multiprocessing.Pool` und verteilt die Szenarien
auf die verfügbaren CPU-Kerne. Jeder Worker startet eine eigene SUMO-Instanz und
kommuniziert über TraCI mit ihr. Ergebnisse werden zeilenweise in CSVs unter
`output/` geschrieben.

### Konvergenzstudie

Die Konvergenz des Positionsrasters wird über eine Halbierungsreihe gefahren
(1600 m → 800 m → 400 m → 200 m → 100 m → 50 m → 25 m). Das Abbruchkriterium
ist die Kolmogorov-Smirnov-Distanz $d_{\mathrm{KS}} \leq 0{,}05$ und
$\Delta_{\max} \leq 0{,}05$ zwischen zwei aufeinanderfolgenden Stufen.

```bash
python3 scripts/convergence.py
```

### Expansion der reduzierten ZUB+-Daten

Die ZUB+-Simulation nutzt eine Äquivalenz unter Umlauf-Symmetrie, sodass nur
die eindeutigen $(z, g)$-Tupel simuliert werden müssen. Vor der Auswertung
werden diese auf das volle Positionsraster expandiert:

```bash
python3 scripts/zub_expand.py
```

### Auswertung und Plots

```bash
python3 scripts/diagramme/alle_diagramme.py
```

Erzeugt alle in der Masterarbeit verwendeten Diagramme (CDFs, Heatmaps,
Boxplots, Delta-Plots, Nested Loop, Parallel Coordinates) im Ausgabeverzeichnis.

## Verzeichnisstruktur

```
.
├── scripts/                Hauptmodule und Batch-Skripte
│   ├── run_all_parallel.py     Top-Level-Orchestrator
│   ├── main.py                 SA-Batch
│   ├── main_zub.py             ZUB+-Batch
│   ├── batch.py                gemeinsame Batch-Logik
│   ├── simulation.py           Simulationsablauf
│   ├── disruption.py           Störungsauslösung
│   ├── sa_routing.py           Routenwahl Stationsagenten
│   ├── sa_distribution.py      Minimax-Verteilung Stationsagenten
│   ├── zub_routing.py          Routenwahl ZUB+
│   ├── zub_distribution.py     Zugzuordnung ZUB+
│   ├── zub_verteilung.py       Minimax-Verteilung ZUB+
│   ├── convergence.py          Konvergenzprüfung
│   ├── zub_expand.py           Äquivalenz-Auflösung ZUB+
│   ├── csv_writer.py           Ergebnis-Serialisierung
│   ├── TraCI_control.py        SUMO-Kopplung
│   └── diagramme/              Auswertungs- und Plot-Skripte
├── network/                SUMO-Netz (OSM-basiert, U4 Frankfurt)
├── routes/                 Routendefinition (Umlaufroute)
├── config/                 SUMO-Konfiguration
├── thesis/                 Masterarbeit als PDF
├── DIAGRAMME.md            Plot-Dokumentation
├── requirements.txt
├── LICENSE
└── README.md
```

## Reproduzierbarkeit

Die Simulation ist bei gleichen Eingabeparametern vollständig deterministisch
(Standardabweichung der Rundenlaufzeit $\sigma = 0{,}0$ s über fünf
Vergleichsumläufe). Mit identischen Skriptversionen, identischer SUMO-Version
und identischer Konfiguration sind die berichteten Interventionszeiten exakt
reproduzierbar.

Der Produktionslauf der Masterarbeit nutzt:

- **SA-Endraster:** 50 m ($d_{\mathrm{KS}} = 2{,}96\,\%$, $\Delta_{\max} = 2{,}97\,\%$)
- **ZUB+-Endraster:** 25 m ($d_{\mathrm{KS}} = 1{,}45\,\%$, $\Delta_{\max} = 1{,}45\,\%$)

Die Rohdaten der Auswertung (Konvergenz-CSVs vom 26./27. April 2026) sind
separat archiviert.

## Lizenz

Dieser Code ist unter der MIT-Lizenz veröffentlicht — siehe [LICENSE](LICENSE).

## Kontakt

Moritz Horsthemke
moritz.horsthemke@icloud.com

**Betreuung:**

- Prof. Dr. Jürgen Pannek — Institut für Intermodale Transport- und Logistiksysteme (ITL)
- Prof. Dr.-Ing. habil. Lars Schnieder — Institut für Eisenbahnwesen und Verkehrssicherung (IfEV)
- Paula von der Heide, M.Sc. — Institut für Eisenbahnwesen und Verkehrssicherung (IfEV)

Technische Universität Braunschweig
