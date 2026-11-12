r"""servidor/nat.py -- la dirección PÚBLICA de cada juego, como en el original (MEDICIONES §53).

El original (PROTOCOLO §4.2–4.3): al conectarse, el Broker le manda al cliente el «UDP label»
(`0x0607`: IP · puerto); el cliente le manda ahí, por UDP y cada 0,4 s, su `0x3002` (la huella + su
IP:puerto LOCALES); el server ve de qué IP:puerto PÚBLICOS llega y se lo dice (`0x0609`: tipo de NAT ·
IP · puerto). El cliente guarda eso y lo manda en el `0x100F` (+0xE3 / +0xE7). Hasta acá contestábamos
un 0x0609 fijo («127.0.0.1»), así que nadie sabía la pública del ANFITRIÓN (que no pasa por el punch,
§47) y entre casas distintas todo iba al relay del VPS (Miami): ~300 ms medidos con una PC por LTE.

Con `config.P2P_ENTRE_CASAS` (y el relay prendido): el 0x0607 apunta al relay (su puerto de punch),
`herramientas/relay_udp.py` anota de dónde llegan los 0x3002 en `nat.json`, y `tick` contesta el
0x0609 con esa dirección. Si en `ESPERA` segundos no llegó ninguno, el 0x0609 de siempre (el juego
sigue igual; esa conexión va al relay).
"""
import json
import struct
import time

from servidor import config
from servidor.estado import PARTIDAS, partida
from servidor.relay import relay

ESPERA = 2.5                           # el juego espera el 0x0609 ~4 s antes de darse por bloqueado
TIPO_PUBLICO = 1                       # el tipo que contestábamos siempre (1 = «public»)
VIEJO = struct.pack("<B3xIH", TIPO_PUBLICO, 0x7F000001, 57654)   # el 0x0609 fijo de antes


def prendido():
    return config.P2P_ENTRE_CASAS and relay() is not None


def al_conectar(cuerpo, conexion):
    """El 0x0604 (la huella): el 0x0607 que lo manda a presentarse al relay. El 0x0609 sale después
    (`tick`), cuando el relay vio su 0x3002."""
    p = partida(conexion)
    p["nat_0604"] = bytes(cuerpo)
    p["nat_desde"] = time.time()
    ip, _ = relay()
    return [(0x0607, struct.pack("<IH", ip, config.RELAY_BASE), 0)]


def _vistos():
    try:
        return json.load(open(config.NAT_MAPA))
    except (OSError, ValueError):
        return {}


def _ip_int(t):
    return struct.unpack(">I", bytes(int(x) for x in t.split(".")))[0]


def texto(huella):
    """La parte que vale de la huella: el TEXTO UTF-16 hasta su 0 final (el usuario del launcher, p. ej.
    «99901»). ⚠ Medido en el server de prueba (13-nov): lo que sigue es basura que CAMBIA en cada 0x3002
    (tres envíos del mismo juego, tres huellas distintas), así que la huella entera no sirve."""
    for i in range(0, len(huella) - 1, 2):
        if huella[i:i + 2] == b"\0\0":
            return huella[:i]
    return huella


def buscar(p, vistos):
    """El 0x3002 de esta conexión: el texto de su huella está en el 0x0604 que mandó, y llegó DESPUÉS
    de él. Sin texto (un juego sin el login del launcher) la huella no distingue a nadie: ahí vale la
    misma IP que la conexión TCP. Devuelve (IP como entero, puerto) o None."""
    cuerpo, desde, ip_tcp = p.get("nat_0604", b""), p.get("nat_desde", 0), p.get("ip_tcp")
    mejor = None
    for huella, (ip, puerto, cuando) in vistos.items():
        h = texto(bytes.fromhex(huella))
        if cuando < desde - 1:
            continue
        if h and h in cuerpo or (not h and ip_tcp and ip == ip_tcp):
            if mejor is None or cuando > mejor[2]:
                mejor = (ip, puerto, cuando)
    return (_ip_int(mejor[0]), mejor[1]) if mejor else None


def tick(conexiones, ahora=None):
    """Los 0x0609 pendientes: con la pública que vio el relay, o el de siempre si no llegó."""
    ahora = time.time() if ahora is None else ahora
    r, vistos = [], None
    for n in conexiones:
        p = PARTIDAS.get(n)
        if not p or not p.get("nat_desde"):
            continue
        vistos = _vistos() if vistos is None else vistos
        publica = buscar(p, vistos)
        if publica:
            p.pop("nat_desde")
            r.append((0x0609, struct.pack("<B3xIH", TIPO_PUBLICO, publica[0], publica[1]), 0, n))
            print("#%s NAT: su dirección pública, la del 0x3002 (P2P entre casas)" % n, flush=True)
        elif ahora - p["nat_desde"] >= ESPERA:
            p.pop("nat_desde")
            r.append((0x0609, VIEJO, 0, n))
            print("#%s NAT: ningún 0x3002 en %.1f s → el 0x0609 de siempre (irá por el relay)" % (n, ESPERA),
                  flush=True)
    return r
