r"""servidor/refineria.py -- la REFINERY: abrir engarces, poner piedras, refinar piedras
y reparar.
"""
import struct

from servidor.registro import maneja
from servidor.cuentas import guardar
from servidor.datos import tipos_item
from servidor.objetos import es_equipo, ficha, inventario, libre_en_bolsa, nivel_engarce, registro_item, serial_nuevo


@maneja(0x1039)
def reparar(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 6):
        return None
    # ★ REPAIR (medido 21:37: «Repair All» → «22500 Gold will be used» → Confirm): 0x1039 =
    #   u32 · u16 1 = TODO (0 = «Repair Each»: le siguen los seriales, 🟡). El precio lo calcula
    #   el cliente igual: Σ (MAXSOLID − durabilidad) × REPAIRGOLD de ItemTypeList.xml (2500 × 1
    #   + 5000 × 4 = 22500, medido).
    #   0x103A (`0x54A7A0`): u16 1 · u32 ORO (→ +0x2C5) · u8 N · N × (u32 serial · u16 la
    #   durabilidad nueva, `0x615D40`) → «Item has been repaired».
    todo = struct.unpack_from("<H", cuerpo, 4)[0] == 1
    pedidos = {struct.unpack_from("<I", cuerpo, o)[0] for o in range(6, len(cuerpo) - 3, 4)}
    tabla = tipos_item()
    durab = c.setdefault("durabilidad", {})
    arreglar, costo = [], 0
    for tipo, _, _, serial, _ in inventario(c):
        if not es_equipo(tipo) or (not todo and serial not in pedidos):
            continue
        maximo, oro = tabla.get(tipo, (10000, 1))
        d = durab.get(str(serial), maximo)
        if d < maximo:
            arreglar.append((serial, maximo))
            costo += (maximo - d) * oro
    if not arreglar or costo > c["plata"]:
        return [(0x103A, struct.pack("<HIB", 0, c["plata"], 0), 0)]
    c["plata"] -= costo
    for serial, maximo in arreglar:
        durab[str(serial)] = maximo
    guardar(c)
    return [(0x103A, struct.pack("<HIB", 1, c["plata"], len(arreglar))
             + b"".join(struct.pack("<IH", s_, m) for s_, m in arreglar), 0)]


@maneja(0x1035)
def refinar_piedra(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 13):
        return None
    # ★ REFINE SPIRIT STONE (medido 21:33: tres 21001 en «Phase» → Refine): 0x1035 = u32 · u8
    #   MODO (0 = Phase, 3 piedras; 1 = Level, 2 piedras) · N × u32 serial de cada piedra.
    #   0x1036 (`0x54AF20`, 25 B + lista): u16 resultado (1 = bien; 0x1B5D = «Refining has
    #   failed», las piedras se pierden) · u8 modo · la piedra NUEVA (21 B) · u8 N · N × u32
    #   las gastadas. 🟡 La regla no está en ningún archivo; de los datos: cada familia tiene 2
    #   FASES (21001–21006 / 21021–21026) × 6 NIVELES (el último dígito) → Phase: 3 iguales de
    #   fase 1 → fase 2 (21001 → 21021); Level: 2 iguales → nivel + 1 (21001 → 21002).
    #   Siempre sale bien.
    modo = cuerpo[4]
    cuantas = 3 if modo == 0 else 2
    seriales = [struct.unpack_from("<I", cuerpo, 5 + 4 * k)[0] for k in range(cuantas)
                if 5 + 4 * k + 4 <= len(cuerpo)]
    inv = inventario(c)
    piedras = [next((x for x in inv if x[3] == s_), None) for s_ in seriales]
    tipos = {p[0] for p in piedras if p}
    nuevo = None
    if len(seriales) == cuantas and all(piedras) and len(tipos) == 1 and len(set(seriales)) == cuantas:
        t = tipos.pop()
        fam, resto = t // 1000, t % 1000             # 21 · 001
        if 21 <= fam <= 25:
            if modo == 0 and 1 <= resto <= 6:
                nuevo = fam * 1000 + 20 + resto        # fase 1 → fase 2
            elif modo == 1 and resto % 20 in range(1, 6):
                nuevo = t + 1                          # nivel + 1
    if nuevo is None:
        return [(0x1036, struct.pack("<HB", 0, modo) + bytes(21) + b"\0", 0)]
    for p in piedras:
        inv.remove(p)
    it = [nuevo, 1, libre_en_bolsa(inv), serial_nuevo(inventario(c)), 1]
    inv.append(it)
    c["items"] = inv
    guardar(c)
    return [(0x1036, struct.pack("<HB", 1, modo) + registro_item(it[3], nuevo, 1, it[2])[0]
             + struct.pack("<B", cuantas) + b"".join(struct.pack("<I", s_) for s_ in seriales), 0)]


