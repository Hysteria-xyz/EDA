r"""servidor/partida.py -- la PARTIDA: cargar, morir y revivir, el final de la stage, las cartas
y el premio. Y el «estoy vivo» (0x1001), que es por donde sale lo pendiente por tiempo.
"""
import json
import os
import random
import re
import struct
import time

from servidor import config
from servidor.registro import maneja
from servidor.estado import PARTIDAS, SALAS, partida, numero
from servidor.cuentas import guardar, nivel
from servidor.datos import ESCENARIOS, NADA, PRECIOS, RANKRATE, puntos_de, tabla_premios
from servidor.objetos import inventario, libre_en_bolsa, registro_item, serial_nuevo


_EXISTEN = None


def existe_en_cliente(tipo):
    """★ (20-nov) ¿el cliente conoce ese tipo de ítem (ItemTypeList.xml)? StageReward.xml pide ítems que el
    cliente no define: el 26004 en las 17 variantes Normal 1032 … 1202 (datos/ del repo) y 26004–26006 en las 47
    variantes Normal 1032 … 1502 (el XML que guardó el juego del dueño). ItemTypeList.xml está completo (sus
    propios NUM: 192 equipos, 60 piedras, 6 pociones = 26001–26003 y 26101–26103, 46 libros, 4 varios = 308), la
    tienda (Product.xml) no los vende y el exe no los nombra: no se inventan. Se saltean y el resto del premio
    (oro, EXP, los demás ítems) sigue igual. Sin el XML, se da por bueno (como antes)."""
    global _EXISTEN
    if _EXISTEN is None:
        try:
            _EXISTEN = {int(i) for i in re.findall(rb'<ITEMTYPE ID="(\d+)"', open(config.TIPOS_XML, "rb").read())}
        except OSError:
            _EXISTEN = set()
    return not _EXISTEN or tipo in _EXISTEN


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
        elif tipo_p == 2 and dato != NADA and existe_en_cliente(dato):
            try:
                # un libro de habilidad llega SIN verificar (para eso está el Skill Check Scroll)
                cas = libre_en_bolsa(inv)
                it = [dato, max(1, cant), cas, serial_nuevo(inv),
                      0 if 31000 <= dato <= 33999 else 1]
                inv.append(it)
                nuevos.append(it)
            except StopIteration:
                pass
    c["items"] = inv
    return nuevos


def premio_de_carta(escenario):
    """★ Lo que trae una CARTA: UN presente de la lista de su stage en StageReward.xml (todas las
    stages traen GiveCount="1": un solo presente → lo que destapa la carta). Al azar entre los
    ítems (Type 2) que no son «None» (40071); 🟡 sin pesos, el XML no trae probabilidades.
    Devuelve (tipo de ítem, cantidad) o None si la stage no tiene ítems."""
    _, lista = tabla_premios().get(escenario, (0, []))
    items = [(d, max(1, n)) for t, d, n in lista if t == 2 and d != NADA and existe_en_cliente(d)]
    return random.choice(items) if items else None


def cerrar_por_bajas(p, conexion):
    """★ CIERRE POR BAJAS (medido en 1-4 Fácil: el cliente contó las 92 y NO mandó el 0x1064):
    en solitario, con todas las bajas del catálogo (MONSTER_CNT) y vencida la espera, el server
    cierra la stage como si llegara el 0x1064. Devuelve lo que éste contesta, o []."""
    cierre = p.get("cierre_bajas")
    if (cierre is None or time.monotonic() < cierre or p.get("game_over_en")
            or p.get("resultado_guardado")):
        return []
    s = SALAS.get(p.get("sala"))
    if not (s and s.get("anfitrion") == conexion):
        return []
    from servidor.cuentas import leer
    p["cierre_bajas"] = None
    p["muertos"] = len(p.get("bajas_stage", ()))
    print("Stage %s: objetivo cumplido (%d bajas) sin aviso de fin del cliente"
          % (p.get("escenario"), p["muertos"]), flush=True)
    return fin_de_stage(0x1064, b"", conexion, leer(conexion), p)


def termino_su_stage(s, conexion):
    """★ (Punto 3, 18-nov) La sala vuelve a «Waiting» (se puede entrar) recién cuando NINGUNO sigue en la
    stage. Antes bastaba con que uno terminara o abandonara: con el otro todavía jugando, la sala quedaba
    abierta en el lobby, el que había salido volvía a entrar, y el server le mandaba al que jugaba el
    0x1059 (direcciones P2P: su juego volvía a conectarse con el que se fue, medido 12:06:01 en plena
    stage: el personaje «fantasma») y al que entraba lo de la stage del otro (0x105D en la sala: el juego
    se cerró, 11:56:59.947)."""
    if not s:
        return
    s.setdefault("en_stage", set()).discard(conexion)
    if s.get("partida_id") and s.get("jugando"):
        quedan = sorted(s["en_stage"] & set(s["miembros"]))
        print("partida %s: #%s terminó su stage%s" % (s["partida_id"], conexion,
              " · siguen en la stage: %s" % ", ".join("#%s" % m for m in quedan) if quedan else " · ya no queda nadie"),
              flush=True)
    if not (s["en_stage"] & set(s["miembros"])):
        if s.get("jugando"):
            # ★ (Punto 3, 18-nov 12:58) el lobby se ENTERA de que vuelve a «Waiting» (con el próximo tick, como
            #   cualquier cambio de la lista). Antes el server la reabría pero no mandaba la lista: el lobby
            #   la siguió viendo «Playing» (última lista 12:54:17, la stage terminó 12:58:03, nada hasta 12:58:42)
            from servidor.estado import VIVO
            VIVO.LISTA_CAMBIO = True
        s["jugando"] = False
        s.setdefault("cargados", set()).clear()
        s.pop("largada", None)
        s.pop("carga_desde", None)


def dejar_la_sala(p, conexion):
    """★ (Punto 3, 18-nov) Con el 0x1075 el CLIENTE ya dejó la sala: `0x546F40` vacía su lista de
    jugadores y va al LOBBY (pantalla 3). El server lo dejaba adentro, y entonces:
      · le seguía reenviando lo de la stage de los demás (0x105D…) estando en el lobby → el juego se
        cerraba (medido 18-nov 10:19:37: EXCEPCION 0xC0000005 manejando 0x105D, 4 s después de
        abandonar el anfitrión con el invitado todavía jugando);
      · al volver del inventario desde el lobby (0x102D) le contestaba la SALA vieja (modo 9): una sala
        «fantasma» con datos viejos;
      · los demás lo tenían en su lista (fantasma) y la sala seguía en la lista del lobby.
    Ahora sale como con Leave Room: los que quedan reciben el 0x1058 tipo 3 (su número fijo y el nuevo
    anfitrión; la stage lo atiende en `0x5482A0`, medido 10:18:04 sin problemas), y la sala vacía se borra."""
    from servidor.salas import _sacar_de_sala
    from servidor.estado import VIVO
    num = p.pop("sala", None)
    s = SALAS.get(num)
    if not (s and conexion in s["miembros"]):
        return []
    VIVO.LISTA_CAMBIO = True                               # (la lista del lobby: uno menos o una sala menos)
    return _sacar_de_sala(s, num, conexion)


def game_over(c, p, conexion):
    """★ GAME OVER (medido 16:20–16:26): 0x1069 = modo espectador («<Jump Key> pushing allow
    viewing of other players», sin HUD); con todos muertos (acá: uno solo) no hay a quién mirar
    → 6 s después 0x1075 → el LOBBY (sin caerse). 🟡 Con varios jugadores no se sabe."""
    p["game_over_en"] = None
    c["partidas"] += 1
    guardar(c)
    termino_su_stage(SALAS.get(p.get("sala")), conexion)
    salida = struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"], nivel(c["exp"]),
                         c["exp"], 0, 0)
    return [(0x1069, b"\x00", 0, conexion), (0x1075, salida, 6000, conexion)] + dejar_la_sala(p, conexion)


def numero_jugador(conexion):
    """El número de jugador en su sala (el que el cliente tiene en cuenta+0x705); solo = 0."""
    s = SALAS.get(partida(conexion).get("sala"))
    return numero(s, conexion) if s and conexion in s["miembros"] else 0


def cuerpo_1072(conexion, p):
    """★ 0x1072 AWARD RESULTS (`0x546CA0`): u32 ÍNDICE de StageReward (→ sala+0x148) · u8 N · N ×
    (u8 jugador · u8 1 = «cobra el premio de la stage»). Con [0, 0] (lo de antes) el cliente
    mostraba Gold 0 / Exp 0. Cada jugador de la sala con su 1."""
    s = SALAS.get(p.get("sala"))
    jugadores = ([numero(s, n) for n in s["miembros"]] if s and conexion in s["miembros"]
                 else [numero_jugador(conexion)])
    return struct.pack("<IB", p.get("escenario", 0), len(jugadores)) + b"".join(
        struct.pack("<BB", j, 1) for j in jugadores)


@maneja(0x105F)
def termino_de_cargar(cmd, cuerpo, conexion, c, p):
    """terminó de cargar: corre el reloj"""
    ahora = time.time()
    p.update(inicio=ahora, ultimo_mensaje=ahora, muertos=0, golpes=0, revividas=0, resultado_guardado=False,
             bajas_stage=set(), cierre_bajas=None)
    if p.get("escenario") in ESCENARIOS:
        print(f"[bajas] Stage {p['escenario']}: 0/{ESCENARIOS[p['escenario']][3]}", flush=True)
    # ★ 0x106C (aporte de Hysteria-xyz, PR #3): «activar al jugador en la stage». El manejador del
    #   cliente (`0x547A60`) lee u8 JUGADOR · u8; si el 1º no es su número (cuenta+0x706) no hace nada;
    #   si lo es, entre otras cosas manda «CursorCenter 1» (agarra el mouse). Según el PR, sin él las
    #   habilidades (F1–F8) no se lanzan. ⛔ MEDIDO (MEDICIONES §43): con y sin él, F1 / F2 / F1+clic
    #   derecho NO gastan MP (la barra queda en 210 píxeles) con un Warrior nivel 10 con sus habilidades
    #   en la barra. Como además agarra el mouse, va APAGADO: se prende con <EDA_ESTADO>/con_106c.
    def activar(destinos, total):
        if not os.path.exists(os.path.join(config.ESTADO, "con_106c")):
            return []
        return [(0x106C, struct.pack("<BB", i, i), 0, n) for n in destinos for i in total]
    # ★ con varios: la largada (0x105E) recién cuando cargaron TODOS, y a todos juntos
    s = SALAS.get(p.get("sala"))
    if s and conexion in s["miembros"] and len(s["miembros"]) > 1 and s.get("jugando"):
        if s.get("largada"):
            # ★ (20-nov) ya se largó (por tiempo o porque los demás estaban): el que llega tarde larga
            #   SOLO él. Antes se repetía el 0x105E a TODOS (una 2.ª largada en plena stage).
            print("[carga] sala %s: #%d terminó de cargar después de la largada: larga sólo él"
                  % (p.get("sala"), conexion), flush=True)
            return [(0x105E, struct.pack("<HI", 1, 600), 0)] + activar([conexion], [numero(s, conexion)])
        s.setdefault("cargados", set()).add(conexion)
        s.setdefault("carga_desde", time.monotonic())
        return largar_si_cargaron(s)
    return [(0x105E, struct.pack("<HI", 1, 600), 0)] + activar([conexion], [numero_jugador(conexion)])


# ★ (20-nov, multijugador) cuánto se espera a los que no terminan de cargar. Medido: los dos cargan en
#   1–2 s (18-nov, 19-nov: 0x104F → 0x105F). Con uno colgado o que se fue, los demás quedaban en la
#   pantalla de carga PARA SIEMPRE (la largada sólo se miraba al llegar un 0x105F).
ESPERA_CARGA = float(os.environ.get("EDA_ESPERA_CARGA") or 45)


def largar_si_cargaron(s, por_tiempo=False):
    """La largada (0x105E) a los que ya cargaron, UNA sola vez: cuando cargaron todos los que siguen en la
    sala o, `por_tiempo`, a los que llegaron. Los que cargan después largan solos (`termino_de_cargar`)."""
    if not s.get("jugando") or s.get("largada"):
        return []
    miembros = list(s["miembros"])
    listos = [n for n in miembros if n in s.get("cargados", ())]
    if not listos or (not por_tiempo and len(listos) < len(miembros)):
        return []
    s["largada"] = True
    if len(listos) < len(miembros):
        print("[carga] ⚠ a los %g s largan %s; todavía cargando: %s"
              % (ESPERA_CARGA, listos, [n for n in miembros if n not in listos]), flush=True)
    r = [(0x105E, struct.pack("<HI", 1, 600), 0, n) for n in listos]
    if os.path.exists(os.path.join(config.ESTADO, "con_106c")):
        r += [(0x106C, struct.pack("<BB", i, i), 0, n) for n in listos for i in [numero(s, m) for m in listos]]
    return r


def vigilar_cargas(salas):
    """Del `tick`: las salas que esperan a alguien más de ESPERA_CARGA segundos largan con los que cargaron."""
    r = []
    for s in list(salas.values()):
        if (s.get("jugando") and not s.get("largada") and s.get("cargados")
                and time.monotonic() - s.get("carga_desde", time.monotonic()) >= ESPERA_CARGA):
            r += largar_si_cargaron(s, por_tiempo=True)
    return r


# ★ (22-nov, multijugador) cuánto tiempo sin ningún mensaje del máster en plena stage (ni el 0x1001 de cada 20 s
#   ni eventos 0x105C/0x1061) antes de darlo por colgado y cerrar la stage de forma limpia para los demás.
ESPERA_MASTER = float(os.environ.get("EDA_ESPERA_MASTER") or 60)


def cerrar_stage_por_master(s, master, motivo="salió"):
    """★ (22-nov) Si el máster de la partida sale (0x1074/0x1045), se desconecta o se cuelga en plena stage
    (después de la largada), en el cliente de 2009 el 0x1058 tipo 3 prende +0x168 en el nuevo anfitrión
    (`0x5482A0` → `0x63EFA0`), pero NO transfiere el estado del guion Lua ni de las oleadas ya lanzadas por el
    máster anterior (medido en TEST el 22-nov: en P-20261122-162832-s1 el nuevo máster quedó en 76/78 bajas sin
    que el guion dispare nunca el 0x1064, y en P-20261122-163025-s2 quedó a 14 FPS con 0 bajas). Para que nadie
    quede colgado en la stage, el server cierra la stage de forma limpia (PlayEnd 0x1073 + resultado 0x106E +
    cartas 0x106F) a todos los que siguen en ella."""
    if not s or not s.get("jugando") or not s.get("largada"):
        return []
    from servidor.cuentas import leer
    pm_master = PARTIDAS.get(master) or {}
    equipo = max(pm_master.get("muertos", 0), s.get("muertos_stage", 0))
    quedan = [m for m in list(s["miembros"]) if m != master and m in s.get("en_stage", ())
              and not partida(m).get("resultado_guardado")]
    r = []
    for m in quedan:
        pm = partida(m)
        pm["muertos"] = max(pm.get("muertos", 0), equipo)
        r += [(x[0], x[1], x[2], m) for x in _fin_de_uno(0x1064, b"", m, leer(m), pm)]
    if quedan:
        print("partida %s: el máster #%s %s en plena stage → cierre limpio para %s"
              % (s.get("partida_id", "?"), master, motivo, ", ".join("#%s" % m for m in quedan)), flush=True)
    return r


def vigilar_master(salas, ahora=None):
    """Del `tick`: si el máster de una stage en grupo se cuelga (no manda ni el 0x1001 de cada 20 s ni eventos
    de la stage durante ESPERA_MASTER s), se cierra la stage de forma limpia para todos los que siguen en ella."""
    ahora = time.time() if ahora is None else ahora
    r = []
    for s in list(salas.values()):
        if not (s.get("jugando") and s.get("largada") and len(s.get("en_stage", ())) >= 2):
            continue
        m = s.get("anfitrion")
        if m not in s.get("en_stage", ()):
            continue
        pm = PARTIDAS.get(m) or {}
        ultimo = pm.get("ultimo_mensaje") or pm.get("inicio") or ahora
        if ahora - ultimo >= ESPERA_MASTER:
            otros = [o for o in s["miembros"] if o != m and o in s.get("en_stage", ())]
            if not otros:
                continue
            r += cerrar_stage_por_master(s, m, motivo="no responde (%d s)" % int(ahora - ultimo))
            termino_su_stage(s, m)
            s["anfitrion"] = otros[0]
            s.get("listos", set()).discard(s["anfitrion"])
    return r


@maneja(0x1061)
def npc_muerto(cmd, cuerpo, conexion, c, p):
    """un NPC muerto [§5.11]: `u8 n · u8 1 · 6 × 0` (n = el NPC). ★ (21-nov) con varios lo manda sólo el máster
    (`0x639AA0`): las bajas son de la partida (`muertos_stage` de la sala), para el resultado de todos."""
    p["muertos"] = p.get("muertos", 0) + 1
    s_ = SALAS.get(p.get("sala"))
    if s_ and s_.get("jugando") and conexion in s_["miembros"]:
        s_["muertos_stage"] = s_.get("muertos_stage", 0) + 1
    esc = p.get("escenario")
    if esc in ESCENARIOS and p.get("inicio") and len(cuerpo) >= 2 and not p.get("resultado_guardado"):
        bajas = p.setdefault("bajas_stage", set())
        antes = len(bajas)
        bajas.add(struct.unpack_from("<H", cuerpo)[0])
        total = ESCENARIOS[esc][3]
        if len(bajas) != antes:
            print(f"[bajas] Stage {esc}: {len(bajas)}/{total}. Restantes según catálogo: "
                  f"{max(0, total - len(bajas))}", flush=True)
        # ★ el cierre por bajas (ver `cerrar_por_bajas`): si el aviso del cliente llega antes,
        #   `resultado_guardado` lo frena; si llega tarde, el 0x1064 no paga dos veces.
        #   🟡 la espera es nuestra (3 s en 1-4 Fácil, la medida; 8 s en las demás)
        s = SALAS.get(p.get("sala"))
        if (s and s.get("anfitrion") == conexion and len(bajas) >= total
                and p.get("cierre_bajas") is None):
            p["cierre_bajas"] = time.monotonic() + (3 if esc == 1041 else 8)
    return []


def en_la_stage(s, conexion):
    """★ (20-nov) A quién se le reenvía lo de la stage: los OTROS de la sala que SIGUEN en ella. Lo midió el
    Punto 3 con el 0x105D (fuera de la stage cierra el juego: 18-nov 10:19:37 en el lobby, 11:56:59 en la
    sala) y se arregló sólo en el 0x105C; el 0x105D, 0x1060, 0x1062, 0x1066 y 0x106D seguían yendo a TODOS
    los de la sala, también al que ya volvió a la sala o a las cartas mientras el otro sigue jugando."""
    en_stage = s.get("en_stage", s["miembros"])
    return [m for m in s["miembros"] if m != conexion and m in en_stage]


@maneja(0x1063)
def le_pegaron(cmd, cuerpo, conexion, c, p):
    """★ le pegaron (0x1063 C→S / 0x1062 S→C `0x547440`, aporte de Hysteria-xyz):
    Difunde la vida y maná actualizados al HUD de los compañeros de equipo."""
    p["golpes"] = p.get("golpes", 0) + 1
    s = SALAS.get(p.get("sala"))
    r = []
    if s and conexion in s["miembros"] and len(s["miembros"]) > 1:
        yo = numero(s, conexion)
        # 0x1062 (16 B, 0x547440): u32 jugador_id · u32 0 · u16 HP · u8 0 · u32 MP · u8 buffs
        hp = struct.unpack_from("<H", cuerpo, 1)[0] if len(cuerpo) >= 3 else 1000
        msg_62 = struct.pack("<IIHBI B", yo, 0, hp, 0, 100, 0)
        for m in en_la_stage(s, conexion):
            r.append((0x1062, msg_62, 0, m))
    return r


@maneja(0x1062)
def sincronizar_hud_companero(cmd, cuerpo, conexion, c, p):
    """★ 0x1062 (`0x547440`, aporte de Hysteria-xyz): retransmite estado de vida/maná a los compañeros."""
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"]:
        return None
    return [(0x1062, cuerpo, 0, m) for m in en_la_stage(s, conexion)]


@maneja(0x1067)
def interactuar_objeto(cmd, cuerpo, conexion, c, p):
    """★ 0x1067 C→S / 0x1066 S→C (`0x547940`, 6 B, aporte de Hysteria-xyz):
    Interacción con cofre/objeto en mapa.
    cuerpo: u32 objeto_id.
    0x1066: u8 jugador_id · u32 objeto_id · u8 estado (1 = abierto/activado)."""
    if len(cuerpo) < 4:
        return []
    obj_id = struct.unpack_from("<I", cuerpo, 0)[0]
    # ★ (medido 14-nov) también es USAR UN ÍTEM de la barra en la stage: `0x50d670` → `0x546280`
    #   («UseItem:%d») manda el SERIAL de la poción. El cliente aplica el efecto solo (el script de
    #   la poción, `0x57ed30`) y baja la pila en pantalla; acá se descuenta de la bolsa. Antes la
    #   pila volvía entera al reconectar (66 usos sin descontar en una partida).
    inv = inventario(c)
    it = next((x for x in inv if x[3] == obj_id), None)
    if it is not None:
        if it[1] > 0:
            it[1] -= 1
            if it[1] <= 0:
                inv.remove(it)
            c["items"] = inv
            guardar(c)
        return []
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"]:
        return []
    yo = numero(s, conexion)
    msg = struct.pack("<BIB", yo, obj_id, 1)
    return [(0x1066, msg, 0, m) for m in s["miembros"]]


@maneja(0x1066)
def sincronizar_objeto_1066(cmd, cuerpo, conexion, c, p):
    """★ 0x1066 (`0x547940`, 6 B): retransmisión de objeto interactivo a compañeros."""
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"]:
        return None
    return [(0x1066, cuerpo, 0, m) for m in en_la_stage(s, conexion)]


@maneja(0x105C)
def evento_guion_escenario(cmd, cuerpo, conexion, c, p):
    """★ 0x105C C→S / 0x105D S→C (`0x546E60`, `0x643750`, aporte de Hysteria-xyz):
    Eventos del guion Lua en partida (puertas, switches, grupos NPC).
    Difunde 0x105D a los demás miembros de la sala para mantener el escenario sincronizado."""
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"] or len(s["miembros"]) <= 1:
        return []
    # ★ (Punto 3) sólo a los que SIGUEN en la stage: el 0x105D fuera de la stage cierra el juego (medido
    #   dos veces el 18-nov: 10:19:37 en el lobby y 11:56:59 en la sala)
    return [(0x105D, cuerpo, 0, m) for m in en_la_stage(s, conexion)]


@maneja(0x105D)
def sincronizar_evento_105d(cmd, cuerpo, conexion, c, p):
    """★ 0x105D (`0x546E60`): retransmisión de evento de escenario."""
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"]:
        return None
    return [(0x105D, cuerpo, 0, m) for m in en_la_stage(s, conexion)]


@maneja(0x1060)
def sincronizar_tick_1060(cmd, cuerpo, conexion, c, p):
    """★ 0x1060 (`0x546D60`, 4 B, aporte de Hysteria-xyz): sincronización de reloj de stage."""
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"]:
        return [(0x1060, cuerpo if len(cuerpo) >= 4 else struct.pack("<I", 0), 0)]
    return [(0x1060, cuerpo, 0, m) for m in en_la_stage(s, conexion)]


@maneja(0x106D)
def sincronizar_tiempo_106d(cmd, cuerpo, conexion, c, p):
    """★ 0x106D (`0x546750`, 16 B, aporte de Hysteria-xyz): temporizador y cuenta regresiva de stage."""
    s = SALAS.get(p.get("sala"))
    if not s or conexion not in s["miembros"]:
        return [(0x106D, cuerpo if len(cuerpo) >= 16 else bytes(16), 0)]
    return [(0x106D, cuerpo, 0, m) for m in en_la_stage(s, conexion)]


@maneja(0x1001)
def estoy_vivo(cmd, cuerpo, conexion, c, p):
    """«estoy vivo», cada 20 s [§5.3]"""
    # ★ el único momento en que el server puede hablar sin que le pregunten (el espía sólo
    #   contesta): acá sale lo que quedó pendiente por TIEMPO, p. ej. el game over
    r = [(0x1001, b"\x80", 0)]
    cierre = cerrar_por_bajas(p, conexion)
    if cierre:
        return r + [x[:3] for x in cierre]
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
        p["revividas"] = p.get("revividas", 0) + 1
        guardar(c)
    r = [(0x106B, struct.pack("<HBHB", 1, 1 if si else 0, c["monedas"], 0), 0)]
    s = SALAS.get(p.get("sala"))
    if si and s and conexion in s["miembros"] and len(s["miembros"]) > 1:
        yo = numero(s, conexion)
        msg_otro = struct.pack("<HBHB", 1, 2, c["monedas"], yo)
        for m in s["miembros"]:
            if m != conexion:
                r.append((0x106B, msg_otro, 0, m))
    if not si:
        # «Cancel» o sin monedas: modo 0 = espectador (estado 0xA) → como el game over, al
        # lobby a los 6 s (🟡 con un solo jugador; con más, seguiría mirando)
        c["partidas"] += 1
        guardar(c)
        r.append((0x1075, struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"],
                                      nivel(c["exp"]), c["exp"], 0, 0), 6000))
        termino_su_stage(SALAS.get(p.get("sala")), conexion)
        r += dejar_la_sala(p, conexion)             # ★ (Punto 3) también este 0x1075 lo saca de la sala
    return r


@maneja(0x1064)
def fin_de_stage(cmd, cuerpo, conexion, c, p):
    """★ la stage terminó [§5.13, §5.14].
    ★ (21-nov) CON VARIOS, el fin es de TODA la partida. Medido en el exe: el guion avisa el fin por
    `SendEvent` (`0x636EA0`), que sólo llama al delegado que manda el 0x1064 (`0x546480`) si la bandera
    `+0x168` del administrador de escenarios está prendida; esa bandera es la del MÁSTER de la partida (se copia
    de la red en `0x64583F`; la prende `0x749020` y la apaga `0x747220`, y el 0x1058 tipo 3 se la pasa al nuevo
    anfitrión en `0x50C2DB` / `0x54851C`). Lo mismo las bajas (0x1061, `0x639AA0`). O sea: los demás NUNCA mandan
    su 0x1064 y su escenario no termina solo. Medido en el server de prueba (21-nov 16:58): el anfitrión terminó
    y volvió a la sala; el invitado quedó en la stage. Ahora el 0x1064 del máster cierra la stage de todos los que
    SIGUEN en ella (cada uno con su resultado y sus cartas); el de otro (no debería llegar) cierra sólo la suya."""
    r = _fin_de_uno(cmd, cuerpo, conexion, c, p)
    s = SALAS.get(p.get("sala"))
    if not (s and conexion in s["miembros"] and len(s["miembros"]) > 1):
        return r
    if s.get("anfitrion") != conexion:
        if r:
            print("partida %s: 0x1064 de #%s, que no es el máster (#%s): sólo su resultado"
                  % (s.get("partida_id", "?"), conexion, s.get("anfitrion")), flush=True)
        return r
    from servidor.cuentas import leer
    equipo = max(p.get("muertos", 0), s.get("muertos_stage", 0))
    otros = [m for m in en_la_stage(s, conexion) if not partida(m).get("resultado_guardado")]
    for m in otros:
        pm = partida(m)
        pm["muertos"] = max(pm.get("muertos", 0), equipo)            # (las bajas son del equipo: las cuenta el máster)
        r += [(x[0], x[1], x[2], m) for x in _fin_de_uno(cmd, b"", m, leer(m), pm)]
    if otros:
        print("partida %s: el máster #%s terminó la stage → también para %s"
              % (s.get("partida_id", "?"), conexion, ", ".join("#%s" % m for m in otros)), flush=True)
    return r


def _fin_de_uno(cmd, cuerpo, conexion, c, p):
    """El fin de la stage de UN jugador: su EXP, su premio, su PlayEnd, su resultado y sus cartas."""
    if p.get("resultado_guardado"):                     # (el aviso tardío no paga dos veces)
        return []
    p["resultado_guardado"] = True
    p["cierre_bajas"] = None
    p["game_over_en"] = None                            # (si estaba muerto esperando: ya no hay game over)
    inicio = p.get("inicio") or time.time()
    ms = int((time.time() - inicio) * 1000)
    # ★ el premio sale del XML del escenario (RANK_POINT, KILL_POINT, TOTALEXP, MONSTER_CNT,
    #   RANKRATE). Si no estaba en p, sale de la sala
    esc = p.get("escenario")
    if not esc:
        s = SALAS.get(p.get("sala"))
        if s and len(s["sala"]) >= 0x2A:
            esc = struct.unpack_from("<H", s["sala"], 0x28)[0]
    esc = esc or 1011
    p["escenario"] = esc
    rp, kp, te, mc = ESCENARIOS.get(esc, ESCENARIOS[1011])
    muertos = p.get("muertos", 0)
    frac = min(1.0, muertos / float(mc)) if mc > 0 else 1.0
    exp_ganada = max(1, int(round(te * frac)))
    # ★ (20-nov, Paso 6, decisión del dueño) sin el oro inventado (100 + 10 × bajas): el oro del Stage es SÓLO el
    #   de StageReward.xml (Type 0, dar_premio), el que el cliente muestra en AWARD (`0x5FEA50`)
    plata_ganada = 0
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
    resultado = struct.pack("<IHHHIIB", 0, muertos, p.get("golpes", 0), p.get("revividas", 0), ms,
                            p.get("puntos", 0), rango)
    cartas = struct.pack("<IIII", 60000, *PRECIOS)
    p["cartas_hasta"] = time.time() + 8 + 60 + 2          # 0x106F a los 8 s + 60 s + margen
    p["exp_cartas"] = 0
    p["cartas_elegidas"] = set()
    termino_su_stage(SALAS.get(p.get("sala")), conexion)
    if n > antes:
        print("sube de nivel", antes, "→", n)
    # ★ el resultado y las cartas ESPACIADOS (juntos, las cartas tapaban el resultado)
    return [(0x1073, fin, 0), (0x106E, resultado, 300), (0x106F, cartas, 8000)]


@maneja(0x1070)
def elegir_carta(cmd, cuerpo, conexion, c, p):
    """eligió: u8 TIPO · u8 número"""
    if not (len(cuerpo) >= 2):
        return None
    # ★ 0x1070 (`0x546A80`) = u8 TIPO · u8 número. Medido en el exe (13-nov):
    #   · TIPO 0 = una CARTA (doble clic, `0x5007D0`): número de corrido (oro 0–3, plata 4–9,
    #     bronce 10–17; la fila como `0x500810`). El cliente sólo la manda si su casilla en
    #     `+0xF8` (18 × 16 B, `0x6111E0`) está VACÍA (u8 +4 = 0xFF): sin darla vuelta, la volvía a
    #     mandar en cada clic.
    #   · TIPO 1 = el botón «EXP» de una FILA (`0x500840`, controles 0x29–0x2B): número = fila.
    # ★ 0x1071 (`0x546B70`) tiene DOS formas según su 1er byte:
    #   · u8 0 · u8 CARTA · 5 B · u32 puntos que QUEDAN, y 16 B más: la CARA de la carta
    #     (4 B · u8 JUGADOR · u32 EXP (+5) · u32 ORO (+9) · u16 TIPO de ítem · u8 cantidad) →
    #     `0x611BC0` la guarda en la casilla y `0x50E200` dibuja las llenas = la carta SE DA VUELTA
    #     («Mazino · Gold · Exp» y el ícono y nombre del ítem: medido 13-nov).
    #   · u8 1 · u8 FILA · u8 JUGADOR · u32 EXP de cartas acumulada · u32 puntos que QUEDAN → la
    #     flecha EXP de la fila (`0x5095F0`) y la EXP que suma AWARD RESULTS (`0x612AC0`).
    #   Antes iba sólo la forma 1: cobraba y animaba la fila, pero la carta seguía de dorso.
    #   🟡 Cuánta EXP da una carta no se sabe: acá, lo que costó (350 / 150 / 50); oro 0.
    # ★ (PR #5, Urek-Mazinoo) la MISMA carta no se cobra dos veces, ni una fuera de las 18, ni fuera
    #   del tiempo de las cartas, ni una que no alcanza: eso no se contesta.
    tipo, numero = cuerpo[0], cuerpo[1]
    hasta = p.get("cartas_hasta")
    elegidas = p.setdefault("cartas_elegidas", set())
    if not hasta or time.time() >= hasta:
        return []
    if tipo == 0 and numero < 18:
        fila, clave = (0 if numero < 4 else (1 if numero < 10 else 2)), numero
    elif tipo == 1 and numero < 3:
        fila, clave = numero, ("fila", numero)          # 🟡 una vez por fila (sin doble cobro)
    else:
        return []
    precio = PRECIOS[fila]
    if clave in elegidas or p.get("puntos", 0) < precio:
        return []
    elegidas.add(clave)
    p["puntos"] -= precio
    p["exp_cartas"] = p.get("exp_cartas", 0) + precio
    c["exp"] += precio
    premio = premio_de_carta(p.get("escenario")) if tipo == 0 else None
    if premio:                                          # el ítem de la carta, a la bolsa
        dar_premio(c, p.get("escenario"), elegir=(2, premio[0], premio[1]))
    guardar(c)
    jugador = numero_jugador(conexion)
    r = []
    if tipo == 0:                                       # la CARA: la carta se da vuelta
        tipo_it, cant = premio or (0, 0)
        cara = struct.pack("<4xBIIHB", jugador, precio, 0, tipo_it, min(cant, 255))
        r.append((0x1071, struct.pack("<BB5xI", 0, numero, p["puntos"]) + cara, 0))
    r.append((0x1071, struct.pack("<BBBII", 1, fila, jugador, p["exp_cartas"], p["puntos"]), 0))
    if p.get("puntos", 0) < min(PRECIOS):               # ya no alcanza para otra carta
        p["cartas_hasta"] = None
        r.append((0x1072, cuerpo_1072(conexion, p), 1500))
    return r


@maneja(0x1074)
def salir_de_stage(cmd, cuerpo, conexion, c, p):
    """salió de la stage [§5.15]"""
    # ★ (PR #9, Urek-Mazinoo) los relojes de ESA partida se cancelan: si no, el Game Over o las cartas
    #   vencidas llegaban después, ya de vuelta en el lobby
    p["game_over_en"] = None
    p["cartas_hasta"] = None
    c["abandonos"] += 1
    c["partidas"] += 1
    guardar(c)
    termino_su_stage(SALAS.get(p.get("sala")), conexion)
    salida = struct.pack("<HHIBIHB", 1, c["monedas"], c["abandonos"], nivel(c["exp"]),
                         c["exp"], 0, 0)
    return [(0x1075, salida, 0)] + dejar_la_sala(p, conexion)
