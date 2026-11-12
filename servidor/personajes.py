r"""servidor/personajes.py -- VARIOS PERSONAJES por cuenta: crear (0x1013) y elegir (0x1017).

Cómo se guardan: `servidor/cuentas.py` (la cuenta tiene `pjs` = la lista y `activo` = el elegido; `leer`
devuelve el activo mezclado con la cuenta). Lo medido, en documentacion/MEDICIONES.md §50.

    0x1013 C→S (PROTOCOLO §5.5): u32 LUGAR (0–4, el casillero de la pantalla) · u16 CLASE (1 Warrior,
           2 Hunter) · nombre UTF-16
    0x1014 S→C: u16 resultado (1 = OK) + el personaje (186 B, con su lugar en +0x52)
"""
import json
import os
import re
import struct

from servidor import config
from servidor.cuentas import (CUENTA_CLAVES, EXPS, INICIO, MAX_PERSONAJES, con_nivel_inicial, escribir,
                              guardar, leer, personajes_de)
from servidor.registro import maneja

# El casillero de EQUIPO de cada familia de ítem (medido con el 0x102D, MEDICIONES §27)
CASILLERO_PARTE = {0: 10, 1: 11, 3: 0, 4: 4, 5: 6, 6: 8, 7: 1, 8: 9}
NOMBRE_OK = re.compile(r"[A-Za-z0-9_]{2,12}")
ERROR_CREAR = 0x8FD                                  # (§5.5: «0x8FD..» son los errores del cliente)


def personaje_nuevo(clase, nivel, nick=None, lugar=0):
    """Un personaje listo para jugar: el set de grado 1 de su clase PUESTO (Warrior 1, 1001, 3001…;
    Hunter 201, 1201…), 20 pociones, y todas las habilidades de su clase que su nivel permite, con
    las de ESPADA en los atajos F1–F8 (lo de `preparar`). Sin el Skill.xml, sin habilidades."""
    base = 0 if clase == 1 else 200
    # (los seriales de cada lugar en su propio rango: dos personajes nunca comparten uno)
    primero = (lugar + 1) * 10000
    items = []
    for familia, cas in CASILLERO_PARTE.items():
        tipo = familia * 1000 + base + 1 if familia else base + 1
        items.append([tipo, 1, cas, primero + len(items) + 1, 1])
    items.append([26001, 20, 18, primero + len(items) + 1, 1])
    habs, atajo, filas = [], 1, []
    try:
        x = open(config.HABILIDADES_XML, "rb").read()
    except OSError:
        x = b""
    for clase_xml, a in re.findall(rb"<(ACTIVE|PASSIVE)_SKILL ([^>]*)>", x):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', a))
        if int(v[b"CLASS"]) in (clase, 65535) and int(v[b"ACQUIRE_LEVEL"]) <= nivel:
            filas.append((clase_xml == b"ACTIVE", int(v.get(b"WEAPON", b"9")), int(v[b"ACQUIRE_LEVEL"]),
                          int(v[b"ID"])))
    for activa, arma, _, ident in sorted(filas, key=lambda f: (not f[0], f[1], f[2])):
        a = atajo if activa and arma == 0 and atajo <= 8 else 0
        atajo += 1 if a else 0
        habs.append([1000 + len(habs), 1 if activa else 2, ident, len(habs), a])
    pj = {k: v for k, v in INICIO.items() if k not in CUENTA_CLAVES}
    pj.update(clase=clase, exp=EXPS[min(nivel, len(EXPS)) - 1], items=items, habilidades=habs,
              lugares_habilidad=max(12, len(habs)), lugar=lugar, partidas=0, abandonos=0, terminadas=[])
    if nick:
        pj["nick"] = nick
    return pj


def seriales_unicos(pjs):
    """★ Dos personajes de la misma cuenta NUNCA comparten un serial de ítem (el cliente arma el equipo
    de cada uno buscando sus seriales en el inventario: con seriales repetidos se vestía con los ítems
    del otro y se deformaba, MEDICIONES §50). Al que choca se le renumeran sus ítems (y sus fichas)
    a su propio rango: (lugar + 1) × 10000 + n. Cambia `pjs` en el lugar; se guarda con la cuenta."""
    from servidor.objetos import inventario
    vistos = set()
    for i, pj in enumerate(pjs):
        inv = inventario(pj)
        mios = {it[3] for it in inv}
        if mios & vistos:
            base = (pj.get("lugar", i) + 1) * 10000
            nuevo = {s: base + k + 1 for k, s in enumerate(sorted(mios))}
            pj["items"] = [[t, q, cas, nuevo[s], v] for t, q, cas, s, v in inv]
            pj["fichas"] = {str(nuevo[int(k)]): f for k, f in (pj.get("fichas") or {}).items()
                            if k.isdigit() and int(k) in nuevo}
            mios = set(nuevo.values())
        vistos |= mios
    return pjs


