r"""servidor/estado.py -- lo que el server recuerda MIENTRAS ANDA (no se guarda en disco).

Lo de cada conexión (una partida): se pierde al cerrar el juego, y está bien. ⚠ Pero NO al recargar
el código (el server recarga `servidor/` cuando cambia un archivo): medido el 10-nov, una recarga a
mitad de partida borró el game over pendiente. Por eso vive en un módulo aparte, `_eda_partidas`,
que la recarga no toca.
"""
import sys
import types

VIVO = sys.modules.get("_eda_partidas")
if VIVO is None:
    VIVO = types.ModuleType("_eda_partidas")
    VIVO.PARTIDAS = {}
    sys.modules["_eda_partidas"] = VIVO
if not hasattr(VIVO, "ASIGNADAS"):
    VIVO.ASIGNADAS = {}                                     # conexión → nombre de la cuenta
if not hasattr(VIVO, "SALAS"):
    VIVO.SALAS = {}                                         # número → {"sala", "anfitrion", "miembros"}
PARTIDAS = VIVO.PARTIDAS
ASIGNADAS = VIVO.ASIGNADAS
SALAS = VIVO.SALAS


def partida(conexion):
    return PARTIDAS.setdefault(conexion, {"escenario": 1011, "muertos": 0, "golpes": 0,
                                          "revividas": 0, "inicio": None, "puntos": 0})
