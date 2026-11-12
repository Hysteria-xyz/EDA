r"""servidor/inventario.py -- el INVENTARIO: lo que el cliente movió (equipar, la barra de
pociones) y el reparto de estadísticas, que manda todo junto al irse de la pantalla.
"""
import struct

from servidor.registro import maneja
from servidor.estado import ASIGNADAS, SALAS
from servidor.cuentas import guardar, leer
from servidor.objetos import inventario, obj_equipo, obj_stats, stats_de
from servidor.salas import miembro


@maneja(0x102B, 0x102D)
def guardar_inventario(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 0x1A):
        return None
    # ★ INVENTARIO (pantalla 6), medido el 10-nov 18:40: el cliente mueve los ítems SOLO (clic
    #   derecho = equipar; no avisa nada) y recién al irse manda lo que cambió:
    #     0x102D (`0x54BE70`, al tocar «Lobby»): u32 (cuenta+0x2B8) · 16 B estadísticas (vt
    #       0x89A368 + 6 u16) · u16 N movidos · u16 N2 · u16 N3 (🟡 sólo con [pantalla+0xDC]
    #       = 7) · N × (u32 serial · u8 casillero) · …
    #     0x102B (cambiar de pestaña, 27 B): lo mismo con un u8 PESTAÑA en +4
    #   y espera, con la misma forma (`0x54BBB0` / `0x54CD70`): u16 1 · u8 MODO · [0x102E: 8 B
    #   = u8 → cuenta+0x21C + el canal (7 B, como el 0x1018)] · 16 B estadísticas · 76 B EQUIPO
    #   (vt + 18 u32 → personaje+0x72) · u16 N × (u32 serial · u8 CANTIDAD (+0xA) · u8
    #   CASILLERO (+0xB), `0x615D90`) · u16 M × (u32 · u8 · u8 → cuenta+0x728, 🟡).
    #   0x102C: MODO → [pantalla+0xDC] (la pestaña). 0x102E: MODO 3 → pantalla 3 = el LOBBY;
    #   9 → la sala (con 0x63 B de sala + miembros: 🟡 no se arma todavía).
    off = 5 if cmd == 0x102B else 4
    stats = list(struct.unpack_from("<6H", cuerpo, off + 4))
    n1 = struct.unpack_from("<H", cuerpo, off + 16)[0]
    inv = inventario(c)                                # se fijan TODOS antes de mover
    por_serial = {it[3]: it for it in inv}
    # ★ (PR #5, Urek-Mazinoo) primero se juntan los destinos (sólo casilleros que existen: < 168) …
    destinos = {}
    for k in range(n1):
        o = off + 22 + 5 * k
        if o + 5 > len(cuerpo):
            break
        serial, casillero = struct.unpack_from("<IB", cuerpo, o)
        if serial in por_serial and casillero < 168:
            destinos[serial] = casillero
    # … al REEMPLAZAR una poción de la barra (casilleros 12–17) por otra de la bolsa, el cliente puede
    #   mandar sólo la que entra: la que estaba vuelve al casillero de bolsa que dejó la nueva …
    for serial, destino in list(destinos.items()):
        it = por_serial[serial]
        if not (it[2] >= 18 and 12 <= destino < 18
                and it[0] in (26001, 26002, 26003, 26101, 26102, 26103)):
            continue
        anterior = next((x for x in inv if x[2] == destino and x[3] not in destinos), None)
        if anterior is not None:
            destinos[anterior[3]] = it[2]
    # … y se mueve sólo si no quedan DOS ítems en el mismo casillero (si no, queda todo como estaba)
    movidos = []
    posiciones = [destinos.get(it[3], it[2]) for it in inv]
    if len(set(posiciones)) == len(posiciones):
        for serial, destino in destinos.items():
            por_serial[serial][2] = destino
            movidos.append(por_serial[serial])
    c["items"] = inv
    # ★ el REPARTO de puntos: el cliente manda las 5 nuevas + en la 6ª los puntos GASTADOS en
    #   esta tanda (medido 21:10: 5 Str + 3 Con → «… 05 00 03 00 … 08 00», mientras la pantalla
    #   decía «Bonus Stat : 64»). Se acepta sólo si ninguna baja, lo que subió = los gastados y no
    #   pasa de los libres; si no, queda lo de antes (y la respuesta le devuelve lo guardado:
    #   medido, el cliente vuelve a «0 · 72»)
    antes = stats_de(c)
    subio = sum(stats[:5]) - sum(antes[:5])
    if (all(n >= v for n, v in zip(stats[:5], antes[:5])) and subio == stats[5]
            and subio <= antes[5]):
        c["stats"] = list(stats[:5])
    guardar(c)
    cola = (obj_stats(c) + obj_equipo(c) + struct.pack("<H", len(movidos))
            + b"".join(struct.pack("<IBB", it[3], it[1], it[2]) for it in movidos)
            + struct.pack("<H", 0))
    if cmd == 0x102B:
        return [(0x102C, struct.pack("<HB", 1, cuerpo[4]) + cola, 0)]
    s = SALAS.get(p.get("sala"))
    if s and conexion in s["miembros"]:
        # ★ vino de la SALA (0x104C): MODO 9 (`0x54D096`) = los 0x63 B del 0x1020 sin su u16
        #   (u8 +0x705 · u8 +0x706 · u8 · vt · u8 · u8 · la sala · u8 N) + N miembros de 0x32C
        #   (🟡 todos, el propio incluido: `0x61C9E0` vacía la lista antes) → pantalla 5
        yo = s["miembros"].index(conexion)
        sala = bytearray(s["sala"])
        sala[0x2D], sala[0x2E] = 1, len(s["miembros"])
        datos = (struct.pack("<BBBIBB", yo, yo, 0, 0x89A3B8, 0, 0) + bytes(sala)
                 + bytes([len(s["miembros"])])
                 + b"".join(miembro(leer(n), s["miembros"].index(n), conexion=n, para=conexion)
                            for n in s["miembros"]))
        r = [(0x102E, struct.pack("<HB", 1, 9) + datos + cola, 0)]
        from servidor.salas import aviso_equipo_105b
        msg_5b = aviso_equipo_105b(c, yo)
        for n in s["miembros"]:
            if n != conexion:
                r.append((0x105B, msg_5b, 0, n))
        return r
    canal = struct.pack("<BHHH", 1, 200, len(ASIGNADAS), 0)
    return [(0x102E, struct.pack("<HBB", 1, 3, 0) + canal + cola, 0)]


