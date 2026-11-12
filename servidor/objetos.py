r"""servidor/objetos.py -- los BYTES de lo que tiene un jugador: el inventario, la ficha de cada
ítem, el equipo puesto, las estadísticas, las habilidades y el personaje entero (0x1012).

Cada registro se arma ENCIMA del objeto que construye el cliente: las vtables van con el
valor que pone su constructor (las direcciones 0x89A3xx).
"""
import struct

from servidor.config import P
from servidor.cuentas import nivel


def personaje_obj(c):
    """El objeto PERSONAJE (0x52 B, `0x53F680`) con sus vtables: va dentro del miembro de la sala
    y del usuario de la lista del lobby."""
    pj = bytearray(P.registro_personaje(c.get("nick", c["nombre"]), lugar=0, clase=c["clase"], ident=c["exp"],
                                        nivel=nivel(c["exp"]), partidas=c["partidas"],
                                        abandonos=c["abandonos"])[0:0x52])
    struct.pack_into("<I", pj, 0, 0x89A3AC)
    struct.pack_into("<I", pj, 0x24, 0x89A378)
    return bytes(pj)


def casilleros_de(items):
    """El casillero de cada ítem ([tipo, cantidad, casillero]); sin casillero, el primero libre
    de la bolsa (18…)."""
    usados = {it[2] for it in items if len(it) > 2}
    libres = (x for x in range(18, 168) if x not in usados)
    return [it[2] if len(it) > 2 else next(libres) for it in items]


def inventario(c):
    """★ Los ítems de la cuenta con todo fijo: [tipo, cantidad, casillero, SERIAL]. El serial es
    la clave con la que el cliente nombra cada ítem (equipar, vender): tiene que ser FIJO —
    antes era «posición + 1» y al vender uno se habrían corrido todos. Las cuentas viejas (sin
    serial) toman posición + 1, que es lo que ya conocía su cliente."""
    items = c.get("items", [])
    cas = casilleros_de(items)
    return [[it[0], it[1], cas[i], it[3] if len(it) > 3 else i + 1, it[4] if len(it) > 4 else 1]
            for i, it in enumerate(items)]


def serial_nuevo(inv):
    return max([it[3] for it in inv] + [0]) + 1


def libre_en_bolsa(inv):
    usados = {it[2] for it in inv}
    return next(k for k in range(18, 168) if k not in usados)


# ★ EL EQUIPO DEL PERSONAJE (+0x6E: vt 0x89A388 + 18 u32 = el SERIAL de cada pieza puesta, 0 =
#   nada). Medido con Frida el 10-nov (`pj.py`, 18:45): con las 8 piezas de Warrior puestas,
#   +0x72.. = 1 2 3 4 5 6 7 8 → el ÍNDICE es la PARTE, no el casillero (la máscara, serial 3, está
#   en el casillero 0 y en el índice 2). 🟡 La parte sale de la familia del tipo (tipo // 1000:
#   0 arma, 1 segunda arma, 3 máscara, 4 torso, 5 piernas, 6 guantes, 7 cinturón, 8 botas; no hay
#   familia 2 en ITEMTYPELIST) en ese orden. Los índices 8–17 no se vieron usados.
PARTE = {0: 0, 1: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7}


