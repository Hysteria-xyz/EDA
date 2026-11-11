r"""piloto -- llevar el juego solo hasta donde haga falta, con clics por mensaje y una foto por paso.

Sin tocar el mouse de nadie (`clic_juego.py`) y sacando foto de cada pantalla (`foto_juego.py`).
Hace falta el espía andando con su guion (`reglas_broker.py` + `espiar_broker.py control`).

    py herramientas\piloto.py lobby              # abre el juego y lo lleva hasta el lobby
    py herramientas\piloto.py lobby stage        # … y aprieta Create Stage
    py herramientas\piloto.py personajes         # sólo hasta SELECT CHARACTER

Las coordenadas son del ÁREA DE CLIENTE (800×600), medidas en las fotos. Las fotos van a
`_trabajo/fotos/piloto_<hora>_<paso>.png`; el juego queda ABIERTO al terminar.
"""
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clic_juego as C                                       # noqa: E402
import foto_juego as F                                       # noqa: E402

JUEGO = os.path.join(RAIZ, "_trabajo", "juego")

# (nombre, segundos de espera ANTES, clic (x, y) o None)
PASOS = {
    "personajes": [
        ("lista", 7, None),
        ("servidor", 0, (560, 166)),      # la primera fila de SEVER LIST («EDA Local»)
        ("enter", 1, (606, 418)),         # ENTER
        ("personajes", 4, None),
    ],
    "lobby": [
        ("slot1", 1.5, (627, 117)),       # el primer lugar
        ("slot1b", 1, (627, 117)),        # (otra vez: a veces el primero llega antes de tiempo)
        ("enter_lobby", 1, (679, 538)),   # Enter Lobby
        ("lobby", 4, None),
    ],
    "stage": [
        ("create_stage", 0, (495, 356)),  # Create Stage
        ("selector", 4, None),
    ],
    # ★ la stage se abre con DOBLE clic en su marcador (el botón cian de la izquierda)
    "sala": [
        ("marcador", 0, (37, 305)),
        ("marcador2", 0, (37, 305)),      # el segundo clic del doble
        ("create_stage_win", 1.5, None),
        ("titulo_clic", 1.0, (310, 342)), # el campo Room Title (⚠ recién abierta, no toma el foco)
        ("titulo_clic2", 0.8, (310, 342)),
        ("titulo", 1.0, "EDA vuelve"),    # ★ un texto = escribirlo; el ENTER ya manda el 0x101D
        ("sala_ok", 3, None),
        ("sala", 4, None),
    ],
    "partida": [
        ("f9", 0, (672, 455)),            # F9 Start Game
        ("cargando", 5, None),
        ("partida", 10, None),         # ★ con el 0x105E del guion: rui EN EL MAPA
    ],
    # ★ salir de la stage: ESC al `Edit` oculto del IME (a la ventana de arriba no llega; medido)
    #   abre «quit the stage?»; Confirm manda 0x1074 y el 0x1075 del guion lo lleva al LOBBY
    "salir": [
        ("esc", 2, "<ESC>"),
        ("confirm", 1.5, (339, 348)),
        ("lobby_vuelta", 5, None),
    ],
}


def foto(pid, hora, nombre):
    v = F.ventanas_de(pid)
    if not v:
        print("  (sin ventana)")
        return None
    h, _, _, w, hh = v[0]
    ruta = os.path.join(RAIZ, "_trabajo", "fotos", "piloto_%s_%s.png" % (hora, nombre))
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    F.foto(h, w, hh).save(ruta)
    return ruta


def main():
    pedidos = sys.argv[1:] or ["lobby"]
    orden = ["lobby", "stage", "sala", "partida", "salir"]
    hasta = max([orden.index(p) for p in pedidos if p in orden] or [-1])
    secuencia = ["personajes"] + orden[:hasta + 1]
    if os.environ.get("EDA_DESDE"):
        # ★ retomar un juego que se quedó a mitad de camino (con EDA_PID): los tiempos son fijos
        #   y bajo Frida el juego anda más lento (medido: se quedó en SELECT CHARACTER)
        secuencia = secuencia[secuencia.index(os.environ["EDA_DESDE"]):]
    if os.environ.get("EDA_PID"):
        # ★ manejar uno YA abierto (p. ej. el que lanzó `espiar_cripto.py` bajo el depurador)
        class Ya:
            pid = int(os.environ["EDA_PID"])
            returncode = None

            def poll(self):
                return None
        p = Ya()
    else:
        subprocess.run(["taskkill", "/F", "/IM", "EDA_limpio.exe"], capture_output=True)
        time.sleep(0.5)
        # ⚠ la ruta ENTRE COMILLAS (como Windows y Frida): sin ellas el juego toma la ruta entera por el
        #   bloque del launcher y pisa la MAC que manda en el 0x100F (MEDICIONES §39)
        p = subprocess.Popen('"%s"' % os.path.join(JUEGO, "EDA_limpio.exe"), cwd=JUEGO)
    hora = time.strftime("%H%M%S")
    print("★ EDA_limpio.exe pid %d" % p.pid)
    for tramo in secuencia:
        for nombre, espera, punto in PASOS[tramo]:
            time.sleep(espera)
            if p.poll() is not None:
                print("  ⛔ el juego se cerró (código %d) antes de «%s»" % (p.returncode, nombre))
                return 1
            h = C.ventana(p.pid)
            if tramo == "salir":
                # WM_ACTIVATEAPP / WM_ACTIVATE: en la partida, sin esto no lee el teclado. ⚠ SÓLO
                # acá: en todos los pasos, el piloto se quedó en la lista de servidores (medido)
                for m, w in ((0x1C, 1), (0x06, 1)):
                    C.u32.PostMessageW(h, m, w, 0)
                time.sleep(0.4)                       # (sin la pausa, el ESC no abría el cuadro)
            if punto == "<ESC>":
                C.tecla(C.edit_oculto(h) or h, 27)
                C.u32.PostMessageW(C.edit_oculto(h) or h, 0x102, 27, 1)
            elif isinstance(punto, str):
                C.escribir(C.ventana(p.pid), punto)
                time.sleep(0.6)
            elif punto:
                C.clic(C.ventana(p.pid), *punto, pausa=0.03)
                time.sleep(0.15 if nombre.startswith("marcador") else 0.6)
                if nombre == "marcador":
                    continue                      # sin foto entre los dos clics del doble
            print("  %-14s %s" % (nombre, foto(p.pid, hora, nombre) or ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
