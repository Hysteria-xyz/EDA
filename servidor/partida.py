r"""servidor/partida.py -- la PARTIDA: cargar, morir y revivir, el final de la stage, las cartas
y el premio. Y el «estoy vivo» (0x1001), que es por donde sale lo pendiente por tiempo.
"""
import json
import os
import struct
import time

from servidor import config
from servidor.registro import maneja
from servidor.estado import SALAS, partida
from servidor.cuentas import guardar, nivel
from servidor.datos import ESCENARIOS, NADA, PRECIOS, RANKRATE, puntos_de, tabla_premios
from servidor.objetos import inventario, libre_en_bolsa, registro_item, serial_nuevo


def dar_premio(c, escenario, elegir=None):
    """★ El premio de la stage = TODA su lista de StageReward.xml, como la suma el cliente en
    AWARD RESULTS (`0x612B40`: con el 0x1072 [índice, (jugador, 1)] llama a `0x5FEA50` = Σ Data de
    Type 0 → ORO, `0x5FEAA0` = Σ Type 1 → EXP, `0x5FEAF0` = lista los Type 2 → ÍTEMS, sin filtrar por
    clase). 🟡 Qué hacía GiveCount no se sabe; así lo que se ve es lo que se recibe. Devuelve los
    ítems nuevos (ya en c) para el PlayEnd. `elegir` (pruebas): dar sólo ese presente."""
    _, lista = tabla_premios().get(escenario, (0, []))
    nuevos = []
    inv = inventario(c)
    for tipo_p, dato, cant in ([elegir] if elegir else lista):
        if tipo_p == 0:
            c["plata"] += dato
        elif tipo_p == 1:
            c["exp"] += dato
        elif tipo_p == 2 and dato != NADA:
            # un libro de habilidad llega SIN verificar (para eso está el Skill Check Scroll)
            it = [dato, max(1, cant), libre_en_bolsa(inv), serial_nuevo(inv),
                  0 if 31000 <= dato <= 33999 else 1]
            inv.append(it)
            nuevos.append(it)
    c["items"] = inv
    return nuevos


def game_over(c, p, conexion):
    """★ GAME OVER (medido 16:20–16:26): 0x1069 = modo espectador («<Jump Key> pushing allow
    viewing of other players», sin HUD); con todos muertos (acá: uno solo) no hay a quién mirar
    → 6 s después 0x1075 → el LOBBY (sin caerse). 🟡 Con varios jugadores no se sabe."""
    p["game_over_en"] = None
    c["partidas"] += 1
    guardar(c)
    salida = struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"], nivel(c["exp"]),
                         c["exp"], 0, 0)
    return [(0x1069, b"\x00", 0, conexion), (0x1075, salida, 6000, conexion)]


def numero_jugador(conexion):
    """El número de jugador en su sala (el que el cliente tiene en cuenta+0x705); solo = 0."""
    s = SALAS.get(partida(conexion).get("sala"))
    return s["miembros"].index(conexion) if s and conexion in s["miembros"] else 0


def cuerpo_1072(conexion, p):
    """★ 0x1072 AWARD RESULTS (`0x546CA0`): u32 ÍNDICE de StageReward (→ sala+0x148) · u8 N · N ×
    (u8 jugador · u8 1 = «cobra el premio de la stage»). Con [0, 0] (lo de antes) el cliente
    mostraba Gold 0 / Exp 0. Cada jugador de la sala con su 1."""
    s = SALAS.get(p.get("sala"))
    jugadores = (range(len(s["miembros"])) if s and conexion in s["miembros"]
                 else [numero_jugador(conexion)])
    return struct.pack("<IB", p.get("escenario", 0), len(jugadores)) + b"".join(
        struct.pack("<BB", j, 1) for j in jugadores)


