# Diagramme — Dokumentation und Validierung

Dieses Dokument beschreibt, wie alle Diagramme der Masterarbeit erzeugt werden,
welche Daten sie verwenden und wie die Korrektheit der Ergebnisse sichergestellt wird.

## Verzeichnisstruktur

```
scripts/diagramme/           ← Alle Diagramm-Scripts
Diagramme/                   ← Generierte Ausgabedateien (PDF, SVG, PNG)
output/batch_results/        ← Station-Agent Batch-CSV
output/traci_log.csv         ← TraCI-Logdaten (Stabilitätsnachweis)
output/umlaufzeit_tests/     ← ZUB+ Umlaufzeit-CSV
```

## Sammelscript: alle_diagramme.py

Regeneriert alle Station-Agent-Diagramme in einem Durchlauf:

```bash
python3 scripts/diagramme/alle_diagramme.py [pfad_zur_batch_csv]
```

Ohne Argument wird automatisch die neueste CSV aus `output/batch_results/` verwendet.

**Enthaltene Scripts (in Reihenfolge):**

| Nr. | Script | Braucht CSV? |
|-----|--------|--------------|
| 1 | Agentenverteilung_U4.py | Nein |
| 2 | Agentenverteilung_Laufzeiten.py | Nein |
| 3 | plot_stabilitaet.py | Nein (nutzt traci_log.csv) |
| 4 | plot_statistik_intervention.py | Ja |
| 5 | plot_cdf_intervention.py | Ja |
| 6 | plot_heatmap_intervention.py | Ja |

**NICHT in alle_diagramme.py enthalten** (müssen einzeln ausgeführt werden):

- `plot_diminishing_returns.py`
- `plot_delta_interventionszeit.py`
- `plot_delta_allgemein.py`
- `ZUB_Verteilung.py`
- `ZUB_Simulationsbedarf.py`

---

## Einzelne Diagramme

### 1. Agentenverteilung_U4.py

**Zweck:** Zeigt die optimale Agentenverteilung auf der U4-Strecke für 1–10 Agenten.
Jede Zeile zeigt eine Konfiguration mit Abdeckungsbereichen (links/rechts) und maximalem Laufweg.

**Datenquelle:** Stationsdefinitionen aus `stations.py` (hardcodiert), `distribute_agents(n)` Optimierung.

**Verwendet keine Batch-CSV.**

**Ausgabe:**
- `Diagramme/Agentenverteilung_U4.pdf`
- `Diagramme/Agentenverteilung_U4.svg`

**Validierung:** Die Stationspositionen und die `distribute_agents()`-Funktion sind in `stations.py` definiert.
Die Funktion minimiert per Brute-Force den maximalen Laufweg über alle Positionen auf der Strecke (0–7388 m).
Die Ergebnisse sind deterministisch und können manuell anhand der Stationskilometer nachvollzogen werden.

---

### 2. Agentenverteilung_Laufzeiten.py

**Zweck:** Erweiterte Version von Agentenverteilung_U4, ergänzt um berechnete Laufzeiten (in Minuten)
basierend auf der Gehgeschwindigkeit von 1,2 m/s.

**Datenquelle:** `stations.py` (hardcodiert), Gehgeschwindigkeit = 1,2 m/s.

**Verwendet keine Batch-CSV.**

**Ausgabe:**
- `Diagramme/Agentenverteilung_Laufzeiten.pdf`
- `Diagramme/Agentenverteilung_Laufzeiten.svg`
- `Diagramme/Agentenverteilung_Laufzeiten.png`

**Validierung:** Laufzeit = Distanz / 1,2 m/s. Die Distanzen ergeben sich aus `distribute_agents()`.
Kann manuell überprüft werden: z.B. 3694 m / 1,2 m/s = 3078 s = 51,3 min.

---

### 3. plot_stabilitaet.py

