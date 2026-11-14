r"""eda_ui.py -- el «look» de EDA para las ventanas aparte (Buddy, Options, Controles, Inventario).

Copiado de la interfaz del juego (lobby, 13-nov): marco de ACERO con bisel, placa de título oscura
con letras separadas (como «L O B B Y») y una luz roja debajo, paneles negros con borde gris fino,
cabeceras de columna en cian, botones de metal con degradé (morado «Search Stage», verde azulado
«Create Stage», granate «Enter») y filas con marco claro («LV 30  Mazino»).

Sólo tkinter (sin PIL). Todas las ventanas: sin barra de Windows, se arrastran por la placa.
"""
import os
import sys
import tkinter as tk

NEGRO = "#050607"
FONDO = "#0d0e10"
PANEL = "#08090b"
ACERO_CLARO = "#c9ccd1"
ACERO = "#7d828a"
ACERO_OSCURO = "#34373c"
TEXTO = "#e6e6e6"
GRIS = "#8a8f96"
CIAN = "#7fd6ff"
CIAN_BRILLO = "#d9f3ff"
ROJO = "#8e1b1b"
ROJO_VIVO = "#e0262b"
ROJO_LUZ = "#ff3b3b"
VERDE = "#3ddc84"
VERDE_CHAT = "#4cd964"
ORO = "#e0b84f"

# (arriba, abajo) de cada botón, como los del lobby
ESTILOS = {
    "morado": ("#454a86", "#15172e"),
    "teal": ("#3c706c", "#102423"),
    "granate": ("#7a2a2a", "#240a0a"),
    "acero": ("#5b6068", "#16181b"),
}

FUENTE = ("Tahoma", 9)
FUENTE_B = ("Tahoma", 9, "bold")
CHICA = ("Tahoma", 8)
TITULO = ("Trebuchet MS", 12, "bold")


def con_dpi():
    """Coordenadas en píxeles reales (pantallas al 125 %)."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:                                         # noqa: BLE001
        pass


def mezcla(a, b, t):
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def degrade(cv, x0, y0, x1, y1, arriba, abajo, tag=None):
    h = max(1, y1 - y0)
    for i in range(h):
        cv.create_line(x0, y0 + i, x1, y0 + i, fill=mezcla(arriba, abajo, i / h), tags=tag)


def espaciado(texto):
    return " ".join(texto.upper())


class Ventana:
    """Una ventana EDA: marco de acero + placa con el título + `self.cuerpo` (un Frame) adentro.

    ancho/alto en píxeles «de 96 dpi» (se escalan). `raiz` None = Tk nueva; si no, un Toplevel."""

    def __init__(self, titulo, ancho, alto, raiz=None, al_cerrar=None, placa=None):
        if raiz is None:
            con_dpi()
            self.tk = tk.Tk()
        else:
            self.tk = tk.Toplevel(raiz)
        self.escala = self.tk.winfo_fpixels("1i") / 96.0
        self.ancho, self.alto = self.e(ancho), self.e(alto)
        self.tk.title(titulo)
        self.tk.overrideredirect(True)
        self.tk.attributes("-topmost", True)
        self.tk.configure(bg=NEGRO)
        self.tk.geometry("%dx%d+80+80" % (self.ancho, self.alto))
        self.al_cerrar = al_cerrar or self.cerrar
        cv = self.cv = tk.Canvas(self.tk, width=self.ancho, height=self.alto, bg=NEGRO,
                                 highlightthickness=0)
        cv.place(x=0, y=0)
        self.placa = placa or titulo
        self._marco(self.placa)
        borde, cab = self.e(9), self.e(52)
        self.cuerpo = tk.Frame(self.tk, bg=FONDO)
        self.cuerpo.place(x=borde, y=cab, width=self.ancho - 2 * borde, height=self.alto - cab - borde)
        self._arrastre = (0, 0)
        cv.tag_bind("placa", "<Button-1>", self._toma)
        cv.tag_bind("placa", "<B1-Motion>", self._mueve)
        cv.bind("<Button-1>", self._toma)
        cv.bind("<B1-Motion>", self._mueve)

    def e(self, n):
        return int(round(n * getattr(self, "escala", 1.0)))

    # ── el marco ───────────────────────────────────────────────────────────────────────────────
    def _marco(self, titulo):
        cv, w, h, e = self.cv, self.ancho, self.alto, self.e
        # acero: bandas del claro al oscuro, como el bisel del lobby
        bandas = ["#1b1d20", "#5c6168", "#b9bdc3", "#8d939b", "#4a4e54", "#24272b", "#0d0e10"]
        for i, color in enumerate(bandas):
            cv.create_rectangle(i, i, w - 1 - i, h - 1 - i, outline=color)
        # remaches en las esquinas
        for x, y in ((e(12), e(12)), (w - e(12), e(12)), (e(12), h - e(12)), (w - e(12), h - e(12))):
            cv.create_oval(x - e(3), y - e(3), x + e(3), y + e(3), fill="#9aa0a8", outline="#2a2d31")
            cv.create_oval(x - e(1), y - e(1), x + e(1), y + e(1), fill="#e8eaee", outline="")
        # la placa del título (bisel cortado, oscura, letras separadas)
        pw = min(w - e(60), max(e(170), e(15) * len(titulo) + e(40)))
        px0, py0, px1, py1 = (w - pw) // 2, e(8), (w + pw) // 2, e(40)
        c = e(10)
        forma = [px0 + c, py0, px1 - c, py0, px1, py0 + c, px1, py1 - c, px1 - c, py1, px0 + c, py1,
                 px0, py1 - c, px0, py0 + c]
        cv.create_polygon(forma, fill="#0a0b0d", outline=ACERO_CLARO, width=2, tags="placa")
        interior = [px0 + c + 3, py0 + 4, px1 - c - 3, py0 + 4, px1 - 4, py0 + c + 1, px1 - 4, py1 - c - 1,
                    px1 - c - 3, py1 - 4, px0 + c + 3, py1 - 4, px0 + 4, py1 - c - 1, px0 + 4, py0 + c + 1]
        cv.create_polygon(interior, fill="", outline="#3a3e44", tags="placa")
        # la luz roja debajo (como la de LOBBY)
        for i, color in enumerate(("#3a0606", "#7a0d0d", ROJO_LUZ, "#7a0d0d", "#3a0606")):
            cv.create_line(px0 + c + e(10), py1 + 3 + i, px1 - c - e(10), py1 + 3 + i, fill=color)
        cv.create_text((px0 + px1) // 2 + 1, (py0 + py1) // 2 + 1, text=espaciado(titulo), fill="#1f6f8f",
                       font=TITULO, tags="placa")
        cv.create_text((px0 + px1) // 2, (py0 + py1) // 2, text=espaciado(titulo), fill=CIAN_BRILLO,
                       font=TITULO, tags="placa")
        # cerrar: una X de metal arriba a la derecha
        x, y = w - e(24), e(22)
        cv.create_oval(x - e(9), y - e(9), x + e(9), y + e(9), fill="#1a1c1f", outline=ACERO, tags="cerrar")
        cv.create_text(x, y, text="✕", fill=GRIS, font=FUENTE_B, tags=("cerrar", "cerrar_x"))
        cv.tag_bind("cerrar", "<Button-1>", lambda ev: self.al_cerrar())
        cv.tag_bind("cerrar", "<Enter>", lambda ev: cv.itemconfigure("cerrar_x", fill=ROJO_LUZ))
        cv.tag_bind("cerrar", "<Leave>", lambda ev: cv.itemconfigure("cerrar_x", fill=GRIS))

    def _toma(self, ev):
        self._arrastre = (ev.x_root - self.tk.winfo_x(), ev.y_root - self.tk.winfo_y())

    def _mueve(self, ev):
        self.tk.geometry("+%d+%d" % (ev.x_root - self._arrastre[0], ev.y_root - self._arrastre[1]))

    def cerrar(self):
        self.tk.destroy()

    def ubicar(self, x, y, alto=None):
        if alto and alto != self.alto:
            self.alto = alto
            self.cv.configure(height=alto)
            self.cv.delete("all")
            self._marco(self.placa)
            self.cuerpo.place_configure(height=alto - self.e(52) - self.e(9))
        self.tk.geometry("%dx%d+%d+%d" % (self.ancho, self.alto, x, y))

    def centrar_en_juego(self):
        dato = ventana_del_juego()
        if dato:
            (x, y, w, h), _ = dato
            self.ubicar(x + (w - self.ancho) // 2, y + (h - self.alto) // 2)
        else:
            sw, sh = self.tk.winfo_screenwidth(), self.tk.winfo_screenheight()
            self.ubicar((sw - self.ancho) // 2, (sh - self.alto) // 2)


class Boton(tk.Canvas):
    """Un botón de metal del lobby. estilo: morado / teal / granate / acero."""

    def __init__(self, padre, texto, accion, estilo="acero", ancho=96, alto=24, escala=1.0, icono=""):
        self.ew, self.eh = int(ancho * escala), int(alto * escala)
        try:
            bg = padre.cget("bg")
        except tk.TclError:
            bg = FONDO
        super().__init__(padre, width=self.ew, height=self.eh, bg=bg, highlightthickness=0, cursor="hand2")
        self.texto, self.accion, self.estilo, self.icono = texto, accion, estilo, icono
        self.activo = True
        self._dibujar(False)
        self.bind("<Enter>", lambda ev: self._dibujar(True))
        self.bind("<Leave>", lambda ev: self._dibujar(False))
        self.bind("<Button-1>", lambda ev: self.activo and self.accion())

    def _dibujar(self, encima):
        self.delete("all")
        w, h = self.ew, self.eh
        arriba, abajo = ESTILOS.get(self.estilo, ESTILOS["acero"])
        if not self.activo:
            arriba, abajo = "#2a2c30", "#141518"
        self.create_rectangle(0, 0, w - 1, h - 1, outline="#0a0a0a", fill="#0a0a0a")
        degrade(self, 2, 2, w - 2, h - 2, mezcla(arriba, "#ffffff", 0.12) if encima else arriba, abajo)
        self.create_line(2, 2, w - 3, 2, fill=mezcla(arriba, "#ffffff", 0.45))
        self.create_rectangle(1, 1, w - 2, h - 2, outline=ROJO_LUZ if encima and self.activo else ACERO_CLARO)
        color = TEXTO if self.activo else GRIS
        txt = (self.icono + "  " if self.icono else "") + self.texto
        self.create_text(w // 2 + 1, h // 2 + 1, text=txt, fill="#000000", font=FUENTE_B)
        self.create_text(w // 2, h // 2, text=txt, fill=color, font=FUENTE_B)

    def habilitar(self, si):
        self.activo = bool(si)
        self._dibujar(False)


class Pestana(tk.Canvas):
    """Una pestaña como «Scenario»: oscura, letras cian; la elegida con la luz roja abajo."""

    def __init__(self, padre, texto, accion, ancho=110, alto=26, escala=1.0):
        self.ew, self.eh = int(ancho * escala), int(alto * escala)
        super().__init__(padre, width=self.ew, height=self.eh, bg=padre.cget("bg"), highlightthickness=0,
                         cursor="hand2")
        self.texto, self.elegida = texto, False
        self.bind("<Button-1>", lambda ev: accion())
        self._dibujar()

    def elegir(self, si):
        self.elegida = si
        self._dibujar()

    def _dibujar(self):
        self.delete("all")
        w, h = self.ew, self.eh
        degrade(self, 1, 1, w - 1, h, "#23413f" if self.elegida else "#1a1c20", "#050607")
        self.create_polygon(1, h, 1, 5, 6, 1, w - 7, 1, w - 2, 5, w - 2, h, outline=ACERO_CLARO if self.elegida
                            else ACERO, fill="")
        self.create_text(w // 2, h // 2 + 1, text=self.texto, fill=CIAN if self.elegida else GRIS,
                         font=("Tahoma", 10, "bold") if self.elegida else FUENTE)
        if self.elegida:
            self.create_line(8, h - 2, w - 8, h - 2, fill=ROJO_LUZ, width=2)


def panel(padre, **kw):
    """Un panel negro con el borde gris fino (como la lista de salas)."""
    marco = tk.Frame(padre, bg=ACERO, padx=1, pady=1)
    adentro = tk.Frame(marco, bg=PANEL, highlightthickness=1, highlightbackground="#1f2226", **kw)
    adentro.pack(fill="both", expand=True)
    return marco, adentro


def cabecera(padre, columnas):
    """La franja de títulos de columna en cian (Number | Stage Name | …). columnas: [(texto, peso)]."""
    f = tk.Frame(padre, bg="#0b1a1f")
    for i, (texto, peso) in enumerate(columnas):
        tk.Label(f, text=texto, bg="#0b1a1f", fg=CIAN, font=CHICA, anchor="w" if i else "center").grid(
            row=0, column=i, sticky="we", padx=4)
        f.grid_columnconfigure(i, weight=peso)
    return f


def entrada(padre, ancho=None):
    """Un campo como el del chat del juego: negro, borde gris, cursor cian."""
    return tk.Entry(padre, bg="#000000", fg=TEXTO, insertbackground=CIAN, relief="flat", font=FUENTE,
                    highlightthickness=1, highlightbackground=ACERO, highlightcolor=CIAN,
                    **({"width": ancho} if ancho else {}))


# ── la ventana del juego ───────────────────────────────────────────────────────────────────────
def ventana_por_proceso():
    """La ventana visible más grande de un proceso EDA*.exe (EDA_cpinfo.exe / EDA.exe): en el lobby
    la ventana ya no se llama «LithTech»."""
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    halladas = []

    def ver(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        if es_del_juego(hwnd):
            r = wintypes.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(r))
            halladas.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
        return True

    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u32.EnumWindows(proc(ver), 0)
    return max(halladas)[1] if halladas else 0


def es_del_juego(hwnd):
    """¿La ventana es de un proceso EDA*.exe?"""
    try:
        import ctypes
        from ctypes import wintypes
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        h = k32.OpenProcess(0x1000, False, pid.value)
        if not h:
            return False
        buf = ctypes.create_unicode_buffer(520)
        n = ctypes.c_ulong(520)
        k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
        k32.CloseHandle(h)
        nombre = buf.value.rsplit("\\", 1)[-1].lower()
        return nombre.startswith("eda") and nombre.endswith(".exe")
    except Exception:                                         # noqa: BLE001
        return False


def ventana_del_juego():
    """((x, y, ancho, alto) de la ventana del juego, (izq, arr, der, aba) del área de su monitor)."""
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        hwnd = ventana_por_proceso()
        if not hwnd:
            return None
        r = wintypes.RECT()
        u32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))

        class INFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        info = INFO()
        info.cbSize = ctypes.sizeof(INFO)
        u32.MonitorFromWindow.restype = ctypes.c_void_p
        u32.GetMonitorInfoW(ctypes.c_void_p(u32.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)), ctypes.byref(info))
        w = info.rcWork
        return (r.left, r.top, r.right - r.left, r.bottom - r.top), (w.left, w.top, w.right, w.bottom)
    except Exception:                                         # noqa: BLE001
        return None


def al_lado(juego, area, ancho):
    """La x de un panel: a la derecha del juego si entra en su monitor, si no a la izquierda."""
    x, y, w, h = juego
    if x + w + 4 + ancho <= area[2]:
        return x + w + 4
    return max(area[0], x - ancho - 4)


def una_instancia(archivo):
    """Deja una sola copia de esta ventana: cierra la vieja (su pid en `archivo`) y anota la nueva."""
    try:
        viejo = int(open(archivo).read().strip())
    except (OSError, ValueError):
        viejo = 0
    if viejo and viejo != os.getpid():
        matar_si_python(viejo)
    try:
        os.makedirs(os.path.dirname(archivo), exist_ok=True)
        open(archivo, "w").write(str(os.getpid()))
    except OSError:
        pass


def vivo(archivo):
    """¿El pid anotado en `archivo` es un python vivo?"""
    try:
        pid = int(open(archivo).read().strip())
    except (OSError, ValueError):
        return False
    return _imagen(pid) is not None and "python" in _imagen(pid).lower()


def _imagen(pid):
    if sys.platform != "win32":
        return None
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        codigo = ctypes.c_ulong(0)
        k32.GetExitCodeProcess(h, ctypes.byref(codigo))
        if codigo.value != 259:                               # STILL_ACTIVE
            return None
        buf = ctypes.create_unicode_buffer(520)
        n = ctypes.c_ulong(520)
        k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
        return buf.value
    finally:
        k32.CloseHandle(h)


def matar_si_python(pid):
    if "python" not in (_imagen(pid) or "").lower():
        return False
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x0001, False, pid)
    if h:
        k32.TerminateProcess(h, 0)
        k32.CloseHandle(h)
        return True
    return False


class Deslizador(tk.Canvas):
    """Una barra de metal con relleno rojo y perilla de acero. `variable` = tk.DoubleVar."""

    def __init__(self, padre, variable, desde, hasta, ancho=240, escala=1.0, formato="%d"):
        self.ew, self.eh = int(ancho * escala), int(22 * escala)
        super().__init__(padre, width=self.ew + int(44 * escala), height=self.eh, bg=padre.cget("bg"),
                         highlightthickness=0, cursor="hand2")
        self.var, self.desde, self.hasta, self.formato = variable, desde, hasta, formato
        self.bind("<Button-1>", self._mover)
        self.bind("<B1-Motion>", self._mover)
        self.bind("<MouseWheel>", lambda ev: self._poner(self.var.get() + (1 if ev.delta > 0 else -1)))
        self._dibujar()

    def _poner(self, valor):
        self.var.set(max(self.desde, min(self.hasta, round(valor))))
        self._dibujar()

    def _mover(self, ev):
        x0, x1 = 8, self.ew - 8
        self._poner(self.desde + (self.hasta - self.desde) * (ev.x - x0) / max(1, x1 - x0))

    def _dibujar(self):
        self.delete("all")
        w, h = self.ew, self.eh
        x0, x1, y = 8, w - 8, h // 2
        t = (self.var.get() - self.desde) / max(1e-9, self.hasta - self.desde)
        xp = x0 + (x1 - x0) * t
        self.create_rectangle(x0 - 1, y - 4, x1 + 1, y + 4, fill="#000000", outline=ACERO)
        if xp > x0:
            degrade(self, x0, y - 3, int(xp), y + 3, ROJO_LUZ, "#5a0b0b")
        self.create_oval(xp - 7, y - 7, xp + 7, y + 7, fill="#9aa0a8", outline="#1a1c1f")
        self.create_oval(xp - 3, y - 3, xp + 3, y + 3, fill="#e8eaee", outline="")
        self.create_text(w + 22, y, text=self.formato % self.var.get(), fill=CIAN_BRILLO, font=FUENTE_B)


class Casilla(tk.Frame):
    """Un interruptor con LED: rojo encendido / apagado oscuro. `variable` = tk.BooleanVar."""

    def __init__(self, padre, texto, variable, escala=1.0, al_cambiar=None):
        super().__init__(padre, bg=padre.cget("bg"), cursor="hand2")
        self.var, self.al_cambiar = variable, al_cambiar
        s = int(16 * escala)
        self.led = tk.Canvas(self, width=s, height=s, bg=self.cget("bg"), highlightthickness=0)
        self.led.pack(side="left", padx=(0, int(8 * escala)))
        self.lbl = tk.Label(self, text=texto, bg=self.cget("bg"), fg=TEXTO, font=FUENTE)
        self.lbl.pack(side="left")
        for w in (self, self.led, self.lbl):
            w.bind("<Button-1>", self._alternar)
        self.s = s
        self._dibujar()

    def _alternar(self, ev=None):
        self.var.set(not self.var.get())
        self._dibujar()
        if self.al_cambiar:
            self.al_cambiar()

    def _dibujar(self):
        c, s = self.led, self.s
        c.delete("all")
        c.create_rectangle(0, 0, s - 1, s - 1, fill="#000000", outline=ACERO_CLARO)
        if self.var.get():
            c.create_rectangle(3, 3, s - 4, s - 4, fill=ROJO_LUZ, outline="#ff9a9a")
        else:
            c.create_rectangle(3, 3, s - 4, s - 4, fill="#1b1d20", outline="#2a2d31")
        self.lbl.configure(fg=TEXTO if self.var.get() else GRIS)


class Selector(tk.Frame):
    """Opciones en fila (como pestañas chicas): una sola elegida. `variable` = tk.Variable."""

    def __init__(self, padre, opciones, variable, escala=1.0, ancho=150):
        super().__init__(padre, bg=padre.cget("bg"))
        self.var, self.botones = variable, []
        for valor, texto in opciones:
            cv = tk.Canvas(self, width=int(ancho * escala), height=int(26 * escala), bg=self.cget("bg"),
                           highlightthickness=0, cursor="hand2")
            cv.pack(side="left", padx=(0, 4))
            cv.bind("<Button-1>", lambda ev, v=valor: (self.var.set(v), self._dibujar()))
            self.botones.append((valor, texto, cv))
        self._dibujar()

    def _dibujar(self):
        for valor, texto, cv in self.botones:
            cv.delete("all")
            w, h = int(cv.cget("width")), int(cv.cget("height"))
            si = self.var.get() == valor
            degrade(cv, 1, 1, w - 1, h - 1, "#3c706c" if si else "#1e2024", "#0b1312" if si else "#060708")
            cv.create_rectangle(0, 0, w - 1, h - 1, outline=CIAN if si else ACERO)
            cv.create_text(w // 2, h // 2, text=texto, fill=CIAN_BRILLO if si else GRIS,
                           font=FUENTE_B if si else FUENTE)
