r"""servidor/cuentas.py -- la CUENTA de cada jugador: leerla, guardarla, la EXP y el nivel.

Una cuenta por conexión de juego (sin launcher ni login todavía: cada conexión toma el primer
nombre libre de NOMBRES). Cada una en `<EDA_ESTADO>/cuentas/<nombre>.json`.
"""
import json
import os
import tempfile

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


# ★★ VARIOS PERSONAJES POR CUENTA (12-nov, MEDICIONES §50): el 0x1012 trae N3 personajes (§5.4) y la
#   pantalla tiene 5 lugares. En el archivo: lo de la CUENTA (estas claves) + `pjs` (la lista de
#   personajes: todo lo demás — clase, EXP, ítems, habilidades, nick, lugar…) + `activo` (el elegido).
#   `leer` devuelve la cuenta con el personaje ACTIVO «mezclado» (así el resto del server sigue igual)
#   y `guardar` lo vuelve a separar. Una cuenta vieja (un solo personaje, todo junto) = lugar 0.
CUENTA_CLAVES = ("nombre", "plata", "cash", "monedas", "pjs", "activo")
MAX_PERSONAJES = 5


def personajes_de(crudo):
    """(lista de personajes, índice del activo) de una cuenta como está en el archivo."""
    if "pjs" in crudo:
        pjs = [dict(x) for x in crudo["pjs"]]
        return pjs, min(max(0, crudo.get("activo", 0)), max(0, len(pjs) - 1))
    if not crudo:
        return [], 0
    pj = {k: v for k, v in crudo.items() if k not in CUENTA_CLAVES}
    pj.setdefault("lugar", 0)
    return [pj], 0


def con_nivel_inicial(pj):
    """★ «al menos por ahora, directo nivel 25» (El tester, 12-nov): config.NIVEL_INICIAL (EDA_NIVEL_INICIAL,
    0 = no) es el piso de cada personaje al leerlo."""
    n = config.NIVEL_INICIAL
    if n and pj.get("exp", 0) < EXPS[min(n, len(EXPS)) - 1]:
        pj["exp"] = EXPS[min(n, len(EXPS)) - 1]
    return pj


def leer(conexion=None):
    nombre = cuenta_de(conexion)
    if nombre == "rui" and not os.path.exists(ruta_cuenta("rui")) and os.path.exists(config.CUENTA):
        os.makedirs(config.CUENTAS, exist_ok=True)
        os.replace(config.CUENTA, ruta_cuenta("rui"))              # la cuenta de antes de las cuentas
    try:
        crudo = json.load(open(ruta_cuenta(nombre), encoding="utf-8"))
    except (OSError, ValueError):
        crudo = {}
    pjs, activo = personajes_de(crudo)
    if not crudo:                                   # cuenta NUEVA: el personaje de siempre, en el lugar 0
        pjs = [{k: v for k, v in INICIO.items() if k not in CUENTA_CLAVES}]
        pjs[0]["lugar"] = 0
    if not pjs:
        # ★ una cuenta que BORRÓ todos sus personajes (se puede, el tester 12-nov): queda vacía; el 0x1012
        #   va sin personajes y el jugador crea uno nuevo
        c = dict(INICIO)
        c.update({k: crudo[k] for k in ("plata", "cash", "monedas") if k in crudo})
        c.update(nombre=nombre, pjs=[], activo=0, items=[], habilidades=[])
        return c
    if len(pjs) > 1:
        from servidor.personajes import seriales_unicos
        seriales_unicos(pjs)                        # (una cuenta vieja con seriales repetidos, arreglada)
    c = dict(INICIO)
    c.update({k: crudo[k] for k in ("plata", "cash", "monedas") if k in crudo})
    c.update(con_nivel_inicial(dict(pjs[activo])))
    c.update(nombre=nombre, pjs=pjs, activo=activo)
    return c


def nombre_visible(c):
    """★ (PR #5, Urek-Mazinoo) el nombre que se VE en el juego (personaje, sala, lobby, chat): el `nick`
    de la cuenta si tiene, si no su nombre (con login, `r2b_<uid>`)."""
    return c.get("nick") or c["nombre"]


def guardar(c):
    """La cuenta con su personaje activo (separado otra vez en la lista `pjs`)."""
    # el personaje activo vuelve a su lugar de la lista; lo de la cuenta, aparte
    if c.get("pjs") == []:                          # (cuenta sin personajes: sólo lo de la cuenta)
        datos = {k: c[k] for k in ("nombre", "plata", "cash", "monedas") if k in c}
        datos.update(pjs=[], activo=0)
        escribir(c["nombre"], datos)
        return
    pjs = [dict(x) for x in (c.get("pjs") or [{}])]
    activo = min(max(0, c.get("activo", 0)), len(pjs) - 1)
    pjs[activo] = {k: v for k, v in c.items() if k not in CUENTA_CLAVES}
    pjs[activo].setdefault("lugar", activo)
    datos = {k: c[k] for k in ("nombre", "plata", "cash", "monedas") if k in c}
    datos.update(pjs=pjs, activo=activo)
    c["pjs"] = pjs                                   # (quien siga usando `c` ve la lista al día)
    escribir(c["nombre"], datos)


def escribir(nombre, datos):
    """★ (PR #5, Urek-Mazinoo) a un archivo temporal y después se REEMPLAZA de una: si el server se corta
    a mitad de escribir, la cuenta vieja queda entera (antes podía quedar un JSON a medias)."""
    os.makedirs(config.CUENTAS, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=config.CUENTAS, suffix=".tmp",
                                         delete=False) as archivo:
            temporal = archivo.name
            json.dump(datos, archivo, indent=1)
        os.replace(temporal, ruta_cuenta(nombre))
        temporal = None
    finally:
        if temporal is not None:
            os.unlink(temporal)