@maneja(0x105F)
def termino_de_cargar(cmd, cuerpo, conexion, c, p):
    """terminó de cargar: corre el reloj"""
    p.update(inicio=time.time(), muertos=0, golpes=0, revividas=0)
    # ★ 0x106C (aporte de Hysteria-xyz, PR #3): «activar al jugador en la stage». El manejador del
    #   cliente (`0x547A60`) lee u8 JUGADOR · u8; si el 1º no es su número (cuenta+0x706) no hace nada;
    #   si lo es, entre otras cosas manda «CursorCenter 1» (agarra el mouse). Según el PR, sin él las
    #   habilidades (F1–F8) no se lanzan. ⛔ MEDIDO (MEDICIONES §43): con y sin él, F1 / F2 / F1+clic
    #   derecho NO gastan MP (la barra queda en 210 píxeles) con un Warrior nivel 10 con sus habilidades
    #   en la barra. Como además agarra el mouse, va APAGADO: se prende con <EDA_ESTADO>/con_106c.
    def activar(destinos, total):
        if not os.path.exists(os.path.join(config.ESTADO, "con_106c")):
            return []
        return [(0x106C, struct.pack("<BB", i, i), 0, n) for n in destinos for i in range(total)]
    # ★ con varios: la largada (0x105E) recién cuando cargaron TODOS, y a todos juntos
    s = SALAS.get(p.get("sala"))
    if s and len(s["miembros"]) > 1:
        s.setdefault("cargados", set()).add(conexion)
        if set(s["miembros"]) <= s["cargados"]:
            return ([(0x105E, struct.pack("<HI", 1, 600), 0, n) for n in s["miembros"]]
                    + activar(s["miembros"], len(s["miembros"])))
        return []
    return [(0x105E, struct.pack("<HI", 1, 600), 0)] + activar([conexion], 1)


@maneja(0x1061)
def npc_muerto(cmd, cuerpo, conexion, c, p):
    """un NPC muerto [§5.11]"""
    p["muertos"] += 1
    return []


@maneja(0x1063)
def le_pegaron(cmd, cuerpo, conexion, c, p):
    """🟡 le pegaron (sale en la pelea)"""
    p["golpes"] += 1
    return []


@maneja(0x1001)
def estoy_vivo(cmd, cuerpo, conexion, c, p):
    """«estoy vivo», cada 20 s [§5.3]"""
    # ★ el único momento en que el server puede hablar sin que le pregunten (el espía sólo
    #   contesta): acá sale lo que quedó pendiente por TIEMPO, p. ej. el game over
    r = [(0x1001, b"\x80", 0)]
    if p.get("game_over_en") and time.time() >= p["game_over_en"]:
        # (con un espía viejo, sin `tick`: sale con el «estoy vivo», hasta 20 s tarde)
        r += [x[:3] for x in game_over(c, p, conexion)]
    if os.path.exists(config.EMPUJAR):
        try:
            for c_hex, cuerpo_hex in json.load(open(config.EMPUJAR, encoding="utf-8")):
                r.append((int(c_hex, 16), bytes.fromhex(cuerpo_hex), 0))
        finally:
            os.remove(config.EMPUJAR)
    return r


@maneja(0x1065)
def murio(cmd, cuerpo, conexion, c, p):
    """murió [§5.12]"""
    # al vencer el tiempo para revivir el cliente NO manda nada (medido 15:19): el game over
    # lo da el server (0x1069, 🟡) si no llegó el «sí» (0x106A) a tiempo
    p["game_over_en"] = time.time() + 15.5
    return [(0x1068, struct.pack("<I", 15000), 0)]


@maneja(0x106A)
def usar_moneda(cmd, cuerpo, conexion, c, p):
    """¿usar moneda?"""
    p["game_over_en"] = None
    si = len(cuerpo) >= 2 and cuerpo[1] == 1 and c["monedas"] > 0
    if si:
        c["monedas"] -= 1
        p["revividas"] += 1
        guardar(c)
    r = [(0x106B, struct.pack("<HBHB", 1, 1 if si else 0, c["monedas"], 0), 0)]
    if not si:
        # «Cancel» o sin monedas: modo 0 = espectador (estado 0xA) → como el game over, al
        # lobby a los 6 s (🟡 con un solo jugador; con más, seguiría mirando)
        c["partidas"] += 1
        guardar(c)
        r.append((0x1075, struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"],
                                      nivel(c["exp"]), c["exp"], 0, 0), 6000))
    return r


