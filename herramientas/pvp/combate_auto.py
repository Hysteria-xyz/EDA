r"""combate_auto -- ★ PvP: una acción de combate con MARCA y la vida de los DOS jugadores medida antes y después.

    py herramientas\pvp\combate_auto.py paso B "D:0.5 clic:0.15 nada:0.6" --marca kai_pega
    py herramientas\pvp\combate_auto.py barras                 # la barra de vida de A y B, ahora
    py herramientas\pvp\combate_auto.py control                # el control (con su revés), sobre imágenes armadas

Mueve al personaje con `herramientas/control_partida.py` (DirectInput de mentira, EDA_PID) — el mismo teclado y
mouse que el juego lee —, y mide la BARRA ROJA de HP del HUD propio de cada juego (fila 35, x 140–400: 221 píxeles
rojos con la vida llena, medido el 24-nov). El HUD no muestra números: la barra es la evidencia visual.
Cada paso queda en <sesión>\pasos.jsonl (y sus fotos en <sesión>\fotos\); la marca, con el reloj de alta
precisión, en <sesión>\marcas.jsonl, que `udp_combate.py resumen` también lee.
"""
import json
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
HERR = os.path.dirname(AQUI)
sys.path.insert(0, HERR)
sys.path.insert(0, AQUI)
import dos_clientes as D                                     # noqa: E402

FILA_HP = 35
X_HP = (140, 400)
LLENA = 221


def rojo(p):
    return p[0] > 150 and p[1] < 70 and p[2] < 70


def barra(im):
    """Píxeles rojos de la barra de HP propia (0..~221)."""
    return sum(1 for x in range(*X_HP) if rojo(im.getpixel((x, FILA_HP))))


def foto(pid):
    import pantallas
    return pantallas.foto(pid)


def al_frente(pid):
    """★ (24-nov) La d3d9.dll 0.5.4 sólo deja pasar el teclado y el mouse del juego «con EDA al frente»
    (eda_d3d9.log: «[mazino] entrada: DirectInput8 del juego enganchado (teclado y mouse sólo con EDA al frente)»):
    sin esto control_partida.py no mueve al personaje (medido: kai quieto 8 rondas). Trae la ventana al frente."""
    import ctypes
    import pantallas  # noqa: F401  (carga foto_juego en el camino)
    from foto_juego import ventanas_de
    v = ventanas_de(pid)
    if not v:
        return False
    u32 = ctypes.windll.user32
    h = v[0][0]
    u32.ShowWindow(h, 9)                                     # SW_RESTORE
    u32.SwitchToThisWindow(h, True)
    u32.SetForegroundWindow(h)
    time.sleep(0.4)
    return u32.GetForegroundWindow() == h


def qpc_ms():
    import ctypes
    k = ctypes.windll.kernel32
    c, f = ctypes.c_int64(), ctypes.c_int64()
    k.QueryPerformanceCounter(ctypes.byref(c))
    k.QueryPerformanceFrequency(ctypes.byref(f))
    return c.value / f.value * 1000.0


def sesion():
    s = D.leer_sesion()
    if not s:
        raise SystemExit("⛔ no hay sesión de dos_clientes.py")
    return s


def barras(s, carpeta=None, etiqueta=None):
    out = {}
    for i, pid in s["clientes"].items():
        im = foto(pid)
        out[i] = None if im is None else barra(im)
        if im is not None and carpeta:
            os.makedirs(carpeta, exist_ok=True)
            im.save(os.path.join(carpeta, "%s_%s.png" % (etiqueta, i)))
    return out


def paso(quien, plan, marca, espera=1.0):
    s = sesion()
    pid = s["clientes"][quien]
    fotos = os.path.join(s["carpeta"], "fotos")
    n = len(open(os.path.join(s["carpeta"], "pasos.jsonl"), encoding="utf-8").readlines()) \
        if os.path.exists(os.path.join(s["carpeta"], "pasos.jsonl")) else 0
    et = "%02d_%s" % (n + 1, marca)
    antes = barras(s, fotos, et + "_antes")
    frente = al_frente(pid)
    t0 = qpc_ms()
    with open(os.path.join(s["carpeta"], "marcas.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": t0, "q": "marca", "texto": marca, "juego": quien, "plan": plan}) + "\n")
    r = subprocess.run([sys.executable, os.path.join(HERR, "control_partida.py"), "plan", plan],
                       env=dict(os.environ, EDA_PID=str(pid), PYTHONIOENCODING="utf-8"),
                       capture_output=True, text=True, timeout=120)
    time.sleep(espera)
    despues = barras(s, fotos, et + "_despues")
    reg = {"paso": et, "t": t0, "juego": quien, "plan": plan, "antes": antes, "despues": despues,
           "control_partida": r.returncode, "al_frente": frente}
    with open(os.path.join(s["carpeta"], "pasos.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(reg) + "\n")
    cambio = {i: (None if antes[i] is None or despues[i] is None else despues[i] - antes[i]) for i in antes}
    print("· %s (%s%s: %s) → barra de HP antes %s, después %s, cambio %s%s"
          % (et, quien, "" if frente else " ⚠ no quedó al frente", plan, antes, despues, cambio,
             "" if r.returncode == 0 else "  ⚠ control_partida: %s" % (r.stderr or r.stdout)[-300:]))
    return reg


def control():
    from PIL import Image, ImageDraw
    ok = []

    def chequear(nombre, cond):
        ok.append(bool(cond))
        print("  %s %s" % ("✅" if cond else "⛔", nombre))

    im = Image.new("RGB", (800, 600), (10, 10, 30))
    d = ImageDraw.Draw(im)
    d.rectangle((163, 33, 163 + LLENA - 1, 37), fill=(200, 20, 20))
    chequear("una barra llena mide %d" % LLENA, barra(im) == LLENA)
    d.rectangle((163 + 100, 33, 163 + LLENA - 1, 37), fill=(40, 10, 10))
    chequear("con el 45 % de vida mide 100", barra(im) == 100)
    im2 = Image.new("RGB", (800, 600), (10, 10, 30))
    ImageDraw.Draw(im2).rectangle((163, 33, 383, 37), fill=(20, 20, 200))
    chequear("★ el revés: una barra AZUL (el MP) no cuenta como vida", barra(im2) == 0)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "control":
        return control()
    if cmd == "barras":
        print(barras(sesion()))
        return 0
    if cmd == "paso" and len(a) >= 3:
        marca = a[a.index("--marca") + 1] if "--marca" in a else "paso"
        if a[1] not in D.INSTANCIAS:
            raise SystemExit("⛔ paso A|B \"plan\"")
        paso(a[1], a[2], marca)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