@maneja(0x1033)
def encantar(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 9):
        return None
    # ★ ENCHANT ITEM = poner piedras espirituales en los engarces (medido 21:29: espada con 1
    #   engarce + la 21001 soltada en el círculo → Refine): 0x1033 = u32 · u32 serial del ÍTEM
    #   · u8 N · N × (u8 engarce · u32 serial de la PIEDRA).
    #   0x1034 (`0x54A180`): u16 1 · u32 serial del ítem · u8 N · los 10 u16 de las piedras (→
    #   ficha+0xC) · N × u32 serial de cada piedra GASTADA (sale de la bolsa: no se apilan,
    #   MAXOVERLAPCNT = 1). 🟡 siempre sale bien.
    it_s, n = struct.unpack_from("<IB", cuerpo, 4)
    inv = inventario(c)
    it = next((x for x in inv if x[3] == it_s), None)
    f = c.setdefault("fichas", {}).setdefault(str(it_s), {"engarces": [0] * 10, "niveles": 0})
    gastadas, bien = [], it is not None
    for k in range(n):
        o = 9 + 5 * k
        if o + 5 > len(cuerpo):
            bien = False
            break
        i, piedra_s = struct.unpack_from("<BI", cuerpo, o)
        piedra = next((x for x in inv if x[3] == piedra_s), None)
        if (piedra is None or not 21000 <= piedra[0] <= 25999 or i >= 10
                or not nivel_engarce(f["niveles"], i) or f["engarces"][i]):
            bien = False
            break
        gastadas.append((i, piedra))
    if not bien or not gastadas:
        return [(0x1034, struct.pack("<HIB", 0, it_s, 0) + bytes(20), 0)]
    for i, piedra in gastadas:
        f["engarces"][i] = piedra[0]
        inv.remove(piedra)
    c["items"] = inv
    guardar(c)
    return [(0x1034, struct.pack("<HIB", 1, it_s, len(gastadas))
             + struct.pack("<10H", *f["engarces"])
             + b"".join(struct.pack("<I", p[3]) for _, p in gastadas), 0)]


@maneja(0x1037)
def crear_engarce(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 12):
        return None
    # ★ CREATE SOCKET (Refinery, medido 21:22: espada + «Add Socket Drill» → Create): 0x1037 =
    #   u32 · u32 serial del ÍTEM · u32 serial del TALADRO (40001).
    #   0x1038 (`0x54B070`, 46 B): u16 resultado (1 = «Congratulation. Succesfully increased
    #   Socket», 0x1F41 = «Increasing Socket has Failed», el taladro igual se gasta) · u32
    #   serial del taladro · i32 los que quedan (≤ 0 → se borra) · la FICHA nueva (36 B).
    #   🟡 Siempre sale bien (la probabilidad de 2009 no se sabe) y hasta 10 engarces.
    it_s, tal_s = struct.unpack_from("<II", cuerpo, 4)
    inv = inventario(c)
    it = next((x for x in inv if x[3] == it_s), None)
    tal = next((x for x in inv if x[3] == tal_s), None)
    fichas = c.setdefault("fichas", {})
    f = fichas.setdefault(str(it_s), {"engarces": [0] * 10, "niveles": 0})
    cerrado = next((i for i in range(10) if not nivel_engarce(f["niveles"], i)), None)
    if (it is None or tal is None or tal[0] != 40001 or tal[1] < 1 or not es_equipo(it[0])
            or cerrado is None):
        return [(0x1038, struct.pack("<HIi", 0, tal_s, tal[1] if tal else 0) + ficha(c, it_s), 0)]
    # ★ abrir = poner ≠ 0 en sus 3 bits de +0x20 (`0x521346`: con 0 el engarce ni se dibuja).
    #   ⛔ NO 0xFFFF en el u16: el cliente lo busca como tipo de ítem y se cae (0x61F922, 21:26)
    f["niveles"] |= 1 << (29 - 3 * cerrado)
    tal[1] -= 1
    if tal[1] <= 0:
        inv.remove(tal)
    c["items"] = inv
    guardar(c)
    return [(0x1038, struct.pack("<HIi", 1, tal_s, tal[1]) + ficha(c, it_s), 0)]
