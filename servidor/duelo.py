r"""servidor/duelo.py -- ★ (24-nov) EXPERIMENTAL: el server como ÁRBITRO del duelo 1 vs 1 (documentacion/PVP_PROTOTIPO.md).

Sólo con `config.PVP` (EDA_PVP=1). El combate lo hace el motor (P2P, sincronizado) cuando el guion de la arena pone a
los dos jugadores en grupos distintos (`SetEntityGroup`, PVP_SETENTITYGROUP.md). El server:
  · reconoce la partida de duelo por los eventos del guion de la arena: un 0x105C tipo 0 cuyo nombre empieza con
    «PvP_» (los manda la arena, herramientas/pvp/arena);
  · con el 0x1065 (`u8 jugador · u32 entidad que lo mató`, medido 24-nov) declara el ganador: no abre el cuadro de
    revivir, avisa por el chat y lo anota en `config.DUELOS`;
  · el fin (0x1064) de un duelo no paga: ni EXP, ni premio, ni puntos para cartas, y el AWARD sale vacío (vuelve a
    la sala por el camino medido, PROTOCOLO §5.14);
  · si uno se desconecta durante el duelo, gana el que queda.
Lo que no está: ranking, premios, sala de duelo propia (la pestaña Battle sigue cerrada).
"""
import json
import struct
import time

from servidor import config
from servidor.estado import ASIGNADAS, de_numero

PREFIJO = b"PvP_"
ESPERA_FIN = 25                     # s: si el guion no cierra la stage después de la muerte, game over → lobby


def evento_nombre(cuerpo):
    """El nombre de un 0x105C tipo 0 (`u32 tipo · u32 largo · texto · …`, PROTOCOLO §5.11), o None."""
    if len(cuerpo) < 8:
        return None
    tipo, largo = struct.unpack_from("<II", cuerpo, 0)
    if tipo != 0 or largo == 0 or largo > 64 or 8 + largo > len(cuerpo):
        return None
    return cuerpo[8:8 + largo]


def en_duelo(s):
    d = s.get("duelo") if s else None
    return bool(config.PVP and d and d.get("partida_id") == s.get("partida_id"))


def nombre(conexion):
    return ASIGNADAS.get(conexion) or "#%s" % conexion


def aviso(texto, destinos):
    from servidor.messenger import aviso as linea
    return [linea(texto, m, nombre="[Duelo]") for m in destinos]


def _vivo():
    from servidor.estado import VIVO                      # (sobrevive a la recarga del código)
    if not hasattr(VIVO, "PVP_DLL"):
        VIVO.PVP_DLL = set()                             # conexiones cuya dll entiende «[PVP]» (mandó «/pvp hola»)
    if not hasattr(VIVO, "PVP_PESTANA"):
        VIVO.PVP_PESTANA = {}                            # conexión → "batalla" | "escenario" (la pestaña del lobby)
    return VIVO


def comando(texto, conexion):
    """Lo que mandan las pestañas del lobby (la d3d9.dll con [pvp] batalla=1): «/batalla», «/escenario» y, al unir
    el lobby, «/pvp hola». Sólo «/batalla» contesta (al que la pidió)."""
    v = _vivo()
    cmd = texto.split()[0].lower()
    if cmd == "/pvp":
        if texto.lower().split()[1:2] == ["hola"]:
            v.PVP_DLL.add(conexion)
        return []
    if cmd == "/escenario":
        v.PVP_PESTANA[conexion] = "escenario"
        return []
    v.PVP_PESTANA[conexion] = "batalla"
    return comando_batalla(conexion)


def sala_nueva(s, conexion):
    """★ Una sala creada con la pestaña «Batalla PvP» elegida es una SALA DE DUELO (sólo con EDA_PVP)."""
    if config.PVP and _vivo().PVP_PESTANA.get(conexion) == "batalla":
        s["sala_pvp"] = True
        print("[duelo] sala de duelo creada por %s #%s" % (nombre(conexion), conexion), flush=True)


def marcador(s, conexion):
    """El aviso «[PVP] sala=duelo|normal» a la dll de quien crea o entra, ANTES del 0x101E / 0x1020: la dll sirve
    la sala con equipos sólo en una sala de duelo (eda_traduccion.c, capa pvp\\). Sólo a una dll que se presentó."""
    if not (config.PVP and conexion in _vivo().PVP_DLL):
        return []
    from servidor.messenger import aviso as linea
    return [linea("sala=duelo" if s.get("sala_pvp") else "sala=normal", conexion, nombre="[PVP]")]


def olvidar(conexion):
    v = _vivo()
    v.PVP_DLL.discard(conexion)
    v.PVP_PESTANA.pop(conexion, None)


def comando_batalla(conexion):
    """«/batalla» = lo que manda la pestaña «Batalla PvP» del lobby (la d3d9.dll con [pvp] batalla=1). Sin
    EDA_PVP contesta con el texto que el juego ya trae para eso (uistring 41: «Service Currently Not available»)."""
    if not config.PVP:
        return aviso("Servicio no disponible actualmente", [conexion])
    from servidor.estado import SALAS
    en_curso = [s for s in SALAS.values() if en_duelo(s) and s["duelo"].get("ganador") is None]
    lineas = ["Batalla PvP (experimental): %d duelo(s) en curso." % len(en_curso)]
    lineas += ["%s vs %s" % (nombre(d["duelo"]["jugadores"][0]), nombre(d["duelo"]["jugadores"][-1]))
               for d in en_curso[:3]]
    lineas.append("Para un duelo: Escenario, stage 1011 Easy, dos jugadores, con la arena instalada.")
    r = []
    for t in lineas:
        r += aviso(t, [conexion])
    return r