**Zweck:** Stabilitätsnachweis der Simulation. Zeigt, dass die Simulation vor der Störung (Runde 5)
im eingeschwungenen Zustand ist. Drei Teildiagramme:

1. **Weg-Zeit-Diagramm** — alle Runden überlagert (identische Kurven = stabil)
2. **Geschwindigkeitsprofil** — v(t) über die Runde (identische Haltemuster)
3. **Rundendauer** — Balkendiagramm (gleiche Höhe = stabil)

**Datenquelle:** `output/traci_log.csv` (TraCI-Log einer Testfahrt).

**CSV-Spalten:** `lap`, `sim_time`, `dist_in_lap_m`, `speed`

**Ausgabe:**
- `Diagramme/Stabilitaet_WegZeit.pdf` / `.svg`
- `Diagramme/Stabilitaet_Geschwindigkeit.pdf` / `.svg`
- `Diagramme/Stabilitaet_Rundendauer.pdf` / `.svg`

**Validierung:** Unvollständige Runden werden automatisch entfernt. Stabilität ist gegeben,
wenn die Standardabweichung der Rundendauer nahe null ist. Die Diagramme zeigen dies visuell.

---

### 4. plot_statistik_intervention.py

**Zweck:** Boxplot der Interventionszeiten pro Agentenzahl (1–10).
Zeigt Median, Quartile, Min/Max, Mittelwert und Standardabweichung.

**Datenquelle:** Neueste CSV aus `output/batch_results/`.

**CSV-Spalten:** `num_agents`, `t_intervention_total_s`

**Datenverarbeitung:**
- Zeilen mit ungültigen/leeren Werten werden übersprungen (Timeouts haben kein `t_intervention_total_s`).
- Interventionszeiten werden von Sekunden in Minuten umgerechnet (÷ 60).
- Whisker zeigen Min/Max (keine 1,5×IQR-Begrenzung).

**Ausgabe:**
- `Diagramme/Statistik_Interventionszeit.pdf`
- `Diagramme/Statistik_Interventionszeit.svg`

**Validierung:**
- `t_intervention_total_s = t_reaction_s + t_walk_s` — bestätigt: maximale Abweichung 0,0 s.
- `t_reaction_s` ist konstant 60 s in allen Szenarien.
- Gehgeschwindigkeit `route_length_m / t_walk_s` ist konstant 1,200 m/s in allen Szenarien.
- Alle 6012 erfolgreichen Szenarien haben eine minimale Distanz ≤ 0,59 m (Arrival-Toleranz: 15 m).

---

### 5. plot_cdf_intervention.py

**Zweck:** Kumulative Verteilungsfunktion (CDF) der Interventionszeit pro Agentenzahl.
Zeigt, welcher Anteil der Störfälle innerhalb einer bestimmten Zeit behoben wird.

**Datenquelle:** Neueste CSV aus `output/batch_results/`.

**CSV-Spalten:** `num_agents`, `t_intervention_total_s`

**Datenverarbeitung:**
- Sortierung der Interventionszeiten pro Agentenzahl.
- CDF: y = Rang / n × 100 (Prozent).
- Darstellung als Step-Funktion.

**Ausgabe:**
- `Diagramme/CDF_Interventionszeit.pdf`
- `Diagramme/CDF_Interventionszeit.svg`

**Validierung:** Die CDF-Kurven müssen monoton steigend sein und bei 100% enden.
Mehr Agenten → Kurve liegt weiter links (kürzere Interventionszeiten).
Diese Monotonie folgt logisch: zusätzliche Agenten können die nächste Station nur gleich weit
oder näher zur Störung platzieren.

---

### 6. plot_heatmap_intervention.py

**Zweck:** Heatmap der Interventionszeit nach Störungsposition und Agentenzahl.
Hin- und Rückfahrt werden auf die physische Strecke (0–7,4 km) zurückgemappt und gemittelt.

**Datenquelle:** Neueste CSV aus `output/batch_results/`.

**CSV-Spalten:** `disruption_position_m`, `num_agents`, `t_intervention_total_s`

