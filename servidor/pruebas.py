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
    from servidor import messenger              # (la conversación y los inventarios de la prueba: en su carpeta)
    messenger.ruta_chat = lambda: os.path.join(config.CUENTAS, "msn_chat.jsonl")
    messenger.ruta_inventario = lambda nombre: os.path.join(config.CUENTAS, "inv_%s.json" % nombre)
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
    oro_antes = leer(99)["plata"]
    r = responder(0x1064, b"\0", 99)
    cmds = [x[0] for x in r]
    tpo = tabla_premios()
    if tpo:
        esc_ = partida(99).get("escenario")
        oro_xml = sum(d_ for t_, d_, _ in tpo.get(esc_, (0, []))[1] if t_ == 0)
        chequear("(Paso 6) al terminar el Stage el oro sube SÓLO lo de StageReward (Type 0: %d), sin 100 + 10 × bajas"
                 % oro_xml, leer(99)["plata"] - oro_antes == oro_xml, leer(99)["plata"] - oro_antes)
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
    r1071 = [x[1] for x in r if x[0] == 0x1071]
    chequear("carta de bronce: dos 0x1071 (la CARA de 27 B + la EXP de 11 B)",
             [len(x) for x in r1071] == [27, 11], [len(x) for x in r1071])
    chequear("carta de bronce: %d − %d puntos" % (puntos, PRECIOS[2]),
             all(struct.unpack_from("<I", x, 7)[0] == max(0, puntos - PRECIOS[2]) for x in r1071))
    chequear("★ 0x1071 forma 0: CARTA 10 en el byte 1, JUGADOR 0 y EXP %d en la cara" % PRECIOS[2],
             r1071[0][:2] == b"\0\x0a" and r1071[0][11 + 4] == 0
             and struct.unpack_from("<I", r1071[0], 11 + 5)[0] == PRECIOS[2], r1071[0].hex())
    chequear("0x1071 forma 1: u8 1 · FILA 2 · JUGADOR 0 · EXP de cartas %d" % PRECIOS[2],
             r1071[1][:3] == b"\1\2\0" and struct.unpack_from("<I", r1071[1], 3)[0] == PRECIOS[2])
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
        chequear("carta %d → se da vuelta (forma 0) · fila %d (cobra %d)" % (
            carta_n, fila_esperada, PRECIOS[fila_esperada]),
                 r[0][1][:2] == bytes([0, carta_n]) and r[1][1][:2] == bytes([1, fila_esperada])
                 and struct.unpack_from("<I", r[1][1], 7)[0] == 1000 - PRECIOS[fila_esperada])
        tp_c = tabla_premios()
        if tp_c:
            it_carta = struct.unpack_from("<H", r[0][1], 11 + 0xD)[0]
            chequear("carta %d: la cara trae un ítem de StageReward 1011 (%d) y entra a la bolsa" % (
                carta_n, it_carta),
                     it_carta in {d for t_, d, _ in tp_c[1011][1] if t_ == 2 and d != NADA}
                     and any(x[0] == it_carta for x in leer(99)["items"]))
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
    for fila_n in (0, 1, 2):                                # el botón «EXP» de la fila (TIPO 1)
        partida(99).update(puntos=1000, exp_cartas=0, cartas_hasta=time.time() + 60, cartas_elegidas=set())
        r = responder(0x1070, bytes([1, fila_n]), 99)
        repetida = responder(0x1070, bytes([1, fila_n]), 99)
        chequear("botón EXP de la fila %d → sólo la forma 1, cobra %d una vez" % (fila_n, PRECIOS[fila_n]),
                 [x[1][:2] for x in r if x[0] == 0x1071] == [bytes([1, fila_n])] and repetida == []
                 and partida(99)["puntos"] == 1000 - PRECIOS[fila_n])
    chequear("★ el revés: TIPO 1 con fila 3, o TIPO 2, no se contestan",
             responder(0x1070, b"\1\3", 99) == [] and responder(0x1070, b"\2\0", 99) == [])
    partida(99).update(puntos=1000, cartas_hasta=time.time() - 1)
    chequear("★ el revés: vencido el tiempo de las cartas, no se cobra",
             responder(0x1070, b"\0\2", 99) == [] and partida(99)["puntos"] == 1000)
    # ★ el cierre por bajas, en cualquier stage (2-1 Normal y 1-4 Fácil)
    from servidor.juego import tick
    from servidor.partida import cerrar_por_bajas
    for esc, espera in ((1021, 8), (1041, 3)):
        total = ESCENARIOS[esc][3]
        SALAS["prueba_bajas"] = {"sala": bytes(0x59), "miembros": [94], "anfitrion": 94}
        partida(94).update(sala="prueba_bajas", escenario=esc, game_over_en=None)
        responder(0x105F, b"\0" * 4, 94)
        for k in range(total - 1):
            responder(0x1061, struct.pack("<H", k) + b"\0" * 6, 94)
        responder(0x1061, struct.pack("<H", 0) + b"\0" * 6, 94)          # repetida: no cuenta
        chequear("%d: %d de %d bajas distintas → sin cierre" % (esc, total - 1, total),
                 partida(94).get("cierre_bajas") is None)
        responder(0x1061, struct.pack("<H", total - 1) + b"\0" * 6, 94)
        c_ = partida(94).get("cierre_bajas")
        chequear("%d: con las %d → cierre programado a los %d s" % (esc, total, espera),
                 c_ is not None and abs(c_ - time.monotonic() - espera) < 1)
        chequear("%d: antes de la espera, tick no cierra" % esc,
                 not [x for x in tick([94]) if x[0] == 0x1073])
        partida(94)["cierre_bajas"] = time.monotonic() - 1
        t = [x for x in tick([94]) if x[3] == 94]
        chequear("%d: vencida la espera, tick → 1073 + 106E + 106F" % esc,
                 [x[0] for x in t] == [0x1073, 0x106E, 0x106F], [hex(x[0]) for x in t])
        chequear("%d: el aviso tardío del cliente no paga dos veces" % esc,
                 responder(0x1064, b"\0", 94) == [] and not [x for x in tick([94]) if x[0] == 0x1073])
    partida(94).update(escenario=1021, game_over_en=None)
    responder(0x105F, b"\0" * 4, 94)
    for k in range(ESCENARIOS[1021][3]):
        responder(0x1061, struct.pack("<H", k) + b"\0" * 6, 94)
    r = responder(0x1064, b"\0", 94)
    chequear("★ el revés: si el cliente avisa a tiempo, el cierre por bajas no se suma",
             [x[0] for x in r] == [0x1073, 0x106E, 0x106F]
             and not [x for x in tick([94]) if x[0] == 0x1073]
             and cerrar_por_bajas(dict(partida(94), cierre_bajas=time.monotonic() - 1), 94) == [])
    # 🧪 el atajo fin_rapido (apagado sin el archivo)
    partida(94).update(inicio=time.time() - 30, resultado_guardado=False, game_over_en=None)
    chequear("sin el archivo fin_rapido, tick no termina la stage",
             not [x for x in tick([94]) if x[0] == 0x1073])
    ruta_fr = os.path.join(config.ESTADO, "fin_rapido")
    open(ruta_fr, "w").write("0")
    chequear("★ el revés: fin_rapido con 0 = apagado", not [x for x in tick([94]) if x[0] == 0x1073])
    open(ruta_fr, "w").write("5")
    try:
        t = [x for x in tick([94]) if x[3] == 94]
        chequear("🧪 con fin_rapido (5 s): tick → 1073 + 106E + 106F",
                 [x[0] for x in t] == [0x1073, 0x106E, 0x106F], [hex(x[0]) for x in t])
        chequear("🧪 fin_rapido: una sola vez", not [x for x in tick([94]) if x[0] == 0x1073])
    finally:
        os.remove(ruta_fr)
    del SALAS["prueba_bajas"]
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
        chequear("(Paso 6) la compra no toca el cash guardado y al cliente va cash = 0 (+6)",
                 d.get("cash") == antes.get("cash") and struct.unpack_from("<I", r[0][1], 6)[0] == 0)
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
        # un ítem en la barra de atajos (casilleros 12–17) tampoco se vende
        d_hot = leer(203)
        inv_hot = inventario(d_hot)
        poc = next((x for x in inv_hot if x[2] >= 18), None)
        if poc:
            poc[2] = 12
            d_hot["items"] = inv_hot
            guardar(d_hot)
            r = responder(0x1041, struct.pack("<II", 0, poc[3]), 203)
            chequear("★ el revés: lo que está en la barra de atajos (12–17) tampoco se vende",
                     r[0][1][:2] == b"\0\0")
            d_hot["items"] = inventario(d3)
            guardar(d_hot)
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
    json.dump({"401": ["200.1.1.1", 40001, 1e12], "402": ["190.2.2.2", 40002, 1e12], "403": ["200.1.1.1", 40003, 1e12],
               "404": ["181.4.4.4", 40004, 1e12]}, open(config.PUNCH_MAPA, "w"))
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
    json.dump({"402": ["190.2.2.2", 40002, 1e12]}, open(config.PUNCH_MAPA, "w"))
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
    json.dump({"401": ["200.1.1.1", 40001, 1e12], "402": ["190.2.2.2", 40002, 1e12], "403": ["200.1.1.1", 40003, 1e12],
               "404": ["181.4.4.4", 40004, 1e12]}, open(config.PUNCH_MAPA, "w"))
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
        # ★ REPAIR EACH, como lo arma el cliente (`0x54A6ED`): u32 · u16 0 · u32 el serial de ESE ítem
        d = leer(203)
        d["durabilidad"] = {str(w): 7500, str(w + 1): 5000}
        plata = d["plata"]
        guardar(d)
        uno = (tt[1][0] - 7500) * tt[1][1]
        r = responder(0x1039, struct.pack("<IHI", 0x186, 0, w), 203)
        chequear("Repair Each (u16 0 + el serial): arregla SÓLO ese ítem y cobra %d" % uno,
                 struct.unpack_from("<HIB", r[0][1]) == (1, plata - uno, 1)
                 and leer(203)["durabilidad"] == {str(w): 10000, str(w + 1): 5000})
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

    # ★ QUICK JOIN y AJUSTES DE SALA (aporte de Hysteria-xyz)
    salas_antes = dict(SALAS)
    SALAS.clear()
    # Quick Join con sala disponible:
    SALAS[55] = {"sala": bytearray(0x59), "anfitrion": 301, "miembros": [301]}
    SALAS[55]["sala"][0x2F] = 3
    r = responder(0x1025, b"", 302)
    chequear("0x1025 (Quick Join) → 0x1026 con resultado 1 y número de sala (55)",
             r == [(0x1026, struct.pack("<HHB", 1, 55, 0), 0)])
    # ★ el revés: sin salas disponibles (o llena) → resultado 0xBB9
    SALAS[55]["sala"][0x2F] = 1
    r = responder(0x1025, b"", 302)
    chequear("★ el revés: sin cupo libre → 0x1026 con error 0xBB9 (sin salas)",
             r == [(0x1026, struct.pack("<HHB", 0xBB9, 0xFFFF, 0), 0)])
    del SALAS[55]
    SALAS.update(salas_antes)

    # 0x104B: actualización de escenario/dificultad a los miembros
    SALAS[55] = {"sala": bytearray(0x59), "anfitrion": 301, "miembros": [301, 302]}
    partida(301)["sala"] = 55
    partida(302)["sala"] = 55
    cuerpo_4b = struct.pack("<HI", 1, 1012)
    r = responder(0x104B, cuerpo_4b, 301)
    chequear("0x104B (ajustes de sala) se retransmite a los otros miembros",
             r == [(0x104B, cuerpo_4b, 0, 302)] and struct.unpack_from("<I", SALAS[55]["sala"], 0x28)[0] == 1012)
    # ★ el revés: sin sala no se procesa
    chequear("★ el revés: 0x104B sin sala → None", responder(0x104B, cuerpo_4b, 999) is None)
    del SALAS[55]

    # ★ COMANDOS DE GM EN EL CHAT (/oro, /cash, /nivel, /item, /ayuda)
    def _chat_payload(texto):
        t = texto.encode("utf-16-le")
        return struct.pack("<BII", 1, 0xFFFFFFFF, 0) + struct.pack("<I", len(t)) + t

    # /oro
    r = responder(0x100D, _chat_payload("/oro 77777"), 203)
    d = leer(203)
    chequear("/oro 77777 actualiza la plata del jugador a 77777",
             d["plata"] == 77777 and r[0][0] == 0x1005 and "77777".encode("utf-16-le") in r[0][1])
    # ★ el revés: /oro sin número devuelve aviso de uso y no cambia el oro
    r = responder(0x100D, _chat_payload("/oro abc"), 203)
    chequear("★ el revés: /oro inválido devuelve aviso y mantiene el oro",
             leer(203)["plata"] == 77777 and "Uso: /oro".encode("utf-16-le") in r[0][1])

    # /cash: deshabilitado (Paso 6: EDA usa sólo oro); el cash guardado NO se toca
    d = leer(203)
    d["cash"] = 1234                                         # (una cuenta vieja con cash)
    guardar(d)
    r = responder(0x100D, _chat_payload("/cash 9999"), 203)
    chequear("(Paso 6) /cash está deshabilitado: avisa y NO cambia el cash guardado (1234)",
             leer(203)["cash"] == 1234 and "no existe".encode("utf-16-le") in r[0][1])
    r = responder(0x1011, b"\1\0\0\0", 203)
    chequear("(Paso 6) 0x1012: cash = 0 al cliente (+0x0F) aunque la cuenta guarde 1234; el oro en +0x13",
             struct.unpack_from("<I", r[0][1], 0x0F)[0] == 0
             and struct.unpack_from("<I", r[0][1], 0x13)[0] == leer(203)["plata"] and leer(203)["cash"] == 1234)

    # /nivel
    r = responder(0x100D, _chat_payload("/nivel 15"), 203)
    d = leer(203)
    chequear("/nivel 15 ajusta la EXP correspondiente a nivel 15",
             nivel(d["exp"]) == 15 and "15".encode("utf-16-le") in r[0][1])

    # /item
    r = responder(0x100D, _chat_payload("/item 21001 10"), 203)
    d = leer(203)
    it = next((x for x in d["items"] if x[0] == 21001), None)
    chequear("/item 21001 10 agrega el ítem al inventario",
             it is not None and it[1] >= 10 and "21001".encode("utf-16-le") in r[0][1])

    # /monedas
    r = responder(0x100D, _chat_payload("/monedas 25"), 203)
    chequear("/monedas 25 actualiza las monedas de resurrección a 25",
             leer(203)["monedas"] == 25 and "25".encode("utf-16-le") in r[0][1])
    r = responder(0x100D, _chat_payload("/monedas abc"), 203)
    chequear("★ el revés: /monedas inválido devuelve aviso y mantiene monedas",
             leer(203)["monedas"] == 25 and "Uso: /monedas".encode("utf-16-le") in r[0][1])

    # /stats
    r = responder(0x100D, _chat_payload("/stats 12 14 16 18 20"), 203)
    chequear("/stats actualiza atributos de combate del personaje",
             leer(203)["stats"] == [12, 14, 16, 18, 20] and "STR 12".encode("utf-16-le") in r[0][1])
    r = responder(0x100D, _chat_payload("/stats"), 203)
    chequear("★ el revés: /stats sin argumentos devuelve aviso de uso",
             "Uso: /stats".encode("utf-16-le") in r[0][1])

    # /limpiar
    items_antes = [list(x) for x in leer(203)["items"]]
    r = responder(0x100D, _chat_payload("/limpiar"), 203)
    chequear("/limpiar limpia la bolsa conservando el equipo puesto",
             all(x[2] < 12 for x in leer(203)["items"]) and "limpiada".encode("utf-16-le") in r[0][1])
    d = leer(203)
    d["items"] = items_antes
    guardar(d)

    # /ayuda y desconocido
    r = responder(0x100D, _chat_payload("/ayuda"), 203)
    chequear("/ayuda responde con la lista de comandos disponibles",
             "Comandos GM:".encode("utf-16-le") in r[0][1])
    r = responder(0x100D, _chat_payload("/noexiste"), 203)
    chequear("★ el revés: comando desconocido avisa sin romper",
             "Comando desconocido".encode("utf-16-le") in r[0][1])

    # ★ el revés: chat normal se difunde a los demás y no ejecuta comandos
    r = responder(0x100D, _chat_payload("Hola mundo"), 203)
    chequear("★ el revés: chat normal lleva tipo 1 y texto original",
             "Hola mundo".encode("utf-16-le") in r[0][1] and r[0][1][2] == 1)

    # ★ 0x105B: sincronización de modelo 3D y equipo en sala de espera
    SALAS[55] = {"sala": bytearray(0x59), "anfitrion": 301, "miembros": [301, 302]}
    partida(301)["sala"] = 55
    partida(302)["sala"] = 55
    r = responder(0x105B, b"", 301)
    chequear("0x105B difunde equipo 3D (633 B) a los compañeros de sala",
             len(r) == 1 and r[0][0] == 0x105B and len(r[0][1]) == 0x279 and r[0][3] == 302)
    chequear("★ el revés: 0x105B sin sala → None", responder(0x105B, b"", 999) is None)
    del SALAS[55]

    # ★ 0x1062: sincronización de vida/maná en cooperativo
    SALAS[55] = {"sala": bytearray(0x59), "anfitrion": 301, "miembros": [301, 302]}
    partida(301)["sala"] = 55
    partida(302)["sala"] = 55
    r = responder(0x1063, b"\x00\x64\x00", 301)
    chequear("0x1063 (daño recibido) difunde 0x1062 (16 B) a los compañeros de equipo",
             len(r) == 1 and r[0][0] == 0x1062 and len(r[0][1]) == 16 and r[0][3] == 302
             and struct.unpack_from("<H", r[0][1], 8)[0] == 100)
    partida(301).pop("sala", None)
    partida(302).pop("sala", None)
    del SALAS[55]
    chequear("★ el revés: 0x1063 con un solo jugador no emite 0x1062",
             len(responder(0x1063, b"\x00\x64\x00", 203)) == 0)

    # ★ 0x1019 / 0x101A: entrar a sala desde la lista del lobby
    sala_raw = bytearray(0x59)
    sala_raw[0x2F] = 2  # max 2 jugadores
    struct.pack_into("<H", sala_raw, 0x28, 1011)
    struct.pack_into("<H", sala_raw, 0x2C, 1)
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 301, "miembros": [301]}
    r = responder(0x1019, struct.pack("<IB", 55, 0), 302)
    chequear("0x1019 con cupo disponible responde 0x101A (9 B) con resultado 1",
             len(r) == 1 and r[0][0] == 0x101A and len(r[0][1]) == 9
             and struct.unpack_from("<HBH HH", r[0][1]) == (1, 0, 55, 1011, 1))
    chequear("★ el revés: 0x1019 a sala inexistente responde error 0x9C5",
             responder(0x1019, struct.pack("<IB", 999, 0), 302)[0][1][:2] == b"\xC5\x09")
    SALAS[55]["miembros"] = [301, 302]
    chequear("★ el revés: 0x1019 a sala llena responde error 0x9C5",
             responder(0x1019, struct.pack("<IB", 55, 0), 303)[0][1][:2] == b"\xC5\x09")
    SALAS[55]["jugando"] = True
    chequear("★ el revés: 0x1019 a sala en partida responde error 0x9C6",
             responder(0x1019, struct.pack("<IB", 55, 0), 303)[0][1][:2] == b"\xC6\x09")
    del SALAS[55]

    # ★ 0x101F: entrar_sala inicializa escenario para invitados y rechaza en juego
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 301, "miembros": [301]}
    partida(302).pop("escenario", None)
    r = responder(0x101F, b"\0\0\0\0\x37\x00" + bytes(20), 302)
    chequear("0x101F inicializa escenario de la sala en la partida del invitado",
             partida(302).get("escenario") == 1011 and 302 in SALAS[55]["miembros"])
    # no duplicar miembro si llama de nuevo
    responder(0x101F, b"\0\0\0\0\x37\x00" + bytes(20), 302)
    chequear("★ el revés: 0x101F repetido no duplica el miembro en la lista",
             SALAS[55]["miembros"].count(302) == 1)
    SALAS[55]["jugando"] = True
    chequear("★ el revés: 0x101F a sala en juego rechaza con resultado 0",
             responder(0x101F, b"\0\0\0\0\x37\x00" + bytes(20), 303)[0][1][:2] == b"\0\0")
    del SALAS[55]

    # ★ cerrada(conexion): transferencia de anfitrión y limpieza de salas zombies
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 301, "miembros": [301, 302]}
    cerrada(301)
    chequear("cerrada(anfitrion) transfiere el anfitrión al siguiente miembro",
             55 in SALAS and SALAS[55]["anfitrion"] == 302 and SALAS[55]["miembros"] == [302])
    cerrada(302)
    chequear("cerrada(ultimo_miembro) elimina la sala y evita salas zombies",
             55 not in SALAS)

    # ★ 0x104E / 0x104F / 0x1050: F9 largada y error
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 301, "miembros": [301, 302]}
    partida(301)["sala"] = 55
    partida(302)["sala"] = 55
    responder(0x1047, b"\1\1", 302)                    # (Punto 3: con varios, el invitado listo antes)
    r = responder(0x104E, b"", 301)
    chequear("0x104E como anfitrión emite 0x104F de inicio de partida",
             any(x[0] == 0x104F for x in r))
    r = responder(0x104E, b"", 302)
    chequear("★ el revés: 0x104E por no-anfitrión responde error 0x1050 (0x138A)",
             len(r) == 1 and r[0][0] == 0x1050 and struct.unpack_from("<H", r[0][1])[0] == 0x138A)
    partida(301).pop("sala", None)
    partida(302).pop("sala", None)
    del SALAS[55]

    # ★ 0x1055 / 0x1056: consulta de estado de sala en lobby
    r = responder(0x1055, b"", 203)
    chequear("0x1055 responde 0x1056 con 82 bytes de estructura",
             len(r) == 1 and r[0][0] == 0x1056 and len(r[0][1]) == 82)

    # ★ 0x1067 / 0x1066: interacción con objetos y cofres
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 301, "miembros": [301, 302]}
    partida(301)["sala"] = 55
    partida(302)["sala"] = 55
    r = responder(0x1067, struct.pack("<I", 777), 301)
    chequear("0x1067 difunde 0x1066 (6 B) de objeto activado a todos los miembros",
             len(r) == 2 and r[0][0] == 0x1066 and len(r[0][1]) == 6
             and struct.unpack_from("<BIB", r[0][1]) == (0, 777, 1))
    partida(301).pop("sala", None)
    partida(302).pop("sala", None)
    del SALAS[55]
    chequear("★ el revés: 0x1067 sin sala no emite eventos", len(responder(0x1067, struct.pack("<I", 777), 203)) == 0)

    # ★ 0x105C / 0x105D: eventos de guion Lua
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 301, "miembros": [301, 302]}
    partida(301)["sala"] = 55
    partida(302)["sala"] = 55
    r = responder(0x105C, b"\x01\x02\x03\x04", 301)
    chequear("0x105C difunde 0x105D a los compañeros de equipo",
             len(r) == 1 and r[0][0] == 0x105D and r[0][1] == b"\x01\x02\x03\x04" and r[0][3] == 302)
    partida(301).pop("sala", None)
    partida(302).pop("sala", None)
    del SALAS[55]
    chequear("★ el revés: 0x105C con jugador solitario no difunde",
             len(responder(0x105C, b"\x01\x02\x03\x04", 203)) == 0)

    # ★ entrar_lobby transfiere sala o saca limpiamente
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 301, "miembros": [301, 302]}
    partida(301)["sala"] = 55
    partida(302)["sala"] = 55
    r = responder(0x1017, struct.pack("<IB", 0, 0), 301)
    chequear("entrar_lobby como anfitrión transfiere la sala al invitado con aviso 0x1058",
             55 in SALAS and SALAS[55]["anfitrion"] == 302 and any(x[0] == 0x1058 and x[3] == 302 for x in r))
    r = responder(0x1017, struct.pack("<IB", 0, 0), 302)
    chequear("entrar_lobby como invitado saca de la sala y elimina la sala vacía",
             55 not in SALAS)

    # ★ cambiar_sala, actualizar_ajustes_sala y ciclo s["jugando"]
    SALAS[55] = {"sala": bytearray(sala_raw), "anfitrion": 301, "miembros": [301]}
    partida(301)["sala"] = 55
    nuevo_tit = "SalaPro".encode("utf-16-le")
    responder(0x1049, struct.pack("<BH", 0, 1) + nuevo_tit, 301)
    chequear("cambiar_sala tipo 1 actualiza los bytes del título en s['sala']",
             SALAS[55]["sala"][6:6 + len(nuevo_tit)] == nuevo_tit)
    SALAS[55]["miembros"] = [301, 302]
    partida(302)["sala"] = 55
    responder(0x104B, struct.pack("<HI", 1, 1012), 301)
    chequear("actualizar_ajustes_sala tipo 1 sincroniza escenario en todos los miembros",
             partida(301).get("escenario") == 1012 and partida(302).get("escenario") == 1012)
    responder(0x1047, b"\1\1", 302)                    # (Punto 3: con varios, el invitado listo antes)
    responder(0x104E, b"", 301)
    chequear("largar marca s['jugando'] = True", SALAS[55].get("jugando") is True)
    r = responder(0x104E, b"", 301)
    chequear("★ el revés: segundo 0x104E con partida en curso rechaza con 0x1050",
             len(r) == 1 and r[0][0] == 0x1050 and struct.unpack_from("<H", r[0][1])[0] == 0x138A)
    responder(0x1074, b"\x00", 301)
    chequear("★ (Punto 3) salir_de_stage con 302 todavía jugando: la sala sigue «jugando» (no se puede entrar)",
             SALAS[55].get("jugando") is True and SALAS[55]["miembros"] == [302])
    responder(0x1074, b"\x00", 302)
    chequear("salir de la stage el último: la sala ya no queda (ni «jugando» ni fantasma)", 55 not in SALAS)
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 302, "miembros": [302]}
    partida(301).pop("sala", None)
    partida(302).pop("sala", None)
    del SALAS[55]

    # ★ usar_moneda en cooperativo difunde a los compañeros
    SALAS[55] = {"sala": bytes(sala_raw), "anfitrion": 301, "miembros": [301, 302]}
    partida(301)["sala"] = 55
    partida(302)["sala"] = 55
    d_rev = leer(301)
    d_rev["monedas"] = 3
    guardar(d_rev)
    r = responder(0x106A, b"\x00\x01\xFF", 301)
    chequear("usar_moneda en coop difunde 0x106B modo 2 ('revivió otro') al compañero",
             any(x[0] == 0x106B and x[1][2] == 2 and x[3] == 302 for x in r))
    partida(301).pop("sala", None)
    partida(302).pop("sala", None)
    del SALAS[55]

    # ★ vender stack de consumibles paga precio * cantidad
    d_v = leer(203)
    inv_v = inventario(d_v)
    s_poc = serial_nuevo(inv_v)
    inv_v += [[26001, 5, libre_en_bolsa(inv_v), s_poc, 1]]
    d_v["items"] = inv_v
    oro_antes = d_v["plata"]
    guardar(d_v)
    precio_u = precios_venta().get(26001, 0)
    responder(0x1041, struct.pack("<II", 0, s_poc), 203)
    d_despues = leer(203)
    chequear("vender stack de 5 pociones paga 5 * precio unitario",
             d_despues["plata"] == oro_antes + precio_u * 5)

    # ★ dar_premio con inventario lleno no lanza StopIteration
    c_llena = {"items": [[1, 1, cas, 1000 + i, 1] for i, cas in enumerate(range(18, 168))],
               "plata": 0, "exp": 0}
    try:
        dar_premio(c_llena, 1011)
        premio_ok = True
    except StopIteration:
        premio_ok = False
    chequear("dar_premio con bolsa llena (150 casilleros) no crashea con StopIteration", premio_ok)

    # ★ 0x1060 / 0x106D: sincronización de temporizador de stage
    r = responder(0x1060, struct.pack("<I", 12345), 203)
    chequear("0x1060 responde con tick de 4 bytes", len(r) == 1 and r[0][0] == 0x1060 and len(r[0][1]) == 4)
    r = responder(0x106D, bytes(16), 203)
    chequear("0x106D responde con temporizador de 16 bytes", len(r) == 1 and r[0][0] == 0x106D and len(r[0][1]) == 16)

    # ★ 0x102F / 0x1030: asignación de puntos de atributos (stats)
    d = leer(203)
    d["stats"] = [5, 5, 5, 5, 5]
    guardar(d)
    libres = stats_de(leer(203))[5]
    r = responder(0x102F, struct.pack("<I6H", 203, 5, 5, 5, 5, 5, 0), 203)
    chequear("0x102F sin cambios guarda y responde 0x1030 resultado 1",
             len(r) == 1 and r[0][0] == 0x1030 and struct.unpack_from("<H", r[0][1])[0] == 1)
    # revés: gastar más de los puntos libres disponibles
    r = responder(0x102F, struct.pack("<I6H", 203, 50, 50, 50, 50, 50, 180), 203)
    chequear("★ el revés: 0x102F con puntos excesivos responde resultado 0",
             len(r) == 1 and r[0][0] == 0x1030 and struct.unpack_from("<H", r[0][1])[0] == 0)

    # ★ 0x1031 / 0x1032: habilidades
    r = responder(0x1031, struct.pack("<III", 203, 1, 1), 203)
    chequear("0x1031 responde 0x1032 con 94 bytes y resultado 1",
             len(r) == 1 and r[0][0] == 0x1032 and len(r[0][1]) == 94
             and struct.unpack_from("<H", r[0][1])[0] == 1)

    # ★ 0x060C / 0x060B y 0x3002 / 0x3003: NAT Broker
    r = responder(0x060C, b"", 203)
    chequear("0x060C responde 0x060B con 6 bytes de Broker IP/Puerto",
             len(r) == 1 and r[0][0] == 0x060B and len(r[0][1]) == 6)
    r = responder(0x3002, b"", 203)
    chequear("0x3002 responde 0x3003 con 1 byte de clasificación NAT",
             len(r) == 1 and r[0][0] == 0x3003 and r[0][1] == b"\x01")
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
    pruebas_ready(chequear)
    pruebas_salida_stage(chequear)
    pruebas_lista_servidores(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_nat(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_entre_casas(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    SALAS.clear()
    pruebas_carga_sin_cortes(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_messenger(chequear)
    pruebas_messenger_cuentas_reales(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_login(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_personajes(chequear)
    pruebas_cazadora(chequear)
    pruebas_150_variantes(chequear)
    pruebas_multijugador(chequear)
    PARTIDAS.clear()
    ASIGNADAS.clear()
    pruebas_panel(chequear)
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
        r_re = crear(4, 1, "Recreado")
        chequear("borrar lugar 4 permite recrear en ese casillero inmediatamente (memoria c sincronizada)",
                 r_re[0][0] == 0x1014 and r_re[0][1][:2] == b"\1\0")
        responder(0x1015, struct.pack("<IB", n, 4), n)
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


def pruebas_cazadora(chequear):
    """★ (20-nov, Paso 4) La CAZADORA (Hunter, clase 2) recién creada, contra los datos del cliente: su set
    de grado 1 es de SU clase (USECLASS 2) y lo puede equipar a su nivel; sus habilidades son de su clase (o de
    todas) y alcanzan a su nivel; F1–F8 = sus activas de arma 0. Lo mismo para el Warrior (control)."""
    from servidor.personajes import personaje_nuevo
    try:
        t = open(config.TIPOS_XML, "rb").read()
        x = open(config.HABILIDADES_XML, "rb").read()
    except OSError:
        print("  (sin ItemTypeList.xml / Skill.xml: se saltea la prueba de la Cazadora)")
        return
    tipos = {}
    for m in re.finditer(rb"<ITEMTYPE ([^>]*)>", t):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', m.group(1)))
        tipos[int(v[b"ID"])] = (int(v[b"USECLASS"]), int(v[b"LEVEL_RESTRICT"]))
    habs = {}
    for clase_xml, a in re.findall(rb"<(ACTIVE|PASSIVE)_SKILL ([^>]*)>", x):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', a))
        habs[(clase_xml == b"ACTIVE", int(v[b"ID"]))] = (clase_xml == b"ACTIVE", int(v[b"CLASS"]),
                                                          int(v.get(b"WEAPON", b"9")), int(v[b"ACQUIRE_LEVEL"]))
    for clase, nombre in ((2, "Cazadora"), (1, "Warrior")):
        pj = personaje_nuevo(clase, 25, "prueba", 0)
        niv = nivel(pj["exp"])
        equipo_ = [it for it in pj["items"] if es_equipo(it[0])]
        chequear("%s: nivel 25 y 8 piezas de equipo puestas (casilleros 0–11)" % nombre,
                 niv == 25 and len(equipo_) == 8 and all(it[2] < 12 for it in equipo_))
        chequear("%s: todo su equipo es de SU clase y lo puede usar a su nivel" % nombre,
                 all(it[0] in tipos and tipos[it[0]][0] == clase and tipos[it[0]][1] <= niv for it in equipo_),
                 [(it[0], tipos.get(it[0])) for it in equipo_])
        ids = [(h[1] == 1, h[2]) for h in pj["habilidades"]]           # (activas e ID: las pasivas repiten IDs)
        propias = [i for i, h in habs.items() if h[1] in (clase, 65535) and h[3] <= niv]
        chequear("%s: tiene TODAS las habilidades de su clase (y comunes) de su nivel, ninguna ajena" % nombre,
                 sorted(ids) == sorted(propias) and all(habs[i][1] in (clase, 65535) for i in ids))
        atajos = sorted((h[4], (h[1] == 1, h[2])) for h in pj["habilidades"] if h[4])
        chequear("%s: F1–F8 = sus activas de arma 0 (1..8 sin repetir)" % nombre,
                 [a for a, _ in atajos] == list(range(1, len(atajos) + 1)) and 0 < len(atajos) <= 8
                 and all(habs[i][0] and habs[i][2] == 0 and habs[i][1] == clase for _, i in atajos), atajos)
    chequear("★ el revés: el set de la Cazadora NO es del Warrior (201 ≠ 1)",
             tipos.get(201, (0,))[0] == 2 and tipos.get(1, (0,))[0] == 1)


def pruebas_150_variantes(chequear):
    """★ (20-nov) Las 50 stages × Fácil/Normal/Difícil (150 variantes) contra los datos del cliente, para que el
    barrido en el juego sea lo mínimo: catálogo (bajas y EXP), premio de StageReward.xml con ítems que existen en
    ItemTypeList.xml, sólo ORO (Paso 6: el oro del premio es el Type 0, el cash no se toca) y la carta."""
    from servidor.partida import premio_de_carta
    tp = tabla_premios()
    try:                                                     # (todos los tipos: equipo, consumibles, libros…)
        tipos = {int(i) for i in re.findall(rb'<ITEMTYPE ID="(\d+)"', open(config.TIPOS_XML, "rb").read())}
    except OSError:
        tipos = set()
    if not tp or not tipos:
        print("  (sin StageReward.xml / ItemTypeList.xml: se saltea la prueba de las 150 variantes)")
        return
    malos_cat, sin_premio, items_malos, oro_mal, carta_mal, premio_malo = [], [], [], [], [], []
    for esc, (rp, kp, te, mc) in sorted(ESCENARIOS.items()):
        if mc <= 0 or te <= 0:
            malos_cat.append(esc)
        if esc not in tp:
            sin_premio.append(esc)
            continue
        lista = tp[esc][1]
        items_malos += [(esc, d) for t_, d, _ in lista if t_ == 2 and d != NADA and d not in tipos]
        c = {"items": [], "plata": 0, "exp": 0, "cash": 777}
        dar_premio(c, esc)
        premio_malo += [(esc, it[0]) for it in c["items"] if it[0] not in tipos]
        if c["plata"] != sum(d for t_, d, _ in lista if t_ == 0) or c["cash"] != 777:
            oro_mal.append(esc)
        x = premio_de_carta(esc)
        if x is not None and (x[0] not in tipos or x[0] == NADA):
            carta_mal.append((esc, x))
    chequear("150 variantes en el catálogo (escenarios.json)", len(ESCENARIOS) == 150, len(ESCENARIOS))
    chequear("todas con bajas (MONSTER_CNT > 0) y EXP total > 0", not malos_cat, malos_cat[:10])
    chequear("todas con su premio en StageReward.xml", not sin_premio, sin_premio[:10])
    chequear("los ítems de StageReward.xml que NO existen en el cliente están sólo en variantes Normal",
             bool(items_malos) and all(e % 10 == 2 for e, _ in items_malos),
             (sorted({d for _, d in items_malos}), len(items_malos), sorted({e for e, _ in items_malos})[:5]))
    chequear("★ el revés: ninguna de las 150 variantes pone en la bolsa un ítem que el cliente no conoce",
             not premio_malo, premio_malo[:10])
    c = {"items": [], "plata": 0, "exp": 0}
    nuevos = dar_premio(c, 1032)
    chequear("★ el revés: el premio de 1032 NO pone el 26004 (desconocido para el cliente) en la bolsa",
             26004 not in [it[0] for it in nuevos] and 26004 not in [it[0] for it in c["items"]])
    chequear("(Paso 6) el premio da sólo ORO (= Σ Type 0) y no toca el cash", not oro_mal, oro_mal[:10])
    chequear("la carta de cada stage es un ítem que existe (o nada)", not carta_mal, carta_mal[:10])


def pruebas_multijugador(chequear):
    """★ (20-nov) MULTIJUGADOR: la largada con varios (0x105F → 0x105E), sin nadie cargando para siempre, sin
    largadas repetidas, de a uno entre hilos; y lo que sale por la red sin que un jugador frene a otro."""
    import threading
    from servidor import partida as mod_partida
    from servidor.juego import tick

    def sala_cargando(num, miembros):
        SALAS[num] = {"sala": bytes(0x59), "anfitrion": miembros[0], "miembros": list(miembros),
                      "numeros": {m: i for i, m in enumerate(miembros)}, "listos": set()}
        for m in miembros:
            partida(m)["sala"] = num
        for m in miembros[1:]:
            responder(0x1047, bytes([SALAS[num]["numeros"][m], 1]), m)
        r = responder(0x104E, b"", miembros[0])
        return [x[3] for x in r if x[0] == 0x104F]

    def largadas(r):
        return sorted(x[3] if len(x) > 3 else None for x in r if x[0] == 0x105E)

    def limpiar(num, miembros):
        SALAS.pop(num, None)
        for m in miembros:
            partida(m).pop("sala", None)

    # 1 · los dos cargan: UNA largada a cada uno, con el último 0x105F
    A, B, C = 501, 502, 503
    chequear("multi: F9 con dos → 0x104F a los dos", sorted(sala_cargando(60, [A, B])) == [A, B])
    r1 = responder(0x105F, b"\0" * 4, A)
    r2 = responder(0x105F, b"\0" * 4, B)
    chequear("multi: el 1.º que carga espera (sin 0x105E)", largadas(r1) == [], r1)
    chequear("multi: el último que carga → 0x105E a los dos, una vez", largadas(r2) == [A, B], largadas(r2))
    r3 = responder(0x105F, b"\0" * 4, A)
    chequear("★ el revés: un 0x105F repetido después de la largada larga SÓLO a ese (antes: a todos otra vez)",
             largadas(r3) == [None], largadas(r3))
    limpiar(60, [A, B])

    # 2 · uno se va mientras el otro ya cargó: antes el que cargó quedaba en la pantalla de carga para siempre
    sala_cargando(61, [A, B])
    chequear("multi: A cargó y espera a B", largadas(responder(0x105F, b"\0" * 4, A)) == [])
    r = responder(0x1045, b"", B)                       # (B sale: Leave Room)
    chequear("★ multi: B se va durante la carga → A larga (0x105E a A)", largadas(r) == [A], largadas(r))
    limpiar(61, [A, B])

    # 3 · al que se le cortó el juego durante la carga (cerrada): A larga con el próximo tick
    sala_cargando(62, [A, B])
    responder(0x105F, b"\0" * 4, A)
    cerrada(B)
    r = tick([A])
    chequear("★ multi: a B se le cortó el juego durante la carga → A larga con el tick", largadas(r) == [A], largadas(r))
    limpiar(62, [A, B])

    # 4 · uno que no termina de cargar nunca: a los ESPERA_CARGA s larga el que cargó; el tarde, solo
    sala_cargando(63, [A, B, C])
    responder(0x105F, b"\0" * 4, A)
    responder(0x105F, b"\0" * 4, B)
    r = tick([A, B, C])
    chequear("★ el revés: antes del plazo NO se larga sin C", largadas(r) == [], largadas(r))
    SALAS[63]["carga_desde"] -= mod_partida.ESPERA_CARGA + 1
    r = tick([A, B, C])
    chequear("★ multi: C no termina de cargar → a los %g s largan A y B" % mod_partida.ESPERA_CARGA,
             largadas(r) == [A, B], largadas(r))
    chequear("multi: y el tick siguiente no larga otra vez", largadas(tick([A, B, C])) == [])
    r = responder(0x105F, b"\0" * 4, C)
    chequear("multi: C carga tarde → larga SÓLO C", largadas(r) == [None], largadas(r))
    limpiar(63, [A, B, C])

    # 5 · la próxima stage de la misma sala vuelve a esperar a todos
    sala_cargando(64, [A, B])
    responder(0x105F, b"\0" * 4, A)
    responder(0x105F, b"\0" * 4, B)
    mod_partida.termino_su_stage(SALAS[64], A)
    mod_partida.termino_su_stage(SALAS[64], B)
    chequear("multi: al terminar la stage se olvida la largada", "largada" not in SALAS[64] and not SALAS[64]["jugando"])
    responder(0x1047, b"\1\1", B)
    responder(0x104E, b"", A)
    chequear("★ el revés: en la 2.ª stage el 1.º que carga vuelve a esperar",
             largadas(responder(0x105F, b"\0" * 4, A)) == [])
    limpiar(64, [A, B])

    # 6 · de a uno entre hilos: los dos 0x105F en el MISMO instante (medido 18-nov 10:17:49, 11:54:47…)
    malas = 0
    for i in range(150):
        sala_cargando(65, [A, B])
        salidas, puerta = [], threading.Barrier(2)

        def cargar(m):
            puerta.wait()
            salidas.extend(responder(0x105F, b"\0" * 4, m))
        hs = [threading.Thread(target=cargar, args=(m,)) for m in (A, B)]
        [h.start() for h in hs]
        [h.join() for h in hs]
        malas += largadas(salidas) != [A, B]
        limpiar(65, [A, B])
    chequear("★ multi: 150 veces los dos 0x105F a la vez desde dos hilos → exactamente una largada a cada uno",
             malas == 0, "%d mal" % malas)

    # 7 · lo de la stage sólo a los que SIGUEN en ella (Punto 3 lo midió con el 0x105D: fuera de la stage cierra
    #     el juego); antes 0x105D / 0x1060 / 0x1062 / 0x1066 / 0x106D iban a todos los de la sala
    sala_cargando(66, [A, B])
    cuerpos = {0x105D: b"\1" * 8, 0x1060: b"\0" * 4, 0x1062: bytes(16), 0x1066: bytes(6), 0x106D: bytes(16),
               0x105C: b"\1" * 8, 0x1063: b"\0\x64\0"}
    ambos = all(any(len(x) > 3 and x[3] == B for x in responder(k, v, A)) for k, v in cuerpos.items())
    chequear("multi: con los dos en la stage, lo de A le llega a B (0x105C/D, 1060, 1062/3, 1066, 106D)", ambos)
    SALAS[66]["en_stage"].discard(B)                     # (B terminó: está en las cartas / volvió a la sala)
    fuera = [hex(k) for k, v in cuerpos.items() if any(len(x) > 3 and x[3] == B for x in responder(k, v, A))]
    chequear("★ multi: B ya salió de la stage → no le llega NADA de la stage de A (antes: 0x105D/1060/1062/1066/106D)",
             not fuera, fuera)
    limpiar(66, [A, B])
    pruebas_estres(chequear)
    pruebas_red_cola(chequear)


def pruebas_estres(chequear):
    """★ (20-nov) Sin interbloqueos ni estado roto con el candado: 6 jugadores en 6 hilos hacen al azar lo que
    hace la gente (crear, entrar, listo, F9, cargar, salir, cortarse) mientras el reloj corre, ~1,5 s."""
    import random
    import threading
    from servidor.juego import tick
    jug = list(range(701, 707))
    errores, hechos, fin = [], [0], time.monotonic() + 1.5
    sala_base = bytearray(0x59)
    struct.pack_into("<I", sala_base, 0x28, 1011)
    sala_base[0x2F] = 3

    def jugar(n):
        rnd = random.Random(n)
        try:
            while time.monotonic() < fin:
                op = rnd.randrange(8)
                if op == 0:
                    responder(0x101D, bytes(4) + bytes(sala_base), n)
                elif op == 1 and SALAS:
                    num = rnd.choice(list(SALAS.keys()) or [0])
                    responder(0x101F, struct.pack("<IH", 0, num if isinstance(num, int) else 0) + bytes(20), n)
                elif op == 2:
                    s = SALAS.get(partida(n).get("sala"))
                    if s and n in s["miembros"]:
                        responder(0x1047, bytes([s.get("numeros", {}).get(n, 0), 1]), n)
                elif op == 3:
                    responder(0x104E, b"", n)
                elif op == 4:
                    responder(0x105F, bytes(4), n)
                elif op == 5:
                    responder(0x1045, b"", n)
                elif op == 6 and rnd.random() < 0.2:
                    cerrada(n)
                else:
                    responder(0x105C, b"\1" * 8, n)
                hechos[0] += 1
        except Exception as e:                              # noqa: BLE001
            errores.append(repr(e))

    def reloj():
        try:
            while time.monotonic() < fin:
                tick(jug)
                time.sleep(0.01)
        except Exception as e:                              # noqa: BLE001
            errores.append("tick: " + repr(e))
    hs = [threading.Thread(target=jugar, args=(n,), daemon=True) for n in jug] + [threading.Thread(target=reloj, daemon=True)]
    [h.start() for h in hs]
    [h.join(10) for h in hs]
    colgados = [h for h in hs if h.is_alive()]
    chequear("★ estrés: 6 jugadores + el reloj en 7 hilos, sin interbloqueos (todos terminan)", not colgados,
             "%d operaciones" % hechos[0])
    chequear("estrés: ninguna excepción", not errores, errores[:3])
    malos = [(k, m) for k, s in SALAS.items() for m in s["miembros"] if partida(m).get("sala") != k]
    dobles = [k for k, s in SALAS.items() if len(set(s["miembros"])) != len(s["miembros"]) or not s["miembros"]]
    chequear("estrés: cada miembro apunta a su sala, sin repetidos ni salas vacías", not malos and not dobles,
             (malos[:3], dobles[:3]))
    for n in jug:
        cerrada(n)


def pruebas_red_cola(chequear):
    """★ (20-nov) servidor/red.py: lo que sale va por la cola de cada conexión. Un jugador que no lee no frena
    al que le manda, y un envío cortado a mitad de paquete corta la conexión (no sigue con el flujo roto)."""
    import socket
    import threading
    from servidor import red
    import paquete_broker as P
    clave, campo2 = bytes(range(16)), P.CAMPO_2
    red.log = lambda m: None                                # (silencio)

    # a) normal: todo llega, en orden y entero
    a, b = socket.socketpair()
    con = {"cli": a, "clave": clave, "campo2": campo2, "lock": threading.Lock(), "cola": __import__("queue").Queue()}
    red.CONEXIONES[9001] = con
    threading.Thread(target=red.escritor, args=(9001, con), daemon=True).start()
    esperado = b"".join(P.armar(P.mensaje(0x2000 + i, bytes([i]) * (i * 7)), clave, campo2) for i in range(40))
    for i in range(40):
        red.enviar_a(9001, 0x2000 + i, bytes([i]) * (i * 7))
    b.settimeout(3)
    llegado = b""
    while len(llegado) < len(esperado):
        d = b.recv(65536)
        if not d:
            break
        llegado += d
    chequear("red: 40 mensajes por la cola llegan enteros y en orden", llegado == esperado,
             "%d/%d B" % (len(llegado), len(esperado)))
    con["cola"].put(None)
    red.CONEXIONES.pop(9001, None)
    a.close()
    b.close()

    # b) el otro NO lee: mandar no espera, y la conexión se corta limpia (antes: hasta 5 s por mensaje)
    a, b = socket.socketpair()
    a.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    a.settimeout(0.5)
    con = {"cli": a, "clave": clave, "campo2": campo2, "lock": threading.Lock(), "cola": __import__("queue").Queue()}
    red.CONEXIONES[9002] = con
    threading.Thread(target=red.escritor, args=(9002, con), daemon=True).start()
    t0 = time.monotonic()
    for i in range(300):
        red.enviar_a(9002, 0x2100, bytes(1000))
    tarda = time.monotonic() - t0
    chequear("★ red: 300 mensajes a uno que no lee NO frenan al que manda", tarda < 0.5, "%.3f s" % tarda)
    fin = time.monotonic() + 5
    while not con.get("cortada") and time.monotonic() < fin:
        time.sleep(0.05)
    chequear("★ red: el envío que no sale (timeout a mitad de paquete) corta la conexión, no sigue con el flujo roto",
             con.get("cortada") is True)
    red.CONEXIONES.pop(9002, None)
    a.close()
    b.close()


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



def pruebas_entre_casas(chequear):
    """★ (21-nov) Lo de la prueba entre dos casas del server de prueba (05:35 UTC): punch.json va por número de
    conexión, los números se reusan, y al invitado se le dio para el anfitrión (conexión 1) el puerto 19745 de una
    sesión de las 04:26 — el de esta era el 18113. Y el modo «auto»: el mismo camino en los dos sentidos."""
    from servidor.relay import estable, punch_de, publica_de, ruta
    from servidor.salas import reanunciar
    viejos = (config.P2P_ENTRE_CASAS, config.RELAY_IP, config.P2P, config.PUNCH_MAPA)
    config.PUNCH_MAPA = os.path.join(config.CUENTAS, "punch_casas.json")
    config.RELAY_IP, config.P2P, config.P2P_ENTRE_CASAS = "203.0.113.9", "directo", True

    def ip_int(t):
        return struct.unpack(">I", bytes(int(x) for x in t.split(".")))[0]

    def entra(n, mac, privada, publica, ip_tcp):
        b = bytearray(0xE9)
        b[0x7A:0x7A + 34] = mac.encode("utf-16-le")[:34].ljust(34, b"\0")
        struct.pack_into("<IHIH", b, 0xDD, ip_int(privada[0]), privada[1], ip_int(publica[0]), publica[1])
        responder(0x100F, bytes(b), n)
        partida(n)["ip_tcp"] = ip_tcp
    ahora = time.time()
    # (las IP son de los rangos de documentación del RFC 5737: no son de nadie)
    entra(970, "02:CC:00:00:00:01", ("192.168.1.48", 57654), ("198.51.100.26", 18113), "198.51.100.26")
    entra(971, "02:CC:00:00:00:02", ("192.168.0.20", 57654), ("203.0.113.77", 40500), "203.0.113.77")
    partida(970)["desde"], partida(971)["desde"] = ahora, ahora
    host = (ip_int("198.51.100.26"), 18113)
    # lo que había en el server de prueba: el anfitrión con la entrada de OTRA sesión (una hora antes)
    json.dump({"970": ["198.51.100.26", 19745, ahora - 3800], "971": ["203.0.113.77", 40500, ahora + 1]},
              open(config.PUNCH_MAPA, "w"))
    chequear("★ lo del server de prueba: una entrada de punch.json de OTRA sesión (mismo número) no vale",
             punch_de(970) is None)
    chequear("…y al invitado le llega la del anfitrión de ESTA sesión (su 0x100F: 18113), no la vieja (19745)",
             dir_udp(970, 971) == host)
    json.dump({"970": ["198.51.100.26", 19745]}, open(config.PUNCH_MAPA, "w"))
    chequear("★ el revés: una entrada sin hora (de un relay viejo) tampoco vale", punch_de(970) is None)
    json.dump({"970": ["198.51.100.26", 18113, ahora + 0.5], "971": ["203.0.113.77", 40500, ahora + 1]},
              open(config.PUNCH_MAPA, "w"))
    chequear("una entrada de ESTA sesión sí vale", punch_de(970) == host)
    cerrada(970)
    entra(970, "02:CC:00:00:00:09", ("192.168.7.7", 57654), ("192.0.2.99", 30000), "192.0.2.99")
    partida(970)["desde"] = ahora + 10
    chequear("★ el revés: el número 970 reusado por OTRA sesión no hereda la dirección del que se fue",
             punch_de(970) is None and dir_udp(970, 971) == (ip_int("192.0.2.99"), 30000))
    cerrada(970)
    entra(970, "02:CC:00:00:00:01", ("192.168.1.48", 57654), ("198.51.100.26", 18113), "198.51.100.26")
    partida(970)["desde"] = ahora
    # ── modo «auto»: por pareja, el mismo camino en los dos sentidos
    config.P2P = "auto"
    json.dump({"971": ["203.0.113.77", 40500, ahora + 1]}, open(config.PUNCH_MAPA, "w"))
    rel = ip_int("203.0.113.9")
    chequear("auto: el anfitrión sin 0x3006 (no se sabe si su NAT guarda el puerto) → la pareja por el RELAY, "
             "los dos sentidos", ruta(970, 971) == ruta(971, 970) == "relay"
             and dir_udp(970, 971) == (rel, config.RELAY_BASE + 1 + 970)
             and dir_udp(971, 970) == (rel, config.RELAY_BASE + 1 + 971))
    json.dump({"970": ["198.51.100.26", 18113, ahora + 1], "971": ["203.0.113.77", 40500, ahora + 1]},
              open(config.PUNCH_MAPA, "w"))
    chequear("auto: las dos públicas confiables (0x3006 y 0x3002 por el mismo puerto) → DIRECTO, los dos sentidos",
             estable(970) and estable(971) and ruta(970, 971) == ruta(971, 970) == "directo"
             and dir_udp(970, 971) == host and dir_udp(971, 970) == (ip_int("203.0.113.77"), 40500))
    json.dump({"970": ["198.51.100.26", 16429, ahora + 1], "971": ["203.0.113.77", 40500, ahora + 1]},
              open(config.PUNCH_MAPA, "w"))
    chequear("★ el revés: el NAT del anfitrión le cambia el puerto (0x3006 por 16429, 0x3002 por 18113) → RELAY, "
             "los dos sentidos (nunca uno directo y el otro no)",
             not estable(970) and ruta(970, 971) == ruta(971, 970) == "relay"
             and dir_udp(971, 970)[1] == config.RELAY_BASE + 1 + 971)
    partida(971)["ip_tcp"] = "198.51.100.26"
    chequear("auto: misma casa (misma IP de conexión) → las PRIVADAS, los dos sentidos",
             ruta(970, 971) == ruta(971, 970) == "casa"
             and dir_udp(970, 971) == (ip_int("192.168.1.48"), 57654)
             and dir_udp(971, 970) == (ip_int("192.168.0.20"), 57654))
    partida(971)["ip_tcp"] = "203.0.113.77"
    partida(971).pop("mac", None)
    chequear("★ el revés: uno sin MAC → relay", ruta(970, 971) == "relay")
    partida(971)["mac"] = "02:CC:00:00:00:02"
    # ── la dirección cambia mientras esperan en la sala → el 0x1059 otra vez (sólo a quien le cambió)
    config.P2P = "directo"
    json.dump({"970": ["198.51.100.26", 18113, ahora + 1], "971": ["203.0.113.77", 40500, ahora + 1]},
              open(config.PUNCH_MAPA, "w"))
    SALAS[77] = {"sala": bytes(0x59), "anfitrion": 970, "miembros": [970, 971]}
    pares(SALAS[77])
    chequear("★ el revés: sin cambios, no se vuelve a mandar nada", reanunciar(SALAS) == [])
    json.dump({"970": ["198.51.100.26", 18665, ahora + 2], "971": ["203.0.113.77", 40500, ahora + 1]},
              open(config.PUNCH_MAPA, "w"))
    r = reanunciar(SALAS)
    chequear("el NAT del anfitrión cambió de puerto (su 0x3006 nuevo): el 0x1059 otra vez, sólo al invitado",
             [(x[0], x[3]) for x in r] == [(0x1059, 971)]
             and struct.pack("<IH", ip_int("198.51.100.26"), 18665) in r[0][1])
    chequear("…y una sola vez", reanunciar(SALAS) == [])
    SALAS[77]["jugando"] = True
    json.dump({"970": ["198.51.100.26", 18700, ahora + 3]}, open(config.PUNCH_MAPA, "w"))
    chequear("★ el revés: jugando, no (el 0x1059 es de la sala que espera)", reanunciar(SALAS) == [])
    SALAS.pop(77)
    (config.P2P_ENTRE_CASAS, config.RELAY_IP, config.P2P, config.PUNCH_MAPA) = viejos


def pruebas_carga_sin_cortes(chequear):
    """★ (21-nov) servidor/salida.py: mientras el juego carga la stage (desde su 0x104F hasta su 0x105E), lo de
    0x1003–0x100B le termina el hilo de carga (exe 0x5345C0 → «Thread DoEnd!!») y el 0x105E ya no se atiende:
    «NOW LOADING» para siempre. Lo del server de prueba: al anfitrión le llegó un 0x1005 entre su 0x105F y su 0x105E."""
    import types
    from servidor import red, salida
    PARTIDAS[980], PARTIDAS[981] = {}, {}
    o = salida.ordenar
    chequear("sin cargar, el chat sale de una", o(980, [(0x1005, b"hola", 0)]) == [(0x1005, b"hola", 0, 980)])
    o(980, [(0x104F, b"", 0)])
    chequear("cargando (después de su 0x104F): el 0x1005 se GUARDA", o(980, [(0x1005, b"a", 0)]) == [])
    chequear("…igual todo 0x1003–0x100B", o(980, [(0x1003, b"", 0), (0x100B, b"b", 0)]) == [])
    chequear("★ el revés: lo demás pasa (0x105F, 0x1002, 0x100C, la lista de salas)",
             [x[0] for x in o(980, [(0x105F, b"", 0), (0x1002, b"", 0), (0x100C, b"", 0), (0x101C, b"", 0)])]
             == [0x105F, 0x1002, 0x100C, 0x101C])
    chequear("★ el revés: al que NO carga (el otro de la sala) le llega en el momento",
             o(980, [(0x1005, b"x", 0, 981)]) == [(0x1005, b"x", 0, 981)])
    r = o(980, [(0x105E, b"L", 0)])
    chequear("su 0x105E sale PRIMERO, y después lo guardado, en el mismo orden",
             r == [(0x105E, b"L", 0, 980), (0x1005, b"a", 0, 980), (0x1003, b"", 0, 980), (0x100B, b"b", 0, 980)])
    chequear("…y después de la largada, el chat sale de una", o(980, [(0x1005, b"c", 0)]) == [(0x1005, b"c", 0, 980)])
    o(980, [(0x104F, b"", 0)])
    o(980, [(0x1005, b"d", 0)])
    chequear("si sale de la stage (0x1075) sin largar, lo guardado sale igual",
             [x[0] for x in o(980, [(0x1075, b"", 0)])] == [0x1075, 0x1005])
    t0 = time.monotonic()
    o(980, [(0x104F, b"", 0)], ahora=t0)
    o(980, [(0x1005, b"e", 0)], ahora=t0)
    chequear("★ una carga que no termina nunca: pasado VENCE se suelta (nada queda guardado para siempre)",
             o(980, [(0x101C, b"", 0)], ahora=t0 + salida.VENCE + 1) == [(0x1005, b"e", 0, 980), (0x101C, b"", 0, 980)]
             and not PARTIDAS[980].get("cargando"))
    o(980, [(0x104F, b"", 0)])
    for i in range(salida.TOPE + 30):
        o(980, [(0x1005, bytes([i % 256]), 0)])
    chequear("★ con más de TOPE guardados, se quedan los últimos TOPE", len(PARTIDAS[980]["diferidos"]) == salida.TOPE)
    o(980, [(0x105E, b"", 0)])
    chequear("los mensajes con espera no se tocan acá (vuelven a pasar cuando vence)",
             o(980, [(0x1005, b"z", 300)]) == [(0x1005, b"z", 300, 980)])
    PARTIDAS[980].clear()
    # ── por servidor/red.py (despachar), con el envío falso: el orden de lo que de verdad sale
    salio = []
    viejos = (red.enviar_a, red.juego)
    red.enviar_a = lambda n, c, cuerpo: salio.append((n, c, cuerpo))
    red.juego = lambda: types.SimpleNamespace(ordenar_salida=salida.ordenar)
    try:
        red.despachar(980, [(0x104F, b"", 0)])
        red.despachar(981, [(0x1005, b"chat", 0, 980), (0x1005, b"chat", 0, 981)])   # el chat del otro, a los dos
        red.despachar(980, [(0x1005, b"tarde", 40)])                                 # uno con espera, mientras carga
        time.sleep(0.15)
        red.despachar(None, [(0x105E, b"L", 0, 980), (0x105E, b"L", 0, 981)])
        a980 = [(c, cuerpo) for n, c, cuerpo in salio if n == 980]
        chequear("red.despachar: al que carga, el 0x105E ANTES que el chat (y el de espera también se guarda)",
                 a980 == [(0x104F, b""), (0x105E, b"L"), (0x1005, b"chat"), (0x1005, b"tarde")], a980)
        chequear("★ el revés: al otro, el chat en el momento", [c for n, c, _ in salio if n == 981] == [0x1005, 0x105E])
        red.juego = lambda: types.SimpleNamespace(ordenar_salida=lambda n, r: 1 / 0)
        salio.clear()
        viejo_log, red.log = red.log, (lambda m: None)
        red.despachar(980, [(0x1005, b"igual", 0)])
        red.log = viejo_log
        chequear("★ el revés: si el orden falla, se manda como antes (no se pierde nada)", salio == [(980, 0x1005, b"igual")])
    finally:
        red.enviar_a, red.juego = viejos

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
    # ★ HABILIDADES: el 0x102B de la pantalla Skill trae N2 (casilla) y N3 (atajo F1…F8)
    c = leer(n)
    c["habilidades"] = [[1000, 1, 1, 0, 1], [1001, 1, 3, 1, 2]]
    guardar(c)
    cuerpo_sk = (struct.pack("<IB", 0, 7) + struct.pack("<I6H", 0, *(list(stats_de(c))[:5] + [0]))
                 + struct.pack("<3H", 0, 2, 3) + struct.pack("<IBIB", 1000, 1, 1001, 0)
                 + struct.pack("<IBIBIB", 1000, 2, 1001, 1, 1000, 9))
    responder(0x102B, cuerpo_sk, n)
    chequear("0x102B Skill: se guardan el nuevo orden (casilla) y los atajos F1…F8 "
             "(★ el revés: un atajo 9 no existe y no se toma)",
             leer(n)["habilidades"] == [[1000, 1, 1, 1, 2], [1001, 1, 3, 0, 1]], leer(n)["habilidades"])
    # ★ «Exit Game» desde el Inventory: 0x102F con el cuerpo entero del 0x102D
    cuerpo = (b"\0" * 8 + struct.pack("<6H", *(list(stats_de(leer(n)))[:5] + [0]))
              + struct.pack("<HHH", 1, 0, 0) + struct.pack("<IB", 9003, 31))
    r = responder(0x102F, cuerpo, n)
    chequear("0x102F de Exit Game (cuerpo del 0x102D) → guarda lo movido y contesta 0x1030 u16 1",
             r == [(0x1030, b"\1\0", 0)] and {it[3]: it[2] for it in leer(n)["items"]}[9003] == 31, r)
    # ★ UseItem: 0x1067 con el SERIAL de una poción de la bolsa → se descuenta (sin difundir nada)
    c = leer(n)
    c["items"] = [[26001, 3, 12, 9001, 1]]
    guardar(c)
    r = responder(0x1067, struct.pack("<I", 9001), n)
    chequear("UseItem (0x1067 con el serial de una poción): baja de 3 a 2, sin respuesta",
             r == [] and [x[1] for x in leer(n)["items"]] == [2], leer(n)["items"])
    responder(0x1067, struct.pack("<I", 9001), n)
    responder(0x1067, struct.pack("<I", 9001), n)
    chequear("★ el revés: al usar la última, la pila desaparece", leer(n)["items"] == [])
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
    guardado2 = (config.CUENTAS_CLAVE_PUBLICA, config.PREFIJO_CUENTA)
    guardado3 = config.CUENTA_NUEVA
    config.CUENTA_NUEVA = "personaje"
    config.CUENTAS_CLAVE_PUBLICA, config.PREFIJO_CUENTA = "", "r2b_"
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
        # ★ (21-nov) el server de PRUEBA acepta SU pase (`eda-prueba`) y no el de prod, y al revés
        chequear("★ el revés: un pase del server de prueba (aud eda-prueba) no entra a prod → «audiencia»",
                 rechazo(firmar(clave, dict(datos, jti="j-6b", aud="eda-prueba")), ahora) == "audiencia")
        aud_antes = config.PORTERO_AUDIENCIA
        config.PORTERO_AUDIENCIA = "eda-prueba"
        try:
            chequear("prueba (EDA_PORTERO_AUDIENCIA=eda-prueba): su pase entra",
                     rechazo(firmar(clave, dict(datos, jti="j-6c", aud="eda-prueba")), ahora) is None)
            chequear("★ el revés: en el de prueba, un pase de prod (aud eda) → «audiencia»",
                     rechazo(firmar(clave, dict(datos, jti="j-6d")), ahora) == "audiencia")
        finally:
            config.PORTERO_AUDIENCIA = aud_antes
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
        # ★ (15-nov) la clave del servicio de cuentas dada DIRECTO por configuración, sin JWKS ni red
        publica = clave.public_key().export_key(format="raw")
        config.PORTERO_CLAVES, config.CUENTAS_CLAVE_PUBLICA = "", b64(publica)
        chequear("clave por configuración (base64url): el pase entra sin JWKS, con cualquier kid",
                 rechazo(firmar(clave, dict(datos, jti="j-20"), kid="el-que-sea"), ahora) is None)
        chequear("★ el revés: firmado con OTRA clave → «firma»",
                 rechazo(firmar(otra, dict(datos, jti="j-21")), ahora) == "firma")
        config.CUENTAS_CLAVE_PUBLICA = publica.hex()
        chequear("…y también en hex", rechazo(firmar(clave, dict(datos, jti="j-22")), ahora) is None)
        config.CUENTAS_CLAVE_PUBLICA = "esto-no-es-una-clave"
        chequear("★ el revés: una clave mal escrita no deja entrar a nadie → «clave»",
                 rechazo(firmar(clave, dict(datos, jti="j-23")), ahora) == "clave")
        config.CUENTAS_CLAVE_PUBLICA = b64(otra.public_key().export_key(format="raw"))
        config.PORTERO_CLAVES = jwks
        chequear("★ el revés: la clave por configuración MANDA sobre el JWKS (uno bueno al lado no la salva)",
                 rechazo(firmar(clave, dict(datos, jti="j-24")), ahora) == "firma")
        # ★ (15-nov) el prefijo de la cuenta: con Cuenta Eñeños el número es el Eñeños ID
        config.CUENTAS_CLAVE_PUBLICA, config.PREFIJO_CUENTA = b64(publica), "en_"
        t = porteria.canjear(firmar(clave, dict(datos, sub="10000570", jti="j-25")), ahora)
        config.LOGIN = "pase"
        rr = responder(0x100F, cuerpo_100f("10000570", t["ticket"]), 330)
        chequear("prefijo «en_»: la cuenta es en_10000570 y su personaje sin bautizar se llama así (11 letras)",
                 rr[0][1][:2] == b"\1\0" and ASIGNADAS.get(330) == "en_10000570")
        rr = responder(0x1011, b"\1\0\0\0", 330)
        chequear("…y su SELECT CHARACTER es el de esa cuenta", rr and rr[0][0] == 0x1012 and leer(330)["nombre"] == "en_10000570")
        chequear("★ el revés: con el prefijo de siempre esa misma persona sería OTRA cuenta (r2b_…)",
                 ASIGNADAS.get(330) != "r2b_10000570")
        # ★ (15-nov) la cuenta NUEVA nace VACÍA: el pase deja entrar, los personajes los crea el jugador
        config.CUENTA_NUEVA = "vacia"
        from servidor.cuentas import ruta_cuenta
        from servidor.objetos import cuerpo_cuenta
        for viejo in ("en_10000900", "en_10000901"):
            if os.path.exists(ruta_cuenta(viejo)):
                os.remove(ruta_cuenta(viejo))
        t = porteria.canjear(firmar(clave, dict(datos, sub="10000900", jti="j-30", nombre="Heredado")), ahora)
        rr = responder(0x100F, cuerpo_100f("10000900", t["ticket"]), 340)
        chequear("cuenta nueva VACÍA: el pase la deja entrar (0x1010 resultado 1) como en_10000900",
                 rr[0][1][:2] == b"\1\0" and ASIGNADAS.get(340) == "en_10000900")
        v = leer(340)
        chequear("…y NO tiene personajes: su 0x1012 va con N3 = 0 y sin ítems",
                 v["pjs"] == [] and cuerpo_cuenta(v, 340)[0x20] == 0 and len(cuerpo_cuenta(v, 340)) == 33)
        chequear("★ el revés: el apodo del pase NO le fabrica un personaje (no hay archivo de la cuenta todavía)",
                 not os.path.exists(ruta_cuenta("en_10000900")))
        r = responder(0x1013, struct.pack("<IBB", 340, 2, 0) + "MiPrimero".encode("utf-16-le") + b"\0" * 4, 340)
        d = leer(340)
        chequear("crea el suyo (0x1013): queda como el único y activo, con el nombre y la clase que eligió",
                 r[0][1][:2] == b"\1\0" and len(d["pjs"]) == 1 and d.get("nick") == "MiPrimero" and d["clase"] == 2,
                 (len(d["pjs"]), d.get("nick")))
        ASIGNADAS.pop(340, None)
        t = porteria.canjear(firmar(clave, dict(datos, sub="10000900", jti="j-31", nombre="Heredado")), ahora)
        responder(0x100F, cuerpo_100f("10000900", t["ticket"]), 342)
        chequear("…y al volver a entrar sigue teniendo SU personaje (el pase no le cambia el nombre)",
                 len(leer(342)["pjs"]) == 1 and leer(342).get("nick") == "MiPrimero")
        config.CUENTA_NUEVA = "personaje"
        t = porteria.canjear(firmar(clave, dict(datos, sub="10000901", jti="j-32")), ahora)
        responder(0x100F, cuerpo_100f("10000901", t["ticket"]), 341)
        chequear("★ el revés: con «personaje» (lo de siempre) una cuenta nueva nace con uno ya hecho",
                 len(leer(341)["pjs"]) == 1)
        for viejo in ("en_10000900", "en_10000901"):
            if os.path.exists(ruta_cuenta(viejo)):
                os.remove(ruta_cuenta(viejo))
        config.CUENTAS_CLAVE_PUBLICA, config.PREFIJO_CUENTA, config.PORTERO_CLAVES = "", "r2b_", jwks
        config.LOGIN = "abierto"
        ASIGNADAS.clear()
        rr = responder(0x100F, cuerpo_100f(), 310)
        chequear("modo abierto (jugar en casa): sin ticket entra, como rui",
                 rr[0][1][:2] == b"\1\0" and cuenta_de(310) == "rui")
    finally:
        config.LOGIN, config.PORTERO_CLAVES, config.PORTERIA = guardado
        config.CUENTAS_CLAVE_PUBLICA, config.PREFIJO_CUENTA = guardado2
        config.CUENTA_NUEVA = guardado3
        ASIGNADAS.clear()
        for x in (jwks, os.path.join(config.ESTADO, "control_porteria.db")):
            if os.path.exists(x):
                os.remove(x)


def pruebas_panel(chequear):
    """★ (20-nov) LA PUERTA INTERNA del panel del Coordinador (servidor/panel.py, «contrato del panel v1»): la
    ficha, X-R2, quién lo pidió, cada ruta y cada acción, con su revés. Y por HTTP de verdad (red.servidor_http)."""
    import threading
    import urllib.error
    import urllib.request
    from servidor import panel
    from servidor.cuentas import CUENTA_CLAVES, escribir, ruta_cuenta

    class Red:                                       # (lo que hace servidor/red.py con las conexiones, anotado)
        def __init__(self):
            self.enviados, self.cortes = [], []

        def enviar(self, resp):
            self.enviados += resp

        def cortar(self, n, espera=0):
            self.cortes.append((n, espera))

    FICHA, QUIEN = "ficha-de-prueba-0123456789", "coordinador:prueba"
    red = Red()

    def pedir(metodo, ruta, cuerpo=None, ficha=FICHA, r2="1", quien=QUIEN, extra=None, con_red=True):
        cab = {}
        if ficha is not None:
            cab["X-Ficha-Interna"] = ficha
        if r2 is not None:
            cab["X-R2"] = r2
        if quien is not None:
            cab["X-Coordinador-Quien"] = quien
        cab.update(extra or {})
        b = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else b""
        return panel.atender(metodo, panel.PREFIJO + "/" + ruta, cab, lambda: b, red if con_red else None)

    def archivo(nombre):
        return json.load(open(ruta_cuenta(nombre), encoding="utf-8"))

    def texto_1005(x):
        return x[1][11:37].decode("utf-16-le").rstrip("\0"), x[1][41:].decode("utf-16-le")

    guardado = (config.LOGIN, config.PREFIJO_CUENTA, config.FICHA_INTERNA, config.PANEL_AUDITORIA, config.ENTORNO)
    config.LOGIN, config.PREFIJO_CUENTA, config.ENTORNO = "pase", "en_", "control"
    config.PANEL_AUDITORIA = os.path.join(config.CUENTAS, "panel_auditoria.jsonl")
    A, B, C = "en_10000042", "en_10000043", "en_123"       # C: un número de R2Beat viejo (< 10.000.000)
    escribir(A, {"nombre": A, "plata": 500, "cash": 10, "monedas": 3, "activo": 0, "pjs": [
        {"nick": "Panelista", "clase": 1, "exp": EXPS[4], "lugar": 0, "stats": [1, 2, 3, 4, 5], "items": [[1, 1, 10, 1, 1]]},
        {"nick": "Arquero2", "clase": 2, "exp": 0, "lugar": 2}]})
    escribir(B, {"nombre": B, "plata": 0, "cash": 0, "monedas": 0, "activo": 0,
                 "pjs": [{"nick": "Arquera", "clase": 2, "exp": 0, "lugar": 0}]})
    escribir(C, {"nombre": C, "plata": 1, "cash": 1, "monedas": 1, "activo": 0, "pjs": []})
    ASIGNADAS.clear()
    PARTIDAS.clear()
    ASIGNADAS.update({501: B, 502: "_sin_login"})           # B conectado; 502 todavía sin mostrar su ticket
    PARTIDAS[501] = {"ip_tcp": "192.0.2.10", "desde": 1_790_000_000}
    try:
        # ── la ficha interna ────────────────────────────────────────────────────────────────────
        config.FICHA_INTERNA = ""
        chequear("★ sin R2_CUENTAS_FICHA_INTERNA la puerta no existe: 404 aunque traiga una ficha (y con una vacía)",
                 pedir("GET", "capacidades")[0] == 404 and pedir("GET", "capacidades", ficha="")[0] == 404)
        config.FICHA_INTERNA = FICHA
        chequear("con la ficha: capacidades → 200", pedir("GET", "capacidades")[0] == 200)
        chequear("★ el revés: sin la cabecera, con otra ficha o con la ficha a medias → 404 (como si no existiera)",
                 [pedir("GET", "capacidades", ficha=f)[0] for f in (None, "otra", FICHA[:-1], FICHA + "x")]
                 == [404, 404, 404, 404])
        chequear("★ con la ficha pero llegado por un proxy (X-Forwarded-For) → 404",
                 pedir("GET", "capacidades", extra={"X-Forwarded-For": "198.51.100.7"})[0] == 404)
        # ── capacidades: EXACTAMENTE lo implementado ────────────────────────────────────────────
        cod, cap = pedir("GET", "capacidades")
        chequear("capacidades: eda, versión 1, su entorno; acciones = ver, aviso, echar, moneda",
                 (cap["juego"], cap["version"], cap["entorno"], cap["acciones"])
                 == ("eda", 1, "control", ["ver", "aviso", "echar", "moneda"]), cap["acciones"])
        chequear("las monedas son las de panel.MONEDAS y cada una es una clave que la CUENTA guarda (CUENTA_CLAVES)",
                 [m["id"] for m in cap["monedas"]] == [m["id"] for m in panel.MONEDAS]
                 and all(m["campo"] in CUENTA_CLAVES for m in panel.MONEDAS) and all(m["nombre"] for m in cap["monedas"]))
        cod, cap2 = pedir("GET", "capacidades", con_red=False)
        chequear("★ el revés: sin las conexiones (sin red.py) no ofrece aviso ni echar, y esas rutas dan 404",
                 cap2["acciones"] == ["ver", "moneda"]
                 and pedir("POST", "aviso", {"texto": "hola", "a": "todos"}, con_red=False)[0] == 404
                 and pedir("POST", "echar", {"id": B}, con_red=False)[0] == 404, cap2["acciones"])
        chequear("★ una ruta que no está (banear, PUT, ficha sin id, otra puerta) → 404",
                 [pedir("GET", "banear")[0], pedir("POST", "banear", {"id": A})[0], pedir("PUT", "capacidades")[0],
                  pedir("GET", "ficha/")[0], pedir("GET", "ficha/../../porteria")[0],
                  panel.atender("GET", "/interno/panelx/capacidades", {"X-Ficha-Interna": FICHA}, red=red)[0]]
                 == [404] * 6)
        # ── X-R2 y quién ────────────────────────────────────────────────────────────────────────
        chequear("★ un POST sin X-R2: 1 → 403 (y con X-R2: 0 también); no cambia nada",
                 pedir("POST", "moneda", {"id": A, "moneda": "oro", "cantidad": 1}, r2=None)[0] == 403
                 and pedir("POST", "moneda", {"id": A, "moneda": "oro", "cantidad": 1}, r2="0")[0] == 403
                 and archivo(A)["plata"] == 500)
        chequear("★ un POST sin X-Coordinador-Quien → 400 (no se puede anotar quién lo pidió); no cambia nada",
                 pedir("POST", "moneda", {"id": A, "moneda": "oro", "cantidad": 1}, quien=None)[0] == 400
                 and archivo(A)["plata"] == 500)
        chequear("un cuerpo que no es JSON → 400", panel.atender(
            "POST", panel.PREFIJO + "/moneda", {"X-Ficha-Interna": FICHA, "X-R2": "1", "X-Coordinador-Quien": QUIEN},
            lambda: b"{no", red)[0] == 400)

        # ── buscar ──────────────────────────────────────────────────────────────────────────────
        def ids(q):
            return [f["id"] for f in pedir("GET", "buscar?q=" + q)[1]["filas"]]
        chequear("buscar por una parte del apodo (sin mayúsculas), también de un personaje que no es el activo",
                 ids("nelis") == [A] and ids("PANELIS") == [A] and ids("quero2") == [A], (ids("nelis"), ids("quero2")))
        chequear("buscar por la cuenta del juego y por el Eñeños ID", ids(B) == [B] and ids("10000042") == [A])
        chequear("★ el revés: lo que no está → nada; vacío → nada; un número de R2Beat viejo (< 10.000.000) no es un Eñeños ID",
                 ids("zzzz") == [] and ids("") == [] and ids("123") == [], ids("123"))
        fila = pedir("GET", "buscar?q=" + B)[1]["filas"][0]
        chequear("cada fila: id, nick, enenos_id, conectado, resumen",
                 fila == {"id": B, "nick": "Arquera", "enenos_id": 10000043, "conectado": True,
                          "resumen": "Nivel 1 · Cazador (Hunter) · 1 personaje"}, fila)
        for k in range(panel.TOPE_BUSCAR + 5):
            escribir("en_%d" % (20000000 + k), {"nombre": "en_%d" % (20000000 + k), "activo": 0,
                                                 "pjs": [{"nick": "Tope%02d" % k, "clase": 1, "exp": 0, "lugar": 0}]})
        chequear("buscar tiene tope de %d (había %d)" % (panel.TOPE_BUSCAR, panel.TOPE_BUSCAR + 5),
                 len(ids("tope")) == panel.TOPE_BUSCAR)
        chequear("★ el revés: el tope no corta una búsqueda chica", ids("Tope07") == ["en_20000007"])
        # ── conectados y salud ──────────────────────────────────────────────────────────────────
        cod, con = pedir("GET", "conectados")
        chequear("conectados: sólo los que entraron (no la conexión sin ticket), con IP, desde, dónde y Eñeños ID",
                 con["filas"] == [{"id": B, "nick": "Arquera", "enenos_id": 10000043, "donde": "en el lobby",
                                   "desde": 1_790_000_000, "ip": "192.0.2.10"}], con)
        cod, sal = pedir("GET", "salud")
        chequear("salud: en línea, 1 jugando, con su detalle en palabras",
                 sal["en_linea"] is True and sal["jugando"] == 1
                 and all(set(d) == {"nombre", "valor"} for d in sal["detalle"]), sal["jugando"])
        # ── la ficha ────────────────────────────────────────────────────────────────────────────
        cod, f = pedir("GET", "ficha/" + A)
        campos = {c["nombre"]: c["valor"] for c in f["campos"]}
        chequear("ficha: el personaje activo, nivel %d (de su EXP), clase, monedas de la cuenta, sus 2 personajes" % nivel(EXPS[4]),
                 cod == 200 and f["nick"] == "Panelista" and f["enenos_id"] == 10000042 and f["conectado"] is False
                 and campos["Nivel"] == nivel(EXPS[4]) and campos["Clase"] == "Guerrero (Warrior)"
                 and campos["Fuerza · Constitución · Destreza · Inteligencia · Sabiduría"] == "1 · 2 · 3 · 4 · 5"
                 and f["monedas"] == {"oro": 500, "cash": 10, "monedas_revivir": 3}
                 and f["personajes"] == [{"id": A + ".0", "nick": "Panelista"}, {"id": A + ".2", "nick": "Arquero2"}],
                 (cod, campos.get("Nivel"), f.get("monedas")))
        cod2, f2 = pedir("GET", "ficha/" + A + ".2")
        chequear("ficha/<cuenta>.<lugar>: ese personaje (Arquero2, Cazador)",
                 cod2 == 200 and f2["nick"] == "Arquero2"
                 and {c["nombre"]: c["valor"] for c in f2["campos"]}["Clase"] == "Cazador (Hunter)")
        chequear("★ el revés: una cuenta que no existe, un lugar vacío, un nombre con ruta → 404",
                 [pedir("GET", "ficha/" + x)[0] for x in ("en_999", A + ".4", "..", "en_1/../x")] == [404] * 4)
        chequear("ficha de una cuenta sin personajes (y un Eñeños ID que no es: None)",
                 pedir("GET", "ficha/" + C)[1]["enenos_id"] is None and pedir("GET", "ficha/" + C)[1]["personajes"] == [])
        todo = json.dumps([pedir("GET", r)[1] for r in ("ficha/" + A, "ficha/" + B, "conectados", "buscar?q=e", "salud")])
        chequear("★ ninguna respuesta lleva la ficha interna, tickets ni contraseñas",
                 FICHA not in todo and not re.search(r'"(ticket|pase|pass\w*|hash|clave)"', todo))
        # ── moneda ──────────────────────────────────────────────────────────────────────────────
        cod, r = pedir("POST", "moneda", {"id": A, "moneda": "oro", "cantidad": 250})
        chequear("moneda: +250 de oro a un desconectado → antes 500, después 750, y queda en su archivo (sus personajes intactos)",
                 (cod, r) == (200, {"ok": True, "antes": 500, "despues": 750}) and archivo(A)["plata"] == 750
                 and [p["nick"] for p in archivo(A)["pjs"]] == ["Panelista", "Arquero2"], (cod, r))
        ultima = json.loads(open(config.PANEL_AUDITORIA, encoding="utf-8").read().splitlines()[-1])
        chequear("se anota con quién lo pidió (auditoría y movimientos de la ficha)",
                 (ultima["quien"], ultima["accion"], ultima["id"]) == (QUIEN, "moneda", A)
                 and pedir("GET", "ficha/" + A)[1]["movimientos"][0]["quien"] == QUIEN, ultima)
        chequear("★ nunca negativo: quitar 751 de 750 → 409 y no cambia",
                 pedir("POST", "moneda", {"id": A, "moneda": "oro", "cantidad": -751})[0] == 409
                 and archivo(A)["plata"] == 750)
        chequear("…y quitar justo 750 → 0 (el borde vale)",
                 pedir("POST", "moneda", {"id": A, "moneda": "oro", "cantidad": "-750"})[1].get("despues") == 0
                 and archivo(A)["plata"] == 0)
        chequear("★ el tope de las monedas para revivir (999): +997 sobre 3 → 409; +996 → 999",
                 pedir("POST", "moneda", {"id": A, "moneda": "monedas_revivir", "cantidad": 997})[0] == 409
                 and pedir("POST", "moneda", {"id": A, "moneda": "monedas_revivir", "cantidad": 996})[1].get("despues") == 999)
        chequear("★ cantidad 0, texto, true, 1.5; moneda inventada → 400; cuenta que no existe → 404",
                 [pedir("POST", "moneda", {"id": A, "moneda": "oro", "cantidad": x})[0] for x in (0, "abc", True, 1.5, None)]
                 == [400] * 5 and pedir("POST", "moneda", {"id": A, "moneda": "rcoin", "cantidad": 1})[0] == 400
                 and pedir("POST", "moneda", {"id": "en_999", "moneda": "oro", "cantidad": 1})[0] == 404)
        cambia = {}
        for m in panel.MONEDAS:                      # (lo esperado sale de la tabla, no escrito a mano)
            antes = archivo(C)[m["campo"]]
            pedir("POST", "moneda", {"id": C, "moneda": m["id"], "cantidad": 2})
            cambia[m["id"]] = archivo(C)[m["campo"]] - antes
        chequear("cada moneda de capacidades cambia SU clave de la cuenta", cambia == {m["id"]: 2 for m in panel.MONEDAS}, cambia)
        cod, r = pedir("POST", "moneda", {"id": B, "moneda": "oro", "cantidad": 10})
        chequear("★ a un CONECTADO no se le tocan las monedas: 409 con el motivo, y no cambia",
                 cod == 409 and "conectado" in r["error"] and archivo(B)["plata"] == 0, r)
        ASIGNADAS.pop(501)
        chequear("…y cuando sale, sí (+10)", pedir("POST", "moneda", {"id": B, "moneda": "oro", "cantidad": 10})[1].get("despues") == 10)
        # ── aviso y echar ───────────────────────────────────────────────────────────────────────
        ASIGNADAS.update({501: B, 503: A})
        cod, r = pedir("POST", "aviso", {"texto": "Reinicio en 5 minutos", "a": "todos"})
        chequear("aviso a todos: llega a los 2 conectados (no a la conexión sin ticket), como línea del chat «[Aviso]»",
                 (cod, r) == (200, {"ok": True, "llego_a": 2}) and sorted(x[3] for x in red.enviados) == [501, 503]
                 and all(x[0] == 0x1005 and texto_1005(x) == ("[Aviso]", "Reinicio en 5 minutos") for x in red.enviados),
                 (cod, r, [x[3] for x in red.enviados]))
        red.enviados.clear()
        cod, r = pedir("POST", "aviso", {"texto": "hola", "a": "uno", "id": A})
        chequear("aviso a uno: sólo a su conexión", (cod, r["llego_a"], [x[3] for x in red.enviados]) == (200, 1, [503]))
        red.enviados.clear()
        chequear("★ el revés: a uno que no está → 404; sin texto, con más de %d letras o «a» inventado → 400; nada sale" % panel.TOPE_AVISO,
                 pedir("POST", "aviso", {"texto": "hola", "a": "uno", "id": C})[0] == 404
                 and [pedir("POST", "aviso", d)[0] for d in ({"texto": "  ", "a": "todos"}, {"texto": "x" * 201, "a": "todos"},
                                                             {"texto": "hola", "a": "algunos"})] == [400] * 3
                 and red.enviados == [])
        cod, r = pedir("POST", "echar", {"id": B})
        chequear("echar: corta SU conexión, ya", (cod, r, red.cortes) == (200, {"ok": True}, [(501, 0)]), red.cortes)
        red.cortes.clear()
        cod, r = pedir("POST", "echar", {"id": A, "motivo": "lenguaje"})
        chequear("echar con motivo: primero el aviso con el motivo, y el corte con espera",
                 cod == 200 and red.cortes == [(503, 1.5)] and "lenguaje" in texto_1005(red.enviados[-1])[1])
        red.cortes.clear()
        chequear("★ el revés: echar a uno que no está conectado → 404 y no se corta nada",
                 pedir("POST", "echar", {"id": C})[0] == 404 and red.cortes == [])
        acc = [json.loads(x)["accion"] for x in open(config.PANEL_AUDITORIA, encoding="utf-8").read().splitlines()]
        chequear("la auditoría tiene cada cambio (moneda, aviso, echar) y ninguno de los rechazados",
                 {"moneda", "aviso", "echar"} <= set(acc) and acc.count("echar") == 2 and acc.count("aviso") == 2, acc)
        # ── por HTTP de verdad (servidor/red.py) ────────────────────────────────────────────────
        from servidor import red as R
        juego_real, R.juego = R.juego, (lambda: None)        # (sin recargar servidor/: perdería lo de la prueba)
        abrir = urllib.request.build_opener(urllib.request.ProxyHandler({})).open

        def http(puerto, metodo, ruta, cab=None, cuerpo=None):
            req = urllib.request.Request("http://127.0.0.1:%d%s" % (puerto, ruta), method=metodo, data=cuerpo,
                                         headers=cab or {})
            try:
                with abrir(req, timeout=5) as rr:
                    return rr.status, json.loads(rr.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        srvs = [R.servidor_http(("127.0.0.1", 0)), R.servidor_http(("127.0.0.1", 0), solo_panel=True)]
        for s in srvs:
            threading.Thread(target=s.serve_forever, daemon=True).start()
        try:
            uno, solo = (s.server_address[1] for s in srvs)
            bien = {"X-Ficha-Interna": FICHA}
            cod, cap = http(uno, "GET", "/interno/panel/capacidades", bien)
            chequear("HTTP: capacidades con la ficha → 200, con aviso y echar (las conexiones de red.py)",
                     cod == 200 and cap["acciones"] == ["ver", "aviso", "echar", "moneda"], (cod, cap))
            sin, nada = http(uno, "GET", "/interno/panel/capacidades"), http(uno, "GET", "/no/existe")
            chequear("★ HTTP: sin la ficha → 404, igual que una ruta que no existe", sin == nada and sin[0] == 404, (sin, nada))
            cod, r = http(uno, "POST", "/interno/panel/moneda", dict(bien, **{"Content-Type": "application/json"}),
                          json.dumps({"id": A, "moneda": "oro", "cantidad": 1}).encode())
            chequear("★ HTTP: un POST sin X-R2 → 403", cod == 403, (cod, r))
            cod, r = http(uno, "POST", "/interno/panel/moneda", dict(bien, **{"X-R2": "1", "X-Coordinador-Quien": QUIEN}),
                          b"x" * (panel.TOPE_CUERPO + 1))
            chequear("★ HTTP: un cuerpo de más de %d bytes → 413" % panel.TOPE_CUERPO, cod == 413, cod)
            chequear("HTTP: el login sigue igual (/eda/salud → 200)", http(uno, "GET", "/eda/salud")[0] == 200)
            chequear("el HTTP aparte (EDA_PANEL_ESCUCHAR): el panel sí; ★ el revés: el login ahí no existe",
                     http(solo, "GET", "/interno/panel/salud", bien)[0] == 200 and http(solo, "GET", "/eda/salud")[0] == 404
                     and http(solo, "POST", "/eda/pase", {}, b"{}")[0] == 404)
        finally:
            for s in srvs:
                s.shutdown()
                s.server_close()
            R.juego = juego_real
    finally:
        (config.LOGIN, config.PREFIJO_CUENTA, config.FICHA_INTERNA, config.PANEL_AUDITORIA, config.ENTORNO) = guardado
        ASIGNADAS.clear()
        PARTIDAS.clear()


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


def pruebas_messenger_cuentas_reales(chequear):
    """★ (18-nov) el Messenger con las cuentas del login «pase» (r2b_<uid>), no sólo rui/kai/mio/ren: el
    identificador es la cuenta, el nick es lo que se ve; búsqueda de desconectados, solicitudes y DELETE."""
    from servidor import messenger as m

    def chat_(texto):
        t = texto.encode("utf-16-le")
        return struct.pack("<BIII", 1, 0xFFFFFFFF, 0, len(t)) + t

    def textos(r, destino):
        return [x[1][41:].decode("utf-16-le") for x in r if x[0] == 0x1005 and x[3] == destino
                and x[1][11:37].decode("utf-16-le").rstrip("\0") != "[MSN]"]
    a, b, c = "r2b_9001", "r2b_9002", "r2b_9003"
    for conexion, cuenta, nick in ((401, a, "Alfa"), (402, b, "Beta"), (403, c, "kai")):
        ASIGNADAS[conexion] = cuenta
        x = leer(conexion)
        x["nick"] = nick
        x["amigos"] = []
        guardar(x)
    cerrada(403)                                            # (c queda guardada, desconectada)
    chequear("cuentas reales: la lista de cuentas incluye r2b_<uid> (no sólo rui/kai/mio/ren)",
             {a, b, c} <= set(m.nombres_de_cuentas()), m.nombres_de_cuentas())
    chequear("★ el revés: otros .json de la carpeta (inventarios, relay, punch) no son cuentas",
             not {"inv_kai", "relay", "punch"} & set(m.nombres_de_cuentas()), m.nombres_de_cuentas())
    chequear("cuentas reales: buscar por nick → la cuenta (conectada)", m.buscar("beta") == (b, 402))
    chequear("cuentas reales: buscar por nick a un DESCONECTADO → la cuenta", m.buscar("KAI")[0] in ("kai", c))
    chequear("★ identificador antes que nick: «kai» es la cuenta kai, no el personaje «kai» de r2b_9003",
             m.buscar("kai")[0] == "kai" and m.buscar(c) == (c, None))
    r = responder(0x100D, chat_("/amigo Beta"), 401)
    chequear("cuentas reales: ADD por nick → solicitud guardada con el IDENTIFICADOR (no el nick)",
             leer(401)["amigos"] == [b] and any("solicitud de amistad" in t for t in textos(r, 402)))
    cu = m.estado()["cuentas"]
    chequear("cuentas reales: la lista R/E con identificador y nick",
             ("\nE\t%s\tBeta" % b) in m.lista_msn(cu, a) and ("\nR\t%s\tAlfa" % a) in m.lista_msn(cu, b))
    r = responder(0x100D, chat_("/aceptar %s" % a), 402)
    chequear("★ cuentas reales: los avisos dicen el NICK aunque la dll mande el identificador",
             any("Alfa y tú ahora son amigos" in t for t in textos(r, 402))
             and not any(a in t for t in textos(r, 402) + textos(r, 401)), textos(r, 402))
    cu = m.estado()["cuentas"]
    chequear("cuentas reales: /aceptar con el identificador → amigos los dos (A con nick)",
             ("\nA\t%s\tBeta\t" % b) in m.lista_msn(cu, a) and ("\nA\t%s\tAlfa\t" % a) in m.lista_msn(cu, b))
    responder(0x100D, chat_("/msn hola"), 401)
    responder(0x100D, chat_("/msn hola"), 402)
    r = responder(0x100D, chat_("/m %s hola real" % b), 401)
    chequear("cuentas reales: /m entre amigos → sólo el Messenger (H), nada al chat",
             any(x[0] == 0x1005 and x[3] == 402 and "hola real" in x[1][41:].decode("utf-16-le") for x in r)
             and not textos(r, 402))
    responder(0x100D, chat_("/amigo %s" % c), 401)
    chequear("cuentas reales: ADD a un desconectado (por identificador) → la solicitud queda guardada",
             c in leer(401)["amigos"] and ("\nR\t%s\t" % a) in m.lista_msn(m.estado()["cuentas"], c))
    ASIGNADAS[403] = c
    responder(0x100D, chat_("/aceptar Alfa"), 403)
    cerrada(403)
    r = responder(0x100D, chat_("/quitar %s" % c), 401)
    chequear("★ cuentas reales: DELETE de un desconectado → el aviso con su nick (kai), no el identificador",
             any(t.startswith("kai quitado") or "kai quitado" in t for t in textos(r, 401))
             and not any(c in t for t in textos(r, 401)), textos(r, 401))
    chequear("cuentas reales: DELETE a un desconectado → fuera de las DOS listas (su archivo también)",
             c not in leer(401)["amigos"] and a not in m.amigos_de(c) and m.amigos_de(b) == [a], m.amigos_de(c))
    for conexion in (401, 402):
        cerrada(conexion)
    chequear("cuentas reales: al irse, sus mensajes de la sesión no quedan", not m.historia_msn(a) and not m.historia_msn(b))


def pruebas_messenger(chequear):
    """★ el MESSENGER por chat (servidor/messenger.py): dos conectados, rui = 301 y kai = 302."""
    from servidor.juego import tick

    def chat_(texto):
        t = texto.encode("utf-16-le")
        return struct.pack("<BIII", 1, 0xFFFFFFFF, 0, len(t)) + t

    def textos(r, destino):                     # (lo que se VE en el chat: los «[MSN]» se los queda la dll)
        return [x[1][41:].decode("utf-16-le") for x in r if x[0] == 0x1005 and x[3] == destino
                and x[1][11:37].decode("utf-16-le").rstrip("\0") != "[MSN]"]
    from servidor import messenger
    responder(0x1017, b"", 301)
    responder(0x1017, b"", 302)
    nom_a, nom_b = ASIGNADAS[301], ASIGNADAS[302]
    r = responder(0x100D, chat_("/amigos"), 301)
    chequear("messenger: /amigos sin amigos → un aviso sólo al que pregunta",
             textos(r, 301) and not textos(r, 302))
    r = responder(0x100D, chat_("/amigo %s" % nom_b), 301)
    chequear("/amigo %s → la SOLICITUD (guardada), y al otro le llega el aviso" % nom_b,
             leer(301).get("amigos") == [nom_b] and any("solicitud de amistad" in t for t in textos(r, 302)))
    chequear("★ el revés: /amigo de alguien que no existe no agrega",
             responder(0x100D, chat_("/amigo nadie_xyz"), 301) and leer(301)["amigos"] == [nom_b])
    # ★ (17-nov) solicitudes con aceptación
    from servidor import messenger as _m
    cu = _m.estado()["cuentas"]
    chequear("solicitud: el que la mandó la ve como E, el otro como R; ninguno como A",
             ("\nE\t%s\t" % nom_b) in _m.lista_msn(cu, nom_a) and ("\nR\t%s\t" % nom_a) in _m.lista_msn(cu, nom_b)
             and "\nA\t" not in _m.lista_msn(cu, nom_a) + _m.lista_msn(cu, nom_b))
    r = responder(0x100D, chat_("/amigo %s" % nom_b), 301)
    chequear("★ el revés: la misma solicitud otra vez → «pendiente», sin duplicar",
             any("pendiente" in t for t in textos(r, 301)) and leer(301)["amigos"] == [nom_b])
    r = responder(0x100D, chat_("/amigo %s" % nom_a), 301)
    chequear("★ el revés: agregarse a uno mismo no se puede", leer(301)["amigos"] == [nom_b])
    r = responder(0x100D, chat_("/rechazar %s" % nom_a), 302)
    chequear("/rechazar → la solicitud desaparece (de la lista del que la mandó) y le llega el aviso",
             leer(301).get("amigos") == [] and any("rechazó" in t for t in textos(r, 301)))
    responder(0x100D, chat_("/amigo %s" % nom_b), 301)
    r = responder(0x100D, chat_("/aceptar %s" % nom_a), 302)
    cu = _m.estado()["cuentas"]
    chequear("/aceptar → amigos los DOS (A en las dos listas) y al que la mandó le llega el aviso",
             leer(302).get("amigos") == [nom_a] and ("\nA\t%s\t" % nom_b) in _m.lista_msn(cu, nom_a)
             and ("\nA\t%s\t" % nom_a) in _m.lista_msn(cu, nom_b) and any("aceptó" in t for t in textos(r, 301)))
    chequear("★ el revés: aceptar una solicitud que no existe → aviso, nada cambia",
             responder(0x100D, chat_("/aceptar %s" % nom_a), 302) and leer(302)["amigos"] == [nom_a])
    r = responder(0x100D, chat_("/amigos"), 301)
    chequear("/amigos → conectado, en el lobby", any("conectado, en el lobby" in t for t in textos(r, 301)),
             textos(r, 301))
    r = responder(0x100D, chat_("/m %s hola amigo" % nom_b), 301)
    chequear("/m → el mensaje sólo al otro (y el eco al que lo manda)",
             textos(r, 302) == ["hola amigo"] and textos(r, 301) == ["hola amigo"])
    r = responder(0x100D, chat_("/messenger"), 301)
    chequear("botón Messenger (/messenger) → los amigos y la ayuda", len(textos(r, 301)) == 2)
    # ★ (16-nov) el Messenger de la DLL: «/msn abrir» → la lista y la historia por «[MSN]» (la dll se los queda)
    def msn(r, destino):
        return [x[1][41:].decode("utf-16-le") for x in r if x[0] == 0x1005 and x[3] == destino
                and x[1][11:37].decode("utf-16-le").rstrip("\0") == "[MSN]"]
    r = responder(0x100D, chat_("/msn abrir"), 301)
    lista = msn(r, 301)
    chequear("dll: /msn abrir → la lista: yo y el amigo conectado, y la historia",
             lista and lista[0].startswith("L\t%s\t" % nom_a) and ("\nA\t%s\t" % nom_b) in lista[0]
             and "\t1\ten el lobby" in lista[0] and any(x == "h\t%s\t%s\t%s\thola amigo" % (nom_a, nom_b, x.split("\t")[3])
                                                       for x in lista[1:]), lista)
    chequear("★ el revés: el otro (sin la dll) no recibe nada de [MSN]", not msn(r, 302))
    r = responder(0x100D, chat_("/msn abrir"), 301)
    chequear("dll: al reabrir, la lista sin repetir la historia", len(msn(r, 301)) == 1)
    r = responder(0x100D, chat_("/m %s otra vez" % nom_b), 301)
    chequear("dll: un /m llega como H al que tiene la dll (y el chat sigue igual)",
             [x.split("\t")[4] for x in msn(r, 301)] == ["otra vez"] and textos(r, 302)[-1] == "otra vez")
    chequear("dll: sin cambios, el tick no manda la lista otra vez", not msn(tick([301, 302]), 301))
    r = responder(0x100D, chat_("/msn hola"), 302)
    chequear("dll: «/msn hola» (al entrar al lobby) → la lista, sin abrir la ventana",
             msn(r, 302) and msn(r, 302)[0].startswith("L\t%s\t" % nom_b))
    r = responder(0x100D, chat_("/m %s con las dos dll" % nom_b), 301)
    chequear("★ entre amigos con la dll: el mensaje SÓLO por el Messenger (H a los dos), nada duplicado en el chat",
             [x.split("\t")[4] for x in msn(r, 302)] == ["con las dos dll"] and not textos(r, 302)
             and [x.split("\t")[4] for x in msn(r, 301)] == ["con las dos dll"] and not textos(r, 301))
    r = responder(0x100D, chat_("/clan"), 301)
    chequear("botón Clan (/clan) → un aviso", any(t.startswith("Clan:") for t in textos(r, 301)))
    r = responder(0x100D, chat_("/opciones"), 301)
    chequear("botón Options (/opciones) → un aviso, sólo al que lo pulsó",
             any("Opciones" in t for t in textos(r, 301)) and not textos(r, 302))
    r = responder(0x100D, chat_("/oro 5"), 301)
    chequear("★ el revés: los comandos GM siguen andando (/oro no es del messenger)",
             any("Oro actualizado" in t for t in textos([x + (301,) if len(x) == 3 else x for x in r], 301)))
    r = responder(0x1017, b"", 302)
    chequear("el amigo entra al lobby → «se conectó»", any("se conectó" in t for t in textos(r, 301)))
    cerrada(302)
    t = tick([301])
    chequear("el amigo se va → con el tick, «se desconectó»", any("se desconectó" in x for x in textos(t, 301)))
    chequear("dll: el amigo se va → el tick manda la lista nueva (desconectado)",
             any(("\nA\t%s\t" % nom_b) in x and "\t0\t" in x for x in msn(t, 301)), msn(t, 301))
    r = responder(0x100D, chat_("/m %s sigues?" % nom_b), 301)
    chequear("★ el revés: /m a un desconectado → aviso (no se envía ni se guarda), sin mensaje al chat ni H",
             len(textos(r, 301)) == 1 and textos(r, 301)[0].startswith("%s no está conectado: el mensaje no se envió" % nom_b)
             and not textos(r, 302) and not msn(r, 301), textos(r, 301))
    # ★ (17-nov) las conversaciones duran sólo la sesión: en memoria, nada en messenger_chat.jsonl
    chequear("sesión: nada se escribe en messenger_chat.jsonl", not os.path.exists(messenger.ruta_chat()))
    chequear("sesión: el que se fue ya no ve la conversación; el que sigue, sí",
             not messenger.historia_msn(nom_b)
             and [x.split("\t")[4] for x in messenger.historia_msn(nom_a)] == ["hola amigo", "otra vez", "con las dos dll"],
             messenger.historia_msn(nom_a))
    # ★ el PANEL (EDA-Messenger.py): estado y pedidos por archivo; el otro vuelve a conectarse
    from servidor import messenger
    responder(0x1017, b"", 302)
    responder(0x100D, chat_("/quitar %s" % nom_b), 301)
    chequear("DELETE (/quitar) saca la amistad de las DOS listas (también la del otro)",
             nom_b not in leer(301).get("amigos", []) and nom_a not in leer(302).get("amigos", []))
    with open(messenger.ruta_pedidos(), "w", encoding="utf-8") as f:
        f.write(json.dumps({"de": nom_a, "accion": "amigo", "nick": nom_b}) + "\n")
        f.write(json.dumps({"de": nom_a, "accion": "mensaje", "nick": nom_b, "texto": "hola desde el panel"}) + "\n")
        f.write("esto no es json\n")
    t = tick([301, 302])
    chequear("panel: el pedido «amigo» manda la solicitud y avisa al otro",
             leer(301).get("amigos") == [nom_b] and any("solicitud" in x for x in textos(t, 302)))
    chequear("panel: el pedido «mensaje» le llega al otro", "hola desde el panel" in textos(t, 302))
    chequear("panel: los pedidos se consumen", not os.path.exists(messenger.ruta_pedidos()))
    est = json.load(open(messenger.ruta_estado(), encoding="utf-8"))["cuentas"]
    chequear("panel: el estado dice quién es amigo de quién, conectado y en el lobby",
             est[nom_a]["amigos"] == [nom_b] and est[nom_b]["conectado"] and est[nom_b]["donde"] == "en el lobby",
             est.get(nom_b))
    chequear("★ el revés: sin cambios, el estado no se reescribe", messenger.escribir_estado() is False)
    with open(messenger.ruta_pedidos(), "w", encoding="utf-8") as f:
        f.write(json.dumps({"de": nom_a, "accion": "quitar", "nick": nom_b}) + "\n")
    tick([301, 302])
    chequear("panel: el pedido «quitar» lo saca", leer(301).get("amigos") == [])
    # ★ VENTA / ELIMINACIÓN EN GRUPO por pedido, y el archivo del inventario de cada conectado
    from servidor.datos import precios_venta
    from servidor.objetos import inventario
    c = leer(301)
    c["items"] = [[1, 1, 10, 1, 1], [11, 1, 20, 2, 1], [12, 1, 21, 3, 1], [26001, 5, 22, 4, 1]]
    c["plata"] = 1000
    guardar(c)
    precios = precios_venta()
    messenger.escribir_inventarios()
    inv_p = json.load(open(messenger.ruta_inventario(nom_a), encoding="utf-8"))
    chequear("inventario: el archivo del panel con oro y 4 ítems (serial, tipo, cant, casillero, precio)",
             inv_p["plata"] == 1000 and [x["serial"] for x in inv_p["items"]] == [1, 2, 3, 4], inv_p)
    if precios.get(11) and precios.get(12):
        with open(messenger.ruta_pedidos(), "w", encoding="utf-8") as f:
            f.write(json.dumps({"de": nom_a, "accion": "vender", "seriales": [1, 2, 3]}) + "\n")
        t = tick([301, 302])
        d = leer(301)
        chequear("vender 3 (uno PUESTO): se venden los 2 de la bolsa, el puesto queda",
                 [x[3] for x in inventario(d)] == [1, 4] and d["plata"] == 1000 + precios[11] + precios[12],
                 [x[3] for x in inventario(d)])
        chequear("un 0x1042 por ítem vendido, con el oro que va quedando",
                 [struct.unpack_from("<HIIB", x[1])[:3] for x in t if x[0] == 0x1042 and x[3] == 301]
                 == [(1, 2, 1000 + precios[11]), (1, 3, 1000 + precios[11] + precios[12])])
    with open(messenger.ruta_pedidos(), "w", encoding="utf-8") as f:
        f.write(json.dumps({"de": nom_a, "accion": "eliminar", "seriales": [4, 99]}) + "\n")
    plata = leer(301)["plata"]
    t = tick([301, 302])
    chequear("eliminar: sale de la bolsa sin oro (y un serial que no existe no hace nada)",
             4 not in [x[3] for x in inventario(leer(301))] and leer(301)["plata"] == plata
             and any(x.startswith("Eliminados 1") for x in textos(t, 301)))
    messenger.escribir_inventarios()
    chequear("el archivo del panel se actualiza", 4 not in [x["serial"] for x in json.load(
        open(messenger.ruta_inventario(nom_a), encoding="utf-8"))["items"]])
    with open(messenger.ruta_pedidos(), "w", encoding="utf-8") as f:
        f.write(json.dumps({"de": nom_a, "accion": "aviso", "texto": "Clan: reservado (F12)."}) + "\n")
    t = tick([301, 302])
    chequear("pedido «aviso» (F12) → una línea en el chat", textos(t, 301) == ["Clan: reservado (F12)."])


class _ClienteSala:
    """(Punto 3) Lo que el CLIENTE recuerda de su sala, como lo hace el exe (EDA_limpio 0799387e), para
    probar el «All users must be ready» sin el juego: +0x706 = mi número · +0x29D = el del anfitrión ·
    la lista de «los otros» (cuenta+0x240, de a 0x36F; cada uno por su número +4, con +0x322 listo y
    +0x323). Quién la toca: 0x101E crear (`0x543500`: vacía) · 0x1020 entrar (`0x543640`: vacía y agrega
    los N) · 0x1057 uno nuevo (`0x54F020`) · 0x1058 (`0x54FC80`: tipo 1 listo, tipo 2 +0x323, tipo 3 se
    fue + nuevo anfitrión) · 0x102E modo 9 vuelta del inventario (`0x54D096`: vacía y agrega los N,
    sin saltear a nadie) · 0x1073 resultado (`0x548AF0` → `0x61C200`: todos no listos) · 0x1075 y 0x1046
    (vacían). F9 del anfitrión (`0x534B20`): larga sólo si `0x61C170` = todos listos y +0x323 en 0;
    si no, el cartel 0x191 «All users must be ready to start the game»."""

    def __init__(self):
        self.yo = self.anfitrion = 0
        self.otros = {}

    def _miembro(self, m):
        self.otros[m[4]] = [m[0x322], m[0x323]]

    def recibe(self, cmd, b):
        if cmd == 0x101E:
            self.otros, self.yo, self.anfitrion = {}, b[3], b[4]
        elif cmd == 0x1020:
            self.otros, self.yo, self.anfitrion = {}, b[3], b[4]
            n = b[2 + 9 + 0x59]
            for k in range(n):
                self._miembro(b[2 + 9 + 0x59 + 1 + 0x32C * k:])
        elif cmd == 0x1057:
            self._miembro(b[8:])
        elif cmd == 0x1058:
            ident, tipo, valor = struct.unpack_from("<BHB", b)
            if tipo == 1 and ident in self.otros:
                self.otros[ident][0] = valor
            elif tipo == 2 and ident in self.otros:
                self.otros[ident][1] = valor
            elif tipo == 3:
                self.otros.pop(ident, None)
                self.anfitrion = valor
        elif cmd == 0x102E and b[2] == 9:
            h = b[3:]
            self.yo, self.anfitrion, self.otros = h[1], h[2], {}
            n = h[9 + 0x59]
            for k in range(n):
                self._miembro(h[9 + 0x59 + 1 + 0x32C * k:])
        elif cmd == 0x1073:
            for v in self.otros.values():
                v[0] = v[1] = 0
        elif cmd in (0x1075, 0x1046, 0x1054):
            self.otros = {}

    def f9(self):
        """Lo que pasa al apretar F9: 'larga' (manda 0x104E), 'cartel' (0x191) o 'listo' (no es anfitrión)."""
        if self.yo != self.anfitrion:
            return "listo"
        return "larga" if all(v == [1, 0] for v in self.otros.values()) else "cartel"


def pruebas_ready(chequear):
    """★ (Punto 3) «All users must be ready to start the game» con el cliente de arriba (sus reglas, del exe)."""
    from servidor.juego import responder, cerrada, tick
    from servidor.estado import SALAS, partida
    clientes = {}

    def mandar(cmd, cuerpo, conexion):
        r = responder(cmd, cuerpo, conexion) or []
        for x in r:
            clientes.setdefault(x[3] if len(x) > 3 else conexion, _ClienteSala()).recibe(x[0], x[1])
        return r

    def f9(conexion):
        """F9: si el cliente larga, el 0x104E al server; → (lo del cliente, lo que contestó el server)."""
        que = clientes[conexion].f9()
        r = mandar(0x104E, b"", conexion) if que == "larga" else []
        if any(x[0] == 0x1050 for x in r):
            que = "cartel (server 0x1050)"
        return que, r

    def limpiar(*conexiones):
        for n in conexiones:
            partida(n).pop("sala", None)
            clientes.pop(n, None)

    def reparto():                              # un 0x102D del inventario (sin cambios de verdad)
        return b"\0" * 4 + struct.pack("<I6H", 0x89A368, 0, 0, 0, 0, 0, 0) + struct.pack("<HHH", 0, 0, 0)
    sala = bytearray(0x59)
    struct.pack_into("<H", sala, 4, 0xFFFF)
    struct.pack_into("<I", sala, 0x28, 1011)
    sala[0x2F] = 3
    crear = b"\0\0\0\0" + bytes(sala)
    entrar = lambda num: struct.pack("<IH", 0, num) + bytes(20)
    for n in list(SALAS):
        del SALAS[n]

    # 1) SOLO: crear, al inventario, cambiar algo (0x102D → 0x102E modo 9), volver y F9
    mandar(0x101D, crear, 601)
    num = partida(601)["sala"]
    chequear("ready: solo, recién creada → F9 larga", clientes[601].f9() == "larga")
    mandar(0x104C, b"\0", 601)
    r = mandar(0x102D, reparto(), 601)
    m9 = next(x for x in r if x[0] == 0x102E)
    chequear("★ ready: el 0x102E modo 9 de la vuelta del inventario NO trae al propio (N = 0 estando solo)",
             m9[1][2] == 9 and m9[1][3 + 9 + 0x59] == 0, len(m9[1]))
    que, r = f9(601)
    chequear("★ ready: solo, después del inventario → F9 larga (antes: cartel «All users must be ready»)",
             que == "larga" and any(x[0] == 0x104F for x in r), que)
    for n in list(SALAS):
        del SALAS[n]
    limpiar(601)

    # 2) DOS: el invitado no listo → cartel; listo → larga; tras el inventario del ANFITRIÓN, el listo del otro sigue
    mandar(0x101D, crear, 601)
    num = partida(601)["sala"]
    mandar(0x101F, entrar(num), 602)
    chequear("ready: dos, el invitado sin F9 → el anfitrión ve el cartel", f9(601)[0] == "cartel")
    chequear("★ el revés: y el server tampoco larga si el cliente lo intentara (0x1050)",
             any(x[0] == 0x1050 for x in responder(0x104E, b"", 601)))
    mandar(0x1047, bytes([clientes[602].yo, 1]), 602)
    mandar(0x104C, b"\0", 601)
    mandar(0x102D, reparto(), 601)
    chequear("ready: el anfitrión vuelve del inventario y el invitado sigue LISTO en su lista",
             clientes[601].otros == {clientes[602].yo: [1, 0]}, clientes[601].otros)
    # el invitado se va al inventario: se le apaga el listo y el anfitrión se entera
    mandar(0x104C, b"\0", 602)
    chequear("★ ready: el invitado al inventario → el anfitrión lo ve NO listo (cartel, no larga sin él)",
             f9(601)[0] == "cartel")
    mandar(0x102D, reparto(), 602)
    mandar(0x1047, bytes([clientes[602].yo, 1]), 602)
    que, r = f9(601)
    chequear("ready: los dos listos → larga, y el 0x104F a los dos",
             que == "larga" and sorted(x[3] for x in r if x[0] == 0x104F) == [601, 602], que)
    chequear("ready: al largar, el server olvida los listos (la próxima vuelta, todos de nuevo)",
             SALAS[num]["listos"] == set())
    for n in list(SALAS):
        del SALAS[n]
    limpiar(601, 602)

    # 3) DOS: el invitado se DESCONECTA → el anfitrión, solo, larga (antes quedaba un fantasma «no listo»)
    mandar(0x101D, crear, 601)
    num = partida(601)["sala"]
    mandar(0x101F, entrar(num), 602)
    cerrada(602)
    for x in tick([601]):
        clientes[601].recibe(x[0], x[1])
    chequear("★ ready: el invitado se desconecta → sale de la lista del anfitrión (sin fantasma)",
             clientes[601].otros == {} and SALAS[num]["miembros"] == [601], clientes[601].otros)
    chequear("ready: … y el anfitrión, solo, larga", f9(601)[0] == "larga")
    for n in list(SALAS):
        del SALAS[n]
    limpiar(601, 602)

    # 4) DOS: se va el ANFITRIÓN → el que queda es anfitrión EN SU CLIENTE y larga solo
    mandar(0x101D, crear, 601)
    num = partida(601)["sala"]
    mandar(0x101F, entrar(num), 602)
    mandar(0x1045, b"", 601)
    chequear("★ ready: se va el anfitrión → el otro queda anfitrión en su cliente (+0x29D = su +0x706)",
             clientes[602].anfitrion == clientes[602].yo == 1, (clientes[602].anfitrion, clientes[602].yo))
    chequear("ready: … y larga solo", f9(602)[0] == "larga")
    for n in list(SALAS):
        del SALAS[n]
    limpiar(601, 602)

    # 5) TRES: se va el del medio, después el último → el anfitrión no queda con un fantasma
    mandar(0x101D, crear, 601)
    num = partida(601)["sala"]
    mandar(0x101F, entrar(num), 602)
    mandar(0x101F, entrar(num), 603)
    mandar(0x1045, b"", 602)
    mandar(0x1047, bytes([clientes[603].yo, 1]), 603)
    chequear("★ ready: tres, se fue el del medio: el «listo» del último le llega al anfitrión",
             clientes[601].otros == {2: [1, 0]}, clientes[601].otros)
    mandar(0x1045, b"", 603)
    chequear("★ ready: … y cuando se va el último, la lista queda vacía (sin fantasma) y larga solo",
             clientes[601].otros == {} and clientes[601].f9() == "larga", clientes[601].otros)
    mandar(0x101F, entrar(num), 604)
    chequear("ready: el que entra después toma el número libre más bajo y ve al anfitrión con su número",
             clientes[604].yo == 1 and clientes[604].anfitrion == 0 and set(clientes[604].otros) == {0},
             (clientes[604].yo, clientes[604].anfitrion, clientes[604].otros))
    for n in list(SALAS):
        del SALAS[n]
    limpiar(601, 602, 603, 604)

    # 6) SOLO, varias vueltas: crear → largar → volver (0x1074/0x1075) → crear otra → largar
    for vuelta in range(3):
        mandar(0x101D, crear, 601)
        que, r = f9(601)
        mandar(0x1074, b"\0", 601)
        chequear("ready: solo, vuelta %d: larga y vuelve al lobby sin arrastrar listos" % (vuelta + 1),
                 que == "larga" and clientes[601].otros == {}, que)
    for n in list(SALAS):
        del SALAS[n]
    limpiar(601)

    # 7) DOS en la stage: el ANFITRIÓN abandona (0x1074) → sale de la sala; al invitado, que sigue jugando,
    #    le llega el «se fue» (0x1058 tipo 3) y queda anfitrión; lo de su stage (0x105C) ya NO va al que se
    #    fue (medido 18-nov 10:19:37: el 0x105D en el lobby cerró el juego del anfitrión)
    mandar(0x101D, crear, 601)
    num = partida(601)["sala"]
    mandar(0x101F, entrar(num), 602)
    mandar(0x1047, bytes([clientes[602].yo, 1]), 602)
    chequear("abandono: los dos listos y larga", f9(601)[0] == "larga")
    r = mandar(0x1074, b"\0", 601)
    chequear("★ abandono del anfitrión: 0x1075 primero, y sale de la sala del server",
             r[0][0] == 0x1075 and partida(601).get("sala") is None and SALAS[num]["miembros"] == [602])
    chequear("★ abandono del anfitrión: el invitado recibe 0x1058 tipo 3 y queda anfitrión en su cliente",
             clientes[602].anfitrion == clientes[602].yo and clientes[602].otros == {},
             (clientes[602].anfitrion, clientes[602].yo, clientes[602].otros))
    r = responder(0x105C, b"\1\2\3\4", 602)
    chequear("★ abandono del anfitrión: lo de la stage del invitado (0x105D) ya no le llega al que se fue",
             not any(len(x) > 3 and x[3] == 601 for x in r), r)
    r = mandar(0x102D, reparto(), 601)
    chequear("★ abandono: el inventario desde el lobby vuelve al LOBBY (modo 3), no a una sala fantasma (modo 9)",
             any(x[0] == 0x102E and x[1][2] == 3 for x in r))
    mandar(0x1074, b"\0", 602)
    chequear("abandono: cuando sale el último, la sala desaparece (sin sala fantasma en el lobby)", num not in SALAS)
    limpiar(601, 602)

    # 8) TRES: el anfitrión se va de la SALA (0x1045) → el siguiente es anfitrión para todos
    mandar(0x101D, crear, 601)
    num = partida(601)["sala"]
    mandar(0x101F, entrar(num), 602)
    mandar(0x101F, entrar(num), 603)
    mandar(0x1045, b"", 601)
    chequear("★ tres, se va el anfitrión: 602 queda anfitrión en su cliente y 603 lo ve así",
             clientes[602].anfitrion == clientes[602].yo == 1 and clientes[603].anfitrion == 1
             and set(clientes[603].otros) == {1} and set(clientes[602].otros) == {2},
             (clientes[602].anfitrion, clientes[602].yo, clientes[603].anfitrion, clientes[603].otros))
    chequear("tres, se va el anfitrión: el nuevo no larga sin el «listo» del otro", clientes[602].f9() == "cartel")
    mandar(0x1047, bytes([clientes[603].yo, 1]), 603)
    chequear("tres, se va el anfitrión: con el listo del otro, larga", f9(602)[0] == "larga")
    for x in (602, 603):
        mandar(0x1074, b"\0", x)
    chequear("tres: abandonan los dos → la sala desaparece", num not in SALAS)
    limpiar(601, 602, 603)

    # 9) TRES en la stage: el anfitrión abandona → los otros dos siguen; el nuevo anfitrión es el mismo para ambos
    mandar(0x101D, crear, 601)
    num = partida(601)["sala"]
    mandar(0x101F, entrar(num), 602)
    mandar(0x101F, entrar(num), 603)
    for x in (602, 603):
        mandar(0x1047, bytes([clientes[x].yo, 1]), x)
    f9(601)
    mandar(0x1074, b"\0", 601)
    chequear("★ tres en la stage, abandona el anfitrión: los dos que quedan tienen el mismo anfitrión (602)",
             clientes[602].anfitrion == clientes[603].anfitrion == clientes[602].yo
             and 0 not in clientes[602].otros and 0 not in clientes[603].otros)
    r = responder(0x105C, b"\1\2\3\4", 603)
    chequear("tres en la stage: lo de la stage va sólo a los que siguen",
             sorted(x[3] for x in r if x[0] == 0x105D) == [602], r)
    for x in (602, 603):
        mandar(0x1074, b"\0", x)
    limpiar(601, 602, 603)
    for n in list(SALAS):
        del SALAS[n]


def pruebas_salida_stage(chequear):
    """★ (Punto 3, 18-nov 11:48) con uno todavía en la stage, la sala no se reabre; y el 0x1075 de «no revivir»."""
    from servidor.juego import responder
    from servidor.estado import SALAS, partida
    sala = bytearray(0x59)
    struct.pack_into("<H", sala, 4, 0xFFFF)
    struct.pack_into("<I", sala, 0x28, 1011)
    sala[0x2F] = 3
    for n in list(SALAS):
        del SALAS[n]
    responder(0x101D, b"\0\0\0\0" + bytes(sala), 701)
    num = partida(701)["sala"]
    responder(0x101F, struct.pack("<IH", 0, num) + bytes(20), 702)
    responder(0x1047, b"\1\1", 702)
    responder(0x104E, b"", 701)
    responder(0x1074, b"\0", 702)                     # el invitado abandona; el anfitrión sigue
    chequear("★ salida: abandona el invitado y el anfitrión sigue → la sala sigue «Playing» (no se entra)",
             SALAS[num].get("jugando") is True)
    from servidor.juego import tick
    lista = [x for x in tick([701, 702]) if x[0] == 0x101C and x[3] == 702]
    chequear("salida: el lobby la ve «Playing» (estado 2) con 1 jugador (como el 12:54:17 medido)",
             lista and lista[0][1][4 + 4 + 0x2D] == 2 and lista[0][1][4 + 4 + 0x2E] == 1)
    r = responder(0x101F, struct.pack("<IH", 0, num) + bytes(20), 702)
    chequear("★ salida: el que se fue NO puede volver a entrar mientras el otro juega (sin 0x1059 al que juega)",
             r[0][0] == 0x1020 and r[0][1][:2] == b"\0\0" and not any(len(x) > 3 and x[3] == 701 for x in r)
             and SALAS[num]["miembros"] == [701], r[:2])
    r = responder(0x1025, b"", 702)
    chequear("salida: tampoco por Quick Join", struct.unpack_from("<H", r[0][1])[0] != 1)
    # el que terminó la stage (0x1064) vuelve a la sala; si es el último, la sala se reabre
    p = partida(701)
    p.update(inicio=__import__("time").time() - 30, resultado_guardado=False)
    responder(0x1064, b"", 701)
    chequear("salida: termina el último que jugaba → la sala vuelve a «Waiting» con él solo",
             SALAS[num].get("jugando") is False and SALAS[num]["miembros"] == [701])
    lista = [x for x in tick([701, 702]) if x[0] == 0x101C and x[3] == 702]
    chequear("★ salida: el lobby RECIBE la lista nueva (0x101C) con la sala en «Waiting» (estado 1) y 1 jugador",
             lista and lista[0][1][4 + 4 + 0x2D] == 1 and lista[0][1][4 + 4 + 0x2E] == 1,
             lista[0][1][4 + 4 + 0x2D:4 + 4 + 0x2F].hex() if lista else "sin 0x101C")
    r = responder(0x1025, b"", 702)
    chequear("salida: con la sala en «Waiting», Quick Join sí entra", struct.unpack_from("<HH", r[0][1]) == (1, num))
    chequear("salida: … y como anfitrión solo puede largar (F9)", any(x[0] == 0x104F for x in responder(0x104E, b"", 701)))
    from servidor.salas import lista_salas
    chequear("salida: tras largar, la lista dice «Playing» (estado 2)", lista_salas()[4 + 4 + 0x2D] == 2)
    responder(0x1074, b"\0", 701)
    # «Cancel» al revivir (0x106A con 0) → 0x1075: también sale de la sala
    responder(0x101D, b"\0\0\0\0" + bytes(sala), 703)
    num = partida(703)["sala"]
    responder(0x104E, b"", 703)
    r = responder(0x106A, b"\0\0", 703)
    chequear("★ salida: «no revivir» (0x106A) → 0x1075 y sale de la sala (sin sala fantasma)",
             any(x[0] == 0x1075 for x in r) and num not in SALAS and partida(703).get("sala") is None)
    for n in list(SALAS):
        del SALAS[n]
    for n in (701, 702, 703):
        partida(n).pop("sala", None)
