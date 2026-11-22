r"""servidor/relay.py -- el MODO RELAY: jugadores en PCs distintas (ver `herramientas/relay_udp.py`).
"""
import json
import os
import re
import struct
import time

from servidor import config
from servidor.estado import ASIGNADAS, SALAS, partida

# ★ (22-nov) Cuánto dura vigente una dirección pública (0x3002 o 0x3006) sin renovarse por UDP: 300 s (5 min, el
#   mismo plazo de `nat.json` en `herramientas/relay_udp.py`). Medido en TEST (22-nov 16:05–16:33 UTC): el
#   anfitrión (#2) registró su 0x3002 a las 16:05:14 (puerto 2510) y no mandó más UDP en 28 min; a los 13 min su
#   router ya había vencido/cambiado el puerto y los demás seguían recibiendo el viejo (2510) → -1000 ms.
VENCE_PUBLICA = float(os.environ.get("EDA_VENCE_PUBLICA") or 300)


def identidad_p2p():
    """🟡 Atajo local (ver `miembro`): la MAC que el juego escribe en la 1ª línea de NetTrace.log."""
    import re
    try:
        with open(os.path.join(config.RAIZ, "_trabajo", "juego", "NetTrace.log"), "rb") as f:
            for linea in f.read(4096).splitlines():
                mm = re.search(rb"([0-9A-F]{2}(?::[0-9A-F]{2}){5})", linea)
                if mm:
                    return mm.group(1).decode()
    except OSError:
        pass
    return None


# ★★ MODO RELAY (para PCs distintas). El cliente NO le dice al server su identidad P2P (la MAC;
#   en el 0x100F aparece sólo a veces, como resto sucio de un buffer: MEDICIONES §30). Entonces el
#   server INVENTA una por jugador (con forma de MAC, 17 caracteres) y la pone en +0xA de su
#   miembro; como dirección de cada par da un puerto del RELAY (`herramientas/relay_udp.py`), que
#   reenvía cada datagrama cambiando la MAC real del que lo manda por la inventada. De paso
#   atraviesa cualquier NAT (cíber, LAN, simétrica): todo pasa por el server.
#   Se prende con EDA_RELAY_IP (la IP pública del server: así anda en Docker / Linux) o con el
#   archivo `<EDA_ESTADO>/modo_relay` (adentro: la IP del relay; vacío = 127.0.0.1). Puertos: el
#   del relay = RELAY_BASE (lo que va en el 0x1010) y RELAY_BASE + 1 + conexión para cada jugador.
def relay():
    """(IP como entero, puerto) del relay si el modo está prendido; si no, None."""
    if config.RELAY_IP:
        ip = config.RELAY_IP
    elif os.path.exists(config.RELAY_BANDERA):
        ip = open(config.RELAY_BANDERA).read().strip() or "127.0.0.1"
    else:
        return None
    return struct.unpack(">I", bytes(int(x) for x in ip.split(".")))[0], config.RELAY_BASE


def identidad_falsa(conexion):
    return "02:00:00:00:%02X:%02X" % ((conexion >> 8) & 0xFF, conexion & 0xFF)


def mac_de(conexion):
    """La MAC que mandó en su 0x100F (= su identidad P2P), o None (juego lanzado sin comillas)."""
    return partida(conexion).get("mac") if conexion is not None else None


def identidad_de(conexion):
    """★ La identidad P2P que va en +0xA de su miembro: su MAC de verdad si la mandó (así los saludos
    se reconocen sin que nadie los toque); si no, la inventada del relay (que reescribe sus saludos);
    sin relay, la de esta PC (el atajo local de antes)."""
    if mac_de(conexion):
        return mac_de(conexion)
    if relay() and conexion is not None:
        return identidad_falsa(conexion)
    return identidad_p2p()


def punch_info(conexion, ahora=None):
    """(IP como entero, puerto, hora) PÚBLICOS con que el server de punch vio a ese jugador (su 0x3006 o el
    relay, en punch.json), sólo si es de ESTA sesión y no venció (`VENCE_PUBLICA`); o None."""
    try:
        e = json.load(open(config.PUNCH_MAPA)).get(str(conexion))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(e, list) or len(e) < 3:
        return None
    desde = (partida(conexion).get("desde") or 0) if conexion is not None else 0
    ahora = time.time() if ahora is None else ahora
    if e[2] < desde - 1 or (VENCE_PUBLICA > 0 and ahora - e[2] > VENCE_PUBLICA):
        return None
    return struct.unpack(">I", bytes(int(x) for x in e[0].split(".")))[0], e[1], float(e[2])