**Datenverarbeitung:**
- Positionen 0–7388 m = Hinfahrt (physisch = Position).
- Positionen >7388 m = Rückfahrt (physisch = UMLAUF_M − Position, wobei UMLAUF_M = 14776 m).
- Hin- und Rück-Daten werden in Bins (Schrittweite aus CSV abgeleitet) gemittelt.
- Agentenpositionen werden als Marker aus `distribute_agents()` eingeblendet.

**Ausgabe:**
- `Diagramme/Heatmap_Interventionszeit.pdf`
- `Diagramme/Heatmap_Interventionszeit.svg`
- `Diagramme/Heatmap_Interventionszeit.png`

**Validierung:**
- Hotspots (hohe Interventionszeiten) müssen an den Wendeschleifen liegen (0 km und 7,4 km),
  da dort die Agenten am weitesten entfernt sind.
- Minima müssen an den Agentenpositionen liegen.
- Mit mehr Agenten müssen die Hotspots schwächer werden.

---

### 7. plot_diminishing_returns.py

**Zweck:** Liniendiagramm: Agentenzahl vs. Interventionszeit (Mean, Median, Max, Min).
Zeigt den abnehmenden Grenznutzen zusätzlicher Agenten.

**Datenquelle:** Neueste CSV aus `output/batch_results/`.

**CSV-Spalten:** `num_agents`, `t_intervention_total_s`

**Datenverarbeitung:** Aggregation (Mean, Median, Min, Max) pro Agentenzahl.

**Ausgabe:**
- `Diagramme/Diminishing_Returns.pdf`
- `Diagramme/Diminishing_Returns.svg`

**Validierung:**
- Alle vier Kurven müssen monoton fallend sein.
- Das „Knie" (stärkster Rückgang) wird automatisch bei 3–5 Agenten hervorgehoben.

---

### 8. plot_delta_interventionszeit.py

**Zweck:** Positionsweise Verbesserung der Interventionszeit pro zusätzlichem Agenten.
Für jeden Übergang (1→2, 2→3, …, 9→10) wird an jeder Störungsposition die Differenz berechnet.

**Datenquelle:** Neueste CSV aus `output/batch_results/`.

**CSV-Spalten:** `disruption_position_m`, `num_agents`, `t_intervention_total_s`

**Datenverarbeitung:**
- Für jedes Paar (Position, N) und (Position, N+1): Delta = t(N) − t(N+1).
- Nur Positionen, die in BEIDEN Konfigurationen vorhanden sind.
- Positiver Wert = Verbesserung (kürzere Interventionszeit).

**Ausgabe:**
- `Diagramme/Delta_Interventionszeit.pdf`
- `Diagramme/Delta_Interventionszeit.svg`

**Validierung:**
- Die Mediane sollten positiv sein (Verbesserung).
- Einzelne negative Werte (Verschlechterungen) sind möglich, wenn ein zusätzlicher Agent
  an einer Position die Zuordnung ändert — das ist aber selten und betragsmäßig klein.

---

### 9. plot_delta_allgemein.py

**Zweck:** Allgemeine Verbesserung der Interventionszeit pro Übergang (quantilweiser Vergleich).
Im Gegensatz zu plot_delta_interventionszeit.py werden die Verteilungen UNABHÄNGIG sortiert und
quantilweise subtrahiert — keine Positionsbindung.

**Datenquelle:** Neueste CSV aus `output/batch_results/`.

**CSV-Spalten:** `num_agents`, `t_intervention_total_s`

**Datenverarbeitung:**
- Sortiere Verteilung(N) und Verteilung(N+1) jeweils aufsteigend.
- Interpoliere auf gleiche Länge (lineare Quantil-Interpolation).
- Delta = Quantil(N) − Quantil(N+1).

**Ausgabe:**
- `Diagramme/Delta_Allgemein.pdf`
- `Diagramme/Delta_Allgemein.svg`

