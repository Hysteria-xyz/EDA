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


# ★ (Punto 3, 18-nov) EL NÚMERO DE JUGADOR DE CADA UNO EN SU SALA, FIJO mientras está en ella. El cliente
#   reconoce a cada miembro por el número que recibió al entrar (+4 / +5 del miembro, `0x61CA30` lo busca
#   así) y nunca los renumera; antes el server usaba el LUGAR en la lista: cuando alguien se iba, los de
#   atrás corrían un lugar y el server los nombraba con un número que su cliente no tenía (el aviso «se
#   fue» o «está listo» no encontraba a nadie, y el nuevo anfitrión no se enteraba de que lo era).
#   Las salas sin "numeros" (las de las pruebas viejas) siguen con el lugar.
def numero(s, conexion):
    nums = s.get("numeros", {})
    return nums[conexion] if conexion in nums else s["miembros"].index(conexion)


def dar_numero(s, conexion):
    """El número más bajo libre (al entrar); el de la sala que ya lo tenía, el mismo."""
    nums = s.setdefault("numeros", {m: i for i, m in enumerate(s["miembros"]) if m != conexion})
    if conexion not in nums:
        nums[conexion] = next(i for i in range(256) if i not in nums.values())
    return nums[conexion]


def de_numero(s, num):
    """La conexión con ese número de jugador en la sala (o None)."""
    return next((m for m in s["miembros"] if numero(s, m) == num), None)
