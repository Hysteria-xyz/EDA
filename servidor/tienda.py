r"""servidor/tienda.py -- la TIENDA: comprar y vender, con los precios de `Product.xml`.
"""
import struct

from servidor.registro import maneja
from servidor.cuentas import guardar
from servidor.datos import precios_venta, productos
from servidor.objetos import inventario, libre_en_bolsa, registro_item, serial_nuevo


@maneja(0x103F)
def comprar(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 5):
        return None
    # ★ COMPRAR (medido el 10-nov 18:48: «[Basic Long Sword] 1200 Gold» → Confirm):
    #   0x103F (`0x54DA47` uno, `0x54DB2C` «Purchase All»): u32 (cuenta+0x2B8) · u8 N · N × u16
    #   ID DE PRODUCTO (Product.xml; el 1 = 1200 oro → ítem 1).
    #   0x1040 (`0x54D340`): u16 1 · u32 ORO (→ cuenta+0x2C5) · u32 CASH (→ +0x2C1) · u8 nA ·
    #   u16 nB · u16 nC · nA × u16 (productos que salen del carrito) · nB × ítem (21 B + ficha
    #   de 36 B si es equipo) · nC × 🟡 (`0x61FA90` sobre el personaje).
    #   🟡 sin oro (o sin el producto) → resultado 0: el cliente no hace nada.
    tabla = productos()
    n = cuerpo[4]
    pedidos = [struct.unpack_from("<H", cuerpo, 5 + 2 * k)[0] for k in range(n)
               if 5 + 2 * k + 2 <= len(cuerpo)]
    # ★ (PR #5, Urek-Mazinoo) se cobra el ORO y el CASH de cada producto (antes sólo el oro), se pide
    #   que el pedido entero se haya leído, y que entre en la bolsa (150 casilleros: 18–167)
    costo_oro = sum(tabla[x][0] for x in pedidos if x in tabla)
    costo_cash = sum(tabla[x][1] for x in pedidos if x in tabla)
    inv = inventario(c)
    cupos = 150 - len({it[2] for it in inv if 18 <= it[2] < 168})
    cantidad_items = sum(len(tabla[x][2]) for x in pedidos if x in tabla)
    if (not pedidos or len(pedidos) != n or any(x not in tabla for x in pedidos)
            or costo_oro > c["plata"] or costo_cash > c["cash"] or cantidad_items > cupos):
        return [(0x1040, struct.pack("<HIIBHH", 0, c["plata"], c["cash"], 0, 0, 0), 0)]
    nuevos = []
    for x in pedidos:
        for tipo, cant in tabla[x][2]:
            # un libro de habilidad (31000–33999) sale SIN verificar («Unknown Skill Book»): se verifica
            #   con el pergamino antes de aprender (MEDICIONES §28)
            verificado = int(not 31000 <= tipo <= 33999)
            it = [tipo, cant, libre_en_bolsa(inv), serial_nuevo(inv), verificado]
            inv.append(it)
            nuevos.append(registro_item(it[3], tipo, cant, it[2], verificado))
    c["items"] = inv
    c["plata"] -= costo_oro
    c["cash"] -= costo_cash
    guardar(c)
    return [(0x1040, struct.pack("<HIIBHH", 1, c["plata"], c["cash"], len(pedidos),
                                 len(nuevos), 0)
             + b"".join(struct.pack("<H", x) for x in pedidos)
             + b"".join(r + f for r, f in nuevos), 0)]


@maneja(0x1041)
def vender(cmd, cuerpo, conexion, c, p):
    if not (len(cuerpo) >= 8):
        return None
    # ★ VENDER (medido 18:59: «[Basic Long Sword] 480 Gold» → Confirm): 0x1041 = u32
    #   (cuenta+0x2B8) · u32 SERIAL. El precio es el `<BuyItem RefID BuyGold>` de Product.xml
    #   (el 1 → 480, el mismo número que mostró el cliente).
    #   0x1042 (`0x54AA80`): u16 1 · u32 serial (sale de cuenta+0x708, `0x616CC0`) · u32 ORO
    #   (→ +0x2C5) · u8 1 = borrar también su ficha (`0x616D50`).
    serial = struct.unpack_from("<I", cuerpo, 4)[0]
    inv = inventario(c)
    it = next((x for x in inv if x[3] == serial), None)
    precio = precios_venta().get(it[0]) if it else None
    if it is None or precio is None or it[2] < 18:      # 🟡 lo puesto y la barra de atajos no se venden
        return [(0x1042, struct.pack("<HIIB", 0, serial, c["plata"], 0), 0)]
    inv.remove(it)
    c["items"] = inv
    c["plata"] = min(c["plata"] + precio * max(1, it[1]), 2_000_000_000)
    guardar(c)
    return [(0x1042, struct.pack("<HIIB", 1, serial, c["plata"], 1 if it[0] <= 19999 else 0), 0)]