def punch_de(conexion, ahora=None):
    """(IP como entero, puerto) PÚBLICOS con que el server de punch vio a ese jugador (su 0x3006, lo
    anota `herramientas/relay_udp.py` en punch.json), o None.
    ★ (21-nov) Sólo si es de ESTA sesión: punch.json va por número de conexión y los números se reusan
    mientras el relay sigue andando. Medido en el server de prueba (21-nov 05:35 UTC): para la conexión 1
    decía el puerto 19745, visto a las 04:26 en OTRA sesión; el anfitrión de esta salía por el 18113, y al
    invitado se le dio el viejo → -1000 ms. Ahora cada entrada lleva su hora y vale sólo si es posterior al
    comienzo de la sesión (`desde`) y no venció (`VENCE_PUBLICA`)."""
    info = punch_info(conexion, ahora=ahora)
    return (info[0], info[1]) if info else None


def publica_info(conexion, ahora=None):
    """(IP como entero, puerto, hora) PÚBLICOS del 0x3002 (el más reciente entre `nat.json` de esta sesión y
    lo que el juego mandó en su 0x100F), si son de verdad (no 127.0.0.1), no vencieron (`VENCE_PUBLICA`), y
    sólo con P2P entre casas."""
    if not config.P2P_ENTRE_CASAS or conexion is None:
        return None
    ahora = time.time() if ahora is None else ahora
    p = partida(conexion)
    cand = None
    pub = p.get("publica")
    if pub and pub[0] and pub[0] >> 24 != 127:
        if p.get("publica_vista") != tuple(pub):
            p["publica_vista"] = tuple(pub)
            p["publica_desde"] = ahora
        t_pub = p.get("publica_desde") or p.get("desde") or ahora
        if VENCE_PUBLICA <= 0 or ahora - t_pub <= VENCE_PUBLICA:
            cand = (pub[0], pub[1], float(t_pub))
    if p.get("nat_0604"):
        from servidor import nat
        m = nat.buscar_con_hora(p)
        if m and m[0] and m[0] >> 24 != 127 and (VENCE_PUBLICA <= 0 or ahora - m[2] <= VENCE_PUBLICA):
            if cand is None or m[2] >= cand[2]:
                cand = m
    return cand


def publica_de(conexion, ahora=None):
    """(IP como entero, puerto) PÚBLICOS que el juego mandó en su 0x100F (o su 0x3002 más reciente en
    `nat.json`), si son de verdad (no la 127.0.0.1 del 0x0609 viejo), vigentes y sólo con P2P entre
    casas. ★ La tiene también el ANFITRIÓN (§47, §53)."""
    info = publica_info(conexion, ahora=ahora)
    return (info[0], info[1]) if info else None


def actual_de(conexion, ahora=None):
    """★ (22-nov) La dirección pública MÁS RECIENTE y vigente de `conexion`: compara la hora del punch/relay
    (`punch_info`) y la del 0x3002 (`publica_info`) y devuelve la más nueva, o None si no hay o venció."""
    a, b = punch_info(conexion, ahora=ahora), publica_info(conexion, ahora=ahora)
    if a and b:
        return (a[0], a[1]) if a[2] >= b[2] else (b[0], b[1])
    info = a or b
    return (info[0], info[1]) if info else None


def marcar_sin_directo(a, b):
    """★ (22-nov) Marca que el P2P directo entre `a` y `b` falló en esta sesión (p. ej. el cliente avisó
    0x105A con -1000 ms) → la pareja pasa automáticamente al relay en los dos sentidos."""
    if a is not None and b is not None and a != b:
        partida(a).setdefault("sin_directo", set()).add(b)
        partida(b).setdefault("sin_directo", set()).add(a)


def sin_directo(a, b):
    """¿El par `a`–`b` tiene el directo marcado como fallido en esta sesión?"""
    if a is None or b is None:
        return False
    return b in partida(a).get("sin_directo", ()) or a in partida(b).get("sin_directo", ())


def misma_casa(a, b, punch_a=None, punch_b=None):
    """¿`a` y `b` salen a internet por la MISMA IP pública (la misma casa, el mismo cíber)? Por la IP
    con que se conectaron al server (`ip_tcp`, la anota `servidor/red.py`) o, si no, por la que vio el
    punch. ★ MEDICIONES §52: el ANFITRIÓN nunca manda su 0x3006 (§47), así que con sólo el punch no
    se sabía nunca, y dos PCs de la misma casa terminaban en el relay (con -1000 ms)."""
    ia, ib = partida(a).get("ip_tcp"), partida(b).get("ip_tcp")
    if ia and ib and not ia.startswith("127.") and not ib.startswith("127."):
        return ia == ib
    return bool(punch_a and punch_b and punch_a[0] == punch_b[0])


