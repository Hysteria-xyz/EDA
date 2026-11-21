r"""servidor -- el server de juego de EDA, por módulos (ver `servidor/LEEME.md`).

`cargar()` devuelve `servidor.juego` y lo RECARGA (con todos sus módulos) cuando cambia cualquier
`.py` de esta carpeta: así el server crece sin reiniciarse. Lo usan `servidor/red.py` (el server
por la red, Linux o Windows) y `herramientas/espiar_broker.py` (el de siempre en Windows).
"""
import glob
import importlib
import os
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
_CARGADO = {"m": None, "t": None}
NO_SE_RECARGAN = {"servidor", "servidor.red"}             # el que está corriendo el bucle de red
# ★ (20-nov, multijugador) EL CANDADO DEL ESTADO. Los dos frentes (servidor/red.py y
#   herramientas/espiar_broker.py) atienden cada conexión en SU hilo, más el reloj (tick) y los
#   cierres: todos tocaban SALAS / PARTIDAS a la vez, sin candado. Dos 0x105F en el mismo instante
#   (medido: 18-nov 10:17:49, 11:54:47, 13:19:25) podían largar la stage DOS veces, y una sala a medio
#   cambiar podía verse desde otro hilo. Todo lo que lee o cambia el estado pasa de a uno por acá.
#   Vive en el paquete (no se recarga), así sobrevive a la recarga de los módulos.
CANDADO = threading.RLock()


def _fecha():
    return max(os.path.getmtime(x) for x in glob.glob(os.path.join(AQUI, "*.py")))


def cargar(avisar=None):
    # ★ (20-nov) mirar las fechas de los .py como mucho una vez por segundo: antes era en CADA mensaje
    #   (un glob + un stat por archivo por paquete, en el hilo que atiende al jugador)
    ahora = time.monotonic()
    if _CARGADO["m"] is not None and ahora - _CARGADO.get("visto", -9.0) < 1.0:
        return _CARGADO["m"]
    t = _fecha()
    _CARGADO["visto"] = ahora
    if _CARGADO["m"] is not None and t == _CARGADO["t"]:
        return _CARGADO["m"]
    with CANDADO:                                           # (dos hilos no recargan a la vez)
        return _recargar(t, avisar)


def _recargar(t, avisar):
    if _CARGADO["m"] is None or t != _CARGADO["t"]:
        paquete = sys.modules[__name__]
        for nombre in [n for n in sys.modules if n.startswith("servidor.") and n not in NO_SE_RECARGAN]:
            del sys.modules[nombre]
            # ⚠ y del paquete: si no, `from servidor import tienda` devuelve el módulo VIEJO (que
            #   registró sus manejadores en el registro viejo) — medido: 31 manejadores → 18
            if hasattr(paquete, nombre.split(".", 1)[1]):
                delattr(paquete, nombre.split(".", 1)[1])
        _CARGADO.update(m=importlib.import_module("servidor.juego"), t=t)
        if avisar:
            avisar("servidor/ (re)cargado")
    return _CARGADO["m"]