@maneja(0x102F)
def asignar_stats_102f(cmd, cuerpo, conexion, c, p):
    """★ 0x102F C→S / 0x1030 S→C (`0x54C690`, 2 B, aporte de Hysteria-xyz):
    Repartir puntos de atributos (STR, CON, DEX, INT, WIS) ganados al subir de nivel.
    cuerpo: u32 conexion · 6 × u16 stats.
    0x1030: u16 resultado (1 = OK, 0 = error)."""
    if len(cuerpo) < 16:
        return [(0x1030, struct.pack("<H", 0), 0)]
    stats = list(struct.unpack_from("<6H", cuerpo, 4))
    antes = stats_de(c)
    subio = sum(stats[:5]) - sum(antes[:5])
    if all(n >= v for n, v in zip(stats[:5], antes[:5])) and subio <= antes[5]:
        c["stats"] = list(stats[:5])
        guardar(c)
        return [(0x1030, struct.pack("<H", 1), 0)]
    return [(0x1030, struct.pack("<H", 0), 0)]


@maneja(0x1030)
def confirmacion_stats_1030(cmd, cuerpo, conexion, c, p):
    """★ 0x1030 (`0x54C690`, 2 B): confirmación de guardado de stats."""
    return [(0x1030, cuerpo if len(cuerpo) >= 2 else struct.pack("<H", 1), 0)]


@maneja(0x1031)
def habilidad_1031(cmd, cuerpo, conexion, c, p):
    """★ 0x1031 C→S / 0x1032 S→C (`0x54B2D0`, 94 B, aporte de Hysteria-xyz):
    Gestión y confirmación de habilidades aprendidas.
    0x1032: u16 resultado (1 = OK) + 92 B estructura de habilidad."""
    buf = bytearray(0x5E)
    struct.pack_into("<H", buf, 0, 1)
    return [(0x1032, bytes(buf), 0)]


@maneja(0x1032)
def confirmacion_habilidad_1032(cmd, cuerpo, conexion, c, p):
    """★ 0x1032 (`0x54B2D0`, 94 B): confirmación de habilidad."""
    return [(0x1032, cuerpo if len(cuerpo) >= 0x5E else bytes(0x5E), 0)]
