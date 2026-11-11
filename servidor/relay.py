r"""servidor/relay.py -- el MODO RELAY: jugadores en PCs distintas (ver `herramientas/relay_udp.py`).
"""
import json
import os
import re
import struct

from servidor import config
from servidor.estado import ASIGNADAS, partida


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


def identidad_de(conexion):
    if relay() and conexion is not None:
        return identidad_falsa(conexion)
    return identidad_p2p()


def dir_udp(conexion):
    """La dirección UDP que el server da de ese jugador: la suya, o su puerto en el relay."""
    r = relay()
    if r and conexion is not None:
        return r[0], config.RELAY_BASE + 1 + conexion
    return partida(conexion).get("udp") if conexion is not None else None


def escribir_relay():
    """Lo que el relay necesita saber de cada conexión: su identidad inventada."""
    if relay():
        # la identidad inventada y la dirección UDP que el cliente declaró en su 0x100F (para la
        #   misma PC / LAN, de respaldo si su 0x3006 no llega)
        json.dump({str(n): {"falsa": identidad_falsa(n), "udp": partida(n).get("udp")}
                   for n in ASIGNADAS}, open(config.RELAY_MAPA, "w"))