def ver_evento(s, conexion, cuerpo):
    """0x105C: el primer «PvP_*» de la partida la marca como duelo. Devuelve los avisos (o [])."""
    if not (config.PVP and s and s.get("jugando")) or en_duelo(s):
        return []
    n = evento_nombre(cuerpo)
    if not (n and n.startswith(PREFIJO)):
        return []
    jugadores = sorted(s.get("en_stage", set(s["miembros"])) & set(s["miembros"]))
    s["duelo"] = {"partida_id": s.get("partida_id"), "jugadores": jugadores, "inicio": time.time(), "ganador": None,
                  "equipos": {m: equipo(s, m) for m in jugadores}}
    print("[duelo] partida %s: duelo %s (por «%s» de #%s)" % (s.get("partida_id"), " vs ".join(
        "%s #%s (%s)" % (nombre(m), m, equipo(s, m)) for m in jugadores), n.decode("ascii", "replace"), conexion),
        flush=True)
    return aviso("Duelo: %s" % " vs ".join("%s (%s)" % (nombre(m), equipo(s, m)) for m in jugadores), jugadores)


def equipo(s, conexion):
    """★ El equipo = el número de sala % 2: la fila de la sala es el número (medido 24-nov) y la sala con equipos
    pinta las filas pares de rojo y las impares de azul; la arena pone el mismo grupo a los del mismo color."""
    from servidor.estado import numero
    return "rojo" if numero(s, conexion) % 2 == 0 else "azul"


def decidir(s, ganador, perdedor, por):
    d = s["duelo"]
    if d.get("ganador") is not None:
        return []
    d.update(ganador=ganador, perdedor=perdedor, por=por, fin=time.time())
    reg = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "partida": d.get("partida_id"), "ganador": nombre(ganador),
           "perdedor": nombre(perdedor), "por": por, "segundos": round(d["fin"] - d["inicio"], 1)}
    try:
        with open(config.DUELOS, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    except OSError as e:
        print("[duelo] no se pudo anotar en %s: %s" % (config.DUELOS, e), flush=True)
    print("[duelo] partida %s: gana %s #%s a %s #%s (%s)" % (d.get("partida_id"), nombre(ganador), ganador,
                                                         nombre(perdedor), perdedor, por), flush=True)
    texto = "Gana %s (%s)" % (nombre(ganador), "por KO" if por == "muerte" else "el otro se desconecto")
    return aviso(texto, [m for m in d["jugadores"] if m in s["miembros"]])


def muerte(s, conexion, cuerpo, p):
    """0x1065 en duelo: sin cuadro de revivir. El que mató = la entidad del cuerpo, que en la partida es el
    número de sala (medido 24-nov: rui 0, kai 1; los NPC empiezan en 256); si no calza, el otro del duelo."""
    d = s["duelo"]
    atacante = struct.unpack_from("<I", cuerpo, 1)[0] if len(cuerpo) >= 5 else None
    ganador = de_numero(s, atacante) if atacante is not None and atacante < 256 else None
    otros = [m for m in d["jugadores"] if m != conexion]
    if ganador is None or ganador == conexion or ganador not in d["jugadores"]:
        print("[duelo] el 0x1065 de #%s dice entidad %s: no es el otro jugador; gana %s"
              % (conexion, atacante, otros), flush=True)
        ganador = otros[0] if len(otros) == 1 else None
    p["game_over_en"] = time.time() + ESPERA_FIN          # red: si el guion no cierra la stage, al lobby
    if ganador is None:
        return []
    return decidir(s, ganador, conexion, "muerte")


def desconexion(s, conexion):
    """Se cortó uno de los dos durante el duelo: gana el que queda. Devuelve los avisos (salen con el tick)."""
    if not en_duelo(s) or conexion not in s["duelo"]["jugadores"]:
        return []
    otros = [m for m in s["duelo"]["jugadores"] if m != conexion and m in s["miembros"]]
    return decidir(s, otros[0], conexion, "desconexion") if len(otros) == 1 else []


def fin_de_uno(c, p, conexion, s):
    """El fin de la stage de un jugador en duelo: PlayEnd sin premio, resultado, cartas sin puntos y AWARD vacío
    enseguida (con 0 puntos no se puede elegir carta: el AWARD es lo que lleva de vuelta a la sala)."""
    from servidor.cuentas import guardar, nivel
    from servidor.datos import PRECIOS
    from servidor.partida import termino_su_stage
    inicio = p.get("inicio") or time.time()
    ms = int((time.time() - inicio) * 1000)
    c["partidas"] += 1
    guardar(c)
    p["puntos"] = 0
    p["premio"] = []
    p["cartas_hasta"] = None
    fin = (struct.pack("<HHIIHB", 1, c["monedas"], c["plata"], c["exp"], 0, nivel(c["exp"]))
           + struct.pack("<IIBB", 0, p.get("escenario") or 1011, 1, 1) + bytes([0, 0, 0]) + bytes([0]))
    gano = s["duelo"].get("ganador") == conexion
    resultado = struct.pack("<IHHHIIB", 0, 1 if gano else 0, p.get("golpes", 0), p.get("revividas", 0), ms, 0, 1)
    cartas = struct.pack("<IIII", 60000, *PRECIOS)
    termino_su_stage(s, conexion)
    return [(0x1073, fin, 0), (0x106E, resultado, 300), (0x106F, cartas, 8000),
            (0x1072, struct.pack("<IB", 0, 0), 9500)]
