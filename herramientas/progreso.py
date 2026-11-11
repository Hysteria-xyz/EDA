r"""progreso -- una ventanita que muestra en vivo cómo va una corrida larga.

Las corridas de `emular_stub.py` (resolver los 310 sitios, o cruzarlos contra otro volcado)
tardan más de una hora. Esto lee el log mientras se escribe y muestra el avance, sin tocar nada.

    py herramientas\progreso.py                      # agarra el log más nuevo de _trabajo/
    py herramientas\progreso.py _trabajo\cruzar_todos.log

Entiende los dos formatos:
  «  67/310 00622ece  API == API»            (cruzar: cuenta coincidencias)
  «  67/310 00402cb2 -> API  0.1s · ...»     (todos: cuenta resueltos)

⚠ Sólo LEE el archivo. Cerrar la ventana no detiene la corrida.
"""
import glob
import os
import re
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINEA = re.compile(r"^\s*(\d+)/(\d+)\s")
FONDO, TINTA, SUAVE = "#15181d", "#e8eaed", "#9aa0a6"
VERDE, ROJO, BARRA = "#5cc98b", "#e06c6c", "#2a2f38"


def log_mas_nuevo():
    ls = glob.glob(os.path.join(RAIZ, "_trabajo", "*.log"))
    if not ls:
        sys.exit("[!] no hay ningún .log en _trabajo/")
    return max(ls, key=os.path.getmtime)


def hhmmss(s):
    s = int(max(s, 0))
    return "%d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)


class Ventana:
    def __init__(self, ruta):
        self.ruta = ruta
        self.t0 = os.path.getctime(ruta)
        self.raiz = tk.Tk()
        self.raiz.title("EDA · progreso")
        self.raiz.configure(bg=FONDO)
        self.raiz.geometry("560x270")
        self.raiz.minsize(460, 240)
        grande = tkfont.Font(family="Segoe UI", size=26, weight="bold")
        normal = tkfont.Font(family="Segoe UI", size=10)
        chica = tkfont.Font(family="Consolas", size=9)

        tk.Label(self.raiz, text=os.path.basename(ruta), bg=FONDO, fg=SUAVE,
                 font=normal).pack(anchor="w", padx=18, pady=(14, 0))
        self.cuenta = tk.Label(self.raiz, text="—", bg=FONDO, fg=TINTA, font=grande)
        self.cuenta.pack(anchor="w", padx=18)

        self.lienzo = tk.Canvas(self.raiz, height=14, bg=BARRA, highlightthickness=0)
        self.lienzo.pack(fill="x", padx=18, pady=(6, 2))
        self.relleno = self.lienzo.create_rectangle(0, 0, 0, 14, fill=VERDE, width=0)

        self.detalle = tk.Label(self.raiz, text="", bg=FONDO, fg=TINTA, font=normal,
                                justify="left")
        self.detalle.pack(anchor="w", padx=18, pady=(8, 0))
        self.tiempos = tk.Label(self.raiz, text="", bg=FONDO, fg=SUAVE, font=normal)
        self.tiempos.pack(anchor="w", padx=18)
        self.ultima = tk.Label(self.raiz, text="", bg=FONDO, fg=SUAVE, font=chica,
                               anchor="w", wraplength=520, justify="left")
        self.ultima.pack(anchor="w", fill="x", padx=18, pady=(10, 14))
        self.refrescar()

    def leer(self):
        """(hechos, total, bien, mal, última línea útil). Se relee entero: son pocos cientos
        de líneas y así no hay que llevar estado del archivo."""
        try:
            with open(self.ruta, encoding="utf-8", errors="replace") as f:
                lineas = f.read().splitlines()
        except OSError:
            return 0, 0, 0, 0, "(no se puede leer el archivo)"
        hechos = total = bien = mal = 0
        ultima = ""
        for l in lineas:
            m = LINEA.match(l)
            if not m:
                continue
            hechos, total = int(m.group(1)), int(m.group(2))
            ultima = l.strip()
            if " == " in l:
                bien += 1
            elif " != " in l:
                mal += 1
            elif "->" in l:
                mal += 1 if "sin resolver" in l else 0
                bien += 0 if "sin resolver" in l else 1
        return hechos, total, bien, mal, ultima

    def refrescar(self):
        hechos, total, bien, mal, ultima = self.leer()
        pasado = time.time() - self.t0
        if total:
            frac = hechos / float(total)
            self.cuenta.config(text="%d / %d      %d %%" % (hechos, total, round(frac * 100)))
            ancho = self.lienzo.winfo_width() or 1
            self.lienzo.coords(self.relleno, 0, 0, int(ancho * frac), 14)
            self.lienzo.itemconfig(self.relleno, fill=VERDE if mal * 4 < max(bien, 1) else ROJO)
            falta = (pasado / hechos) * (total - hechos) if hechos else 0
            self.tiempos.config(text="van %s   ·   falta ~%s   ·   %.1f s por sitio"
                                     % (hhmmss(pasado), hhmmss(falta), pasado / max(hechos, 1)))
        else:
            self.cuenta.config(text="esperando…")
            self.tiempos.config(text="van %s" % hhmmss(pasado))
        if " == " in ultima or " != " in ultima:
            self.detalle.config(text="coinciden en los dos volcados: %d        difieren: %d"
                                     % (bien, mal))
        else:
            self.detalle.config(text="resueltos: %d        sin resolver: %d" % (bien, mal))
        self.ultima.config(text=ultima or "")
        if hechos and total and hechos >= total:
            self.cuenta.config(fg=VERDE)
            self.tiempos.config(text="terminado en %s" % hhmmss(pasado))
        self.raiz.after(1000, self.refrescar)

    def correr(self):
        self.raiz.mainloop()


if __name__ == "__main__":
    Ventana(sys.argv[1] if len(sys.argv) > 1 else log_mas_nuevo()).correr()