def nombre_tomado(nick):
    """¿Algún personaje (de cualquier cuenta) ya se llama así? (sin distinguir mayúsculas)"""
    try:
        archivos = [f for f in os.listdir(config.CUENTAS) if f.endswith(".json")]
    except OSError:
        return False
    for f in archivos:
        try:
            crudo = json.load(open(os.path.join(config.CUENTAS, f), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pjs, _ = personajes_de(crudo)
        if any((p.get("nick") or "").lower() == nick.lower() for p in pjs):
            return True
    return False


def vista(c, pj):
    """Un personaje de la lista, con la forma de una cuenta (lo que leen pj_cuenta / equipo / stats)."""
    v = dict(INICIO)
    v.update({k: c[k] for k in ("nombre", "plata", "cash", "monedas") if k in c})
    v.update(con_nivel_inicial(dict(pj)))
    return v


@maneja(0x1013)
def crear(cmd, cuerpo, conexion, c, p):
    """CREATE CHARACTER [§5.5]: guarda el personaje en el lugar elegido, con el nombre que escribió."""
    from servidor.objetos import pj_cuenta
    if len(cuerpo) < 8:
        return None
    # ⚠ MEDIDO (12-nov, dos 0x1013 de verdad): u32 = el ID de la cuenta (el de +6 del 0x1012) · u8 CLASE ·
    #   u8 LUGAR · nombre UTF-16 hasta el 0. «… 02 02 Arquer» (Hunter, 3er lugar) no decidía el orden;
    #   «… 02 01 ruimleon» (Hunter en el 2º lugar) sí. (PROTOCOLO decía «u32 lugar · u16 clase»: con
    #   eso se leía el lugar 442; y al revés, el lugar 2 ocupado → «Character type does not exist»,
    #   que es el texto del cliente para 0x8FD)
    clase, lugar = cuerpo[4], cuerpo[5]
    nick = cuerpo[6:6 + 2 * 16].decode("utf-16-le", "replace").split("\0")[0].strip()
    pjs = c["pjs"]
    ocupados = {x.get("lugar", i) for i, x in enumerate(pjs)}
    if (not 0 <= lugar < MAX_PERSONAJES or lugar in ocupados or clase not in (1, 2)
            or not NOMBRE_OK.fullmatch(nick) or nombre_tomado(nick)):
        return [(0x1014, struct.pack("<H", ERROR_CREAR) + bytes(186), 0)]
    nuevo = personaje_nuevo(clase, max(1, config.NIVEL_INICIAL or 1), nick, lugar)
    if not pjs:                                      # cuenta vacía (los borró todos): éste es el único
        crudo = {k: c[k] for k in ("nombre", "plata", "cash", "monedas") if k in c}
        crudo.update(pjs=[nuevo], activo=0)
        escribir(c["nombre"], crudo)
        c["pjs"] = [nuevo]
    else:
        c["pjs"] = pjs + [nuevo]
        guardar(c)                                   # (el activo no cambia: se elige al entrar al lobby)
    return [(0x1014, struct.pack("<H", 1) + pj_cuenta(vista(c, nuevo)), 0)]


@maneja(0x1015)
def borrar(cmd, cuerpo, conexion, c, p):
    """DELETE CHARACTER (MEDIDO, 12-nov: «05 00 15 10 c0 01 00 00 00» borrando a rui): 0x1015 = u32 id de
    la cuenta · u8 LUGAR. El cliente espera 0x1016 (`0x544620`, lee 3 B): u16 resultado (1 = OK) · u8
    LUGAR → lo saca de su lista (`0x61F810` sobre cuenta+0x2B0), redibuja y muestra el mensaje 0x67.
    Se pueden borrar TODOS (El tester, 12-nov): la cuenta queda vacía y el jugador crea uno nuevo."""
    if len(cuerpo) < 5:
        return None
    lugar = cuerpo[4]
    pjs = c["pjs"]
    i = next((k for k, x in enumerate(pjs) if x.get("lugar", k) == lugar), None)
    if i is None:
        return [(0x1016, struct.pack("<HB", 0, lugar), 0)]
    guardar(c)                                       # (lo del activo, al día en la lista)
    pjs = [dict(x) for x in c["pjs"]]
    del pjs[i]
    activo = c["activo"]
    activo = 0 if i == activo else (activo - 1 if i < activo else activo)
    crudo = {k: c[k] for k in ("nombre", "plata", "cash", "monedas") if k in c}
    crudo.update(pjs=pjs, activo=activo)
    escribir(c["nombre"], crudo)
    return [(0x1016, struct.pack("<HB", 1, lugar), 0)]


def elegir(conexion, c, lugar):
    """Cambia el personaje ACTIVO al del lugar elegido. Devuelve la cuenta releída (o la misma)."""
    for i, x in enumerate(c["pjs"]):
        if x.get("lugar", i) == lugar and i != c["activo"]:
            guardar(c)                               # lo del que estaba, guardado (y `c["pjs"]` al día)
            crudo = {k: c[k] for k in ("nombre", "plata", "cash", "monedas") if k in c}
            crudo.update(pjs=c["pjs"], activo=i)
            escribir(c["nombre"], crudo)             # la misma lista, con el nuevo activo …
            return leer(conexion)                    # … y releída: queda «mezclado» el elegido
    return c
