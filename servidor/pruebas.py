r"""servidor/pruebas.py -- ★ las PRUEBAS del server, sin el juego (cada una con su control al
revés), y `preparar`, que arma cuentas de prueba.

    py servidor\juego.py control

Con una cuenta aparte (no toca las de verdad). Las que necesitan los XML del juego se SALTAN
si no están (EDA_EXIGIR_DATOS=1 las vuelve obligatorias).
"""
import json
import os
import re
import struct
import time

from servidor import config
from servidor.estado import ASIGNADAS, PARTIDAS, SALAS, partida
from servidor.cuentas import EXPS, INICIO, cuenta_de, guardar, leer, nivel
from servidor.datos import ESCENARIOS, NADA, PRECIOS, precios_venta, productos, puntos_de, tabla_habilidades, tabla_premios, tipos_item
from servidor.objetos import PUNTOS_POR_NIVEL, casilleros_de, equipo, es_equipo, ficha, inventario, libre_en_bolsa, nivel_engarce, obj_habilidad, pj_cuenta, serial_nuevo, stats_de
from servidor.relay import dir_udp, escribir_relay, identidad_de, identidad_falsa, relay
from servidor.salas import miembro, pares
from servidor.partida import cuerpo_1072, dar_premio
from servidor.juego import cerrada, responder


