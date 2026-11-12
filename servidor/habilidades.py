r"""servidor/habilidades.py -- las HABILIDADES: verificar el libro, aprender y borrar.
"""
import struct

from servidor.registro import maneja
from servidor.cuentas import guardar, nivel
from servidor.datos import tabla_habilidades
from servidor.objetos import inventario, obj_habilidad, registro_item


@maneja(0x103B)
def verificar_libro(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 12):
        return None
    # ★ VERIFICAR UN LIBRO (medido 19:09): pantalla Skill → clic derecho en el «Skill Check
    #   Scroll» (40051) → clic en el libro = un ítem de habilidad (31000–33999, `0x51BB40`) con
    #   +0xE = 0. 0x103B (`0x54A850`): u32 · u32 serial del LIBRO · u32 serial del PERGAMINO.
    #   0x103C (`0x54B1E0`, 31 B): u16 1 · u32 serial del pergamino · i32 pergaminos que
    #   quedan (≤ 0 → se borra) · el ítem nuevo (21 B: reemplaza al de su serial) → «Selected
    #   Skill has been verified. [Dash, 1Lv]» (`0x527070`).
    libro_s, perg_s = struct.unpack_from("<II", cuerpo, 4)
    inv = inventario(c)
    libro = next((x for x in inv if x[3] == libro_s), None)
    perg = next((x for x in inv if x[3] == perg_s), None)
    if (libro is None or perg is None or not 31000 <= libro[0] <= 33999 or libro[4]
            or perg[0] != 40051 or perg[1] < 1):
        return [(0x103C, struct.pack("<HII", 0, perg_s, 0), 0)]
    libro[4] = 1
    perg[1] -= 1
    if perg[1] <= 0:
        inv.remove(perg)
    c["items"] = inv
    guardar(c)
    return [(0x103C, struct.pack("<HIi", 1, perg_s, perg[1])
             + registro_item(libro[3], libro[0], libro[1], libro[2], 1)[0], 0)]


@maneja(0x103D)
def aprender(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 8):
        return None
    # ★ APRENDER (medido 19:12: clic derecho en el libro VERIFICADO → «450 Gold will be used.
    #   Do you want to learn the skill?» → Confirm): 0x103D (`0x54C9B0`) = u32 · u32 serial
    #   del libro · u16 N2 · u16 N3 · listas (u32 · u8) de la grilla (🟡).
    #   0x103E (`0x54CB70`): u16 1 · u8 MODO (0 = agregar; 1 = antes borrar la de clave
    #   [+0xB], 🟡 subir de nivel) · u32 ORO (+3 → cuenta+0x2C5) · u32 serial del libro (+7,
    #   sale de la bolsa) · u32 clave a borrar (+0xB, modo 1) · la habilidad (13 B, +0xF)
    #   ⚠ el oro va en +3: contado al revés (un push esi en 0x54CBFE) el cliente mostró «0 Gold» · u16 N × (u32 clave · u8 · u8) → «Selected Skill has
    #   been Learned» (`0x527380`).
    serial = struct.unpack_from("<I", cuerpo, 4)[0]
    inv = inventario(c)
    libro = next((x for x in inv if x[3] == serial), None)
    dato = tabla_habilidades().get(libro[0]) if libro else None
    habs = c.get("habilidades", [])
    no = (libro is None or dato is None or not libro[4] or dato[2] not in (c["clase"], 65535)
          or nivel(c["exp"]) < dato[4] or c["plata"] < dato[3]
          or any(h[2] == dato[1] and h[1] == dato[0] for h in habs)
          or len(habs) >= c.get("lugares_habilidad", 12))
    if no:
        return [(0x103E, struct.pack("<HBIII", 0, 0, c["plata"], serial, 0) + bytes(13)
                 + struct.pack("<H", 0), 0)]
    usadas = {h[3] for h in habs}
    # 🟡 al primer ATAJO libre (1–8): comodidad nuestra mientras arrastrar a la grilla de
    #   arriba no anda (con 0 la habilidad no queda en la barra de la partida)
    atajos = {x[4] for x in habs}
    h = [serial, dato[0], dato[1], next(k for k in range(36) if k not in usadas),
         next((k for k in range(1, 9) if k not in atajos), 0)]
    habs.append(h)
    inv.remove(libro)
    c["items"], c["habilidades"] = inv, habs
    c["plata"] -= dato[3]
    guardar(c)
    return [(0x103E, struct.pack("<HBIII", 1, 0, c["plata"], serial, 0) + obj_habilidad(h)
             + struct.pack("<H", 0), 0)]


@maneja(0x1043)
def borrar_habilidad(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 8):
        return None
    # ★ BORRAR HABILIDAD (medido 21:15: «[Dash] 1 Lv. Do you want to delete the skill?» →
    #   Confirm): 0x1043 = u32 · u32 CLAVE. 0x1044 (`0x54AD80`, 6 B): u16 1 · u32 clave → la
    #   saca de cuenta+0x728 (`0x61F1E0`). 🟡 no devuelve oro ni el libro.
    clave = struct.unpack_from("<I", cuerpo, 4)[0]
    habs = c.get("habilidades", [])
    if not any(h[0] == clave for h in habs):
        return [(0x1044, struct.pack("<HI", 0, clave), 0)]
    c["habilidades"] = [h for h in habs if h[0] != clave]
    guardar(c)
    return [(0x1044, struct.pack("<HI", 1, clave), 0)]
