r"""servidor/cuentas.py -- la CUENTA de cada jugador: leerla, guardarla, la EXP y el nivel.

Una cuenta por conexión de juego (sin launcher ni login todavía: cada conexión toma el primer
nombre libre de NOMBRES). Cada una en `<EDA_ESTADO>/cuentas/<nombre>.json`.
"""
import json
import os

from servidor import config
from servidor.estado import ASIGNADAS


INICIO = {"nombre": "rui", "clase": 1, "monedas": 3, "plata": 5678, "cash": 1234, "exp": 0,
          "partidas": 0, "abandonos": 0, "terminadas": [],
          # ★ El set de grado 1 de Warrior (`ITEMTYPELIST`, USECLASS=1): ningún equipo de Warrior
          #   pide menos de nivel 2 (LEVEL_RESTRICT=2) → con nivel 1 dice «Can't equip» con razón.
          #   + el 201 (USECLASS=2, Hunter) como control al revés: NO se tiene que poder equipar
          #   nunca. + consumibles de USECLASS=65535 (todas las clases).
          "items": [[1, 1], [1001, 1], [3001, 1], [4001, 1], [5001, 1], [6001, 1], [7001, 1],
                    [8001, 1], [201, 1], [21001, 5], [26001, 5]]}


# ★ La EXP acumulada para pasar de nivel: `<EXPS>` de `Data\Player.xml` (dentro de Data.dat,
#   volcado con `volcar_inflados.py`). EXPS[n] = la EXP con la que se llega al nivel n+1; cierra
#   con el lobby: «1LV (11/300)». (99 niveles; acá los primeros 30 alcanzan de sobra.)
EXPS = [0, 300, 1060, 2160, 3600, 5500, 8100, 11760, 16960, 24300, 34500, 48400, 66960, 91260,
        122500, 162000, 211200, 271660, 345060, 433200, 538000, 661500, 805860, 973360, 1166400,
        1387500, 1639300, 1924560, 2246160, 2607100]


def nivel(exp):
    n = 1
    while n < len(EXPS) and exp >= EXPS[n]:
        n += 1
    return n


# ★ MULTIJUGADOR: una cuenta por conexión de juego. Sin launcher ni login (los dos clientes mandan
#   lo mismo en el 0x100F), cada conexión toma el primer nombre libre de la lista. Cada cuenta en
#   `_trabajo/servidor/cuentas/<nombre>.json` (la vieja `cuenta.json` pasa a ser la de «rui»).
NOMBRES = ["rui", "kai", "mio", "ren"]
SIN_LOGIN = "_sin_login"         # (config.LOGIN == "pase") una conexión que todavía no mostró su ticket


def ruta_cuenta(nombre):
    return os.path.join(config.CUENTAS, nombre + ".json")


def cuenta_de(conexion):
    """El nombre de la cuenta de esa conexión (le asigna el primero libre si no tiene)."""
    if conexion is None:
        return NOMBRES[0]
    if config.LOGIN == "pase" and conexion not in ASIGNADAS:
        return SIN_LOGIN                       # ★ con login nadie cae en rui/kai: la pone entrada.py
    if conexion not in ASIGNADAS:
        usados = set(ASIGNADAS.values())
        ASIGNADAS[conexion] = next((x for x in NOMBRES if x not in usados), NOMBRES[-1])
    return ASIGNADAS[conexion]


def leer(conexion=None):
    nombre = cuenta_de(conexion)
    if nombre == "rui" and not os.path.exists(ruta_cuenta("rui")) and os.path.exists(config.CUENTA):
        os.makedirs(config.CUENTAS, exist_ok=True)
        os.replace(config.CUENTA, ruta_cuenta("rui"))              # la cuenta de antes de las cuentas
    try:
        c = json.load(open(ruta_cuenta(nombre), encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    return dict(INICIO, **dict(c, nombre=nombre))


def guardar(c):
    os.makedirs(config.CUENTAS, exist_ok=True)
    json.dump(c, open(ruta_cuenta(c["nombre"]), "w", encoding="utf-8"), indent=1)
