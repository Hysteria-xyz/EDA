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
    nivel_real, config.NIVEL_INICIAL = config.NIVEL_INICIAL, 0   # (las cuentas de prueba arrancan en 0 EXP)
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
        partida(99).update(puntos=1000, exp_cartas=0, cartas_hasta=time.time() + 60, cartas_elegidas=set())
        antes_exp = leer(99)["exp"]
        r = responder(0x1070, bytes([0, carta_n]), 99)
        chequear("carta %d → fila %d (cobra %d)" % (carta_n, fila_esperada, PRECIOS[fila_esperada]),
                 r[0][1][1] == fila_esperada
                 and struct.unpack_from("<I", r[0][1], 7)[0] == 1000 - PRECIOS[fila_esperada])
        # ★ (PR #5) la misma carta otra vez: no se contesta ni se cobra
        repetida = responder(0x1070, bytes([0, carta_n]), 99)
        chequear("★ el revés: la carta %d otra vez → sin 2.º cobro (la EXP quedó guardada una vez)" % carta_n,
                 repetida == [] and leer(99)["exp"] == antes_exp + PRECIOS[fila_esperada]
                 and partida(99)["puntos"] == 1000 - PRECIOS[fila_esperada])
    antes_exp = leer(99)["exp"]
    partida(99)["puntos"] = PRECIOS[0] - 1
    r = responder(0x1070, b"\0\1", 99)
    chequear("★ el revés: sin puntos para la carta de oro NO da EXP (y no se contesta, como el PR #5)",
             leer(99)["exp"] == antes_exp and r == [] and partida(99)["puntos"] == PRECIOS[0] - 1)
    for carta_n, que in ((18, "fuera de las 18"), (255, "fuera de las 18")):
        chequear("★ el revés: una carta %s (%d) no se contesta" % (que, carta_n),
                 responder(0x1070, bytes([0, carta_n]), 99) == [])
    partida(99).update(puntos=1000, cartas_hasta=time.time() - 1)
    chequear("★ el revés: vencido el tiempo de las cartas, no se cobra",
             responder(0x1070, b"\0\2", 99) == [] and partida(99)["puntos"] == 1000)
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
    # ★ (MEDICIONES §52, lo de prod: dos PCs de la misma casa y el ANFITRIÓN sin 0x3006) → la misma IP
    #   con que se conectaron alcanza para darse la PRIVADA
    json.dump({"402": ["190.2.2.2", 40002]}, open(config.PUNCH_MAPA, "w"))
    partida(401)["ip_tcp"], partida(402)["ip_tcp"] = "190.2.2.2", "190.2.2.2"
    chequear("misma IP de conexión, el anfitrión sin punch: a 402 le llega la PRIVADA de 401",
             dir_udp(401, 402) == (ip_int("192.168.0.1"), 50401)
             and dir_udp(402, 401) == (ip_int("192.168.0.2"), 50402))
    partida(402)["ip_tcp"] = "190.9.9.9"
    chequear("★ el revés: con IPs de conexión distintas, NO la privada; y como el anfitrión no pasó por "
             "el punch, NO mixto: los DOS por el relay (con CGNAT el directo no entra)",
             dir_udp(402, 401) == (0x7F000001, config.RELAY_BASE + 1 + 402)
             and dir_udp(401, 402) == (0x7F000001, config.RELAY_BASE + 1 + 401))
    partida(401).pop("ip_tcp"), partida(402).pop("ip_tcp")
    json.dump({"401": ["200.1.1.1", 40001], "402": ["190.2.2.2", 40002], "403": ["200.1.1.1", 40003],
               "404": ["181.4.4.4", 40004]}, open(config.PUNCH_MAPA, "w"))
    escribir_relay()
    chequear("relay.json: la «falsa» de quien mandó su MAC es la real (el relay no la toca)",
             json.load(open(config.RELAY_MAPA))["401"]["falsa"] == macs[401])
    mapa_rel = json.load(open(config.RELAY_MAPA))
    chequear("relay.json: cada uno con los de SU sala (para el descarte del relay, §47)",
             sorted(mapa_rel["401"]["sala"]) == sorted(SALAS[88]["miembros"])
             and all(mapa_rel[str(n)]["sala"] == [] for n in ASIGNADAS if n not in SALAS[88]["miembros"]))
    ASIGNADAS.setdefault(499, "ren")
    escribir_relay()
    estaba = "499" in json.load(open(config.RELAY_MAPA))
    cerrada(499)                                           # (uno que no está en ninguna sala)
    chequear("★ el revés: al cerrarse una conexión, el mapa se reescribe sin ella",
             estaba and "499" not in json.load(open(config.RELAY_MAPA)))
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
    pruebas_inventario(chequear)
    pruebas_salir_stage(chequear)
    pruebas_lista_servidores(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_nat(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_login(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_personajes(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    shutil.rmtree(config.CUENTAS, ignore_errors=True)
    config.NIVEL_INICIAL = nivel_real
    if saltadas:
        print("\n  (%d pruebas; saltadas las de %s: faltan los XML del juego)"
              % (len(ok), ", ".join(saltadas)))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def pruebas_personajes(chequear):
    """★ (MEDICIONES §50) varios personajes por cuenta: crear (0x1013), la lista en el 0x1012, elegir
    (0x1017) y el piso de nivel 25. Cada cosa con su revés."""
    from servidor.cuentas import nivel
    n = 140
    ASIGNADAS.pop(n, None)
    real = config.NIVEL_INICIAL
    config.NIVEL_INICIAL = 25
    try:
        c = leer(n)
        chequear("cuenta nueva: un personaje, en el lugar 0", len(c["pjs"]) == 1 and c.get("lugar", 0) == 0)
        chequear("★ nivel 25 de piso (EDA_NIVEL_INICIAL): el personaje de siempre ya es nivel 25",
                 nivel(c["exp"]) == 25, nivel(c["exp"]))
        guardar(c)

        def crear(lugar, clase, nick):
            # (el formato MEDIDO: u32 id de la cuenta · u8 CLASE · u8 LUGAR · nombre UTF-16)
            return responder(0x1013, struct.pack("<IBB", n, clase, lugar) + nick.encode("utf-16-le") + b"\0" * 8, n)
        r = crear(2, 2, "Arquera")
        pj = r[0][1][2:]
        chequear("0x1013 → 0x1014 resultado 1 + un personaje de 186 B",
                 r[0][0] == 0x1014 and r[0][1][:2] == b"\1\0" and len(pj) == 186, len(r[0][1]))
        chequear("…en el lugar 2 (+0x52), clase 2 (+0x04), «Arquera» (+0x05), nivel 25 (+0x1F)",
                 pj[0x52] == 2 and pj[0x04] == 2 and pj[0x1F] == 25
                 and pj[0x05:0x05 + 14].decode("utf-16-le") == "Arquera", (pj[0x52], pj[0x04], pj[0x1F]))
        chequear("y queda guardado: la cuenta tiene 2 personajes", len(leer(n)["pjs"]) == 2)
        from servidor.objetos import cuerpo_cuenta
        chequear("el 0x1012 trae los DOS (N3 = 2 en +0x20)", cuerpo_cuenta(leer(n), n)[0x20] == 2)
        for (lugar, clase, nick), que in (((2, 1, "Otro"), "el lugar ya ocupado"),
                                          ((3, 1, "arquera"), "un nombre que ya existe (sin mayúsculas)"),
                                          ((3, 1, "con espacio"), "un nombre con espacio"),
                                          ((3, 3, "Clase3"), "una clase que no existe"),
                                          ((5, 1, "Lugar5"), "el lugar 5 (hay 0–4)")):
            r = crear(lugar, clase, nick)
            chequear("★ el revés: %s → error y nada nuevo" % que,
                     struct.unpack_from("<H", r[0][1])[0] != 1 and len(leer(n)["pjs"]) == 2)
        r = responder(0x1017, struct.pack("<IB", 0, 2), n)
        chequear("0x1017 eligiendo el lugar 2: primero la cuenta otra vez (0x1012) y el 0x1018 con +2 = 0"
                 " (el activo va PRIMERO en la lista)",
                 [x[0] for x in r[:2]] == [0x1012, 0x1018] and r[1][1][2] == 0, r[1][1][2] if len(r) > 1 else r)
        cuerpo12 = r[0][1]
        primero, segundo = cuerpo12[-186 * 2:-186], cuerpo12[-186:]
        chequear("en ese 0x1012 el elegido va en el LUGAR 0 (el cliente se queda con ése) y el que estaba"
                 " ahí, en el lugar del elegido (2)", cuerpo12[0x20] == 2
                 and primero[0x52] == 0 and primero[0x04] == 2 and segundo[0x52] == 2 and segundo[0x04] == 1)
        n1 = struct.unpack_from("<H", cuerpo12, 0x1C)[0]
        regs = [cuerpo12[33 + 21 * k:33 + 21 * (k + 1)] for k in range(n1)]
        casilleros = [x[0xB] for x in regs]
        seriales = [struct.unpack_from("<I", x, 4)[0] for x in regs]
        eq1 = set(struct.unpack_from("<18I", primero, 0x72)) - {0}
        eq2 = set(struct.unpack_from("<18I", segundo, 0x72)) - {0}
        chequear("los dos CON su equipo, y cada serial de equipo está en el inventario (sin repetidos)",
                 eq1 and eq2 and not eq1 & eq2 and (eq1 | eq2) <= set(seriales)
                 and len(seriales) == len(set(seriales)), (len(eq1), len(eq2), n1))
        chequear("…los ítems puestos del que NO está activo van en casilleros escondidos (≥ 200)",
                 all(cas >= 200 for cas, s in zip(casilleros, seriales) if s in eq2)
                 and all(cas < 200 for cas, s in zip(casilleros, seriales) if s in eq1))
        chequear("★ el revés: el 0x1012 de siempre (el de SELECT CHARACTER) deja a cada uno en su lugar",
                 sorted(x[0x52] for x in (cuerpo_cuenta(leer(n), n)[-186 * 2:-186], cuerpo_cuenta(leer(n), n)[-186:]))
                 == [0, 2])
        d = leer(n)
        chequear("…y el activo pasa a ser la Arquera (clase 2, su nombre)",
                 d["clase"] == 2 and d.get("nick") == "Arquera")
        d["exp"] += 7
        guardar(d)
        r = responder(0x1017, struct.pack("<IB", 0, 2), n)
        chequear("★ el revés: elegir el que YA está activo no manda el 0x1012 otra vez", r[0][0] == 0x1018)
        responder(0x1017, struct.pack("<IB", 0, 0), n)
        d = leer(n)
        arquera = next(x for x in d["pjs"] if x.get("lugar") == 2)
        chequear("volviendo al lugar 0: el de siempre (clase 1), y la Arquera conservó lo suyo (+7 EXP)",
                 d["clase"] == 1 and arquera["exp"] == EXPS[24] + 7, arquera.get("exp"))
        crear(4, 1, "Borrable")
        antes = len(leer(n)["pjs"])
        r = responder(0x1015, struct.pack("<IB", n, 4), n)
        chequear("0x1015 borrando el lugar 4 → 0x1016 = u16 1 · u8 4, y la cuenta tiene uno menos",
                 r[0] == (0x1016, struct.pack("<HB", 1, 4), 0) and len(leer(n)["pjs"]) == antes - 1)
        r = responder(0x1015, struct.pack("<IB", n, 4), n)
        chequear("★ el revés: borrar un lugar VACÍO → resultado 0 y nada cambia",
                 struct.unpack_from("<H", r[0][1])[0] == 0 and len(leer(n)["pjs"]) == antes - 1)
        uno = 142
        ASIGNADAS.pop(uno, None)
        guardar(leer(uno))
        r = responder(0x1015, struct.pack("<IB", uno, 0), uno)
        vacia = leer(uno)
        chequear("se puede borrar el ÚLTIMO: la cuenta queda VACÍA (y no reaparece el de siempre al releer)",
                 r[0][1] == struct.pack("<HB", 1, 0) and vacia["pjs"] == [])
        b = cuerpo_cuenta(vacia, uno)
        chequear("…su 0x1012 va sin personajes y sin ítems (N3 = 0, N1 = 0), con el oro de la cuenta",
                 b[0x20] == 0 and struct.unpack_from("<H", b, 0x1C)[0] == 0 and len(b) == 33
                 and struct.unpack_from("<I", b, 0x13)[0] == vacia["plata"], len(b))
        r = responder(0x1013, struct.pack("<IBB", uno, 1, 3) + "Nuevo".encode("utf-16-le") + b"\0" * 4, uno)
        d = leer(uno)
        chequear("…y en la cuenta vacía se crea uno nuevo, que queda como el ÚNICO y activo (su nombre y lugar)",
                 r[0][1][:2] == b"\1\0" and len(d["pjs"]) == 1 and d.get("nick") == "Nuevo"
                 and d.get("lugar") == 3 and d["clase"] == 1, (len(d["pjs"]), d.get("nick")))
        ASIGNADAS.pop(uno, None)
        from servidor.personajes import seriales_unicos
        viejos = [{"lugar": 0, "items": [[1, 1, 10, 1, 1], [26001, 5, 18, 2, 1]], "fichas": {"1": {"niveles": 3}}},
                  {"lugar": 2, "items": [[201, 1, 10, 1, 1], [26001, 5, 18, 2, 1]], "fichas": {"1": {"niveles": 7}}}]
        seriales_unicos(viejos)
        s0, s1 = [it[3] for it in viejos[0]["items"]], [it[3] for it in viejos[1]["items"]]
        chequear("una cuenta vieja con seriales repetidos: el 2.º se renumera (su rango, 30001…) y su ficha"
                 " lo sigue; ★ el revés: el 1.º queda igual",
                 s0 == [1, 2] and s1 == [30001, 30002] and viejos[1]["fichas"] == {"30001": {"niveles": 7}}
                 and viejos[0]["fichas"] == {"1": {"niveles": 3}}, (s0, s1))
        config.NIVEL_INICIAL = 0
        ASIGNADAS[141] = "cuenta_nueva_control"            # (una cuenta que seguro no existe)
        from servidor.cuentas import ruta_cuenta
        if os.path.exists(ruta_cuenta("cuenta_nueva_control")):
            os.remove(ruta_cuenta("cuenta_nueva_control"))
        chequear("★ el revés: sin el piso (0), una cuenta nueva arranca en nivel 1",
                 nivel(leer(141)["exp"]) == 1)
    finally:
        config.NIVEL_INICIAL = real
        ASIGNADAS.pop(n, None)
        ASIGNADAS.pop(141, None)


def pruebas_nat(chequear):
    """★ P2P ENTRE CASAS (MEDICIONES §53, servidor/nat.py): el 0x0607 al relay, el 0x0609 con la
    pública que vio el relay en el 0x3002, y con ella la dirección directa del ANFITRIÓN."""
    from servidor import nat
    from servidor.relay import publica_de
    viejos = (config.P2P_ENTRE_CASAS, config.NAT_MAPA, config.RELAY_IP, config.P2P, config.PUNCH_MAPA)
    config.NAT_MAPA = os.path.join(config.CUENTAS, "nat.json")
    config.PUNCH_MAPA = os.path.join(config.CUENTAS, "punch_nat.json")
    config.RELAY_IP, config.P2P = "203.0.113.9", "directo"
    json.dump({}, open(config.PUNCH_MAPA, "w"))

    def ip_int(t):
        return struct.unpack(">I", bytes(int(x) for x in t.split(".")))[0]
    huella = "12345".encode("utf-16-le").ljust(40, b"\0")
    config.P2P_ENTRE_CASAS = False
    r = responder(0x0604, huella + b"\0" * 4, 950)
    chequear("★ el revés: sin P2P entre casas, el 0x0604 lo contestan las reglas de siempre", r is None)
    config.P2P_ENTRE_CASAS = True
    r = responder(0x0604, huella + b"\0" * 4, 950)
    chequear("con P2P entre casas: 0x0604 → 0x0607 al puerto de punch del relay (y nada más todavía)",
             len(r) == 1 and r[0][0] == 0x0607 and r[0][1] == struct.pack("<IH", ip_int("203.0.113.9"),
                                                                          config.RELAY_BASE))
    json.dump({}, open(config.NAT_MAPA, "w"))
    chequear("sin 0x3002 todavía: el 0x0609 espera", nat.tick([950]) == [])
    # (como el juego: el texto, su 0 final y BASURA que cambia en cada 0x3002 — medido en prueba, §53)
    con_basura = "12345".encode("utf-16-le") + b"\0\0" + bytes.fromhex("908f940040fe1a00f05bf976").ljust(28, b"\0")
    json.dump({con_basura.hex(): ["198.51.100.20", 7544, time.time()],
               ("99999".encode("utf-16-le").ljust(40, b"\0")).hex(): ["192.0.2.7", 1111, time.time()]},
              open(config.NAT_MAPA, "w"))
    chequear("★ el revés: la huella ENTERA (con la basura del final) no está en el 0x0604",
             con_basura not in partida(950)["nat_0604"])
    r = nat.tick([950])
    chequear("con su 0x3002 visto: 0x0609 con SU pública (por el texto de su huella, no la de otro)",
             len(r) == 1 and r[0][:2] == (0x0609, struct.pack("<B3xIH", 1, ip_int("198.51.100.20"), 7544)))
    chequear("…y una sola vez", nat.tick([950]) == [])
    responder(0x0604, ("77777".encode("utf-16-le").ljust(40, b"\0")) + b"\0" * 4, 951)
    r = nat.tick([951], ahora=time.time() + nat.ESPERA + 0.1)
    chequear("★ el revés: sin su 0x3002 a tiempo → el 0x0609 de siempre (127.0.0.1)",
             len(r) == 1 and r[0][1] == nat.VIEJO)
    # el 0x100F trae la pública que le dimos → el anfitrión (sin punch) tiene dirección directa
    b = bytearray(0xE9)
    b[0x7A:0x7A + 34] = "02:BB:00:00:00:01".encode("utf-16-le")
    struct.pack_into("<IHIH", b, 0xDD, ip_int("10.0.0.5"), 57654, ip_int("198.51.100.20"), 7544)
    responder(0x100F, bytes(b), 960)
    b2 = bytearray(b)
    b2[0x7A:0x7A + 34] = "02:BB:00:00:00:02".encode("utf-16-le")
    struct.pack_into("<IHIH", b2, 0xDD, ip_int("192.168.0.9"), 51001, ip_int("192.0.2.80"), 51001)
    responder(0x100F, bytes(b2), 961)
    partida(960)["ip_tcp"], partida(961)["ip_tcp"] = "198.51.100.20", "192.0.2.80"
    chequear("el 0x100F guarda la pública (+0xE3) → publica_de", publica_de(960) == (ip_int("198.51.100.20"), 7544))
    chequear("entre casas, el anfitrión SIN punch: cada uno recibe la PÚBLICA del otro (directo)",
             dir_udp(960, 961) == (ip_int("198.51.100.20"), 7544)
             and dir_udp(961, 960) == (ip_int("192.0.2.80"), 51001))
    config.P2P_ENTRE_CASAS = False
    chequear("★ el revés: sin P2P entre casas, los dos por el relay (lo de siempre)",
             dir_udp(960, 961) == (ip_int("203.0.113.9"), config.RELAY_BASE + 1 + 960))
    config.P2P_ENTRE_CASAS = True
    partida(961)["publica"] = (0x7F000001, 57654)
    chequear("★ el revés: una pública 127.0.0.1 (el 0x0609 viejo) no cuenta → los dos al relay",
             dir_udp(960, 961) == (ip_int("203.0.113.9"), config.RELAY_BASE + 1 + 960))
    (config.P2P_ENTRE_CASAS, config.NAT_MAPA, config.RELAY_IP, config.P2P, config.PUNCH_MAPA) = viejos


def pruebas_lista_servidores(chequear):
    """★ La lista de servidores (0x070B) con los jugadores de verdad."""
    ASIGNADAS.clear()
    r = responder(0x070A, b"\0", 900)
    reg = r[0][1][3:3 + 96]
    nombre = reg[0x03:0x03 + 40].decode("utf-16-le").split("\0")[0]
    chequear("0x070A → 0x070B: 1 server, «%s», 0 jugadores de %d" % (config.NOMBRE_SERVER, config.MAX_JUGADORES),
             r[0][0] == 0x070B and r[0][1][2] == 1 and nombre == config.NOMBRE_SERVER
             and struct.unpack_from("<HH", reg, 0x33) == (config.MAX_JUGADORES, 0) and reg[0x5F] == 1,
             (nombre, struct.unpack_from("<HH", reg, 0x33)))
    ASIGNADAS.update({901: "rui", 902: "kai", 903: "mio"})
    reg = responder(0x070A, b"\0", 900)[0][1][3:3 + 96]
    chequear("★ el revés: con 3 conectados, dice 3 (no un número fijo)",
             struct.unpack_from("<H", reg, 0x35)[0] == 3)
    ASIGNADAS.clear()


def pruebas_salir_stage(chequear):
    """★ (PR #9, Urek-Mazinoo) al salir de la stage (0x1074) se cancelan sus relojes."""
    from servidor.juego import tick
    n = 131
    ASIGNADAS.pop(n, None)
    PARTIDAS.pop(n, None)
    p = partida(n)
    p.update(game_over_en=time.time() - 1, cartas_hasta=time.time() - 1)
    chequear("★ el revés: con los relojes vencidos y SIN salir, el tick manda lo de la partida",
             any(len(x) > 3 and x[3] == n for x in tick([n])))
    p.update(game_over_en=time.time() + 30, cartas_hasta=time.time() + 30)
    r = responder(0x1074, b"\0" * 4, n)
    chequear("0x1074 → 0x1075, y los relojes de esa partida quedan cancelados",
             r[0][0] == 0x1075 and partida(n).get("game_over_en") is None and partida(n).get("cartas_hasta") is None)
    chequear("…así el tick ya no manda nada de esa partida", not tick([n]))
    ASIGNADAS.pop(n, None)
    PARTIDAS.pop(n, None)


def pruebas_inventario(chequear):
    """★ (PR #5) guardar el inventario (0x102D): reemplazar una poción de la barra y que nunca queden dos
    ítems en el mismo casillero."""
    from servidor.objetos import stats_de
    n = 130
    ASIGNADAS.pop(n, None)
    c = leer(n)
    c["items"] = [[26001, 5, 12, 9001, 1], [26002, 7, 20, 9002, 1], [1, 1, 30, 9003, 1]]
    guardar(c)

    def mover(*pares):
        cuerpo = (b"\0" * 8 + struct.pack("<6H", *(list(stats_de(c))[:5] + [0]))
                  + struct.pack("<HHH", len(pares), 0, 0)
                  + b"".join(struct.pack("<IB", s, cas) for s, cas in pares))
        responder(0x102D, cuerpo, n)
        return {it[3]: it[2] for it in leer(n)["items"]}
    pos = mover((9002, 12))
    chequear("poción de la bolsa a la barra (tecla 1): la que estaba vuelve a la bolsa, a su lugar",
             pos[9002] == 12 and pos[9001] == 20, pos)
    pos = mover((9003, 12))
    chequear("★ el revés: un ítem al casillero de OTRO (que no es una poción a la barra) → nadie se mueve",
             pos[9003] == 30 and pos[9002] == 12, pos)
    pos = mover((9003, 200))
    chequear("★ el revés: un casillero que no existe (≥ 168) → no se mueve", pos[9003] == 30, pos)
    from servidor.objetos import pj_cuenta
    c = leer(n)
    nombre_en = lambda pj: pj[0x05:0x05 + 26].decode("utf-16-le").split("\0")[0]   # noqa: E731
    sin = nombre_en(pj_cuenta(c))
    c["nick"] = "Espada"
    chequear("(PR #5) con «nick», el personaje se ve con ese nombre; ★ el revés: sin él, el de la cuenta",
             nombre_en(pj_cuenta(c)) == "Espada" and sin == c["nombre"], (sin, nombre_en(pj_cuenta(c))))
    ASIGNADAS.pop(n, None)


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
        chequear("…y sin claim «nombre», el personaje sigue sin nombre propio (se ve r2b_4242)",
                 not leer(301).get("nick"))
        # ★ el claim «nombre» del pase (el apodo de R2Beat, desde el 12-nov): al personaje sin nombre propio
        chequear("nombre del pase: «Espadachin» pasa, uno de 15 se recorta a 12; ★ el revés: espacio, ñ, "
                 "1 letra, un número o nada → None",
                 porteria.nombre_del_pase({"nombre": "Espadachin"}) == "Espadachin"
                 and porteria.nombre_del_pase({"nombre": "abcdefghijklmno"}) == "abcdefghijkl"
                 and porteria.nombre_del_pase({"nombre": "dos palabras"}) is None
                 and porteria.nombre_del_pase({"nombre": "Muñeca"}) is None
                 and porteria.nombre_del_pase({"nombre": "x"}) is None
                 and porteria.nombre_del_pase({"nombre": 7}) is None and porteria.nombre_del_pase({}) is None)
        con = porteria.canjear(firmar(clave, dict(datos, sub="5151", jti="j-13", nombre="Espadachin")), ahora)
        chequear("★ el revés: el nombre del ticket sólo sale con SU cuenta",
                 porteria.nombre_de("5151", con["ticket"]) == "Espadachin"
                 and porteria.nombre_de("5152", con["ticket"]) is None)
        rr = responder(0x100F, cuerpo_100f("5151", con["ticket"]), 320)
        chequear("login con «nombre»: el personaje de la cuenta nueva se llama así",
                 rr[0][1][:2] == b"\1\0" and leer(320).get("nick") == "Espadachin", leer(320).get("nick"))
        otro = porteria.canjear(firmar(clave, dict(datos, sub="5152", jti="j-14", nombre="espadachin")), ahora)
        responder(0x100F, cuerpo_100f("5152", otro["ticket"]), 321)
        chequear("★ el revés: el mismo nombre (otras mayúsculas) en otra cuenta → no se lo da",
                 leer(321)["nombre"] == "r2b_5152" and not leer(321).get("nick"))
        otra_vez = porteria.canjear(firmar(clave, dict(datos, sub="5151", jti="j-15", nombre="OtroNombre")), ahora)
        responder(0x100F, cuerpo_100f("5151", otra_vez["ticket"]), 322)
        chequear("★ el revés: un personaje que ya tiene nombre no lo cambia por el del pase",
                 leer(322).get("nick") == "Espadachin")
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