def dir_udp(conexion, para=None):
    """★ La dirección UDP de `conexion` que el server le da a `para` (MEDICIONES §40):
      · P2P DIRECTO (config.P2P = "directo", los dos mandaron su MAC y no falló el directo entre ellos):
        la pública MÁS RECIENTE y vigente (`actual_de`); si los dos tienen la MISMA IP pública (el mismo
        cíber, la misma casa), la PRIVADA (su 0x100F);
      · si no (sin directo, sin UDP vigente o con relay), su puerto en el RELAY; sin relay, 127.0.0.1."""
    if conexion is None:
        return None
    p = partida(conexion)
    if config.P2P == "auto" and relay() and para is not None:
        return _dir_auto(conexion, para)
    if (config.P2P == "directo" and mac_de(conexion) and (para is None or mac_de(para))
            and not sin_directo(conexion, para)):
        mio = actual_de(conexion)
        suyo = actual_de(para) if para is not None else None
        if para is not None and p.get("privada") and misma_casa(conexion, para, mio, suyo):
            return tuple(p["privada"])
        # ★ (MEDICIONES §52) la pública DIRECTA sólo si los DOS tienen dirección pública vigente: si uno no
        #   (o ya venció), quedaría MIXTO o al puerto viejo → los dos al relay
        if mio and (para is None or suyo):
            return mio
    r = relay()
    if r:
        return r[0], config.RELAY_BASE + 1 + conexion
    return p.get("udp")


def udp_para_relay(n):
    """★ (22-nov) La dirección UDP de `n` que va a `relay.json`:
      · si el server conoce su dirección pública vigente (`actual_de`: 0x3006 o 0x3002), ésa;
      · si se conectó desde la misma PC (127.x, o sin `ip_tcp` en pruebas locales), su `udp` local (127.0.0.1);
      · si viene de otra PC y no tiene pública vigente, None (nunca `[2130706433, 57654]` en el VPS)."""
    pub = actual_de(n)
    if pub:
        return list(pub)
    ip_tcp = partida(n).get("ip_tcp")
    if not ip_tcp or ip_tcp.startswith("127."):
        u = partida(n).get("udp")
        return list(u) if u else None
    return None


def escribir_relay():
    """Lo que el relay necesita saber de cada conexión: su identidad inventada."""
    if relay():
        # la identidad inventada y la dirección UDP conocida (la pública vigente si viene de internet;
        #   127.0.0.1 + su puerto sólo para la misma PC, de respaldo si su 0x3006 no llega)
        #   (con su MAC conocida, «falsa» = la real: el relay la deja como está)
        #   ★ y con quién está en SALA (MEDICIONES §47): el relay reconoce al que no se registró en el
        #   punch por descarte DENTRO de la sala del destino (entre todo el server suele haber varios)
        sala_de = {}
        for s in SALAS.values():
            for n in s["miembros"]:
                sala_de[n] = list(s["miembros"])
        json.dump({str(n): {"falsa": identidad_de(n), "udp": udp_para_relay(n),
                            "sala": sala_de.get(n, []),
                            # ★ (21-nov) desde cuándo es esta sesión: con un número reusado, el relay
                            #   olvida la dirección que aprendió de la sesión anterior
                            "desde": partida(n).get("desde")}
                   for n in ASIGNADAS}, open(config.RELAY_MAPA, "w"))


def estable(conexion):
    """★ (21-nov) ¿La dirección pública de `conexion` es CONFIABLE para el directo? Su 0x3006 (punch, de ESTA
    sesión) y su 0x3002 (la pública del 0x100F) salieron por el MISMO puerto público: su NAT mantiene el puerto."""
    a, b = punch_de(conexion), publica_de(conexion)
    return bool(a and b and a == b)


def ruta(a, b):
    """★ (21-nov) El camino de la PAREJA a–b, el MISMO en los dos sentidos (nunca uno directo y el otro por el
    relay): «casa» (las privadas: misma IP pública), «directo» (las públicas, sólo si las dos son confiables:
    `estable`) o «relay». Con EDA_P2P=auto."""
    if not (mac_de(a) and mac_de(b)) or sin_directo(a, b):
        return "relay"
    pa, pb = partida(a), partida(b)
    if pa.get("privada") and pb.get("privada") and misma_casa(a, b, actual_de(a), actual_de(b)):
        return "casa"
    if estable(a) and estable(b):
        return "directo"
    return "relay"


def _dir_auto(conexion, para):
    camino = ruta(conexion, para)
    p = partida(conexion)
    if camino == "casa":
        return tuple(p["privada"])
    if camino == "directo":
        return actual_de(conexion)
    return relay()[0], config.RELAY_BASE + 1 + conexion