def equipo(c):
    """Los 18 u32 del equipo: el serial de cada ítem en un casillero de equipo."""
    e = [0] * 18
    for tipo, _, cas, serial, _ in inventario(c):
        parte = PARTE.get(tipo // 1000)
        if cas < 12 and parte is not None:
            e[parte] = serial
        elif 12 <= cas < 18:
            # ★ la BARRA de la partida (los 6 de la derecha del HUD, teclas 1–6 = GameItem1–6):
            #   el HUD lee personaje +0xA2 + 4·i = índices 12–17 (`0x510619`) = casilleros 12–17
            e[cas] = serial
    return e


def obj_habilidad(h):
    """Una habilidad aprendida (13 B, `0x53F530`, → cuenta+0x728): vt 0x89A3A4 · u32 CLAVE · u8
    1 activa / 2 pasiva (`0x523D89`) · u16 ID de Skill.xml · u8 +0xB = la casilla en la grilla de
    APRENDIDAS (SLOT 1–3, 0…; nace 0xFF) · u8 +0xC = el ATAJO de la partida (1…8 = F1…F8, la grilla
    de arriba; 0 = ninguno). Medido 19:30: con +0xC = 1 el Dash aparece en la grilla de arriba y en
    la barra del HUD, y F1 lo marca. (Lo cambian las listas de 0x102D/0x103D, `0x61ECB0`.)"""
    clave, tipo, ident, b, cc = h
    return struct.pack("<IIBHBB", 0x89A3A4, clave, tipo, ident, b, cc)


def es_equipo(tipo):
    return 1 <= tipo <= 19999                               # `0x5177C0`


def nivel_engarce(niveles, i):
    """Los 3 bits del engarce i en +0x20 de la ficha (`0x521332`): 0 = cerrado (no se dibuja)."""
    return (niveles >> (29 - 3 * i)) & 7


def ficha(c, serial):
    """★ La FICHA de un ítem (36 B, `0x540400` / `0x61FDB0`): vt 0x89A384 · u32 serial · vt
    0x89A380 · **10 × u16 = la piedra espiritual de cada ENGARCE** (tipo de ítem 21xxx–25xxx;
    0 = no hay engarce) · u32 = el NIVEL de cada engarce, 3 bits cada uno (`(x >> (29 − 3i)) & 7`,
    `0x61FE33`). Lo que tiene cada ítem lo guarda la cuenta en c["fichas"][serial]."""
    f = c.get("fichas", {}).get(str(serial), {})
    engarces = (list(f.get("engarces", [])) + [0] * 10)[:10]
    return struct.pack("<III10HI", 0x89A384, serial, 0x89A380, *engarces, f.get("niveles", 0))


def registro_item(serial, tipo, cant, casillero, verificado=1, pegada=False, c=None):
    """Un ítem como lo lee `0x617630` (21 B) y, si es equipo, su ficha (36 B, `ficha`).
    vt 0x89A39C (el objeto, `0x53F4B0`) · u32 serial · u16 tipo · u8 🟡 (iba la cantidad) · u8
    CASILLERO · u16 +0xC 🟡 (nace con 0xFFFF) · u8 +0xE VERIFICADO (nace con 1; un ítem de
    habilidad 31000–33999 con 0 es un «Unknown Skill Book») · i16 +0xF ★ DURABILIDAD (la ficha
    muestra +0xF / MAXSOLID × 100, `0x5201F9`: con 0 decía «Durability 0%») · u32 +0x11 ★ la
    CANTIDAD (la barra de pociones lee [ítem+0x11], `0x510734`); en el PlayEnd, −1 = equipo con
    su ficha PEGADA detrás (`0x548C77`)."""
    r = struct.pack("<IIHBBHBhI", 0x89A39C, serial, tipo, cant, casillero, 0, verificado,
                    # 🟡 MAXSOLID (10000 en casi todo el equipo) o lo que guarde la cuenta
                    (c or {}).get("durabilidad", {}).get(str(serial), 10000) if es_equipo(tipo) else 0,
                    0xFFFFFFFF if pegada and es_equipo(tipo) else cant)
    return r, (ficha(c or {}, serial) if es_equipo(tipo) else b"")


def equipo_tipos(c):
    """Como `equipo`, pero con el TIPO de ítem de cada parte en vez del serial."""
    por_serial = {it[3]: it[0] for it in inventario(c)}
    return [por_serial.get(s, 0) for s in equipo(c)]


def obj_equipo(c):
    return struct.pack("<I18I", 0x89A388, *equipo(c))


PUNTOS_POR_NIVEL = 3          # 🟡 los de 2009 no se saben


def stats_de(c):
    """Las 6 u16 del personaje (+0x62): Strength Constitution Dexterity Intelligence Wisdom y
    ★ +0x6C = los PUNTOS SIN REPARTIR («Bonus Stat», `0x51E9F4`). Los repartidos los guarda la
    cuenta; los libres = PUNTOS_POR_NIVEL × (nivel − 1) − los repartidos."""
    repartidos = list((c.get("stats") or [0] * 5)[:5])
    libres = max(0, PUNTOS_POR_NIVEL * (nivel(c["exp"]) - 1) - sum(repartidos))
    return repartidos + [libres]


def obj_stats(c):
    """+0x5E: vt 0x89A368 + las 6 u16 de `stats_de`."""
    return struct.pack("<I6H", 0x89A368, *stats_de(c))


def pj_cuenta(c):
    """El personaje (0xBA B) de la cuenta, con sus estadísticas y su EQUIPO puesto."""
    return P.registro_personaje(c.get("nick", c["nombre"]), lugar=0, clase=c["clase"], ident=c["exp"],
                                nivel=nivel(c["exp"]), partidas=c["partidas"],
                                abandonos=c["abandonos"], stats=tuple(stats_de(c)),
                                extra={0x72: struct.pack("<18I", *equipo(c)),
                                       # ★ +0x6C = Bonus Stat (registro_personaje escribe sólo 5)
                                       0x6C: struct.pack("<H", stats_de(c)[5]),
                                       # ★ +0x5B = LUGARES DE HABILIDAD: `0x523E41` lo compara con
                                       #   cuántas tiene (cuenta+0x728); con 0 → «You do not have
                                       #   enough skill slot» (19:11). 🟡 12 = una página SLOT de
                                       #   3×4 (el valor de 2009 no se sabe)
                                       0x5B: bytes([c.get("lugares_habilidad", 12)]),
                                       0x5C: b"\x06",
                                       0x5D: b"\x08",
                                       # 🟡 PARA MEDIR: {"0x5c": "4d"} pisa esos bytes del personaje
                                       **{int(k, 16): bytes.fromhex(v)
                                          for k, v in c.get("extra_pj", {}).items()}})


def cuerpo_cuenta(c, conexion=0):
    """0x1012 [§5.4]: la cuenta (cash, plata, monedas, lugares) + el personaje."""
    b = bytearray(struct.pack("<H", 1) + bytes(26) + struct.pack("<HHB", 0, 0, 0))
    # ★ +6 u32 → cuenta+0x2B8 = el ID con que el cliente se registra en el punch (`0x3006`). Pisa
    #   el del 0x1010: en 0 los dos clientes se anotaban como «jugador 0» (relay, 20:03)
    struct.pack_into("<I", b, 6, conexion or 0)
    struct.pack_into("<I", b, 0x0F, c["cash"])
    struct.pack_into("<I", b, 0x13, c["plata"])
    struct.pack_into("<H", b, 0x17, c["monedas"])          # monedas de revivir (+0x2C9)
    b[0x19] = 5                                             # lugares habilitados
    # ★ +0x1A → cuenta+0x2CC = LUGARES LIBRES en la bolsa (+6 = +0x2B8, medido; nadie más lo
    #   escribe). Con 0, «Purchase All» decía «No Empty Slot Available» (`0x54DCEA`, 21:41)
    b[0x1A] = max(0, 150 - sum(1 for it in inventario(c) if it[2] >= 18))
    b[0x20] = 1                                             # un personaje
    # ★ N1 (+0x1C) × 21 B = el INVENTARIO (`0x617630` → cuenta+0x708; el mismo del PlayEnd): +4 u32
    #   🟡 serie · +8 u16 TIPO DE ÍTEM (ITEMTYPELIST) · +0xA u8 🟡 · +0xB u8 🟡 · +0xC u16 🟡 ·
    #   +0xE u8 🟡 · +0xF u16 🟡 · +0x11 u32 (−1 → vienen 36 B más, `0x6176E0`). Se copia campo
    #   por campo (la vtable de +0 no se pisa).
    #   (+0xA = la CANTIDAD, `0x615D90`)
    # ★ +0xB = EL CASILLERO (medido 18:30–18:40, foto por foto): 0–11 = EQUIPO (control − 10000,
    #   `0x51C6A5`), 12–17 = la fila de 6 de arriba (🟡 la barra de ítems de la partida, teclas
    #   1–6), 18… = la BOLSA (5 páginas de 30). Cada ítem de la cuenta: `inventario()`.
    inv = inventario(c)
    struct.pack_into("<H", b, 0x1C, len(inv))
    regs = b"".join(registro_item(serial, tipo, cant, cas, ver, c=c)[0]
                    for tipo, cant, cas, serial, ver in inv)
    # ★ N2 (+0x1E) × 36 B = la FICHA de cada ítem (`0x6176E0`): vt (no se copia) · u32 clave (🟡 la
    #   serie del ítem) · 28 B 🟡 (opciones / refinado). Sin ella, al pasar el mouse por un ítem
    #   EQUIPADO la ficha (`0x520336` → `0x61FDB0`) lee un puntero nulo y el juego se cae (18:24)
    struct.pack_into("<H", b, 0x1E, len(inv))
    fichas = b"".join(ficha(c, it[3]) for it in inv)
    return bytes(b) + regs + fichas + pj_cuenta(c)
