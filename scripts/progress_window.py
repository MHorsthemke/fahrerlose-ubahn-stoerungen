"""
progress_window.py — Tkinter-Fenster für den Batch-Fortschritt.

Live-Anzeige:
  - Zähler + Fortschrittsbalken
  - OK / FEHLER / AUFF
  - Ø t_I + Max t_I
  - Verstrichen / Rest (ETA)

Tkinter ist Teil der Python-Standardbibliothek. Fällt batch.py auf
Terminal-Output zurück, wenn das Fenster nicht geöffnet werden kann.
"""

import time
import tkinter as tk
from tkinter import ttk


def _fmt_time(sec: float) -> str:
    m, s = divmod(int(max(sec, 0)), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class ProgressWindow:
    def __init__(self, total: int, title: str = "Batch-Fortschritt"):
        self.total = total
        self.start = time.time()

        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("460x230")
        self.root.resizable(False, False)

        font_big = ("Menlo", 14, "bold")
        font_mono = ("Menlo", 11)
        pad = {"padx": 16, "pady": 4}

        self.lbl_count = tk.Label(self.root, text=f"0 / {total}  (0.0 %)",
                                  font=font_big)
        self.lbl_count.pack(**pad)

        self.bar = ttk.Progressbar(self.root, length=420, maximum=total)
        self.bar.pack(padx=16, pady=(2, 10))

        self.lbl_status = tk.Label(self.root,
                                   text="OK: 0   FEHLER: 0   AUFF: 0",
                                   font=font_mono)
        self.lbl_status.pack(**pad)

        self.lbl_t = tk.Label(self.root, text="Ø t_I: —   Max: —",
                              font=font_mono)
        self.lbl_t.pack(**pad)

        self.lbl_time = tk.Label(
            self.root, text="Verstrichen: 00:00   Rest: —:—", font=font_mono)
        self.lbl_time.pack(**pad)

        self.root.update()

    def update(self, done: int, ok: int, failed: int, anomaly: int,
               t_values: list[float]) -> None:
        self.bar["value"] = done
        pct = 100 * done / self.total if self.total else 0.0
        self.lbl_count.config(text=f"{done} / {self.total}  ({pct:.1f} %)")
        self.lbl_status.config(
            text=f"OK: {ok}   FEHLER: {failed}   AUFF: {anomaly}")

        if t_values:
            avg = sum(t_values) / len(t_values)
            mx = max(t_values)
            self.lbl_t.config(
                text=f"Ø t_I: {avg/60:5.1f} min   Max: {mx/60:5.1f} min")
        else:
            self.lbl_t.config(text="Ø t_I: —   Max: —")

        elapsed = time.time() - self.start
        if done > 0:
            eta = elapsed * (self.total - done) / done
            self.lbl_time.config(
                text=f"Verstrichen: {_fmt_time(elapsed)}   "
                     f"Rest: {_fmt_time(eta)}")
        else:
            self.lbl_time.config(
                text=f"Verstrichen: {_fmt_time(elapsed)}   Rest: —:—")

        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            pass

    def finish(self, summary: str) -> None:
        try:
            self.lbl_time.config(text=summary, justify="left")
            self.root.title("Batch-Fortschritt — FERTIG")
            self.root.mainloop()
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass


class ConvergenceProgressWindow:
    """
    Persistentes Fenster für die komplette Konvergenzstudie.
    Zeigt aktuelle Variante, aktuelle Stufe, Szenario-Fortschritt der Stufe
    und den Status beider Varianten (ausstehend / läuft / fertig).
    """

    def __init__(self, stages_m: list[int], variants: list[str]):
        self.stages_m = stages_m
        self.variants = variants
        self.variant_status = {v: "ausstehend" for v in variants}
        self.current_variant: str | None = None
        self.current_stage_idx = 0
        self.current_stage_total = 0
        self.stage_start = time.time()
        self.global_start = time.time()

        self.root = tk.Tk()
        self.root.title("Konvergenzstudie")
        self.root.geometry("780x540")
        self.root.resizable(False, False)

        font_big = ("Menlo", 13, "bold")
        font_mono = ("Menlo", 11)
        font_table = ("Menlo", 10)

        self.lbl_variant = tk.Label(self.root, text="(noch nicht gestartet)",
                                    font=font_big)
        self.lbl_variant.pack(pady=(14, 4))
        self.lbl_stage = tk.Label(self.root, text="Stufe —", font=font_mono)
        self.lbl_stage.pack(pady=2)

        self.bar = ttk.Progressbar(self.root, length=440)
        self.bar.pack(pady=(4, 6))
        self.lbl_count = tk.Label(self.root, text="0 / 0", font=font_mono)
        self.lbl_count.pack()

        ttk.Separator(self.root, orient="horizontal").pack(
            fill="x", padx=16, pady=10)

        self.lbl_sa = tk.Label(self.root, text="SA:    ausstehend",
                               font=font_mono, justify="left", anchor="w")
        self.lbl_sa.pack(fill="x", padx=16)
        self.lbl_zub = tk.Label(self.root, text="ZUB+:  ausstehend",
                                font=font_mono, justify="left", anchor="w")
        self.lbl_zub.pack(fill="x", padx=16)

        self.lbl_time = tk.Label(self.root,
                                 text="Verstrichen: 00:00   Rest (Stufe): —",
                                 font=font_mono)
        self.lbl_time.pack(pady=(10, 4))

        ttk.Separator(self.root, orient="horizontal").pack(
            fill="x", padx=16, pady=(4, 6))

        self.lbl_stages_hdr = tk.Label(
            self.root,
            text="Abgeschlossene Stufen (live nach jedem Stufenende):",
            font=font_mono, anchor="w", justify="left")
        self.lbl_stages_hdr.pack(fill="x", padx=16)

        header = (
            f"{'Stufe':<7}{'n':>5}{'KS%pp':>9}{'Δmax%':>9}"
            f"{'t_I_max':>10}{'t_walk_max':>12}{'walk_max_m':>12}"
            f"  Worst-Case"
        )
        self.txt_stages = tk.Text(
            self.root, height=11, font=font_table,
            wrap="none", borderwidth=0, highlightthickness=0,
            background=self.root.cget("background"))
        self.txt_stages.pack(fill="x", padx=16, pady=(2, 8))
        self.txt_stages.insert("end", header + "\n")
        self.txt_stages.insert("end", "-" * (len(header) + 22) + "\n")
        self.txt_stages.config(state="disabled")

        self._refresh_variant_labels()
        self._tick(done=0)

    def set_stage(self, variant: str, stage_idx: int, step_m: int,
                  total: int) -> None:
        self.current_variant = variant
        self.current_stage_idx = stage_idx
        self.current_stage_total = total
        self.stage_start = time.time()
        label = "SA" if variant == "sa" else "ZUB+"
        self.lbl_variant.config(text=f"Variante: {label}")
        self.lbl_stage.config(
            text=f"Stufe {stage_idx}/{len(self.stages_m)}: {step_m} m")
        self.bar.config(maximum=max(total, 1), value=0)
        self.lbl_count.config(text=f"0 / {total}")
        self.variant_status[variant] = \
            f"läuft — Stufe {stage_idx}/{len(self.stages_m)}"
        self._refresh_variant_labels()
        self._tick(done=0)

    def update_scenarios(self, done: int) -> None:
        self.bar.config(value=done)
        self.lbl_count.config(text=f"{done} / {self.current_stage_total}")
        self._tick(done=done)

    def add_stage_result(self, step_m: int, n: int,
                         ks: float | None, dmax: float | None,
                         t_i_max: float, t_walk_max: float,
                         walk_max_m: float, wc_str: str) -> None:
        """Hängt eine Zeile mit den kumulativen Stats nach Stufenende an."""
        ks_str = f"{'—':>8}" if ks is None else f"{ks*100:>8.2f}"
        dm_str = f"{'—':>8}" if dmax is None else f"{dmax*100:>8.2f}"
        line = (f"{step_m:>4} m{n:>6}{ks_str:>9}{dm_str:>9}"
                f"{t_i_max:>8.0f}s{t_walk_max:>10.0f}s{walk_max_m:>10.0f}m"
                f"  {wc_str}\n")
        try:
            self.txt_stages.config(state="normal")
            self.txt_stages.insert("end", line)
            self.txt_stages.see("end")
            self.txt_stages.config(state="disabled")
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            pass

    def mark_variant_done(self, variant: str,
                          converged_at: int | None = None) -> None:
        if converged_at is not None:
            self.variant_status[variant] = f"fertig (Konvergenz bei {converged_at} m)"
        else:
            self.variant_status[variant] = "fertig"
        self._refresh_variant_labels()
        self._tick(done=self.current_stage_total)

    def done(self) -> None:
        self.lbl_variant.config(text="Konvergenzstudie fertig")
        self._tick(done=self.current_stage_total)

    def _refresh_variant_labels(self) -> None:
        mapping = {"sa": ("SA:   ", self.lbl_sa),
                   "zub": ("ZUB+: ", self.lbl_zub)}
        for v in self.variants:
            prefix, widget = mapping[v]
            widget.config(text=f"{prefix} {self.variant_status[v]}")

    def _tick(self, done: int) -> None:
        elapsed = time.time() - self.global_start
        stage_elapsed = time.time() - self.stage_start
        if done > 0 and self.current_stage_total > 0:
            eta = stage_elapsed * (self.current_stage_total - done) / done
            rest = _fmt_time(eta)
        else:
            rest = "—"
        self.lbl_time.config(
            text=f"Verstrichen: {_fmt_time(elapsed)}   Rest (Stufe): {rest}")
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass
