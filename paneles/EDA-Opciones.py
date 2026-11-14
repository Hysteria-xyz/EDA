"""Opciones de EDA: pantalla, sonido, mouse y calidad gráfica.

El botón «Options» del lobby no hace nada en el cliente de 2009 (medido en el exe: el control 5
de la barra no tiene función asociada), así que las opciones se eligen acá.

Detalles medidos el 13-nov:
  · El juego lee las opciones de repo\\_trabajo\\juego\\autoexec.cfg al abrir y LO REESCRIBE AL
    SALIR: lo que se cambie ahí con el juego abierto se pierde. Por eso las opciones se guardan
    en EDA-opciones.json y EDA-Jugar.bat las vuelve a aplicar antes de cada partida
    (`python EDA-Opciones.py --aplicar`).
  · La interfaz de 2009 está hecha para 800×600 y NO se escala: con 1024×768 los menús quedan en
    la esquina y el resto negro. Para jugar grande: «Pantalla completa» (800×600 estirado por el
    monitor).

    python EDA-Opciones.py            # la ventana de opciones
    python EDA-Opciones.py --aplicar  # sólo aplica EDA-opciones.json al autoexec.cfg
    python EDA-Opciones.py --ubicar   # espera la ventana del juego y la centra en su monitor
    python EDA-Opciones.py --prueba   # pruebas sin el juego
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CFG = RAIZ / "repo" / "_trabajo" / "juego" / "autoexec.cfg"
OPCIONES = RAIZ / "EDA-opciones.json"
PANEL_PID = RAIZ / "repo" / "_trabajo" / "servidor" / "opciones_panel.pid"
sys.path.insert(0, str(RAIZ))

# clave del autoexec.cfg → (valor por defecto, cómo se escribe)
POR_DEFECTO = {
    "pantalla_completa": False,
    "musica": 100,
    "efectos": 50,
    "sensibilidad": 6,          # ×0.001 = el «scale» del mouse (el juego trae 0.006)
    "sombras": False,           # ModelShadow_Proj_Enable
    "texturas_detalle": False,  # DetailTextures
    "reflejos": False,          # EnvMapEnable
    "niebla": True,             # FogEnable
    "brillo": False,            # ★ 14-nov: el BRILLO de la ropa con piedras (ScreenGlow); apagado como
                                #   el original (el brillo por color de gema quedó para la «etapa 2»). En las stages
                                #   lo enciende el mapa (0x404a00); en el lobby, con la intensidad medida
                                #   a ojo (GaussAmp 0.045 / 0.035: con la de fábrica queda todo blanco)
    "monitor": 1,               # 1 = el principal; 2… = los otros, de izquierda a derecha
}


def leer_opciones():
    datos = dict(POR_DEFECTO)
    try:
        datos.update(json.loads(OPCIONES.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return datos


def aplicar(texto, op):
    """Devuelve el autoexec.cfg (texto latin-1) con las opciones `op` puestas."""
    valores = {
        "windowed": "0" if op["pantalla_completa"] else "1",
        "screenwidth": "800",
        "screenheight": "600",
        "MusicVolume": "%.2f" % (max(0, min(100, op["musica"])) / 100),
        "SoundVolume": "%.2f" % (max(0, min(100, op["efectos"])) / 100),
        "ModelShadow_Proj_Enable": "1" if op["sombras"] else "0",
        "DetailTextures": "1" if op["texturas_detalle"] else "0",
        "EnvMapEnable": "1" if op["reflejos"] else "0",
        "FogEnable": "1" if op["niebla"] else "0",
        "ScreenGlowEnable": "1" if op.get("brillo", False) else "0",
        "ScreenGlowGaussAmp0": "0.045",
        "ScreenGlowGaussAmp1": "0.035",
        "alwaysfocused": "0",       # (como el original: el foco lo maneja eda_original.py FOCO_JS)
    }
    nl = "\r\n" if "\r\n" in texto else "\n"
    for clave, valor in valores.items():
        linea = '"%s" "%s"' % (clave, valor)
        texto, n = re.subn(r'(?m)^"%s" "[^"\r\n]*"' % re.escape(clave), linea, texto)
        if not n:
            texto = linea + nl + texto
    escala = "%.6f" % (max(1, min(30, op["sensibilidad"])) / 1000)
    for eje in ("x-axis", "y-axis"):
        texto, n = re.subn(r'(?m)^scale "##mouse" "##%s" [0-9.]+' % eje,
                           'scale "##mouse" "##%s" %s' % (eje, escala), texto)
        if not n:
            texto += 'scale "##mouse" "##%s" %s%s' % (eje, escala, nl)
    return texto


def aplicar_al_juego(op=None):
    if not CFG.is_file():
        return False
    texto = CFG.read_bytes().decode("latin-1")
    nuevo = aplicar(texto, op or leer_opciones())
    if nuevo != texto:
        temporal = CFG.with_suffix(".cfg.tmp")
        temporal.write_bytes(nuevo.encode("latin-1"))
        temporal.replace(CFG)
    return True


# ★ EL MONITOR. El juego abre su ventana («LithTech») siempre en el principal; con dos monitores,
#   `--ubicar` (lo lanza EDA-Jugar.bat, aparte) la espera y la centra en el elegido. Sólo en modo
#   ventana: la pantalla completa la pone Direct3D en el principal.
def monitores():
    """[(izquierda, arriba, derecha, abajo)] del área de trabajo de cada monitor: el principal
    primero y los demás de izquierda a derecha."""
    import ctypes
    from ctypes import wintypes
    lista = []

    class INFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    def uno(hmon, hdc, rect, dato):
        info = INFO()
        info.cbSize = ctypes.sizeof(INFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        r = info.rcWork
        lista.append((not (info.dwFlags & 1), r.left, (r.left, r.top, r.right, r.bottom)))
        return True
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HMONITOR, wintypes.HDC,
                              ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, PROC(uno), 0)
    return [r for _, _, r in sorted(lista)]


def centrada(area, ancho, alto):
    """La esquina (x, y) para centrar una ventana de ancho × alto en `area`."""
    izq, arr, der, aba = area
    return izq + max(0, (der - izq - ancho) // 2), arr + max(0, (aba - arr - alto) // 2)


def ubicar(op=None, espera=90):
    """Espera la ventana del juego y la mueve, centrada, al monitor elegido."""
    import ctypes
    import time
    from ctypes import wintypes
    op = op or leer_opciones()
    if op.get("pantalla_completa") or op.get("monitor", 1) <= 1:
        return False
    areas = monitores()
    if op["monitor"] > len(areas):
        return False
    u32 = ctypes.windll.user32
    fin = time.time() + espera
    movida = 0
    while time.time() < fin:
        hwnd = u32.FindWindowW(None, "LithTech")
        if hwnd:
            r = wintypes.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(r))
            ancho, alto = r.right - r.left, r.bottom - r.top
            x, y = centrada(areas[op["monitor"] - 1], ancho, alto)
            if (r.left, r.top) != (x, y):
                u32.SetWindowPos(hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE|NOZORDER|NOACTIVATE
            movida += 1
            if movida >= 6:                  # (el juego a veces se reubica al arrancar: unos segundos más)
                return True
        time.sleep(0.5)
    return movida > 0


def ventana():
    """★ Options al estilo EDA (13-nov): ancha, menú de metal a la izquierda (como la barra del lobby)
    y el contenido a la derecha; LEDs rojos y barras de acero. Distinta del Buddy (angosto, lista)."""
    import tkinter as tk
    import eda_ui as ui

    op = leer_opciones()
    v = ui.Ventana("Options", 660, 450)
    ui.una_instancia(str(PANEL_PID))
    e, sc = v.e, v.escala

    izquierda = tk.Frame(v.cuerpo, bg="#0a0b0d", highlightthickness=1, highlightbackground=ui.ACERO_OSCURO)
    izquierda.pack(side="left", fill="y", padx=(e(8), 0), pady=e(8))
    marco, derecha = ui.panel(v.cuerpo)
    marco.pack(side="left", fill="both", expand=True, padx=e(8), pady=e(8))

    completa = tk.BooleanVar(value=op["pantalla_completa"])
    try:
        cuantos = len(monitores())
    except Exception:                                         # noqa: BLE001
        cuantos = 1
    monitor = tk.IntVar(value=min(op.get("monitor", 1), max(1, cuantos)))
    musica = tk.DoubleVar(value=op["musica"])
    efectos = tk.DoubleVar(value=op["efectos"])
    sens = tk.DoubleVar(value=op["sensibilidad"])
    sombras = tk.BooleanVar(value=op["sombras"])
    detalle = tk.BooleanVar(value=op["texturas_detalle"])
    reflejos = tk.BooleanVar(value=op["reflejos"])
    niebla = tk.BooleanVar(value=op["niebla"])
    brillo = tk.BooleanVar(value=op.get("brillo", False))

    def titulo(padre, texto):
        f = tk.Frame(padre, bg=ui.PANEL)
        f.pack(fill="x", pady=(e(10), e(6)))
        tk.Label(f, text=texto.upper(), bg=ui.PANEL, fg=ui.CIAN, font=("Tahoma", 10, "bold")).pack(side="left")
        tk.Frame(f, bg=ui.ROJO, height=2).pack(side="left", fill="x", expand=True, padx=(e(8), 0), pady=e(8))

    def nota(padre, texto):
        tk.Label(padre, text=texto, bg=ui.PANEL, fg=ui.GRIS, font=ui.CHICA, justify="left",
                 wraplength=e(400)).pack(anchor="w", pady=(e(4), 0))

    def fila(padre, texto):
        f = tk.Frame(padre, bg=ui.PANEL)
        f.pack(fill="x", pady=e(5))
        tk.Label(f, text=texto, bg=ui.PANEL, fg=ui.TEXTO, font=ui.FUENTE, width=14, anchor="w").pack(side="left")
        return f

    def video(p):
        titulo(p, "Pantalla")
        ui.Selector(fila(p, "Modo"), [(False, "Ventana"), (True, "Pantalla completa")], completa, sc,
                    150).pack(side="left")
        if cuantos > 1:
            ui.Selector(fila(p, "Monitor"), [(k, "%d%s" % (k, " · principal" if k == 1 else ""))
                                              for k in range(1, cuantos + 1)], monitor, sc, 110).pack(side="left")
        nota(p, "La interfaz de 2009 sólo funciona en 800×600 (en pantalla completa se estira). "
                "El monitor vale en modo ventana.")

    def sonido(p):
        titulo(p, "Sonido")
        ui.Deslizador(fila(p, "Música"), musica, 0, 100, 260, sc).pack(side="left")
        ui.Deslizador(fila(p, "Efectos"), efectos, 0, 100, 260, sc).pack(side="left")

    def mouse(p):
        titulo(p, "Mouse")
        ui.Deslizador(fila(p, "Sensibilidad"), sens, 1, 30, 260, sc).pack(side="left")
        nota(p, "6 = la del juego.")

    def graficos(p):
        titulo(p, "Calidad gráfica")
        for texto, var in (("Brillo de la ropa con piedras", brillo), ("Sombras de los personajes", sombras),
                           ("Texturas de detalle", detalle), ("Reflejos", reflejos), ("Niebla", niebla)):
            ui.Casilla(p, texto, var, sc).pack(anchor="w", pady=e(5))

    def controles(p):
        titulo(p, "Controles")
        nota(p, "Habilidades F1–F8, ítems de HP/MP, moverse (WASD), mouse, cambiar de arma, defender…: "
                "cada acción con la tecla que quieras.")
        caja = tk.Frame(p, bg=ui.PANEL)
        caja.pack(anchor="w", pady=e(12))
        ui.Boton(caja, "CAMBIAR TECLAS", abrir_teclas, "morado", 170, 30, sc).pack(side="left")
        titulo(p, "Atajos")
        for tecla, que in (("F9", "Listo / empezar (en la sala)"), ("F10", "Options"), ("F11", "Messenger"),
                           ("F12", "Clan (reservado)")):
            f = fila(p, tecla)
            f.winfo_children()[0].configure(fg=ui.ORO, font=ui.FUENTE_B, width=6)
            tk.Label(f, text=que, bg=ui.PANEL, fg=ui.TEXTO, font=ui.FUENTE).pack(side="left")

    def abrir_teclas():
        import subprocess
        py = Path(sys.executable).with_name("pythonw.exe")
        subprocess.Popen([str(py if py.exists() else sys.executable), str(RAIZ / "EDA-Teclas.py")],
                         cwd=str(RAIZ))

    secciones = [("VIDEO", video), ("SONIDO", sonido), ("MOUSE", mouse), ("GRÁFICOS", graficos),
                 ("CONTROLES", controles)]
    contenido = tk.Frame(derecha, bg=ui.PANEL)
    contenido.pack(fill="both", expand=True, padx=e(16), pady=e(6))
    menu = []

    def mostrar(i):
        for w in contenido.winfo_children():
            w.destroy()
        for k, (texto, b) in enumerate(menu):
            b.estilo = "granate" if k == i else "acero"
            b._dibujar(False)
        secciones[i][1](contenido)

    tk.Label(izquierda, text="MENU", bg="#0a0b0d", fg=ui.CIAN, font=ui.CHICA).pack(pady=(e(8), e(4)))
    for i, (texto, _) in enumerate(secciones):
        b = ui.Boton(izquierda, texto, lambda i=i: mostrar(i), "acero", 130, 32, sc)
        b.pack(padx=e(8), pady=e(3))
        menu.append((texto, b))

    linea = tk.Label(izquierda, text="", bg="#0a0b0d", fg=ui.VERDE, font=ui.CHICA, wraplength=e(130),
                     justify="left")

    def guardar():
        nuevas = {
            "pantalla_completa": completa.get(), "musica": round(musica.get()),
            "efectos": round(efectos.get()), "sensibilidad": round(sens.get()),
            "sombras": sombras.get(), "texturas_detalle": detalle.get(),
            "reflejos": reflejos.get(), "niebla": niebla.get(), "monitor": monitor.get(),
            "brillo": brillo.get(),
        }
        try:
            OPCIONES.write_text(json.dumps(nuevas, indent=1), encoding="utf-8")
            aplicar_al_juego(nuevas)
        except OSError as exc:
            linea.configure(text=str(exc), fg=ui.ROJO_LUZ)
            return
        linea.configure(text="Aplicado al instante (ventana / pantalla completa y monitor: al reabrir EDA).",
                        fg=ui.VERDE)

    ui.Boton(izquierda, "CERRAR", v.cerrar, "granate", 130, 28, sc).pack(side="bottom", padx=e(8), pady=e(8))
    ui.Boton(izquierda, "GUARDAR", guardar, "teal", 130, 28, sc).pack(side="bottom", padx=e(8))
    linea.pack(side="bottom", padx=e(6), pady=e(6))
    mostrar(0)
    v.centrar_en_juego()
    v.tk.mainloop()


def aplicar_teclas():
    """Las teclas de EDA-teclas.json (EDA-Teclas.py) al autoexec.cfg."""
    import importlib.util
    ruta = RAIZ / "EDA-Teclas.py"
    if not ruta.is_file():
        return False
    spec = importlib.util.spec_from_file_location("eda_teclas", str(ruta))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.aplicar_al_juego()


def prueba():
    base = ('"windowed" "1"\r\n"screenwidth" "1024"\r\n"screenheight" "768"\r\n"MusicVolume" "1.0"\r\n'
            '"FogEnable" "1"\r\nscale "##mouse" "##x-axis" 0.006000\r\nscale "##mouse" "##y-axis" 0.006000\r\n')
    op = dict(POR_DEFECTO, pantalla_completa=True, musica=40, sensibilidad=12, sombras=True, niebla=False)
    t = aplicar(base, op)
    ok = []

    def chequear(n, c):
        print("  %s %s" % ("✅" if c else "⛔", n))
        ok.append(c)
    chequear("pantalla completa → windowed 0", '"windowed" "0"' in t)
    chequear("la resolución vuelve a 800×600", '"screenwidth" "800"' in t and '"screenheight" "600"' in t)
    chequear("música 40 → 0.40", '"MusicVolume" "0.40"' in t)
    chequear("sensibilidad 12 → 0.012 en los dos ejes", t.count("0.012000") == 2)
    chequear("sombras y niebla", '"ModelShadow_Proj_Enable" "1"' in t and '"FogEnable" "0"' in t)
    chequear("alwaysfocused como el original", '"alwaysfocused" "0"' in t)
    chequear("brillo apagado por defecto", '"ScreenGlowEnable" "0"' in t)
    chequear("conserva los finales de línea CRLF", "\r\n" in t and "\n\n" not in t.replace("\r\n", ""))
    chequear("★ el revés: aplicar dos veces da lo mismo", aplicar(t, op) == t)
    # dos monitores: 1920×1040 principal y 1920×1040 a la derecha
    chequear("centrada en el 2º monitor (806×629)", centrada((1920, 0, 3840, 1040), 806, 629) == (2477, 205))
    chequear("★ el revés: una ventana más grande que el monitor no queda fuera",
             centrada((0, 0, 800, 600), 1000, 700) == (0, 0))
    chequear("★ el revés: con pantalla completa o monitor 1, ubicar no mueve nada",
             ubicar(dict(POR_DEFECTO, pantalla_completa=True, monitor=2)) is False
             and ubicar(dict(POR_DEFECTO, monitor=1)) is False)
    print("\n→ TODO BIEN" if all(ok) else "\n→ ⛔ ALGO FALLA")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        sys.exit(prueba())
    if "--ubicar" in sys.argv:
        ubicar()
        sys.exit(0)
    if "--aplicar" in sys.argv:
        aplicar_al_juego()
        aplicar_teclas()
        sys.exit(0)
    if not CFG.is_file():
        import tkinter as tk
        from tkinter import messagebox
        tk.Tk().withdraw()
        messagebox.showerror("EDA", "No se encontró repo\\_trabajo\\juego\\autoexec.cfg.")
        sys.exit(1)
    ventana()