@maneja(0x1064)
def fin_de_stage(cmd, cuerpo, conexion, c, p):
    """★ la stage terminó [§5.13, §5.14]"""
    ms = int((time.time() - (p["inicio"] or time.time())) * 1000)
    # ★ el premio sale del XML del escenario (RANK_POINT, KILL_POINT, TOTALEXP, MONSTER_CNT,
    #   RANKRATE). 🟡 CÓMO los combinaba Softnyx no se sabe: acá, proporcional a los NPC muertos
    rp, kp, te, mc = ESCENARIOS.get(p["escenario"], ESCENARIOS[1011])
    frac = min(1.0, p["muertos"] / float(mc))
    exp_ganada = max(1, int(round(te * frac)))
    plata_ganada = 100 + 10 * p["muertos"]              # 🟡 la plata: inventada
    rango_xml = next((5 - i for i, corte in enumerate(RANKRATE) if frac >= corte), 1)
    antes = nivel(c["exp"])
    c["exp"] += exp_ganada
    c["plata"] += plata_ganada
    c["partidas"] += 1
    if p["escenario"] not in c["terminadas"]:
        c["terminadas"].append(p["escenario"])
    # ★ el PREMIO de StageReward.xml: va en el PlayEnd (N1 × ítem de 21 B, con la ficha
    #   pegada si es equipo: +0x11 = −1, `0x548C54`) y entra a la bolsa
    nuevos = dar_premio(c, p["escenario"])
    p["premio"] = [it[0] for it in nuevos]
    guardar(c)
    n = nivel(c["exp"])
    p["puntos"] = puntos_de(te, frac)
    extra = os.path.join(config.ESTADO, "puntos_extra")   # (para probar a mano)
    if os.path.exists(extra):
        p["puntos"] += int(open(extra).read().strip() or 0)
    rango = rango_xml                                   # 1 = D (medido) … 5 = S (supuesto)
    regs = b"".join(b"".join(registro_item(it[3], it[0], it[1], it[2], it[4], pegada=True))
                    for it in nuevos)
    fin = (struct.pack("<HHIIHB", 1, c["monedas"], c["plata"], c["exp"], 0, n)
           + struct.pack("<IIBB", 0, p["escenario"], 1, 1) + bytes([len(nuevos), 0, 0])
           + regs + bytes([0]))
    resultado = struct.pack("<IHHHIIB", 0, p["muertos"], p["golpes"], p["revividas"], ms,
                            p["puntos"], rango)
    cartas = struct.pack("<IIII", 60000, *PRECIOS)
    p["cartas_hasta"] = time.time() + 8 + 60 + 2          # 0x106F a los 8 s + 60 s + margen
    p["exp_cartas"] = 0
    p["cartas_elegidas"] = set()
    if n > antes:
        print("sube de nivel", antes, "→", n)
    # ★ el resultado y las cartas ESPACIADOS (juntos, las cartas tapaban el resultado)
    return [(0x1073, fin, 0), (0x106E, resultado, 300), (0x106F, cartas, 8000)]


@maneja(0x1070)
def elegir_carta(cmd, cuerpo, conexion, c, p):
    """eligió una carta: u8 fila · u8 carta"""
    if not (len(cuerpo) >= 2):
        return None
    # ★ 0x1071 (`0x546B70`, 11 B): u8 1 · u8 FILA (la animación, `0x5095F0`) · u8 JUGADOR ·
    #   u32 EXP ganada con cartas (acumulada → `0x612AC0`; la carta muestra la diferencia) ·
    #   u32 puntos que QUEDAN (→ +0x251). ⚠ Antes iba el número de CARTA donde va el jugador:
    #   el cliente lo compara con el suyo (cuenta+0x705) y, distinto, NO da vuelta la carta
    #   (El tester, 19:55: «la tarjeta no se volteó»).
    #   🟡 Cuánta EXP da una carta no se sabe: acá, lo que costó (350 / 150 / 50).
    # ⚠ el 0x1070 es u8 · u8 CARTA numerada de corrido (oro 0–3, plata 4–9, bronce 10–17;
    #   medido 20:00: la 1ª de oro = «00 00», la 1ª de bronce = «00 0a») → la fila como la
    #   saca el cliente (`0x500810`). Antes se tomaba el 1er byte como fila: siempre «oro».
    carta_n = cuerpo[1]
    hasta = p.get("cartas_hasta")
    if not hasta or time.time() >= hasta or carta_n >= 18:
        return []
    elegidas = p["cartas_elegidas"]
    fila = 0 if carta_n < 4 else (1 if carta_n < 10 else 2)
    precio = PRECIOS[fila]
    if carta_n in elegidas or p["puntos"] < precio:
        return []
    c["exp"] += precio
    guardar(c)
    elegidas.add(carta_n)
    p["puntos"] -= precio
    p["exp_cartas"] += precio
    carta = struct.pack("<BBBII", 1, fila, numero_jugador(conexion), p.get("exp_cartas", 0),
                        p.get("puntos", 0))
    r = [(0x1071, carta, 0)]
    if p.get("puntos", 0) < min(PRECIOS):               # ya no alcanza para otra carta
        p["cartas_hasta"] = None
        r.append((0x1072, cuerpo_1072(conexion, p), 1500))
    return r


@maneja(0x1074)
def salir_de_stage(cmd, cuerpo, conexion, c, p):
    """salió de la stage [§5.15]"""
    p["game_over_en"] = None
    p["cartas_hasta"] = None
    c["abandonos"] += 1
    c["partidas"] += 1
    guardar(c)
    salida = struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"], nivel(c["exp"]),
                         c["exp"], 0, 0)
    return [(0x1075, salida, 0)]
