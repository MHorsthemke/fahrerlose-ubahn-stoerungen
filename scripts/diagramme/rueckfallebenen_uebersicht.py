#!/usr/bin/env python3
"""
Übersichtsdiagramm: Rückfallebenen bei Störung Kategorie A
Masterarbeit Horsthemke — Stand 2026-04-07
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

# ── Einstellungen ──────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(22, 16))
ax.set_xlim(0, 22)
ax.set_ylim(0, 16)
ax.axis("off")
fig.patch.set_facecolor("white")

# ── Farben ─────────────────────────────────────────────────────
C_ROOT   = "#2C3E50"   # Dunkelblau — Wurzel
C_GREEN  = "#27AE60"   # Grün — vollständig implementiert
C_YELLOW = "#F39C12"   # Gelb — teilweise / Bug
C_RED    = "#E74C3C"   # Rot — nicht implementiert
C_GRAY   = "#95A5A6"   # Grau — nur erwähnt
C_LIGHT  = "#ECF0F1"   # Hintergrund für Parameterboxen
C_TEXT   = "#2C3E50"
C_WHITE  = "white"

# ── Hilfsfunktionen ───────────────────────────────────────────
def draw_box(x, y, w, h, color, title, lines, fontsize_title=11,
             fontsize_body=8.5, title_color="white", status=None):
    """Zeichnet eine Box mit Titel (farbiger Header) und Textzeilen."""
    # Header
    header_h = h * 0.32 if lines else h * 0.6
    header = FancyBboxPatch((x, y + h - header_h), w, header_h,
                            boxstyle="round,pad=0.05", fc=color, ec="none")
    ax.add_patch(header)
    # Body
    if lines:
        body = FancyBboxPatch((x, y), w, h - header_h,
                              boxstyle="round,pad=0.05", fc=C_LIGHT, ec=color,
                              linewidth=1.5)
        ax.add_patch(body)
    # Titel
    ax.text(x + w / 2, y + h - header_h / 2, title,
            ha="center", va="center", fontsize=fontsize_title,
            fontweight="bold", color=title_color, wrap=True)
    # Status-Badge
    if status:
        badge_colors = {
            "FERTIG":    C_GREEN,
            "BUG":       C_YELLOW,
            "OFFEN":     C_RED,
            "ERWÄHNT":   C_GRAY,
        }
        bc = badge_colors.get(status, C_GRAY)
        badge = FancyBboxPatch((x + w - 1.55, y + h - header_h + 0.05),
                               1.5, 0.32, boxstyle="round,pad=0.03",
                               fc=bc, ec="none", alpha=0.9)
        ax.add_patch(badge)
        ax.text(x + w - 0.8, y + h - header_h + 0.21, status,
                ha="center", va="center", fontsize=6.5,
                fontweight="bold", color="white")
    # Body-Text
    if lines:
        text_y = y + h - header_h - 0.25
        for line in lines:
            text_y -= 0.28
            ax.text(x + 0.15, text_y, line, ha="left", va="top",
                    fontsize=fontsize_body, color=C_TEXT)


def draw_arrow(x1, y1, x2, y2, color=C_ROOT):
    """Zeichnet eine Verbindungslinie."""
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-", color=color,
                                linewidth=1.5, connectionstyle="arc3,rad=0"))


def draw_arrow_L(x1, y1, x_mid, x2, y2, color=C_ROOT):
    """Zeichnet eine L-förmige Verbindung (runter, dann seitlich)."""
    ax.plot([x1, x1], [y1, y2 + (y1 - y2) * 0.4], color=color, lw=1.5)
    ax.plot([x1, x2], [y2 + (y1 - y2) * 0.4, y2 + (y1 - y2) * 0.4],
            color=color, lw=1.5)
    ax.plot([x2, x2], [y2 + (y1 - y2) * 0.4, y2], color=color, lw=1.5)


# ══════════════════════════════════════════════════════════════
# EBENE 0 — Wurzel
# ══════════════════════════════════════════════════════════════
root_x, root_y, root_w, root_h = 6.5, 14.3, 9, 1.3
draw_box(root_x, root_y, root_w, root_h, C_ROOT,
         "Rückfallebenen bei Einheitsstörung (VDV Kat. A)",
         ["Zug liegengeblieben auf freier Strecke — Frankfurt U4",
          "Kennzahl: Interventionszeit = Reaktionszeit + Anfahrt/Gehzeit"],
         fontsize_title=13, fontsize_body=9)

# ══════════════════════════════════════════════════════════════
# EBENE 1 — Die vier Hauptrückfallebenen
# ══════════════════════════════════════════════════════════════
# Positionen: A, B, C, D gleichmäßig verteilt
level1_y = 11.3
level1_h = 2.5
box_w = 4.5

# --- A: Mischbetrieb ---
ax_pos = 0.3
draw_box(ax_pos, level1_y, box_w, level1_h, C_GRAY,
         "A — Mischbetrieb (GoA2/GoA4)",
         ["Fahrer an Bord = erste Rückfallebene",
          "Manuell bei geringer v zum Bhf.",
          "t_intervention ≈ 0",
          "",
          "Keine Parameter nötig",
          "(Fahrer ist bereits vor Ort)"],
         status="ERWÄHNT")
draw_arrow(root_x + 1.5, root_y, ax_pos + box_w / 2, level1_y + level1_h)

# --- B: ZUB+ ---
bx_pos = 5.5
draw_box(bx_pos, level1_y, box_w, level1_h, C_YELLOW,
         "B — ZUB+ (Zugbegleiter-Plus)",
         ["ZUB+ fährt auf regulärem Zug mit",
          "Steigt bei Störung aus → läuft zu Havarist",
          "",
          "v_geh = 3,33 m/s  |  t_reakt = 90 s",
          "Gap = 0…(n−1)  |  n = 1…10 Züge",
          "Umlaufzeit = 1.562 s (≈ 26 min)"],
         status="BUG")
draw_arrow(root_x + root_w / 2 - 1, root_y, bx_pos + box_w / 2, level1_y + level1_h)

# --- C: Stationsagenten ---
cx_pos = 11.2
draw_box(cx_pos, level1_y, box_w, level1_h, C_GREEN,
         "C — Stationsagenten",
         ["Ortsfeste Agenten an Stationen",
          "Laufen über Gleise zum Havaristen",
          "",
          "v_geh = 3,33 m/s  |  t_reakt = 90 s",
          "n = 1…10 Agenten (Minimax-Verteilung)",
          "6.050 Szenarien  |  605 Positionen × 25 m"],
         status="FERTIG")
draw_arrow(root_x + root_w / 2 + 1, root_y, cx_pos + box_w / 2, level1_y + level1_h)

# --- D: Telebetrieb ---
dx_pos = 17.0
draw_box(dx_pos, level1_y, box_w, level1_h, C_RED,
         "D — Telebetrieb (Fernsteuerung)",
         ["Remote Operator (RO) im OCC",
          "Steuert Havarist ferngesteuert",
          "",
          "v_max = 40 km/h (Fernfahrt)",
          "t_reakt(RO) = ? (fehlt)",
          "Komm.-Latenz = ? (fehlt)"],
         status="OFFEN")
draw_arrow(root_x + root_w - 1.5, root_y, dx_pos + box_w / 2, level1_y + level1_h)

# ══════════════════════════════════════════════════════════════
# EBENE 2 — ZUB+ Varianten
# ══════════════════════════════════════════════════════════════
level2_y = 6.8
sub_w = 4.8
sub_h = 4.0

# B1 — Eingleisig
b1_x = 0.2
draw_box(b1_x, level2_y, sub_w, sub_h, C_YELLOW,
         "B1 — Eingleisig",
         ["ZUB+-Zug staut HINTER Havarist auf",
          "ZUB+ steigt aus, läuft nach vorne",
          "",
          "───── Ablauf ─────",
          "Störung → Zug staut → Queue erkannt",
          "→ ZUB+ steigt aus → läuft zu Havarist",
          "",
          "Gehstrecke: kurz (nur Zugabstand)",
          "Hauptzeit: Restfahrzeit + Aufstau",
          "",
          "⚠ Bug: Exit-Logik falsch",
          "406 Szenarien simuliert"],
         fontsize_body=8, status="BUG")

# Verbindung B → B1
draw_arrow(bx_pos + box_w / 2 - 1.5, level1_y, b1_x + sub_w / 2, level2_y + sub_h)

# B2a — Zweigleisig, von hinten
b2a_x = 5.5
draw_box(b2a_x, level2_y, sub_w, sub_h, C_YELLOW,
         "B2a — Zweigl., von hinten",
         ["Wie B1, aber zweigleisiger Tunnel",
          "Kein Gleiswechsel genutzt",
          "",
          "───── Ablauf ─────",
          "Identisch mit B1:",
          "Aufstauen → Aussteigen → Laufen",
          "",
          "Gleicher Code wie B1",
          "(Unterschied nur konzeptionell)",
          "",
          "⚠ Bug: Exit-Logik falsch",
          "In 406 Szenarien enthalten"],
         fontsize_body=8, status="BUG")
draw_arrow(bx_pos + box_w / 2 - 0.5, level1_y, b2a_x + sub_w / 2, level2_y + sub_h)

# B2b — Zweigleisig, Gegengleis
b2b_x = 11.0
draw_box(b2b_x, level2_y, sub_w, sub_h, C_RED,
         "B2b — Zweigl., Gegengleis",
         ["ZUB+-Zug fährt auf Gegengleis",
          "AM Havaristen VORBEI",
          "",
          "───── Ablauf ─────",
          "Störung → Umleitung Gegengleis",
          "→ Vorbeifahrt → Halt → Gleiswechsel",
          "→ ZUB+ läuft ZURÜCK zu Havarist",
          "",
          "Voraussetzung: Weichen vorhanden",
          "Vorteil: nicht durch Aufstau blockiert",
          "Nachteil: Gegenverkehr sperren",
          ""],
         fontsize_body=8, status="OFFEN")
draw_arrow(bx_pos + box_w / 2 + 0.5, level1_y, b2b_x + sub_w / 2, level2_y + sub_h)

# B2c — Zug vor Havarist
b2c_x = 16.7
draw_box(b2c_x, level2_y, sub_w, sub_h, C_RED,
         "B2c — Zug VOR Havarist",
         ["ZUB+ sitzt auf Zug der bereits",
          "VOR dem Havaristen gefahren ist",
          "",
          "───── Ablauf ─────",
          "Störung → Zug vor Hav. fährt weiter",
          "→ Halt an nächster Station",
          "→ ZUB+ steigt aus",
          "→ Läuft auf Gleis ZURÜCK zu Havarist",
          "",
          "Vorteil: kein Aufstau nötig",
          "Nachteil: Zug schon entfernt",
          ""],
         fontsize_body=8, status="OFFEN")
draw_arrow(bx_pos + box_w / 2 + 1.5, level1_y, b2c_x + sub_w / 2, level2_y + sub_h)

# ══════════════════════════════════════════════════════════════
# EBENE 2 — Telebetrieb Varianten (unterhalb D, kleiner)
# ══════════════════════════════════════════════════════════════
# Telebetrieb-Varianten als kompakte Liste rechts
tele_x = 17.0
tele_y = 3.5
tele_w = 4.5
tele_h = 3.0
draw_box(tele_x, tele_y, tele_w, tele_h, C_RED,
         "Telebetrieb-Varianten",
         ["D1  Weiterfahrt zur nächsten Station",
          "     RO steuert Hav. zum Bahnhof",
          "",
          "D2  Räumung des Streckenabschnitts",
          "     RO fährt Hav. zum Ausweichgleis",
          "",
          "D3  Rangieren / Bergen",
          "     RO steuert Hav. zur Werkstatt",
          "",
          "D4  Überwachung + Dispatch",
          "     RO überwacht, sendet Bodenpersonal"],
         fontsize_body=8, status="OFFEN")
draw_arrow(dx_pos + box_w / 2, level1_y, tele_x + tele_w / 2, tele_y + tele_h)

# ══════════════════════════════════════════════════════════════
# EBENE 2 — Stationsagenten Ergebnisse (unterhalb C)
# ══════════════════════════════════════════════════════════════
sa_x = 11.2
sa_y = 3.5
sa_w = 4.8
sa_h = 3.0
draw_box(sa_x, sa_y, sa_w, sa_h, C_GREEN,
         "Stationsagenten — Kernergebnisse",
         ["Agenten | Mittel | Max   | Optimum",
          "   1    | 35 min | 75 min|",
          "   3    | 16 min | 34 min| ← Kosten-",
          "   5    | 13 min | 29 min| ← Nutzen",
          "  10    | 10 min | 23 min|",
          "",
          "Minimax-Verteilung (nicht geschachtelt)",
          "99,4% Erfolgsquote | ±5% analytisch",
          "Sättigung ab 5–7 Agenten"],
         fontsize_body=8, status="FERTIG")
draw_arrow(cx_pos + box_w / 2, level1_y, sa_x + sa_w / 2, sa_y + sa_h)

# ══════════════════════════════════════════════════════════════
# LEGENDE
# ══════════════════════════════════════════════════════════════
legend_x = 0.2
legend_y = 0.3
ax.text(legend_x, legend_y + 2.5, "Legende", fontsize=11,
        fontweight="bold", color=C_TEXT)

legend_items = [
    (C_GREEN,  "FERTIG — Vollständig implementiert und simuliert"),
    (C_YELLOW, "BUG — Im Code vorhanden, aber fehlerhaft"),
    (C_RED,    "OFFEN — Nicht implementiert, nicht simuliert"),
    (C_GRAY,   "ERWÄHNT — Nur konzeptionell in der Arbeit"),
]
for i, (color, label) in enumerate(legend_items):
    y_pos = legend_y + 1.8 - i * 0.5
    rect = FancyBboxPatch((legend_x, y_pos), 0.6, 0.35,
                          boxstyle="round,pad=0.03", fc=color, ec="none")
    ax.add_patch(rect)
    ax.text(legend_x + 0.8, y_pos + 0.17, label, fontsize=9,
            va="center", color=C_TEXT)

# ── Parameter-Box unten mitte ──
param_x = 5.5
param_y = 0.3
param_w = 5.5
param_h = 2.5
draw_box(param_x, param_y, param_w, param_h, C_ROOT,
         "Gemeinsame Parameter",
         ["Strecke: Frankfurt U4, 6.723 m, 10 Haltestellen",
          "Störung: VDV Kat. A, alle 25 m (605 Pos.)",
          "Gehgeschwindigkeit: 3,33 m/s (≈ 12 km/h)",
          "Reaktionszeit: 90 s",
          "Simulationstool: SUMO + TraCI (Python)",
          "Geometriefaktor: ×1,08 (Tunnelkurven)"],
         fontsize_body=9, title_color="white")

# ── Titel ──
ax.text(11, 15.8, "Rückfallebenen-Übersicht — Masterarbeit Horsthemke",
        ha="center", fontsize=16, fontweight="bold", color=C_ROOT)
ax.text(11, 15.45, "Einheitsstörung VDV Kategorie A · Frankfurt U4 · SUMO-Simulation · Stand 2026-04-07",
        ha="center", fontsize=10, color=C_GRAY)

# ── Speichern ──
plt.tight_layout()
plt.savefig("/Users/moritzhorsthemke/Desktop/Rueckfallebenen_Uebersicht.png",
            dpi=200, bbox_inches="tight", facecolor="white")
plt.savefig("/Users/moritzhorsthemke/Desktop/Rueckfallebenen_Uebersicht.pdf",
            bbox_inches="tight", facecolor="white")
print("Gespeichert: Rueckfallebenen_Uebersicht.png + .pdf auf dem Schreibtisch")