def control():
    """Sin el juego: cada respuesta tiene que tener el largo que el cliente lee, y el estado
    tiene que cambiar como se espera. Con una cuenta aparte (no toca la de verdad)."""
    import shutil
    ok = []
    saltadas = []

    def chequear(n, cond, d=""):
        print("  %s %s %s" % ("✅" if cond else "⛔", n, d))
        ok.append(bool(cond))

    def falta_xml(nombre, ruta):
        """Sin el XML del juego (Softnyx: no está en el repositorio) esa parte se SALTA; con
        EDA_EXIGIR_DATOS=1 cuenta como falla (en una PC con el juego, tiene que estar)."""
        if os.environ.get("EDA_EXIGIR_DATOS"):
            chequear("%s (py herramientas\\sacar_xml.py)" % nombre, False, ruta)
        else:
            print("  ⏭ saltada: falta %s (%s)" % (nombre, ruta))
            saltadas.append(nombre)
    os.makedirs(config.ESTADO, exist_ok=True)
    config.RELAY_IP = ""                                    # (el modo relay lo prueba más abajo)
    config.CUENTAS = os.path.join(config.ESTADO, "cuentas_control")
    config.CUENTA = os.path.join(config.CUENTAS, "no_existe.json")
    shutil.rmtree(config.CUENTAS, ignore_errors=True)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    r = responder(0x1011, b"\1\0\0\0", 99)
    n_items = len(leer(99)["items"])
    chequear("0x1012 = 33 + (21 + 36) × %d ítems + 186 bytes" % n_items,
             len(r[0][1]) == 33 + 57 * n_items + 186, len(r[0][1]))
    chequear("N1 (cuántos ítems) en +0x1C", struct.unpack_from("<H", r[0][1], 0x1C)[0] == n_items)
    chequear("las monedas en cuerpo[0x17]", struct.unpack_from("<H", r[0][1], 0x17)[0] == 3)
    r = responder(0x106A, b"\0\1\xff", 99)
    chequear("revivir descuenta una moneda", leer(99)["monedas"] == 2 and r[0][0] == 0x106B)
    chequear("0x106B = 6 bytes, modo 1, quedan 2", r[0][1] == struct.pack("<HBHB", 1, 1, 2, 0))
    responder(0x106A, b"\0\1\xff", 99)
    responder(0x106A, b"\0\1\xff", 99)
    r = responder(0x106A, b"\0\1\xff", 99)
    chequear("★ el revés: sin monedas NO revive (modo 0)", r[0][1][2] == 0 and leer(99)["monedas"] == 0)
    responder(0x105F, b"\0" * 4, 99)
    for _ in range(10):
        responder(0x1061, b"\0" * 8, 99)
    r = responder(0x1064, b"\0", 99)
    cmds = [x[0] for x in r]
    chequear("0x1064 → 1073 + 106E + 106F", cmds == [0x1073, 0x106E, 0x106F], cmds)
    premio = partida(99).get("premio", [])
    largo = 29 + sum(21 + (36 if es_equipo(t) else 0) for t in premio)
    chequear("largos %d / 19 / 16 (29 + el premio %s)" % (largo, premio),
             [len(x[1]) for x in r] == [largo, 19, 16])
    chequear("N1 del PlayEnd (+25) = los ítems del premio", r[0][1][25] == len(premio))
    # el premio sale de StageReward.xml (si está): cada presente posible, de a uno
    tp = tabla_premios()
    if tp:
        for pres in tp[1011][1]:
            cc = {"items": [], "plata": 0}
            nuevos = dar_premio(cc, 1011, elegir=pres)
            bien = (nuevos == [] if pres[0] != 2 or pres[1] == NADA else
                    [n[:2] for n in nuevos] == [[pres[1], max(1, pres[2])]]
                    and nuevos[0][4] == (0 if 31000 <= pres[1] <= 33999 else 1))
            chequear("premio %s → %s" % (pres, [n[:2] + n[4:] for n in nuevos] or "nada"), bien)
    else:
        falta_xml("StageReward.xml", config.PREMIOS_XML)
    chequear("10 NPC muertos en el resultado", struct.unpack_from("<H", r[1][1], 4)[0] == 10)
    rp, kp, te, mc = ESCENARIOS[1011]
    esperada = max(1, int(round(te * 10 / float(mc))))        # del generador: la tabla del XML
    chequear("EXP = TOTALEXP × 10/56 = %d" % esperada, leer(99)["exp"] == esperada, leer(99)["exp"])
    chequear("la misión 1011 terminada", 1011 in leer(99)["terminadas"])
    chequear("nivel(299) = 1, nivel(300) = 2", nivel(299) == 1 and nivel(300) == 2)
    puntos = puntos_de(te, 10 / float(mc))
    chequear("con 10 de 56 NPC: %d puntos (proporcional, calibrado con el video)" % puntos,
             partida(99)["puntos"] == puntos)
    puntos = PRECIOS[2] + 30                                # alcanza para el bronce, no para otra
    partida(99)["puntos"] = puntos
    r = responder(0x1070, bytes.fromhex("000a"), 99)           # la 1ª de bronce, medida (20:00)
    chequear("carta de bronce: %d − %d puntos" % (puntos, PRECIOS[2]),
             struct.unpack_from("<I", r[0][1], 7)[0] == max(0, puntos - PRECIOS[2]))
    chequear("0x1071: u8 1 · FILA 2 · JUGADOR 0 (no la carta) · EXP de cartas %d" % PRECIOS[2],
             r[0][1][:3] == b"\1\2\0" and struct.unpack_from("<I", r[0][1], 3)[0] == PRECIOS[2])
    quedan = max(0, puntos - PRECIOS[2])
    hay_1072 = [x for x in r if x[0] == 0x1072]
    chequear("con %d puntos %s otra carta → %s 0x1072" % (
        quedan, "no alcanza para" if quedan < min(PRECIOS) else "alcanza para",
        "sale el" if quedan < min(PRECIOS) else "todavía no sale el"),
             bool(hay_1072) == (quedan < min(PRECIOS)))
    c1072 = cuerpo_1072(99, partida(99))
    chequear("0x1072 = el índice de la stage (1011) + (jugador 0, 1)",
             c1072 == struct.pack("<IBBB", 1011, 1, 0, 1), c1072.hex())
    for carta_n, fila_esperada in ((0, 0), (3, 0), (4, 1), (9, 1), (10, 2), (17, 2)):
        partida(99)["puntos"], partida(99)["exp_cartas"] = 1000, 0
        r = responder(0x1070, bytes([0, carta_n]), 99)
        chequear("carta %d → fila %d (cobra %d)" % (carta_n, fila_esperada, PRECIOS[fila_esperada]),
                 r[0][1][1] == fila_esperada
                 and struct.unpack_from("<I", r[0][1], 7)[0] == 1000 - PRECIOS[fila_esperada])
    antes_exp = leer(99)["exp"]
    partida(99)["puntos"] = PRECIOS[0] - 1
    r = responder(0x1070, b"\0\3", 99)
    chequear("★ el revés: sin puntos para la carta de oro NO da EXP",
             leer(99)["exp"] == antes_exp and struct.unpack_from("<I", r[0][1], 7)[0] == PRECIOS[0] - 1)
    tp2 = tabla_premios()
    if tp2:
        cc = {"items": [], "plata": 0, "exp": 0}
        dar_premio(cc, 1013)
        oro = sum(d for t_, d, _ in tp2[1013][1] if t_ == 0)
        exp_ = sum(d for t_, d, _ in tp2[1013][1] if t_ == 1)
        chequear("premio 1013 = Σ Type 0 → oro (%d), Σ Type 1 → EXP (%d), como `0x5FEA50/AA0`" % (oro, exp_),
                 cc["plata"] == oro and cc["exp"] == exp_)
    chequear("calibrado con el video: 1011 completa = 257 puntos", puntos_de(128, 1.0) == 257)
    sala = bytearray(0x59)
    struct.pack_into("<H", sala, 4, 0xFFFF)
    struct.pack_into("<I", sala, 0x28, 1012)
    r = responder(0x101D, b"\0\0\0\0" + bytes(sala), 98)
    chequear("0x101E = 94 B con la sala del cliente (1012) y número 1",
             len(r[0][1]) == 94 and struct.unpack_from("<I", r[0][1], 5 + 0x28)[0] == 1012
             and struct.unpack_from("<H", r[0][1], 5 + 4)[0] == 1, r[0][1][5 + 0x28:5 + 0x2C].hex())
    chequear("★ el revés: sin 0x101D, la partida queda en 1011", partida(97)["escenario"] == 1011)
    chequear("un comando desconocido → None (contestan las reglas)", responder(0x9999, b"", 99) is None)
    responder(0x1065, b"\0" * 5, 96)
    chequear("★ el revés: recién muerto, el «estoy vivo» NO trae game over",
             [x[0] for x in responder(0x1001, b"\xf0", 96)] == [0x1001])
    partida(96)["game_over_en"] = time.time() - 1
    r = responder(0x1001, b"\xf0", 96)
    chequear("vencido: 1001 + 1069 + 1075 (a los 6 s)",
             [(x[0], x[2]) for x in r] == [(0x1001, 0), (0x1069, 0), (0x1075, 6000)], r)
    responder(0x1065, b"\0" * 5, 95)
    responder(0x106A, b"\0\0\xff", 95)
    chequear("con respuesta al cuadro (aunque sea «no»), no hay game over por tiempo",
             partida(95)["game_over_en"] is None)
    # ★ multijugador: cada conexión su cuenta; al cerrarse, la cuenta queda libre
    PARTIDAS.clear()
    ASIGNADAS.clear()
    a, b = cuenta_de(201), cuenta_de(202)
    chequear("dos conexiones → dos cuentas distintas", (a, b) == ("rui", "kai"), (a, b))
    chequear("la misma conexión → la misma cuenta", cuenta_de(201) == "rui")
    cerrada(201)
    chequear("★ cerrada la 1ª, la conexión nueva toma «rui» (libre)", cuenta_de(203) == "rui")
    r = responder(0x1011, b"\1\0\0\0", 202)
    chequear("el personaje de la 2ª conexión se llama «kai»", b"k\0a\0i\0" in r[0][1] or b"kai" in r[0][1])
    # ★ INVENTARIO: el 0x102D que mandó el cliente de verdad (18:40, las 8 piezas de Warrior
    #   equipadas con clic derecho), + un serial que no existe (99) que se tiene que ignorar
    real = bytes.fromhex("0000000068a38900000000000000000000000000080000000000010000000a02000000"
                         "0b030000000004000000040500000006060000000807000000010800000009")
    medido = dict(struct.unpack_from("<IB", real, 26 + 5 * k) for k in range(8))
    falso = bytearray(real) + struct.pack("<IB", 99, 3)
    struct.pack_into("<H", falso, 20, 9)
    antes = leer(203)
    r = responder(0x102D, bytes(falso), 203)
    d = leer(203)
    chequear("0x102D → 0x102E, modo 3 (lobby)", r[0][0] == 0x102E and r[0][1][:3] == b"\1\0\3")
    chequear("0x102E = 3 + 8 + 16 + 76 + 2 + 8 × 6 + 2", len(r[0][1]) == 3 + 8 + 16 + 76 + 2 + 48 + 2,
             len(r[0][1]))
    chequear("cada serial quedó en el casillero que mandó el cliente",
             all(d["items"][s - 1][2] == k for s, k in medido.items()))
    chequear("★ el revés: el 201 (Hunter, serial 9) no se movió: sigue en la bolsa",
             d["items"][8][2] == casilleros_de(antes["items"])[8] >= 18)
    chequear("★ el revés: el serial 99 no existe → ignorado (8 confirmados, no 9)",
             struct.unpack_from("<H", r[0][1], 3 + 8 + 16 + 76)[0] == 8)
    # el equipo (18 u32) del generador = el que midió Frida en el cliente: 1..8 y nada más
    chequear("el EQUIPO = lo medido en el cliente (1 2 3 4 5 6 7 8 0…)",
             equipo(d) == list(range(1, 9)) + [0] * 10, equipo(d))
    chequear("y va en el personaje del 0x1012 (+0x72)",
             responder(0x1011, b"\1\0\0\0", 203)[0][1][-0xBA + 0x72:][:8] == struct.pack("<2I", 1, 2))
    # ★ TIENDA: el 0x103F de verdad (18:48, «Basic Long Sword» = producto 1). El precio y el ítem
    #   salen de Product.xml (el generador), no se escriben acá
    tabla = productos()
    if not tabla:
        falta_xml("Product.xml", config.PRODUCTOS_XML)
    else:
        precio, _, dan = tabla[1]
        antes = leer(203)
        r = responder(0x103F, bytes.fromhex("00000000010100"), 203)
        d = leer(203)
        chequear("0x103F producto 1 → 0x1040 resultado 1", r[0][0] == 0x1040 and r[0][1][:2] == b"\1\0")
        chequear("se cobra el precio de Product.xml (%d)" % precio,
                 d["plata"] == antes["plata"] - precio and
                 struct.unpack_from("<I", r[0][1], 2)[0] == d["plata"])
        chequear("y da su ítem %s en la bolsa" % (dan,),
                 [it[:2] for it in d["items"][len(antes["items"]):]] == [list(x) for x in dan]
                 and d["items"][-1][2] >= 18)
        chequear("0x1040 = 15 + 2 + 21 + 36 (equipo: con ficha)", len(r[0][1]) == 15 + 2 + 21 + 36,
                 len(r[0][1]))
        d["plata"] = precio - 1
        guardar(d)
        r = responder(0x103F, bytes.fromhex("00000000010100"), 203)
        chequear("★ el revés: sin oro → resultado 0 y no cobra", r[0][1][:2] == b"\0\0"
                 and leer(203)["plata"] == precio - 1)
        r = responder(0x103F, bytes.fromhex("000000000134ff"), 203)
        chequear("★ el revés: un producto que no existe → resultado 0", r[0][1][:2] == b"\0\0")
        # ★ VENDER: la espada comprada (último serial). Precio del generador (BuyItem)
        d = leer(203)
        inv = inventario(d)
        vendida = inv[-1]
        venta = precios_venta()[vendida[0]]
        r = responder(0x1041, struct.pack("<II", 0, vendida[3]), 203)
        d2 = leer(203)
        chequear("0x1041 → 0x1042 = u16 1 · serial · oro · 1 (11 B)",
                 r[0][1] == struct.pack("<HIIB", 1, vendida[3], d["plata"] + venta, 1), r[0][1].hex())
        chequear("paga %d (BuyGold) y el ítem ya no está" % venta,
                 d2["plata"] == d["plata"] + venta and vendida[3] not in [x[3] for x in inventario(d2)])
        # vender uno del MEDIO (el 201 de Hunter, serial 9): los de después NO cambian de serial
        despues = [x for x in inventario(d2) if x[3] > 9]
        responder(0x1041, struct.pack("<II", 0, 9), 203)
        d3 = leer(203)
        chequear("★ vendido uno del medio, los demás conservan su serial",
                 [x for x in inventario(d3) if x[3] > 9] == despues and despues)
        equipado = next(x for x in inventario(d3) if x[2] < 12)
        r = responder(0x1041, struct.pack("<II", 0, equipado[3]), 203)
        chequear("★ el revés: lo que está PUESTO no se vende", r[0][1][:2] == b"\0\0"
                 and leer(203)["plata"] == d3["plata"])
        r = responder(0x1041, struct.pack("<II", 0, 777), 203)
        chequear("★ el revés: un serial que no existe → resultado 0", r[0][1][:2] == b"\0\0")
    # ★ MODO RELAY: con la bandera, identidad inventada + dirección del relay; sin ella, lo de antes
    bandera_real, mapa_real = config.RELAY_BANDERA, config.RELAY_MAPA
    config.RELAY_BANDERA = os.path.join(config.CUENTAS, "modo_relay")
    config.RELAY_MAPA = os.path.join(config.CUENTAS, "relay.json")
    chequear("★ el revés: sin bandera, sin relay (identidad = la local)", relay() is None
             and identidad_de(5) != identidad_falsa(5) and dir_udp(5) == partida(5).get("udp"))
    open(config.RELAY_BANDERA, "w").close()
    m = miembro(leer(203), 0, conexion=203)
    chequear("con bandera: identidad inventada en +0xA del miembro",
             m[0xA:0xA + 34] == identidad_falsa(203).encode("utf-16-le"))
    chequear("y la dirección = su puerto en el relay (127.0.0.1:%d)" % (config.RELAY_BASE + 1 + 203),
             struct.unpack_from("<IH", m, 0x48) == (0x7F000001, config.RELAY_BASE + 1 + 203))
    r = responder(0x100F, bytes(0xE9), 203)
    chequear("el 0x1010 manda el punch al RELAY", r[0][1][-6:] == struct.pack("<IH", 0x7F000001, config.RELAY_BASE))
    chequear("y escribe relay.json para el relay",
             json.load(open(config.RELAY_MAPA)).get("203", {}).get("falsa") == identidad_falsa(203))
    chequear("el 0x1012 lleva la conexión en +6 (el id del 0x3006)",
             struct.unpack_from("<I", responder(0x1011, b"\1\0\0\0", 203)[0][1], 6)[0] == 203)
    # ★★ P2P DIRECTO (MEDICIONES §39–40): con la MAC del 0x100F y lo que vio el punch, cada uno recibe
    #   la dirección del OTRO (pública, o privada si comparten IP pública); el relay sólo de respaldo
    punch_real, p2p_real = config.PUNCH_MAPA, config.P2P
    config.PUNCH_MAPA = os.path.join(config.CUENTAS, "punch.json")
    config.P2P = "directo"

    def quien(mac, ip_priv, puerto_priv):
        b = bytearray(0xE9)
        b[0x7A:0x7A + 34] = mac.encode("utf-16-le")[:34].ljust(34, b"\0")
        struct.pack_into("<IH", b, 0xDD, ip_priv, puerto_priv)
        return bytes(b)

    def ip_int(t):
        return struct.unpack(">I", bytes(int(x) for x in t.split(".")))[0]
    macs = {401: "02:AA:00:00:00:01", 402: "02:AA:00:00:00:02", 403: "02:AA:00:00:00:03"}
    for n, mac_n in macs.items():
        responder(0x100F, quien(mac_n, ip_int("192.168.0.%d" % (n - 400)), 50000 + n), n)
    basura = bytearray(quien("x", 0, 0))
    basura[0x7A:0x7A + 34] = "H80:\u00d9089:\u008b5:6E:\u00e3".encode("utf-16-le")[:34].ljust(34, b"\0")
    responder(0x100F, bytes(basura), 404)
    chequear("el 0x100F trae la MAC (cuerpo +0x7A) → es su identidad", partida(401).get("mac") == macs[401]
             and identidad_de(401) == macs[401])
    chequear("★ el revés: con basura en ese lugar (juego sin comillas) NO hay MAC → la inventada",
             partida(404).get("mac") is None and identidad_de(404) == identidad_falsa(404))
    # el punch vio a 401 y 403 detrás de la MISMA IP pública (un cíber), y a 402 en otra casa
    json.dump({"401": ["200.1.1.1", 40001], "402": ["190.2.2.2", 40002], "403": ["200.1.1.1", 40003],
               "404": ["181.4.4.4", 40004]}, open(config.PUNCH_MAPA, "w"))
    SALAS[88] = {"sala": bytes(0x59), "anfitrion": 401, "miembros": [401, 402, 403, 404]}
    a = {x[3]: x[1] for x in pares(SALAS[88])}

    def direccion_de(cuerpo, indice):
        for k in range(cuerpo[0]):
            i, ip, puerto = struct.unpack_from("<BIH", cuerpo, 7 + 7 * k)
            if i == indice:
                return ip, puerto
    chequear("a 402 (otra casa) le llega la PÚBLICA de 401 (la que vio el punch)",
             direccion_de(a[402], 0) == (ip_int("200.1.1.1"), 40001))
    chequear("a 403 (mismo cíber que 401) le llega la PRIVADA de 401 (su 0x100F)",
             direccion_de(a[403], 0) == (ip_int("192.168.0.1"), 50401))
    chequear("★ el revés: 404 (sin MAC) va por el RELAY, para todos y todos hacia él",
             direccion_de(a[401], 3) == (0x7F000001, config.RELAY_BASE + 1 + 404)
             and direccion_de(a[404], 0) == (0x7F000001, config.RELAY_BASE + 1 + 401))
    m = miembro(leer(401), 0, conexion=401, para=402)
    chequear("el miembro lleva la MAC REAL en +0xA y la dirección directa en +0x48",
             m[0xA:0xA + 34] == macs[401].encode("utf-16-le")
             and struct.unpack_from("<IH", m, 0x48) == (ip_int("200.1.1.1"), 40001))
    escribir_relay()
    chequear("relay.json: la «falsa» de quien mandó su MAC es la real (el relay no la toca)",
             json.load(open(config.RELAY_MAPA))["401"]["falsa"] == macs[401])
    config.P2P = "relay"
    chequear("★ el revés: con EDA_P2P=relay, todo por el relay aunque haya MAC",
             dir_udp(401, 402) == (0x7F000001, config.RELAY_BASE + 1 + 401))
    del SALAS[88]
    config.PUNCH_MAPA, config.P2P = punch_real, p2p_real
    config.RELAY_BANDERA, config.RELAY_MAPA = bandera_real, mapa_real
    # ★ CREATE SOCKET (el 0x1037 de verdad: ítem 11, taladro 12)
    d = leer(203)
    inv = inventario(d)
    s = serial_nuevo(inv)
    inv += [[2, 1, libre_en_bolsa(inv), s, 1]]
    inv += [[40001, 2, libre_en_bolsa(inv), s + 1, 1]]
    d["items"] = inv
    guardar(d)
    r = responder(0x1037, struct.pack("<III", 0x178, s, s + 1), 203)
    chequear("0x1037 → 0x1038 de 46 B, resultado 1, queda 1 taladro",
             len(r[0][1]) == 46 and struct.unpack_from("<HIi", r[0][1]) == (1, s + 1, 1))
    niv = struct.unpack_from("<I", r[0][1], 10 + 0x20)[0]
    chequear("la ficha nueva: el ítem %d con el engarce 0 ABIERTO (3 bits ≠ 0) y sin piedra" % s,
             struct.unpack_from("<I", r[0][1], 10 + 4)[0] == s and nivel_engarce(niv, 0) == 1
             and nivel_engarce(niv, 1) == 0
             and struct.unpack_from("<10H", r[0][1], 10 + 12) == (0,) * 10)
    responder(0x1037, struct.pack("<III", 0x178, s, s + 1), 203)
    niv = leer(203)["fichas"][str(s)]["niveles"]
    chequear("un 2º taladro: 2 engarces abiertos, y el taladro se acaba",
             [nivel_engarce(niv, i) for i in range(3)] == [1, 1, 0]
             and not any(x[3] == s + 1 for x in inventario(leer(203))))
    r = responder(0x1037, struct.pack("<III", 0x178, s, s + 1), 203)
    chequear("★ el revés: sin taladro → resultado 0 y sin engarce nuevo", r[0][1][:2] == b"\0\0"
             and nivel_engarce(leer(203)["fichas"][str(s)]["niveles"], 2) == 0)
    # ★ ENCHANT: una piedra (21001) en el engarce 0 (el 0x1033 medido: ítem, N 1, engarce 0, piedra)
    d = leer(203)
    inv = inventario(d)
    ps = serial_nuevo(inv)
    inv += [[21001, 1, libre_en_bolsa(inv), ps, 1]]
    d["items"] = inv
    guardar(d)
    r = responder(0x1033, struct.pack("<IIBBI", 0x17E, s, 1, 0, ps), 203)
    chequear("0x1033 → 0x1034 = 7 + 20 + 4 B: la piedra 21001 en el engarce 0, y se gasta",
             len(r[0][1]) == 31 and struct.unpack_from("<HIB", r[0][1]) == (1, s, 1)
             and struct.unpack_from("<H", r[0][1], 7)[0] == 21001
             and struct.unpack_from("<I", r[0][1], 27)[0] == ps
             and not any(x[3] == ps for x in inventario(leer(203))))
    inv = inventario(leer(203))
    d = leer(203)
    d["items"] = inv + [[21002, 1, libre_en_bolsa(inv), ps + 1, 1]]
    guardar(d)
    r = responder(0x1033, struct.pack("<IIBBI", 0x17E, s, 1, 0, ps + 1), 203)
    chequear("★ el revés: un engarce YA ocupado no se pisa (y la piedra no se gasta)",
             r[0][1][:2] == b"\0\0" and any(x[3] == ps + 1 for x in inventario(leer(203))))
    r = responder(0x1033, struct.pack("<IIBBI", 0x17E, s, 1, 5, ps + 1), 203)
    chequear("★ el revés: un engarce CERRADO (el 5) no acepta piedra", r[0][1][:2] == b"\0\0")
    # ★ REPAIR: los dos ítems gastados de la medición (75 % del tipo 1, 50 % del tipo 2) → 22500
    tt = tipos_item()
    if tt:
        d = leer(203)
        inv = inventario(d)
        w = serial_nuevo(inv)
        inv += [[1, 1, libre_en_bolsa(inv), w, 1]]
        inv += [[2, 1, libre_en_bolsa(inv), w + 1, 1]]
        d["items"], d["plata"] = inv, 30000
        d["durabilidad"] = {str(w): 7500, str(w + 1): 5000}
        guardar(d)
        esperado = (tt[1][0] - 7500) * tt[1][1] + (tt[2][0] - 5000) * tt[2][1]
        r = responder(0x1039, struct.pack("<IH", 0x186, 1), 203)
        chequear("Repair All cobra %d (como el cliente) y deja las dos al 100 %%" % esperado,
                 esperado == 22500 and struct.unpack_from("<HIB", r[0][1]) == (1, 30000 - esperado, 2)
                 and leer(203)["durabilidad"] == {str(w): 10000, str(w + 1): 10000})
        r = responder(0x1039, struct.pack("<IH", 0x186, 1), 203)
        chequear("★ el revés: con todo sano no hay nada que arreglar → resultado 0",
                 r[0][1][:2] == b"\0\0" and leer(203)["plata"] == 30000 - esperado)
    else:
        falta_xml("ItemTypeList.xml", config.TIPOS_XML)
    # ★ REFINE SPIRIT STONE: Phase (3 × 21001 → 21021) y Level (2 × 21001 → 21002)
    d = leer(203)
    inv = inventario(d)
    q = serial_nuevo(inv)
    for k in range(5):
        inv += [[21001, 1, libre_en_bolsa(inv), q + k, 1]]
    d["items"] = inv
    guardar(d)
    habia = [x[0] for x in inv].count(21001)
    r = responder(0x1035, struct.pack("<IB3I", 0x182, 0, q, q + 1, q + 2), 203)
    chequear("Phase: 3 × 21001 → 0x1036 con una 21021 nueva y las 3 gastadas (25 + 12 B)",
             len(r[0][1]) == 37 and r[0][1][:3] == b"\1\0\0"
             and struct.unpack_from("<H", r[0][1], 3 + 8)[0] == 21021
             and [x[0] for x in inventario(leer(203))].count(21001) == habia - 3)
    r = responder(0x1035, struct.pack("<IB2I", 0x182, 1, q + 3, q + 4), 203)
    chequear("Level: 2 × 21001 → una 21002", struct.unpack_from("<H", r[0][1], 3 + 8)[0] == 21002
             and [x[0] for x in inventario(leer(203))].count(21001) == habia - 5)
    nueva = next(x for x in inventario(leer(203)) if x[0] == 21002)
    otra = next(x for x in inventario(leer(203)) if x[0] == 21021)
    r = responder(0x1035, struct.pack("<IB2I", 0x182, 1, nueva[3], otra[3]), 203)
    chequear("★ el revés: dos piedras DISTINTAS no se refinan (y no se gastan)",
             r[0][1][:2] == b"\0\0" and any(x[3] == nueva[3] for x in inventario(leer(203))))
    chequear("y la ficha va en el 0x1012 con sus engarces",
             ficha(leer(203), s) in responder(0x1011, b"\1\0\0\0", 203)[0][1])
    # ★ BORRAR HABILIDAD
    d = leer(203)
    d["habilidades"] = [[1000, 1, 1, 0, 1], [1001, 1, 3, 1, 2]]
    guardar(d)
    r = responder(0x1043, struct.pack("<II", 0x174, 1000), 203)
    chequear("0x1043 clave 1000 → 0x1044 (1, 1000) y queda sólo la otra",
             r[0] == (0x1044, struct.pack("<HI", 1, 1000), 0)
             and [h[0] for h in leer(203)["habilidades"]] == [1001])
    r = responder(0x1043, struct.pack("<II", 0x174, 1000), 203)
    chequear("★ el revés: una clave que no tiene → resultado 0", r[0][1][:2] == b"\0\0")
    d = leer(203)
    d["habilidades"] = []                                   # (las pruebas de aprender empiezan sin)
    guardar(d)
    # ★ PUNTOS DE ESTADÍSTICA: los libres salen del nivel; el reparto vuelve en el 0x102D
    d = leer(203)
    d["exp"], d["stats"] = EXPS[9], [0, 0, 0, 0, 0]          # nivel 10
    guardar(d)
    libres = PUNTOS_POR_NIVEL * 9
    chequear("nivel 10 → %d puntos libres en +0x6C del personaje" % libres,
             struct.unpack_from("<H", pj_cuenta(leer(203)), 0x6C)[0] == libres)

    def reparto(st):
        return (b"\0" * 4 + struct.pack("<I6H", 0x89A368, *st) + struct.pack("<HHH", 0, 0, 0))
    # el 0x102D de verdad (21:10): 5 Str, 3 Con, y 8 = los gastados en la tanda
    responder(0x102D, reparto([5, 3, 0, 0, 0, 8]), 203)
    chequear("un reparto que cuadra se guarda (5 Str, 3 Con; 8 gastados)",
             leer(203)["stats"] == [5, 3, 0, 0, 0] and stats_de(leer(203))[5] == libres - 8)
    responder(0x102D, reparto([5, 3, 2, 0, 0, 2]), 203)
    chequear("una 2ª tanda (+2 Dex) suma", leer(203)["stats"] == [5, 3, 2, 0, 0])
    responder(0x102D, reparto([50, 3, 2, 0, 0, 45]), 203)
    chequear("★ el revés: pedir más puntos de los que hay NO se guarda",
             leer(203)["stats"] == [5, 3, 2, 0, 0])
    responder(0x102D, reparto([0, 3, 7, 0, 0, 0]), 203)
    chequear("★ el revés: BAJAR uno ya repartido no se guarda", leer(203)["stats"] == [5, 3, 2, 0, 0])
    responder(0x102D, reparto([6, 3, 2, 0, 0, 5]), 203)
    chequear("★ el revés: los gastados no coinciden con lo que subió → no se guarda",
             leer(203)["stats"] == [5, 3, 2, 0, 0])
    # ★ READY con 3: el 0x1047 de mio (jugador 2) es «02 01» → estado 1 para los demás
    SALAS[77] = {"sala": bytes(0x59), "anfitrion": 301, "miembros": [301, 302, 303]}
    partida(303)["sala"] = 77
    r = responder(0x1047, b"\2\1", 303)
    chequear("0x1047 «02 01» (jugador 2, listo) → 0x1058 (2, tipo 1, estado 1) a los otros dos",
             sorted(x[3] for x in r if x[0] == 0x1058) == [301, 302]
             and all(x[1] == struct.pack("<BHB", 2, 1, 1) for x in r if x[0] == 0x1058))
    del SALAS[77]
    # ★ EL CICLO DE LA SALA (aporte de Hysteria-xyz, PR #3): salir, el mando que pasa, echar, el título
    SALAS[77] = {"sala": bytes(0x59), "anfitrion": 301, "miembros": [301, 302, 303]}
    for n in (301, 302, 303):
        partida(n)["sala"] = 77
    r = responder(0x1045, b"", 301)
    chequear("0x1045 (Leave Room) → 0x1046 (u16 1) al que sale", (0x1046, b"\1\0", 0) in r)
    chequear("se fue el anfitrión: el mando pasa a 302, y 0x1058 (lugar 0, tipo 3, nuevo anfitrión 0) a los dos",
             SALAS[77]["anfitrion"] == 302
             and sorted(x[3] for x in r if x[0] == 0x1058) == [302, 303]
             and all(x[1] == struct.pack("<BHB", 0, 3, 0) for x in r if x[0] == 0x1058))
    r = responder(0x1051, b"\x00", 303)
    chequear("★ el revés: 303 NO es el anfitrión: no puede echar a nadie",
             SALAS[77]["miembros"] == [302, 303] and not any(x[0] == 0x1054 for x in r))
    r = responder(0x1051, b"\x00", 302)
    chequear("★ el revés: el anfitrión no se puede echar a sí mismo", SALAS[77]["miembros"] == [302, 303])
    r = responder(0x1051, b"\x01", 302)
    chequear("0x1051 (Kick) → 0x1052 al anfitrión y 0x1054 al echado (303)",
             any(x[0] == 0x1052 and len(x) == 3 for x in r) and any(x[0] == 0x1054 and x[3] == 303 for x in r))
    chequear("303 queda sin sala y en la sala sólo está 302",
             partida(303).get("sala") is None and SALAS[77]["miembros"] == [302])
    r = responder(0x1049, b"\0\1\0" + "Nueva".encode("utf-16-le"), 302)
    chequear("0x1049 (título) → 0x104A con el texto", r[0][0] == 0x104A and r[0][1][4:] == "Nueva".encode("utf-16-le"))
    responder(0x1045, b"", 302)
    chequear("se fue el último: la sala desaparece", 77 not in SALAS)
    chequear("sala → Inventory: 0x104C → 0x104D (u16 1 · u8)",
             responder(0x104C, b"\0", 203) == [(0x104D, b"\1\0\0", 0)])
    # ★ VERIFICAR un libro de habilidad (el 0x103B de verdad: libro 14, pergamino 13)
    d = leer(203)
    inv = inventario(d)
    s = serial_nuevo(inv)
    inv += [[32001, 1, libre_en_bolsa(inv), s, 0]]
    inv += [[40051, 2, libre_en_bolsa(inv), s + 1, 1]]
    d["items"] = inv
    guardar(d)
    r = responder(0x103B, struct.pack("<III", 0, s, s + 1), 203)
    d = leer(203)
    libro = next(x for x in inventario(d) if x[3] == s)
    chequear("0x103B → 0x103C de 31 B, resultado 1, queda 1 pergamino",
             len(r[0][1]) == 31 and struct.unpack_from("<HIi", r[0][1]) == (1, s + 1, 1))
    chequear("el libro queda VERIFICADO (+0xE = 1, en la cuenta y en el registro)",
             libro[4] == 1 and r[0][1][10 + 0xE] == 1 and struct.unpack_from("<H", r[0][1], 18)[0] == 32001)
    r = responder(0x103B, struct.pack("<III", 0, s, s + 1), 203)
    chequear("★ el revés: un libro YA verificado no se vuelve a verificar (ni gasta pergamino)",
             r[0][1][:2] == b"\0\0" and next(x for x in inventario(leer(203)) if x[3] == s + 1)[1] == 1)
    # ★ APRENDER: el libro verificado (Dash). Precio y nivel salen de Skill.xml (el generador)
    th = tabla_habilidades()
    if not th:
        falta_xml("Skill.xml", config.HABILIDADES_XML)
    else:
        tipo_h, ident, _, costo, nivel_min = th[32001]
        d = leer(203)
        d["exp"], d["plata"] = EXPS[nivel_min - 2], 100000             # un nivel MENOS que el pedido
        guardar(d)
        r = responder(0x103D, struct.pack("<IIHH", 0, s, 0, 0), 203)
        chequear("★ el revés: con nivel %d (< %d) NO aprende" % (nivel_min - 1, nivel_min),
                 r[0][1][:2] == b"\0\0" and not leer(203).get("habilidades"))
        d = leer(203)
        d["exp"] = EXPS[nivel_min - 1]
        guardar(d)
        r = responder(0x103D, struct.pack("<IIHH", 0, s, 0, 0), 203)
        d = leer(203)
        chequear("0x103D → 0x103E de 15 + 13 + 2 B, resultado 1", len(r[0][1]) == 30
                 and r[0][1][:2] == b"\1\0", len(r[0][1]))
        chequear("cobra %d (COST_GOLD) y el libro sale de la bolsa" % costo,
                 d["plata"] == 100000 - costo and s not in [x[3] for x in inventario(d)])
        chequear("el ORO en +3 y el serial del libro en +7 (como los lee 0x54CCC1 / 0x54CCD0)",
                 struct.unpack_from("<II", r[0][1], 3) == (d["plata"], s))
        chequear("la habilidad: activa, ID %d" % ident,
                 struct.unpack_from("<IBH", r[0][1], 15 + 4) == (s, tipo_h, ident))
        r = responder(0x1017, b"", 203)
        chequear("y viene en el 0x1018 (N2 = 1, 13 B al final)",
                 struct.unpack_from("<H", r[0][1], 7)[0] == 1 and r[0][1][-13:] == obj_habilidad(d["habilidades"][0]))
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_login(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    shutil.rmtree(config.CUENTAS, ignore_errors=True)
    if saltadas:
        print("\n  (%d pruebas; saltadas las de %s: faltan los XML del juego)"
              % (len(ok), ", ".join(saltadas)))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def cuerpo_100f(usuario="", ticket="", mac="AA:BB:CC:DD:EE:01"):
    """Un 0x100F como lo arma el juego (237 B con la cabecera): el bloque del launcher en +0x04 y
    +0x2E (UTF-16 hasta el 0, y BASURA después, como se midió), la MAC en +0x7A y su UDP en +0xDD."""
    c = bytearray(b"\x9b\x8d\x98\x37" * 59)[:0xE9]
    for desde, texto in ((0x04, usuario), (0x2E, ticket), (0x7A, mac)):
        # ⚠ con 20 caracteres el juego NO deja el 0 (medido): lo que sigue es basura de otro campo
        b = texto.encode("utf-16-le") + (b"\0\0" if len(texto) < 20 else b"")
        c[desde:desde + len(b)] = b
    struct.pack_into("<IHIH", c, 0xDD, 0x0100007F, 57654, 0x0100007F, 57654)
    return bytes(c)


def pruebas_login(chequear):
    """★ El LOGIN (servidor/porteria.py): el pase del portero → el ticket → el 0x100F. Con una clave
    Ed25519 de prueba, cada rechazo del pase con su revés, y el modo «abierto» como antes."""
    import base64
    from Crypto.PublicKey import ECC
    from Crypto.Signature import eddsa
    from servidor import porteria

    def b64(x):
        return base64.urlsafe_b64encode(x).rstrip(b"=").decode()

    def firmar(clave, datos, kid="k1", alg="EdDSA"):
        h = b64(json.dumps({"alg": alg, "typ": "JWT", "kid": kid}).encode())
        d = b64(json.dumps(datos).encode())
        return h + "." + d + "." + b64(eddsa.new(clave, "rfc8032").sign((h + "." + d).encode()))

    def rechazo(pase, ahora=None):
        try:
            porteria.canjear(pase, ahora)
            return None
        except porteria.Rechazo as e:
            return e.codigo

    guardado = (config.LOGIN, config.PORTERO_CLAVES, config.PORTERIA)
    clave, otra = ECC.generate(curve="Ed25519"), ECC.generate(curve="Ed25519")
    jwks = os.path.join(config.ESTADO, "control_jwks_%d.json" % os.getpid())
    json.dump({"keys": [{"kty": "OKP", "crv": "Ed25519", "kid": "k1",
                         "x": b64(clave.public_key().export_key(format="raw"))}]}, open(jwks, "w"))
    config.PORTERO_CLAVES = jwks
    config.PORTERIA = os.path.join(config.ESTADO, "control_porteria.db")
    if os.path.exists(config.PORTERIA):
        os.remove(config.PORTERIA)
    try:
        ahora = time.time()
        datos = {"iss": "r2beat-portero", "aud": "eda", "sub": "4242", "iat": int(ahora),
                 "exp": int(ahora) + 300, "jti": "j-1"}
        pase = firmar(clave, datos)
        r = porteria.canjear(pase, ahora)
        chequear("login: el pase del portero → usuario 4242 y un ticket de 20 letras/números",
                 r["usuario"] == "4242" and re.fullmatch(r"[A-Za-z0-9]{20}", r["ticket"]), r)
        chequear("★ el revés: el MISMO pase otra vez → «repetido» (su jti ya se usó)", rechazo(pase, ahora) == "repetido")
        h, d, f = firmar(clave, dict(datos, jti="j-2")).split(".")
        d2 = b64(json.dumps(dict(datos, jti="j-2", sub="1")).encode())
        chequear("★ el revés: cambiarle la cuenta al pase (sin volver a firmar) → «firma»",
                 rechazo(h + "." + d2 + "." + f, ahora) == "firma")
        chequear("★ el revés: firmado con OTRA clave (mismo kid) → «firma»",
                 rechazo(firmar(otra, dict(datos, jti="j-3")), ahora) == "firma")
        chequear("★ el revés: un kid que no está en el JWKS → «clave»",
                 rechazo(firmar(clave, dict(datos, jti="j-4"), kid="k9"), ahora) == "clave")
        sin_firma = b64(b'{"alg":"none","kid":"k1"}') + "." + b64(json.dumps(dict(datos, jti="j-5")).encode()) + "."
        chequear("★ el revés: alg «none» → «algoritmo»", rechazo(sin_firma, ahora) == "algoritmo")
        chequear("★ el revés: para otro juego (aud) → «audiencia»",
                 rechazo(firmar(clave, dict(datos, jti="j-6", aud="r2beat")), ahora) == "audiencia")
        chequear("★ el revés: de otro emisor (iss) → «emisor»",
                 rechazo(firmar(clave, dict(datos, jti="j-7", iss="otro")), ahora) == "emisor")
        chequear("★ el revés: vencido hace 31 s → «vencido»",
                 rechazo(firmar(clave, dict(datos, jti="j-8", exp=int(ahora) - 31)), ahora) == "vencido")
        chequear("…y vencido hace 29 s todavía entra (tolerancia de reloj)",
                 rechazo(firmar(clave, dict(datos, jti="j-9", exp=int(ahora) - 29)), ahora) is None)
        chequear("★ el revés: una cuenta que no es un uid → «cuenta»",
                 rechazo(firmar(clave, dict(datos, jti="j-10", sub="rui")), ahora) == "cuenta")
        chequear("★ el revés: basura → «formato»", rechazo("no.es.unpase!", ahora) == "formato")
        r = porteria.canjear(firmar(clave, dict(datos, jti="j-11")), ahora)   # el ticket que vale

        config.LOGIN = "pase"
        rr = responder(0x100F, cuerpo_100f("4242", r["ticket"]), 301)
        chequear("login: 0x100F con usuario y ticket → 0x1010 resultado 1, cuenta r2b_4242",
                 rr[0][0] == 0x1010 and rr[0][1][:2] == b"\1\0" and ASIGNADAS.get(301) == "r2b_4242")
        rr = responder(0x1011, b"\1\0\0\0", 301)
        chequear("…y su SELECT CHARACTER es el de esa cuenta", rr and rr[0][0] == 0x1012 and leer(301)["nombre"] == "r2b_4242")
        for n, (u, t, que) in enumerate((("4242", "X" * 20, "un ticket inventado"),
                                         ("4243", r["ticket"], "el ticket de OTRA cuenta"),
                                         ("", "", "sin bloque del launcher"))):
            rr = responder(0x100F, cuerpo_100f(u, t), 302 + n)
            chequear("★ el revés: %s → 0x1010 con error 0x66 y sin cuenta" % que,
                     struct.unpack_from("<H", rr[0][1])[0] == 0x66 and 302 + n not in ASIGNADAS)
        chequear("★ el revés: sin login, el 0x1011 no se atiende (ni las reglas fijas)",
                 responder(0x1011, b"\1\0\0\0", 302) == [])
        chequear("★ el revés: el ticket vencido (TICKET_HORAS después) ya no vale",
                 not porteria.ticket_valido("4242", r["ticket"], ahora + config.TICKET_HORAS * 3600 + 1))
        nuevo = porteria.canjear(firmar(clave, dict(datos, jti="j-12")), ahora)
        chequear("★ el revés: un ticket nuevo de la cuenta anula el anterior",
                 porteria.ticket_valido("4242", nuevo["ticket"], ahora)
                 and not porteria.ticket_valido("4242", r["ticket"], ahora))
        config.LOGIN = "abierto"
        ASIGNADAS.clear()
        rr = responder(0x100F, cuerpo_100f(), 310)
        chequear("modo abierto (jugar en casa): sin ticket entra, como rui",
                 rr[0][1][:2] == b"\1\0" and cuenta_de(310) == "rui")
    finally:
        config.LOGIN, config.PORTERO_CLAVES, config.PORTERIA = guardado
        ASIGNADAS.clear()
        for x in (jwks, os.path.join(config.ESTADO, "control_porteria.db")):
            if os.path.exists(x):
                os.remove(x)


# El casillero de EQUIPO de cada familia de ítem (medido con el 0x102D, MEDICIONES §27)
CASILLERO_PARTE = {0: 10, 1: 11, 3: 0, 4: 4, 5: 6, 6: 8, 7: 1, 8: 9}


def preparar(nombre, clase, nivel_pedido):
    """🟡 Una cuenta DE PRUEBA: nivel pedido, el set de grado 1 de su clase PUESTO (Warrior 1, 1001,
    3001…; Hunter 201, 1201, 3201…), todas las habilidades de su clase (y las de todas) que su nivel
    permite, con las de ESPADA (WEAPON 0) en los atajos F1–F8. Pisa la cuenta."""
    os.makedirs(config.CUENTAS, exist_ok=True)
    c = dict(INICIO, nombre=nombre, clase=clase, exp=EXPS[nivel_pedido - 1], plata=100000)
    base = 0 if clase == 1 else 200
    items = []
    for familia, cas in CASILLERO_PARTE.items():
        tipo = familia * 1000 + base + 1 if familia else base + 1
        items.append([tipo, 1, cas, len(items) + 1, 1])
    items.append([26001, 20, 18, len(items) + 1, 1])
    c["items"] = items
    x = open(config.HABILIDADES_XML, "rb").read()
    habs, atajo = [], 1
    filas = []
    for clase_xml, a in re.findall(rb"<(ACTIVE|PASSIVE)_SKILL ([^>]*)>", x):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', a))
        if int(v[b"CLASS"]) in (clase, 65535) and int(v[b"ACQUIRE_LEVEL"]) <= nivel_pedido:
            filas.append((clase_xml == b"ACTIVE", int(v.get(b"WEAPON", b"9")), int(v[b"ACQUIRE_LEVEL"]),
                          int(v[b"ID"])))
    for activa, arma, _, ident in sorted(filas, key=lambda f: (not f[0], f[1], f[2])):
        a = atajo if activa and arma == 0 and atajo <= 8 else 0
        atajo += 1 if a else 0
        habs.append([1000 + len(habs), 1 if activa else 2, ident, len(habs), a])
    c["habilidades"] = habs
    c["lugares_habilidad"] = max(12, len(habs))
    guardar(c)
    return c
