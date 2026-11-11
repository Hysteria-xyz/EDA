r"""servidor -- el server de juego de EDA, por módulos (ver `servidor/LEEME.md`).

`cargar()` devuelve `servidor.juego` y lo RECARGA (con todos sus módulos) cuando cambia cualquier
`.py` de esta carpeta: así el server crece sin reiniciarse. Lo usan `servidor/red.py` (el server
por la red, Linux o Windows) y `herramientas/espiar_broker.py` (el de siempre en Windows).
"""
import glob
import importlib
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
_CARGADO = {"m": None, "t": None}
NO_SE_RECARGAN = {"servidor", "servidor.red"}             # el que está corriendo el bucle de red


def _fecha():
    return max(os.path.getmtime(x) for x in glob.glob(os.path.join(AQUI, "*.py")))


def cargar(avisar=None):
    t = _fecha()
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