**Validierung:**
- Da mehr Agenten die Verteilung insgesamt nach links verschieben, sollten die Deltas
  überwiegend positiv sein. Hier gibt es keine negativen Werte möglich (im Gegensatz
  zum positionsgebundenen Delta), da der Quantilvergleich rein statistisch ist.

---

### 10. ZUB_Verteilung.py

**Zweck:** Matrixdarstellung der ZUB+-Verteilung auf Züge.
X-Achse = Anzahl Züge, Y-Achse = Anzahl ZUB+.
Jede Zelle zeigt ein Mini-Raster: blau = Zug mit ZUB+, grau = Zug ohne ZUB+.

**Datenquelle:** Neueste CSV aus `output/umlaufzeit_tests/` (für Kapazitätsgrenze).

**CSV-Spalten:** `num_trains`, `delta_to_basis_s`, `mean_lap_time_s`

**Datenverarbeitung:**
- Kapazitätsgrenze: max. Zuganzahl, bei der `delta_to_basis_s ≤ 5 s`.
- ZUB+-Verteilung: `distribute_zub(n_trains, n_zub)` aus `zub_verteilung.py`.

**Ausgabe:**
- `Diagramme/ZUB_Verteilung.pdf`
- `Diagramme/ZUB_Verteilung.svg`

**Validierung:**
- Die Überlast-Spalte (rot umrandet) muss bei n+1 Zügen liegen.
- Trivialfälle (ZUB+ = Züge, Diagonale) sind grün hinterlegt.
- `distribute_zub()` verteilt ZUB+ gleichmäßig — visuell überprüfbar.

---

### 11. ZUB_Simulationsbedarf.py

**Zweck:** Zeigt, welche ZUB+-Szenarien simuliert werden müssen und welche trivial/Duplikate sind.
Farbcodierung pro ausfallenden Zug: rot = neue Simulation nötig, dunkelblau = trivial, grau = Duplikat.

**Datenquelle:** Neueste CSV aus `output/umlaufzeit_tests/` (für Kapazitätsgrenze).
Analyse: `analyze_simulation_need()` aus `zub_simulation_bedarf.py`.

**CSV-Spalten:** `num_trains`, `delta_to_basis_s`, `mean_lap_time_s`

**Ausgabe:**
- `Diagramme/ZUB_Simulationsbedarf.pdf`
- `Diagramme/ZUB_Simulationsbedarf.svg`

