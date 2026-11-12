r"""servidor/relay.py -- el MODO RELAY: jugadores en PCs distintas (ver `herramientas/relay_udp.py`).
"""
import json
import os
import re
import struct

from servidor import config
from servidor.estado import ASIGNADAS, SALAS, partida


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


def punch_de(conexion):
    """(IP como entero, puerto) PÚBLICOS con que el server de punch vio a ese jugador (su 0x3006, lo
    anota `herramientas/relay_udp.py` en punch.json), o None."""
    try:
        ip, puerto = json.load(open(config.PUNCH_MAPA)).get(str(conexion))
    except (OSError, ValueError, TypeError):
        return None
    return struct.unpack(">I", bytes(int(x) for x in ip.split(".")))[0], puerto


def publica_de(conexion):
    """(IP como entero, puerto) PÚBLICOS que el juego mandó en su 0x100F (los del 0x0609 que le dio
    `servidor/nat.py`), si son de verdad (no la 127.0.0.1 del 0x0609 viejo), y sólo con P2P entre
    casas. ★ La tiene también el ANFITRIÓN, que nunca pasa por el punch (§47, §53)."""
    if not config.P2P_ENTRE_CASAS or conexion is None:
        return None
    pub = partida(conexion).get("publica")
    if not pub or not pub[0] or pub[0] >> 24 == 127:
        return None
    return tuple(pub)


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
      · P2P DIRECTO (config.P2P = "directo", y los dos mandaron su MAC): la pública que vio el punch;
        si los dos tienen la MISMA IP pública (el mismo cíber, la misma casa), la PRIVADA (su 0x100F);
      · si no, su puerto en el RELAY (con relay); sin relay, lo de antes (127.0.0.1 + su puerto)."""
    if conexion is None:
        return None
    p = partida(conexion)
    if config.P2P == "directo" and mac_de(conexion) and (para is None or mac_de(para)):
        mio = punch_de(conexion) or publica_de(conexion)
        suyo = (punch_de(para) or publica_de(para)) if para is not None else None
        if para is not None and p.get("privada") and misma_casa(conexion, para, mio, suyo):
            return tuple(p["privada"])
        # ★ (MEDICIONES §52) la pública DIRECTA sólo si los DOS pasaron por el punch: si uno no (el
        #   anfitrión nunca manda su 0x3006, §47), quedaba MIXTO —uno le habla directo al otro y el otro
        #   por el relay—, y con un NAT de compañía (LTE, CGNAT) el directo no entra: los dos al relay
        if mio and (para is None or suyo):
            return mio
    r = relay()
    if r:
        return r[0], config.RELAY_BASE + 1 + conexion
    return p.get("udp")


def escribir_relay():
    """Lo que el relay necesita saber de cada conexión: su identidad inventada."""
    if relay():
        # la identidad inventada y la dirección UDP que el cliente declaró en su 0x100F (para la
        #   misma PC / LAN, de respaldo si su 0x3006 no llega)
        #   (con su MAC conocida, «falsa» = la real: el relay la deja como está)
        #   ★ y con quién está en SALA (MEDICIONES §47): el relay reconoce al que no se registró en el
        #   punch por descarte DENTRO de la sala del destino (entre todo el server suele haber varios)
        sala_de = {}
        for s in SALAS.values():
            for n in s["miembros"]:
                sala_de[n] = list(s["miembros"])
        json.dump({str(n): {"falsa": identidad_de(n), "udp": partida(n).get("udp"),
                            "sala": sala_de.get(n, [])}
                   for n in ASIGNADAS}, open(config.RELAY_MAPA, "w"))