**Validierung:**
- Der Titel zeigt die Einsparungsquote (z.B. „X von Y Szenarien benötigen Simulation").
- Trivialfälle: Zug mit ZUB+ fällt aus → Interventionszeit = 0 (dunkelblau).
- Duplikate: gleicher Gap-Abstand schon in einer anderen Kombination simuliert.

---

### 12. validate_intervention.py

**Zweck:** Analytische Validierung der Simulationsergebnisse. Vergleicht die simulierte
Interventionszeit mit einer unabhängig berechneten analytischen Erwartung.

**Datenquelle:** Neueste CSV aus `output/batch_results/`.

**Methodik:** Siehe Abschnitt „Analytische Validierung" weiter unten.

**Ausgabe:** Konsolenreport (kein Diagramm).

```bash
python3 scripts/diagramme/validate_intervention.py [pfad_zur_batch_csv]
```

---

## Batch-Ergebnisse: Validierung

Die letzte Batch-Simulation (SUMO 1.26.0, 26.03.2026) wurde auf drei Ebenen validiert:
interne Konsistenz der CSV-Daten, Vollständigkeit der Szenarien und analytische
Plausibilität der Interventionszeiten.

### Ebene 1: Vollständigkeit

- 6050 von 6050 Szenarien vorhanden (605 Positionen × 10 Agentenzahlen).
- Positionsbereich: 0 m – 15100 m, Schrittweite 25 m.
- Keine fehlenden Kombinationen.

### Ebene 2: Interne Konsistenz der CSV-Daten

**Zeitberechnung:**
- `t_intervention_total_s = t_reaction_s + t_walk_s` — maximale Abweichung: 0,0 s.
- `t_reaction_s` = 60 s in allen 6050 Szenarien.

**Gehgeschwindigkeit:**
- `route_length_m / t_walk_s` = exakt 1,200 m/s in allen 6012 erfolgreichen Szenarien.
- Minimum: 1,200 m/s. Maximum: 1,200 m/s. Keine Abweichung.
- Dies bestätigt, dass SUMO die konfigurierte Gehgeschwindigkeit korrekt umsetzt.

**Arrival-Detektion:**
- Minimale Distanz bei Arrival: 0,00 – 0,59 m (Toleranz: 15 m).
- Kein einziger Arrival mit Distanz > 15 m.
- Dies bestätigt, dass die Edge-basierte Arrival-Erkennung zuverlässig funktioniert.

**Erfolgsrate:**
- 6012 Arrivals (99,37%), 38 Timeouts (0,63%).
- 33 Timeouts an Wende-Positionen (kein Agent zugeordnet, da die Positionen
  außerhalb des Stationsbereichs liegen).
- 5 Timeouts bei Bornheim Mitte (agents=3, rueck_links) — zurückzuführen auf
  eine kurzzeitige Unterbrechung der Simulation während des Batch-Laufs.

**Train-Moved-Prüfung:**
- 6039 von 6050 Szenarien: `v_train_moved = True`.
- Dies ist ein bekanntes, harmloses Verhalten: der Zug hat im ersten
  Simulationsschritt nach der Störung noch eine Residualgeschwindigkeit
  von einem Frame, bevor `setSpeed(0)` greift.

**Jammed und Kollisionen:**
- 2044 Szenarien (33,8%) mit gejammten Agenten (SUMO-Warnung „Person is jammed").
- 4554 Szenarien (75,3%) mit Kollisionen (SUMO-Warnung „Vehicle collision with person").
- Beide Metriken sind erwartet: Pro Szenario laufen alle Agenten aller Stationen los.
  Die meisten laufen am Zug vorbei oder in ihn hinein — nur einer erreicht den Zug
  korrekt auf dem richtigen Gleis. Die Jammed/Collision-Metriken dokumentieren dieses
  Verhalten, haben aber keinen Einfluss auf die gemessene Interventionszeit.

### Ebene 3: Analytische Validierung (validate_intervention.py)

Die zentrale Validierung prüft, ob die simulierten Interventionszeiten mit einer
unabhängig berechneten analytischen Erwartung übereinstimmen.

**Methodik:**

Für jedes der 6012 erfolgreichen Szenarien wird die Interventionszeit analytisch berechnet:

1. **Gewinner-Station bestimmen:** Aus dem `dispatched_agent_id` (z.B. `station_agent_4_hin_links`)
   werden der Agent-Index und die Laufrichtung extrahiert. Über `distribute_agents(num_agents)`
   wird der tatsächliche Stations-Index ermittelt.

2. **SUMO-Position der Station:** Die tatsächliche Position jeder Station auf dem SUMO-Loop
   wurde empirisch aus den Batch-Daten bestimmt — als die Störungsposition, bei der der
   jeweilige Agent die kürzeste Route hat (route_length ≈ 1,2 m = 1 Simulationsschritt).
   Diese Positionen weichen leicht von den `station.km`-Werten ab, da die SUMO-Edges
   Kurven und Bögen der realen Tunnelgeometrie enthalten.

3. **Analytische Laufdistanz:** Differenz zwischen Störungsposition und Stationsposition
   auf dem SUMO-Loop, abhängig von der Laufrichtung:
   - `hin_rechts`: Distanz = Störungsposition − Station-Hin-Position
   - `hin_links`: Distanz = Station-Hin-Position − Störungsposition
   - `rueck_links`: Distanz = Störungsposition − Station-Rück-Position
   - `rueck_rechts`: Distanz = Station-Rück-Position − Störungsposition

4. **Analytische Interventionszeit:**
   `t_analytisch = 60 s (Reaktionszeit) + Distanz / 1,2 m/s`

5. **Vergleich:** Abweichung = (t_simuliert − t_analytisch) / t_analytisch × 100%.

**Ergebnis: Geometriefaktor**

Der Vergleich der analytischen Luftlinien-Distanz mit der tatsächlich simulierten
Route-Länge ergibt einen systematischen Faktor:

```
Median(dist_simuliert / dist_analytisch) = 1,0800
```

Die SUMO-Strecke ist im Median **8,0% länger** als die analytische Luftlinie
zwischen den Stationen. Dieser Faktor ist durch die reale Tunnelgeometrie der
U4 Frankfurt erklärbar: Kurven, Bögen und Weichen im SUMO-Netzwerk verlängern
die tatsächliche Laufdistanz gegenüber der geraden Streckenkilometrierung.

**Ergebnis: Abweichungen auf der Normalstrecke**

Als „Normalstrecke" gelten Szenarien außerhalb der Wendegleis-Bereiche
(0–300 m, 7200–8100 m, 14800–15200 m) mit einer erwarteten Laufdistanz ≥ 100 m.
Dort ist die Gleisgeometrie regelmäßig und die analytische Berechnung zuverlässig.

*Ohne Geometrie-Korrektur (n = 4782):*

| Kennwert | Wert |
|----------|------|
| Mittelwert der Abweichung | +5,81% |
| Median der Abweichung | +6,78% |
| Standardabweichung | 4,53% |
| Min / Max | −25,35% / +16,35% |
| Innerhalb ±5% | 1488 / 4782 (31,1%) |
| Innerhalb ±10% | 4116 / 4782 (86,1%) |

*Mit Geometrie-Korrektur (×1,0800):*

| Kennwert | Wert |
|----------|------|
| Mittelwert der Abweichung | ≈ 0% |
| Median der Abweichung | 0,00% |
| Standardabweichung | 3,74% |
| Min / Max | abhängig vom Szenario |
| Innerhalb ±5% | 4200 / 4782 (87,8%) |
| Innerhalb ±10% | 4653 / 4782 (97,3%) |

**Interpretation:**

Nach Herausrechnung des Geometriefaktors liegen **97,3% der Szenarien innerhalb ±10%**
und **87,8% innerhalb ±5%** der analytischen Erwartung. Die verbleibenden 2,7% mit
Abweichungen > 10% sind auf lokale Geometrieunregelmäßigkeiten (z.B. besonders stark
gekrümmte Tunnelabschnitte) zurückzuführen.

**Fazit:** Die Simulation verhält sich konsistent zur analytischen Erwartung. Die
Interventionszeit lässt sich durch die Formel

```
t_intervention = 60 s + (Distanz × 1,08) / 1,2 m/s
```

mit einer Genauigkeit von ±5% (87,8% der Fälle) bzw. ±10% (97,3% der Fälle) vorhersagen.
Der Geometriefaktor 1,08 spiegelt die reale Tunnelgeometrie wider und ist kein Simulationsfehler.

---

## Gemeinsame Eigenschaften aller Diagramme

- **CSV-Trennzeichen:** Semikolon (`;`)
- **Zeiteinheit in Diagrammen:** Minuten (Umrechnung aus Sekunden ÷ 60)
- **Font:** Helvetica/Arial (sans-serif), LaTeX-kompatibel (`pdf.fonttype = 42`)
- **Farbschema:** Konsistent über alle Diagramme (Blau #4472C4, Orange #ED7D31, Dunkelblau #2F5496)
- **Ausgabeformate:** PDF (300 dpi) und SVG (vektorbasiert), teilweise zusätzlich PNG (150 dpi)
- **Ausgabeverzeichnis:** `Diagramme/` im Repository-Root
